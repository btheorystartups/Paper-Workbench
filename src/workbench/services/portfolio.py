"""Cross-project research memory (workspace-scoped; strict isolation between
workspaces). Finds unpublished/uncited results, traces result usage, reruns saved
searches, and searches titles across a workspace's projects."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Claim, ClaimEvidence, Project, ResearchObject, SavedSearch, Source
from ..vocab import ObjectKind
from . import literature, research


def _workspace_projects(session: Session, workspace_id: str) -> list[Project]:
    return list(
        session.scalars(
            select(Project).where(
                Project.workspace_id == workspace_id, Project.deleted_at.is_(None)
            )
        )
    )


def unpublished_results(session: Session, workspace_id: str) -> list[dict]:
    """Results in the workspace not cited by any claim (i.e. never used in a manuscript
    path). A lead list, not a judgment."""
    out = []
    for project in _workspace_projects(session, workspace_id):
        cited_object_ids = {
            ev.research_object_id
            for ev in session.scalars(
                select(ClaimEvidence)
                .join(Claim, Claim.id == ClaimEvidence.claim_id)
                .where(Claim.project_id == project.id)
            )
            if ev.research_object_id
        }
        for obj in session.scalars(
            select(ResearchObject).where(
                ResearchObject.project_id == project.id,
                ResearchObject.kind == ObjectKind.RESULT,
                ResearchObject.deleted_at.is_(None),
            )
        ):
            if obj.id not in cited_object_ids:
                out.append(
                    {"project_id": project.id, "project": project.name,
                     "object_id": obj.id, "title": obj.title, "strength": obj.strength}
                )
    return out


def result_usage(session: Session, object_id: str) -> dict:
    """Trace where a research object is used: claims citing it, and sections citing
    those claims."""
    obj = session.get(ResearchObject, object_id)
    if obj is None:
        raise research.IntegrityError("object not found")
    claim_ids = [
        ev.claim_id
        for ev in session.scalars(
            select(ClaimEvidence).where(ClaimEvidence.research_object_id == object_id)
        )
    ]
    sections = []
    for section in session.scalars(
        select(ResearchObject).where(
            ResearchObject.kind == ObjectKind.SECTION,
            ResearchObject.project_id == obj.project_id,
        )
    ):
        used = set(section.body.get("claim_ids", [])) & set(claim_ids)
        if used:
            sections.append({"section_id": section.id, "heading": section.title,
                             "via_claims": sorted(used)})
    return {"object_id": object_id, "title": obj.title,
            "claims": claim_ids, "sections": sections}


def rerun_saved_search(session: Session, saved_search_id: str):
    saved = session.get(SavedSearch, saved_search_id)
    if saved is None:
        raise research.IntegrityError("saved search not found")
    return literature.run_search(
        session, saved.project_id, provider=saved.provider, query=saved.query,
        count=saved.filters.get("count", 10),
    )


def workspace_search(session: Session, workspace_id: str, query: str) -> list[dict]:
    """Keyword title search across all projects in ONE workspace (never across
    workspaces — that is the isolation boundary)."""
    q = query.lower().strip()
    out = []
    for project in _workspace_projects(session, workspace_id):
        for obj in session.scalars(
            select(ResearchObject).where(
                ResearchObject.project_id == project.id,
                ResearchObject.deleted_at.is_(None),
            )
        ):
            if q in obj.title.lower():
                out.append({"type": "object", "project": project.name,
                            "project_id": project.id, "id": obj.id,
                            "kind": str(obj.kind), "title": obj.title})
        for src in session.scalars(
            select(Source).where(
                Source.project_id == project.id, Source.deleted_at.is_(None)
            )
        ):
            if q in src.title.lower():
                out.append({"type": "source", "project": project.name,
                            "project_id": project.id, "id": src.id,
                            "kind": "source", "title": src.title})
    return out
