"""Research-graph services: projects, research objects, sources, excerpts, claims.

Integrity rules enforced here (not left to the UI):
- Source rows must state access level; full-text access levels require an acquisition note.
- Excerpts are checksummed and carry a locator.
- Claims whose support involves an external source must link at least one excerpt;
  claims supported by project research must link at least one research object.
- AI-suggested objects stay ai_suggested=True until a human accepts them.
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import (
    Claim,
    ClaimEvidence,
    Edge,
    Excerpt,
    Project,
    ResearchObject,
    Source,
    Workspace,
)
from ..vocab import ClaimSupport, ObjectKind, Relation, SourceAccess

FULL_TEXT_LEVELS = {SourceAccess.FULL_TEXT_AUTHORIZED, SourceAccess.FULL_TEXT_USER_SUPPLIED}


class IntegrityError(ValueError):
    """A domain integrity rule was violated; the mutation is rejected."""


def create_workspace(session: Session, name: str) -> Workspace:
    ws = Workspace(name=name)
    session.add(ws)
    session.flush()
    record_audit(
        session, workspace_id=ws.id, actor="user", action="create",
        object_type="workspace", object_id=ws.id, detail={"name": name},
    )
    return ws


def create_project(session: Session, workspace_id: str, name: str, description: str = "") -> Project:
    if session.get(Workspace, workspace_id) is None:
        raise IntegrityError("workspace not found")
    project = Project(workspace_id=workspace_id, name=name, description=description)
    session.add(project)
    session.flush()
    record_audit(
        session, workspace_id=workspace_id, actor="user", action="create",
        object_type="project", object_id=project.id, detail={"name": name},
    )
    return project


def _project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise IntegrityError("project not found")
    return project


def create_object(
    session: Session,
    project_id: str,
    *,
    kind: ObjectKind | str,
    title: str,
    body: dict | None = None,
    strength: str | None = None,
    ai_suggested: bool = False,
    actor: str = "user",
) -> ResearchObject:
    project = _project(session, project_id)
    obj = ResearchObject(
        project_id=project_id,
        kind=ObjectKind(kind),
        title=title,
        body=body or {},
        strength=strength,
        ai_suggested=ai_suggested,
        accepted_by_user=not ai_suggested,
    )
    session.add(obj)
    session.flush()
    record_audit(
        session, workspace_id=project.workspace_id, actor=actor, action="create",
        object_type="research_object", object_id=obj.id,
        detail={"kind": str(obj.kind), "title": title, "ai_suggested": ai_suggested},
    )
    return obj


def accept_object(session: Session, object_id: str) -> ResearchObject:
    obj = session.get(ResearchObject, object_id)
    if obj is None:
        raise IntegrityError("object not found")
    obj.accepted_by_user = True
    project = _project(session, obj.project_id)
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="accept",
        object_type="research_object", object_id=obj.id, detail={},
    )
    return obj


def link_objects(
    session: Session, project_id: str, src_id: str, dst_id: str,
    relation: Relation | str, note: str = "", actor: str = "user",
) -> Edge:
    project = _project(session, project_id)
    for oid in (src_id, dst_id):
        obj = session.get(ResearchObject, oid)
        if obj is None or obj.project_id != project_id:
            raise IntegrityError(f"object {oid} not in project")
    edge = Edge(
        project_id=project_id, src_id=src_id, dst_id=dst_id,
        relation=Relation(relation), note=note,
    )
    session.add(edge)
    session.flush()
    record_audit(
        session, workspace_id=project.workspace_id, actor=actor, action="link",
        object_type="edge", object_id=edge.id,
        detail={"src": src_id, "dst": dst_id, "relation": str(edge.relation)},
    )
    return edge


def register_source(
    session: Session,
    project_id: str,
    *,
    title: str,
    access: SourceAccess | str,
    acquisition: str = "",
    authors: str = "",
    year: int | None = None,
    venue: str = "",
    doi: str | None = None,
    url: str | None = None,
    license: str = "unknown",
    provider_metadata: dict | None = None,
) -> Source:
    project = _project(session, project_id)
    access = SourceAccess(access)
    if access in FULL_TEXT_LEVELS and not acquisition.strip():
        raise IntegrityError(
            "full-text access levels require an acquisition note (how the text was lawfully obtained)"
        )
    source = Source(
        project_id=project_id, title=title, authors=authors, year=year, venue=venue,
        doi=doi, url=url, access=access, license=license, acquisition=acquisition,
        provider_metadata=provider_metadata or {},
    )
    session.add(source)
    session.flush()
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="register",
        object_type="source", object_id=source.id,
        detail={"title": title, "access": str(access), "doi": doi},
    )
    return source


def capture_excerpt(
    session: Session, source_id: str, *, text: str, locator: str
) -> Excerpt:
    source = session.get(Source, source_id)
    if source is None:
        raise IntegrityError("source not found")
    if not locator.strip():
        raise IntegrityError("excerpts require a durable locator (page/section/offset)")
    if source.access == SourceAccess.METADATA_ONLY:
        raise IntegrityError("cannot capture an excerpt from a metadata-only source")
    excerpt = Excerpt(
        source_id=source_id, text=text, locator=locator,
        checksum=hashlib.sha256(text.encode()).hexdigest(),
    )
    session.add(excerpt)
    session.flush()
    project = _project(session, source.project_id)
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="capture",
        object_type="excerpt", object_id=excerpt.id,
        detail={"source_id": source_id, "locator": locator},
    )
    return excerpt


def create_claim(
    session: Session,
    project_id: str,
    *,
    text: str,
    support: ClaimSupport | str,
    excerpt_ids: list[str] | None = None,
    research_object_ids: list[str] | None = None,
    notes: str = "",
) -> Claim:
    project = _project(session, project_id)
    support = ClaimSupport(support)
    excerpt_ids = excerpt_ids or []
    research_object_ids = research_object_ids or []

    needs_source = support in {ClaimSupport.EXTERNAL_SOURCE, ClaimSupport.BOTH}
    needs_result = support in {ClaimSupport.RESEARCH_RESULT, ClaimSupport.BOTH}
    if needs_source and not excerpt_ids:
        raise IntegrityError(f"support '{support}' requires at least one excerpt link")
    if needs_result and not research_object_ids:
        raise IntegrityError(f"support '{support}' requires at least one research-object link")

    for eid in excerpt_ids:
        excerpt = session.get(Excerpt, eid)
        if excerpt is None:
            raise IntegrityError(f"excerpt {eid} not found")
        source = session.get(Source, excerpt.source_id)
        if source is None or source.project_id != project_id:
            raise IntegrityError(f"excerpt {eid} does not belong to this project")
    for oid in research_object_ids:
        obj = session.get(ResearchObject, oid)
        if obj is None or obj.project_id != project_id:
            raise IntegrityError(f"research object {oid} not in project")

    claim = Claim(project_id=project_id, text=text, support=support, notes=notes)
    session.add(claim)
    session.flush()
    for eid in excerpt_ids:
        session.add(ClaimEvidence(claim_id=claim.id, excerpt_id=eid))
    for oid in research_object_ids:
        session.add(ClaimEvidence(claim_id=claim.id, research_object_id=oid))
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="create",
        object_type="claim", object_id=claim.id,
        detail={"support": str(support), "excerpts": excerpt_ids, "objects": research_object_ids},
    )
    return claim


def claim_evidence(session: Session, claim_id: str) -> list[ClaimEvidence]:
    return list(
        session.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim_id))
    )
