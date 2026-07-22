"""Semantic indexing/retrieval (project-scoped). Results always carry
kind="similarity" labeling — a match is a lead to inspect, never evidence.
Index entries are versioned per model; reindex_project() rebuilds cleanly.
"""

import hashlib

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Embedding, ResearchObject, Source
from ..providers.embeddings import cosine, get_embedding_provider
from . import research

INDEX_VERSION = 1


def _object_text(obj: ResearchObject) -> str:
    return f"{obj.kind}: {obj.title}. {obj.body}"


def _source_text(src: Source) -> str:
    abstract = (src.provider_metadata or {}).get("scholarly", {}).get("abstract") or ""
    return f"source: {src.title}. {src.authors} {src.venue} {abstract}"


def index_project(session: Session, project_id: str) -> dict:
    """(Re)index all live objects+sources of a project with the current provider/model."""
    research._project(session, project_id)
    provider = get_embedding_provider()
    targets: list[tuple[str, str, str]] = []
    for obj in session.scalars(
        select(ResearchObject).where(
            ResearchObject.project_id == project_id, ResearchObject.deleted_at.is_(None)
        )
    ):
        targets.append(("object", obj.id, _object_text(obj)))
    for src in session.scalars(
        select(Source).where(Source.project_id == project_id, Source.deleted_at.is_(None))
    ):
        targets.append(("source", src.id, _source_text(src)))
    session.execute(
        delete(Embedding).where(
            Embedding.project_id == project_id,
            Embedding.model == provider.model,
            Embedding.index_version == INDEX_VERSION,
        )
    )
    if targets:
        from ..config import get_settings
        from . import usage as usage_service

        if get_settings().provider_mode == "live":
            usage_service.check_budget(session, project_id)
        vectors = provider.embed([t[2] for t in targets])
        usage_service.record_usage(
            session, project_id, provider="embeddings", model=provider.model,
            kind="embedding_index", usage={},  # embed API returns no usage; count of calls only
            simulated=get_settings().provider_mode != "live",
        )
        for (ttype, tid, text), vec in zip(targets, vectors, strict=True):
            session.add(
                Embedding(
                    project_id=project_id, target_type=ttype, target_id=tid,
                    model=provider.model, index_version=INDEX_VERSION, vector=vec,
                    text_hash=hashlib.sha256(text.encode()).hexdigest(),
                )
            )
    return {"indexed": len(targets), "model": provider.model, "index_version": INDEX_VERSION}


def semantic_search(session: Session, project_id: str, query: str, *, top_k: int = 8) -> list[dict]:
    provider = get_embedding_provider()
    [qvec] = provider.embed([query])
    rows = list(
        session.scalars(
            select(Embedding).where(
                Embedding.project_id == project_id,
                Embedding.model == provider.model,
                Embedding.index_version == INDEX_VERSION,
            )
        )
    )
    scored = sorted(
        ((cosine(qvec, r.vector), r) for r in rows), key=lambda t: t[0], reverse=True
    )[:top_k]
    out = []
    for score, row in scored:
        title = None
        if row.target_type == "object":
            obj = session.get(ResearchObject, row.target_id)
            title = obj.title if obj else None
        else:
            src = session.get(Source, row.target_id)
            title = src.title if src else None
        if title is None:
            continue
        out.append(
            {
                "kind": "similarity",  # never evidence
                "target_type": row.target_type,
                "target_id": row.target_id,
                "title": title,
                "score": round(score, 4),
                "model": row.model,
            }
        )
    return out
