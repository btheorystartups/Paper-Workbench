"""Offline closure gate and portable evidence regressions; no model calls."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from workbench.models import stable_hash
from workbench.providers.research_quality_offline import reply
from workbench.services import manuscript_closure as closure
from workbench.services import manuscript_evidence_package as evidence


def fixture():
    candidate = {"title": "Finite note", "novelty_claim": False, "limitations": ["Finite only"],
                 "claims": [{"id": "c1", "statement": "Finite identity", "kind": "theorem",
                             "source_ids": [], "verification_ids": []}],
                 "sections": [{"id": "s1", "heading": "Proof", "text": "Finite identity.",
                               "claim_ids": ["c1"]}], "responses": []}
    task = SimpleNamespace(contract={"quality_policy": closure.QUALITY_POLICY,
        "paper_type": "expository", "success_criteria": "Explain finite identity.",
        "instructions": "State assumptions.", "manuscript_length": None,
        "verification_routines": [], "compute_run_ids": []}, sources=[])
    campaign = SimpleNamespace(body={"drafts": [{"candidate": candidate,
                                                  "candidate_sha256": stable_hash(candidate)}],
                                     "verification_receipts": [], "search_receipts": [],
                                     "reports": []})
    return task, campaign, candidate


def report_for(packet):
    return reply("closure", {"packet": packet})


def finding():
    return {"id": "F1", "category": "error", "disposition": "open",
            "dimension": "terminology", "affected_sections": ["s1"],
            "requirement_ids": ["purpose"], "problem": "Literal terminology is wrong.",
            "acceptance_criterion": "Correct the literal terminology.",
            "evidence_paths": ["manuscript.md#s1"], "disposition_reason": "Sentence remains."}


def decide(report, packet, **kwargs):
    return closure.evaluate(report, packet, assigned_reviewer_id="reviewer",
                            reviewer_thread_id="independent", writer_thread_ids={"author"},
                            specialists_current=True, artifacts_verified=True, **kwargs)["status"]


def test_preflight_is_not_acceptance():
    task, campaign, candidate = fixture()
    packet = closure.packet_for(task, campaign, stable_hash(candidate), "reviewer", "preflight")
    assert decide(report_for(packet), packet) == "preflight_complete"
    report = report_for(packet)
    report["findings"] = [finding()]
    assert decide(report, packet) == "needs_revision"
    report["findings"][0]["disposition"] = "resolved"
    assert decide(report, packet) == "invalid_report"


def test_cross_dimension_required_finding_still_blocks_and_optional_only_does_not():
    task, campaign, candidate = fixture()
    packet = closure.packet_for(task, campaign, stable_hash(candidate), "reviewer", "preflight")
    report = report_for(packet)
    report["checks"][0]["outcome"] = "unresolved"
    report["findings"] = [{**finding(), "category": "optional_improvement"}]
    assert decide(report, packet) == "invalid_report"
    report["findings"] = [finding()]
    report["checks"][1]["outcome"] = "unresolved"
    assert decide(report, packet) == "needs_revision"


def test_confirmation_preserves_prior_finding_substance():
    task, campaign, candidate = fixture()
    preflight = closure.packet_for(task, campaign, stable_hash(candidate), "first", "preflight")
    campaign.body["closure_scope"] = preflight["scope"]
    campaign.body["closure_reports"] = [{"candidate_sha256": stable_hash(candidate),
                                          "report": {"findings": [finding()]}}]
    changed = deepcopy(candidate)
    changed["sections"][0]["text"] = "Corrected terminology."
    campaign.body["drafts"].append({"candidate": changed, "candidate_sha256": stable_hash(changed)})
    campaign.body["closure_repair"] = {"author_id": "author", "base_candidate_sha256": stable_hash(candidate),
                                       "candidate_sha256": stable_hash(changed), "finding_ids": ["F1"]}
    packet = closure.packet_for(task, campaign, stable_hash(changed), "reviewer", "confirmation")
    report = report_for(packet)
    report["findings"][0]["disposition"] = "resolved"
    assert decide(report, packet) == "ready_for_human_review"
    report["findings"][0]["problem"] = "A different problem"
    assert decide(report, packet) == "invalid_report"
    report["findings"][0]["problem"] = finding()["problem"]
    report["findings"][0]["disposition"] = "justified_rejection"
    assert decide(report, packet) == "invalid_report"


def test_new_required_confirmation_defect_stops():
    task, campaign, candidate = fixture()
    packet = closure.packet_for(task, campaign, stable_hash(candidate), "reviewer", "confirmation")
    report = report_for(packet)
    report["findings"] = [finding()]
    assert decide(report, packet) == "needs_revision"
    report["findings"][0]["disposition"] = "resolved"
    assert decide(report, packet) == "invalid_report"


def test_author_thread_cannot_review():
    task, campaign, candidate = fixture()
    packet = closure.packet_for(task, campaign, stable_hash(candidate), "reviewer", "confirmation")
    report = report_for(packet)
    assert closure.evaluate(report, packet, assigned_reviewer_id="reviewer",
        reviewer_thread_id="author", writer_thread_ids={"author"},
        specialists_current=True, artifacts_verified=True)["status"] == "invalid_report"


def test_evidence_empty_receipts_are_truthful_and_reviews_do_not_repeat_packets():
    task, campaign, candidate = fixture()
    report = {"summary": "Retained specialist finding", "objections": []}
    campaign.body["reports"] = [{"agent_id": "reviewer", "role": "proof_method", "iteration": 0,
        "candidate_sha256": stable_hash(candidate), "packet": {"packet_sha256": "a" * 64,
            "candidate": candidate, "admitted_original_evidence": {"source": "DUPLICATED_PACKET_TEXT"}},
        "report": report, "report_sha256": stable_hash(report), "blockers": []}]
    files = evidence.files_for(task, campaign)
    evidence.verify_files(files)
    assert b"No verifier implementation is supplied" in files["evidence/README.md"]
    rows = json.loads(files["evidence/specialist-records.json"])
    assert rows[0]["packet_sha256"] == "a" * 64 and rows[0]["report"] == report
    assert rows[0]["report_sha256"] == stable_hash(report)
    assert b"DUPLICATED_PACKET_TEXT" not in files["evidence/specialist-records.json"]
    assert "packet" not in rows[0]
    campaign.body["reports"][0]["report"]["summary"] = "Tampered specialist content"
    with pytest.raises(ValueError, match="accepted hash"):
        evidence.files_for(task, campaign)


def test_retained_verifier_is_exported_and_hashed(monkeypatch):
    script = b"print('checked')\n"
    digest = hashlib.sha256(script).hexdigest()
    receipt = {"id": "routine_1", "implementation_sha256": digest, "scope": "tiny",
               "reproduction": {"implementation_artifact": {"sha256": digest},
                                "implementation_text": script.decode(),
                                "expected_output": {"status": "checked"}}}
    monkeypatch.setattr(evidence.storage, "read_bytes", lambda ref: script)
    task, campaign, candidate = fixture()
    campaign.body["verification_receipts"] = [receipt]
    campaign.body["search_receipts"] = [{"id": "search-1", "query": "finite"}]
    files = evidence.files_for(task, campaign)
    evidence.verify_files(files)
    assert files["evidence/verification/routine_1.py"] == script
    assert json.loads(files["evidence/search-receipts.json"])[0]["id"] == "search-1"
    packet = closure.packet_for(task, campaign, stable_hash(candidate), "reviewer", "preflight")
    assert packet["evidence_files"]["evidence/verification/routine_1.py"] == script.decode()
    files["evidence/verification/routine_1.py"] = b"changed"
    with pytest.raises(ValueError, match="differs"):
        evidence.verify_files(files)
