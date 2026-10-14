"""Audited finalization of the pinned worker's completed-turn validation failure."""

from copy import deepcopy

from ..models import ResearchAgent
from . import manuscript_continuation, research_tasks


def reconcile(session, task, expected_checkpoint_sha256):
    saved = manuscript_continuation.checkpoint(session, task)
    if saved["checkpoint_sha256"] != expected_checkpoint_sha256:
        raise research_tasks.TaskError("checkpoint changed; usage reconciliation denied")
    allocations = deepcopy(task.ledger.get("allocations", []))
    changed = []
    for row in allocations:
        if row.get("final_actual"):
            continue
        agent = session.get(ResearchAgent, row["agent_id"])
        provenance = agent.provenance if agent else {}
        span = row.get("span_id")
        stream = next((item for item in provenance.get("codex_streams", [])
                       if item.get("call_span_id") == span), {})
        turn = provenance.get("active_model_turn", {})
        failed = next((event for event in task.ledger.get("call_trace", [])
                       if event.get("event") == "worker_failed"
                       and event.get("span_id") == span and event.get("agent_id") == row["agent_id"]), {})
        # In this pinned worker report_validation is reached only after a successful
        # turn/completed; its normal receipt uses this exact last usage counter.
        verified = (
            task.state == "failed_partial"
            and row.get("phase") in {"draft", "revise"}
            and provenance.get("capabilities", {}).get("executor") == "Codex app-server 0.160.1"
            and provenance.get("worker_failure_stage") == "report_validation"
            and provenance.get("worker_failure_class") == "ValidationError"
            and failed.get("failure_stage") == "report_validation"
            and failed.get("failure_class") == "ValidationError"
            and stream.get("finished") is True
            and type(stream.get("completed_text_characters")) is int
            and 0 < stream["completed_text_characters"] == stream.get("characters") <= 400000
            and all(turn.get(key) and stream.get(key) == turn[key]
                    for key in ("codex_thread_id", "codex_turn_id"))
            and row.get("usage_kind") == "actual"
            and row.get("usage_source") == "Codex thread/tokenUsage/updated"
            and type(row.get("actual_tokens")) is int
            and row["actual_tokens"] == row.get("reported_tokens")
            and row["actual_tokens"] >= 0
        )
        if not verified:
            raise research_tasks.TaskError(
                "completed turn and actual usage are not verifiable; reserve retained")
        row["final_actual"] = True
        row["released_tokens"] = max(0, row["reserved"] - row["actual_tokens"])
        row["final_usage_basis"] = "pinned completed-turn report-validation failure"
        changed.append({"span_id": span, "actual_tokens": row["actual_tokens"],
                        "released_tokens": row["released_tokens"]})
    if not changed:
        return {"changed": False, "charged_tokens": task.ledger["charged_tokens"]}
    before = task.ledger["charged_tokens"]
    actual = sum(row.get("actual_tokens") or 0 for row in allocations)
    estimated = sum(max(0, row["reserved"] - (row.get("actual_tokens") or 0))
                    for row in allocations if not row.get("final_actual"))
    task.ledger = {
        **task.ledger, "allocations": allocations, "actual_tokens": actual,
        "estimated_tokens": estimated, "charged_tokens": actual + estimated,
        "usage_complete": all(row.get("final_actual") for row in allocations),
        "completed_usage_reconciliations": [
            *task.ledger.get("completed_usage_reconciliations", []),
            {"checkpoint_sha256": expected_checkpoint_sha256, "before_charged": before,
             "after_charged": actual + estimated, "receipts": changed},
        ],
    }
    research_tasks.audit(session, task, "reconcile_completed_validation_usage", {
        "before_charged": before, "after_charged": actual + estimated, "receipts": changed,
    })
    session.commit()
    return {"changed": True, "charged_tokens": actual + estimated, "receipts": changed}
