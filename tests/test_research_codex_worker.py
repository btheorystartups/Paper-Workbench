"""Offline checks of the Codex worker's turn and telemetry boundary."""

import json
import threading
import time
from types import SimpleNamespace

import pytest

from workbench.providers import research_codex_worker as worker_module


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
        codex_local_model="gpt-5.6-sol", codex_local_reasoning_effort="low"
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


def test_codex_worker_refuses_account_change_before_turn(monkeypatch):
    client = ControlledCodexClient(account="different@example.invalid")
    worker = prepared_worker(client)
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kw: None)
    with pytest.raises(ValueError, match="account changed"):
        worker.run("parent", "plan", {"token_limit": 4000, "time_limit_seconds": 20})
    assert all(method != "turn/start" for method, _ in client.calls)


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
