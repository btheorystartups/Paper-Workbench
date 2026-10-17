"""Explicit new grants for saved manuscript work; never restart a paid run automatically."""

import hashlib
import json
from copy import deepcopy

from .. import storage
from ..models import ResearchAgent, ResearchObject, stable_hash
from ..providers.research_model_policy import ModelSelection
from ..research_contract import (
    SPECIALIST_ROLES,
    ContractModel,
    Field,
    Key,
    ManuscriptClaim,
    ManuscriptDraft,
    ManuscriptSection,
    Sha256,
    SpecialistReport,
    SpecialistRole,
)
from . import manuscript_quality as quality
from . import research_tasks, revision_review
from .research_recovery import (
    AuthorizationGrant,
    accounting,
    continuation_authorization,
    normalization_authority,
    normalize_review_report,
)


class ContinuationGrant(ContractModel):
    expected_checkpoint_sha256: Sha256
    token_limit: int = Field(ge=2000, le=1500000, strict=True)
    time_limit_seconds: int = Field(ge=10, le=7200, strict=True)
    max_revision_cycles: int = Field(ge=0, le=2, strict=True)
    acknowledge_live_execution: bool = False
    authorization: AuthorizationGrant | None = None
    request_id: str | None = Field(default=None, min_length=1, max_length=100)
    retry_uncertain_operations: bool = False
    normalization_approvals: dict[Sha256, list[Key]] = Field(default_factory=dict, max_length=4)
    specialist_policy: dict[SpecialistRole, ModelSelection] | None = None
    max_report_corrections: int = Field(default=1, ge=0, le=4, strict=True)


def recoverable_return(parent, campaign, task):
    rejected = campaign.body.get("rejected_drafts", [])
    returned = parent.provenance.get("returned_outputs", [])
    retained = list(returned)
    for checkpoint_row in parent.provenance.get("output_checkpoints", []):
        if (checkpoint_row.get("operation") != "revise" or not checkpoint_row.get("complete_message")
                or not checkpoint_row.get("identity_verified")
                or stable_hash(checkpoint_row.get("text")) != checkpoint_row.get("text_sha256")):
            continue
        try:
            raw = json.loads(checkpoint_row["text"])
        except (ValueError, TypeError):
            continue
        retained.append({**checkpoint_row, "result": raw, "result_sha256": stable_hash(raw)})
    if not retained:
        return None
    allocations = [*task.ledger.get("allocations", []),
                   *(row for run in reversed(task.ledger.get("previous_runs", []))
                     for row in run["ledger"].get("allocations", []))]
    by_span = {output["call_span_id"]: output for output in retained}
    for allocation in allocations:
        output = by_span.get(allocation.get("span_id"), {})
        raw = output.get("result")
        legacy_bound = any(last.get("operation") == "revise" and last.get("agent_id") == parent.id
                           and last.get("span_id") == output.get("call_span_id")
                           and last.get("draft_sha256") == output.get("result_sha256") for last in rejected)
        if (output.get("operation") != "revise" or allocation.get("agent_id") != parent.id
                or not isinstance(raw, dict) or stable_hash(raw) != output.get("result_sha256")
                or not (output.get("identity_verified") is True
                        or allocation.get("final_actual") and legacy_bound)
                or raw == campaign.body.get("drafts", [{}])[-1].get("candidate")):
            continue
        try:
            if not raw["sections"] or not raw["claims"] or not isinstance(raw["responses"], list):
                continue
            for row in raw["sections"]:
                ManuscriptSection.model_validate(row)
            for row in raw["claims"]:
                ManuscriptClaim.model_validate(row)
        except (ValueError, KeyError, TypeError):
            continue
        return output
    return None


def checkpoint(session, task, *, active=False):
    """Validate saved evidence before advertising or spending a continuation grant."""
    if task.state not in research_tasks.TERMINAL and not active:
        raise research_tasks.TaskError("only a stopped manuscript can continue")
    mid = task.contract.get("quality_manuscript_id")
    manuscript = session.get(ResearchObject, mid) if mid else None
    campaign = quality.campaign_for(session, mid) if mid else None
    if (not manuscript or manuscript.deleted_at or not campaign or campaign.deleted_at
            or campaign.body.get("quality_task_id") != task.id or not campaign.body.get("drafts")):
        raise research_tasks.TaskError("continuation requires a preserved accepted manuscript candidate")
    draft = campaign.body["drafts"][-1]
    if revision_review.candidate_hash(session, mid) != draft["candidate_sha256"]:
        raise research_tasks.TaskError("saved candidate or its evidence changed; continuation denied")
    parent = session.get(ResearchAgent, draft["author_id"])
    if not parent or parent.deleted_at or parent.task_id != task.id or parent.role != "parent":
        raise research_tasks.TaskError("saved author provenance is unavailable")
    original = parent.report.get("revise", parent.report.get("draft"))
    # The latest accepted draft may precede a failed revision attempt.
    originals = [original, *(row.get("draft") for row in parent.provenance.get("draft_attempts", []))]
    accepted = []
    for raw in originals:
        try:
            accepted.append(ManuscriptDraft.model_validate(raw).model_dump())
        except ValueError:
            continue
    from .manuscript_local_revision import retained_local_candidate
    previous = campaign.body["drafts"][-2] if len(campaign.body["drafts"]) > 1 else None
    local = retained_local_candidate(parent, draft, previous)
    if draft.get("local_revision") and not local:
        raise research_tasks.TaskError("saved local admission receipt changed")
    if draft["candidate"] not in accepted and not local:
        raise research_tasks.TaskError("saved candidate differs from its author's preserved return")
    try:
        for source in task.sources:
            if source.get("source_id"):
                original = storage.read_bytes(source["artifact"])
                extracted = storage.read_bytes(source["extracted_artifact"])
                if (hashlib.sha256(original).hexdigest() != source["sha256"]
                        or hashlib.sha256(extracted).hexdigest() != source["full_extracted_sha256"]):
                    raise ValueError("source artifact changed")
        receipts = [*campaign.body["search_receipts"], *campaign.body["verification_receipts"]]
        frozen = [json.loads(storage.read_bytes(ref)) for ref in manuscript.body.get("quality_evidence", [])]
        if frozen != receipts:
            raise ValueError("receipts changed")
        for receipt in campaign.body["verification_receipts"]:
            reproduction = receipt.get("reproduction")
            if receipt.get("executed_by") == "workbench_allowlisted_routine":
                payload = storage.read_bytes(reproduction["implementation_artifact"])
                if (hashlib.sha256(payload).hexdigest() != receipt["implementation_sha256"]
                        or payload.decode("utf-8") != reproduction["implementation_text"]):
                    raise ValueError("verifier changed")
    except (OSError, ValueError, KeyError, TypeError, storage.ArtifactStorageError) as exc:
        raise research_tasks.TaskError("saved source or receipt evidence is unavailable or changed") from exc
    reports = [r for r in campaign.body["reports"]
               if r["candidate_sha256"] == draft["candidate_sha256"]
               and r["iteration"] == len(campaign.body["drafts"]) - 1]
    if len({r["role"] for r in reports}) != len(reports):
        raise research_tasks.TaskError("saved wave has duplicate specialist roles")
    identities = set()
    authors = [session.get(ResearchAgent, row["author_id"]) for row in campaign.body["drafts"]]
    author_threads = set().union(*(quality.author_model_threads(a) for a in authors))
    for record in reports:
        agent = session.get(ResearchAgent, record["agent_id"])
        if (not agent or agent.deleted_at or agent.task_id != task.id
                or stable_hash(agent.report) != record["report_sha256"]
                or agent.assignment.get("specialist_role") != record["role"]
                or agent.assignment.get("candidate_sha256") != draft["candidate_sha256"]
                or agent.assignment.get("packet_sha256") != record["packet"]["packet_sha256"]):
            raise research_tasks.TaskError("saved specialist report changed")
        model = agent.provenance.get("specialist_report_model", {})
        identity = model.get("codex_thread_id", agent.id)
        requested = agent.provenance.get("requested_model_policy")
        if (identity in identities or identity in author_threads
                or agent.parent_id not in {a.id for a in authors if a}
                or requested and (requested.get("role") != record["role"] or any(
                    requested.get(k) != model.get(k) for k in ("model", "reasoning_effort")))):
            raise research_tasks.TaskError("saved specialist independence or model policy changed")
        identities.add(identity)
        try:
            quality.validate_report(agent.report, record["packet"])
            attempts = agent.provenance.get("report_attempts", [])
            if attempts:
                original = attempts[-1]
                derived, normalization = normalize_review_report(
                    original["report"], normalization_authority(task))
                if (stable_hash(original["report"]) != original["report_sha256"]
                        or original["packet_sha256"] != record["packet"]["packet_sha256"]
                        or SpecialistReport.model_validate(derived).model_dump() != agent.report
                        or normalization and (record.get("normalization") != normalization
                            or agent.provenance.get("review_normalization") != normalization)):
                    raise ValueError("original reviewer return changed")
            expected = quality.packet_for(task, campaign, draft["candidate_sha256"], record["role"], [])
            for key in ("candidate", "task_specification", "task_requirements", "length_check",
                        "source_manifest", "admitted_original_evidence", "verification_receipts",
                        "search_receipts"):
                if record["packet"].get(key) != expected[key]:
                    raise ValueError("review evidence changed")
        except (ValueError, KeyError, TypeError) as exc:
            raise research_tasks.TaskError("saved specialist report is invalid") from exc
    status = campaign.body["status"]
    if (status == "agent_checks_complete"
            and not quality.assessment(session, mid).get("specialist_checks_complete", False)):
        raise research_tasks.TaskError("saved specialist completion no longer passes its checks")
    stage = {"agent_checks_complete": "integrate", "needs_revision": "revise"}.get(status, "audit")
    recovery = recoverable_return(parent, campaign, task) if stage == "revise" else None
    if recovery:
        stage = "correct"
    if (task.ledger.get("parent_integration_received") and task.ledger.get("child_handoff_received")
            and status == "agent_checks_complete"):
        raise research_tasks.TaskError("manuscript workflow already completed")
    agents = research_tasks.agents_for(session, task.id)
    rounds = [session.get(ResearchObject, rid) for rid in campaign.body["rounds"]]
    if any(not row or row.deleted_at for row in rounds):
        raise research_tasks.TaskError("saved review round is unavailable")
    saved_work = {
        "requirements": quality.task_requirements(task), "instructions": task.contract["instructions"],
        "sources": task.sources, "campaign": campaign.body,
        "candidate_sha256": draft["candidate_sha256"],
        "agents": [{"id": a.id, "parent_id": a.parent_id, "state": a.state,
                    "assignment": a.assignment, "report": a.report, "provenance": a.provenance}
                   for a in agents],
        "rounds": [row.body for row in rounds],
    }
    work_digest = stable_hash(saved_work)
    digest = stable_hash({"saved_work": work_digest, "revision": task.revision,
                          "state": task.state, "contract": task.contract, "ledger": task.ledger})
    return {"checkpoint_sha256": digest, "candidate_sha256": draft["candidate_sha256"],
            "aggregate_accounting": accounting(task), "authorization": task.ledger.get("authorization"),
            "saved_work_sha256": work_digest,
            "stage": stage, "reusable_review_roles": sorted({r["role"] for r in reports}),
            "author_id": parent.id, "manuscript_id": mid, "campaign_id": campaign.id,
            "recoverable_return_sha256": recovery["result_sha256"] if recovery else None}


def prepare(session, task, grant):
    """Return the atomic transition values without changing the stopped task."""
    saved = checkpoint(session, task)
    campaign = quality.campaign_for(session, saved["manuscript_id"])
    if campaign.body["drafts"][-1].get("local_revision") and grant.max_revision_cycles:
        raise research_tasks.TaskError("local admission continuation is review-only")
    if campaign.body["drafts"][-1].get("local_revision") and grant.specialist_policy is None:
        raise research_tasks.TaskError("local review requires explicit operator model policy")
    if grant.specialist_policy is not None and (
            not campaign.body["drafts"][-1].get("local_revision")
            or set(grant.specialist_policy) != set(SPECIALIST_ROLES)):
        raise research_tasks.TaskError("explicit policy requires all four local-review roles")
    if saved["checkpoint_sha256"] != grant.expected_checkpoint_sha256:
        raise research_tasks.TaskError("checkpoint changed; inspect it again before authorizing continuation")
    if saved["stage"] in {"revise", "correct"} and grant.max_revision_cycles == 0:
        raise research_tasks.TaskError("this checkpoint needs at least one authorized revision")
    if grant.normalization_approvals and (saved["stage"] != "audit" or grant.max_revision_cycles != 0):
        raise research_tasks.TaskError(
            "normalization recovery is restricted to the saved audit without revision")
    contract = {**task.contract, "token_limit": grant.token_limit,
                "time_limit_seconds": grant.time_limit_seconds,
                "handoff_time_reserve_seconds": max(2, grant.time_limit_seconds // 10),
                "max_revision_cycles": grant.max_revision_cycles}
    ledger = deepcopy(task.ledger)
    history = ledger.pop("previous_runs", [])
    history.append({"contract": deepcopy(task.contract), "ledger": ledger,
                    "synthesis": deepcopy(task.synthesis), "state": task.state,
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                    "agents": [{"id": a.id, "state": a.state, "assignment": deepcopy(a.assignment),
                                "report": deepcopy(a.report), "provenance": deepcopy(a.provenance)}
                               for a in research_tasks.agents_for(session, task.id)]})
    authority = continuation_authorization(task, grant)
    return contract, {"previous_runs": history, "continuation": {
        **saved, "retry_uncertain_operations": grant.retry_uncertain_operations,
        "normalization_approvals": grant.normalization_approvals,
        "specialist_policy": {role: selection.model_dump()
                              for role, selection in (grant.specialist_policy or {}).items()},
        "max_report_corrections": grant.max_report_corrections}, "authorization": authority}
