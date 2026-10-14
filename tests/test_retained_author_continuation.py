"""One retained correction followed by one fresh review wave; isolated controlled workers."""

import copy

from test_manuscript_continuation import continue_and_wait, grant_for
from test_manuscript_quality import isolated as isolated
from test_manuscript_quality import run

from workbench.models import stable_hash
from workbench.services import manuscript_quality as quality
from workbench.services import research_tasks
from workbench.services.manuscript_continuation import checkpoint


def test_retained_return_continuation_repairs_once_without_rewriting_seed(session, project):
    task = run(session, project, "revise", token_limit=240000, max_revision_cycles=0)
    campaign = quality.campaign_for(session, task.contract["quality_manuscript_id"])
    parent = next(agent for agent in research_tasks.agents_for(session, task.id) if agent.role == "parent")
    raw = copy.deepcopy(campaign.body["drafts"][-1]["candidate"])
    raw["claims"][0]["source_ids"] = ["unfrozen-source"]
    digest = stable_hash(raw)
    parent.provenance = {**parent.provenance, "returned_outputs": [{
        "call_span_id": "retained-span", "operation": "revise",
        "result": raw, "result_sha256": digest, "status": "unaccepted_return",
    }]}
    parent.report = {**parent.report, "revise": raw}
    quality.update_campaign(campaign, rejected_drafts=[{
        "agent_id": parent.id, "operation": "revise", "attempt": 1,
        "span_id": "retained-span", "draft_sha256": digest, "issues": [{"code": "draft_evidence"}],
    }])
    task.ledger = {**task.ledger, "allocations": [*task.ledger["allocations"], {
        "agent_id": parent.id, "span_id": "retained-span", "phase": "revise",
        "operation_kind": "draft_correction", "reserved": 1000, "actual_tokens": 1000,
        "final_actual": True,
    }]}
    task.state = "failed_partial"
    session.commit()
    saved = checkpoint(session, task)
    assert saved["stage"] == "correct" and saved["recoverable_return_sha256"] == digest
    continue_and_wait(session, task, grant_for(session, task))
    assert task.state == "completed", task.ledger.get("stop_reason")
    assert len(campaign.body["drafts"]) == 2 and len(campaign.body["reports"]) == 8
    assert [row["phase"] for row in task.ledger["allocations"]].count("revise") == 1
    assert [row["phase"] for row in task.ledger["allocations"]].count("audit") == 4
    assert not any(row["phase"] == "draft" for row in task.ledger["allocations"])
    assert quality.assessment(session, task.contract["quality_manuscript_id"])["agent_checks_complete"]
