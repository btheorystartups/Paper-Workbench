"""Submission state machine + LLM-quality eval harness (fake provider)."""

import pytest

from workbench.services import authoring, submissions, venues
from workbench.vocab import ObjectKind


@pytest.fixture()
def manuscript(session, project):
    ms = authoring.create_manuscript(session, project.id, title="Paper")
    session.commit()
    return ms


def test_submission_happy_path_with_revision(session, project, manuscript):
    venue = venues.create_venue(
        session, project.workspace_id, name="J. Boolean", rules={},
        rules_source="site 2026-07-20",
    )
    sub = submissions.create_submission(
        session, project.id, manuscript_id=manuscript.id, venue_id=venue.id,
        deadline="2026-09-01",
    )
    assert sub.status == "drafting"
    assert sub.venue_name == "J. Boolean"

    submissions.transition(session, sub.id, "submitted", note="submitted via portal")
    submissions.transition(session, sub.id, "under_review")
    submissions.transition(session, sub.id, "revision_requested", note="major revisions")
    submissions.add_revision(
        session, sub.id, summary="addressed all points",
        response_to_reviewers="R1: fixed. R2: added CUDD comparison.",
        changes=["added section 5", "new figure 3"],
    )
    submissions.transition(session, sub.id, "resubmitted")
    submissions.transition(session, sub.id, "under_review")
    final = submissions.transition(session, sub.id, "accepted")
    assert final.status == "accepted"
    assert len(final.revisions) == 1
    assert final.revisions[0]["round"] == 1
    # history is append-only and complete
    assert [h["to"] for h in final.history] == [
        "drafting", "submitted", "under_review", "revision_requested",
        "resubmitted", "under_review", "accepted",
    ]


def test_illegal_transition_rejected(session, project, manuscript):
    sub = submissions.create_submission(
        session, project.id, manuscript_id=manuscript.id, venue_name="V"
    )
    with pytest.raises(submissions.SubmissionError, match="cannot move"):
        submissions.transition(session, sub.id, "accepted")  # can't accept from drafting


def test_terminal_state_is_frozen(session, project, manuscript):
    sub = submissions.create_submission(
        session, project.id, manuscript_id=manuscript.id, venue_name="V"
    )
    submissions.transition(session, sub.id, "withdrawn")
    with pytest.raises(submissions.SubmissionError, match="terminal"):
        submissions.transition(session, sub.id, "submitted")


def test_submission_requires_real_manuscript(session, project):
    obj = None
    from workbench.services import research

    note = research.create_object(session, project.id, kind=ObjectKind.NOTE, title="not a ms")
    with pytest.raises(submissions.SubmissionError, match="manuscript not found"):
        submissions.create_submission(session, project.id, manuscript_id=note.id)
    assert obj is None


def test_llm_eval_harness_fake_all_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'le.sqlite3'}")
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
    from workbench import config, db, evals_llm

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    db.create_all()
    report = evals_llm.run(db.session_factory())
    assert report.provider_mode == "fake"
    assert report.model == "fake"
    # the fake provider is designed to be grounded, injection-safe, and action-safe
    for r in report.results:
        assert r["passed"], (r["scenario"], r["checks"])
    assert report.per_check["injection_resistance"]["pass_rate"] == 1.0
    assert report.per_check["grounding"]["pass_rate"] == 1.0
    assert report.per_check["action_registered"]["pass_rate"] == 1.0
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
