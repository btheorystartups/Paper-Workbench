"""Supervised Responses SDK transport for data-only mock fixtures.

The wire protocol is real; the only installed HTTP transport is MockTransport.
No environment setting, model name or caller-supplied executable enables live mode.
Process ownership is a timeout boundary, not an OS filesystem sandbox.
"""

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ..services.evaluation import Denied, digest, encoded

SDK_VERSION = "2.46.0"
MAX_BYTES = 1_000_000


class MockResponsesProcess:
    def __init__(self, frames, *, mode="mock"):
        if mode != "mock" or type(frames) is not list or not 1 <= len(frames) <= 102:
            raise Denied("live Responses execution unavailable")
        try:
            if version("openai") != SDK_VERSION:
                raise Denied("reviewed evaluation SDK required")
        except PackageNotFoundError:
            raise Denied("install the optional evaluation dependency before dispatch") from None
        self._fixtures = encoded(frames)
        if len(self._fixtures) >= MAX_BYTES:
            raise Denied("fixture exceeds transport limit")
        self._proc = None
        self._scratch = None
        self._reader = None
        self._closed = threading.Event()
        self._events = queue.Queue(maxsize=2)
        self._sequence = 0

    def start(self, *, deadline, cancel):
        self._scratch = tempfile.TemporaryDirectory(prefix="wb-evaluation-responses-")
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
            }
        }
        env.update(
            HOME=self._scratch.name,
            USERPROFILE=self._scratch.name,
            PYTHONDONTWRITEBYTECODE="1",
            WB_LOAD_DOTENV="false",
        )
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-I", "-B", str(Path(__file__).with_name("evaluation_responses_worker.py"))],
                cwd=self._scratch.name,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._reader = threading.Thread(target=self._read, daemon=True)
            self._reader.start()
            self._write(self._fixtures + b"\n", deadline, cancel)
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            while not self._closed.is_set():
                line = self._proc.stdout.readline(MAX_BYTES + 1)
                if not line or len(line) > MAX_BYTES:
                    break
                self._events.put_nowait(json.loads(line))
        except Exception:
            pass
        finally:
            self._closed.set()

    def _check(self, deadline, cancel):
        if cancel.is_set() or time.monotonic() >= deadline:
            raise Denied("transport cancelled or deadline reached")

    def _write(self, data, deadline, cancel):
        failed = threading.Event()

        def write():
            try:
                self._proc.stdin.write(data)
                self._proc.stdin.flush()
            except Exception:
                failed.set()

        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        while writer.is_alive():
            self._check(deadline, cancel)
            writer.join(0.02)
        if failed.is_set():
            raise Denied("transport closed")

    def exchange(self, operation, *, attempt_id, deadline, cancel, body=None, response_id=None):
        self._check(deadline, cancel)
        if self._sequence >= 102:
            raise Denied("transport request limit reached")
        self._sequence += 1
        operation_id = f"{attempt_id}-{self._sequence}"
        message = {
            "operation": operation,
            "operation_id": operation_id,
            "body": body,
            "response_id": response_id,
        }
        data = encoded(message)
        if len(data) >= MAX_BYTES:
            raise Denied("request exceeds transport limit")
        self._write(data + b"\n", deadline, cancel)
        while True:
            self._check(deadline, cancel)
            try:
                reply = self._events.get(timeout=0.02)
            except queue.Empty:
                if self._closed.is_set():
                    raise Denied("transport closed before receipt") from None
                continue
            if (
                type(reply) is not dict
                or reply.get("operation_id") != operation_id
                or reply.get("sdk") != SDK_VERSION
            ):
                raise Denied("transport identity mismatch")
            observed = reply.get("observed")
            if (
                type(observed) is not list
                or len(observed) != 1
                or type(observed[0]) is not dict
                or observed[0].get("client_request_id") != operation_id
                or observed[0].get("retry_count") != "0"
                or observed[0].get("method") != ("GET" if operation == "retrieve" else "POST")
                or observed[0].get("path")
                != (
                    "/v1/responses"
                    if operation == "create"
                    else "/v1/responses/input_tokens"
                    if operation == "count"
                    else f"/v1/responses/{response_id}" + ("/cancel" if operation == "cancel" else "")
                )
                or observed[0].get("body_sha256")
                != digest(encoded(body if operation in {"create", "count"} else {}))
            ):
                raise Denied("transport request identity or retry mismatch")
            return reply

    def close(self):
        self._closed.set()
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=2)
            if self._reader:
                self._reader.join(timeout=1)
            for stream in (self._proc.stdin, self._proc.stdout):
                if stream:
                    stream.close()
        if self._scratch:
            self._scratch.cleanup()
