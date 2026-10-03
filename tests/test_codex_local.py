"""No network, credentials or model calls: injected app-server and tokenizer."""

import asyncio
import json
import threading
import time

import pytest

from workbench.config import Settings
from workbench.providers import codex_access, codex_local, registry
from workbench.providers.codex_access import (
    CodexGateError,
    CodexLimitError,
    CodexLocalError,
    CodexTimeoutError,
    gate_scope,
)
from workbench.providers.codex_rpc import RUNTIME_VERSION, StdioCodexClient

GATE = "test-gate-only-not-a-real-secret-123456789"
OWNER = "local-user@example.test"


class TextEncoding:
    """One Unicode character per application test token; no tokenizer download."""

    def encode(self, text, **kwargs):
        return list(text)

    def decode(self, tokens):
        return "".join(tokens)


class Rpc:
    def __init__(self, settings, *, events=None, replies=None):
        self.settings = settings
        self.calls = []
        self.closed = False
        self.launch = None
        self.replies = replies or {}
        self.events = events if events is not None else [
            {"method": "item/agentMessage/delta", "params": {"threadId": "thr_test", "delta": "Hello"}},
            {"method": "thread/tokenUsage/updated", "params": {
                "threadId": "thr_test", "tokenUsage": {"total": {
                    "inputTokens": 120, "outputTokens": 30, "totalTokens": 150,
                }},
            }},
            {"method": "turn/completed", "params": {
                "threadId": "thr_test", "turn": {"id": "turn_test", "status": "completed"},
            }},
        ]

    def factory(self, **kwargs):
        self.launch = kwargs
        return self

    def config(self):
        config = {}
        for key, value in codex_local.runtime_overrides(self.settings).items():
            target = config
            path = key.split(".")
            for part in path[:-1]:
                target = target.setdefault(part, {})
            target[path[-1]] = value
        return config

    def request(self, method, params, **kwargs):
        self.calls.append((method, params))
        if method in self.replies:
            result = self.replies[method]
            if isinstance(result, Exception):
                raise result
            return result
        return {
            "initialize": {"serverInfo": {"version": RUNTIME_VERSION},
                           "codexHome": self.settings.codex_local_home},
            "config/read": {"config": self.config()},
            "account/read": {"account": {"type": "chatgpt", "email": OWNER, "planType": "plus"}},
            "account/rateLimits/read": {"rateLimits": {"limitId": "codex", "primary": {
                "usedPercent": 10, "windowDurationMins": 300,
            }}},
            "model/list": {"data": [{"model": self.settings.codex_local_model,
                "supportedReasoningEfforts": [{"reasoningEffort": "xhigh"}]}]},
            "thread/start": {"thread": {"id": "thr_test", "ephemeral": True},
                             "model": self.settings.codex_local_model, "instructionSources": [],
                             "modelProvider": "openai", "reasoningEffort": "xhigh",
                             "approvalPolicy": "never", "sandbox": {"type": "readOnly"}},
            "turn/start": {"turn": {"id": "turn_test"}},
        }[method]

    def notify(self, method, params=None):
        self.calls.append((method, params))

    send = notify

    def event(self, **kwargs):
        result = self.events.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed = True


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_access, "_loopback_listener_verified", True)
    return Settings(llm_provider="codex_local", provider_mode="fake", codex_local_enabled=True,
                    codex_local_gate_secret=GATE, codex_local_home=str(tmp_path / "isolated"),
                    codex_local_account_email=OWNER,
                    codex_local_workspace_id="00000000-0000-0000-0000-000000000001",
                    deployment_mode="local", auth_required=False, oidc_mode="disabled",
                    auth_cookie_sessions_enabled=False, auth_allow_registration=False)


def run(settings, rpc, **overrides):
    adapter = codex_local.CodexLocalChatAdapter(settings, client_factory=rpc.factory,
                                               encoding_factory=TextEncoding)
    args = {"system": "Be concise", "messages": [{"role": "user", "content": "Hi"}],
            "model": settings.codex_local_model, "reasoning_effort": "xhigh", "max_output_tokens": 100}
    args.update(overrides)
    with gate_scope(GATE, local_request=True, settings=settings):
        return adapter.chat(**args)


@pytest.mark.parametrize("gate", [None, "wrong"])
def test_gate_required_before_client_creation(settings, gate):
    rpc = Rpc(settings)
    adapter = codex_local.CodexLocalChatAdapter(settings, client_factory=rpc.factory)
    with gate_scope(gate, local_request=True, settings=settings), pytest.raises(CodexGateError):
        adapter.account_status()
    assert rpc.launch is None


@pytest.mark.parametrize("field,value", [("deployment_mode", "vercel"), ("auth_required", True),
    ("auth_allow_registration", True), ("oidc_mode", "live"), ("codex_local_enabled", False)])
def test_unsafe_configuration_refused(settings, field, value):
    setattr(settings, field, value)
    rpc = Rpc(settings)
    with pytest.raises(CodexLocalError):
        run(settings, rpc)
    assert rpc.launch is None


def test_requires_verified_listener(settings, monkeypatch):
    monkeypatch.setattr(codex_access, "_loopback_listener_verified", False)
    with pytest.raises(CodexLocalError, match="loopback launcher"):
        run(settings, Rpc(settings))


@pytest.mark.parametrize("account", [None, {}, {"type": "apiKey"}, {"type": "chatgptAuthTokens"},
    {"type": "chatgpt", "planType": "plus"},
    {"type": "chatgpt", "email": "someone-else@example.test", "planType": "plus"},
    {"type": "chatgpt", "email": OWNER, "planType": "unknown"}])
def test_bad_account_fails_before_generation(settings, account):
    rpc = Rpc(settings, replies={"account/read": {"account": account}})
    with pytest.raises(CodexLocalError):
        run(settings, rpc)
    assert "thread/start" not in [call[0] for call in rpc.calls]
    assert rpc.closed


@pytest.mark.parametrize("method,response", [
    ("model/list", {"data": []}), ("account/rateLimits/read", {}),
    ("initialize", {"serverInfo": {"version": "unreviewed"}}),
    ("config/read", {"config": {}}),
])
def test_unverifiable_prerequisites_fail_closed(settings, method, response):
    rpc = Rpc(settings, replies={method: response})
    with pytest.raises(CodexLocalError):
        run(settings, rpc)
    assert "turn/start" not in [call[0] for call in rpc.calls]
    assert rpc.closed


def test_success_exact_selection_isolation_and_provenance(settings):
    rpc = Rpc(settings)
    result = run(settings, rpc)
    assert result.text == "Hello"
    assert result.usage == {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150}
    assert result.provenance["authentication_mode"] == "chatgpt"
    assert result.provenance["quota_source"] == "chatgpt_plan"
    assert result.provenance["usage_available"] is True
    assert result.provenance["account_usage_capped"] is False
    assert result.provenance["codex_thread_id"] == "thr_test"
    start = next(p for m, p in rpc.calls if m == "thread/start")
    turn = next(p for m, p in rpc.calls if m == "turn/start")
    assert start["ephemeral"] is True
    assert start["model"] == turn["model"] == "gpt-5.6-sol"
    assert turn["effort"] == "xhigh"
    assert turn["sandboxPolicy"]["type"] == "readOnly"
    assert turn["sandboxPolicy"]["access"]["readableRoots"] == []
    assert turn["approvalPolicy"] == "never"
    assert not any(m in {"thread/resume", "thread/read", "thread/list"} for m, _ in rpc.calls)
    assert rpc.closed
    assert GATE not in json.dumps(rpc.calls)
    assert GATE not in json.dumps(result.__dict__)
    assert GATE not in str(settings)
    assert "codex_local_gate_secret" not in settings.model_dump()


@pytest.mark.parametrize("endpoint", [None, "https://example.test/backend-api/",
                                     "https://chatgpt.com/backend-api/?override=true"])
def test_chatgpt_endpoint_must_match_pinned_official_default(settings, endpoint):
    rpc = Rpc(settings)
    config = rpc.config()
    config["chatgpt_base_url"] = endpoint
    rpc.replies["config/read"] = {"config": config}
    with pytest.raises(CodexLocalError, match="restrictions"):
        run(settings, rpc)
    assert "account/read" not in [method for method, _ in rpc.calls]
    assert rpc.closed


def test_usage_absence_is_not_reported_as_measured_zero(settings):
    rpc = Rpc(settings)
    rpc.events.pop(1)
    result = run(settings, rpc)
    assert result.usage == {}
    assert result.provenance["usage_available"] is False
    assert result.provenance["usage_final"] is False


def test_prompt_limit_rejects_before_runtime(settings):
    settings.codex_local_max_input_tokens = 5
    rpc = Rpc(settings)
    with pytest.raises(CodexLimitError):
        run(settings, rpc)
    assert rpc.launch is None


def test_output_truncated_and_cancelled_without_actions(settings):
    rpc = Rpc(settings)
    result = run(settings, rpc, max_output_tokens=3)
    assert result.text == "Hel"
    assert result.provenance["output_truncated"] is True
    assert result.provenance["usage_final"] is False
    assert result.proposed_actions == []
    assert rpc.calls[-1] == ("turn/interrupt", {"threadId": "thr_test", "turnId": "turn_test"})
    assert rpc.closed


@pytest.mark.parametrize("error", [CodexTimeoutError("codex_local request timed out"),
                                    RuntimeError(GATE)])
def test_errors_cancel_close_and_hide_provider_details(settings, error, caplog):
    rpc = Rpc(settings, events=[error])
    with pytest.raises(CodexLocalError) as exc:
        run(settings, rpc)
    assert GATE not in str(exc.value)
    assert GATE not in caplog.text
    assert rpc.calls[-1][0] == "turn/interrupt"
    assert rpc.closed


def test_secret_in_prompt_or_output_is_never_returned(settings):
    rpc = Rpc(settings)
    with pytest.raises(CodexLocalError):
        run(settings, rpc, system=GATE)
    assert rpc.launch is None
    rpc.events[0]["params"]["delta"] = GATE
    with pytest.raises(CodexLocalError, match="protected"):
        run(settings, rpc)


def test_tool_attempt_and_auth_change_refused(settings):
    for event in [
        {"method": "item/started", "params": {"threadId": "thr_test", "item": {"type": "commandExecution"}}},
        {"method": "account/updated", "params": {"authMode": "apikey"}},
    ]:
        rpc = Rpc(settings, events=[event])
        with pytest.raises(CodexLocalError):
            run(settings, rpc)
        assert rpc.closed


def test_configured_limit_overrides_larger_request(settings):
    settings.codex_local_max_output_tokens = 2
    result = run(settings, Rpc(settings), max_output_tokens=1000)
    assert result.text == "He"
    assert result.provenance["returned_output_tokens"] == 2


@pytest.mark.parametrize("overrides", [{"model": "another-model"}, {"reasoning_effort": "high"}])
def test_model_and_effort_mismatch_before_launch(settings, overrides):
    rpc = Rpc(settings)
    with pytest.raises(CodexLocalError):
        run(settings, rpc, **overrides)
    assert rpc.launch is None


def test_transport_does_not_inherit_gate_or_api_keys(settings, monkeypatch):
    import io
    import sys
    from types import SimpleNamespace

    from workbench.providers import codex_rpc

    seen = {}
    class Process:
        def __init__(self, command, **kwargs):
            seen.update(command=command, **kwargs)
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()

        def poll(self):
            return 0

    monkeypatch.setenv("WB_CODEX_LOCAL_GATE_SECRET", GATE)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-api-key")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "test-only-access-token")
    monkeypatch.setattr(codex_rpc, "version", lambda _: RUNTIME_VERSION)
    monkeypatch.setitem(sys.modules, "codex_cli_bin", SimpleNamespace(bundled_codex_path=lambda: "test.exe"))
    monkeypatch.setattr(codex_rpc.subprocess, "Popen", Process)
    client = StdioCodexClient(profile=settings.codex_local_home, cwd=settings.codex_local_home,
                              overrides=codex_local.runtime_overrides(settings), cancel=threading.Event())
    client.close()
    assert GATE not in repr(seen)
    assert "test-only-api-key" not in repr(seen)
    assert "test-only-access-token" not in repr(seen)
    assert seen["env"]["CODEX_HOME"] == settings.codex_local_home
    assert seen["stderr"] == codex_rpc.subprocess.DEVNULL
    assert seen["command"][-3:] == ["app-server", "--listen", "stdio://"]


def test_api_account_gate_and_success(settings, monkeypatch):
    from fastapi.testclient import TestClient

    from workbench import codex_boundary, main

    rpc = Rpc(settings)
    adapter = codex_local.CodexLocalChatAdapter(settings, client_factory=rpc.factory,
                                               encoding_factory=TextEncoding)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(codex_boundary, "get_settings", lambda: settings)
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    monkeypatch.setattr(codex_local, "CodexLocalChatAdapter", lambda _: adapter)
    # No lifespan: this account-status route neither needs nor opens a database.
    client = TestClient(main.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 5000))
    missing = client.get("/providers/codex-local/account")
    assert missing.status_code == 403
    assert rpc.launch is None
    response = client.get("/providers/codex-local/account", headers={"X-Workbench-Codex-Gate": GATE})
    assert response.status_code == 200
    assert response.json()["authentication_mode"] == "chatgpt"
    assert response.json()["account_email"] == OWNER
    assert GATE not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert rpc.closed


def test_charged_chat_records_local_account_and_ignores_api_ceiling(settings, monkeypatch, session, project):
    from workbench import config
    from workbench.models import UsageEvent
    from workbench.services import usage

    actual = config.get_settings()
    for name in ("llm_provider", "provider_mode", "codex_local_reasoning_effort"):
        monkeypatch.setattr(actual, name, getattr(settings, name))
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    rpc = Rpc(settings)
    adapter = codex_local.CodexLocalChatAdapter(settings, client_factory=rpc.factory,
                                               encoding_factory=TextEncoding)
    monkeypatch.setattr(codex_local, "CodexLocalChatAdapter", lambda _: adapter)
    usage.set_budget(session, project.id, monthly_token_ceiling=1)
    usage.record_usage(session, project.id, provider="openai", model="api-test", kind="dialogue",
                       usage={"total_tokens": 100}, simulated=False)
    with gate_scope(GATE, local_request=True, settings=settings):
        result = usage.charged_chat(session, project.id, "dialogue", system="Hi", messages=[])
    session.commit()
    event = session.query(UsageEvent).filter_by(provider="codex_local").one()
    assert event.provenance["codex_thread_id"] == "thr_test"
    assert event.simulated is False
    assert result.model == settings.codex_local_model
    assert GATE not in json.dumps(event.provenance)


def test_disconnect_signals_cancellation(settings, monkeypatch):
    from workbench import codex_boundary

    monkeypatch.setattr(codex_boundary, "get_settings", lambda: settings)
    cancelled = []

    async def endpoint(scope, receive, send):
        await receive()
        cancelled.append(codex_local.request_cancel.get().is_set())

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        pass

    scope = {"type": "http", "scheme": "http", "server": ("127.0.0.1", 8000),
             "client": ("127.0.0.1", 5000), "headers": [(b"host", b"127.0.0.1:8000")]}
    asyncio.run(codex_boundary.CodexLocalBoundary(endpoint)(scope, receive, send))
    assert cancelled == [True]


def test_rpc_timeout_and_cancellation_without_process():
    # Exercise the actual transport's wait loop without starting an executable.
    import queue

    client = object.__new__(StdioCodexClient)
    client._cancel = threading.Event()
    client._closed = threading.Event()
    client._queue = queue.Queue()
    with pytest.raises(CodexTimeoutError):
        client._next(time.monotonic() - 1)
    client._cancel.set()
    with pytest.raises(CodexLocalError, match="cancelled"):
        client._next(time.monotonic() + 1)


def test_blocked_transport_write_is_bounded():
    from types import SimpleNamespace

    release = threading.Event()

    class BlockedPipe:
        def write(self, data):
            release.wait(timeout=2)

        def flush(self):
            pass

    client = object.__new__(StdioCodexClient)
    client._cancel = threading.Event()
    client._deadline = time.monotonic() - 1
    client._proc = SimpleNamespace(stdin=BlockedPipe())
    try:
        with pytest.raises(CodexTimeoutError):
            client._write({"method": "test"})
    finally:
        release.set()


@pytest.mark.parametrize("effort", [None, "xhigh"])
def test_openai_reasoning_is_only_sent_when_explicit(effort):
    from types import SimpleNamespace

    from workbench.providers.llm import OpenAIChatAdapter

    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text="Hello", id="test", usage=None)

    adapter = OpenAIChatAdapter("test-only", client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    result = adapter.chat(system="Hi", messages=[], model="test", max_output_tokens=20,
                          reasoning_effort=effort)
    assert result.text == "Hello"
    if effort is None:
        assert "reasoning" not in calls[0]
    else:
        assert calls[0]["reasoning"] == {"effort": effort}


def test_anthropic_rejects_explicit_reasoning_before_network():
    from workbench.providers.llm import AnthropicChatAdapter

    with pytest.raises(ValueError, match="not supported"):
        AnthropicChatAdapter("test-only").chat(system="Hi", messages=[], model="test",
                                                max_output_tokens=20, reasoning_effort="xhigh")


def test_local_usage_separate_from_api_budget(settings, monkeypatch, session, project):
    from workbench.services import usage

    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    rpc = Rpc(settings)
    result = run(settings, rpc)
    usage.set_budget(session, project.id, monthly_token_ceiling=1)
    event = usage.record_usage(session, project.id, provider="codex_local", model=result.model,
                              kind="dialogue", simulated=False, usage=result.usage,
                              provenance=result.provenance)
    session.commit()
    summary = usage.month_usage(session, project.id)
    assert summary["live_total_tokens"] == 0
    assert summary["ceiling_reached"] is False
    assert summary["codex_local"]["reported_total_tokens"] == 150
    assert GATE not in json.dumps(event.provenance)
    usage.check_budget(session, project.id)


@pytest.mark.parametrize("host,client,origin,expected", [
    ("127.0.0.1", "127.0.0.1", None, 200),
    ("0.0.0.0", "127.0.0.1", None, 503),
    ("127.0.0.1", "192.168.1.2", None, 503),
    ("127.0.0.1", "127.0.0.1", "https://hostile.example", 503),
])
def test_asgi_boundary_checks_addresses_and_strips_gate(
    settings, monkeypatch, host, client, origin, expected,
):
    from workbench import codex_boundary

    monkeypatch.setattr(codex_boundary, "get_settings", lambda: settings)
    sent = []

    async def endpoint(scope, receive, send):
        codex_access.require_access(settings)
        assert GATE.encode() not in repr(scope).encode()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        await asyncio.sleep(60)

    async def send(message):
        sent.append(message)

    headers = [(b"host", b"127.0.0.1:8000"), (b"x-workbench-codex-gate", GATE.encode())]
    if origin:
        headers.append((b"origin", origin.encode()))
    scope = {"type": "http", "scheme": "http", "method": "GET", "path": "/providers/codex-local/account",
             "server": (host, 8000), "client": (client, 1234), "headers": headers}
    asyncio.run(codex_boundary.CodexLocalBoundary(endpoint)(scope, receive, send))
    assert sent[0]["status"] == expected
    assert GATE not in repr(sent)
    if expected == 200:
        assert (b"cache-control", b"no-store") in sent[0]["headers"]
