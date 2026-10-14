"""Restart, replay, peer isolation and request identity against isolated stores."""

import copy
import threading

import pytest
from test_manuscript_continuation import continue_and_wait, grant_for
from test_manuscript_quality import isolated as isolated
from test_manuscript_quality import run, task_for

from workbench.models import utcnow
from workbench.services import manuscript_quality as quality
from workbench.services import research_runner, research_tasks
from workbench.services.research_runner import Runner, StopResearch


def test_first_reviewer_failure_saves_peers_and_continuation_reuses_them(session, project):
    task = run(session, project, "stream_failure", token_limit=240000)
    assert task.state == "failed_partial"
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    reports = copy.deepcopy(campaign.body["reports"])
    assert {r["role"] for r in reports} == {"source_citation", "literature_contribution"}
    continue_and_wait(session, task, grant_for(session, task))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert campaign.body["reports"][:2] == reports
    assert len(campaign.body["reports"]) == 4
    assert len([a for a in task.ledger["allocations"] if a["phase"] == "audit"]) == 2


def test_lost_start_response_can_be_retrieved_without_second_run(session, project):
    task = run(session, project, "fail", token_limit=240000)
    grant = grant_for(session, task, request_id="request-one")
    first = research_runner.start(session, task, continuation=grant, acknowledge_live_execution=True)
    session.expire_all()
    second = research_runner.start(session, task, continuation=grant, acknowledge_live_execution=True)
    assert second["run_id"] == first["run_id"]
    changed = grant.model_copy(update={"token_limit": grant.token_limit - 1})
    with pytest.raises(research_tasks.TaskError, match="different continuation"):
        research_runner.start(session, task, continuation=changed, acknowledge_live_execution=True)
    research_runner.shutdown()


def test_thread_start_failure_preserves_authority_without_dispatch(session, project, monkeypatch):
    task = task_for(session, project)
    monkeypatch.setattr(threading.Thread, "start",
                        lambda self: (_ for _ in ()).throw(RuntimeError("fixture")))
    with pytest.raises(research_tasks.TaskError, match="could not start"):
        research_runner.start(session, task, acknowledge_live_execution=True)
    assert task.state == "failed_partial" and task.ledger["allocations"] == []
    assert task.ledger["authorization"]["token_ceiling"] == task.contract["token_limit"]
    assert task.id not in research_runner._jobs


def test_restarted_owner_marks_orphan_without_waiting_or_redispatch(session, project):
    task = task_for(session, project)
    task.state, task.started_at = "researching", utcnow()
    task.ledger = {"owner_id": "previous-controller", "owner_pid": 2147483647,
                   "run_id": "old-run", "allocations": []}
    session.commit()
    research_runner.recover_expired(session, task)
    assert task.state == "interrupted_partial" and task.ledger["allocations"] == []


def test_stale_runner_cannot_poll_or_finish_a_new_run(session, project):
    task = task_for(session, project)
    task.state, task.started_at = "researching", utcnow()
    task.ledger = {"run_id": "old-run", "allocations": []}
    session.commit()
    runner = Runner(session, task, threading.Event(), None)
    task.ledger = {"run_id": "new-run", "allocations": []}
    session.commit()
    with pytest.raises(StopResearch, match="stale runner"):
        runner.event(None, None, None, "draft")
    runner.finish()
    assert task.state == "researching" and task.ledger["run_id"] == "new-run"


def test_replaying_completed_wave_does_not_duplicate_manifests_or_comments(session, project):
    from workbench.services.manuscript_quality_runner import _audit_wave

    task = run(session, project, "revise", token_limit=240000, max_revision_cycles=0)
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    rounds, manifests = copy.deepcopy(campaign.body["rounds"]), copy.deepcopy(campaign.body["packets"])
    task.state = "researching"
    session.commit()
    runner = Runner(session, task, threading.Event(), None)
    runner.agents = research_tasks.agents_for(session, task.id)
    parent = next(a for a in runner.agents if a.role == "parent")
    manuscript = session.get(quality.ResearchObject, task.contract["quality_manuscript_id"])
    assert not _audit_wave(runner, parent, manuscript, campaign,
                           campaign.body["drafts"][-1]["candidate_sha256"], 0)
    assert campaign.body["rounds"] == rounds and campaign.body["packets"] == manifests
