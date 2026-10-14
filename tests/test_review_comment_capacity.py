"""Saved review waves must retain every objection without starting model calls."""

from types import SimpleNamespace
from typing import Annotated

import pytest
from pydantic import TypeAdapter, ValidationError

from workbench.research_contract import (
    MAX_REVISION_COMMENTS,
    SPECIALIST_ROLES,
    ManuscriptDraft,
    SpecialistReport,
)
from workbench.services import manuscript_quality_runner as controller
from workbench.services.research_runner import StopResearch


@pytest.mark.parametrize("count", [65, MAX_REVISION_COMMENTS, MAX_REVISION_COMMENTS + 1])
def test_saved_wave_capacity_and_zero_dispatch(count, monkeypatch):
    reports, agents = [], []
    for index, role in enumerate(SPECIALIST_ROLES):
        objections = [
            {"severity": "blocking", "objection": f"Objection {number}", "acceptance_criterion": "Verify"}
            for number in range(index, count, len(SPECIALIST_ROLES))
        ]
        report = {"role": role, "objections": objections}
        agents.append(SimpleNamespace(id=role, report=report))
        reports.append({"agent_id": role, "role": role, "candidate_sha256": "a" * 64,
                        "iteration": 0, "packet": {"packet_sha256": "b" * 64, "evidence_artifacts": []}})
    campaign = SimpleNamespace(body={"reports": reports, "rounds": [], "packets": [],
                                    "audit_budget_plans": []})
    opened = []

    def open_round(*_args, comments, **_kwargs):
        opened.extend(comments)
        return SimpleNamespace(id="review")

    monkeypatch.setattr(controller.quality, "validate_report", lambda report, _packet: (report, [], []))
    monkeypatch.setattr(controller, "_revision_budget",
                        lambda *_args: {"repair_reserve": 0, "review_role_reserves": {}})
    monkeypatch.setattr(controller.research_trace, "record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(controller.revision_review, "open_round", open_round)
    monkeypatch.setattr(controller.revision_review, "dispositions", lambda *_args: {"issue": "open"})
    runner = SimpleNamespace(
        agents=agents, task=SimpleNamespace(contract={"token_limit": 1500000}),
        remaining_tokens=lambda: 1000000,
        session=SimpleNamespace(commit=lambda: None, get=lambda *_args: None),
    )
    # No executor/spawn/send methods: any attempted model work fails this test.
    if count > MAX_REVISION_COMMENTS:
        with pytest.raises(StopResearch) as error:
            controller._audit_wave(runner, SimpleNamespace(), SimpleNamespace(id="manuscript"),
                                   campaign, "a" * 64, 0)
        assert str(count) in error.value.reason
        assert str(MAX_REVISION_COMMENTS) in error.value.reason
        assert not opened
    else:
        assert not controller._audit_wave(runner, SimpleNamespace(), SimpleNamespace(id="manuscript"),
                                          campaign, "a" * 64, 0)
        assert len(opened) == len({c["id"] for c in opened}) == count
        assert campaign.body["status"] == "needs_revision"
    assert campaign.body["reports"] == reports


@pytest.mark.parametrize("model,field,row", [
    (ManuscriptDraft, "responses", {"comment_id": "c", "response": "Response", "changes": "Changes"}),
    (SpecialistReport, "resolutions", {"comment_id": "c", "criterion_met": False,
                                     "regression_passed": False, "evidence": "Unresolved",
                                     "disposition": "open"}),
])
def test_response_and_resolution_limits_match_wave(model, field, row):
    definition = model.model_fields[field]
    adapter = TypeAdapter(Annotated[definition.annotation, *definition.metadata])
    assert len(adapter.validate_python([row] * MAX_REVISION_COMMENTS)) == MAX_REVISION_COMMENTS
    with pytest.raises(ValidationError):
        adapter.validate_python([row] * (MAX_REVISION_COMMENTS + 1))
