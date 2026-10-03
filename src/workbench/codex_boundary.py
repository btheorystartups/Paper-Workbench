"""ASGI boundary: transient gate authorization and disconnect cancellation."""

import asyncio
import threading
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from .config import get_settings
from .providers.codex_access import CodexLocalError, gate_scope, is_loopback, validate_configuration
from .providers.codex_local import request_cancel


class CodexLocalBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        settings = get_settings()
        if scope["type"] != "http" or settings.llm_provider != "codex_local":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        host = headers.get("host", "")
        host_name = urlsplit("http://" + host).hostname
        origin = headers.get("origin")
        local = (
            is_loopback((scope.get("client") or (None,))[0])
            and is_loopback((scope.get("server") or (None,))[0])
            and (is_loopback(host_name) or host_name == "localhost")
            and (not origin or origin == scope.get("scheme", "http") + "://" + host)
            and not any(name in headers for name in ("forwarded", "x-forwarded-for", "x-forwarded-host"))
        )
        try:
            validate_configuration(settings)
            if not local:
                raise CodexLocalError("codex_local refuses non-local or proxied requests")
        except CodexLocalError as exc:
            return await JSONResponse({"detail": str(exc)}, status_code=exc.status_code)(scope, receive, send)
        cancel = threading.Event()
        token = request_cancel.set(cancel)
        messages: asyncio.Queue = asyncio.Queue(maxsize=4)

        async def pump():
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    cancel.set()
                await messages.put(message)
                if message["type"] == "http.disconnect":
                    return

        task = asyncio.create_task(pump())
        async def no_store(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() != b"cache-control"
                ] + [(b"cache-control", b"no-store")]}
            await send(message)

        try:
            with gate_scope(headers.get("x-workbench-codex-gate"), local_request=local, settings=settings):
                # Downstream routes cannot accidentally log or persist this header.
                safe_scope = {**scope, "headers": [
                    (key, value) for key, value in scope.get("headers", [])
                    if key.lower() != b"x-workbench-codex-gate"
                ]}
                await self.app(safe_scope, messages.get, no_store)
        finally:
            cancel.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            request_cancel.reset(token)
