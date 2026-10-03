"""Section-scoped context and optimistic, review-gated prose revisions.

Only linked evidence is included. Source metadata is labelled as metadata, and accepting
prose never changes a claim's support, evidence entailment, or research acceptance state.
"""

import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import (
    Claim,
    ClaimEvidence,
    Edge,
    Excerpt,
    ResearchObject,
    Source,
    Thread,
    stable_hash,
    utcnow,
)
from ..vocab import ObjectKind, Relation, SourceAccess

MAX_CONTEXT_CHARS = 80_000
MAX_SECTION_CHARS = 30_000


class ManuscriptChatError(ValueError):
    pass


def _object(session: Session, object_id: str, project_id: str, kind=None) -> ResearchObject:
    obj = session.get(ResearchObject, object_id, populate_existing=True)
    if (obj is None or obj.deleted_at is not None or obj.project_id != project_id
            or (kind is not None and obj.kind != kind)):
        raise ManuscriptChatError("manuscript context not found in this project")
    return obj


def selected_section(session: Session, thread: Thread) -> tuple[ResearchObject, ResearchObject]:
    if not thread.manuscript_id or not thread.section_id:
        raise ManuscriptChatError("select a manuscript and section first")
    manuscript = _object(session, thread.manuscript_id, thread.project_id, ObjectKind.MANUSCRIPT)
    section = _object(session, thread.section_id, thread.project_id, ObjectKind.SECTION)
    edge = session.scalar(select(Edge.id).where(
        Edge.project_id == thread.project_id, Edge.src_id == section.id,
        Edge.dst_id == manuscript.id, Edge.relation == Relation.PART_OF,
        Edge.deleted_at.is_(None),
    ))
    if section.id not in manuscript.body.get("section_order", []) or edge is None:
        raise ManuscriptChatError("section is not part of this manuscript")
    return manuscript, section


def section_hash(section: ResearchObject) -> str:
    return stable_hash({"title": section.title, "body": section.body,
                        "updated_at": section.updated_at, "deleted_at": section.deleted_at})


def context(session: Session, thread: Thread) -> dict:
    """An inspectable snapshot, used unchanged for both prompting and proposal binding."""
    if not thread.manuscript_id and not thread.section_id:
        return {"items": [], "warnings": [], "context_hash": None}
    manuscript, section = selected_section(session, thread)
    items: dict[str, dict] = {}
    warnings: list[str] = []

    def add(identifier, kind, title, data):
        items[identifier] = {"id": identifier, "kind": kind, "title": title, "data": data}

    def add_object(obj):
        add(obj.id, str(obj.kind), obj.title, {
            "body": obj.body, "ai_suggested": obj.ai_suggested,
            "accepted_by_user": obj.accepted_by_user, "strength": obj.strength,
        })

    outline = []
    for sid in manuscript.body.get("section_order", []):
        other = session.get(ResearchObject, sid)
        if (other and other.project_id == thread.project_id and other.deleted_at is None
                and other.kind == ObjectKind.SECTION):
            outline.append({"id": sid, "heading": other.title,
                            "purpose": other.body.get("purpose", "")})
    add(manuscript.id, "manuscript", manuscript.title, {"outline": outline})
    add_object(section)
    for cid in section.body.get("claim_ids", []):
        claim = session.get(Claim, cid, populate_existing=True)
        if not claim or claim.deleted_at is not None or claim.project_id != thread.project_id:
            warnings.append("A linked claim is unavailable; no support may be inferred from it.")
            continue
        add(claim.id, "claim", claim.text, {"support": claim.support, "notes": claim.notes})
        evidence = session.scalars(select(ClaimEvidence).where(
            ClaimEvidence.claim_id == claim.id, ClaimEvidence.deleted_at.is_(None)
        ).order_by(ClaimEvidence.id)).all()
        if not evidence:
            warnings.append(f"Claim {claim.id} has no linked evidence.")
        for link in evidence:
            if link.research_object_id:
                obj = session.get(ResearchObject, link.research_object_id, populate_existing=True)
                if obj and obj.project_id == thread.project_id and obj.deleted_at is None:
                    add_object(obj)
                    add(link.id, "evidence_link", "Claim to research object", {
                        "claim_id": claim.id, "object_id": obj.id, "entailment": link.entailment,
                    })
                else:
                    warnings.append(f"Claim {claim.id} has an unavailable evidence object.")
            if link.excerpt_id:
                excerpt = session.get(Excerpt, link.excerpt_id, populate_existing=True)
                source = session.get(Source, excerpt.source_id, populate_existing=True) if excerpt else None
                if (not excerpt or excerpt.deleted_at is not None or not source
                        or source.deleted_at is not None or source.project_id != thread.project_id):
                    warnings.append(f"Claim {claim.id} has an unavailable source excerpt.")
                    continue
                add(source.id, "source_metadata", source.title, {
                    "authors": source.authors, "year": source.year, "doi": source.doi,
                    "access": source.access, "human_verified": source.human_verified,
                    "integrity_note": source.integrity_note,
                    "notice": "Bibliographic metadata alone does not substantiate the claim.",
                })
                if source.access == SourceAccess.METADATA_ONLY:
                    warnings.append(f"Source {source.id} is metadata-only; excerpt withheld.")
                    continue
                add(excerpt.id, "excerpt", excerpt.locator, {
                    "source_id": source.id, "text": excerpt.text, "checksum": excerpt.checksum,
                    "locator": excerpt.locator,
                })
                add(link.id, "evidence_link", "Claim to source excerpt", {
                    "claim_id": claim.id, "excerpt_id": excerpt.id, "entailment": link.entailment,
                })
    snapshot = {"items": list(items.values()), "warnings": warnings,
                "section_hash": section_hash(section)}
    if len(json.dumps(snapshot, ensure_ascii=False)) > MAX_CONTEXT_CHARS:
        raise ManuscriptChatError("section context is too large; narrow its linked evidence first")
    return {**snapshot, "context_hash": stable_hash(snapshot), "section_id": section.id,
            "manuscript_id": manuscript.id}


def revision_payload(thread: Thread, snapshot: dict, text: str) -> dict:
    if not isinstance(text, str) or len(text) > MAX_SECTION_CHARS:
        raise ManuscriptChatError(f"replacement text must be at most {MAX_SECTION_CHARS} characters")
    if not snapshot.get("section_id"):
        raise ManuscriptChatError("section revision requires manuscript context")
    section = next(item for item in snapshot["items"] if item["id"] == thread.section_id)
    return {
        "manuscript_id": thread.manuscript_id, "section_id": thread.section_id,
        "before_text": section["data"]["body"].get("text", ""), "text": text,
        "section_hash": snapshot["section_hash"], "context_hash": snapshot["context_hash"],
    }


def apply_revision(session: Session, thread: Thread, payload: dict) -> dict:
    snapshot = context(session, thread)
    if (payload.get("section_id") != thread.section_id
            or payload.get("manuscript_id") != thread.manuscript_id
            or payload.get("context_hash") != snapshot["context_hash"]
            or payload.get("section_hash") != snapshot["section_hash"]):
        raise ManuscriptChatError("section or evidence changed; request a fresh proposal")
    revision_payload(thread, snapshot, payload.get("text"))  # validate the replacement again
    _, section = selected_section(session, thread)
    changed = session.execute(update(ResearchObject).where(
        ResearchObject.id == section.id, ResearchObject.project_id == thread.project_id,
        ResearchObject.updated_at == section.updated_at, ResearchObject.deleted_at.is_(None),
    ).values(body={**section.body, "text": payload["text"]}, updated_at=utcnow())
      .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise ManuscriptChatError("section changed during approval; request a fresh proposal")
    session.refresh(section)
    return {"section_id": section.id, "before_text": payload["before_text"],
            "after_text": payload["text"], "after_section_hash": section_hash(section)}
