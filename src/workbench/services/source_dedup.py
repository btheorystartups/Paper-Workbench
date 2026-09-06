"""Deterministic duplicate-source discovery and human-confirmed consolidation.

Duplicate signals are discovery metadata, never evidence.  Nothing is merged
automatically: callers must submit the plan hash returned by
``find_duplicate_candidates`` together with a human review note.
"""

import re
import unicodedata
from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import Embedding, Excerpt, LiteratureEntry, Source, Thread, stable_hash, utcnow
from ..providers.scholarly import canonical_doi
from ..vocab import SourceAccess
from . import research


class DuplicateSignal(StrEnum):
    SAME_DOI = "same_doi"
    SAME_NORMALIZED_TITLE = "same_normalized_title"
    SAME_TITLE_YEAR = "same_title_year"


class DuplicateBlocker(StrEnum):
    CONFLICTING_DOI = "conflicting_doi"
    CONFLICTING_YEAR = "conflicting_year"
    IDENTITY_REQUIRES_RESOLUTION = "identity_requires_resolution"


_ACCESS_RANK = {
    SourceAccess.METADATA_ONLY: 0,
    SourceAccess.ABSTRACT_ONLY: 1,
    SourceAccess.EXCERPT_AVAILABLE: 2,
    SourceAccess.FULL_TEXT_AUTHORIZED: 3,
    SourceAccess.FULL_TEXT_USER_SUPPLIED: 3,
}

_LITERATURE_DEFAULTS = {
    "state": "unread",
    "reason": "",
    "relationship": "background",
    "question": "",
    "method": "",
    "result_summary": "",
    "limitations": "",
    "relevance": "",
}


def normalize_title(title: str) -> str:
    """Normalize only formatting differences; do not infer semantic equivalence."""
    text = unicodedata.normalize("NFKC", title).casefold()
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def _source_snapshot(source: Source) -> dict:
    return {
        "id": source.id,
        "title": source.title,
        "authors": source.authors,
        "year": source.year,
        "venue": source.venue,
        "doi": canonical_doi(source.doi),
        "url": source.url,
        "access": str(source.access),
        "license": source.license,
        "acquisition": source.acquisition,
        "human_verified": source.human_verified,
        "integrity_note": source.integrity_note,
        "provider_metadata": source.provider_metadata or {},
    }


def _pair_analysis(first: Source, second: Source) -> tuple[list[str], list[str]]:
    signals: list[str] = []
    blockers: list[str] = []
    first_doi = canonical_doi(first.doi)
    second_doi = canonical_doi(second.doi)
    first_title = normalize_title(first.title)
    second_title = normalize_title(second.title)

    if first_doi and second_doi and first_doi == second_doi:
        signals.append(DuplicateSignal.SAME_DOI)
    if first_title and first_title == second_title:
        signals.append(DuplicateSignal.SAME_NORMALIZED_TITLE)
        if first.year is not None and first.year == second.year:
            signals.append(DuplicateSignal.SAME_TITLE_YEAR)

    if not signals:
        return [], []
    if first_doi and second_doi and first_doi != second_doi:
        blockers.append(DuplicateBlocker.CONFLICTING_DOI)
    if (
        DuplicateSignal.SAME_NORMALIZED_TITLE in signals
        and first.year is not None
        and second.year is not None
        and first.year != second.year
    ):
        blockers.append(DuplicateBlocker.CONFLICTING_YEAR)
    if DuplicateSignal.SAME_DOI not in signals and DuplicateSignal.SAME_TITLE_YEAR not in signals:
        blockers.append(DuplicateBlocker.IDENTITY_REQUIRES_RESOLUTION)
    return [str(signal) for signal in signals], [str(blocker) for blocker in blockers]


def _plan_hash(
    project_id: str,
    first: Source,
    second: Source,
    signals: list[str],
    blockers: list[str],
) -> str:
    snapshots = sorted((_source_snapshot(first), _source_snapshot(second)), key=lambda row: row["id"])
    return stable_hash(
        {
            "operation": "merge_duplicate_sources",
            "project_id": project_id,
            "sources": snapshots,
            "signals": signals,
            "blockers": blockers,
        }
    )


def _source_summary(source: Source) -> dict:
    return {
        "id": source.id,
        "title": source.title,
        "authors": source.authors,
        "year": source.year,
        "doi": canonical_doi(source.doi),
        "access": str(source.access),
        "human_verified": source.human_verified,
    }


def find_duplicate_candidates(session: Session, project_id: str) -> list[dict]:
    """Return deterministic candidate pairs; every result remains review-required."""
    research._project(session, project_id)
    sources = list(
        session.scalars(
            select(Source)
            .where(Source.project_id == project_id, Source.deleted_at.is_(None))
            .order_by(Source.created_at, Source.id)
        )
    )
    candidates: list[dict] = []
    for index, first in enumerate(sources):
        for second in sources[index + 1 :]:
            signals, blockers = _pair_analysis(first, second)
            if not signals:
                continue
            candidates.append(
                {
                    "source_a": _source_summary(first),
                    "source_b": _source_summary(second),
                    "signals": signals,
                    "blockers": blockers,
                    "merge_allowed": not blockers,
                    "review_required": True,
                    "plan_hash": _plan_hash(project_id, first, second, signals, blockers),
                }
            )
    return candidates


def _literature_conflicts(retained: LiteratureEntry, duplicate: LiteratureEntry) -> list[str]:
    conflicts = []
    for field, default in _LITERATURE_DEFAULTS.items():
        left = getattr(retained, field)
        right = getattr(duplicate, field)
        if left != default and right != default and left != right:
            conflicts.append(field)
    return conflicts


def _merge_literature_entries(
    session: Session, retained: Source, duplicate: Source
) -> tuple[int, dict | None]:
    entries = list(
        session.scalars(
            select(LiteratureEntry).where(
                LiteratureEntry.project_id == retained.project_id,
                LiteratureEntry.source_id.in_([retained.id, duplicate.id]),
            )
        )
    )
    by_source = {entry.source_id: entry for entry in entries}
    retained_entry = by_source.get(retained.id)
    duplicate_entry = by_source.get(duplicate.id)
    if duplicate_entry is None:
        return 0, None
    snapshot = {
        field: getattr(duplicate_entry, field)
        for field in ("id", "source_id", *_LITERATURE_DEFAULTS)
    }
    if retained_entry is None:
        duplicate_entry.source_id = retained.id
        return 1, snapshot
    conflicts = _literature_conflicts(retained_entry, duplicate_entry)
    if conflicts:
        raise research.IntegrityError(
            "literature entries conflict in fields "
            f"{', '.join(conflicts)}; reconcile them before merging sources"
        )
    for field, default in _LITERATURE_DEFAULTS.items():
        if getattr(retained_entry, field) == default:
            setattr(retained_entry, field, getattr(duplicate_entry, field))
    session.delete(duplicate_entry)
    return 1, snapshot


def merge_duplicate_sources(
    session: Session,
    project_id: str,
    *,
    retained_source_id: str,
    duplicate_source_id: str,
    plan_hash: str,
    review_note: str,
) -> dict:
    """Consolidate a reviewed candidate while preserving evidence and provenance."""
    project = research._project(session, project_id)
    if retained_source_id == duplicate_source_id:
        raise research.IntegrityError("retained and duplicate source must differ")
    retained = session.get(Source, retained_source_id)
    duplicate = session.get(Source, duplicate_source_id)
    for source in (retained, duplicate):
        if source is None or source.project_id != project_id or source.deleted_at is not None:
            raise research.IntegrityError("source not found in project")
    if not review_note.strip():
        raise research.IntegrityError("a human review note is required to merge sources")

    signals, blockers = _pair_analysis(retained, duplicate)
    if not signals:
        raise research.IntegrityError("sources are not a deterministic duplicate candidate")
    if blockers:
        raise research.IntegrityError(
            f"duplicate candidate is blocked: {', '.join(blockers)}"
        )
    expected_hash = _plan_hash(project_id, retained, duplicate, signals, blockers)
    if plan_hash != expected_hash:
        raise research.IntegrityError("duplicate merge plan changed; review the candidate again")

    retained_entry = session.scalars(
        select(LiteratureEntry).where(
            LiteratureEntry.project_id == project_id,
            LiteratureEntry.source_id == retained.id,
        )
    ).first()
    duplicate_entry = session.scalars(
        select(LiteratureEntry).where(
            LiteratureEntry.project_id == project_id,
            LiteratureEntry.source_id == duplicate.id,
        )
    ).first()
    if retained_entry is not None and duplicate_entry is not None:
        conflicts = _literature_conflicts(retained_entry, duplicate_entry)
        if conflicts:
            raise research.IntegrityError(
                "literature entries conflict in fields "
                f"{', '.join(conflicts)}; reconcile them before merging sources"
            )

    duplicate_snapshot = _source_snapshot(duplicate)
    excerpt_count = session.query(Excerpt).filter(Excerpt.source_id == duplicate.id).update(
        {Excerpt.source_id: retained.id}, synchronize_session="fetch"
    )
    literature_count, literature_snapshot = _merge_literature_entries(
        session, retained, duplicate
    )
    from . import citation_graph

    citation_updates = citation_graph.repoint_source(
        session,
        project_id,
        retained_source_id=retained.id,
        duplicate_source_id=duplicate.id,
    )

    updated_threads = 0
    for thread in session.scalars(select(Thread).where(Thread.project_id == project_id)):
        pins = list(thread.pinned_source_ids or [])
        if duplicate.id not in pins:
            continue
        thread.pinned_source_ids = list(
            dict.fromkeys(retained.id if source_id == duplicate.id else source_id for source_id in pins)
        )
        updated_threads += 1

    session.execute(
        delete(Embedding).where(
            Embedding.project_id == project_id,
            Embedding.target_type == "source",
            Embedding.target_id.in_([retained.id, duplicate.id]),
        )
    )

    for field in ("authors", "venue", "url"):
        if not getattr(retained, field) and getattr(duplicate, field):
            setattr(retained, field, getattr(duplicate, field))
    if retained.year is None:
        retained.year = duplicate.year
    if not retained.doi:
        retained.doi = canonical_doi(duplicate.doi)
    if retained.license == "unknown" and duplicate.license != "unknown":
        retained.license = duplicate.license
    if _ACCESS_RANK[SourceAccess(duplicate.access)] > _ACCESS_RANK[SourceAccess(retained.access)]:
        retained.access = duplicate.access
        if duplicate.acquisition:
            retained.acquisition = duplicate.acquisition
    retained.human_verified = retained.human_verified or duplicate.human_verified
    if duplicate.integrity_note and duplicate.integrity_note not in retained.integrity_note:
        retained.integrity_note = " | ".join(
            note for note in (retained.integrity_note, duplicate.integrity_note) if note
        )

    metadata = dict(retained.provider_metadata or {})
    merge_records = list(metadata.get("duplicate_merges", []))
    merge_records.append(
        {
            "merged_source": duplicate_snapshot,
            "merged_at": utcnow().isoformat(),
            "review_note": review_note.strip(),
            "signals": signals,
            "literature_entry": literature_snapshot,
        }
    )
    metadata["duplicate_merges"] = merge_records
    retained.provider_metadata = metadata

    duplicate_metadata = dict(duplicate.provider_metadata or {})
    duplicate_metadata["merged_into"] = {
        "source_id": retained.id,
        "merged_at": utcnow().isoformat(),
        "review_note": review_note.strip(),
    }
    duplicate.provider_metadata = duplicate_metadata
    duplicate.deleted_at = utcnow()

    detail = {
        "retained_source_id": retained.id,
        "duplicate_source_id": duplicate.id,
        "signals": signals,
        "review_note": review_note.strip(),
        "moved_excerpts": excerpt_count,
        "merged_literature_entries": literature_count,
        "updated_threads": updated_threads,
        "embeddings_invalidated": True,
        "plan_hash": plan_hash,
        **citation_updates,
    }
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="merge_duplicate",
        object_type="source",
        object_id=retained.id,
        detail=detail,
    )
    session.flush()
    return detail
