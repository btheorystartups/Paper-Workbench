"""Read-only readiness rubric: scoped agent evidence and human decisions are separate.

Use the existing quality/evidence and publication-package gates. This report must
never be called from those gates (publication audits already call quality.assessment).
"""

from sqlalchemy import select

from ..models import (
    Claim,
    PublicationPackage,
    ResearchAgent,
    ResearchObject,
    ResearchTask,
    Source,
    stable_hash,
)
from ..research_contract import SPECIALIST_ROLES
from . import audits, authoring, publication_packages
from . import manuscript_quality as quality


def report(session, manuscript_id):
    state = quality.assessment(session, manuscript_id)
    manuscript = session.get(ResearchObject, manuscript_id)
    campaign = quality.campaign_for(session, manuscript_id)
    latest = campaign.body["reports"][-len(SPECIALIST_ROLES):] if campaign else []
    reviews = []
    for role in SPECIALIST_ROLES:
        records = [r for r in latest if r["role"] == role]
        row = {"role": role, "status": "missing", "report_sha256": None,
               "packet_sha256": None, "agent_id": None, "claim_assessments": [], "challenges": []}
        if len(records) == 1:
            record = records[0]
            agent = session.get(ResearchAgent, record["agent_id"])
            row.update(
                status="unconfirmed",
                report_sha256=record["report_sha256"],
                packet_sha256=record.get("packet", {}).get("packet_sha256"),
                agent_id=record["agent_id"],
            )
            if agent and stable_hash(agent.report) == record["report_sha256"]:
                row["challenges"] = agent.report.get("adversarial_checks", [])
                row["claim_assessments"] = agent.report.get("assessments", [])
                row["summary"] = agent.report.get("summary", "")
                row["contribution_comparison"] = agent.report.get("contribution_comparison", "")
                # The aggregate gate checks identity, frozen evidence, current candidate,
                # independence and revision closure. Do not show stale local passes as green.
                if state["agent_checks_complete"]:
                    row["status"] = "passed_within_scope"
        reviews.append(row)
    sections = authoring.manuscript_sections(session, manuscript_id)
    pending_text = [o.id for o in [manuscript, *sections] if o.ai_suggested and not o.accepted_by_user]
    claim_ids = manuscript.body.get("quality_claim_map", {}).values()
    pending_claims = [c.id for cid in claim_ids if (c := session.get(Claim, cid))
                      and not c.deleted_at and c.support in {"unsupported", "verification_required"}]
    source_ids = manuscript.body.get("quality_source_excerpt_map", {}).keys()
    pending_sources = [s.id for sid in source_ids if (s := session.get(Source, sid))
                       and not s.deleted_at and not s.human_verified]
    findings = audits.audit_manuscript(session, manuscript_id)
    packages = []
    for package in session.scalars(select(PublicationPackage).where(
        PublicationPackage.manuscript_id == manuscript_id, PublicationPackage.deleted_at.is_(None)
    )):
        readiness = publication_packages.readiness(session, package.id)
        packages.append({"id": package.id, "state": package.state, **readiness})
    approved = any(p["state"] == "approved" and p["ready"]
                   and p["stored_basis_hash"] == p["current_basis_hash"] for p in packages)
    handoff = bool(state.get("draft_produced") and not state["blockers"])
    capacity = None
    if campaign:
        task = session.get(ResearchTask, campaign.body["quality_task_id"])
        for stage, key in (("author_time_admission", "author_time_plans"),
                           ("revision_admission", "revision_budget_plans"),
                           ("before_first_review", "initial_capacity_plans")):
            plans = campaign.body.get(key, [])
            if plans and (key != "author_time_plans" or plans[-1]["status"] == "insufficient_time"):
                forecast = plans[-1]
                capacity = {
                    "stage": stage,
                    "forecast": forecast,
                    "basis_current": bool(
                        task
                        and forecast.get("candidate_sha256") == state.get("candidate_sha256")
                        and forecast.get("token_limit", task.contract["token_limit"])
                        == task.contract["token_limit"]
                        and forecast.get("time_limit_seconds") == task.contract["time_limit_seconds"]
                    ),
                    "notice": "Conditional planning estimate, not a completion guarantee; "
                    "future candidate, objections, actual usage and wall time remain uncertain.",
                }
                break
    return {
        "policy": quality.POLICY,
        "candidate_sha256": state.get("candidate_sha256"),
        "limitations": campaign.body["drafts"][-1]["candidate"]["limitations"]
        if campaign and campaign.body.get("drafts")
        else [],
        "agent_checks_complete": state["agent_checks_complete"],
        "length_check": state.get("length_check"),
        "task_requirements": state.get("task_requirements"),
        "release_review_flags": state.get("release_review_flags", []),
        "diagnostic_handoff_complete": handoff,
        "capacity": capacity,
        "review_dimensions": reviews,
        "agent_blockers": state["blockers"],
        "human_review": {
            "pending_text_ids": pending_text,
            "pending_claim_ids": pending_claims,
            "pending_source_ids": pending_sources,
        },
        "publication_audit": findings,
        "publication_packages": packages,
        "human_publication_approval": approved,
        "release_eligible": approved,
        "status": "human_approved_current_package"
        if approved
        else ("agent_checks_complete_human_review_pending" if handoff else "agent_review_incomplete"),
        "scope_notice": "Agent passes cover supplied source passages, search scope and executed receipts "
        "for this candidate only. They do not certify all source content, universal novelty "
        "or publication quality. Human verification, text acceptance, authorship, declarations "
        "and current package approval remain separate decisions. No submission probability is assigned.",
    }
