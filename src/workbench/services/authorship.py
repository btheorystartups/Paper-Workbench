"""Review-gated CRediT contribution capture and authorship-order assistance.

CRediT describes who did what; it does not determine authorship eligibility or order.
Assignments therefore begin as proposals, reviewed states stay explicit, and an order is
written to a manuscript only after human approval against an unchanged contribution
snapshot. The built-in ordering heuristic is deterministic and advisory; it never calls a
provider and never silently changes an approved order.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import (
    AuthorshipProposal,
    Contributor,
    CreditAssignment,
    Project,
    ResearchObject,
    stable_hash,
    utcnow,
)
from ..vocab import ObjectKind
from . import research

CREDIT_ROLES = {
    "conceptualization": "Conceptualization",
    "data_curation": "Data curation",
    "formal_analysis": "Formal analysis",
    "funding_acquisition": "Funding acquisition",
    "investigation": "Investigation",
    "methodology": "Methodology",
    "project_administration": "Project administration",
    "resources": "Resources",
    "software": "Software",
    "supervision": "Supervision",
    "validation": "Validation",
    "visualization": "Visualization",
    "writing_original_draft": "Writing – original draft",
    "writing_review_editing": "Writing – review & editing",
}
CONTRIBUTION_DEGREES = {"lead", "equal", "supporting"}
ASSIGNMENT_STATES = {"proposed", "confirmed", "disputed", "declined"}
ASSIGNMENT_REVIEW_STATES = ASSIGNMENT_STATES - {"proposed"}
ASSIGNMENT_ORIGINS = {"human", "assistant"}
PROPOSAL_STATES = {"proposed", "approved", "rejected", "superseded"}
AUTHORSHIP_DISCLAIMER = (
    "CRediT records contribution roles; it does not determine authorship eligibility or "
    "author order. Any order shown here is an advisory discussion draft until explicitly "
    "approved by a human."
)

_ORCID_RE = re.compile(r"^(\d{4})-(\d{4})-(\d{4})-(\d{3}[\dX])$")


def _manuscript(session: Session, manuscript_id: str) -> ResearchObject:
    manuscript = session.get(ResearchObject, manuscript_id)
    if (
        manuscript is None
        or manuscript.deleted_at is not None
        or manuscript.kind != ObjectKind.MANUSCRIPT
    ):
        raise research.IntegrityError("manuscript not found")
    return manuscript


def _project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise research.IntegrityError("project not found")
    return project


def _record(
    session: Session,
    project_id: str,
    action: str,
    object_type: str,
    object_id: str,
    detail: dict,
) -> None:
    project = _project(session, project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action=action,
        object_type=object_type,
        object_id=object_id,
        detail=detail,
    )


def _normalise_orcid(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().removeprefix("https://orcid.org/").upper()
    match = _ORCID_RE.fullmatch(candidate)
    if not match:
        raise research.IntegrityError("ORCID must use the form 0000-0000-0000-000X")
    compact = candidate.replace("-", "")
    total = 0
    for char in compact[:15]:
        total = (total + int(char)) * 2
    checksum = (12 - (total % 11)) % 11
    expected = "X" if checksum == 10 else str(checksum)
    if compact[-1] != expected:
        raise research.IntegrityError("ORCID checksum is invalid")
    return candidate


def contributor_out(contributor: Contributor) -> dict:
    return {
        "id": contributor.id,
        "project_id": contributor.project_id,
        "display_name": contributor.display_name,
        "given_names": contributor.given_names,
        "family_name": contributor.family_name,
        "orcid": contributor.orcid,
        "affiliation": contributor.affiliation,
        "corresponding": contributor.corresponding,
    }


def assignment_out(assignment: CreditAssignment) -> dict:
    return {
        "id": assignment.id,
        "project_id": assignment.project_id,
        "manuscript_id": assignment.manuscript_id,
        "contributor_id": assignment.contributor_id,
        "role": assignment.role,
        "role_label": CREDIT_ROLES[assignment.role],
        "degree": assignment.degree,
        "state": assignment.state,
        "origin": assignment.origin,
        "rationale": assignment.rationale,
        "review_note": assignment.review_note,
        "history": list(assignment.history or []),
    }


def proposal_out(proposal: AuthorshipProposal, *, current_basis_hash: str | None = None) -> dict:
    return {
        "id": proposal.id,
        "project_id": proposal.project_id,
        "manuscript_id": proposal.manuscript_id,
        "ordered_contributor_ids": list(proposal.ordered_contributor_ids or []),
        "rationale": proposal.rationale,
        "method": proposal.method,
        "basis_hash": proposal.basis_hash,
        "status": proposal.status,
        "review_note": proposal.review_note,
        "snapshot": dict(proposal.snapshot or {}),
        "history": list(proposal.history or []),
        "stale": current_basis_hash is not None and proposal.basis_hash != current_basis_hash,
    }


def create_contributor(
    session: Session,
    project_id: str,
    *,
    display_name: str,
    given_names: str = "",
    family_name: str = "",
    orcid: str | None = None,
    affiliation: str = "",
    corresponding: bool = False,
) -> Contributor:
    _project(session, project_id)
    name = display_name.strip()
    if not name:
        raise research.IntegrityError("contributor display_name is required")
    contributor = Contributor(
        project_id=project_id,
        display_name=name,
        given_names=given_names.strip(),
        family_name=family_name.strip(),
        orcid=_normalise_orcid(orcid),
        affiliation=affiliation.strip(),
        corresponding=corresponding,
    )
    session.add(contributor)
    session.flush()
    _record(
        session,
        project_id,
        "create_contributor",
        "contributor",
        contributor.id,
        {"display_name": name, "orcid": contributor.orcid},
    )
    return contributor


def list_contributors(session: Session, project_id: str) -> list[Contributor]:
    _project(session, project_id)
    return list(
        session.scalars(
            select(Contributor)
            .where(Contributor.project_id == project_id, Contributor.deleted_at.is_(None))
            .order_by(Contributor.display_name, Contributor.id)
        )
    )


def _contributor(session: Session, contributor_id: str, project_id: str) -> Contributor:
    contributor = session.get(Contributor, contributor_id)
    if (
        contributor is None
        or contributor.deleted_at is not None
        or contributor.project_id != project_id
    ):
        raise research.IntegrityError("contributor not found in project")
    return contributor


def propose_assignment(
    session: Session,
    manuscript_id: str,
    *,
    contributor_id: str,
    role: str,
    degree: str = "equal",
    rationale: str,
    origin: str = "human",
) -> CreditAssignment:
    manuscript = _manuscript(session, manuscript_id)
    _contributor(session, contributor_id, manuscript.project_id)
    if role not in CREDIT_ROLES:
        raise research.IntegrityError(f"role must be one of {sorted(CREDIT_ROLES)}")
    if degree not in CONTRIBUTION_DEGREES:
        raise research.IntegrityError(f"degree must be one of {sorted(CONTRIBUTION_DEGREES)}")
    if origin not in ASSIGNMENT_ORIGINS:
        raise research.IntegrityError(f"origin must be one of {sorted(ASSIGNMENT_ORIGINS)}")
    note = rationale.strip()
    if not note:
        raise research.IntegrityError("a contribution rationale is required")
    existing = session.scalar(
        select(CreditAssignment).where(
            CreditAssignment.manuscript_id == manuscript_id,
            CreditAssignment.contributor_id == contributor_id,
            CreditAssignment.role == role,
            CreditAssignment.deleted_at.is_(None),
        )
    )
    if existing is not None:
        raise research.IntegrityError("that contributor already has this CRediT role")
    at = utcnow().isoformat()
    assignment = CreditAssignment(
        project_id=manuscript.project_id,
        manuscript_id=manuscript_id,
        contributor_id=contributor_id,
        role=role,
        degree=degree,
        state="proposed",
        origin=origin,
        rationale=note,
        history=[{"at": at, "from": None, "to": "proposed", "note": note, "origin": origin}],
    )
    session.add(assignment)
    session.flush()
    _record(
        session,
        manuscript.project_id,
        "propose_credit_assignment",
        "credit_assignment",
        assignment.id,
        {"contributor_id": contributor_id, "role": role, "degree": degree, "origin": origin},
    )
    return assignment


def review_assignment(
    session: Session, assignment_id: str, *, state: str, note: str
) -> CreditAssignment:
    assignment = session.get(CreditAssignment, assignment_id)
    if assignment is None or assignment.deleted_at is not None:
        raise research.IntegrityError("CRediT assignment not found")
    if state not in ASSIGNMENT_REVIEW_STATES:
        raise research.IntegrityError(
            f"review state must be one of {sorted(ASSIGNMENT_REVIEW_STATES)}"
        )
    review_note = note.strip()
    if not review_note:
        raise research.IntegrityError("a human review note is required")
    previous = assignment.state
    assignment.state = state
    assignment.review_note = review_note
    assignment.history = [
        *(assignment.history or []),
        {"at": utcnow().isoformat(), "from": previous, "to": state, "note": review_note},
    ]
    _record(
        session,
        assignment.project_id,
        "review_credit_assignment",
        "credit_assignment",
        assignment.id,
        {"from": previous, "to": state, "note": review_note},
    )
    return assignment


def _assignments(session: Session, manuscript_id: str) -> list[CreditAssignment]:
    return list(
        session.scalars(
            select(CreditAssignment)
            .where(
                CreditAssignment.manuscript_id == manuscript_id,
                CreditAssignment.deleted_at.is_(None),
            )
            .order_by(CreditAssignment.contributor_id, CreditAssignment.role)
        )
    )


def _snapshot(session: Session, manuscript_id: str) -> tuple[dict, str]:
    manuscript = _manuscript(session, manuscript_id)
    assignments = _assignments(session, manuscript_id)
    contributor_ids = sorted({a.contributor_id for a in assignments})
    contributors = [_contributor(session, cid, manuscript.project_id) for cid in contributor_ids]
    payload = {
        "manuscript_id": manuscript_id,
        "contributors": [
            {
                "id": c.id,
                "display_name": c.display_name,
                "orcid": c.orcid,
                "affiliation": c.affiliation,
                "corresponding": c.corresponding,
            }
            for c in contributors
        ],
        "assignments": [
            {
                "id": a.id,
                "contributor_id": a.contributor_id,
                "role": a.role,
                "degree": a.degree,
                "state": a.state,
                "origin": a.origin,
                "rationale": a.rationale,
                "review_note": a.review_note,
            }
            for a in assignments
        ],
    }
    return payload, stable_hash(payload)


def _validate_order(
    session: Session, manuscript: ResearchObject, ordered_contributor_ids: list[str]
) -> list[str]:
    order = list(ordered_contributor_ids)
    if not order:
        raise research.IntegrityError("authorship order must include at least one contributor")
    if len(order) != len(set(order)):
        raise research.IntegrityError("authorship order cannot contain duplicate contributors")
    for contributor_id in order:
        _contributor(session, contributor_id, manuscript.project_id)
    return order


def create_order_proposal(
    session: Session,
    manuscript_id: str,
    *,
    ordered_contributor_ids: list[str],
    rationale: str,
) -> AuthorshipProposal:
    manuscript = _manuscript(session, manuscript_id)
    order = _validate_order(session, manuscript, ordered_contributor_ids)
    note = rationale.strip()
    if not note:
        raise research.IntegrityError("an authorship-order rationale is required")
    snapshot, basis_hash = _snapshot(session, manuscript_id)
    proposal = AuthorshipProposal(
        project_id=manuscript.project_id,
        manuscript_id=manuscript_id,
        ordered_contributor_ids=order,
        rationale=note,
        method="manual",
        basis_hash=basis_hash,
        status="proposed",
        snapshot=snapshot,
        history=[{"at": utcnow().isoformat(), "from": None, "to": "proposed", "note": note}],
    )
    session.add(proposal)
    session.flush()
    _record(
        session,
        manuscript.project_id,
        "propose_authorship_order",
        "authorship_proposal",
        proposal.id,
        {"method": "manual", "ordered_contributor_ids": order, "basis_hash": basis_hash},
    )
    return proposal


def suggest_order(session: Session, manuscript_id: str) -> AuthorshipProposal:
    """Create a deterministic discussion draft from confirmed role assignments only."""
    manuscript = _manuscript(session, manuscript_id)
    assignments = _assignments(session, manuscript_id)
    disputed = [a for a in assignments if a.state == "disputed"]
    if disputed:
        raise research.IntegrityError(
            "resolve disputed CRediT assignments before generating an order draft"
        )
    confirmed = [a for a in assignments if a.state == "confirmed"]
    if not confirmed:
        raise research.IntegrityError(
            "confirm at least one CRediT assignment before generating an order draft"
        )

    scores: dict[str, dict[str, int]] = {}
    for assignment in confirmed:
        score = scores.setdefault(
            assignment.contributor_id, {"lead": 0, "equal": 0, "supporting": 0, "roles": 0}
        )
        score[assignment.degree] += 1
        score["roles"] += 1
    contributors = {
        cid: _contributor(session, cid, manuscript.project_id) for cid in scores
    }
    order = sorted(
        scores,
        key=lambda cid: (
            -scores[cid]["lead"],
            -scores[cid]["equal"],
            -scores[cid]["roles"],
            contributors[cid].display_name.casefold(),
            cid,
        ),
    )
    snapshot, basis_hash = _snapshot(session, manuscript_id)
    snapshot["ordering_basis"] = {cid: scores[cid] for cid in order}
    rationale = (
        "Deterministic discussion draft ranked by confirmed lead-role count, then "
        "confirmed equal-role count, then total confirmed roles, with name only as a "
        "stable tie-breaker. This is not an authorship determination."
    )
    proposal = AuthorshipProposal(
        project_id=manuscript.project_id,
        manuscript_id=manuscript_id,
        ordered_contributor_ids=order,
        rationale=rationale,
        method="confirmed_credit_heuristic_v1",
        basis_hash=basis_hash,
        status="proposed",
        snapshot=snapshot,
        history=[{"at": utcnow().isoformat(), "from": None, "to": "proposed", "note": rationale}],
    )
    session.add(proposal)
    session.flush()
    _record(
        session,
        manuscript.project_id,
        "suggest_authorship_order",
        "authorship_proposal",
        proposal.id,
        {"method": proposal.method, "ordered_contributor_ids": order, "basis_hash": basis_hash},
    )
    return proposal


def review_order_proposal(
    session: Session, proposal_id: str, *, decision: str, note: str
) -> AuthorshipProposal:
    proposal = session.get(AuthorshipProposal, proposal_id)
    if proposal is None or proposal.deleted_at is not None:
        raise research.IntegrityError("authorship proposal not found")
    if proposal.status != "proposed":
        raise research.IntegrityError("only a proposed authorship order can be reviewed")
    if decision not in {"approved", "rejected"}:
        raise research.IntegrityError("decision must be approved or rejected")
    review_note = note.strip()
    if not review_note:
        raise research.IntegrityError("a human review note is required")

    manuscript = _manuscript(session, proposal.manuscript_id)
    _validate_order(session, manuscript, proposal.ordered_contributor_ids)
    snapshot, current_hash = _snapshot(session, proposal.manuscript_id)
    if decision == "approved":
        if current_hash != proposal.basis_hash:
            raise research.IntegrityError(
                "authorship proposal is stale; create a new proposal from current contributions"
            )
        assignments = _assignments(session, proposal.manuscript_id)
        included = set(proposal.ordered_contributor_ids)
        if any(a.state == "disputed" and a.contributor_id in included for a in assignments):
            raise research.IntegrityError(
                "resolve disputed assignments for proposed authors before approval"
            )
        confirmed_ids = {a.contributor_id for a in assignments if a.state == "confirmed"}
        missing = included - confirmed_ids
        if missing:
            raise research.IntegrityError(
                "each proposed author must have at least one confirmed CRediT role"
            )
        prior = list(
            session.scalars(
                select(AuthorshipProposal).where(
                    AuthorshipProposal.manuscript_id == proposal.manuscript_id,
                    AuthorshipProposal.status == "approved",
                    AuthorshipProposal.id != proposal.id,
                    AuthorshipProposal.deleted_at.is_(None),
                )
            )
        )
        for old in prior:
            old.status = "superseded"
            old.history = [
                *(old.history or []),
                {
                    "at": utcnow().isoformat(),
                    "from": "approved",
                    "to": "superseded",
                    "note": f"superseded by approved proposal {proposal.id}",
                },
            ]
        manuscript.body = {
            **manuscript.body,
            "approved_authorship_proposal_id": proposal.id,
            "author_order": list(proposal.ordered_contributor_ids),
            "author_order_basis_hash": current_hash,
            "author_order_approved_at": utcnow().isoformat(),
        }

    proposal.status = decision
    proposal.review_note = review_note
    proposal.snapshot = snapshot
    proposal.history = [
        *(proposal.history or []),
        {"at": utcnow().isoformat(), "from": "proposed", "to": decision, "note": review_note},
    ]
    _record(
        session,
        proposal.project_id,
        "review_authorship_order",
        "authorship_proposal",
        proposal.id,
        {"decision": decision, "note": review_note, "basis_hash": proposal.basis_hash},
    )
    return proposal


def _proposals(session: Session, manuscript_id: str) -> list[AuthorshipProposal]:
    return list(
        session.scalars(
            select(AuthorshipProposal)
            .where(
                AuthorshipProposal.manuscript_id == manuscript_id,
                AuthorshipProposal.deleted_at.is_(None),
            )
            .order_by(AuthorshipProposal.created_at.desc(), AuthorshipProposal.id)
        )
    )


def manuscript_credit(session: Session, manuscript_id: str) -> dict:
    manuscript = _manuscript(session, manuscript_id)
    contributors = list_contributors(session, manuscript.project_id)
    assignments = _assignments(session, manuscript_id)
    _snapshot_payload, basis_hash = _snapshot(session, manuscript_id)
    proposals = _proposals(session, manuscript_id)
    approved_id = manuscript.body.get("approved_authorship_proposal_id")
    approved = next((p for p in proposals if p.id == approved_id and p.status == "approved"), None)
    approved_current = approved is not None and approved.basis_hash == basis_hash
    return {
        "manuscript_id": manuscript_id,
        "taxonomy": [{"id": key, "label": label} for key, label in CREDIT_ROLES.items()],
        "degrees": sorted(CONTRIBUTION_DEGREES),
        "assignment_states": sorted(ASSIGNMENT_STATES),
        "disclaimer": AUTHORSHIP_DISCLAIMER,
        "contributors": [contributor_out(c) for c in contributors],
        "assignments": [assignment_out(a) for a in assignments],
        "proposals": [proposal_out(p, current_basis_hash=basis_hash) for p in proposals],
        "current_basis_hash": basis_hash,
        "approved_order": list(approved.ordered_contributor_ids) if approved_current else [],
        "approved_proposal_id": approved.id if approved_current else None,
        "approved_order_stale": approved is not None and not approved_current,
    }


def export_credit(session: Session, manuscript_id: str) -> dict:
    """Stable export view: only a current human-approved order is presented as authorship."""
    data = manuscript_credit(session, manuscript_id)
    by_id = {item["id"]: item for item in data["contributors"]}
    confirmed = [a for a in data["assignments"] if a["state"] == "confirmed"]
    roles_by_contributor: dict[str, list[dict]] = {}
    for assignment in confirmed:
        roles_by_contributor.setdefault(assignment["contributor_id"], []).append(
            {
                "role": assignment["role"],
                "label": assignment["role_label"],
                "degree": assignment["degree"],
            }
        )
    authors = []
    for contributor_id in data["approved_order"]:
        contributor = by_id[contributor_id]
        authors.append(
            {
                **contributor,
                "credit_roles": sorted(
                    roles_by_contributor.get(contributor_id, []), key=lambda item: item["role"]
                ),
            }
        )
    return {
        "status": "human_approved" if authors else "not_approved",
        "proposal_id": data["approved_proposal_id"],
        "basis_hash": data["current_basis_hash"],
        "authors": authors,
        "disclaimer": AUTHORSHIP_DISCLAIMER,
    }


def audit_authorship(session: Session, manuscript_id: str) -> list[dict]:
    assignments = _assignments(session, manuscript_id)
    proposals = _proposals(session, manuscript_id)
    if not assignments and not proposals:
        return []
    data = manuscript_credit(session, manuscript_id)
    findings: list[dict] = []
    for assignment in assignments:
        if assignment.state == "disputed":
            findings.append(
                {
                    "severity": "warning",
                    "code": "credit-assignment-disputed",
                    "message": (
                        f"CRediT role {assignment.role} is disputed; resolve before "
                        "authorship approval"
                    ),
                    "object_id": assignment.id,
                }
            )
        elif assignment.state == "proposed":
            findings.append(
                {
                    "severity": "info",
                    "code": "credit-assignment-unreviewed",
                    "message": f"CRediT role {assignment.role} awaits human review",
                    "object_id": assignment.id,
                }
            )
    if data["approved_order_stale"]:
        findings.append(
            {
                "severity": "warning",
                "code": "authorship-order-stale",
                "message": "approved authorship order no longer matches the contribution snapshot",
                "object_id": manuscript_id,
            }
        )
    elif not data["approved_order"]:
        findings.append(
            {
                "severity": "info",
                "code": "authorship-order-unapproved",
                "message": "contribution data exists but no current authorship order is human-approved",
                "object_id": manuscript_id,
            }
        )
    return findings
