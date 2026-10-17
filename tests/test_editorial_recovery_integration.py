"""Closure on the current recovery controller; controlled peers, no live models."""

import io
import json
import zipfile

import pytest
from test_manuscript_quality import isolated, run  # noqa: F401

from workbench.providers import research_codex_worker
from workbench.services import manuscript_quality as quality
from workbench.services import research_results, research_tasks


@pytest.mark.parametrize("flag,expected", [
    (None, "ready_for_human_review"),
    ("closure_repair", "ready_for_human_review"),
    ("closure_confirmation_defect", "needs_revision"),
    ("closure_malformed", "invalid_report"),
])
def test_editorial_campaign_preserves_evidence_and_gates_readiness(
        session, project, monkeypatch, flag, expected):
    task = run(session, project, *([flag] if flag else []), editorial_closure=True,
               token_limit=500000, time_limit_seconds=1800)
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    records = campaign.body.get("closure_reports", [])
    assert records, task.ledger
    assert records[-1]["status"] == expected, (records, task.ledger)
    state = quality.assessment(session, campaign.body["manuscript_id"])
    assert state["agent_checks_complete"] == (expected == "ready_for_human_review"), state
    assert state["agent_review_grants_publication_approval"] is False
    assert len(campaign.body["closure_calls"]) == (1 if flag == "closure_malformed" else 2)
    payload = research_tasks.package(session, task, include_results_pdf=False)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert "evidence/manifest.json" in archive.namelist()
        assert "manuscript.md" in archive.namelist()
        retained = json.loads(archive.read("editorial/closure-reports.json"))
        assert retained == records
        if expected == "ready_for_human_review":
            coverage = json.loads(archive.read("evidence/literature-coverage.json"))
            assert coverage["current_literature_report_available"]
    snapshot = research_results.snapshot_from_package(payload)
    assert snapshot["readiness"]["human_publication_approval"] is False
    if flag is None:
        from workbench.models import ResearchAgent

        reviewer = session.get(ResearchAgent, records[-1]["agent_id"])
        provenance = reviewer.provenance
        reviewer.provenance = {**reviewer.provenance, "requested_model_policy": {
            "role": "editorial_closure", "model": "changed-after-review", "reasoning_effort": "high"}}
        session.commit()
        assert not quality.assessment(session, campaign.body["manuscript_id"])["agent_checks_complete"]
        reviewer.provenance = provenance
        session.commit()
        from workbench import storage
        from workbench.services import manuscript_evidence_package

        def unavailable(*args, **kwargs):
            raise storage.ArtifactStorageError("synthetic missing artifact")

        monkeypatch.setattr(manuscript_evidence_package, "files_for", unavailable)
        state = quality.assessment(session, campaign.body["manuscript_id"])
        assert state["closure"]["status"] == "stale_report"
        assert not state["agent_checks_complete"]


@pytest.mark.parametrize("stop_phase", ["audit", "integrate"])
def test_editorial_resume_reuses_durable_reviews_and_usage(session, project, monkeypatch, stop_phase):
    from copy import deepcopy

    from test_manuscript_continuation import continue_and_wait, grant_for

    from workbench.services import research_runner

    original = research_runner.Runner.send

    def stop(self, handle, agent, phase, allowance, payload):
        if phase == stop_phase:
            raise research_runner.StopResearch("interrupted_partial", "controlled interruption")
        return original(self, handle, agent, phase, allowance, payload)

    monkeypatch.setattr(research_runner.Runner, "send", stop)
    task = run(session, project, editorial_closure=True, token_limit=500000, time_limit_seconds=1800)
    assert task.state == "interrupted_partial", task.ledger
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    records = deepcopy(campaign.body["closure_reports"])
    ledger = deepcopy(task.ledger)
    monkeypatch.setattr(research_runner.Runner, "send", original)
    continue_and_wait(session, task, grant_for(session, task, token_limit=500000,
                                             time_limit_seconds=1800, max_revision_cycles=0))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert task.ledger["previous_runs"][-1]["ledger"] == ledger
    session.refresh(campaign)
    assert campaign.body["closure_reports"][:len(records)] == records
    assert len(campaign.body["closure_calls"]) == 2
    assert not any(a["phase"] in {"draft", "revise"} for a in task.ledger["allocations"])
    if stop_phase == "integrate":
        assert not any(a["phase"] == "closure" for a in task.ledger["allocations"])
    assert quality.assessment(session, campaign.body["manuscript_id"])["agent_checks_complete"]


def test_closure_prompt_and_schema_keep_long_manuscript_inventory():
    from test_manuscript_closure import fixture

    from workbench.models import stable_hash
    from workbench.services import manuscript_closure as closure

    task, campaign, candidate = fixture()
    packet = closure.packet_for(task, campaign, stable_hash(candidate), "reviewer", "preflight")
    before = stable_hash(packet)
    schema = research_codex_worker.output_schema("closure", {"packet": packet})
    assert schema["properties"]["reviewed_sections"]["items"]["enum"] == ["s1"]
    prompt = research_codex_worker.json_prompt("closure", {"packet": packet})
    assert "independent editorial closure reviewer" in prompt
    assert prompt.count("Finite identity.") == 1
    assert stable_hash(packet) == before


def test_legacy_author_packet_hash_is_unchanged_without_editorial_findings():
    from workbench.models import stable_hash

    message = {key: None for key in (
        "contract", "sources", "verification_receipts", "search_receipts", "prior_comments",
        "expected_response_ids", "previous_candidate", "previous_candidate_sha256")}
    assert research_codex_worker.author_packet_hash(message) == stable_hash(message)
    assert research_codex_worker.author_packet_hash(
        {**message, "editorial_findings": []}) == stable_hash(message)
    assert research_codex_worker.author_packet_hash(
        {**message, "editorial_findings": ["required"]}) != stable_hash(message)


def test_local_revision_preserves_editorial_history_and_never_calls_author(session, project):
    from copy import deepcopy

    from test_local_candidate_admission import grant_for, proposal
    from test_manuscript_continuation import continue_and_wait

    from workbench.services.manuscript_local_revision import admit

    task = run(session, project, "closure_confirmation_defect", editorial_closure=True,
               token_limit=500000, time_limit_seconds=1800)
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    original = deepcopy(campaign.body["closure_reports"])
    assert len(original) == 2
    admit(session, task, proposal(session, task), actor="controlled-test")
    assert campaign.body["closure_history"][-1]["reports"] == original
    assert campaign.body["closure_reports"] == []
    continue_and_wait(session, task, grant_for(session, task, token_limit=500000,
        time_limit_seconds=1800, max_revision_cycles=0))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert {a["phase"] for a in task.ledger["allocations"]} == {"audit", "closure"}
    assert campaign.body["closure_history"][-1]["reports"] == original
    assert quality.assessment(session, campaign.body["manuscript_id"])["agent_checks_complete"]


def test_editorial_authorization_is_opt_in_and_old_envelopes_are_not_expanded():
    from types import SimpleNamespace

    from workbench.services.research_recovery import (
        AuthorizationGrant,
        continuation_authorization,
        initial_authorization,
    )

    task = SimpleNamespace(contract={"token_limit": 2000, "time_limit_seconds": 60}, ledger={})
    legacy = initial_authorization(task)
    assert "closure" not in legacy["allowed_operations"]
    task.contract["quality_policy"] = "manuscript-quality-v3-editorial"
    assert "closure" in initial_authorization(task)["allowed_operations"]
    task.ledger["authorization"] = legacy
    grant = SimpleNamespace(authorization=None, token_limit=2000, time_limit_seconds=60)
    assert continuation_authorization(task, grant) == legacy
    grant.authorization = AuthorizationGrant(token_ceiling=2000, time_ceiling_seconds=60,
                                              reason="Explicit new test grant")
    assert "closure" in continuation_authorization(task, grant)["allowed_operations"]
