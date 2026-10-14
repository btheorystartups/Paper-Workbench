"""Expanded inventories and retained-return recovery remain bounded and provenance-bound."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_research_codex_worker import ControlledCodexClient, prepared_worker

from workbench.models import stable_hash
from workbench.providers import research_codex_worker as worker_module
from workbench.research_contract import (
    MAX_MANUSCRIPT_CLAIMS,
    ManuscriptDraft,
    SpecialistReport,
)
from workbench.services.manuscript_continuation import recoverable_return


def candidate(count=61):
    identifiers = [f"C{i}" for i in range(1, count + 1)]
    return {"title": "Retained example", "novelty_claim": False, "limitations": ["Bounded fixture"],
            "sections": [{"id": "S1", "heading": "Example", "text": "Source-grounded assertion.",
                          "claim_ids": identifiers}],
            "claims": [{"id": key, "statement": "Source-grounded assertion.", "kind": "method",
                        "source_ids": [], "verification_ids": []} for key in identifiers],
            "responses": []}


def test_claim_capacity_is_consistent_and_still_bounded():
    assert len(ManuscriptDraft.model_validate(candidate()).claims) == 61
    assert SpecialistReport.model_json_schema()["properties"]["assessments"]["maxItems"] == 80
    assert MAX_MANUSCRIPT_CLAIMS == 80
    with pytest.raises(ValidationError):
        ManuscriptDraft.model_validate(candidate(81))


@pytest.mark.parametrize("defect", [None, "history", "hash", "unfinished", "foreign_span", "shape"])
def test_only_complete_bound_retained_return_can_seed_recovery(defect):
    raw = candidate()
    raw["claims"] = raw["claims"][:40]
    output = {"operation": "revise", "call_span_id": "span",
              "result": raw, "result_sha256": stable_hash(raw)}
    parent = SimpleNamespace(id="author", provenance={"returned_outputs": [output]})
    rejected = {"operation": "revise", "agent_id": "author", "span_id": "span",
                "draft_sha256": output["result_sha256"]}
    allocation = {"agent_id": "author", "span_id": "span", "final_actual": True}
    if defect == "hash":
        output["result_sha256"] = "b" * 64
    elif defect == "unfinished":
        allocation["final_actual"] = False
    elif defect == "foreign_span":
        rejected["span_id"] = "foreign"
    elif defect == "shape":
        raw["sections"] = [{"invalid": "shape"}]
        output["result_sha256"] = rejected["draft_sha256"] = stable_hash(raw)
    ledger = ({"previous_runs": [{"ledger": {"allocations": [allocation]}}]} if defect == "history"
              else {"allocations": [allocation]})
    recovered = recoverable_return(
        parent, SimpleNamespace(body={"rejected_drafts": [rejected]}),
        SimpleNamespace(ledger=ledger))
    assert bool(recovered) is (defect in {None, "history"})


@pytest.mark.parametrize("tamper", [False, True])
def test_fresh_worker_can_repair_only_a_bound_author_return(monkeypatch, tamper):
    raw = candidate()
    client = ControlledCodexClient()
    client.events[1]["params"]["item"]["text"] = json.dumps(raw)
    worker = prepared_worker(client)
    worker.thread_id = None
    worker.ensure_thread = lambda *_args, **_kwargs: setattr(worker, "thread_id", "parent-thread")
    message = {"call_span_id": "span", "token_limit": 20000, "time_limit_seconds": 20,
               "draft_corrections": [{"code": "claim_inventory"}], "original_draft": raw,
               "original_draft_sha256": stable_hash(raw), "expected_response_ids": [],
               "recovery_claim_ids": [row["id"] for row in raw["claims"]]}
    message["author_return_checkpoint"] = {
        "checkpoint_sha256": "a" * 64,
        "draft_sha256": "b" * 64 if tamper else stable_hash(raw),
        "evidence_sha256": worker_module.author_evidence_hash(message),
    }
    schema = worker_module.output_schema("revise", message)
    assert schema["properties"]["claims"]["minItems"] == schema["properties"]["claims"]["maxItems"] == 61
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    if tamper:
        with pytest.raises(ValueError):
            worker.run("author", "revise", message)
        assert not any(method == "turn/start" for method, _params in client.calls)
    else:
        worker.run("author", "revise", message)
        result = next(fields for args, fields in emitted if args[1] == "draft")
        assert len(result["result"]["claims"]) == 61
        assert sum(method == "turn/start" for method, _params in client.calls) == 1


def test_recovery_counter_budget_is_enforced_before_another_tool_roundtrip():
    worker = prepared_worker(ControlledCodexClient())
    worker.length_tool_active = {"thread_id": "thread", "turn_id": "turn", "max_checks": 1}
    worker.length_tool_call_ids = {"first"}
    request = {"method": "item/tool/call", "params": {
        "threadId": "thread", "turnId": "turn", "callId": "second",
        "tool": worker_module.TOOL_NAME, "namespace": worker_module.TOOL_NAMESPACE,
    }}
    with pytest.raises(worker_module.WorkerStreamError):
        worker.handle_length_tool_request(request)
