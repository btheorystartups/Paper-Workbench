"""Fixed offline SDK worker. No live mode, credentials, plugin imports or tools."""

import hashlib
import json
import platform
import socket
import sys
import time
from collections import namedtuple

MAX_BYTES = 1_000_000
SDK_VERSION = "2.46.0"


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def deny(*args, **kwargs):
    raise RuntimeError("network disabled")


def main():
    # Even an accidentally introduced ordinary HTTP transport cannot connect.
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    socket.getaddrinfo = deny
    # Mock requests need no host fingerprint or Windows WMI/version subprocess.
    host = namedtuple("SyntheticHost", "system node release version machine processor")
    platform.uname = lambda: host("Windows", "offline", "10", "10", "AMD64", "")
    import httpx
    import openai

    if openai.__version__ != SDK_VERSION:
        raise RuntimeError("SDK version not reviewed")
    line = sys.stdin.buffer.readline(MAX_BYTES + 1)
    if len(line) > MAX_BYTES:
        raise ValueError("fixture exceeds limit")
    fixtures = json.loads(line)
    if type(fixtures) is not list or not 1 <= len(fixtures) <= 102:
        raise ValueError("invalid fixture")
    index = 0
    observed = []

    def handler(request):
        nonlocal index
        frame = fixtures[index]
        index += 1
        if request.headers.get("authorization") != "Bearer offline-placeholder":
            raise RuntimeError("unexpected authentication material")
        observed.append(
            {
                "method": request.method,
                "path": request.url.path,
                "client_request_id": request.headers.get("x-client-request-id"),
                "retry_count": request.headers.get("x-stainless-retry-count"),
                "body_sha256": hashlib.sha256(encode(json.loads(request.content or b"{}"))).hexdigest(),
            }
        )
        if frame.get("fault") == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        if frame.get("fault") == "hang":
            time.sleep(3600)  # supervisor must terminate the owned process
        if frame.get("fault") == "exit":
            sys.exit(17)
        return httpx.Response(
            frame.get("http_status", 200),
            json=frame.get("body", {}),
            headers={
                "x-request-id": frame.get("http_request_id", "req_synthetic"),
                **({"location": frame["redirect_location"]} if "redirect_location" in frame else {}),
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http:
        with openai.OpenAI(
            api_key="offline-placeholder",
            organization="offline",
            project="offline",
            base_url="https://api.openai.com/v1",
            http_client=http,
            max_retries=0,
            timeout=httpx.Timeout(10, connect=2),
        ) as client:
            for _ in range(102):
                line = sys.stdin.buffer.readline(MAX_BYTES + 1)
                if not line:
                    return
                if len(line) > MAX_BYTES:
                    raise ValueError("request exceeds limit")
                message = json.loads(line)
                observed.clear()
                kwargs = {"extra_headers": {"X-Client-Request-Id": message["operation_id"]}}
                try:
                    operation = message["operation"]
                    if operation == "count":
                        result = client.responses.input_tokens.count(**message["body"], **kwargs)
                    elif operation == "create":
                        result = client.responses.create(**message["body"], **kwargs)
                    elif operation == "retrieve":
                        result = client.responses.retrieve(message["response_id"], **kwargs)
                    elif operation == "cancel":
                        result = client.responses.cancel(message["response_id"], **kwargs)
                    else:
                        raise ValueError("operation denied")
                    reply = {"body": result.model_dump(mode="json"), "http_request_id": result._request_id}
                except Exception as exc:
                    reply = {
                        "error": "provider outcome uncertain",
                        "http_request_id": exc.request_id if isinstance(exc, openai.APIStatusError) else None,
                    }
                reply.update(operation_id=message["operation_id"], observed=observed, sdk=SDK_VERSION)
                data = encode(reply)
                if len(data) > MAX_BYTES:
                    raise ValueError("response exceeds limit")
                sys.stdout.buffer.write(data + b"\n")
                sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never print provider response bodies, environment or raw SDK exceptions.
        sys.exit(2)
