"""Receipt reconstruction requires the completed pinned validation path, never progress alone."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from workbench.services import completed_usage_reconciliation as service
from workbench.services.research_tasks import TaskError


@pytest.fixture
def saved(monkeypatch):
    agent = SimpleNamespace(provenance={
        "capabilities": {"executor": "Codex app-server 0.160.1"},
        "worker_failure_stage": "report_validation", "worker_failure_class": "ValidationError",
        "active_model_turn": {"codex_thread_id": "thread", "codex_turn_id": "turn"},
        "codex_streams": [{"call_span_id": "span", "finished": True, "characters": 100,
                          "completed_text_characters": 100,
                          "codex_thread_id": "thread", "codex_turn_id": "turn"}],
    })
    task = SimpleNamespace(state="failed_partial", ledger={
        "charged_tokens": 1000, "actual_tokens": 83, "previous_runs": [{"immutable": "history"}],
        "allocations": [{"agent_id": "a", "span_id": "span", "phase": "revise", "reserved": 1000,
                         "actual_tokens": 83, "reported_tokens": 83, "usage_kind": "actual",
                         "usage_source": "Codex thread/tokenUsage/updated"}],
        "call_trace": [{"event": "worker_failed", "agent_id": "a", "span_id": "span",
                        "failure_stage": "report_validation", "failure_class": "ValidationError"}],
    })
    audits = []
    session = SimpleNamespace(get=lambda *_args: agent, commit=lambda: None)
    monkeypatch.setattr(service.manuscript_continuation, "checkpoint",
                        lambda *_args: {"checkpoint_sha256": "a" * 64})
    monkeypatch.setattr(service.research_tasks, "audit", lambda *args: audits.append(args[-1]))
    return task, agent, session, audits


def test_verified_completion_releases_only_unused_reservation_with_audit(saved):
    task, _agent, session, audits = saved
    before_history = deepcopy(task.ledger["previous_runs"])
    result = service.reconcile(session, task, "a" * 64)
    assert result["charged_tokens"] == task.ledger["actual_tokens"] == 83
    assert task.ledger["usage_complete"] and task.ledger["estimated_tokens"] == 0
    assert task.ledger["previous_runs"] == before_history
    assert audits[0]["before_charged"] == 1000 and audits[0]["after_charged"] == 83
    assert task.ledger["allocations"][0]["released_tokens"] == 917
    assert service.reconcile(session, task, "a" * 64)["changed"] is False
    assert len(audits) == 1


@pytest.mark.parametrize("defect", [
    "checkpoint", "unfinished", "no_text", "foreign_turn", "wrong_stage",
    "unpinned", "no_failure", "estimate", "counter_mismatch", "running",
])
def test_unverifiable_usage_retains_entire_reservation_without_mutation(saved, defect):
    task, agent, session, audits = saved
    digest = "b" * 64 if defect == "checkpoint" else "a" * 64
    if defect == "unfinished":
        agent.provenance["codex_streams"][0]["finished"] = False
    elif defect == "no_text":
        agent.provenance["codex_streams"][0]["completed_text_characters"] = 0
    elif defect == "foreign_turn":
        agent.provenance["codex_streams"][0]["codex_turn_id"] = "foreign"
    elif defect == "wrong_stage":
        agent.provenance["worker_failure_stage"] = "turn_stream"
    elif defect == "unpinned":
        agent.provenance["capabilities"]["executor"] = "unverified"
    elif defect == "no_failure":
        task.ledger["call_trace"] = []
    elif defect == "estimate":
        task.ledger["allocations"][0]["usage_kind"] = "estimate"
    elif defect == "counter_mismatch":
        task.ledger["allocations"][0]["reported_tokens"] = 82
    elif defect == "running":
        task.state = "researching"
    before = deepcopy(task.ledger)
    with pytest.raises(TaskError):
        service.reconcile(session, task, digest)
    assert task.ledger == before and not audits
