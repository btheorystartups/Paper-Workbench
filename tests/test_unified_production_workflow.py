"""Synthetic production path across research, writing, review and release; no live provider."""

import json
import sys
import threading
from pathlib import Path

from sqlalchemy import select

from workbench import config
from workbench.models import ProposedAction, ResearchTask, stable_hash, utcnow
from workbench.providers.research_executor import ProcessResearchExecutor
from workbench.research_contract import TaskBrief
from workbench.services import (
    authoring,
    authorship,
    dialogue,
    manuscript_chat,
    publication_packages,
    research_runner,
    research_tasks,
    revision_review,
    submissions,
)

WORKER = Path(__file__).parent / "fixtures" / "research_protocol_worker.py"


def test_reviewed_research_reaches_manuscript_and_bound_release(
    session, project, tmp_path, monkeypatch
):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WB_DEPLOYMENT_MODE", "local")
    monkeypatch.setenv("WB_RESEARCH_EXECUTOR_ENABLED", "true")
    monkeypatch.setenv(
        "WB_RESEARCH_EXECUTOR_COMMAND",
        json.dumps([sys.executable, str(WORKER), "live-best-effort"]),
    )
    config.get_settings.cache_clear()

    manuscript = authoring.create_manuscript(session, project.id, title="Unified synthetic paper")
    task = research_tasks.create_task(
        session,
        project.id,
        TaskBrief(
            question="Evaluate one synthetic claim for a bounded manuscript example.",
            executor="process",
            allow_best_effort_tokens=True,
            max_children=1,
        ),
    )
    research_tasks.attach(
        session,
        task,
        "synthetic-source.md",
        b"Synthetic evidence supplied only for this integration test.",
        version="v1",
    )
    task.state, task.started_at = "planning", utcnow()
    session.commit()
    try:
        research_runner.run_task(
            task.id,
            threading.Event(),
            executor_factory=lambda mode: ProcessResearchExecutor(
                mode, [sys.executable, str(WORKER), "live-best-effort"]
            ),
        )
    finally:
        research_runner.shutdown()
    session.expire_all()
    task = session.get(ResearchTask, task.id)
    assert task.state == "completed" and task.ledger["live_handoff_verified"], task.ledger.get(
        "stop_reason"
    )

    child = next(agent for agent in research_tasks.agents_for(session, task.id) if agent.role == "child")
    finding = child.report["findings"][0]
    review_hash = research_tasks.snapshot(session, task)["review_hash"]
    research_tasks.review_finding(
        session,
        task,
        agent_id=child.id,
        finding_id=finding["id"],
        expected_hash=review_hash,
        decision="approved",
        purpose="manuscript",
        note="Human checked the synthetic source, scope and report linkage.",
        reviewer="synthetic-human",
    )
    promoted = research_tasks.promote(
        session,
        task,
        agent_id=child.id,
        finding_id=finding["id"],
        purpose="manuscript",
        expected_hash=review_hash,
        manuscript_id=manuscript.id,
    )
    session.commit()

    thread = dialogue.create_thread(
        session,
        project.id,
        title="Revise reviewed finding",
        mode="act",
        manuscript_id=manuscript.id,
        section_id=promoted["section_id"],
    )
    context = manuscript_chat.context(session, thread)
    assert any(item["id"] == promoted["object_id"] for item in context["items"])
    _, turn = dialogue.post_user_turn(
        session,
        thread.id,
        "revise: State the reviewed finding with its bounded synthetic scope.",
    )
    session.commit()
    action = session.scalar(
        select(ProposedAction).where(ProposedAction.result["turn_id"].as_string() == turn.id)
    )
    dialogue.approve_action(session, action.id, plan_hash=action.plan_hash)
    session.commit()

    review = revision_review.open_round(
        session,
        manuscript.id,
        reviewer="synthetic-reviewer",
        comments=[{
            "id": "R1",
            "objection": "Confirm that the promoted source and scope remain bound.",
            "acceptance_criterion": "The final candidate retains the promoted claim and evidence link.",
        }],
    )
    revision_review.respond(
        session,
        review.id,
        comment_id="R1",
        author="synthetic-author",
        response="The scoped claim and source linkage are retained.",
        changes="No evidence link was removed; prose was narrowed to the recorded scope.",
    )
    response = review.body["events"][-1]
    comment = review.body["comments"][0]
    candidate_hash = revision_review.candidate_hash(session, manuscript.id)
    revision_review.verify(
        session,
        review.id,
        comment_id="R1",
        verifier="synthetic-independent-verifier",
        response_hash=stable_hash(response),
        expected_candidate_hash=candidate_hash,
        expected_comment_hash=stable_hash(comment),
        criterion_met=True,
        regression_passed=True,
        evidence="The promoted claim, result object and research-task hash remain in the evidence basis.",
        disposition="resolved",
    )
    assert revision_review.dispositions(session, review) == {"R1": "resolved"}

    contributor = authorship.create_contributor(
        session,
        project.id,
        display_name="Synthetic Author",
        given_names="Synthetic",
        family_name="Author",
        corresponding=True,
    )
    assignment = authorship.propose_assignment(
        session,
        manuscript.id,
        contributor_id=contributor.id,
        role="writing_original_draft",
        degree="lead",
        rationale="Authored and reviewed the synthetic integration artifact.",
    )
    authorship.review_assignment(session, assignment.id, state="confirmed", note="confirmed")
    order = authorship.suggest_order(session, manuscript.id)
    authorship.review_order_proposal(session, order.id, decision="approved", note="approved")
    assert revision_review.dispositions(session, review) == {"R1": "open"}
    revision_review.respond(
        session,
        review.id,
        comment_id="R1",
        author="synthetic-author",
        response="The final authorship record and scoped evidence linkage are retained.",
        changes="Authorship was finalized; the promoted claim and evidence graph are unchanged.",
    )
    response = review.body["events"][-1]
    candidate_hash = revision_review.candidate_hash(session, manuscript.id)
    revision_review.verify(
        session,
        review.id,
        comment_id="R1",
        verifier="synthetic-independent-verifier",
        response_hash=stable_hash(response),
        expected_candidate_hash=candidate_hash,
        expected_comment_hash=stable_hash(comment),
        criterion_met=True,
        regression_passed=True,
        evidence="Final authorship and the promoted research evidence are present in the bound basis.",
        disposition="resolved",
    )
    assert revision_review.dispositions(session, review) == {"R1": "resolved"}
    submission = submissions.create_submission(
        session,
        project.id,
        manuscript_id=manuscript.id,
        venue_name="Synthetic Journal",
    )
    package = publication_packages.create_package(session, submission.id, included_formats=["md"])
    publication_packages.set_cover_letter(
        session,
        package.id,
        text="Please consider this synthetic integration artifact.",
        state="confirmed",
        review_note="reviewed",
    )
    for kind in publication_packages.DECLARATION_TYPES:
        publication_packages.set_declaration(
            session,
            package.id,
            kind=kind,
            state="confirmed",
            text=f"Confirmed synthetic {kind.replace('_', ' ')} statement.",
            review_note="reviewed",
        )
    publication_packages.prepare_for_review(session, package.id)
    publication_packages.review_package(
        session,
        package.id,
        decision="approved",
        note="The complete synthetic package and bound evidence were reviewed.",
    )
    status = publication_packages.readiness(session, package.id)
    assert status["ready"] and not status["stale"]
    assert task.id in json.dumps(package.snapshot, sort_keys=True)
    assert promoted["object_id"] in json.dumps(package.snapshot, sort_keys=True)
