"""Literature workspace (P3): saved searches, explicit import of works as Sources,
screening states, literature matrix, and novelty/contribution mapping.

Rules:
- A search run never auto-creates evidence; works are imported explicitly.
- Imported works are metadata_only (or abstract_only when an abstract came along),
  human_verified=False, license/provenance recorded.
- Import dedupes against existing project Sources by canonical DOI.
- Novelty states come from vocab.Novelty and always carry a search-coverage note;
  novelty is never asserted without recording what was (and wasn't) searched.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import LiteratureEntry, ResearchObject, SavedSearch, Source
from ..providers.scholarly import (
    CrossrefAdapter,
    FakeScholarlyProvider,
    OpenAlexAdapter,
    ScholarlyWork,
    canonical_doi,
    dedupe,
)
from ..vocab import Novelty, ObjectKind, SourceAccess
from . import research

SCREEN_STATES = {"unread", "maybe", "include", "exclude"}
RELATIONSHIPS = {"supports", "contradicts", "background"}


def get_scholarly_provider(name: str):
    from ..providers.registry import provider_mode

    if provider_mode() != "live":
        return FakeScholarlyProvider()
    if name == "openalex":
        return OpenAlexAdapter()
    if name == "crossref":
        return CrossrefAdapter()
    return FakeScholarlyProvider()


def run_search(
    session: Session, project_id: str, *, provider: str, query: str, count: int = 10
) -> tuple[SavedSearch, list[ScholarlyWork]]:
    project = research._project(session, project_id)
    adapter = get_scholarly_provider(provider)
    works = dedupe(adapter.search(query, count=count))
    saved = SavedSearch(
        project_id=project_id, provider=provider, query=query,
        filters={"count": count}, last_run_at=datetime.now(UTC),
        last_result_count=len(works),
    )
    session.add(saved)
    session.flush()
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="search",
        object_type="saved_search", object_id=saved.id,
        detail={"provider": provider, "query": query, "results": len(works)},
    )
    return saved, works


def import_work(session: Session, project_id: str, work: ScholarlyWork) -> tuple[Source, bool]:
    """Import a discovered work as a Source. Returns (source, created). Dedup by DOI."""
    doi = canonical_doi(work.doi)
    if doi:
        existing = session.scalars(
            select(Source).where(Source.project_id == project_id, Source.doi == doi)
        ).first()
        if existing:
            return existing, False
    access = SourceAccess.ABSTRACT_ONLY if work.abstract else SourceAccess.METADATA_ONLY
    source = research.register_source(
        session,
        project_id,
        title=work.title,
        access=access,
        acquisition=f"imported from {work.provider} search",
        authors="; ".join(a for a in work.authors if a),
        year=work.year,
        venue=work.venue,
        doi=doi,
        url=work.url,
        license=work.license or "unknown",
        provider_metadata={
            "scholarly": {
                "provider": work.provider,
                "provider_id": work.provider_id,
                "cited_by_count": work.cited_by_count,
                "open_access_url": work.open_access_url,
                "abstract": work.abstract,
                "raw": work.raw,
            }
        },
    )
    return source, True


def set_screening(
    session: Session, project_id: str, source_id: str, *,
    state: str | None = None, reason: str | None = None,
    relationship: str | None = None, **matrix_fields: str,
) -> LiteratureEntry:
    project = research._project(session, project_id)
    source = session.get(Source, source_id)
    if source is None or source.project_id != project_id:
        raise research.IntegrityError("source not in project")
    if state is not None and state not in SCREEN_STATES:
        raise research.IntegrityError(f"state must be one of {sorted(SCREEN_STATES)}")
    if relationship is not None and relationship not in RELATIONSHIPS:
        raise research.IntegrityError(f"relationship must be one of {sorted(RELATIONSHIPS)}")

    entry = session.scalars(
        select(LiteratureEntry).where(
            LiteratureEntry.project_id == project_id, LiteratureEntry.source_id == source_id
        )
    ).first()
    if entry is None:
        entry = LiteratureEntry(project_id=project_id, source_id=source_id)
        session.add(entry)
    if state is not None:
        entry.state = state
    if reason is not None:
        entry.reason = reason
    if relationship is not None:
        entry.relationship = relationship
    for name in ("question", "method", "result_summary", "limitations", "relevance"):
        if name in matrix_fields and matrix_fields[name] is not None:
            setattr(entry, name, matrix_fields[name])
    session.flush()
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="screen",
        object_type="literature_entry", object_id=entry.id,
        detail={"source_id": source_id, "state": entry.state},
    )
    return entry


def literature_matrix(session: Session, project_id: str) -> list[dict]:
    rows = []
    entries = session.scalars(
        select(LiteratureEntry).where(LiteratureEntry.project_id == project_id)
    )
    for e in entries:
        src = session.get(Source, e.source_id)
        rows.append(
            {
                "source_id": e.source_id,
                "title": src.title if src else "?",
                "year": src.year if src else None,
                "doi": src.doi if src else None,
                "access": str(src.access) if src else None,
                "human_verified": src.human_verified if src else False,
                "state": e.state,
                "reason": e.reason,
                "relationship": e.relationship,
                "question": e.question,
                "method": e.method,
                "result_summary": e.result_summary,
                "limitations": e.limitations,
                "relevance": e.relevance,
            }
        )
    return rows


def assess_contribution(
    session: Session, project_id: str, *,
    title: str, statement: str, novelty: Novelty | str,
    coverage_note: str, closest_prior_source_ids: list[str] | None = None,
) -> ResearchObject:
    """Create/record a contribution-map entry. Novelty is provisional by definition:
    the coverage note (what was searched, what wasn't) is mandatory."""
    novelty = Novelty(novelty)
    if not coverage_note.strip():
        raise research.IntegrityError(
            "novelty assessments require a search-coverage note (databases, queries, dates, gaps)"
        )
    prior_ids = closest_prior_source_ids or []
    for sid in prior_ids:
        src = session.get(Source, sid)
        if src is None or src.project_id != project_id:
            raise research.IntegrityError(f"source {sid} not in project")
    return research.create_object(
        session, project_id, kind=ObjectKind.NOTE, title=title,
        body={
            "contribution": statement,
            "novelty": str(novelty),
            "coverage_note": coverage_note,
            "closest_prior_source_ids": prior_ids,
            "provisional": True,
            "expert_confirmation": "pending",
        },
    )
