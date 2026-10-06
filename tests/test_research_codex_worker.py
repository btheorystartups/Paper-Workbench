"""Offline checks of the Codex worker's turn and telemetry boundary."""

import io
import json
import threading
import time
from types import SimpleNamespace

import pytest

from workbench.providers import research_codex_worker as worker_module


@pytest.mark.parametrize("method,params,code", [
    ("account/updated", {"authMode": "other"}, "authentication_changed"),
    ("model/rerouted", {}, "model_rerouted"),
    ("error", {"message": "PRIVATE_RUNTIME_TEXT"}, "runtime_error"),
    ("item/started", {"item": {"type": "PRIVATE_TOOL_NAME"}}, "unsupported_item"),
    ("item/agentMessage/delta", {"delta": {"private": "PRIVATE_TEXT"}}, "invalid_message_delta"),
    ("item/agentMessage/delta", {"delta": "PRIVATE_TEXT" * 25000}, "response_text_bound"),
    ("turn/completed", {"turn": {"status": "failed", "error": "PRIVATE_ERROR"}}, "turn_incomplete"),
])
def test_stream_failures_have_fixed_codes_and_still_interrupt(monkeypatch, method, params, code):
    client = ControlledCodexClient()
    client.events = [{"method": method, "params": {"threadId": "parent-thread", **params}}]
    worker = prepared_worker(client)
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: None)
    with pytest.raises(worker_module.WorkerStreamError) as captured:
        worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20})
    metadata = worker_module.failure_metadata(captured.value)
    expected = {"error_class": "WorkerStreamError", "failure_code": code}
    if code in {"runtime_error", "turn_incomplete"}:
        expected["runtime_error"] = {"source": "error_notification" if code == "runtime_error" else "failed_turn",
            "category": "unknown", "http_status_code": None, "will_retry": None}
    assert metadata == expected
    assert "PRIVATE" not in json.dumps(metadata)
    assert worker.stage == "turn_stream"
    assert any(method == "turn/interrupt" for method, _ in client.calls)


def test_worker_entrypoint_serializes_sanitized_failure_code_and_closes(monkeypatch):
    closed, emitted = [], []
    worker = SimpleNamespace(stage="turn_stream", rpc_calls=[],
        preflight=lambda deadline: None, close=lambda: closed.append(True))

    def fail(*args):
        raise worker_module.WorkerStreamError("runtime_error")

    worker.run = fail
    monkeypatch.setattr(worker_module, "CodexResearchWorker", lambda: worker)
    monkeypatch.setattr(worker_module.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(
        b'{"agent_id":"test","op":"hello"}\n{"agent_id":"test","op":"plan"}\n')))
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    worker_module.main()
    args, fields = emitted[-1]
    assert args == ("test", "error")
    assert fields == {"stage": "turn_stream", "error_class": "WorkerStreamError",
                      "failure_code": "runtime_error", "rpc_calls": []}
    assert closed == [True]
    assert worker_module.failure_metadata(ValueError("PRIVATE_EXCEPTION_TEXT")) == {"error_class": "ValueError"}


@pytest.mark.parametrize("code", [*sorted(worker_module.STREAM_FAILURE_CODES), "PRIVATE_CODE", ["runtime_error"]])
def test_controller_retains_only_allowlisted_stream_failure_codes(monkeypatch, code):
    from workbench.providers.research_executor import ExecutorError
    from workbench.services import research_trace
    from workbench.services.research_runner import Runner

    commits, traces = [], []
    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: traces.append((args, kw)))
    runner = SimpleNamespace(usage=lambda *args: None,
                             session=SimpleNamespace(commit=lambda: commits.append(True)))
    agent = SimpleNamespace(provenance={})
    event = {"type": "error", "stage": "turn_stream", "error_class": "WorkerStreamError",
             "failure_code": code, "message": "PRIVATE_RUNTIME_TEXT", "item": {"type": "PRIVATE_TOOL"}}
    with pytest.raises(ExecutorError):
        Runner.event(runner, SimpleNamespace(poll=lambda: event), agent, {}, "report")
    expected = code if isinstance(code, str) and code in worker_module.STREAM_FAILURE_CODES else None
    assert agent.provenance.get("worker_failure_code") == expected
    assert "PRIVATE" not in json.dumps(agent.provenance)
    assert commits
    assert traces[0][0][1] == "worker_failed"
    assert traces[0][1].get("failure_code") == expected
    assert "PRIVATE" not in json.dumps({k: v for k, v in traces[0][1].items() if k != "agent"})


def test_controller_does_not_accept_stream_codes_from_other_stages(monkeypatch):
    from workbench.providers.research_executor import ExecutorError
    from workbench.services import research_trace
    from workbench.services.research_runner import Runner

    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: None)
    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: None))
    agent = SimpleNamespace(provenance={})
    event = {"type": "error", "stage": "report_validation", "error_class": "ValueError",
             "failure_code": "runtime_error"}
    with pytest.raises(ExecutorError):
        Runner.event(runner, SimpleNamespace(poll=lambda: event), agent, {}, "report")
    assert agent.provenance["worker_failure_stage"] == "report_validation"
    assert "worker_failure_code" not in agent.provenance


@pytest.mark.parametrize("method", ["error", "turn/completed"])
@pytest.mark.parametrize("retry", [False, True])
def test_worker_keeps_safe_runtime_metadata_and_stops_without_retry(monkeypatch, method, retry):
    client = ControlledCodexClient()
    error = {"message": "PRIVATE_MESSAGE", "additionalDetails": "PRIVATE_DETAILS",
             "codexErrorInfo": {"responseStreamDisconnected": {"httpStatusCode": 503}}}
    params = {"threadId": "parent-thread", "turnId": "plan-turn", "error": error, "willRetry": retry}
    if method == "turn/completed":
        params = {"threadId": "parent-thread", "turn": {"id": "plan-turn", "status": "failed", "error": error}}
    client.events = [{"method": method, "params": params}]
    worker = prepared_worker(client)
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: None)
    with pytest.raises(worker_module.WorkerStreamError) as caught:
        worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20, "call_span_id": "span1"})
    data = worker_module.failure_metadata(caught.value)
    assert data["runtime_error"]["category"] == "responseStreamDisconnected"
    assert data["runtime_error"]["http_status_code"] == 503
    assert data["runtime_error"]["will_retry"] == (retry if method == "error" else None)
    assert "PRIVATE" not in str(data)
    assert sum(m == "turn/start" for m, _ in client.calls) == 1
    assert sum(m == "turn/interrupt" for m, _ in client.calls) == 1


@pytest.mark.parametrize("params", [{"threadId": "foreign", "turnId": "plan-turn"},
    {"threadId": "parent-thread", "turnId": "foreign"}])
def test_foreign_runtime_error_does_not_fail_current_turn_or_contaminate_activity(monkeypatch, params):
    client = ControlledCodexClient()
    client.events.insert(0, {"method": "error", "params": {**params, "error": {"codexErrorInfo": "badRequest"}}})
    worker = prepared_worker(client)
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20, "call_span_id": "span1"})
    assert any(args[1] == "plan" for args, _ in emitted)
    activity = [fields["progress"]["activity"] for args, fields in emitted
                if args[1] == "progress" and "activity" in fields["progress"]][-1]
    assert activity["notification_count"] == 3


def test_reasoning_counts_and_heartbeat_gap_preserve_no_content_and_reset_each_turn(monkeypatch):
    client = ControlledCodexClient()
    worker = prepared_worker(client)
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    for span in ("first", "second"):
        client.events = ControlledCodexClient().events
        client.events[0]["params"]["tokenUsage"]["total"]["totalTokens"] = worker.total_tokens + 83
        client.events = [
            {"method": "item/started", "params": {"threadId": "parent-thread", "turnId": "plan-turn", "item": {"type": "reasoning"}}},
            {"method": "item/reasoning/summaryTextDelta", "params": {"threadId": "parent-thread", "turnId": "plan-turn", "delta": "PRIVATE_REASONING"}},
            {"method": "item/reasoning/textDelta", "params": {"threadId": "parent-thread", "turnId": "plan-turn", "delta": "PRIVATE_RAW"}},
        ] + client.events
        original_event = ControlledCodexClient.event
        simulated = []

        def event(*, deadline, simulated=simulated, original_event=original_event):
            if not simulated:
                # Simulate resuming after an 880-second local heartbeat gap without waiting.
                simulated.append(True)
                worker.stream_started_monotonic -= 880
                worker.progress("parent", "worker_heartbeat", force=True)
            return original_event(client, deadline=deadline)

        client.event = event
        worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20, "call_span_id": span})
    terminals = [fields["progress"]["activity"] for args, fields in emitted
        if args[1] == "progress" and fields["progress"].get("stream", {}).get("finished")]
    assert [r["call_span_id"] for r in terminals] == ["first", "second"]
    assert all(r["reasoning_delta_count"] == 2 and r["worker_heartbeat_count"] == 1 for r in terminals)
    assert all(r["max_heartbeat_gap_seconds"] >= 880 for r in terminals)
    assert "PRIVATE" not in json.dumps(terminals)


@pytest.mark.parametrize("invalid", [False, True])
def test_controller_error_metadata_is_allowlisted_and_trace_bound(monkeypatch, invalid):
    from workbench.providers.research_executor import ExecutorError
    from workbench.services import research_trace
    from workbench.services.research_runner import Runner

    traces = []
    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: traces.append(kw))
    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: None))
    agent = SimpleNamespace(provenance={})
    info = {"source": "error_notification", "category": "usageLimitExceeded", "http_status_code": None, "will_retry": False}
    if invalid:
        info["message"] = "PRIVATE"
    event = {"type": "error", "stage": "turn_stream", "error_class": "WorkerStreamError",
        "failure_code": "runtime_error", "runtime_error": info, "message": "PRIVATE"}
    with pytest.raises(ExecutorError):
        Runner.event(runner, SimpleNamespace(poll=lambda: event), agent, {"span_id": "span1"}, "report")
    assert ("worker_runtime_error" in agent.provenance) is not invalid
    assert ("runtime_error" in traces[0]) is not invalid
    assert traces[0]["span_id"] == "span1"
    assert "PRIVATE" not in str(agent.provenance)


@pytest.mark.parametrize("changes", [{"call_span_id": "other"}, {"version": True},
    {"reasoning_text": "PRIVATE"}, {"elapsed_seconds": 899.0}, {"last_reasoning_seconds": 901.0}])
def test_controller_rejects_invalid_activity_before_persistence(changes):
    from test_codex_diagnostics import activity_fixture

    from workbench.providers.research_executor import ExecutorError
    from workbench.services.research_runner import Runner

    commits = []
    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: commits.append(True)))
    agent = SimpleNamespace(provenance={"active_model_turn": {"codex_thread_id": "thread1", "codex_turn_id": "turn1"}})
    progress = stream_progress_fixture()
    progress["stream"]["elapsed_seconds"] = 900.0
    progress["activity"] = activity_fixture(**changes)
    with pytest.raises(ExecutorError):
        Runner.event(runner, SimpleNamespace(poll=lambda: {"type": "progress", "progress": progress}),
            agent, {"span_id": "span1"}, "report")
    assert not commits and "codex_activities" not in agent.provenance


def test_controller_activity_summary_is_saved_without_raw_text_and_monotonic(monkeypatch):
    from test_codex_diagnostics import activity_fixture

    from workbench.providers.research_executor import ExecutorError
    from workbench.services.research_runner import Runner

    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: None))
    agent = SimpleNamespace(provenance={"active_model_turn": {"codex_thread_id": "thread1", "codex_turn_id": "turn1"}})
    progress = stream_progress_fixture()
    progress["stream"].update(elapsed_seconds=900.0, delta_count=0, characters=0, utf8_bytes=0,
                              first_delta_seconds=None, last_delta_seconds=None)
    progress["activity"] = activity_fixture()

    def deliver():
        Runner.event(runner, SimpleNamespace(poll=lambda: {"type": "progress", "progress": progress}),
            agent, {"span_id": "span1"}, "report")

    deliver()
    saved = agent.provenance["codex_activities"][0]
    assert saved["summary"]["local_heartbeat_gap_observed"] and saved["summary"]["long_observable_silence"]
    assert saved["summary"]["first_output_pending_seconds"] == 900
    progress["activity"]["reasoning_characters"] = 7
    with pytest.raises(ExecutorError, match="regressed"):
        deliver()


@pytest.mark.parametrize("last_size,exceeds_bound", [(125000, False), (125001, True)])
def test_stream_text_bound_counts_multiple_fragments(monkeypatch, last_size, exceeds_bound):
    client = ControlledCodexClient()
    client.events = [
        {"method": "item/agentMessage/delta", "params": {
            "threadId": "parent-thread", "delta": "x" * size}}
        for size in (125000, last_size)
    ] + client.events
    worker = prepared_worker(client)
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    if exceeds_bound:
        with pytest.raises(worker_module.WorkerStreamError) as captured:
            worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20})
        assert captured.value.code == "response_text_bound"
        assert not any(args[1] == "plan" for args, _ in emitted)
    else:
        worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20})
        assert any(args[1] == "plan" for args, _ in emitted)
    assert any(method == "turn/interrupt" for method, _ in client.calls)


class ControlledCodexClient:
    def __init__(self, *, account="research@example.invalid"):
        self.account = account
        self.calls = []
        plan = {
            "rationale": "Separate the finite cases.",
            "assignments": [{
                "key": "symmetric", "question": "Check the symmetric case",
                "success_criteria": "Record a scoped result",
                "instructions": "Inspect the supplied source", "source_ids": [],
            }],
        }
        self.events = [
            {"method": "thread/tokenUsage/updated", "params": {
                "threadId": "parent-thread", "tokenUsage": {"total": {"totalTokens": 83}},
            }},
            {"method": "item/completed", "params": {
                "threadId": "parent-thread", "item": {
                    "type": "agentMessage", "text": json.dumps(plan),
                },
            }},
            {"method": "turn/completed", "params": {
                "threadId": "parent-thread", "turn": {"status": "completed"},
            }},
        ]

    def request(self, method, params, *, deadline):
        self.calls.append((method, params))
        if method == "account/read":
            return {"account": {"type": "chatgpt", "email": self.account}}
        if method == "turn/start":
            return {"turn": {"id": "plan-turn"}}
        raise AssertionError(method)

    def event(self, *, deadline):
        return self.events.pop(0)

    def send(self, method, params):
        self.calls.append((method, params))


def prepared_worker(client):
    worker = worker_module.CodexResearchWorker.__new__(worker_module.CodexResearchWorker)
    worker.settings = SimpleNamespace(
        codex_local_model="gpt-5.5", codex_local_reasoning_effort="low"
    )
    worker.client = client
    worker.thread_id = "parent-thread"
    worker.account = {"email": "research@example.invalid"}
    worker.total_tokens = 0
    worker.started_monotonic = time.monotonic()
    worker.progress_lock = threading.Lock()
    worker.notification_count = 0
    worker.notification_types = {}
    worker.last_progress_monotonic = float("-inf")
    worker.last_progress_stage = None
    return worker


@pytest.mark.parametrize("model", ["gpt-5.6-terra", "PRIVATE_MODEL"])
@pytest.mark.parametrize("operation", ["draft", "revise"])
def test_incompatible_bounded_author_stops_before_account_or_model_dispatch(model, operation, monkeypatch):
    from workbench.providers.counter_compatibility import CounterCompatibilityError

    client = ControlledCodexClient()
    worker = prepared_worker(client)
    worker.settings.codex_local_model = model
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kwargs: None)
    with pytest.raises(CounterCompatibilityError):
        worker.run("parent", operation, {"token_limit": 10000, "time_limit_seconds": 20,
            "contract": {"manuscript_length": {"min_words": 3, "max_words": 5}}})
    assert client.calls == [] and worker.stage == "input_check"


def test_text_only_plan_does_not_require_counter_compatibility(monkeypatch):
    client = ControlledCodexClient()
    worker = prepared_worker(client)
    worker.settings.codex_local_model = "gpt-5.6-sol"
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kwargs: None)
    worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20})
    assert any(method == "turn/start" for method, _params in client.calls)


def test_codex_worker_uses_read_only_turn_and_returns_actual_usage(monkeypatch):
    client = ControlledCodexClient()
    worker = prepared_worker(client)
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    worker.run("parent", "plan", {
        "token_limit": 4000, "time_limit_seconds": 20,
        "contract": {"question": "Lifting", "max_children": 1},
        "sources": [{"source_id": "s1", "title": "Pilot", "version": "v1",
                     "sha256": "a" * 64, "text": "Frozen source text"}],
    })

    turn = next(params for method, params in client.calls if method == "turn/start")
    assert turn["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    assert turn["threadId"] == "parent-thread"
    assert turn["outputSchema"]["required"] == ["rationale", "assignments"]
    assert turn["outputSchema"]["additionalProperties"] is False
    assert "Frozen source text" not in turn["input"][0]["text"]
    assert emitted[0][0] == ("parent", "turn_started")
    assert emitted[0][1]["provenance"]["codex_turn_id"] == "plan-turn"
    usage_event = next(fields for args, fields in emitted if args[1] == "usage")
    result_event = next(fields for args, fields in emitted if args[1] == "plan")
    assert usage_event["usage"] == {
        "tokens": 83, "kind": "actual", "source": "Codex thread/tokenUsage/updated"
    }
    assert result_event["usage"]["tokens"] == 83
    assert result_event["provenance"]["codex_thread_id"] == "parent-thread"
    assert result_event["provenance"]["codex_turn_id"] == "plan-turn"
    trace = result_event["provenance"]["rpc_calls"]
    assert [call["method"] for call in trace] == ["account/read", "turn/start"]
    assert all(call["duration_seconds"] >= 0 and call["call_stack"] for call in trace)
    assert all(call["status"] == "returned" for call in trace)
    assert "Frozen source text" not in json.dumps(trace)
    assert "research@example.invalid" not in json.dumps(trace)


def test_codex_worker_refuses_account_change_before_turn(monkeypatch):
    client = ControlledCodexClient(account="different@example.invalid")
    worker = prepared_worker(client)
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: None)
    with pytest.raises(ValueError, match="account changed"):
        worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20})
    assert all(method != "turn/start" for method, _ in client.calls)


@pytest.mark.parametrize("reviewed_handoff", [False, True])
def test_only_reviewed_handoff_starts_fresh_context_with_per_thread_usage(monkeypatch, reviewed_handoff):
    class SummaryClient(ControlledCodexClient):
        def request(self, method, params, *, deadline):
            if method == "thread/start":
                self.calls.append((method, params))
                return {"thread": {"id": "summary-thread", "ephemeral": True},
                        "model": "gpt-5.5", "modelProvider": "openai", "reasoningEffort": "low",
                        "approvalPolicy": "never", "sandbox": {"type": "readOnly"}}
            return super().request(method, params, deadline=deadline)

    client = SummaryClient()
    thread_id = "summary-thread" if reviewed_handoff else "parent-thread"
    for event in client.events:
        event["params"]["threadId"] = thread_id
    client.events[0]["params"]["tokenUsage"]["total"]["totalTokens"] = (
        83 if reviewed_handoff else 90083)
    client.events[1]["params"]["item"]["text"] = json.dumps({
        "summary": "Scoped summary", "report_ids": ["review-1"], "agreements": [],
        "conflicts": [], "unresolved_questions": [],
        "deliverables": {"research_report": "Bounded reviewed decisions"},
    })
    if reviewed_handoff:
        client.events.insert(0, {"method": "thread/tokenUsage/updated", "params": {
            "threadId": "parent-thread", "tokenUsage": {"total": {"totalTokens": 90099}}}})
    worker = prepared_worker(client)
    worker.scratch = SimpleNamespace(name="synthetic-scratch")
    worker.total_tokens = 90000
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    message = {"token_limit": 7000, "time_limit_seconds": 20,
               "contract": {"deliverables": ["research_report"]}, "reports": {"review-1": {}}}
    if reviewed_handoff:
        message["reviewed_candidate"] = {"candidate_sha256": "a" * 64}
    worker.run("parent", "integrate", message)
    turns = [params for method, params in client.calls if method == "turn/start"]
    assert len(turns) == 1 and turns[0]["threadId"] == thread_id
    assert turns[0]["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    assert sum(method == "thread/start" for method, _ in client.calls) == int(reviewed_handoff)
    result = next(fields for args, fields in emitted if args[1] == "synthesis")
    assert result["usage"]["tokens"] == 83
    assert worker.total_tokens == (83 if reviewed_handoff else 90083)
    assert result["provenance"]["codex_thread_id"] == thread_id
    if reviewed_handoff:
        assert result["provenance"]["prior_codex_thread_id"] == "parent-thread"
        assert result["provenance"]["context_policy"] == "fresh_reviewed_candidate_summary"
    else:
        assert "prior_codex_thread_id" not in result["provenance"]


def test_progress_telemetry_is_content_free_and_distinguishes_notifications(monkeypatch):
    worker = prepared_worker(ControlledCodexClient())
    worker.stage = "turn_stream"
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))

    worker.record_notification("child", "item/agentMessage/delta")
    worker.progress("child", "worker_heartbeat")

    progress = [fields["progress"] for _, fields in emitted]
    assert [item["source"] for item in progress] == ["codex_notification", "worker_heartbeat"]
    assert progress[-1]["stage"] == "turn_stream"
    assert progress[-1]["codex_notification_count"] == 1
    assert progress[-1]["codex_notification_types"] == {"item/agentMessage/delta": 1}
    assert "text" not in json.dumps(progress)
    assert all(item["elapsed_seconds"] >= 0 and item["timestamp"].endswith("+00:00") for item in progress)


def test_notification_burst_is_coalesced_without_losing_counts(monkeypatch):
    worker = prepared_worker(ControlledCodexClient())
    worker.stage = "turn_stream"
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append(kw["progress"]))
    monkeypatch.setattr(worker_module.time, "monotonic", lambda: 100.0)
    for _ in range(500):
        worker.record_notification("child", "item/agentMessage/delta")
    assert len(emitted) == 1
    worker.progress("child", "worker_heartbeat")
    assert emitted[-1]["codex_notification_count"] == 500
    assert emitted[-1]["codex_notification_types"] == {"item/agentMessage/delta": 500}
    monkeypatch.setattr(worker_module.time, "monotonic", lambda: 101.0)
    worker.record_notification("child", "item/completed")
    assert len(emitted) == 3
    worker.stage = "report_validation"
    worker.record_notification("child", "turn/completed")
    assert len(emitted) == 4 and emitted[-1]["stage"] == "report_validation"


def test_structured_synthesis_requires_only_requested_deliverables():
    schema = worker_module.output_schema("integrate", {"contract": {"deliverables": ["paper"]}})
    deliverables = schema["properties"]["deliverables"]
    assert deliverables["required"] == ["paper"]
    assert set(deliverables["properties"]) == {"paper"}
    assert deliverables["additionalProperties"] is False
    assert "deliverables" in schema["required"]


def test_specialist_schema_exposes_exact_packet_scope_to_model():
    from workbench.research_contract import AvailabilityAssertion

    schema = worker_module.output_schema("audit", {})
    scope = schema["$defs"]["AvailabilityAssertion"]["properties"]["packet_scope"]
    assert {option.get("const") for option in scope["anyOf"]} >= {"current"}
    assert any(option.get("pattern") == r"^[a-f0-9]{64}$" for option in scope["anyOf"])
    base = {"artifact_path": "/candidate/sections/0/text", "availability": "available",
            "artifact_sha256": "a" * 64}
    for value in ("current", "b" * 64):
        assert AvailabilityAssertion(packet_scope=value, **base).packet_scope == value
    with pytest.raises(ValueError):
        AvailabilityAssertion(packet_scope="current packet", **base)


@pytest.mark.parametrize("operation", ["draft", "revise"])
@pytest.mark.parametrize("identifiers", [[], ["proof-comment", "source-comment"]])
def test_author_schema_binds_the_controller_response_inventory(operation, identifiers):
    message = {"expected_response_ids": identifiers, "draft_corrections": [{"code": "manuscript_length"}]}
    schema = worker_module.output_schema(operation, message)
    responses = schema["properties"]["responses"]
    assert responses["minItems"] == responses["maxItems"] == len(identifiers)
    comment = schema["$defs"]["RevisionResponse"]["properties"]["comment_id"]
    if identifiers:
        assert comment["enum"] == identifiers
    else:
        assert "enum" not in comment  # Empty enum is not a valid schema.
    prompt = worker_module.json_prompt(operation, message)
    assert "validation diagnostics, not reviewer comment IDs" in prompt
    assert "return responses=[]" in prompt


def test_adversarial_schema_exposes_challenges_and_blocking_objection_binding():
    schema = worker_module.output_schema("audit", {})
    assert "adversarial" in schema["properties"]["role"]["enum"]
    check = schema["$defs"]["AdversarialCheck"]
    assert set(check["required"]) == {
        "criterion", "challenge", "outcome", "rationale", "claim_ids", "objection_id"}
    assert set(check["properties"]["criterion"]["enum"]) == {
        "proof_stress", "source_entailment", "novelty_limits", "scope_overclaim", "reproducibility"}


def test_structured_report_keeps_all_evidence_fields():
    schema = worker_module.output_schema("research", {})
    citation = schema["$defs"]["Citation"]
    assert set(citation["required"]) == {"id", "source_id", "locator", "url", "access"}
    assert "default" not in json.dumps(schema)
    with pytest.raises(ValueError, match="verified result"):
        worker_module.parse_json(json.dumps({
            "summary": "Unsupported success", "findings": [{
                "id": "f1", "claim_key": "example", "statement": "Claim", "category": "verified_result",
                "stance": "supports", "scope": "synthetic", "citation_ids": [], "verification_ids": [],
            }], "citations": [], "proof_attempts": [], "failed_approaches": [],
            "unresolved_questions": [], "research_leads": [], "search_log": [], "verification_artifacts": [],
        }), worker_module.AgentReport)


def test_report_correction_starts_fresh_context_and_retains_bound_original(monkeypatch):
    from workbench.models import stable_hash
    from workbench.providers.research_quality_offline import reply

    class RepairClient(ControlledCodexClient):
        def request(self, method, params, *, deadline):
            if method == "thread/start":
                self.calls.append((method, params))
                return {"thread": {"id": "repair-thread", "ephemeral": True},
                        "model": "gpt-5.5", "modelProvider": "openai", "reasoningEffort": "low",
                        "approvalPolicy": "never", "sandbox": {"type": "readOnly"}}
            return super().request(method, params, deadline=deadline)

    packet = {"role": "proof_method", "candidate_sha256": "a" * 64,
              "candidate": {"sections": [], "claims": []}, "prior_comments": []}
    packet["packet_sha256"] = stable_hash(packet)
    original = reply("audit", {"packet": packet})
    original["summary"] = "Original scientific findings retained for repair."
    client = RepairClient()
    for event in client.events:
        event["params"]["threadId"] = "repair-thread"
    client.events[1]["params"]["item"]["text"] = json.dumps(original)
    worker = prepared_worker(client)
    worker.scratch = SimpleNamespace(name="synthetic-scratch")
    worker.total_tokens = 90000
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    message = {"packet": packet, "original_report": original,
               "original_report_sha256": stable_hash(original),
               "report_corrections": [{"path": "/assessments", "message": "Controlled defect"}],
               "token_limit": 12000, "time_limit_seconds": 20}
    worker.run("same-specialist", "audit", message)
    result = next(fields for args, fields in emitted if args[1] == "specialist_report")
    assert result["usage"]["tokens"] == 83 and worker.total_tokens == 83
    assert result["provenance"]["prior_codex_thread_id"] == "parent-thread"
    assert result["provenance"]["codex_thread_id"] == "repair-thread"
    assert result["provenance"]["context_policy"] == "fresh_report_correction"
    prompt = next(params for method, params in client.calls if method == "turn/start")["input"][0]["text"]
    assert original["summary"] in prompt and packet["packet_sha256"] in prompt
    with pytest.raises(ValueError, match="binding denied"):
        worker.run("same-specialist", "audit", message)
    assert sum(method == "turn/start" for method, _ in client.calls) == 1


class AuthorCorrectionClient(ControlledCodexClient):
    def request(self, method, params, *, deadline):
        if method == "thread/start":
            self.calls.append((method, params))
            return {"thread": {"id": getattr(self, "next_thread_id", "author-repair-thread"), "ephemeral": True},
                    "model": "gpt-5.5", "modelProvider": "openai", "reasoningEffort": "low",
                    "approvalPolicy": "never", "sandbox": {"type": "readOnly"}}
        return super().request(method, params, deadline=deadline)

    def draft_events(self, operation, message, thread_id):
        from workbench.providers.research_quality_offline import reply

        self.events = ControlledCodexClient().events
        for event in self.events:
            event["params"]["threadId"] = thread_id
        self.events[1]["params"]["item"]["text"] = json.dumps(reply(operation, message))


def length_request(**changes):
    params = {"tool": worker_module.TOOL_NAME, "namespace": worker_module.TOOL_NAMESPACE,
              "threadId": "parent-thread", "turnId": "plan-turn",
              "callId": "count-1", "arguments": {"sections": [{"id": "scope", "text": "one two"}]}}
    params.update(changes)
    return {"method": "item/tool/call", "params": params}


def counter_worker():
    worker = prepared_worker(ControlledCodexClient())
    worker.length_tool_active = {"thread_id": "parent-thread", "turn_id": "plan-turn",
                                 "bounds": {"min_words": 3, "max_words": 5}}
    worker.length_tool_receipts, worker.length_tool_call_ids = [], set()
    return worker


@pytest.mark.parametrize("changes", [{"tool": "shell"}, {"threadId": "other"}, {"turnId": "stale"},
    {"namespace": "other"}, {"namespace": None}, {"callId": None}, {"callId": ""}])
def test_counter_denies_other_capabilities_and_contexts(changes):
    worker = counter_worker()
    assert worker.handle_length_tool_request(length_request(**changes)) is None
    assert worker.length_tool_receipts == [] and worker.length_tool_call_ids == set()
    assert worker.handle_length_tool_request({"method": "account/chatgptAuthTokens/refresh"}) is None
    worker.length_tool_active = None
    assert worker.handle_length_tool_request(length_request()) is None


def test_counter_bounds_attempts_including_bad_arguments_and_replay():
    worker = counter_worker()
    response = worker.handle_length_tool_request(length_request(arguments={"path": "PRIVATE_PATH"}))
    assert not response["success"] and "PRIVATE_PATH" not in str(response)
    assert worker.handle_length_tool_request(length_request()) is None
    for i in range(2, 5):
        response = worker.handle_length_tool_request(length_request(callId=f"count-{i}"))
        assert response["success"]
        assert json.loads(response["contentItems"][0]["text"])["word_count"] == 2
    with pytest.raises(worker_module.WorkerStreamError, match="unsupported_item"):
        worker.handle_length_tool_request(length_request(callId="count-5"))
    assert len(worker.length_tool_receipts) == 3


@pytest.mark.parametrize("changed_after_check,call_counter", [(False, True), (True, True), (False, False)])
def test_author_counter_receipt_binds_final_text_without_new_prose_rejection(monkeypatch, changed_after_check, call_counter):
    from workbench.providers.research_quality_offline import reply

    client = AuthorCorrectionClient()
    worker = prepared_worker(client)
    worker.scratch = SimpleNamespace(name="synthetic-scratch")
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    message = {"contract": {"manuscript_length": {"min_words": 3, "max_words": 5}},
               "expected_response_ids": [], "token_limit": 20000, "time_limit_seconds": 20}
    candidate = reply("draft", message)
    candidate["sections"][0]["text"] = "one two three four"
    client.draft_events("draft", message, "author-repair-thread")
    client.events[1]["params"]["item"]["text"] = json.dumps(candidate)
    original_event = client.event
    did_check = []

    def event(*, deadline):
        if call_counter and not did_check:
            did_check.append(True)
            first = worker.handle_length_tool_request(length_request(threadId=worker.thread_id))
            assert json.loads(first["contentItems"][0]["text"])["status"] == "out_of_bounds"
            second = worker.handle_length_tool_request(length_request(threadId=worker.thread_id, callId="count-2",
                arguments={"sections": [{"id": candidate["sections"][0]["id"], "text": candidate["sections"][0]["text"]}]}))
            assert json.loads(second["contentItems"][0]["text"])["status"] == "within_bounds"
            if changed_after_check:
                candidate["sections"][0]["text"] += " five"
                client.events[1]["params"]["item"]["text"] = json.dumps(candidate)
            return {"method": "item/started", "params": {"threadId": worker.thread_id, "turnId": "plan-turn",
                "item": {"type": "dynamicToolCall", "tool": worker_module.TOOL_NAME,
                         "namespace": worker_module.TOOL_NAMESPACE}}}
        return original_event(deadline=deadline)

    client.event = event
    worker.run("author", "draft", message)
    result = next(fields for args, fields in emitted if args[1] == "draft")
    receipt = result["provenance"]["length_precheck"]
    assert receipt["matching_check"] == (call_counter and not changed_after_check)
    assert receipt["final"]["word_count"] == (5 if changed_after_check else 4)
    assert receipt["request_count"] == (2 if call_counter else 0)
    assert len(receipt["calls"]) == receipt["request_count"]
    assert all(c["success"] and c["call_stack"] and c["duration_seconds"] >= 0 for c in receipt["calls"])
    assert sum(method == "turn/start" for method, _ in client.calls) == 1
    thread = next(params for method, params in client.calls if method == "thread/start")
    assert thread["dynamicTools"][0]["name"] == worker_module.TOOL_NAMESPACE
    counter = thread["dynamicTools"][0]["tools"][0]
    assert counter["name"] == worker_module.TOOL_NAME
    assert result["provenance"]["length_tool_registration"] == {
        "registered": True, "tool": worker_module.TOOL_NAME,
        "namespace": worker_module.TOOL_NAMESPACE, "max_checks": 4,
        "input_schema_sha256": worker_module.stable_hash(counter["inputSchema"])}
    assert counter["deferLoading"] is False
    assert result["provenance"]["length_tool_capability"]["successful_invocation_received"] is call_counter
    assert result["provenance"]["length_tool_capability"]["verification"] == "pinned_runtime_offline"
    assert worker.length_tool_active is None and "one two" not in json.dumps(receipt)


def test_fresh_author_correction_resets_counter_calls_but_keeps_original_binding(monkeypatch):
    from workbench.models import stable_hash
    from workbench.providers.research_quality_offline import reply

    client = AuthorCorrectionClient()
    worker = prepared_worker(client)
    worker.scratch = SimpleNamespace(name="synthetic-scratch")
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    message = {"contract": {"manuscript_length": {"min_words": 3, "max_words": 5}},
               "expected_response_ids": [], "token_limit": 20000, "time_limit_seconds": 20}
    candidate = reply("draft", message)
    candidate["sections"][0]["text"] = "one two three four"
    original_event = client.event
    checked_turns = set()

    def event(*, deadline):
        if worker.thread_id not in checked_turns:
            checked_turns.add(worker.thread_id)
            for i in range(4):
                response = worker.handle_length_tool_request(length_request(threadId=worker.thread_id,
                    callId=f"count-{i}", arguments={"sections": [{"id": s["id"], "text": s["text"]}
                                                             for s in candidate["sections"]]}))
                assert response["success"]
        return original_event(deadline=deadline)

    client.event = event
    for thread in ("author-repair-thread", "fresh-correction-thread"):
        client.next_thread_id = thread
        client.draft_events("draft", message, thread)
        client.events[1]["params"]["item"]["text"] = json.dumps(candidate)
        worker.run("author", "draft", message)
        message = {**message, "draft_corrections": [{"code": "synthetic_check"}],
                   "original_draft": candidate, "original_draft_sha256": stable_hash(candidate)}
    drafts = [fields for args, fields in emitted if args[1] == "draft"]
    assert [r["provenance"]["length_precheck"]["request_count"] for r in drafts] == [4, 4]
    assert all(r["provenance"]["length_precheck"]["matching_check"] for r in drafts)
    assert drafts[-1]["provenance"]["context_policy"] == "fresh_author_correction"
    assert sum(method == "turn/start" for method, _ in client.calls) == 2
    assert worker.total_tokens == 83


@pytest.mark.parametrize("operation", ["draft", "revise"])
def test_author_correction_fresh_context_binds_packet_and_only_resets_thread_usage(monkeypatch, operation):
    from workbench.models import stable_hash
    from workbench.providers.research_quality_offline import reply

    client = AuthorCorrectionClient()
    worker = prepared_worker(client)
    worker.scratch = SimpleNamespace(name="synthetic-scratch")
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    payload = {"contract": {"question": "Synthetic"}, "sources": [{"source_id": "s1", "text": "FROZEN"}],
               "verification_receipts": [], "search_receipts": [],
               "prior_comments": [{"id": "review-1"}] if operation == "revise" else [],
               "expected_response_ids": ["review-1"] if operation == "revise" else [],
               "previous_candidate": reply("draft", {}) if operation == "revise" else None,
               "token_limit": 20000, "time_limit_seconds": 20, "call_span_id": "first-span"}
    initial_thread = "parent-thread"
    if operation == "revise":
        payload["previous_candidate_sha256"] = stable_hash(payload["previous_candidate"])
        worker.last_author_candidate = {"draft_sha256": payload["previous_candidate_sha256"],
                                        "evidence_sha256": worker_module.author_evidence_hash(payload)}
        initial_thread = client.next_thread_id = "author-revision-thread"
    client.draft_events(operation, payload, initial_thread)
    worker.run("same-author", operation, payload)
    original = reply(operation, payload)
    correction = {**payload, "call_span_id": "correction-span", "token_limit": 19000,
                  "original_draft": original, "original_draft_sha256": stable_hash(original),
                  "draft_corrections": [{"code": "manuscript_length", "path": "/sections"}]}
    client.draft_events(operation, correction, "author-repair-thread")
    client.next_thread_id = "author-repair-thread"
    worker.run("same-author", operation, correction)
    results = [fields for args, fields in emitted if args[1] == "draft"]
    assert len(results) == 2 and [r["usage"]["tokens"] for r in results] == [83, 83]
    assert worker.total_tokens == 83
    assert results[-1]["provenance"]["context_policy"] == "fresh_author_correction"
    assert results[-1]["provenance"]["prior_codex_thread_id"] == initial_thread
    turns = [params for method, params in client.calls if method == "turn/start"]
    prompt = turns[-1]["input"][0]["text"]
    assert "FROZEN" in prompt and stable_hash(original) in prompt and original["title"] in prompt
    assert turns[-1]["outputSchema"]["properties"]["responses"]["minItems"] == len(payload["expected_response_ids"])
    with pytest.raises(ValueError, match="binding denied"):
        worker.run("same-author", operation, correction)
    assert sum(method == "turn/start" for method, _ in client.calls) == 2


@pytest.mark.parametrize("tamper", ["draft", "hash", "source", "responses", "operation"])
def test_author_correction_rejects_tampering_before_fresh_thread(monkeypatch, tamper):
    from workbench.models import stable_hash
    from workbench.providers.research_quality_offline import reply

    client = AuthorCorrectionClient()
    worker = prepared_worker(client)
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: None)
    payload = {"sources": [{"source_id": "s1", "text": "Frozen"}], "expected_response_ids": [],
               "token_limit": 20000, "time_limit_seconds": 20}
    client.draft_events("draft", payload, "parent-thread")
    worker.run("same-author", "draft", payload)
    original = reply("draft", payload)
    correction = {**payload, "original_draft": original, "original_draft_sha256": stable_hash(original),
                  "draft_corrections": [{"code": "controlled"}]}
    if tamper == "draft":
        correction["original_draft"] = {**original, "title": "Changed"}
        correction["original_draft_sha256"] = stable_hash(correction["original_draft"])
    elif tamper == "hash":
        correction["original_draft_sha256"] = "a" * 64
    elif tamper == "source":
        correction["sources"] = []
    elif tamper == "responses":
        correction["expected_response_ids"] = ["invented"]
    with pytest.raises(ValueError, match="binding denied"):
        worker.run("same-author", "revise" if tamper == "operation" else "draft", correction)
    assert sum(method == "turn/start" for method, _ in client.calls) == 1
    assert not any(method == "thread/start" for method, _ in client.calls)


@pytest.mark.parametrize("fail", [False, True])
def test_stream_measurements_reset_and_preserve_content_free_terminal_snapshot(monkeypatch, fail):
    client = ControlledCodexClient()
    worker = prepared_worker(client)
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    for span in ("first", "second"):
        client.events = ControlledCodexClient().events
        client.events.insert(0, {"method": "item/agentMessage/delta", "params": {
            "threadId": "parent-thread", "delta": "秘密"}})
        if fail:
            client.events[1] = {"method": "error", "params": {"message": "PRIVATE_FAILURE"}}
            with pytest.raises(worker_module.WorkerStreamError):
                worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20,
                                               "call_span_id": span})
        else:
            client.events[1]["params"]["tokenUsage"]["total"]["totalTokens"] = worker.total_tokens + 83
            worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20,
                                           "call_span_id": span})
    snapshots = [fields["progress"]["stream"] for args, fields in emitted
                 if args[1] == "progress" and fields["progress"].get("stream", {}).get("finished")]
    assert [row["call_span_id"] for row in snapshots] == ["first", "second"]
    for row in snapshots:
        assert row["delta_count"] == 1 and row["characters"] == 2 and row["utf8_bytes"] == 6
        assert 0 <= row["first_delta_seconds"] <= row["last_delta_seconds"] <= row["elapsed_seconds"]
        assert row["prompt_tokens"] > 0
        assert row["prompt_counting_policy"] == worker_module.prompt_token_measurement("probe")[1]
        assert (row["completed_text_characters"] > 0) is not fail
    assert "秘密" not in json.dumps(snapshots, ensure_ascii=False)
    assert "PRIVATE_FAILURE" not in json.dumps(snapshots)


def stream_progress_fixture():
    return {"source": "codex_notification", "stage": "turn_stream",
            "timestamp": "2026-10-05T00:00:00+00:00", "elapsed_seconds": 5,
            "codex_notification_count": 2, "codex_notification_types": {"item/agentMessage/delta": 2},
            "stream": {"call_span_id": "span1", "codex_thread_id": "thread1", "codex_turn_id": "turn1",
                       "delta_count": 2, "characters": 4, "utf8_bytes": 6,
                       "first_delta_seconds": 0.1, "last_delta_seconds": 0.2, "elapsed_seconds": 1,
                       "prompt_tokens": 100, "prompt_counting_policy": "o200k_base", "finished": False,
                       "completed_text_characters": 0, "completed_text_utf8_bytes": 0}}


def test_controller_persists_turn_measurements_separately_and_accepts_legacy_progress():
    from workbench.services.research_runner import Runner

    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: None))
    agent = SimpleNamespace(provenance={"active_model_turn": {"codex_thread_id": "thread1", "codex_turn_id": "turn1"}})
    progress = stream_progress_fixture()
    def deliver(payload, span):
        return Runner.event(runner, SimpleNamespace(poll=lambda: {"type": "progress", "progress": payload}),
                            agent, {"span_id": span}, "draft")
    deliver(progress, "span1")
    progress["stream"] = {**progress["stream"], "finished": True, "elapsed_seconds": 2}
    deliver(progress, "span1")
    assert len(agent.provenance["codex_streams"]) == 1
    agent.provenance["active_model_turn"] = {"codex_thread_id": "thread2", "codex_turn_id": "turn2"}
    progress["stream"] = {**stream_progress_fixture()["stream"], "call_span_id": "span2",
                          "codex_thread_id": "thread2", "codex_turn_id": "turn2", "delta_count": 1}
    deliver(progress, "span2")
    assert [row["call_span_id"] for row in agent.provenance["codex_streams"]] == ["span1", "span2"]
    legacy = {k: v for k, v in progress.items() if k != "stream"}
    deliver(legacy, "span2")
    assert len(agent.provenance["codex_streams"]) == 2


@pytest.mark.parametrize("field,value", [
    ("call_span_id", "other-span"), ("codex_thread_id", "other-thread"), ("codex_turn_id", "other-turn"),
    ("characters", True), ("utf8_bytes", -1), ("delta_count", 0),
    ("elapsed_seconds", float("nan")), ("last_delta_seconds", float("inf")),
    ("first_delta_seconds", 2), ("prompt_counting_policy", []), ("finished", "yes"),
    ("private_text", "PRIVATE_CONTENT"),
])
def test_controller_rejects_invalid_stream_measurements(field, value):
    from workbench.providers.research_executor import ExecutorError
    from workbench.services.research_runner import Runner

    commits = []
    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: commits.append(True)))
    agent = SimpleNamespace(provenance={"active_model_turn": {"codex_thread_id": "thread1", "codex_turn_id": "turn1"}})
    progress = stream_progress_fixture()
    progress["stream"][field] = value
    with pytest.raises(ExecutorError):
        Runner.event(runner, SimpleNamespace(poll=lambda: {"type": "progress", "progress": progress}),
                     agent, {"span_id": "span1"}, "draft")
    assert not commits and "codex_streams" not in agent.provenance


@pytest.mark.parametrize("field,value", [("delta_count", 1), ("elapsed_seconds", 0.5), ("finished", False)])
def test_controller_rejects_regressed_or_reopened_stream_measurements(field, value):
    from workbench.providers.research_executor import ExecutorError
    from workbench.services.research_runner import validate_stream_measurement

    previous = {**stream_progress_fixture()["stream"], "finished": True}
    agent = SimpleNamespace(provenance={"active_model_turn": {"codex_thread_id": "thread1", "codex_turn_id": "turn1"},
                                        "codex_streams": [previous]})
    with pytest.raises(ExecutorError):
        validate_stream_measurement({**previous, field: value}, agent, {"span_id": "span1"})


def test_native_schema_prompt_preserves_frozen_data_without_second_schema(monkeypatch):
    client = ControlledCodexClient()
    worker = prepared_worker(client)
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: None)
    message = {"token_limit": 4000, "time_limit_seconds": 20,
               "sources": [], "contract": {"question": "Literal \"quotes\" and λ"}}
    worker.run("parent", "plan", message)
    turn = next(params for method, params in client.calls if method == "turn/start")
    prompt = turn["input"][0]["text"]
    assert "JSON schema:" not in prompt
    data = json.loads(prompt.split("Operation and frozen task data:\n", 1)[1])
    assert data == {"operation": "plan", "message": message}
    assert turn["outputSchema"]["additionalProperties"] is False
    assert turn["outputSchema"]["required"] == ["rationale", "assignments"]


@pytest.mark.parametrize("prior_correction", [False, True])
def test_scientific_revision_starts_fresh_from_latest_bound_candidate(monkeypatch, prior_correction):
    from workbench.models import stable_hash
    from workbench.providers.research_quality_offline import reply

    client = AuthorCorrectionClient()
    worker = prepared_worker(client)
    worker.scratch = SimpleNamespace(name="synthetic-scratch")
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    payload = {"contract": {"question": "Synthetic"}, "sources": [], "verification_receipts": [],
               "search_receipts": [], "prior_comments": [], "expected_response_ids": [],
               "previous_candidate": None, "previous_candidate_sha256": None,
               "token_limit": 20000, "time_limit_seconds": 20, "call_span_id": "draft-span"}
    client.draft_events("draft", payload, "parent-thread")
    worker.run("author", "draft", payload)
    latest = reply("draft", payload)
    old_thread = "parent-thread"
    if prior_correction:
        correction = {**payload, "original_draft": latest, "original_draft_sha256": stable_hash(latest),
                      "draft_corrections": [{"code": "controlled"}], "call_span_id": "repair-span"}
        client.draft_events("draft", correction, "author-repair-thread")
        latest = {**latest, "title": "Corrected original title"}
        client.events[1]["params"]["item"]["text"] = json.dumps(latest)
        worker.run("author", "draft", correction)
        old_thread = "author-repair-thread"
    revision = {**payload, "previous_candidate": latest, "previous_candidate_sha256": stable_hash(latest),
                "prior_comments": [{"id": "source-coverage"}], "expected_response_ids": ["source-coverage"],
                "call_span_id": "revision-span", "token_limit": 18000, "time_limit_seconds": 10}
    client.next_thread_id = "scientific-revision-thread"
    client.draft_events("revise", revision, "scientific-revision-thread")
    worker.run("author", "revise", revision)
    final = [fields for args, fields in emitted if args[1] == "draft"][-1]
    assert final["usage"]["tokens"] == 83 and worker.total_tokens == 83
    assert final["provenance"]["context_policy"] == "fresh_author_revision"
    assert final["provenance"]["prior_codex_thread_id"] == old_thread
    turn = [params for method, params in client.calls if method == "turn/start"][-1]
    data = json.loads(turn["input"][0]["text"].split("Operation and frozen task data:\n", 1)[1])
    assert data["message"] == revision
    assert final["result"]["responses"][0]["comment_id"] == "source-coverage"


@pytest.mark.parametrize("tamper", ["candidate", "hash", "evidence", "missing_prior"])
def test_scientific_revision_binding_failure_prevents_dispatch(monkeypatch, tamper):
    from workbench.models import stable_hash
    from workbench.providers.research_quality_offline import reply

    client = AuthorCorrectionClient()
    worker = prepared_worker(client)
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: None)
    payload = {"contract": {"question": "Synthetic"}, "sources": [], "expected_response_ids": [],
               "token_limit": 20000, "time_limit_seconds": 20}
    client.draft_events("draft", payload, "parent-thread")
    worker.run("author", "draft", payload)
    original = reply("draft", payload)
    revision = {**payload, "previous_candidate": original, "previous_candidate_sha256": stable_hash(original)}
    if tamper == "candidate":
        revision["previous_candidate"] = {**original, "title": "Injected candidate"}
        revision["previous_candidate_sha256"] = stable_hash(revision["previous_candidate"])
    elif tamper == "hash":
        revision["previous_candidate_sha256"] = "a" * 64
    elif tamper == "evidence":
        revision["sources"] = [{"source_id": "injected"}]
    else:
        worker.last_author_candidate = {}
    with pytest.raises(ValueError, match="previous candidate binding denied"):
        worker.run("author", "revise", revision)
    assert sum(method == "turn/start" for method, _ in client.calls) == 1
    assert not any(method == "thread/start" for method, _ in client.calls)


def synthetic_agent_report():
    return {"summary": "Synthetic bounded report", "findings": [], "citations": [],
            "proof_attempts": [], "failed_approaches": [], "unresolved_questions": [],
            "research_leads": [], "search_log": [], "verification_artifacts": []}


@pytest.mark.parametrize("defect,code,path", [
    ("missing_field", "missing", ["summary"]),
    ("extra_field", "extra_forbidden", ["*"]),
    ("duplicate_ids", "report_duplicate_ids", []),
    ("missing_evidence", "report_missing_evidence", []),
    ("unverified_result", "report_unverified_result", []),
    ("uncited_prior_art", "report_uncited_prior_art", []),
    ("unrecorded_search", "report_unrecorded_search", []),
    ("citation_target", "citation_target", ["citations", 0]),
    ("citation_url", "citation_url", ["citations", 0]),
    ("invalid_json", "json_invalid", []),
])
def test_completed_invalid_child_records_safe_diagnostics_without_retry(monkeypatch, defect, code, path):
    from workbench.providers.research_executor import ExecutorError
    from workbench.services import research_trace
    from workbench.services.research_runner import Runner

    report = synthetic_agent_report()
    finding = {"id": "f1", "claim_key": "bounded", "statement": "PRIVATE_MODEL_TEXT",
               "category": "unresolved", "stance": "neutral", "scope": "synthetic",
               "citation_ids": [], "verification_ids": []}
    report["findings"] = [finding]
    if defect == "missing_field":
        del report["summary"]
    elif defect == "extra_field":
        report["PRIVATE_EXTRA_KEY"] = "PRIVATE_VALUE"
    elif defect == "duplicate_ids":
        report["findings"].append(dict(finding))
    elif defect == "missing_evidence":
        finding["citation_ids"] = ["PRIVATE_MISSING_CITATION"]
    elif defect in {"unverified_result", "uncited_prior_art", "unrecorded_search"}:
        finding["category"] = {"unverified_result": "verified_result",
                               "uncited_prior_art": "apparent_prior_art",
                               "unrecorded_search": "nothing_found"}[defect]
    elif defect.startswith("citation_"):
        report["citations"] = [{"id": "c1", "source_id": "", "url": "",
                                "locator": "PRIVATE_LOCATOR", "access": "frozen"}]
        if defect == "citation_url":
            report["citations"][0]["url"] = "file:///PRIVATE_PATH"
    output = "{PRIVATE_INVALID_JSON" if defect == "invalid_json" else json.dumps(report)
    client = ControlledCodexClient()
    client.events[1]["params"]["item"]["text"] = output
    client.events.insert(1, {"method": "item/agentMessage/delta", "params": {
        "threadId": "parent-thread", "delta": output}})
    worker = prepared_worker(client)
    closed, emitted, traces = [], [], []
    worker.preflight = lambda deadline: None
    worker.close = lambda: closed.append(True)
    monkeypatch.setattr(worker_module, "CodexResearchWorker", lambda: worker)
    request = {"agent_id": "child", "op": "research", "token_limit": 4000, "time_limit_seconds": 20}
    wire = json.dumps({"agent_id": "child", "op": "hello"}) + "\n" + json.dumps(request) + "\n"
    monkeypatch.setattr(worker_module.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(wire.encode())))
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: emitted.append((args, kw)))
    worker_module.main()

    args, fields = emitted[-1]
    expected = {"error_count": 1, "errors": [{"code": code, "path": path}]}
    assert args == ("child", "error")
    assert fields["stage"] == "report_validation"
    assert fields["validation_diagnostics"] == expected
    assert not any(args[1] == "report" for args, _ in emitted)
    assert closed == [True]
    assert sum(method == "turn/start" for method, _ in client.calls) == 1
    assert worker.stream_measurement["completed_text_characters"] == len(output)

    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: traces.append(kw))
    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: None))
    agent = SimpleNamespace(provenance={})
    event = {"type": "error", **fields}
    with pytest.raises(ExecutorError):
        Runner.event(runner, SimpleNamespace(poll=lambda: event), agent, {}, "report")
    assert agent.provenance["worker_validation_diagnostics"] == expected
    assert traces[0]["validation_diagnostics"] == expected
    assert "PRIVATE" not in json.dumps(agent.provenance)


def test_validation_diagnostics_bound_and_scrub_untrusted_worker_fields(monkeypatch):
    from workbench.providers.research_executor import ExecutorError
    from workbench.providers.research_validation import normalize_validation_diagnostics
    from workbench.services import research_trace
    from workbench.services.research_runner import Runner

    value = {"error_count": 30, "errors": [{"code": "PRIVATE_CODE",
        "path": ["findings", 0, "PRIVATE_KEY", {"PRIVATE": True}, -1],
        "message": "PRIVATE_MESSAGE", "input": "PRIVATE_RESPONSE"}] * 30}
    cleaned = normalize_validation_diagnostics(value)
    assert cleaned["error_count"] == 30 and len(cleaned["errors"]) == 20
    assert cleaned["errors"][0] == {"code": "value_error", "path": ["findings", 0, "*", "*", "*"]}
    assert "PRIVATE" not in json.dumps(cleaned)
    for bad in (None, [], {}, {"error_count": True, "errors": [{}]},
                {"error_count": 1, "errors": ["PRIVATE"]}):
        assert normalize_validation_diagnostics(bad) is None

    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: None)
    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: None))
    for stage in ("report_validation", "turn_stream"):
        agent = SimpleNamespace(provenance={})
        event = {"type": "error", "stage": stage, "error_class": "ValidationError",
                 "validation_diagnostics": value}
        with pytest.raises(ExecutorError):
            Runner.event(runner, SimpleNamespace(poll=lambda event=event: event), agent, {}, "report")
        assert agent.provenance.get("worker_validation_diagnostics") == (
            cleaned if stage == "report_validation" else None)


@pytest.mark.parametrize("ids", [[], ["completed-1", "completed-2"]])
def test_synthesis_schema_excludes_failed_lineage_ids(ids):
    message = {"contract": {"deliverables": ["research_report"]},
               "reports": dict.fromkeys(ids, {}),
               "lineage": [{"id": key, "state": "completed"} for key in ids]
                          + [{"id": "failed-child", "state": "failed"}]}
    schema = worker_module.output_schema("integrate", message)
    report_ids = schema["properties"]["report_ids"]
    assert report_ids["minItems"] == report_ids["maxItems"] == len(ids)
    assert report_ids["items"].get("enum") == (ids or None)
    prompt = worker_module.json_prompt("integrate", message)
    assert "exactly the keys of message.reports, each once" in prompt
    assert "Lineage and checkpoints do not add report IDs" in prompt


def test_child_prompt_states_cross_reference_contract_without_fabricating_evidence():
    prompt = worker_module.json_prompt("research", {})
    assert "IDs must be unique within findings, citations and verification_artifacts" in prompt
    assert "citation_ids and verification_ids must reference entries in this report" in prompt
    assert "Never invent evidence or change a failed/not_run outcome" in prompt


def test_prompt_measurement_without_optional_tokenizer_is_conservative(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def without_tokenizer(name, *args, **kwargs):
        if name == "tiktoken":
            raise ImportError("controlled missing optional dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_tokenizer)
    text = "Frozen evidence 秘密"
    assert worker_module.prompt_token_measurement(text) == (
        len(text.encode("utf-8")), "utf8-byte-upper-estimate")
    assert worker_module.prompt_token_count(text) == len(text.encode("utf-8"))
