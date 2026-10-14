"""Failure-boundary regressions; controlled workers and in-memory accounting only."""

import copy
from types import SimpleNamespace

import pytest
from test_research_codex_worker import ControlledCodexClient, prepared_worker
from test_retained_author_recovery import candidate

from workbench.models import stable_hash
from workbench.providers import research_codex_worker as worker_module
from workbench.services.manuscript_continuation import recoverable_return
from workbench.services.research_recovery import (
    AuthorizationGrant,
    accounting,
    admit_operation,
    continuation_authorization,
    envelope,
)
from workbench.services.research_runner import Runner, StopResearch, allocation_charge
from workbench.services.research_tasks import TaskError


def test_preflight_rejection_releases_only_proven_undispatched_reservation(monkeypatch):
    client = ControlledCodexClient()
    worker = prepared_worker(client)
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda agent, kind, **fields:
                        emitted.append({"type": kind, **fields}))
    worker.run("author", "draft", {"call_span_id": "span", "token_limit": 100, "time_limit_seconds": 20})
    event = next(e for e in emitted if e["type"] == "limit")
    assert not any(method == "turn/start" for method, _ in client.calls)
    allocation = {"span_id": "span", "phase": "draft", "reserved": 100}
    runner = SimpleNamespace(task=SimpleNamespace(contract={"executor": "process"}),
        session=SimpleNamespace(commit=lambda: None), save_ledger=lambda: None)
    runner.usage = lambda *args: Runner.usage(runner, *args)
    with pytest.raises(StopResearch):
        Runner.event(runner, SimpleNamespace(poll=lambda: event), SimpleNamespace(provenance={}),
                     allocation, "draft")
    assert allocation_charge(allocation) == 0 and allocation["final_actual"]
    unknown = {"span_id": "other", "phase": "draft", "reserved": 100}
    with pytest.raises(StopResearch):
        Runner.event(runner, SimpleNamespace(poll=lambda: {"type": "limit"}),
                     SimpleNamespace(provenance={}), unknown, "draft")
    assert allocation_charge(unknown) == 100


def test_invalid_completed_review_is_saved_before_validation(monkeypatch):
    client = ControlledCodexClient()
    client.events[1]["params"]["item"]["text"] = "{}"
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda agent, kind, **fields:
                        emitted.append({"type": kind, **fields}))
    prepared_worker(client).run("reviewer", "audit", {"call_span_id": "span", "token_limit": 10000,
                                                     "time_limit_seconds": 20})
    kinds = [e["type"] for e in emitted]
    assert (kinds.index("output_checkpoint") < kinds.index("turn_usage_receipt")
            < kinds.index("invalid_return"))
    assert next(e for e in emitted if e["type"] == "turn_usage_receipt")["usage"]["tokens"] == 83
    assert next(e for e in emitted if e["type"] == "output_checkpoint")["complete_message"]


def test_complete_bound_content_can_recover_without_releasing_unknown_usage():
    raw = candidate()
    output = {"operation": "revise", "call_span_id": "span", "result": raw,
              "result_sha256": stable_hash(raw), "identity_verified": True}
    allocation = {"agent_id": "author", "span_id": "span", "reserved": 1000, "final_actual": False}
    parent = SimpleNamespace(id="author", provenance={"returned_outputs": [output]})
    campaign = SimpleNamespace(body={"rejected_drafts": [{"operation": "revise", "agent_id": "author",
                                  "span_id": "span", "draft_sha256": stable_hash(raw)}]})
    task = SimpleNamespace(ledger={"allocations": [allocation]})
    assert recoverable_return(parent, campaign, task) == output
    assert accounting(task) == {"known_tokens": 0, "charged_tokens": 1000, "held_tokens": 1000}
    output["identity_verified"] = False
    assert recoverable_return(parent, campaign, task) is None


def test_continuation_cannot_omit_history_or_unknown_reservations():
    authority = envelope(AuthorizationGrant(token_ceiling=10000, time_ceiling_seconds=100,
                                           reason="Test approval"))
    task = SimpleNamespace(ledger={"authorization": authority, "allocations": [{"reserved": 3000}],
        "previous_runs": [{"ledger": {"allocations": [{"reserved": 4000, "actual_tokens": 2000,
                                                         "final_actual": True}]}}]})
    grant = SimpleNamespace(authorization=None, token_limit=5001, time_limit_seconds=20)
    with pytest.raises(TaskError, match="aggregate token"):
        continuation_authorization(task, grant)
    grant.token_limit = 5000
    assert continuation_authorization(task, grant) == authority
    del task.ledger["authorization"]
    with pytest.raises(TaskError, match="explicit aggregate"):
        continuation_authorization(task, grant)


def test_retry_counts_survive_run_boundaries_and_changed_budget():
    task = SimpleNamespace(ledger={})
    payload = {"original_draft_sha256": "a" * 64, "draft_corrections": [{"code": "length"}]}
    key = admit_operation(task, "revise", payload, [])
    task.ledger = {"previous_runs": [{"ledger": {"allocations": [
        {"operation_key": key, "dispatch_state": "returned_invalid"} for _ in range(2)]}}]}
    with pytest.raises(TaskError, match="attempt limit"):
        admit_operation(task, "revise", {**payload, "token_limit": 500000}, [])
    task.ledger["previous_runs"][0]["ledger"]["allocations"] = [
        {"operation_key": key, "dispatch_state": "sent"}]
    with pytest.raises(TaskError, match="unresolved"):
        admit_operation(task, "revise", payload, [])


def test_error_diagnostic_does_not_retain_secret_provider_message():
    from workbench.providers.codex_diagnostics import normalize_runtime_error

    result = normalize_runtime_error({"message": "Invalid schema; Bearer secret-credential here",
        "codexErrorInfo": "other", "requestId": "req_test123"}, source="error_notification", will_retry=False)
    assert result["diagnostic"] == "output_schema" and result["request_id"] == "req_test123"
    assert "secret" not in str(result) and "Bearer" not in str(result)
    bad = copy.deepcopy(result)
    bad["request_id"] = "private-secret"
    from workbench.providers.codex_diagnostics import RuntimeErrorInfo
    with pytest.raises(ValueError):
        RuntimeErrorInfo.model_validate(bad)


def test_factored_manifest_projection_is_lossless_and_does_not_mutate_packet():
    inventory = [{"path": "/task_specification", "sha256": "a" * 64, "kind": "task_specification"}]
    packet = {"earlier_packet_manifests": [{"role": role, "packet_sha256": role,
                                          "evidence_artifacts": inventory} for role in ("proof", "source")]}
    original = copy.deepcopy(packet)
    projected = worker_module.prompt_projection("audit", {"packet": packet})["packet"]
    assert packet == original and len(projected["historical_evidence_sets"]) == 1
    expanded = [{k: v for k, v in r.items() if k != "evidence_set_sha256"}
                | {"evidence_artifacts": projected["historical_evidence_sets"][r["evidence_set_sha256"]]}
                for r in projected["earlier_packet_manifests"]]
    assert expanded == original["earlier_packet_manifests"]


def test_impossible_inventory_fails_before_account_or_turn_dispatch():
    client = ControlledCodexClient()
    worker = prepared_worker(client)
    with pytest.raises(ValueError, match="capacity"):
        worker.run("author", "draft", {"token_limit": 10000, "time_limit_seconds": 20,
                                       "expected_response_ids": [str(i) for i in range(257)]})
    assert client.calls == [] and worker.stage == "input_check"


@pytest.mark.parametrize("minimum,selected", [(7000, True), (9000, False)])
def test_section_plan_respects_configured_bounds_and_non_r4_identifiers(minimum, selected):
    from test_section_recovery import retained

    from workbench.services.manuscript_quality_runner import _author_payload

    raw = retained()
    raw["sections"][-1]["id"] = "discussion"
    previous = copy.deepcopy(raw)
    previous["sections"][-1]["id"] = "bibliography"
    previous["sections"].insert(-1, {"id": "discussion", "heading": "Synthesis", "text": "Old discussion",
                                      "claim_ids": ["C1"]})
    campaign = SimpleNamespace(body={"drafts": [{"candidate": previous}], "rounds": [],
                                     "verification_receipts": [], "search_receipts": []})
    runner = SimpleNamespace(task=SimpleNamespace(sources=[], contract={
        "manuscript_length": {"min_words": minimum, "max_words": 10000}}),
        author_checkpoint="a" * 64,
        recoverable_author_return={"result": raw, "result_sha256": stable_hash(raw)},
        agents=[SimpleNamespace(role="parent", provenance={})], session=None)
    payload = _author_payload(runner, campaign, revision=True)
    assert bool(payload.get("section_recovery")) is selected
    if selected:
        spec = payload["section_recovery"]
        assert spec["discussion_id"] == "discussion" and spec["reference_id"] == "bibliography"
        schema = worker_module.output_schema("revise", payload)
        assert schema["properties"]["text"] == {"type": "string"}
