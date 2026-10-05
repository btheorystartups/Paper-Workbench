"""Bounded stdio transport for the documented Codex app-server JSON-RPC API.

Uses the official SDK's pinned CLI distribution. No interactive conversation,
credential-file access, shell transport, inherited API keys, or inherited gate.
"""

import json
import os
import queue
import subprocess
import threading
import time
from importlib.metadata import version

from .codex_access import CodexLocalError, CodexTimeoutError

RUNTIME_VERSION = "0.154.0"


class StdioCodexClient:
    def __init__(self, *, profile: str, cwd: str, overrides: dict, cancel: threading.Event,
                 server_request_handler=None):
        self._cancel = cancel
        self._server_request_handler = server_request_handler
        self._proc = None
        self._reader = None
        self._closed = threading.Event()
        self._queue: queue.Queue = queue.Queue(maxsize=64)
        self._pending: list[dict] = []
        self._sequence = 0
        self._deadline = time.monotonic() + 10
        try:
            if version("openai-codex-cli-bin") != RUNTIME_VERSION:
                raise CodexLocalError("codex_local requires the pinned optional SDK runtime")
            from codex_cli_bin import bundled_codex_path

            command = [str(bundled_codex_path())]
            for key, value in overrides.items():
                command.extend(["--config", f"{key}={json.dumps(value)}"])
            command.extend(["app-server", "--listen", "stdio://"])
            # An allowlist avoids passing gate/API keys or ambient provider overrides.
            env = {key: value for key, value in os.environ.items() if key.upper() in {
                "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "LANG", "LC_ALL",
            }}
            env.update({"CODEX_HOME": profile, "HOME": cwd, "USERPROFILE": cwd})
            self._proc = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, cwd=cwd, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._reader = threading.Thread(target=self._read, daemon=True)
            self._reader.start()
        except CodexLocalError:
            self.close()
            raise
        except Exception:
            self.close()
            raise CodexLocalError("codex_local runtime could not start; install the optional SDK") from None

    def _read(self):
        try:
            while not self._closed.is_set():
                line = self._proc.stdout.readline(8_000_001)
                if not line or len(line) > 8_000_000:
                    break
                message = json.loads(line)
                if not isinstance(message, dict):
                    break
                while not self._closed.is_set():
                    try:
                        self._queue.put(message, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        except Exception:
            pass  # never propagate raw subprocess data or diagnostic text
        finally:
            self._closed.set()

    def send(self, method, params=None):
        self._sequence += 1
        message = {"id": self._sequence, "method": method, "params": params or {}}
        self._write(message)
        return self._sequence

    def notify(self, method, params=None):
        self._write({"method": method, "params": params or {}})

    def _write(self, message):
        failed = threading.Event()

        def write():
            try:
                self._proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
                self._proc.stdin.flush()
            except Exception:
                failed.set()

        # A hung runtime must not make a large stdin write wait forever.
        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        while writer.is_alive():
            if self._cancel.is_set():
                raise CodexLocalError("codex_local request cancelled")
            if time.monotonic() >= self._deadline:
                raise CodexTimeoutError("codex_local request timed out")
            writer.join(timeout=0.05)
        if failed.is_set():
            raise CodexLocalError("codex_local transport closed")

    def _next(self, deadline):
        while True:
            if self._cancel.is_set():
                raise CodexLocalError("codex_local request cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexTimeoutError("codex_local request timed out")
            try:
                message = self._queue.get(timeout=min(0.1, remaining))
            except queue.Empty:
                if self._closed.is_set():
                    raise CodexLocalError("codex_local transport closed") from None
                continue
            if "method" in message and "id" in message:
                handler = getattr(self, "_server_request_handler", None)
                result = handler(message) if handler else None
                if result is not None:
                    self._deadline = deadline
                    self._write({"id": message["id"], "result": result})
                    continue
                # Default deny, including approvals, token refresh and user input.
                self._write({"id": message["id"], "error": {
                    "code": -32601, "message": "Unsupported by this text-only client",
                }})
                raise CodexLocalError("codex_local requested an unsupported client capability")
            return message

    def request(self, method, params, *, deadline):
        self._deadline = deadline
        request_id = self.send(method, params)
        while True:
            message = self._next(deadline)
            if message.get("id") == request_id:
                if "error" in message or not isinstance(message.get("result"), dict):
                    raise CodexLocalError("codex_local rejected the requested operation")
                return message["result"]
            if len(self._pending) >= 256:
                raise CodexLocalError("codex_local exceeded the pending event limit")
            self._pending.append(message)

    def event(self, *, deadline):
        if self._cancel.is_set():
            raise CodexLocalError("codex_local request cancelled")
        if time.monotonic() >= deadline:
            raise CodexTimeoutError("codex_local request timed out")
        return self._pending.pop(0) if self._pending else self._next(deadline)

    def close(self):
        self._closed.set()
        proc = self._proc
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            for stream in (proc.stdin, proc.stdout):
                if stream:
                    stream.close()
        if self._reader is not None:
            self._reader.join(timeout=0.5)
