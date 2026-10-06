"""Explicit research-process-v1 executor, independent of the text-only ChatProvider.

An operator-installed trusted worker implements the documented protocol. Each child is
a separate process with its own identity and bounded assignment. The parent process
remains alive between planning and integration. The bundled worker is an OFFLINE FAKE,
not a model; process handoffs alone are not evidence of live model-agent delegation.
"""

import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from ..config import get_settings
from ..research_contract import Capabilities
from .research_model_policy import role_selection

MAX_MESSAGE = 2_000_000
MAX_TRANSCRIPT = 8_000_000


class ExecutorError(ValueError):
    pass


class AgentProcess:
    def __init__(self, command: list[str], agent_id: str, worker_config: dict[str, str]):
        self.agent_id = agent_id
        self.worker_pid = None
        self.events: queue.Queue = queue.Queue(maxsize=100)
        self.closed = threading.Event()
        self.scratch = tempfile.TemporaryDirectory(prefix="wb-research-agent-")
        # Do not hand worker processes the app's credentials, local gate or .env.
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC"}
        }
        env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", WB_LOAD_DOTENV="false")
        env.update(worker_config)
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=self.scratch.name,
                env=env,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
            )
        except (OSError, ValueError):
            self.scratch.cleanup()
            raise ExecutorError("research worker could not start") from None
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    @property
    def pid(self):
        return self.process.pid

    def _emit(self, event):
        # Apply backpressure without losing terminal reports or usage. The reader
        # must also wake when cancellation closes a full queue.
        while not self.closed.is_set():
            try:
                self.events.put(event, timeout=0.1)
                return
            except queue.Full:
                continue

    def _read(self):
        total = 0
        try:
            while not self.closed.is_set():
                line = self.process.stdout.readline(MAX_MESSAGE + 1)
                if not line:
                    self._emit({"type": "transport_error"})
                    return
                total += len(line)
                if len(line) > MAX_MESSAGE or total > MAX_TRANSCRIPT:
                    self._emit({"type": "transport_error"})
                    return
                event = json.loads(line)
                if not isinstance(event, dict) or event.get("agent_id") != self.agent_id:
                    self._emit({"type": "transport_error"})
                    return
                self._emit(event)
        except (OSError, ValueError, UnicodeError):
            self._emit({"type": "transport_error"})

    def send(self, operation: str, payload: dict):
        data = (json.dumps({"op": operation, "agent_id": self.agent_id, **payload}) + "\n").encode()
        if len(data) > MAX_MESSAGE:
            raise ExecutorError("research context exceeds the worker message limit; narrow the sources")

        def write():
            try:
                self.process.stdin.write(data)
                self.process.stdin.flush()
            except (OSError, ValueError):
                self._emit({"type": "transport_error"})

        threading.Thread(target=write, daemon=True).start()

    def poll(self) -> dict | None:
        try:
            return self.events.get_nowait()
        except queue.Empty:
            if self.closed.is_set():
                return {"type": "transport_error"}
            return None

    def close(self):
        self.closed.set()
        if self.process.poll() is None:
            # Kill the owned process tree, not arbitrary command text supplied by a task.
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=5,
                    check=False,
                )
            else:
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.process.kill()
        self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        for stream in (self.process.stdin, self.process.stdout):
            try:
                stream.close()
            except OSError:
                pass
        self.scratch.cleanup()


class ProcessResearchExecutor:
    def __init__(self, mode: str, command: list[str] | None = None, *, allow_best_effort_tokens=False):
        settings = get_settings()
        if settings.deployment_mode != "local":
            raise ExecutorError("research execution v1 requires a persistent local application")
        self.mode = mode
        self.allow_best_effort_tokens = allow_best_effort_tokens
        self.role_policy = {role: (selection.model_dump() if hasattr(selection, "model_dump") else selection)
                            for role, selection in settings.research_codex_role_policy.items()}
        self.worker_config = {
            "WB_RESEARCH_CODEX_HOME": settings.research_codex_home,
            "WB_RESEARCH_CODEX_ACCOUNT_EMAIL": settings.research_codex_account_email,
            "WB_RESEARCH_CODEX_MODEL": settings.research_codex_model,
            "WB_RESEARCH_CODEX_REASONING_EFFORT": settings.research_codex_reasoning_effort,
            "WB_RESEARCH_CODEX_ROLE_POLICY": json.dumps(self.role_policy),
        } if mode == "process" else {}
        if mode == "offline":
            self.command = [sys.executable, str(Path(__file__).with_name("research_offline_worker.py"))]
        elif mode == "process" and settings.research_executor_enabled and settings.research_executor_command:
            self.command = list(settings.research_executor_command)
        else:
            raise ExecutorError("live research executor is not configured; text-only chat cannot delegate")
        # Explicit injection is used by offline tests, never accepted from an HTTP request.
        if command is not None:
            self.command = command
        if not Path(self.command[0]).is_absolute():
            raise ExecutorError("research executor executable must be an absolute operator-configured path")
        self.handles: list[AgentProcess] = []
        self.capabilities: dict = {}

    def spawn(self, agent_id: str, *, deadline: float, role="research") -> AgentProcess:
        selection = role_selection(role, self.role_policy,
            model=self.worker_config.get("WB_RESEARCH_CODEX_MODEL", "gpt-5.5"),
            effort=self.worker_config.get("WB_RESEARCH_CODEX_REASONING_EFFORT", "low"))
        handle = AgentProcess(self.command, agent_id, {**self.worker_config, "WB_RESEARCH_CODEX_ROLE": role})
        handle.requested_model_policy = {"role": role, **selection}
        self.handles.append(handle)
        handle.send("hello", {})
        until = min(deadline, time.monotonic() + 20)
        while time.monotonic() < until:
            event = handle.poll()
            if event:
                if event.get("type") != "capabilities":
                    raise ExecutorError("research worker did not provide capabilities")
                try:
                    caps = Capabilities.model_validate(event.get("capabilities")).model_dump()
                except ValueError:
                    raise ExecutorError(
                        "worker lacks required delegation or hard-budget capabilities"
                    ) from None
                if caps["simulated"] != (self.mode == "offline"):
                    raise ExecutorError("worker simulation mode does not match the selected executor")
                if not caps["hard_total_token_limit"] and (
                    not caps["best_effort_token_stopping"] or not self.allow_best_effort_tokens
                ):
                    raise ExecutorError("best-effort token stopping needs explicit task opt-in")
                if self.capabilities and caps != self.capabilities:
                    raise ExecutorError("child executor capabilities differ from the parent")
                self.capabilities = caps
                self_pid = event.get("worker_pid")
                if isinstance(self_pid, int) and self_pid > 0:
                    handle.worker_pid = self_pid
                return handle
            time.sleep(0.01)
        raise ExecutorError("research worker capability handshake timed out")

    def close(self):
        for handle in self.handles:
            try:
                handle.close()
            except (OSError, subprocess.SubprocessError):
                # Continue cancelling all other children even if one process disappeared.
                pass


def availability() -> dict:
    settings = get_settings()
    return {
        "offline": {
            "available": settings.deployment_mode == "local",
            "simulated": True,
            "description": "Controlled offline workers; no model research or spending.",
        },
        "process": {
            "available": bool(
                settings.deployment_mode == "local"
                and settings.research_executor_enabled
                and settings.research_executor_command
            ),
            "simulated": False,
            "description": "Requires an operator-installed research-process-v1 agent worker. "
            "Capabilities are checked before any research.",
        },
        "chat_provider_delegation": False,
    }
