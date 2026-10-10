"""Regression guards for manuscript escaping and bounded comparison obligations."""

import copy
import json
from types import SimpleNamespace

import pytest

from workbench.models import stable_hash
from workbench.providers.research_codex_worker import json_prompt, parse_json
from workbench.providers.research_quality_offline import reply
from workbench.research_contract import ManuscriptDraft, TaskBrief
from workbench.services import manuscript_integrity as integrity
from workbench.services import manuscript_literature as literature
from workbench.services import manuscript_quality as quality


def fixture(*, required=(), access="excerpt_available"):
    contract = TaskBrief(question="Explain the inherited result", task_type="manuscript",
                         required_literature_comparisons=list(required)).normalized()
    source = {"source_id": "note", "access": access,
              "text": "The support is updated by image and conditioning.",
              "version": "dated-note", "title": "Prior note", "authors": [], "sha256": "a" * 64}
    task = SimpleNamespace(contract=contract, sources=[source])
    candidate = reply("draft", {})
    campaign = SimpleNamespace(body={"drafts": [{"candidate": candidate,
                                                  "candidate_sha256": stable_hash(candidate)}],
                                     "verification_receipts": [], "search_receipts": [],
                                     "reports": [], "packets": []})
    packet = quality.packet_for(task, campaign, stable_hash(candidate), "literature_contribution", [])
    return task, campaign, candidate, packet, reply("audit", {"packet": packet})


@pytest.mark.parametrize("text", [
    r"\(A\ne\varnothing\)",
    "\\[\nA\\ne\\varnothing\n\\quad B\\neq\\emptyset\n\\]",
    "```latex\nA\\ne\\varnothing\n```",
])
def test_valid_math_and_code_examples_survive_json_roundtrip(text):
    task, campaign, candidate, _, _ = fixture()
    candidate["sections"][0]["text"] = text
    decoded = parse_json(json.dumps(candidate), ManuscriptDraft)
    before = copy.deepcopy(decoded)
    assert not integrity.candidate_issues(decoded)
    quality.validate_draft(task, campaign, decoded)
    assert decoded == before


@pytest.mark.parametrize("text", ["\\(x\times y\\)", "\\(\x08eta + x\\)", "Bad\x00text"])
def test_damaged_math_escaping_and_controls_are_diagnostics(text):
    assert integrity.text_issues(text, "/text")


def test_historical_style_escape_damage_blocks_report_not_mutate_candidate():
    task, campaign, candidate, packet, report = fixture()
    candidate["sections"][0]["text"] = "\\[A\ne\\varnothing\\]"
    campaign.body["drafts"][0]["candidate_sha256"] = stable_hash(candidate)
    packet = quality.packet_for(task, campaign, stable_hash(candidate), "literature_contribution", [])
    report = reply("audit", {"packet": packet})
    before = copy.deepcopy(candidate)
    _, blockers, _ = quality.validate_report(report, packet)
    assert "candidate has suspected escaping damage" in blockers
    assert candidate == before


def _supported(report):
    report["literature_comparisons"][0].update(
        status="supported_within_scope",
        rationale="Inherited support update; no theorem or priority claim.",
        passages=[{"source_id": "note", "locator": "definition 1",
                   "quotation": "support is updated by image and conditioning"}],
    )


@pytest.mark.parametrize("defect", ["missing", "duplicate", "stale", "limited_access"])
def test_required_comparisons_require_exact_current_primary_evidence(defect):
    task, campaign, _, packet, report = fixture(required=["Prior note"])
    _supported(report)
    if defect == "missing":
        report["literature_comparisons"] = []
        with pytest.raises(quality.ReportValidationError):
            quality.validate_report(report, packet)
        return
    if defect == "duplicate":
        report["literature_comparisons"].append(copy.deepcopy(report["literature_comparisons"][0]))
        with pytest.raises(quality.ReportValidationError):
            quality.validate_report(report, packet)
        return
    if defect == "limited_access":
        task.sources[0]["access"] = "metadata_only"
        packet = quality.packet_for(task, campaign, packet["candidate_sha256"], "literature_contribution", [])
        report = reply("audit", {"packet": packet})
        _supported(report)
        assert any("limited source access" in item for item in quality.validate_report(report, packet)[1])
        return
    campaign.body["reports"] = [{"role": "literature_contribution", "report": report,
                                  "candidate_sha256": "0" * 64, "report_sha256": stable_hash(report)}]
    status = literature.coverage_status(task.contract, task.sources, [], reports=campaign.body["reports"],
                                        candidate_sha256=packet["candidate_sha256"])
    assert status["required_comparisons"][0]["status"] == "not_assessed"


def test_comparison_contract_is_bounded_and_does_not_enable_search():
    brief = TaskBrief(question="Report", task_type="manuscript",
                      required_literature_comparisons=["Prior work"])
    assert not brief.allow_public_search and not brief.agent_literature_discovery
    with pytest.raises(ValueError, match="unique"):
        TaskBrief(question="Report", task_type="manuscript",
                  required_literature_comparisons=["Prior work", "Prior work"])
    assert "runtime-supplied outputSchema" in json_prompt("draft", {})
