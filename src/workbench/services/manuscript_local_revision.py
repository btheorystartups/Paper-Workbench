"""Explicit local candidate admission; no worker returns or review approval."""
from copy import deepcopy

from ..models import ResearchAgent, ResearchObject, stable_hash
from ..research_contract import ContractModel, Field, Key, ManuscriptDraft, Sha256
from . import manuscript_quality as quality
from . import research_tasks, revision_review


class LocalCandidateGrant(ContractModel):
    expected_checkpoint_sha256: Sha256
    expected_candidate_sha256: Sha256
    expected_raw_candidate_sha256: Sha256
    candidate_sha256: Sha256
    candidate: ManuscriptDraft
    request_id: Key
    prepared_by_thread_id: Key
    authorization_reason: str = Field(min_length=1, max_length=2000)
    acknowledge_local_revision: bool = False
    controller_completion_comments: dict[Key, Sha256] = Field(default_factory=dict, max_length=16)


def retained_local_candidate(parent, draft, previous):
    receipt = draft.get("local_revision")
    return bool(receipt and previous and receipt in parent.provenance.get(
        "local_candidate_admissions", []) and receipt.get("version") == 1
        and receipt.get("acknowledge_local_revision") is True
        and receipt.get("review_only") is True
        and receipt.get("report_corrections_limit") == 1
        and receipt.get("candidate_sha256") == draft["candidate_sha256"]
        and receipt.get("raw_candidate_sha256") == stable_hash(draft["candidate"])
        and receipt.get("base_candidate_sha256") == previous["candidate_sha256"]
        and receipt.get("base_raw_candidate_sha256") == stable_hash(previous["candidate"])
        and receipt.get("prepared_by_thread_id") and receipt.get("authorization_reason"))


def admit(session, task, grant, *, actor):
    """Hash-bound, idempotent and atomic local revision of a stopped manuscript."""
    from .manuscript_continuation import checkpoint
    from .manuscript_quality_runner import _prior

    if task.state not in research_tasks.TERMINAL:
        raise research_tasks.TaskError("local admission requires a stopped manuscript")
    if not grant.acknowledge_local_revision:
        raise research_tasks.TaskError("explicit local-revision acknowledgement required")
    campaign = quality.campaign_for(session, task.contract.get("quality_manuscript_id"))
    if not campaign:
        raise research_tasks.TaskError("preserved manuscript campaign required")
    request_hash = stable_hash(grant.model_dump())
    existing = next((d for d in campaign.body["drafts"]
        if d.get("local_revision", {}).get("request_id") == grant.request_id), None)
    if existing:
        receipt = existing["local_revision"]
        if receipt["request_sha256"] != request_hash:
            raise research_tasks.TaskError("local admission request ID reused with different content")
        parent = session.get(ResearchAgent, existing["author_id"])
        index = campaign.body["drafts"].index(existing)
        if not parent or not retained_local_candidate(parent, existing,
                campaign.body["drafts"][index - 1] if index else None):
            raise research_tasks.TaskError("retained local admission receipt changed")
        return {"receipt": receipt, "idempotent": True}
    saved = checkpoint(session, task)
    if saved["checkpoint_sha256"] != grant.expected_checkpoint_sha256:
        raise research_tasks.TaskError("checkpoint changed; local admission denied")
    previous = campaign.body["drafts"][-1]
    if (previous["candidate_sha256"] != grant.expected_candidate_sha256
            or stable_hash(previous["candidate"]) != grant.expected_raw_candidate_sha256):
        raise research_tasks.TaskError("base candidate changed; local admission denied")
    raw = grant.candidate.model_dump()
    if stable_hash(raw) != grant.candidate_sha256 or raw == previous["candidate"]:
        raise research_tasks.TaskError("local candidate hash differs or candidate is unchanged")
    prior = _prior(session, campaign)
    expected_ids = [c["id"] for c in prior]
    by_id = {c["id"]: {k: v for k, v in c.items()
             if k not in {"round_id", "reviewed_candidate_sha256", "response"}} for c in prior}
    for cid, expected in grant.controller_completion_comments.items():
        comment = by_id.get(cid, {})
        words = comment.get("objection", "").casefold()
        if (stable_hash(comment) != expected or not all(w in words for w in ("four", "review"))
                or not any(w in words for w in ("candidate", "controller"))):
            raise research_tasks.TaskError("controller comment must bind a four-review criterion")
    quality.validate_draft(task, campaign, raw, expected_response_ids=expected_ids)
    manuscript = session.get(ResearchObject, saved["manuscript_id"])
    parent = session.get(ResearchAgent, saved["author_id"])
    research_tasks.lock_revision(session, task)
    try:
        admitted, digest = quality.apply_draft(session, task, manuscript, campaign, raw,
            parent.id, expected_response_ids=expected_ids, commit=False)
        receipt = {"version": 1, "origin": "authorized_local_revision", "request_id": grant.request_id,
            "request_sha256": request_hash, "base_candidate_sha256": previous["candidate_sha256"],
            "base_raw_candidate_sha256": stable_hash(previous["candidate"]),
            "candidate_sha256": digest, "raw_candidate_sha256": stable_hash(admitted),
            "prepared_by_thread_id": grant.prepared_by_thread_id,
            "authorization_reason": grant.authorization_reason, "actor": str(actor),
            "acknowledge_local_revision": True, "review_only": True,
            "report_corrections_limit": 1, "worker_calls": 0,
            "controller_completion_comments": dict(grant.controller_completion_comments)}
        drafts = deepcopy(campaign.body["drafts"])
        drafts[-1]["local_revision"] = receipt
        quality.update_campaign(campaign, drafts=drafts)
        parent.provenance = {**parent.provenance, "local_candidate_admissions": [
            *parent.provenance.get("local_candidate_admissions", []), receipt]}
        responses = {r["comment_id"]: r for r in admitted["responses"]}
        for comment in prior:
            response = responses[comment["id"]]
            revision_review.respond(session, comment["round_id"], comment_id=comment["id"],
                author=parent.id, response=response["response"], changes=response["changes"])
        task.ledger = {**task.ledger, "local_candidate_admissions": [
            *task.ledger.get("local_candidate_admissions", []), receipt],
            "parent_integration_received": False, "child_handoff_received": False,
            "live_handoff_verified": False}
        research_tasks.audit(session, task, "admit_local_manuscript_candidate", receipt)
        session.commit()
        if revision_review.candidate_hash(session, manuscript.id) != digest:
            raise research_tasks.TaskError("native candidate binding changed after local admission")
        return {"receipt": receipt, "idempotent": False, "checkpoint": checkpoint(session, task)}
    except Exception:
        session.rollback()
        raise


def verify_controller_completion(session, task, campaign, digest):
    """Verify only explicitly classified four-review facts after scientific checks.

    Raw specialist reports and their judgments remain unchanged. These new native
    verification events are separate controller evidence, never author approval.
    """
    from ..research_contract import SPECIALIST_ROLES

    selected = campaign.body["drafts"][-1].get("local_revision", {}).get(
        "controller_completion_comments", {})
    if not selected:
        return []
    records = [r for r in campaign.body["reports"] if r["candidate_sha256"] == digest]
    if (len(records) != 4 or {r["role"] for r in records} != set(SPECIALIST_ROLES)
            or any(r["blockers"] for r in records)):
        return []
    # This native check covers identity, thread separation, originals, exact source
    # and candidate bindings, policy, coverage and report integrity. Only the
    # incomplete workflow facts being verified here may remain.
    state = quality.assessment(session, campaign.body["manuscript_id"])
    allowed = {"specialist campaign has not completed its checks",
               "unresolved or stale specialist objection",
               "manuscript production task has not completed its final handoff"}
    if set(state["blockers"]) - allowed:
        return []
    pending = []
    for rid in campaign.body["rounds"]:
        review = session.get(ResearchObject, rid)
        dispositions = revision_review.dispositions(session, review)
        for comment in review.body["comments"]:
            cid = comment["id"]
            if dispositions[cid] in {"resolved", "justified_rejection"}:
                continue
            if cid not in selected or selected[cid] != stable_hash(comment):
                return []  # Never close a scientific, changed or unclassified criterion.
            response = next(e for e in reversed(review.body["events"])
                            if e["kind"] == "response" and e["comment_id"] == cid)
            pending.append((rid, comment, response))
    evidence = {"policy": "controller-four-current-reviews-v1", "candidate_sha256": digest,
                "reports": [{"role": r["role"], "agent_id": r["agent_id"],
                    "report_sha256": r["report_sha256"], "packet_sha256": r["packet"]["packet_sha256"]}
                    for r in records], "scientific_comments_independently_dispositioned": True,
                "human_publication_approval": False}
    verified = []
    for rid, comment, response in pending:
        revision_review.verify(session, rid, comment_id=comment["id"],
            verifier="controller-review-completion", response_hash=stable_hash(response),
            expected_candidate_hash=digest, expected_comment_hash=stable_hash(comment),
            criterion_met=True, regression_passed=True, evidence=str(evidence), disposition="resolved")
        verified.append(comment["id"])
    if verified:
        research_tasks.audit(session, task, "verify_controller_review_completion",
                             {**evidence, "comment_ids": verified})
    return verified
