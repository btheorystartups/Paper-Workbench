"""Synthetic stores and controlled processes; no manuscript agents or external services."""

import copy
import io
import json
import sys
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from workbench import config
from workbench.models import ComputeRun, ResearchObject, ResearchTask, Source, stable_hash, utcnow
from workbench.providers.research_executor import ProcessResearchExecutor
from workbench.providers.research_quality_offline import reply
from workbench.research_contract import ManuscriptDraft, TaskBrief
from workbench.services import (
    audits,
    authoring,
    evidence_basis,
    manuscript_acquisition,
    manuscript_path,
    manuscript_readiness,
    manuscript_verification,
    research_runner,
    research_tasks,
    revision_review,
)
from workbench.services import manuscript_quality as quality
from workbench.services.manuscript_quality_runner import (
    _cycle_timing,
    _initial_capacity_plan,
    _integration_payload,
    _prior,
    _revision_budget,
)

WORKER = Path(__file__).parent / "fixtures" / "manuscript_protocol_worker.py"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("WB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WB_DEPLOYMENT_MODE", "local")
    monkeypatch.setenv("WB_RESEARCH_EXECUTOR_ENABLED", "true")
    monkeypatch.setenv("WB_RESEARCH_EXECUTOR_COMMAND", json.dumps([sys.executable, str(WORKER)]))
    config.get_settings.cache_clear()
    yield
    research_runner.shutdown()


def task_for(session, project, **options):
    task = research_tasks.create_task(
        session,
        project.id,
        TaskBrief(
            question="Controlled manuscript coverage test",
            task_type="manuscript",
            token_limit=options.pop("token_limit", 96000),
            executor=options.pop("executor", "process"),
            **options,
        ),
    )
    research_tasks.attach(
        session,
        task,
        "source.txt",
        b"A partition is a set of disjoint nonempty blocks.",
        version="fixture-v1",
    )
    session.commit()
    return task


@pytest.mark.parametrize("best_effort", [False, True])
def test_manuscript_contract_and_planner_report_the_same_handoff_reserve(session, project, best_effort):
    task = task_for(session, project, token_limit=240000, allow_best_effort_tokens=best_effort)
    runner = SimpleNamespace(task=task, allocations=[], agents=[], remaining_tokens=lambda: 240000)
    assert task.contract["handoff_token_reserve"] == _revision_budget(runner)["handoff_reserve"] == 10000
    general = TaskBrief(question="General research", token_limit=240000,
                        allow_best_effort_tokens=best_effort).normalized()
    assert general["handoff_token_reserve"] == (60000 if best_effort else 48000)


def run(session, project, *flags, **options):
    task = task_for(session, project, **options)
    task.state, task.started_at = "planning", utcnow()
    session.commit()
    research_runner.run_task(
        task.id,
        threading.Event(),
        executor_factory=lambda mode: ProcessResearchExecutor(mode, [sys.executable, str(WORKER), *flags]),
    )
    session.expire_all()
    return session.get(ResearchTask, task.id)


def candidate_packet(session, project, role="source_citation"):
    task = task_for(session, project)
    manuscript, campaign = quality.create_campaign(session, task)
    draft = reply("draft", {})
    sid = task.sources[0]["source_id"]
    draft["claims"][0]["source_ids"] = [sid]
    _, digest = quality.apply_draft(session, task, manuscript, campaign, draft, "author")
    packet = quality.packet_for(task, campaign, digest, role, [])
    report = reply("audit", {"packet": packet})
    report["assessments"][0]["passages"] = [
        {"source_id": sid, "locator": "line 1", "quotation": "disjoint nonempty blocks"}
    ]
    return task, manuscript, campaign, packet, report


def reseal(packet, report):
    packet["packet_sha256"] = stable_hash({k: v for k, v in packet.items() if k != "packet_sha256"})
    report["packet_sha256"] = packet["packet_sha256"]


@pytest.mark.parametrize("defect,code", [
    ("missing", "adversarial_coverage"), ("duplicate", "adversarial_coverage"),
    ("unknown_claim", "adversarial_claim"), ("unlinked", "adversarial_objection"),
    ("advisory", "adversarial_objection"),
])
def test_adversarial_challenges_require_full_coverage_and_bound_objections(session, project, defect, code):
    _, _, _, packet, report = candidate_packet(session, project, "adversarial")
    if defect == "missing":
        report["adversarial_checks"].pop()
    elif defect == "duplicate":
        report["adversarial_checks"][-1] = copy.deepcopy(report["adversarial_checks"][0])
    elif defect == "unknown_claim":
        report["adversarial_checks"][0]["claim_ids"] = ["unknown"]
    else:
        report["adversarial_checks"][0].update(outcome="unresolved", objection_id="test")
        if defect == "advisory":
            report["objections"] = [{"id": "test", "severity": "advisory", "claim_ids": ["scope"],
                "objection": "Unanswered challenge", "acceptance_criterion": "Show boundary case"}]
    with pytest.raises(quality.ReportValidationError) as exc:
        quality.validate_report(report, packet)
    assert code in {i["code"] for i in exc.value.issues}


def test_adversarial_pass_requires_cited_passages_and_unresolved_challenge_blocks(session, project):
    _, _, _, packet, report = candidate_packet(session, project, "adversarial")
    assert not quality.validate_report(report, packet)[1]
    report["assessments"][0]["passages"] = []
    assert any("missing passage support" in b for b in quality.validate_report(report, packet)[1])
    report["adversarial_checks"][0].update(outcome="unresolved", objection_id="test")
    report["objections"] = [{"id": "test", "severity": "blocking", "claim_ids": ["scope"],
        "objection": "Unanswered boundary challenge", "acceptance_criterion": "Show boundary case"}]
    assert any("adversarial proof_stress" in b for b in quality.validate_report(report, packet)[1])


def test_adversarial_binding_diagnostic_names_exact_uncovered_claims(session, project):
    _, _, _, packet, report = candidate_packet(session, project, "adversarial")
    check = report["adversarial_checks"][1]
    check.update(outcome="unresolved", objection_id="O1")
    report["objections"] = [{"id": "O1", "severity": "blocking", "claim_ids": [],
        "objection": "Correct attribution", "acceptance_criterion": "Narrow the cited attribution"}]
    with pytest.raises(quality.ReportValidationError) as exc:
        quality.validate_report(report, packet)
    issue = next(i for i in exc.value.issues if i["code"] == "adversarial_objection")
    assert issue["path"] == "/adversarial_checks/1/claim_ids"
    assert "source_entailment binds O1" in issue["message"]
    assert "does not cover scope" in issue["message"]
    report["objections"][0]["claim_ids"] = ["scope"]
    assert quality.validate_report(report, packet)[1]  # Valid report still carries scientific blockers.


@pytest.mark.parametrize("role", ["source_citation", "adversarial"])
@pytest.mark.parametrize("status", ["unresolved", "contradicted"])
def test_negative_assessment_can_cite_frozen_counterevidence_without_promoting_support(session, project, role, status):
    _, _, _, packet, report = candidate_packet(session, project, role)
    original_ids = copy.deepcopy(packet["candidate"]["claims"][0]["source_ids"])
    other = "counter_source"
    packet["source_manifest"].append({**packet["source_manifest"][0], "source_id": other})
    packet["admitted_original_evidence"][other] = next(iter(packet["admitted_original_evidence"].values()))
    packet["evidence_artifacts"] = quality.evidence_inventory(packet)
    reseal(packet, report)
    item = report["assessments"][0]
    item.update(status=status, rationale="The frozen alternate source reveals an attribution mismatch.")
    item["passages"].append({"source_id": other, "locator": "line 1", "quotation": "disjoint nonempty blocks"})
    assert quality.validate_report(report, packet)[1]
    assert packet["candidate"]["claims"][0]["source_ids"] == original_ids
    item["status"] = "supported_within_scope"
    with pytest.raises(quality.ReportValidationError, match="outside this claim"):
        quality.validate_report(report, packet)
    item["status"] = status
    item["passages"][-1]["quotation"] = "A fabricated counterexample passage."
    with pytest.raises(quality.ReportValidationError, match="absent from the frozen source"):
        quality.validate_report(report, packet)
    item["passages"][-1]["source_id"] = "unfrozen_source"
    with pytest.raises(quality.ReportValidationError, match="outside this claim"):
        quality.validate_report(report, packet)


def test_adversarial_only_objection_requires_revision_and_fresh_independent_verification(session, project):
    task = run(session, project, "adversarial_revision", "author_response_contract")
    assert task.state == "completed", task.ledger.get("stop_reason")
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert len(campaign.body["drafts"]) == 2 and len(campaign.body["reports"]) == 8
    assert campaign.body["author_time_plans"][-1]["status"] == "admitted"
    review = session.get(ResearchObject, campaign.body["rounds"][0])
    assert {c["specialist_role"] for c in review.body["comments"]} == {"adversarial"}
    assert set(revision_review.dispositions(session, review).values()) == {"resolved"}
    agents = research_tasks.agents_for(session, task.id)
    assert len({a.provenance["specialist_report_model"]["codex_thread_id"]
                for a in agents if a.role == "child"}) == 8
    readiness = manuscript_readiness.report(session, task.contract["quality_manuscript_id"])
    assert readiness["status"] == "agent_checks_complete_human_review_pending"
    assert not readiness["release_eligible"] and not readiness["human_publication_approval"]
    assert {r["status"] for r in readiness["review_dimensions"]} == {"passed_within_scope"}


def test_readiness_does_not_promote_human_fields_and_cannot_green_missing_or_stale_review(session, project):
    task = run(session, project)
    mid = task.contract["quality_manuscript_id"]
    manuscript = session.get(ResearchObject, mid)
    source = session.get(Source, task.sources[0]["source_id"])
    before = (source.human_verified, manuscript.accepted_by_user, copy.deepcopy(manuscript.body))
    ready = manuscript_readiness.report(session, mid)
    assert ready["diagnostic_handoff_complete"] and not ready["release_eligible"]
    assert ready["human_review"]["pending_text_ids"]
    assert ready["human_review"]["pending_claim_ids"]
    assert before == (source.human_verified, manuscript.accepted_by_user, manuscript.body)
    assert research_tasks.snapshot(session, task)["readiness"] == ready
    assert quality.campaign_export(session, task)["readiness"] == ready
    campaign = quality.campaign_for(session, mid)
    original_reports = copy.deepcopy(campaign.body["reports"])
    quality.update_campaign(campaign, reports=[r for r in campaign.body["reports"] if r["role"] != "adversarial"])
    missing = manuscript_readiness.report(session, mid)
    assert not missing["agent_checks_complete"]
    assert next(r for r in missing["review_dimensions"] if r["role"] == "adversarial")["status"] == "missing"
    assert "passed_within_scope" not in {r["status"] for r in missing["review_dimensions"]}
    quality.update_campaign(campaign, reports=original_reports)
    section = authoring.manuscript_sections(session, mid)[0]
    authoring.update_section(session, section.id, text=section.body["text"] + " Changed after review.")
    stale = manuscript_readiness.report(session, mid)
    assert not stale["agent_checks_complete"] and not stale["release_eligible"]
    assert "passed_within_scope" not in {r["status"] for r in stale["review_dimensions"]}


def test_task_seed_provenance_is_available_and_hash_bound_without_becoming_a_source(session, project):
    task, _, campaign, packet, report = candidate_packet(session, project)
    seed = "Task-supplied false assertion: Equal block counts imply equal function spaces."
    task.contract = {**task.contract, "instructions": seed}
    current = quality.packet_for(task, campaign, packet["candidate_sha256"], "source_citation", [])
    assert current["task_specification"] == seed
    assert current["source_manifest"] == packet["source_manifest"]
    assert current["admitted_original_evidence"] == packet["admitted_original_evidence"]
    artifact = next(a for a in current["evidence_artifacts"] if a["path"] == "/task_specification")
    report["packet_sha256"] = current["packet_sha256"]
    report["evidence_assertions"] = [{"packet_scope": "current", "artifact_path": artifact["path"],
        "artifact_sha256": artifact["sha256"], "availability": "available"}]
    quality.validate_report(report, current)
    report["evidence_assertions"][0].update(availability="unavailable", artifact_sha256=None)
    with pytest.raises(quality.ReportValidationError, match="contradicted"):
        quality.validate_report(report, current)
    current["task_specification"] += " changed"
    with pytest.raises(ValueError, match="packet bytes changed"):
        quality.validate_report(report, current)


def test_prior_review_keeps_original_candidate_separate_from_response(session, project):
    task, manuscript, campaign, packet, _ = candidate_packet(session, project)
    comment = {"id": "original", "specialist_role": "proof_method",
               "objection": "Clarify the scope", "acceptance_criterion": "State the scope"}
    review = revision_review.open_round(session, manuscript.id, comments=[comment], reviewer="proof")
    quality.update_campaign(campaign, rounds=[review.id])
    original_hash = review.body["candidate_hash"]
    draft = copy.deepcopy(campaign.body["drafts"][-1]["candidate"])
    draft["sections"][0]["text"] += " This result is limited to the stated finite scope."
    _, revised_hash = quality.apply_draft(session, task, manuscript, campaign, draft, "author")
    revision_review.respond(session, review.id, comment_id="original", author="author",
                            response="Clarified scope", changes="Added finite scope sentence")
    prior = _prior(session, campaign, "proof_method")
    assert original_hash == packet["candidate_sha256"] != revised_hash
    assert prior[0]["reviewed_candidate_sha256"] == original_hash
    assert prior[0]["response"]["candidate_hash"] == revised_hash
    assert _prior(session, campaign, "source_citation") == []
    current = quality.packet_for(task, campaign, revised_hash, "proof_method", prior)
    assert current["candidate_sha256"] == revised_hash
    assert current["prior_comments"][0]["reviewed_candidate_sha256"] == original_hash
    assert revision_review.dispositions(session, review) == {"original": "open"}
    assert review.body["comments"] == [comment]


def test_structured_section_availability_and_historical_scope(session, project):
    _, _, _, packet, report = candidate_packet(session, project)
    assert "candidate_tex" not in packet
    sections = [a for a in packet["evidence_artifacts"] if a["kind"] == "candidate"]
    assert len(sections) == len(packet["candidate"]["sections"])
    artifact = sections[0]
    assertion = {"packet_scope": "current", "artifact_path": artifact["path"],
                 "availability": "available", "artifact_sha256": artifact["sha256"]}
    report["evidence_assertions"] = [assertion]
    assert not quality.validate_report(report, packet)[1]
    assertion.update(availability="unavailable", artifact_sha256=None)
    with pytest.raises(quality.ReportValidationError, match="contradicted"):
        quality.validate_report(report, packet)
    earlier_hash = packet["packet_sha256"]
    packet["earlier_packet_manifests"] = [{"role": "source_citation-0",
        "packet_sha256": earlier_hash, "evidence_artifacts": copy.deepcopy(packet["evidence_artifacts"])}]
    assertion.update(packet_scope=earlier_hash, availability="available", artifact_sha256=artifact["sha256"])
    report["historical_corrections"] = [{"source_role": "source_citation-0",
        "packet_sha256": earlier_hash, "artifact_path": artifact["path"],
        "corrected_availability": "available", "reason": "The earlier missing-section claim was incorrect."}]
    reseal(packet, report)
    assert not quality.validate_report(report, packet)[1]


def test_intake_freezes_bibliographic_metadata_and_candidate_links(session, project):
    from workbench.services.export_service import _collect

    task, manuscript, _, _, _ = candidate_packet(session, project)
    source = session.get(Source, task.sources[0]["source_id"])
    source.authors, source.year = "Example, Ada", 2026
    source.venue, source.doi, source.url = "Synthetic venue", "10.0000/fixture", "https://example.invalid/work"
    session.flush()
    frozen = research_tasks.create_task(session, project.id, TaskBrief(
        question="Freeze citation metadata", source_ids=[source.id])).sources[0]
    assert {k: frozen[k] for k in ("authors", "year", "venue", "doi", "url")} == {
        "authors": source.authors, "year": 2026, "venue": source.venue,
        "doi": source.doi, "url": source.url}
    assert _collect(session, manuscript.id)[3][source.id].authors == "Example, Ada"
    source.authors = "Changed after freezing"
    assert frozen["authors"] == "Example, Ada"


def test_report_validation_collects_all_independent_defects(session, project):
    _, _, _, packet, report = candidate_packet(session, project)
    report["covered_section_ids"] = []
    report["assessments"][0]["passages"][0]["quotation"] = "disjoint ... blocks"
    report["assessments"][0]["verification_ids"] = ["invented"]
    artifact = packet["evidence_artifacts"][0]
    report["evidence_assertions"] = [{"packet_scope": "current", "artifact_path": artifact["path"],
        "availability": "unavailable", "artifact_sha256": None}]
    with pytest.raises(quality.ReportValidationError) as captured:
        quality.validate_report(report, packet)
    assert {i["code"] for i in captured.value.issues} == {
        "coverage", "quotation", "verification_receipt", "evidence_availability"}
    assert all(i["path"].startswith("/") for i in captured.value.issues)


@pytest.mark.parametrize("stuck", [False, True])
def test_report_corrections_wait_for_whole_wave_and_are_bounded(session, project, stuck):
    task = run(session, project, "report_repair_stuck" if stuck else "report_repair")
    assert task.state == ("failed_partial" if stuck else "completed"), task.ledger.get("stop_reason")
    agents = research_tasks.agents_for(session, task.id)
    children = [a for a in agents if a.role == "child"]
    assert len(children) == (3 if stuck else 4)
    proof = next(a for a in children if a.assignment["specialist_role"] == "proof_method")
    assert len(proof.provenance["report_attempts"]) == 2
    assert len({r["span_id"] for r in proof.provenance["report_attempts"]}) == 2
    assert len({r["packet_sha256"] for r in proof.provenance["report_attempts"]}) == 1
    assert all(len(a.provenance["report_attempts"]) == 1 for a in children if a.id != proof.id)
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert len(campaign.body["reports"]) == (2 if stuck else 4)
    assert len(campaign.body["rejected_reports"]) == (2 if stuck else 1)
    assert {i["code"] for i in campaign.body["rejected_reports"][0]["issues"]} == {
        "coverage", "verification_receipt"}
    state = quality.assessment(session, task.contract["quality_manuscript_id"])
    assert state["agent_checks_complete"] is not stuck
    events = task.ledger["call_trace"]
    audits = [e for e in events if e["event"] == "dispatch" and e["operation"] == "audit"]
    assert len(audits) == (4 if stuck else 5)
    initial_returns = [e["sequence"] for e in events
        if e["event"] == "return" and e["span_id"] in {a["span_id"] for a in audits[:3]}]
    assert len(initial_returns) == 3 and max(initial_returns) < audits[3]["sequence"]
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"]
    assert len([e for e in events if e["event"] == "worker_closed"]) == (4 if stuck else 5)


def test_report_corrections_cannot_reset_or_exceed_task_budget(session, project):
    task = run(session, project, "report_repair_budget")
    assert task.state == "limit_reached_partial"
    assert "report corrections exceed remaining allowance" in task.ledger["stop_reason"]
    calls = task.ledger["trace_summary"]["calls"]
    assert len([c for c in calls if c["operation"] == "audit"]) == 3
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"] == 96000
    assert len(research_tasks.agents_for(session, task.id)) == 4


@pytest.mark.parametrize("has_previous", [False, True])
def test_draft_evidence_errors_are_collected_before_graph_mutation(session, project, has_previous):
    task = task_for(session, project)
    manuscript, campaign = quality.create_campaign(session, task)
    if has_previous:
        quality.apply_draft(session, task, manuscript, campaign, reply("draft", {}), "author")
    original = copy.deepcopy(manuscript.body)
    original_drafts = copy.deepcopy(campaign.body["drafts"])
    raw = reply("draft", {})
    raw["claims"][0].update(source_ids=["unfrozen-source"], verification_ids=["search-1"])
    with pytest.raises(quality.DraftValidationError) as captured:
        quality.apply_draft(session, task, manuscript, campaign, raw, "author",
                            expected_response_ids={"required-comment"})
    assert {issue["path"] for issue in captured.value.issues} == {
        "/responses", "/claims/0/source_ids", "/claims/0/verification_ids"}
    response_issue = next(i for i in captured.value.issues if i["code"] == "responses")
    assert response_issue["expected_response_ids"] == response_issue["missing_response_ids"] == ["required-comment"]
    assert response_issue["unexpected_response_ids"] == []
    assert manuscript.body == original and campaign.body["drafts"] == original_drafts
    assert not session.new


@pytest.mark.parametrize("stuck", [False, True])
def test_author_correction_uses_same_worker_and_preserves_rejected_draft(session, project, stuck):
    task = run(session, project, "draft_repair_stuck" if stuck else "draft_repair")
    assert task.state == ("failed_partial" if stuck else "completed"), task.ledger.get("stop_reason")
    agents = research_tasks.agents_for(session, task.id)
    parent = next(a for a in agents if a.role == "parent")
    attempts = parent.provenance["draft_attempts"]
    assert len(attempts) == 2 and len({a["span_id"] for a in attempts}) == 2
    assert attempts[0]["draft"]["claims"][0]["verification_ids"] == ["search-1"]
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert len(campaign.body["rejected_drafts"]) == (2 if stuck else 1)
    assert len(campaign.body["drafts"]) == (0 if stuck else 1)
    assert len(campaign.body["reports"]) == (0 if stuck else 4)
    assert {issue["path"] for issue in campaign.body["rejected_drafts"][0]["issues"]} == {
        "/claims/0/source_ids", "/claims/0/verification_ids"}
    calls = task.ledger["trace_summary"]["calls"]
    assert [c["operation"] for c in calls[:2]] == ["draft", "draft"]
    assert all(c["agent_id"] == parent.id for c in calls[:2])
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"]
    assert quality.assessment(session, task.contract["quality_manuscript_id"])[
        "agent_checks_complete"] is not stuck


def test_author_correction_cannot_borrow_review_reservation(session, project):
    task = run(session, project, "draft_repair_budget")
    assert task.state == "limit_reached_partial"
    assert task.ledger["stop_reason"] == "draft correction exceeds author allowance"
    assert task.ledger["charged_tokens"] == task.ledger["allocations"][0]["reserved"] - 1
    assert len(task.ledger["allocations"]) == 1
    assert len(research_tasks.agents_for(session, task.id)) == 1
    assert not quality.assessment(session, task.contract["quality_manuscript_id"])[
        "agent_checks_complete"]


@pytest.mark.parametrize("flags,operation", [(('draft_repair',), "draft"),
                                           (('revise', 'revise_repair'), "revise")])
def test_author_correction_payload_preserves_original_and_frozen_packet(session, project, monkeypatch, flags, operation):
    sent = []
    original_send = research_runner.Runner.send

    def capture(self, handle, agent, phase, allowance, payload):
        sent.append((phase, copy.deepcopy(payload)))
        return original_send(self, handle, agent, phase, allowance, payload)

    monkeypatch.setattr(research_runner.Runner, "send", capture)
    task = run(session, project, *flags)
    assert task.state == "completed", task.ledger.get("stop_reason")
    parent = next(a for a in research_tasks.agents_for(session, task.id) if a.role == "parent")
    attempts = [row for row in parent.provenance["draft_attempts"] if row["operation"] == operation]
    payloads = [payload for phase, payload in sent if phase == operation]
    assert len(attempts) == len(payloads) == 2
    assert payloads[1]["original_draft"] == attempts[0]["draft"]
    assert payloads[1]["original_draft_sha256"] == attempts[0]["draft_sha256"]
    assert all(payloads[1][key] == value for key, value in payloads[0].items())
    assert payloads[1]["draft_corrections"]
    assert bool(payloads[1]["expected_response_ids"]) == (operation == "revise")
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"]


def test_fresh_author_correction_missing_usage_keeps_full_shared_reservation(session, project, monkeypatch):
    original_usage = research_runner.Runner.usage

    def omit_correction_usage(self, allocation, event):
        if allocation.get("operation_kind") == "draft_correction":
            event.pop("usage", None)
        return original_usage(self, allocation, event)

    monkeypatch.setattr(research_runner.Runner, "usage", omit_correction_usage)
    task = run(session, project, "draft_repair")
    correction = task.ledger["allocations"][1]
    assert correction["operation_kind"] == "draft_correction"
    assert correction["actual_tokens"] is None and not correction.get("final_actual")
    assert research_runner.allocation_charge(correction) == correction["reserved"]
    assert task.ledger["charged_tokens"] == sum(research_runner.allocation_charge(a) for a in task.ledger["allocations"])
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"]
    parent = next(a for a in research_tasks.agents_for(session, task.id) if a.role == "parent")
    assert len(parent.provenance["draft_attempts"]) == 2


@pytest.mark.parametrize("allow_revision", [False, True])
def test_scope_inventory_objection_survives_other_role_passes_and_requires_re_review(session, project, allow_revision):
    task = run(session, project, "scope_inventory", max_revision_cycles=int(allow_revision))
    assert task.state == "completed", task.ledger.get("stop_reason")
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    state = quality.assessment(session, task.contract["quality_manuscript_id"])
    assert state["agent_checks_complete"] is allow_revision
    initial = campaign.body["reports"][:4]
    assert [r["role"] for r in initial if r["blockers"]] == ["source_citation"]
    review = session.get(ResearchObject, campaign.body["rounds"][0])
    assert len(review.body["comments"]) == 2
    assert set(revision_review.dispositions(session, review).values()) == ({"resolved"} if allow_revision else {"open"})
    if allow_revision:
        assert "arbitrary nonempty" in campaign.body["drafts"][-1]["candidate"]["claims"][0]["statement"]
        assert len(campaign.body["reports"]) == 8
    else:
        assert len(campaign.body["drafts"]) == 1
        assert not task.ledger.get("live_handoff_verified")
    assert not manuscript_readiness.report(session, task.contract["quality_manuscript_id"])["release_eligible"]


def test_historical_author_context_cannot_be_reused_as_independent_reviewer(session, project):
    task = run(session, project)
    agents = research_tasks.agents_for(session, task.id)
    parent = next(a for a in agents if a.role == "parent")
    reviewer = next(a for a in agents if a.assignment.get("specialist_role") == "source_citation")
    old_identity = reviewer.provenance["specialist_report_model"]["codex_thread_id"]
    parent.provenance = {**parent.provenance, "draft_attempts": [
        *parent.provenance["draft_attempts"], {"model_thread_id": old_identity}]}
    session.commit()
    state = quality.assessment(session, task.contract["quality_manuscript_id"])
    assert not state["agent_checks_complete"]
    assert "author cannot verify their own manuscript" in state["blockers"]


@pytest.mark.parametrize("repair", [False, True])
def test_review_dispatch_reuses_freed_slots_without_exceeding_three_workers(session, project, repair):
    flags = ["rolling_review", *(["report_repair"] if repair else [])]
    task = run(session, project, *flags)
    assert task.state == "completed", task.ledger.get("stop_reason")
    agents = research_tasks.agents_for(session, task.id)
    children = {a.id: a.assignment["specialist_role"] for a in agents if a.role == "child"}
    events = task.ledger["call_trace"]
    active, peak = set(), 0
    for event in events:
        if event["agent_id"] not in children:
            continue
        if event["event"] == "spawn_finished":
            active.add(event["agent_id"])
            peak = max(peak, len(active))
        elif event["event"] == "worker_closed":
            active.remove(event["agent_id"])
    assert peak == 3 and not active
    if not repair:
        adversarial = next(aid for aid, role in children.items() if role == "adversarial")
        launch = next(i for i, event in enumerate(events)
                      if event["event"] == "spawn_finished" and event["agent_id"] == adversarial)
        assert any(event["event"] == "worker_closed" for event in events[:launch]
                   if event["agent_id"] in children)
        assert any(event["event"] == "return" for event in events[launch:]
                   if children.get(event["agent_id"]) in {"source_citation", "literature_contribution"})
    planned = next(i for i, event in enumerate(events) if event["event"] == "initial_capacity_planned")
    first_review = next(i for i, event in enumerate(events)
                        if event["event"] == "spawn_started" and event["agent_id"] in children)
    assert planned < first_review


@pytest.mark.parametrize("cycles,expected", [(0, 110000), (2, 222000)])
def test_initial_capacity_is_conditional_records_history_growth_and_does_not_mutate_packet(session, project, cycles, expected):
    task, _, campaign, _, _ = candidate_packet(session, project)
    task.contract = {**task.contract, "max_revision_cycles": cycles, "token_limit": 240000}
    before = copy.deepcopy(campaign.body)
    runner = SimpleNamespace(task=task, session=session, agents=[], allocations=[], remaining_tokens=lambda: 190000)
    plan = _initial_capacity_plan(runner, campaign)
    assert campaign.body == before
    assert plan["required_remaining_tokens"] == expected
    assert plan["minimum_total_token_limit"] == 50000 + expected
    assert plan["shortfall_tokens"] == max(0, expected - 190000)
    assert plan["capacity_status"] == ("estimated_funded" if cycles == 0 else "capacity_risk")
    assert plan["forecast_revision_cycles"] == int(cycles > 0)
    assert plan["additional_cycles_not_forecast"] == max(0, cycles - 1)
    if cycles:
        assert plan["conditional_revision"]["input_token_estimate"] > 0
    assert "wall time" in plan["unknowns"]


def test_capacity_readiness_exposes_forecast_and_marks_changed_basis_stale(session, project):
    task = run(session, project, "revise", "budget_pause")
    assert task.state == "limit_reached_partial"
    state = manuscript_readiness.report(session, task.contract["quality_manuscript_id"])
    forecast = state["capacity"]["forecast"]
    assert state["capacity"]["stage"] == "revision_admission" and state["capacity"]["basis_current"]
    assert forecast["required_remaining_tokens"] == (
        forecast["review_reserve"] + forecast["repair_reserve"]
        + forecast["handoff_reserve"] + forecast["minimum_author_grant"])
    assert forecast["capacity_status"] == "insufficient_tokens" and forecast["shortfall_tokens"] > 0
    assert not state["release_eligible"]
    task.contract = {**task.contract, "token_limit": task.contract["token_limit"] + 1000}
    session.commit()
    assert not manuscript_readiness.report(session, task.contract["quality_manuscript_id"])["capacity"]["basis_current"]


def test_cycle_timing_uses_returned_calls_and_three_slots_without_inventing_unknown_time():
    calls = [("draft", "parent", 177.616), ("audit", "proof_method", 32.025),
             ("audit", "source_citation", 143.574), ("audit", "literature_contribution", 120.783),
             ("audit", "adversarial", 162.898)]
    events = []
    for i, (op, role, seconds) in enumerate(calls):
        events += [{"event": "dispatch", "span_id": str(i), "operation": op, "role": role,
                    "agent_id": str(i), "timestamp": "synthetic", "elapsed_seconds": 0},
                   {"event": "return", "span_id": str(i), "agent_id": str(i), "timestamp": "synthetic",
                    "elapsed_seconds": seconds, "actual_tokens": 100}]
    runner = SimpleNamespace(task=SimpleNamespace(ledger={"call_trace": events}), allocations=[])
    timing = _cycle_timing(runner)
    assert timing["review_wave_seconds"] == pytest.approx(194.923)
    assert timing["revision_and_review_seconds"] == pytest.approx(372.539)
    assert timing["required_remaining_seconds"] == pytest.approx((372.539 + 177.616 + 162.898) * 1.25 + 5)
    assert timing["author_repair_basis"] == "ordinary_author_fallback"
    assert timing["report_repair_basis"] == "largest_reviewer_fallback"
    assert timing["remaining_research_seconds"] is None
    runner.task.ledger = {}
    assert _cycle_timing(runner)["status"] == "unestimated"


def test_cycle_timing_includes_observed_repairs_and_startup_but_not_unfinished_calls(monkeypatch):
    calls = [("draft", "parent", 163.519738, None), ("draft", "parent", 175.603246, "draft_correction"),
             ("audit", "proof_method", 170.526204, None), ("audit", "source_citation", 40.645673, None),
             ("audit", "literature_contribution", 151.344108, None), ("audit", "adversarial", 199.667078, None),
             ("audit", "source_citation", 70, "report_correction")]
    events, allocations = [], []
    for i, (op, role, seconds, kind) in enumerate(calls):
        events += [{"event": "dispatch", "span_id": str(i), "operation": op, "role": role,
                    "agent_id": str(i), "timestamp": "synthetic", "elapsed_seconds": 0},
                   {"event": "return", "span_id": str(i), "agent_id": str(i), "timestamp": "synthetic",
                    "elapsed_seconds": seconds, "actual_tokens": 100}]
        allocations.append({"span_id": str(i), "operation_kind": kind})
    events += [{"event": "spawn_started", "span_id": "spawn", "elapsed_seconds": 0},
               {"event": "spawn_finished", "span_id": "spawn", "elapsed_seconds": 2},
               {"event": "dispatch", "span_id": "unfinished", "operation": "revise", "role": "parent",
                "agent_id": "parent", "timestamp": "synthetic", "elapsed_seconds": 0}]
    monkeypatch.setattr("workbench.services.manuscript_quality_runner.time.monotonic", lambda: 100)
    runner = SimpleNamespace(task=SimpleNamespace(ledger={"call_trace": events}), allocations=allocations,
                             research_deadline=360.399902)
    timing = _cycle_timing(runner)
    assert timing["revision_and_review_seconds"] == pytest.approx(403.832489)
    assert timing["author_repair_seconds"] == 175.603246
    assert timing["report_repair_pool_seconds"] == 70 and timing["startup_reserve_seconds"] == 10
    assert timing["required_remaining_seconds"] == pytest.approx(821.79466875)
    assert timing["shortfall_seconds"] > 500 and timing["status"] == "insufficient_time"


def test_time_shortfall_stops_revision_despite_funded_tokens_and_keeps_evidence(session, project, monkeypatch):
    from workbench.services import manuscript_quality_runner as controller

    original = controller._cycle_timing
    completed_forecasts = []

    def forecast(runner):
        timing = original(runner)
        if timing["revision_and_review_seconds"] is not None:
            completed_forecasts.append(timing)
            if len(completed_forecasts) >= 2:
                timing.update(remaining_research_seconds=0, status="insufficient_time")
        return timing

    monkeypatch.setattr(controller, "_cycle_timing", forecast)
    task = run(session, project, "adversarial_revision", token_limit=240000)
    assert task.state == "limit_reached_partial" and "insufficient research time" in task.ledger["stop_reason"]
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert len(campaign.body["drafts"]) == 1 and len(campaign.body["reports"]) == 4
    assert campaign.body["revision_budget_plans"][-1]["capacity_status"] == "funded"
    assert campaign.body["revision_budget_plans"][-1]["timing"]["status"] == "observed_duration_estimate"
    assert [c["operation"] for c in task.ledger["trace_summary"]["calls"]] == ["draft", *["audit"] * 4]
    assert campaign.body["author_time_plans"][-1]["status"] == "insufficient_time"
    review = session.get(ResearchObject, campaign.body["rounds"][0])
    assert set(revision_review.dispositions(session, review).values()) == {"open"}
    ready = manuscript_readiness.report(session, task.contract["quality_manuscript_id"])
    assert ready["capacity"]["stage"] == "author_time_admission" and ready["capacity"]["basis_current"]
    assert not ready["release_eligible"]
    task.contract = {**task.contract, "time_limit_seconds": task.contract["time_limit_seconds"] + 1}
    session.commit()
    assert not manuscript_readiness.report(session, task.contract["quality_manuscript_id"])["capacity"]["basis_current"]


def test_insufficient_revision_correction_time_preserves_accepted_candidate_and_unapplied_responses(session, project, monkeypatch):
    from workbench.services import manuscript_quality_runner as controller

    original = controller._cycle_timing

    def forecast(runner):
        timing = original(runner)
        if any(a["phase"] == "revise" and a.get("final_actual") for a in runner.allocations):
            timing.update(remaining_research_seconds=0, status="insufficient_time")
        return timing

    monkeypatch.setattr(controller, "_cycle_timing", forecast)
    task = run(session, project, "adversarial_revision", "revise_repair", token_limit=240000)
    assert task.state == "limit_reached_partial"
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert len(campaign.body["drafts"]) == 1 and len(campaign.body["reports"]) == 4
    assert len(campaign.body["rejected_drafts"]) == 1
    plan = campaign.body["author_time_plans"][-1]
    assert plan["correction"] and plan["status"] == "insufficient_time"
    assert plan["required_remaining_seconds"] > plan["timing"]["author_repair_seconds"]
    assert [c["operation"] for c in task.ledger["trace_summary"]["calls"]].count("revise") == 1
    review = session.get(ResearchObject, campaign.body["rounds"][0])
    assert not any(e["kind"] == "response" for e in review.body["events"])


def test_capacity_floor_accounts_for_author_slice_cap_separately(session, project, monkeypatch):
    from workbench.providers import research_codex_worker

    task, _, campaign, _, _ = candidate_packet(session, project)
    task.contract = {**task.contract, "token_limit": 240000}
    runner = SimpleNamespace(task=task, session=session, agents=[], allocations=[], remaining_tokens=lambda: 230000)
    monkeypatch.setattr(research_codex_worker, "json_prompt", lambda op, message: op)
    monkeypatch.setattr(research_codex_worker, "prompt_token_count", lambda text: 70000 if text == "revise" else 0)
    plan = _revision_budget(runner, campaign)
    assert plan["minimum_author_grant"] == 76000 and plan["author_grant"] == 60000
    assert plan["capacity_status"] == "author_slice_below_minimum"
    assert plan["shortfall_tokens"] == 0 and plan["author_slice_shortfall_tokens"] == 16000
    assert plan["minimum_total_token_limit"] == 304000


def test_revision_waits_for_specialist_review_budget(session, project):
    task = run(session, project, "revise", "budget_pause")
    assert task.state == "limit_reached_partial"
    assert "reserving 90000 for specialist re-review and 10000 for final handoff" in task.ledger["stop_reason"]
    assert task.ledger["charged_tokens"] == 85411
    assert [c["operation"] for c in task.ledger["trace_summary"]["calls"]] == [
        "draft", "audit", "audit", "audit", "audit"]
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert campaign.body["status"] == "needs_revision"
    assert len(campaign.body["drafts"]) == 1 and len(campaign.body["reports"]) == 4
    assert not quality.assessment(session, task.contract["quality_manuscript_id"])[
        "agent_checks_complete"]


@pytest.mark.parametrize("usage,remaining,expected_grant,admitted", [
    ([13570, 18028, 19331, 19002], 110069, 0, False),
    ([13613, 32731, 18759, 18655], 78074, 0, False),
])
def test_revision_budget_replays_observed_acceptance_usage(usage, remaining, expected_grant, admitted):
    roles = ["proof_method", "source_citation", "literature_contribution"]
    allocations = [{"agent_id": "author", "phase": "draft",
                    "actual_tokens": usage[0], "final_actual": True}]
    allocations += [{"agent_id": role, "phase": "audit", "actual_tokens": tokens,
                     "final_actual": True} for role, tokens in zip(roles, usage[1:], strict=True)]
    runner = SimpleNamespace(task=SimpleNamespace(contract={"token_limit": 180000}),
        allocations=allocations, agents=[SimpleNamespace(id=role, assignment={"specialist_role": role})
                                      for role in roles], remaining_tokens=lambda: remaining)
    plan = _revision_budget(runner)
    assert plan["author_grant"] == expected_grant
    assert (plan["author_grant"] >= plan["minimum_author_grant"]) is admitted
    if admitted:
        assert plan["author_grant"] + plan["review_reserve"] + plan["handoff_reserve"] <= remaining
    # An unfinished turn cannot lower the observed reserve or release capacity.
    runner.allocations.append({"agent_id": roles[0], "phase": "audit", "actual_tokens": 1,
                               "reserved": 45000, "final_actual": False})
    assert _revision_budget(runner) == plan


def test_revision_preserves_larger_role_grant_and_final_handoff(session, project):
    task = run(session, project, "revise", "unequal_review", token_limit=240000)
    assert task.state == "completed", task.ledger.get("stop_reason")
    agents = research_tasks.agents_for(session, task.id)
    revised_agents = {a.id: a.assignment["specialist_role"] for a in agents
                      if a.assignment.get("iteration") == 1}
    grants = {revised_agents[a["agent_id"]]: a["reserved"] for a in task.ledger["allocations"]
              if a["agent_id"] in revised_agents}
    assert grants["source_citation"] > grants["proof_method"] >= 22500
    assert grants["source_citation"] >= 27500
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    plan = campaign.body["revision_budget_plans"][0]
    assert plan["review_role_reserves"]["source_citation"] == 27500
    assert plan["handoff_reserve"] == 10000
    assert task.ledger["parent_integration_received"]
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"]


def test_deferred_review_reuses_final_receipt_capacity_without_borrowing_handoff(session, project):
    task = run(session, project, "revise", "observed_nine", token_limit=240000)
    assert task.state == "completed", task.ledger.get("stop_reason")
    agents = research_tasks.agents_for(session, task.id)
    second = {a.assignment["specialist_role"]: a.id for a in agents
              if a.assignment.get("iteration") == 1}
    allocations = {a["agent_id"]: a for a in task.ledger["allocations"] if a["phase"] == "audit"}
    assert allocations[second["adversarial"]]["reserved"] >= 24000
    assert allocations[second["literature_contribution"]]["reserved"] >= 24506
    events = task.ledger["call_trace"]
    launch = next(i for i, e in enumerate(events) if e["event"] == "spawn_finished"
                  and e["agent_id"] == second["adversarial"])
    assert any(e["event"] == "worker_closed" and e["agent_id"] in {
        second[role] for role in ("proof_method", "source_citation", "literature_contribution")}
        for e in events[:launch])
    assert task.ledger["actual_tokens"] == 171875
    assert task.ledger["parent_integration_received"]
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"]


@pytest.mark.parametrize("stuck", [False, True])
def test_deferred_review_waits_for_bounded_report_correction(session, project, stuck):
    task = run(session, project, "revise",
               "re_review_repair_stuck" if stuck else "re_review_report_repair")
    assert task.state == ("failed_partial" if stuck else "completed")
    agents = research_tasks.agents_for(session, task.id)
    second = {a.assignment["specialist_role"]: a for a in agents
              if a.assignment.get("iteration") == 1}
    proof = second["proof_method"]
    assert len(proof.provenance["report_attempts"]) == 2
    assert "literature_contribution" in second
    assert ("adversarial" in second) is not stuck
    if not stuck:
        events = task.ledger["call_trace"]
        launch = next(i for i, e in enumerate(events) if e["event"] == "spawn_finished"
                      and e["agent_id"] == second["adversarial"].id)
        assert any(e["event"] == "worker_closed" and e["agent_id"] == proof.id
                   for e in events[:launch])
        assert task.ledger["parent_integration_received"]
    else:
        assert not task.ledger.get("parent_integration_received")
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"]


def test_four_fresh_reviewers_revision_and_parent_handoff(session, project):
    task = run(session, project, "revise")
    assert task.state == "completed", task.ledger.get("stop_reason")
    state = quality.assessment(session, task.contract["quality_manuscript_id"])
    assert state["agent_checks_complete"], state["blockers"]
    assert task.synthesis["quality"]["blockers"] == state["blockers"]
    assert state["agent_review_grants_publication_approval"] is False
    assert not evidence_basis.collect(session, state["manuscript_id"])["problems"]
    agents = research_tasks.agents_for(session, task.id)
    assert len(agents) == 9
    campaign = quality.campaign_for(session, state["manuscript_id"])
    assert len(campaign.body["drafts"]) == 2 and len(campaign.body["reports"]) == 8
    assert len(campaign.body["rounds"]) == 1
    review = session.get(ResearchObject, campaign.body["rounds"][0])
    assert set(revision_review.dispositions(session, review).values()) == {"resolved"}
    assert task.synthesis["integration"] == "parent_agent_with_immutable_reviewed_candidate"
    calls = task.ledger["trace_summary"]["calls"]
    assert [c["operation"] for c in calls] == [
        "draft",
        "audit",
        "audit",
        "audit",
        "audit",
        "revise",
        "audit",
        "audit",
        "audit",
        "audit",
        "integrate",
    ]
    assert all(c["duration_seconds"] >= 0 and c["status"] == "return" for c in calls)
    assert all(e["call_stack"] for e in task.ledger["call_trace"])
    assert task.ledger["actual_tokens"] == 1100
    assert len(campaign.body["dispatches"]) == 8
    active, peak = set(), 0
    for event in task.ledger["call_trace"]:
        if event["event"] == "spawn_finished" and event["parent_agent_id"]:
            active.add(event["agent_id"])
            peak = max(peak, len(active))
        elif event["event"] == "worker_closed":
            active.discard(event["agent_id"])
    assert peak == 3 and not active
    with zipfile.ZipFile(io.BytesIO(research_tasks.package(session, task))) as archive:
        assert {"call-trace.json", "call-timing-summary.json", "manuscript-quality.json", "readiness-report.json"} <= set(
            archive.namelist()
        )


def test_compact_handoff_keeps_all_report_decisions_and_candidate_identity(session, project):
    task = run(session, project)
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    agents = research_tasks.agents_for(session, task.id)
    payload = _integration_payload(task, campaign, agents)
    assert set(payload["reports"]) == {r["agent_id"] for r in campaign.body["reports"]}
    assert payload["reviewed_candidate"]["candidate_sha256"] == campaign.body["drafts"][-1][
        "candidate_sha256"]
    assert set(payload["reviewed_candidate"]["claim_ids"]) == {
        c["id"] for c in campaign.body["drafts"][-1]["candidate"]["claims"]}
    for record in campaign.body["reports"]:
        report = next(a.report for a in agents if a.id == record["agent_id"])
        handed = payload["reports"][record["agent_id"]]
        assert handed["sha256"] == record["report_sha256"]
        assert handed["objections"] == report["objections"]
        assert handed["resolutions"] == report["resolutions"]
        assert handed["blockers"] == record["blockers"]
        assert {a["claim_id"]: a["status"] for a in handed["claim_assessments"]} == {
            a["claim_id"]: a["status"] for a in report["assessments"]}
    assert "sections" not in payload["reviewed_candidate"]


@pytest.mark.parametrize("unfinished", ["partial_state", "missing_parent_handoff"])
def test_completed_reviews_in_partial_task_remain_release_blocked(session, project, unfinished):
    task = run(session, project)
    mid = task.contract["quality_manuscript_id"]
    assert quality.assessment(session, mid)["agent_checks_complete"]
    if unfinished == "partial_state":
        task.state = "limit_reached_partial"
    else:
        task.ledger = {**task.ledger, "parent_integration_received": False}
    session.commit()
    state = quality.assessment(session, mid)
    assert state["agent_checks_complete"]
    assert "manuscript production task has not completed its final handoff" in state["blockers"]
    assert any(f["code"] == "manuscript-quality-incomplete" for f in audits.audit_manuscript(session, mid))
    path = manuscript_path.build_project_path(session, project.id, manuscript_id=mid)
    assert not path["publication_ready"]


@pytest.mark.parametrize("flag", ["fail", "coverage", "shared"])
def test_partial_failure_keeps_draft_and_closes_trace(session, project, flag):
    task = run(session, project, flag)
    assert task.state == "failed_partial", task.ledger.get("stop_reason")
    state = quality.assessment(session, task.contract["quality_manuscript_id"])
    assert state["draft_produced"] and not state["agent_checks_complete"]
    assert "OFFLINE manuscript" in task.synthesis["deliverables"]["paper"]
    assert all(c["status"] != "no_terminal_receipt" for c in task.ledger["trace_summary"]["calls"])


def test_offline_production_never_becomes_live_evidence(session, project):
    task = task_for(session, project, executor="offline")
    task.state, task.started_at = "planning", utcnow()
    session.commit()
    research_runner.run_task(task.id, threading.Event())
    session.expire_all()
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert (
        "simulated research cannot pass production review"
        in quality.assessment(session, task.contract["quality_manuscript_id"])["blockers"]
    )


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("quote", "quotation"),
        ("coverage", "coverage"),
        ("packet", "packet bytes"),
        ("hash", "another role"),
        ("check", "invented"),
        ("source", "outside this claim"),
    ],
)
def test_deterministic_rejections(session, project, mutation, expected):
    _, _, _, packet, report = candidate_packet(session, project)
    if mutation == "quote":
        report["assessments"][0]["passages"][0]["quotation"] = "Invented passage."
    elif mutation == "coverage":
        report["covered_section_ids"] = []
    elif mutation == "packet":
        packet["candidate"]["title"] = "Changed"
    elif mutation == "hash":
        report["candidate_sha256"] = "0" * 64
    elif mutation == "check":
        report["assessments"][0]["verification_ids"] = ["imaginary"]
    elif mutation == "source":
        report["assessments"][0]["passages"][0]["source_id"] = "other"
    with pytest.raises(ValueError, match=expected):
        quality.validate_report(report, packet)


@pytest.mark.parametrize("gap", ["truncated", "metadata", "novelty", "finite", "missing_passage", "na"])
def test_semantic_and_access_gaps_are_visible_blockers(session, project, gap):
    _, _, _, packet, report = candidate_packet(session, project)
    if gap == "truncated":
        packet["source_manifest"][0]["context_truncated"] = True
    elif gap == "metadata":
        packet["source_manifest"][0]["access"] = "metadata_only"
    elif gap == "novelty":
        packet["candidate"]["novelty_claim"] = True
    elif gap == "finite":
        packet["role"] = report["role"] = "proof_method"
        packet["candidate"]["claims"][0]["kind"] = "finite_check"
    elif gap == "missing_passage":
        report["assessments"][0]["passages"] = []
    elif gap == "na":
        report["assessments"][0]["status"] = "not_applicable"
    reseal(packet, report)
    assert quality.validate_report(report, packet)[1]


@pytest.fixture
def two_source_claim_packet(session, project):
    task = task_for(session, project)
    second_text = "Distinct blocks in a partition are disjoint, and each block is nonempty."
    research_tasks.attach(session, task, "second.txt", second_text.encode(), version="fixture-v2")
    session.commit()
    first, second = [s["source_id"] for s in task.sources]
    manuscript, campaign = quality.create_campaign(session, task)
    draft = reply("draft", {})
    draft["claims"] = [
        {"id": "partition", "kind": "background",
         "statement": "Partition blocks are disjoint and nonempty.",
         "source_ids": [first, second], "verification_ids": []},
        {"id": "nonempty", "kind": "background",
         "statement": "Every partition block is nonempty.",
         "source_ids": [second], "verification_ids": []},
    ]
    draft["sections"][0].update(
        heading="Definitions", text=draft["claims"][0]["statement"],
        claim_ids=["partition", "nonempty"],
    )
    _, digest = quality.apply_draft(session, task, manuscript, campaign, draft, "author")
    packet = quality.packet_for(task, campaign, digest, "source_citation", [])
    report = reply("audit", {"packet": packet})
    report["assessments"][0].update(
        rationale="Both sources support the claim, including source " + second,
        passages=[{"source_id": first, "locator": "line 1",
                   "quotation": "disjoint nonempty blocks"}],
    )
    report["assessments"][1]["passages"] = [
        {"source_id": second, "locator": "line 1", "quotation": second_text}]
    return packet, report, second


@pytest.mark.parametrize("duplicate_first_source", [False, True])
def test_passage_binding_is_per_claim_and_per_source(two_source_claim_packet, duplicate_first_source):
    packet, report, missing = two_source_claim_packet
    if duplicate_first_source:
        passages = report["assessments"][0]["passages"]
        passages.append(copy.deepcopy(passages[0]))
    original = copy.deepcopy((packet, report))
    accepted, blockers, _ = quality.validate_report(report, packet)
    assert accepted["assessments"][0]["status"] == "supported_within_scope"
    assert blockers == [f"missing passage support: partition (source_ids: {missing})"]
    # A prose assertion, a quote on another claim, and duplicate quotes do not close the gap.
    assert (packet, report) == original
    report["assessments"][0]["passages"].extend(
        copy.deepcopy(report["assessments"][1]["passages"]))
    assert not quality.validate_report(report, packet)[1]


def test_multi_source_support_checks_each_quotation_against_its_bound_source(two_source_claim_packet):
    packet, report, second = two_source_claim_packet
    quote = copy.deepcopy(report["assessments"][0]["passages"][0])
    quote["source_id"] = second
    report["assessments"][0]["passages"].append(quote)
    with pytest.raises(quality.ReportValidationError) as captured:
        quality.validate_report(report, packet)
    assert [(issue["code"], issue["path"]) for issue in captured.value.issues] == [
        ("quotation", "/assessments/0/passages/1/quotation")]


def test_explicit_partial_source_support_remains_an_accepted_blocker(two_source_claim_packet):
    packet, report, second = two_source_claim_packet
    report["assessments"][0].update(
        status="unresolved", rationale=f"Whole-claim support from {second} is not established.")
    report["objections"] = [{
        "id": "source-scope", "severity": "blocking", "claim_ids": ["partition"],
        "objection": f"Source {second} has no bound passage for this whole claim.",
        "acceptance_criterion": "Bind sufficient exact passages or narrow the claim's attribution.",
    }]
    accepted, blockers, _ = quality.validate_report(report, packet)
    assert accepted["objections"] == report["objections"]
    assert report["objections"][0]["objection"] in blockers
    assert any("not established" in b for b in blockers)


def test_candidate_contract_requires_explicit_complete_inventory():
    candidate = reply("draft", {})
    candidate["sections"][0]["claim_ids"] = []
    with pytest.raises(ValueError):
        ManuscriptDraft.model_validate(candidate)


def test_review_events_do_not_change_candidate_but_content_does(session, project):
    _, manuscript, _, _, _ = candidate_packet(session, project)
    before = revision_review.candidate_hash(session, manuscript.id)
    review = revision_review.open_round(
        session,
        manuscript.id,
        reviewer="independent",
        comments=[{"id": "c", "objection": "Clarify", "acceptance_criterion": "Add precise scope"}],
    )
    session.flush()
    revision_review.respond(
        session,
        review.id,
        comment_id="c",
        author="writer",
        response="Explained",
        changes="No scientific change",
    )
    assert revision_review.candidate_hash(session, manuscript.id) == before
    section = authoring.manuscript_sections(session, manuscript.id)[0]
    section.body = {**section.body, "text": "Different theorem."}
    assert revision_review.candidate_hash(session, manuscript.id) != before


@pytest.mark.parametrize("change", ["section", "source", "receipt", "identity", "campaign", "bibliography"])
def test_completed_checks_cannot_survive_changed_evidence(session, project, change):
    task = run(session, project)
    mid = task.contract["quality_manuscript_id"]
    assert quality.assessment(session, mid)["agent_checks_complete"]
    manuscript = session.get(ResearchObject, mid)
    campaign = quality.campaign_for(session, mid)
    if change in {"section", "bibliography"}:
        section = authoring.manuscript_sections(session, mid)[0]
        section.title = "References" if change == "bibliography" else section.title
        section.body = {
            **section.body,
            "text": "[citation needed]" if change == "bibliography" else "Changed",
        }
    elif change == "source":
        manuscript.body = {**manuscript.body, "source_ids": ["missing-source"]}
    elif change == "receipt":
        quality.update_campaign(campaign, verification_receipts=[{"id": "fabricated", "outcome": "passed"}])
    elif change == "identity":
        agents = research_tasks.agents_for(session, task.id)
        parent = next(a for a in agents if a.role == "parent")
        child = next(a for a in agents if a.role == "child")
        child.provenance = {**child.provenance, "specialist_report_model": parent.provenance["draft_model"]}
    elif change == "campaign":
        campaign.deleted_at = utcnow()
        manuscript.body = {k: v for k, v in manuscript.body.items() if k != "quality_policy"}
    session.commit()
    state = quality.assessment(session, mid)
    assert not state["agent_checks_complete"] and state["required"]


def test_actual_allowlisted_check_has_reproducible_scope():
    result = manuscript_verification.execute_routine(
        "finite_partitions_v1", deadline=time.monotonic() + 30, cancel=threading.Event()
    )
    assert [r["partitions"] for r in result["cases"]] == [1, 2, 5, 15, 52]
    assert result["ordered_pairs"] == 2959
    payload = copy.deepcopy(result)
    assert payload.pop("receipt_sha256") == stable_hash(payload)
    with pytest.raises(ValueError, match="allowlisted"):
        manuscript_verification.execute_routine("model_generated_code", deadline=0, cancel=threading.Event())


def test_observed_live_review_size_fits_without_increasing_task_budget(session, project):
    task = run(session, project, "large_review")
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert quality.assessment(session, task.contract["quality_manuscript_id"])["agent_checks_complete"]
    assert task.ledger["actual_tokens"] == 4 * 19555 + 200
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"] == 96000


def test_requested_search_failure_is_preserved_and_blocks_review(session, project, monkeypatch):
    class FailedAdapter:
        last_error = "TimeoutError"
        _session = None

        def __init__(self, **kwargs):
            pass

        def search(self, query, *, count):
            return []

    monkeypatch.setattr(manuscript_acquisition, "CrossrefAdapter", FailedAdapter)
    task = task_for(
        session,
        project,
        allow_public_search=True,
        verification_routines=["finite_partitions_v1"],
        literature_queries=[{"provider": "crossref", "query": "fixture", "count": 1}],
    )
    task.started_at = utcnow()
    session.commit()
    manuscript, campaign = quality.create_campaign(session, task)
    runner = research_runner.Runner(session, task, threading.Event(), None)
    manuscript_acquisition.collect(runner, manuscript, campaign)
    session.expire_all()
    assert len(campaign.body["verification_receipts"]) == 1
    assert campaign.body["search_receipts"][0]["status"] == "failed"
    assert manuscript.body["quality_evidence"]
    _, digest = quality.apply_draft(session, task, manuscript, campaign, reply("draft", {}), "author")
    packet = quality.packet_for(task, campaign, digest, "literature_contribution", [])
    assert (
        "requested literature search did not complete"
        in quality.validate_report(reply("audit", {"packet": packet}), packet)[1]
    )


def test_revision_ceiling_and_consistent_release_and_path_blockers(session, project):
    task = run(session, project, "revise", max_revision_cycles=0)
    mid = task.contract["quality_manuscript_id"]
    assert len(research_tasks.agents_for(session, task.id)) == 5
    assert not quality.assessment(session, mid)["agent_checks_complete"]
    assert any(f["code"] == "manuscript-quality-incomplete" for f in audits.audit_manuscript(session, mid))
    path = manuscript_path.build_project_path(session, project.id, manuscript_id=mid)
    assert not path["publication_ready"]
    assert next(s for s in path["stages"] if s["id"] == "specialist_review")["state"] == "blocked"


def test_cancelled_campaign_cannot_restart_or_call_models(session, project):
    task = task_for(session, project)
    task.state, task.started_at = "planning", utcnow()
    session.commit()
    cancelled = threading.Event()
    cancelled.set()
    research_runner.run_task(task.id, cancelled)
    session.expire_all()
    assert task.state == "cancelled_partial"
    assert not research_tasks.agents_for(session, task.id)
    original = copy.deepcopy(task.ledger)
    research_runner.run_task(task.id, threading.Event())
    session.expire_all()
    assert task.ledger == original


@pytest.mark.parametrize("stale", [False, True])
def test_compute_receipt_requires_current_approved_inputs(session, project, monkeypatch, stale):
    task = task_for(session, project)
    run = ComputeRun(
        project_id=project.id,
        script_source_id=task.sources[0]["source_id"],
        state="succeeded",
        review_state="verified",
        review_note="fixture",
        plan_hash="a" * 64,
        plan={},
    )
    session.add(run)
    session.flush()
    task.contract = {**task.contract, "compute_run_ids": [run.id]}
    task.started_at = utcnow()
    monkeypatch.setattr(
        manuscript_acquisition.compute, "run_out", lambda s, r: {"plan_status": {"stale": stale}}
    )
    monkeypatch.setattr(manuscript_acquisition.compute, "_verify_output_artifacts", lambda r: None)
    manuscript, campaign = quality.create_campaign(session, task)
    runner = research_runner.Runner(session, task, threading.Event(), None)
    manuscript_acquisition.collect(runner, manuscript, campaign)
    session.expire_all()
    assert campaign.body["verification_receipts"][0]["outcome"] == (
        "not_run" if stale else "passed_within_scope"
    )


def test_forecast_separates_repairs_and_does_not_scale_with_ceiling():
    allocations = [
        {"agent_id": "proof", "phase": "audit", "actual_tokens": 19505,
         "final_actual": True, "operation_kind": "audit"},
        {"agent_id": "proof", "phase": "audit", "actual_tokens": 37000,
         "final_actual": True, "operation_kind": "report_correction"},
    ]
    runner = SimpleNamespace(task=SimpleNamespace(contract={"token_limit": 240000}),
        allocations=allocations, agents=[SimpleNamespace(id="proof", assignment={
            "specialist_role": "proof_method"})], remaining_tokens=lambda: 150000)
    plan = _revision_budget(runner)
    assert plan["review_role_reserves"]["proof_method"] == 24382
    assert plan["repair_reserve"] == 46250
    runner.task.contract["token_limit"] = 420000
    enlarged = _revision_budget(runner)
    assert enlarged["review_reserve"] == plan["review_reserve"]
    assert enlarged["minimum_author_grant"] == plan["minimum_author_grant"]
    assert plan["author_grant"] + plan["review_reserve"] + plan["repair_reserve"] + plan["handoff_reserve"] <= 150000


def test_verifier_reproduction_artifact_is_bound_and_inspectable(session, project):
    from workbench import storage

    task = task_for(session, project, verification_routines=["finite_partitions_v1"])
    task.started_at = utcnow()
    manuscript, campaign = quality.create_campaign(session, task)
    runner = research_runner.Runner(session, task, threading.Event(), None)
    manuscript_acquisition.collect(runner, manuscript, campaign)
    receipt = campaign.body["verification_receipts"][0]
    reproduction = receipt["reproduction"]
    assert storage.read_bytes(reproduction["implementation_artifact"]).decode() == reproduction["implementation_text"]
    assert reproduction["expected_output"]["ordered_pairs"] == 2959
    assert receipt["implementation_sha256"] in reproduction["invocation"]
    assert manuscript.body["quality_verifier_artifacts"] == [reproduction["implementation_artifact"]]
    _, digest = quality.apply_draft(session, task, manuscript, campaign, reply("draft", {}), "author")
    packet = quality.packet_for(task, campaign, digest, "proof_method", [])
    assert any(row["kind"] == "reviewed_verifier" for row in packet["evidence_artifacts"])
    bound = evidence_basis.collect(session, manuscript.id)
    assert reproduction["implementation_artifact"]["sha256"] in json.dumps(bound)
    path = Path(reproduction["implementation_artifact"]["local_path"])
    path.write_bytes(b"changed trusted implementation")
    assert "execution or search receipts unavailable" in quality.assessment(session, manuscript.id)["blockers"]


def test_hash_checked_verifier_cli_matches_deterministic_output():
    import subprocess

    receipt = manuscript_verification.execute_routine(
        "finite_partitions_v1", deadline=time.monotonic() + 30, cancel=threading.Event())
    command = [sys.executable, "-m", "workbench.services.manuscript_verification", "--expected-sha256"]
    actual = subprocess.run([*command, receipt["implementation_sha256"]], capture_output=True, text=True, check=True)
    assert json.loads(actual.stdout) == manuscript_verification.deterministic_result(receipt)
    denied = subprocess.run([*command, "0" * 64], capture_output=True, text=True)
    assert denied.returncode != 0 and not denied.stdout


def test_legacy_retained_context_repair_does_not_forecast_fresh_calls():
    runner = SimpleNamespace(task=SimpleNamespace(contract={"token_limit": 240000}),
        allocations=[{"agent_id": "proof", "phase": "audit", "actual_tokens": 19505,
                      "final_actual": True},
                     {"agent_id": "proof", "phase": "audit", "actual_tokens": 37000,
                      "final_actual": True}],
        agents=[SimpleNamespace(id="proof", assignment={"specialist_role": "proof_method"})],
        remaining_tokens=lambda: 150000)
    plan = _revision_budget(runner)
    assert plan["review_role_reserves"]["proof_method"] == 24382
    assert plan["repair_reserve"] == 20000


@pytest.mark.parametrize("bounds", [
    {"min_words": 10, "max_words": 9}, {"min_words": 0, "max_words": 9},
    {"min_words": True, "max_words": 9}, {"min_words": "4", "max_words": 9},
    {"min_words": 4, "max_words": 9, "counting_policy": "invented"},
])
def test_invalid_structured_length_bounds_are_rejected(bounds):
    with pytest.raises(ValueError):
        TaskBrief(question="Length bounds", task_type="manuscript", manuscript_length=bounds)


def test_length_bounds_are_manuscript_only_and_not_inferred_from_prose():
    with pytest.raises(ValueError, match="manuscript task"):
        TaskBrief(question="Research", manuscript_length={"min_words": 4, "max_words": 9})
    legacy = TaskBrief(question="Legacy", task_type="manuscript", success_criteria="900-1200 words")
    assert legacy.normalized()["manuscript_length"] is None


@pytest.mark.parametrize("count,status", [(3, "out_of_bounds"), (4, "within_bounds"),
                                         (6, "within_bounds"), (7, "out_of_bounds")])
def test_manuscript_word_count_has_inclusive_bounds_and_documented_scope(count, status):
    draft = reply("draft", {})
    draft["title"] = "Ignored title words"
    draft["sections"][0]["heading"] = "Ignored heading words"
    draft["sections"][0]["text"] = "\t\n".join(["word"] * (count - 1))
    draft["sections"].append({"id": "references", "heading": "References", "text": "Reference"})
    measured = quality.length_check(draft, {"min_words": 4, "max_words": 6})
    assert measured["word_count"] == count and measured["status"] == status


def test_length_rejection_precedes_manuscript_mutation_and_reviewer_dispatch(session, project):
    task = run(session, project, manuscript_length={"min_words": 900, "max_words": 1200})
    assert task.state == "failed_partial"
    agents = research_tasks.agents_for(session, task.id)
    assert len(agents) == 1
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert not campaign.body["drafts"] and not campaign.body["reports"]
    assert len(campaign.body["rejected_drafts"]) == 2
    issue = campaign.body["rejected_drafts"][0]["issues"][0]
    assert issue["code"] == "manuscript_length" and issue["word_count"] == 4
    assert issue["bounds"]["min_words"] == 900
    assert [a["operation_kind"] for a in task.ledger["allocations"]] == ["draft", "draft_correction"]
    manuscript = session.get(ResearchObject, task.contract["quality_manuscript_id"])
    assert not authoring.manuscript_sections(session, manuscript.id)
    assert not manuscript.accepted_by_user


def test_structured_length_reaches_reviewers_and_readiness_and_stale_bounds_block(session, project):
    task = run(session, project, manuscript_length={"min_words": 4, "max_words": 4})
    assert task.state == "completed", task.ledger.get("stop_reason")
    mid = task.contract["quality_manuscript_id"]
    campaign = quality.campaign_for(session, mid)
    for row in campaign.body["dispatches"]:
        assert row["packet"]["task_requirements"]["manuscript_length"]["min_words"] == 4
        assert row["packet"]["task_requirements"]["success_criteria"] == task.contract["success_criteria"]
        assert row["packet"]["length_check"]["status"] == "within_bounds"
    readiness = manuscript_readiness.report(session, mid)
    assert readiness["length_check"]["word_count"] == 4
    assert not readiness["release_eligible"] and not readiness["human_publication_approval"]
    task.contract = {**task.contract, "manuscript_length": {
        "min_words": 3, "max_words": 5, "counting_policy": "section-text-whitespace-v1"}}
    session.commit()
    changed_requirements = quality.assessment(session, mid)
    assert changed_requirements["length_check"]["status"] == "within_bounds"
    assert not changed_requirements["agent_checks_complete"]
    assert "specialist assignment or evidence changed" in changed_requirements["blockers"]
    task.contract = {**task.contract, "manuscript_length": {
        "min_words": 900, "max_words": 1200, "counting_policy": "section-text-whitespace-v1"}}
    session.commit()
    state = quality.assessment(session, mid)
    assert not state["agent_checks_complete"]
    assert "manuscript length is outside required bounds" in state["blockers"]
    assert "specialist assignment or evidence changed" in state["blockers"]


def test_initial_reviews_preserve_a_bounded_repair_pool_near_their_grants(session, project):
    task = run(session, project, "report_repair", "initial_review_near_grant")
    assert task.state == "completed", task.ledger.get("stop_reason")
    allocations = task.ledger["allocations"]
    repairs = [a for a in allocations if a.get("operation_kind") == "report_correction"]
    assert len(repairs) == 1 and repairs[0]["reserved"] >= 1000
    assert len(research_tasks.agents_for(session, task.id)) == 5
    assert task.ledger["charged_tokens"] <= task.contract["token_limit"]


def test_spent_repair_pool_is_not_reserved_again_for_deferred_review(session, project):
    task = run(session, project, "revise", "tight_re_review_repair", token_limit=92000)
    assert task.state == "completed", task.ledger.get("stop_reason")
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    repair = next(a for a in task.ledger["allocations"] if a.get("operation_kind") == "report_correction")
    assert repair["actual_tokens"] >= campaign.body["revision_budget_plans"][0]["repair_reserve"]
    assert len(campaign.body["reports"]) == 8 and task.ledger["parent_integration_received"]
    assert task.ledger["charged_tokens"] <= 92000


@pytest.mark.parametrize("field,new_value", [
    ("question", "A different research objective"), ("paper_type", "research"),
    ("instructions", "A changed task specification"),
    ("verification_routines", ["finite_partitions_v1"]),
])
def test_scoped_task_changes_invalidate_reviewer_binding(session, project, field, new_value):
    task = run(session, project)
    task.contract = {**task.contract, field: new_value}
    session.commit()
    state = quality.assessment(session, task.contract["quality_manuscript_id"])
    assert not state["agent_checks_complete"]
    assert "specialist assignment or evidence changed" in state["blockers"]


def test_frozen_source_manifest_changes_invalidate_review(session, project):
    task = run(session, project)
    sources = copy.deepcopy(task.sources)
    sources[0]["title"] = "Changed frozen source metadata"
    task.sources = sources
    session.commit()
    state = quality.assessment(session, task.contract["quality_manuscript_id"])
    assert not state["agent_checks_complete"]
    assert "specialist assignment or evidence changed" in state["blockers"]


def test_resealed_specialist_report_cannot_replace_original_return(session, project):
    task = run(session, project)
    mid = task.contract["quality_manuscript_id"]
    campaign = quality.campaign_for(session, mid)
    child = next(a for a in research_tasks.agents_for(session, task.id) if a.role == "child")
    child.report = {**child.report, "summary": "Changed after the model returned."}
    reports = copy.deepcopy(campaign.body["reports"])
    next(row for row in reports if row["agent_id"] == child.id)["report_sha256"] = stable_hash(child.report)
    quality.update_campaign(campaign, reports=reports)
    session.commit()
    state = quality.assessment(session, mid)
    assert not state["agent_checks_complete"]
    assert "accepted specialist report differs from its original return" in state["blockers"]


def test_ambiguous_evidence_diagnostic_is_accepted_but_blocks_release(session, project):
    task = run(session, project, "ambiguous_evidence")
    assert task.state == "completed", task.ledger.get("stop_reason")
    mid = task.contract["quality_manuscript_id"]
    state = quality.assessment(session, mid)
    assert state["agent_checks_complete"] and state["release_review_flags"]
    assert all(not flag["resolved"] for flag in state["release_review_flags"])
    campaign = quality.campaign_for(session, mid)
    records = copy.deepcopy(campaign.body["reports"])
    for record in records:
        for flag in record["review_flags"]:
            flag["resolved"] = True
    quality.update_campaign(campaign, reports=records)
    session.commit()
    assert quality.assessment(session, mid)["release_review_flags"]
    assert any(f["code"] == "manuscript-evidence-review-flag" and f["severity"] == "error"
               for f in audits.audit_manuscript(session, mid))
    readiness = manuscript_readiness.report(session, mid)
    assert readiness["diagnostic_handoff_complete"]
    assert readiness["release_review_flags"] and not readiness["release_eligible"]
    from workbench.services import publication_packages, submissions

    submission = submissions.create_submission(session, project.id, manuscript_id=mid)
    package = publication_packages.create_package(session, submission.id)
    publication = publication_packages.readiness(session, package.id)
    assert any(b["code"] == "manuscript-audit-blocker"
               and "manuscript-evidence-review-flag" in b["message"] for b in publication["blockers"])


def test_length_readiness_measures_current_section_text(session, project):
    task = run(session, project, manuscript_length={"min_words": 4, "max_words": 4})
    mid = task.contract["quality_manuscript_id"]
    section = authoring.manuscript_sections(session, mid)[0]
    section.body = {**section.body, "text": "Short"}
    session.commit()
    state = quality.assessment(session, mid)
    assert state["length_check"]["word_count"] == 1
    assert "manuscript length is outside required bounds" in state["blockers"]


def test_revision_forecast_accounts_for_original_report_in_fresh_repair(session, project):
    task, _manuscript, campaign, packet, report = candidate_packet(session, project)
    task.contract = {**task.contract, "token_limit": 240000}
    runner = SimpleNamespace(task=task, session=session, agents=[], allocations=[],
                             remaining_tokens=lambda: 150000)
    baseline = _revision_budget(runner, campaign)
    report["summary"] = "An extensive rejected report. " * 10000
    runner.agents = [SimpleNamespace(id="proof", assignment={"specialist_role": packet["role"]},
        provenance={"report_attempts": [{"report": report}]})]
    quality.update_campaign(campaign, rejected_reports=[{
        "agent_id": "proof", "issues": [{"code": "quotation", "message": "Absent source quotation"}]}])
    plan = _revision_budget(runner, campaign)
    assert plan["review_reserve"] == baseline["review_reserve"]
    assert plan["repair_input_token_estimate"] > baseline["repair_input_token_estimate"]
    assert plan["repair_reserve"] > baseline["repair_reserve"]
    assert plan["author_grant"] < baseline["author_grant"]


def test_deleted_production_task_invalidates_manuscript_clearance(session, project):
    task = run(session, project)
    task.deleted_at = utcnow()
    session.commit()
    state = quality.assessment(session, task.contract["quality_manuscript_id"])
    assert not state["agent_checks_complete"]
    assert "required manuscript production task is unavailable" in state["blockers"]


def test_length_correction_uses_empty_response_inventory_and_preserves_both_returns(session, project):
    task = run(session, project, "length_response_contract",
               manuscript_length={"min_words": 900, "max_words": 1200})
    assert task.state == "completed", task.ledger.get("stop_reason")
    parent = next(a for a in research_tasks.agents_for(session, task.id) if a.role == "parent")
    attempts = parent.provenance["draft_attempts"]
    assert [sum(len(s["text"].split()) for s in a["draft"]["sections"]) for a in attempts] == [811, 1045]
    assert all(a["draft"]["responses"] == [] for a in attempts)
    assert [a["operation_kind"] for a in task.ledger["allocations"][:2]] == ["draft", "draft_correction"]
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert len(campaign.body["rejected_drafts"]) == 1 and len(campaign.body["drafts"]) == 1
    assert len(campaign.body["reports"]) == 4


def test_invented_validation_response_is_rejected_before_manuscript_mutation(session, project):
    task, manuscript, campaign, _packet, raw = candidate_packet(session, project)
    original = copy.deepcopy(manuscript.body)
    original_drafts = copy.deepcopy(campaign.body["drafts"])
    raw = reply("draft", {})
    raw["responses"] = [{"comment_id": "manuscript_length", "response": "Expanded.", "changes": "Longer."}]
    with pytest.raises(quality.DraftValidationError) as captured:
        quality.apply_draft(session, task, manuscript, campaign, raw, "author", expected_response_ids=[])
    issue = next(i for i in captured.value.issues if i["code"] == "responses")
    assert issue["expected_response_ids"] == issue["missing_response_ids"] == []
    assert issue["unexpected_response_ids"] == ["manuscript_length"]
    assert manuscript.body == original and campaign.body["drafts"] == original_drafts


def test_stream_failure_code_is_preserved_in_saved_provenance_and_trace(session, project):
    task = run(session, project, "stream_failure")
    assert task.state == "failed_partial"
    proof = next(a for a in research_tasks.agents_for(session, task.id)
                 if a.assignment.get("specialist_role") == "proof_method")
    assert proof.provenance["worker_failure_code"] == "runtime_error"
    assert proof.provenance["worker_failure_stage"] == "turn_stream"
    failure = next(e for e in task.ledger["call_trace"] if e["event"] == "worker_failed")
    assert failure["agent_id"] == proof.id and failure["failure_code"] == "runtime_error"
    assert failure["call_stack"]
    assert "PRIVATE_RUNTIME_MESSAGE" not in json.dumps(proof.provenance)
    assert "PRIVATE_RUNTIME_MESSAGE" not in json.dumps(task.ledger)
    assert not task.ledger.get("parent_integration_received")


def test_runtime_diagnostics_survive_package_without_retry_or_release(session, project):
    task = run(session, project, "runtime_diagnostics")
    assert task.state == "failed_partial"
    agents = research_tasks.agents_for(session, task.id)
    proof = next(a for a in agents if a.assignment.get("specialist_role") == "proof_method")
    info = proof.provenance["worker_runtime_error"]
    assert info["category"] == "responseStreamDisconnected" and info["will_retry"] is True
    failure = next(e for e in task.ledger["call_trace"] if e["event"] == "worker_failed")
    assert failure["runtime_error"] == info and failure["agent_id"] == proof.id
    activity = proof.provenance["codex_activities"][0]
    assert activity["summary"]["local_heartbeat_gap_observed"]
    assert activity["summary"]["long_observable_silence"]
    allocations = task.ledger["allocations"]
    audits = [a for a in allocations if a["phase"] == "audit"]
    proof_allocation = next(a for a in audits if a["agent_id"] == proof.id)
    assert not proof_allocation.get("final_actual")
    assert research_runner.allocation_charge(proof_allocation) == proof_allocation["reserved"]
    assert sum(research_runner.allocation_charge(a) for a in allocations) == task.ledger["charged_tokens"]
    assert [a["operation_kind"] for a in allocations].count("draft") == 1
    assert not any(a["operation_kind"] in {"draft_correction", "report_correction", "revise"} for a in allocations)
    snapshot = research_tasks.snapshot(session, task)
    assert not snapshot["readiness"]["release_eligible"] and not snapshot["readiness"]["agent_checks_complete"]
    assert "PRIVATE_RUNTIME_MESSAGE" not in json.dumps(snapshot)
    with zipfile.ZipFile(io.BytesIO(research_tasks.package(session, task))) as archive:
        data = b"\n".join(archive.read(name) for name in archive.namelist() if name.endswith(".json"))
    assert b"responseStreamDisconnected" in data and b"max_heartbeat_gap_seconds" in data
    assert b"PRIVATE_RUNTIME_MESSAGE" not in data
