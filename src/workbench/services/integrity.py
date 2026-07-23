"""Retraction/correction watch. Checks every DOI-bearing source of a project against the
integrity provider (Crossref `updated-by` live; deterministic fake offline).

Rules:
- A retraction/correction found → the source's `integrity_note` is set (prefixed
  "[integrity-watch]") and full details land in provider_metadata["integrity"]. The
  existing `source-integrity-flag` audit finding then fires everywhere audits run.
- A note a human wrote by hand (no prefix) is never overwritten; watch details still
  land in provider_metadata.
- A failed lookup is recorded as failed, never treated as "clean" — absence of evidence
  of retraction is not evidence of integrity.
- The watch never un-flags: a previously found notice is not cleared by a later clean
  or failed check (a human clears integrity_note deliberately).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import Source
from ..providers.registry import get_integrity_provider
from . import research

_PREFIX = "[integrity-watch]"


def _summarize(updates: list[dict]) -> str:
    parts = []
    for u in updates:
        label = u.get("type") or "update"
        notice = u.get("notice_doi") or ""
        date = u.get("date") or ""
        parts.append(f"{label} ({date}, notice doi:{notice}, via {u.get('via', '?')})")
    return "; ".join(parts)


def check_project_sources(session: Session, project_id: str) -> dict:
    """Run the watch over all live, DOI-bearing sources of the project. Returns a summary;
    flagged sources get integrity_note + metadata set in the same transaction."""
    project = research._project(session, project_id)
    provider = get_integrity_provider()
    checked_at = datetime.now(UTC).isoformat()
    checked = flagged = failed = skipped = 0
    flagged_sources: list[dict] = []

    for src in session.scalars(
        select(Source).where(Source.project_id == project_id, Source.deleted_at.is_(None))
    ):
        if not src.doi:
            skipped += 1
            continue
        updates = provider.fetch_updates(src.doi)
        checked += 1
        meta = dict(src.provider_metadata or {})
        integrity = dict(meta.get("integrity") or {})
        integrity["checked_at"] = checked_at
        if updates is None:
            failed += 1
            integrity["last_check"] = "failed"
            # a failed check never clears earlier findings
        elif updates:
            flagged += 1
            integrity["last_check"] = "flagged"
            integrity["updates"] = updates
            summary = _summarize(updates)
            # never overwrite a human-written note (one without our prefix)
            if not src.integrity_note or src.integrity_note.startswith(_PREFIX):
                src.integrity_note = f"{_PREFIX} {summary}"
            flagged_sources.append({"source_id": src.id, "title": src.title,
                                    "doi": src.doi, "updates": updates})
            record_audit(
                session, workspace_id=project.workspace_id, actor="integrity-watch",
                action="flag_source", object_type="source", object_id=src.id,
                detail={"doi": src.doi, "updates": updates},
            )
        else:
            integrity["last_check"] = "clean"
            # do not clear integrity_note or previously stored updates — human's call
        meta["integrity"] = integrity
        src.provider_metadata = meta
    session.flush()
    record_audit(
        session, workspace_id=project.workspace_id, actor="integrity-watch",
        action="check_project", object_type="project", object_id=project_id,
        detail={"checked": checked, "flagged": flagged, "failed": failed,
                "skipped_no_doi": skipped},
    )
    return {"checked_at": checked_at, "checked": checked, "flagged": flagged,
            "failed": failed, "skipped_no_doi": skipped,
            "flagged_sources": flagged_sources}
