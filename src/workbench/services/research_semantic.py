"""Opt-in local vector index in existing project-scoped Embedding rows."""

import hashlib
import json
import math

from sqlalchemy import select

from ..models import Embedding, stable_hash
from ..providers.embeddings import cosine
from ..providers.research_embeddings import MAX_TEXT_CHARS, SemanticUnavailable, get_local_provider

INDEX_VERSION = 1
MAX_INDEX_CARDS = 512
MATCH_THRESHOLD = 0.45
OVERLAP_THRESHOLD = 0.82


def search_text(card):
    # Filenames and JSON field names can dominate embeddings of short mathematical passages.
    text = card["text"]
    if card["kind"] in {"prior_finding", "recorded_search"}:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                text = "\n".join(str(data[k]) for k in
                    ("statement", "scope", "query", "coverage", "outcome") if data.get(k))
        except (TypeError, ValueError):
            pass
    return text[:MAX_TEXT_CHARS]


def identity(project_id, card):
    digest = hashlib.sha256(search_text(card).encode()).hexdigest()
    return stable_hash([project_id, card["kind"], digest])[:32], digest


def valid(vector, dimensions):
    return (isinstance(vector, list) and len(vector) == dimensions
            and all(type(n) in (int, float) and math.isfinite(n) and abs(n) <= 1.001 for n in vector)
            and abs(sum(n * n for n in vector) - 1) < .01)


def index_project(session, project_id):
    from .research_retrieval import collect

    cards, scan = collect(session, project_id)
    provider = get_local_provider()  # No API fallback and no automatic downloads.
    rows = list(session.scalars(select(Embedding).where(
        Embedding.project_id == project_id, Embedding.target_type == "research_card",
        Embedding.model == provider.model, Embedding.index_version == INDEX_VERSION)))
    existing = {r.target_id: r for r in rows}
    # Idempotent incremental batches eventually index the whole bounded corpus.
    current = {identity(project_id, c)[0]: (c, identity(project_id, c)[1]) for c in cards}
    pending = [(key, card, digest) for key, (card, digest) in sorted(current.items())
               if key not in existing or existing[key].text_hash != digest
               or not valid(existing[key].vector, provider.dimensions)]
    batch = pending[:MAX_INDEX_CARDS]
    vectors = provider.embed([search_text(c) for _, c, _ in batch]) if batch else []
    if len(vectors) != len(batch) or any(not valid(v, provider.dimensions) for v in vectors):
        raise ValueError("Invalid embedding batch; existing index retained")
    for (key, _, digest), vector in zip(batch, vectors, strict=True):
        row = existing.get(key)
        if row is None:
            row = Embedding(project_id=project_id, target_type="research_card", target_id=key,
                            model=provider.model, index_version=INDEX_VERSION)
            session.add(row)
        row.text_hash, row.vector = digest, vector
    for row in rows:
        if row.target_id not in current:
            session.delete(row)  # Only this project's obsolete research-card cache entries.
    session.flush()
    return {"model": provider.model, "embedded_now": len(batch),
            "reused": len(current) - len(pending), "remaining": len(pending) - len(batch),
            "scan": scan, "local_only": True, "input_character_limit": MAX_TEXT_CHARS}


def score(session, project_id, cards, queries):
    try:
        provider = get_local_provider()
    except SemanticUnavailable as exc:
        return {}, {}, {"status": "unavailable", "reason": str(exc), "local_only": True}
    rows = {r.target_id: r for r in session.scalars(select(Embedding).where(
        Embedding.project_id == project_id, Embedding.target_type == "research_card",
        Embedding.model == provider.model, Embedding.index_version == INDEX_VERSION))}
    vectors = {}
    for card in cards:
        key, digest = identity(project_id, card)
        row = rows.get(key)
        if row is not None and row.text_hash == digest and valid(row.vector, provider.dimensions):
            vectors[card["id"]] = row.vector
    metadata = {"status": "ready" if len(vectors) == len(cards) else "partial_index",
                "model": provider.model, "indexed_cards": len(vectors), "current_cards": len(cards),
                "local_only": True, "match_threshold": MATCH_THRESHOLD,
                "input_character_limit": MAX_TEXT_CHARS,
                "query_inputs_clipped": sum(len(q) > MAX_TEXT_CHARS for q in queries)}
    if not vectors:
        metadata["status"] = "index_required"
        return {}, {}, metadata
    qvectors = provider.embed([q[:MAX_TEXT_CHARS] for q in queries])
    if len(qvectors) != len(queries) or any(not valid(v, provider.dimensions) for v in qvectors):
        raise ValueError("Invalid semantic query vector")
    scores = {key: [cosine(q, v) for q in qvectors] for key, v in vectors.items()}
    return scores, vectors, metadata
