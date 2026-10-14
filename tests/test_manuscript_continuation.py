"""Continuation tests use isolated stores and controlled workers; no paid execution."""

import copy
import time

import pytest
from test_manuscript_quality import isolated as isolated
from test_manuscript_quality import run

from workbench.models import ResearchObject
from workbench.services import manuscript_quality as quality
from workbench.services import research_runner, research_tasks
from workbench.services.manuscript_continuation import ContinuationGrant, checkpoint


def grant_for(session, task, **overrides):
    return ContinuationGrant(**{
        "expected_checkpoint_sha256": checkpoint(session, task)["checkpoint_sha256"],
        "token_limit": 240000, "time_limit_seconds": 120, "max_revision_cycles": 1,
        "acknowledge_live_execution": True, **overrides,
        "retry_uncertain_operations": True,
        "authorization": {"token_ceiling": 2_000_000, "time_ceiling_seconds": 7200,
                          "reason": "Explicit controlled-test continuation authority"},
    })


def continue_and_wait(session, task, grant):
    research_runner.start(session, task, continuation=grant,
                          acknowledge_live_execution=grant.acknowledge_live_execution)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        session.expire_all()
        if task.state in research_tasks.TERMINAL and task.id not in research_runner._jobs:
            return task
        time.sleep(0.03)
    pytest.fail("controlled continuation did not finish")


def test_continue_after_author_preserves_original_accounting_and_skips_draft(session, project):
    task = run(session, project, "fail", token_limit=240000)
    assert task.state == "failed_partial"
    mid = task.contract["quality_manuscript_id"]
    old_ledger, old_contract = copy.deepcopy(task.ledger), copy.deepcopy(task.contract)
    saved = checkpoint(session, task)
    assert saved["stage"] == "audit"
    continue_and_wait(session, task, grant_for(session, task))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert task.contract["quality_manuscript_id"] == mid
    assert task.ledger["previous_runs"][0]["ledger"] == old_ledger
    assert task.ledger["previous_runs"][0]["contract"] == old_contract
    assert not any(a["phase"] == "draft" for a in task.ledger["allocations"])
    assert len(quality.campaign_for(session, mid).body["drafts"]) == 1
    assert quality.assessment(session, mid)["agent_checks_complete"]
    assert task.ledger["parent_integration_received"]


def test_partial_wave_reuses_accepted_reviews(session, project, monkeypatch):
    original = research_runner.Runner.event

    def fail_last(self, handle, agent, allocation, expected):
        if agent.assignment.get("specialist_role") == "adversarial":
            raise research_runner.StopResearch("interrupted_partial", "controlled interruption")
        return original(self, handle, agent, allocation, expected)

    monkeypatch.setattr(research_runner.Runner, "event", fail_last)
    task = run(session, project, token_limit=240000)
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    reports = copy.deepcopy(campaign.body["reports"])
    assert reports
    monkeypatch.setattr(research_runner.Runner, "event", original)
    continue_and_wait(session, task, grant_for(session, task))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert campaign.body["reports"][:len(reports)] == reports
    assert len(campaign.body["reports"]) == 4
    dispatched = [a for a in task.ledger["allocations"] if a["phase"] == "audit"]
    assert len(dispatched) == 4 - len(reports)
    assert quality.assessment(session, task.contract["quality_manuscript_id"])["agent_checks_complete"]


def test_continue_at_revision_and_then_handoff(session, project, monkeypatch):
    task = run(session, project, "revise", token_limit=240000, max_revision_cycles=0)
    assert checkpoint(session, task)["stage"] == "revise"
    with pytest.raises(research_tasks.TaskError, match="at least one"):
        research_runner.start(session, task, continuation=grant_for(session, task, max_revision_cycles=0),
                              acknowledge_live_execution=True)
    original = research_runner.Runner.send

    def stop_integration(self, handle, agent, phase, allowance, payload):
        if phase == "integrate":
            raise research_runner.StopResearch("interrupted_partial", "controlled handoff failure")
        return original(self, handle, agent, phase, allowance, payload)

    monkeypatch.setattr(research_runner.Runner, "send", stop_integration)
    continue_and_wait(session, task, grant_for(session, task))
    assert task.state == "interrupted_partial", task.ledger.get("stop_reason")
    assert checkpoint(session, task)["stage"] == "integrate"
    assert [a["phase"] for a in task.ledger["allocations"]].count("revise") == 1
    monkeypatch.setattr(research_runner.Runner, "send", original)
    continue_and_wait(session, task, grant_for(session, task, max_revision_cycles=0))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert [a["phase"] for a in task.ledger["allocations"]] == ["integrate"]
    assert len(task.ledger["previous_runs"]) == 2
    with pytest.raises(research_tasks.TaskError, match="already completed"):
        checkpoint(session, task)


@pytest.mark.parametrize("changed", ["candidate", "report", "checkpoint"])
def test_changed_checkpoint_cannot_start_paid_work(session, project, changed):
    task = run(session, project, "revise", token_limit=240000, max_revision_cycles=0)
    grant = grant_for(session, task)
    if changed == "candidate":
        mid = task.contract["quality_manuscript_id"]
        manuscript = session.get(ResearchObject, mid)
        manuscript.title = "Changed after authorization"
    elif changed == "report":
        agent = research_tasks.agents_for(session, task.id)[1]
        agent.report = {**agent.report, "summary": "Changed review"}
    else:
        grant.expected_checkpoint_sha256 = "0" * 64
    session.commit()
    with pytest.raises(research_tasks.TaskError):
        research_runner.start(session, task, continuation=grant, acknowledge_live_execution=True)
    assert task.state == "completed"
    assert "previous_runs" not in task.ledger


def test_continuation_requires_live_ack_and_retains_failed_attempts(session, project):
    task = run(session, project, "fail", token_limit=240000)
    grant = grant_for(session, task, acknowledge_live_execution=False)
    with pytest.raises(research_tasks.TaskError, match="explicit acknowledgement"):
        research_runner.start(session, task, continuation=grant)
    grant = grant_for(session, task, token_limit=2000)
    continue_and_wait(session, task, grant)
    assert task.state == "limit_reached_partial"
    assert len(task.ledger["previous_runs"]) == 1
    continue_and_wait(session, task, grant_for(session, task))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert len(task.ledger["previous_runs"]) == 2


def test_missing_frozen_artifact_blocks_continuation(session, project, monkeypatch):
    from workbench import storage

    task = run(session, project, "fail", token_limit=240000)
    original = storage.read_bytes
    target = task.sources[0]["artifact"]

    def missing(ref):
        if ref == target:
            raise OSError("controlled missing artifact")
        return original(ref)

    monkeypatch.setattr(storage, "read_bytes", missing)
    with pytest.raises(research_tasks.TaskError, match="changed"):
        checkpoint(session, task)


def test_changed_work_after_grant_stops_before_any_worker(session, project, monkeypatch):
    from workbench.services import manuscript_quality_runner

    task = run(session, project, "fail", token_limit=240000)
    grant = grant_for(session, task)
    original = manuscript_quality_runner.execute

    def changed(runner):
        manuscript = runner.session.get(ResearchObject, runner.task.contract["quality_manuscript_id"])
        manuscript.title = "Changed while queued"
        runner.session.commit()
        return original(runner)

    monkeypatch.setattr(manuscript_quality_runner, "execute", changed)
    continue_and_wait(session, task, grant)
    assert task.state == "failed_partial"
    assert not task.ledger["allocations"]
    assert not any(e["event"] == "spawn_started" for e in task.ledger.get("call_trace", []))


def test_crash_after_accepted_revision_restores_responses_without_redrafting(session, project, monkeypatch):
    from workbench.services import revision_review

    original = revision_review.respond

    def interrupted(*args, **kwargs):
        raise research_runner.StopResearch("interrupted_partial", "accepted draft before response commit")

    monkeypatch.setattr(revision_review, "respond", interrupted)
    task = run(session, project, "revise", token_limit=240000, max_revision_cycles=1)
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    assert task.state == "interrupted_partial"
    assert len(campaign.body["drafts"]) == 2
    assert checkpoint(session, task)["stage"] == "audit"
    monkeypatch.setattr(revision_review, "respond", original)
    continue_and_wait(session, task, grant_for(session, task, max_revision_cycles=0))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert len(campaign.body["drafts"]) == 2
    assert not any(a["phase"] in {"draft", "revise"} for a in task.ledger["allocations"])
    assert quality.assessment(session, task.contract["quality_manuscript_id"])["agent_checks_complete"]
