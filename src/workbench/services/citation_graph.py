"""Project-scoped citation discovery graph with explicit provenance and review state.

Citation links are discovery metadata only. Resolving or human-verifying an edge never
creates an excerpt, claim-evidence link, or accepted research object.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import CitationEdge, Source, stable_hash, utcnow
from ..providers.scholarly import (
    FakeScholarlyProvider,
    ScholarlyWork,
    SemanticScholarAdapter,
    canonical_doi,
    citation_key,
    work_key,
)
from . import research


class CitationDirection(StrEnum):
    BACKWARD = "backward"
    FORWARD = "forward"


class CitationResolution(StrEnum):
    RESOLVED = "resolved"
    CITING_UNRESOLVED = "citing_unresolved"
    CITED_UNRESOLVED = "cited_unresolved"
    BOTH_UNRESOLVED = "both_unresolved"


class CitationReview(StrEnum):
    PROVIDER_REPORTED = "provider_reported"
    HUMAN_VERIFIED = "human_verified"
    REJECTED = "rejected"


def get_citation_provider(name: str):
    from ..providers.registry import provider_mode

    if provider_mode() != "live":
        return FakeScholarlyProvider(), True
    if name == "semanticscholar":
        return SemanticScholarAdapter(), False
    raise research.IntegrityError("citation provider must be semanticscholar")


def _source_provider_identity(source: Source) -> tuple[str, str] | None:
    scholarly = (source.provider_metadata or {}).get("scholarly") or {}
    provider = scholarly.get("provider")
    provider_id = scholarly.get("provider_id")
    if provider and provider_id:
        return str(provider), str(provider_id)
    return None


def _source_key(source: Source) -> str:
    doi = canonical_doi(source.doi)
    if doi:
        return f"doi:{doi}"
    provider_identity = _source_provider_identity(source)
    if provider_identity:
        return f"provider:{provider_identity[0]}:{provider_identity[1]}"
    return work_key(
        ScholarlyWork(
            title=source.title,
            authors=[],
            year=source.year,
            venue=source.venue,
            doi=None,
            url=source.url,
            abstract=None,
            cited_by_count=None,
            open_access_url=None,
            license=source.license,
            provider="",
            provider_id="",
        )
    )


def _strong_source_keys(source: Source) -> set[str]:
    keys: set[str] = set()
    doi = canonical_doi(source.doi)
    if doi:
        keys.add(f"doi:{doi}")
    provider_identity = _source_provider_identity(source)
    if provider_identity:
        keys.add(f"provider:{provider_identity[0]}:{provider_identity[1]}")
    return keys


def _matching_source(session: Session, project_id: str, work: ScholarlyWork) -> Source | None:
    key = citation_key(work)
    for source in session.scalars(
        select(Source).where(Source.project_id == project_id, Source.deleted_at.is_(None))
    ):
        if key in _strong_source_keys(source):
            return source
    return None


def _resolution(edge: CitationEdge) -> CitationResolution:
    if edge.citing_source_id and edge.cited_source_id:
        return CitationResolution.RESOLVED
    if edge.citing_source_id:
        return CitationResolution.CITED_UNRESOLVED
    if edge.cited_source_id:
        return CitationResolution.CITING_UNRESOLVED
    return CitationResolution.BOTH_UNRESOLVED


def _refresh_resolution(edge: CitationEdge) -> None:
    edge.resolution_state = _resolution(edge)
    edge.updated_at = utcnow()


def _source_summary(source: Source | None, *, key: str, title: str) -> dict:
    if source is None:
        return {"id": None, "key": key, "title": title, "doi": None, "resolved": False}
    return {
        "id": source.id,
        "key": key,
        "title": source.title,
        "doi": canonical_doi(source.doi),
        "resolved": True,
    }


def edge_out(session: Session, edge: CitationEdge) -> dict:
    citing = session.get(Source, edge.citing_source_id) if edge.citing_source_id else None
    cited = session.get(Source, edge.cited_source_id) if edge.cited_source_id else None
    return {
        "id": edge.id,
        "citing": _source_summary(citing, key=edge.citing_key, title=edge.citing_title),
        "cited": _source_summary(cited, key=edge.cited_key, title=edge.cited_title),
        "resolution_state": edge.resolution_state,
        "review_state": edge.review_state,
        "review_note": edge.review_note,
        "observations": edge.observations or [],
        "discovery_only": True,
    }


def record_citations(
    session: Session,
    project_id: str,
    source_id: str,
    *,
    direction: CitationDirection | str,
    provider: str,
    works: list[ScholarlyWork],
    simulated: bool,
) -> tuple[list[CitationEdge], int]:
    """Upsert provider observations without importing works or creating evidence."""
    project = research._project(session, project_id)
    source = session.get(Source, source_id)
    if source is None or source.project_id != project_id or source.deleted_at is not None:
        raise research.IntegrityError("source not found in project")
    if not canonical_doi(source.doi):
        raise research.IntegrityError("citation discovery requires a DOI on the source")
    direction = CitationDirection(direction)
    observed_at = datetime.now(UTC).isoformat()
    touched: list[CitationEdge] = []
    created = 0

    for work in works:
        linked_source = _matching_source(session, project_id, work)
        linked_key = citation_key(work)
        anchor_key = _source_key(source)
        if direction == CitationDirection.BACKWARD:
            citing_source_id, cited_source_id = source.id, linked_source.id if linked_source else None
            citing_key, cited_key = anchor_key, linked_key
            citing_title, cited_title = source.title, work.title
        else:
            citing_source_id, cited_source_id = linked_source.id if linked_source else None, source.id
            citing_key, cited_key = linked_key, anchor_key
            citing_title, cited_title = work.title, source.title
        if citing_key == cited_key:
            continue

        edge = session.scalars(
            select(CitationEdge).where(
                CitationEdge.project_id == project_id,
                CitationEdge.citing_key == citing_key,
                CitationEdge.cited_key == cited_key,
                CitationEdge.deleted_at.is_(None),
            )
        ).first()
        if edge is None:
            edge = CitationEdge(
                project_id=project_id,
                citing_source_id=citing_source_id,
                cited_source_id=cited_source_id,
                citing_key=citing_key,
                cited_key=cited_key,
                citing_title=citing_title,
                cited_title=cited_title,
                resolution_state=CitationResolution.BOTH_UNRESOLVED,
                review_state=CitationReview.PROVIDER_REPORTED,
                observations=[],
            )
            session.add(edge)
            created += 1
        else:
            edge.citing_source_id = edge.citing_source_id or citing_source_id
            edge.cited_source_id = edge.cited_source_id or cited_source_id

        observation = {
            "provider": provider,
            "provider_id": work.provider_id,
            "direction": str(direction),
            "observed_at": observed_at,
            "simulated": simulated,
            "linked_work": {
                "title": work.title,
                "year": work.year,
                "doi": canonical_doi(work.doi),
                "url": work.url,
            },
        }
        observation["observation_hash"] = stable_hash(observation)
        edge.observations = [*(edge.observations or []), observation]
        _refresh_resolution(edge)
        touched.append(edge)

    session.flush()
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="discover_citations",
        object_type="source",
        object_id=source.id,
        detail={
            "provider": provider,
            "direction": str(direction),
            "simulated": simulated,
            "observed": len(works),
            "edges_touched": len(touched),
            "edges_created": created,
            "discovery_only": True,
        },
    )
    return touched, created


def discover_citations(
    session: Session,
    project_id: str,
    source_id: str,
    *,
    provider: str = "semanticscholar",
    direction: CitationDirection | str = CitationDirection.BACKWARD,
    count: int = 20,
) -> dict:
    if count < 1 or count > 100:
        raise research.IntegrityError("citation count must be between 1 and 100")
    source = session.get(Source, source_id)
    if source is None or source.project_id != project_id or source.deleted_at is not None:
        raise research.IntegrityError("source not found in project")
    doi = canonical_doi(source.doi)
    if not doi:
        raise research.IntegrityError("citation discovery requires a DOI on the source")
    direction = CitationDirection(direction)
    adapter, simulated = get_citation_provider(provider)
    works = adapter.citations(doi, direction=str(direction), count=count)
    edges, created = record_citations(
        session,
        project_id,
        source_id,
        direction=direction,
        provider=provider if not simulated else "fake-citations",
        works=works,
        simulated=simulated,
    )
    return {
        "provider": provider,
        "direction": str(direction),
        "simulated": simulated,
        "works_observed": len(works),
        "edges_created": created,
        "edges": [edge_out(session, edge) for edge in edges],
        "discovery_only": True,
    }


def resolve_edges_for_source(session: Session, source: Source) -> int:
    """Resolve exact DOI/provider identifiers when a discovered work is imported."""
    strong_keys = _strong_source_keys(source)
    if not strong_keys:
        return 0
    updated = 0
    edges = session.scalars(
        select(CitationEdge).where(
            CitationEdge.project_id == source.project_id,
            CitationEdge.deleted_at.is_(None),
            or_(
                CitationEdge.citing_key.in_(strong_keys),
                CitationEdge.cited_key.in_(strong_keys),
            ),
        )
    )
    for edge in edges:
        if edge.citing_key in strong_keys and edge.citing_source_id is None:
            edge.citing_source_id = source.id
            updated += 1
        if edge.cited_key in strong_keys and edge.cited_source_id is None:
            edge.cited_source_id = source.id
            updated += 1
        _refresh_resolution(edge)
    return updated


def resolve_edge(
    session: Session,
    project_id: str,
    edge_id: str,
    *,
    endpoint: str,
    source_id: str,
    review_note: str,
) -> CitationEdge:
    project = research._project(session, project_id)
    edge = session.get(CitationEdge, edge_id)
    source = session.get(Source, source_id)
    if edge is None or edge.project_id != project_id or edge.deleted_at is not None:
        raise research.IntegrityError("citation edge not found in project")
    if source is None or source.project_id != project_id or source.deleted_at is not None:
        raise research.IntegrityError("resolution source not found in project")
    if endpoint not in {"citing", "cited"}:
        raise research.IntegrityError("endpoint must be citing or cited")
    if not review_note.strip():
        raise research.IntegrityError("citation resolution requires a human review note")

    current_id = edge.citing_source_id if endpoint == "citing" else edge.cited_source_id
    if current_id and current_id != source.id:
        raise research.IntegrityError("citation endpoint is already resolved to another source")
    other_id = edge.cited_source_id if endpoint == "citing" else edge.citing_source_id
    if other_id == source.id:
        raise research.IntegrityError("citation resolution would create a self-edge")
    key = edge.citing_key if endpoint == "citing" else edge.cited_key
    if key.startswith(("doi:", "provider:")) and key not in _strong_source_keys(source):
        raise research.IntegrityError("source identifier conflicts with citation endpoint")
    if endpoint == "citing":
        edge.citing_source_id = source.id
    else:
        edge.cited_source_id = source.id
    edge.observations = [
        *(edge.observations or []),
        {
            "provider": "human",
            "direction": "identity_resolution",
            "endpoint": endpoint,
            "source_id": source.id,
            "observed_at": datetime.now(UTC).isoformat(),
            "review_note": review_note.strip(),
            "simulated": False,
        },
    ]
    _refresh_resolution(edge)
    session.flush()
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="resolve_citation_endpoint",
        object_type="citation_edge",
        object_id=edge.id,
        detail={"endpoint": endpoint, "source_id": source.id, "review_note": review_note.strip()},
    )
    return edge


def review_edge(
    session: Session,
    project_id: str,
    edge_id: str,
    *,
    state: CitationReview | str,
    review_note: str,
) -> CitationEdge:
    project = research._project(session, project_id)
    edge = session.get(CitationEdge, edge_id)
    if edge is None or edge.project_id != project_id or edge.deleted_at is not None:
        raise research.IntegrityError("citation edge not found in project")
    state = CitationReview(state)
    if state == CitationReview.PROVIDER_REPORTED:
        raise research.IntegrityError("human review state must be human_verified or rejected")
    if not review_note.strip():
        raise research.IntegrityError("citation review requires a human review note")
    edge.review_state = state
    edge.review_note = review_note.strip()
    edge.updated_at = utcnow()
    session.flush()
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="review_citation",
        object_type="citation_edge",
        object_id=edge.id,
        detail={"state": str(state), "review_note": edge.review_note, "discovery_only": True},
    )
    return edge


def citation_graph(
    session: Session,
    project_id: str,
    root_source_id: str,
    *,
    depth: int = 1,
    max_nodes: int = 100,
    include_rejected: bool = False,
) -> dict:
    research._project(session, project_id)
    root = session.get(Source, root_source_id)
    if root is None or root.project_id != project_id or root.deleted_at is not None:
        raise research.IntegrityError("root source not found in project")
    if depth < 1 or depth > 4:
        raise research.IntegrityError("citation graph depth must be between 1 and 4")
    if max_nodes < 2 or max_nodes > 500:
        raise research.IntegrityError("citation graph max_nodes must be between 2 and 500")

    all_edges = list(
        session.scalars(
            select(CitationEdge).where(
                CitationEdge.project_id == project_id,
                CitationEdge.deleted_at.is_(None),
            )
        )
    )
    if not include_rejected:
        all_edges = [edge for edge in all_edges if edge.review_state != CitationReview.REJECTED]
    frontier = {root.id}
    seen_sources = {root.id}
    included_edges: dict[str, CitationEdge] = {}
    unresolved: dict[str, dict] = {}
    truncated = False

    for _level in range(depth):
        next_frontier: set[str] = set()
        for edge in all_edges:
            if edge.citing_source_id not in frontier and edge.cited_source_id not in frontier:
                continue
            new_source_ids = {
                endpoint
                for endpoint in (edge.citing_source_id, edge.cited_source_id)
                if endpoint and endpoint not in seen_sources
            }
            new_unresolved_keys = {
                key
                for endpoint, key in (
                    (edge.citing_source_id, edge.citing_key),
                    (edge.cited_source_id, edge.cited_key),
                )
                if endpoint is None and key not in unresolved
            }
            if (
                len(seen_sources)
                + len(unresolved)
                + len(new_source_ids)
                + len(new_unresolved_keys)
                > max_nodes
            ):
                truncated = True
                continue
            included_edges[edge.id] = edge
            for endpoint, key, title in (
                (edge.citing_source_id, edge.citing_key, edge.citing_title),
                (edge.cited_source_id, edge.cited_key, edge.cited_title),
            ):
                if endpoint:
                    if endpoint not in seen_sources:
                        seen_sources.add(endpoint)
                        next_frontier.add(endpoint)
                else:
                    unresolved[key] = {
                        "node_id": f"unresolved:{key}",
                        "source_id": None,
                        "key": key,
                        "title": title,
                        "resolved": False,
                    }
        frontier = next_frontier
        if not frontier:
            break

    nodes = []
    for source_id in seen_sources:
        source = session.get(Source, source_id)
        if source is not None and source.deleted_at is None:
            nodes.append(
                {
                    "node_id": f"source:{source.id}",
                    "source_id": source.id,
                    "key": _source_key(source),
                    "title": source.title,
                    "doi": canonical_doi(source.doi),
                    "resolved": True,
                }
            )
    nodes.extend(unresolved.values())
    return {
        "root_source_id": root.id,
        "depth": depth,
        "nodes": sorted(nodes, key=lambda node: (not node["resolved"], node["title"])),
        "edges": [edge_out(session, edge) for edge in included_edges.values()],
        "truncated": truncated,
        "discovery_only": True,
    }


def repoint_source(
    session: Session, project_id: str, *, retained_source_id: str, duplicate_source_id: str
) -> dict:
    """Keep citation endpoints valid when the reviewed duplicate-source merge runs."""
    updated = 0
    self_edges_soft_deleted = 0
    edges = session.scalars(
        select(CitationEdge).where(
            CitationEdge.project_id == project_id,
            CitationEdge.deleted_at.is_(None),
            or_(
                CitationEdge.citing_source_id == duplicate_source_id,
                CitationEdge.cited_source_id == duplicate_source_id,
            ),
        )
    )
    for edge in edges:
        if edge.citing_source_id == duplicate_source_id:
            edge.citing_source_id = retained_source_id
        if edge.cited_source_id == duplicate_source_id:
            edge.cited_source_id = retained_source_id
        if edge.citing_source_id == edge.cited_source_id:
            edge.deleted_at = utcnow()
            self_edges_soft_deleted += 1
        else:
            _refresh_resolution(edge)
            updated += 1
    return {"citation_edges_updated": updated, "citation_self_edges_removed": self_edges_soft_deleted}
