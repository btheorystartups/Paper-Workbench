"""Submission tracking (P-hardening). An explicit, audited state machine for a
manuscript's lifecycle at a venue. Transitions are validated; every change appends to an
immutable history. This never contacts a venue — it records what the researcher did.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import ResearchObject, Submission, VenueProfile
from ..vocab import ObjectKind
from . import research

# state -> allowed next states
TRANSITIONS: dict[str, set[str]] = {
    "drafting": {"submitted", "withdrawn"},
    "submitted": {"under_review", "withdrawn", "rejected"},
    "under_review": {"revision_requested", "accepted", "rejected", "withdrawn"},
    "revision_requested": {"resubmitted", "withdrawn"},
    "resubmitted": {"under_review", "withdrawn", "rejected"},
    "accepted": set(),
    "rejected": set(),   # terminal (a new venue = a new Submission)
    "withdrawn": set(),
}
TERMINAL = {s for s, nxt in TRANSITIONS.items() if not nxt}


class SubmissionError(ValueError):
    pass


def create_submission(
    session: Session, project_id: str, *, manuscript_id: str,
    venue_id: str | None = None, venue_name: str = "", deadline: str | None = None,
) -> Submission:
    project = research._project(session, project_id)
    ms = session.get(ResearchObject, manuscript_id)
    if ms is None or ms.project_id != project_id or ms.kind != ObjectKind.MANUSCRIPT:
        raise SubmissionError("manuscript not found in project")
    if venue_id is not None:
        venue = session.get(VenueProfile, venue_id)
        if venue is None:
            raise SubmissionError("venue not found")
        venue_name = venue_name or venue.name
    now = datetime.now(UTC).isoformat()
    sub = Submission(
        project_id=project_id, manuscript_id=manuscript_id, venue_id=venue_id,
        venue_name=venue_name, status="drafting", deadline=deadline,
        history=[{"at": now, "from": None, "to": "drafting", "note": "created"}],
        revisions=[],
    )
    session.add(sub)
    session.flush()
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="create",
        object_type="submission", object_id=sub.id,
        detail={"manuscript_id": manuscript_id, "venue": venue_name},
    )
    return sub


def transition(session: Session, submission_id: str, to_status: str, *, note: str = "") -> Submission:
    sub = session.get(Submission, submission_id)
    if sub is None:
        raise SubmissionError("submission not found")
    if sub.status in TERMINAL:
        raise SubmissionError(f"submission is in terminal state '{sub.status}'")
    allowed = TRANSITIONS.get(sub.status, set())
    if to_status not in allowed:
        raise SubmissionError(
            f"cannot move from '{sub.status}' to '{to_status}'; allowed: {sorted(allowed)}"
        )
    now = datetime.now(UTC).isoformat()
    sub.history = [*sub.history, {"at": now, "from": sub.status, "to": to_status, "note": note}]
    sub.status = to_status
    project = research._project(session, sub.project_id)
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="transition",
        object_type="submission", object_id=sub.id,
        detail={"to": to_status, "note": note},
    )
    return sub


def add_revision(
    session: Session, submission_id: str, *,
    summary: str, response_to_reviewers: str, changes: list[str] | None = None,
) -> Submission:
    """Attach a response-to-reviewers document to a submission (typically while in
    revision_requested). Recorded, not submitted."""
    sub = session.get(Submission, submission_id)
    if sub is None:
        raise SubmissionError("submission not found")
    now = datetime.now(UTC).isoformat()
    sub.revisions = [
        *sub.revisions,
        {
            "at": now,
            "round": len(sub.revisions) + 1,
            "summary": summary,
            "response_to_reviewers": response_to_reviewers,
            "changes": changes or [],
            "status_when_added": sub.status,
        },
    ]
    return sub


def get_submission(session: Session, submission_id: str) -> Submission:
    sub = session.get(Submission, submission_id)
    if sub is None:
        raise SubmissionError("submission not found")
    return sub


def list_submissions(session: Session, project_id: str) -> list[Submission]:
    return list(
        session.scalars(
            select(Submission).where(
                Submission.project_id == project_id, Submission.deleted_at.is_(None)
            )
        )
    )
