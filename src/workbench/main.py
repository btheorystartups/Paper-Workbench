"""FastAPI surface (thin: validation + service calls; all rules live in services).

Run: uvicorn workbench.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import db
from .config import get_settings
from .models import Claim, ProposedAction, ResearchObject, Source, Thread, Turn
from .services import audits, authoring, dialogue, export_service, literature, research
from .vocab import ClaimSupport, Novelty, ObjectKind, SourceAccess


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.create_all()
    yield


app = FastAPI(title="Paper-Workbench", version="0.1.0", lifespan=lifespan)


def _session():
    yield from db.get_session()


@app.get("/health")
def health():
    settings = get_settings()
    return {"status": "ok", "provider_mode": settings.provider_mode}


# --- workspaces / projects ---


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@app.post("/workspaces")
def create_workspace(body: WorkspaceIn, session: Session = Depends(_session)):
    ws = research.create_workspace(session, body.name)
    session.commit()
    return {"id": ws.id, "name": ws.name}


class ProjectIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


@app.post("/projects")
def create_project(body: ProjectIn, session: Session = Depends(_session)):
    try:
        project = research.create_project(session, body.workspace_id, body.name, body.description)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": project.id, "name": project.name}


# --- research objects ---


class ObjectIn(BaseModel):
    kind: ObjectKind
    title: str = Field(min_length=1, max_length=500)
    body: dict = Field(default_factory=dict)
    strength: str | None = None


@app.post("/projects/{project_id}/objects")
def create_object(project_id: str, body: ObjectIn, session: Session = Depends(_session)):
    try:
        obj = research.create_object(
            session, project_id, kind=body.kind, title=body.title,
            body=body.body, strength=body.strength,
        )
    except (research.IntegrityError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(obj)


@app.get("/projects/{project_id}/objects")
def list_objects(project_id: str, session: Session = Depends(_session)):
    rows = session.scalars(
        select(ResearchObject).where(
            ResearchObject.project_id == project_id, ResearchObject.deleted_at.is_(None)
        )
    )
    return [_object_out(o) for o in rows]


def _object_out(o: ResearchObject) -> dict:
    return {
        "id": o.id, "kind": str(o.kind), "title": o.title, "body": o.body,
        "strength": o.strength, "ai_suggested": o.ai_suggested,
        "accepted_by_user": o.accepted_by_user,
    }


# --- sources / excerpts / claims ---


class SourceIn(BaseModel):
    title: str
    access: SourceAccess
    acquisition: str = ""
    authors: str = ""
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    url: str | None = None
    license: str = "unknown"


@app.post("/projects/{project_id}/sources")
def register_source(project_id: str, body: SourceIn, session: Session = Depends(_session)):
    try:
        source = research.register_source(session, project_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": source.id, "title": source.title, "access": str(source.access)}


class IngestIn(BaseModel):
    path: str
    title: str | None = None
    license: str = "author-owned"


@app.post("/projects/{project_id}/ingest")
def ingest_local_file(project_id: str, body: IngestIn, session: Session = Depends(_session)):
    """Ingest a local file (single-user local deployment; the path is the user's own disk)."""
    from .ingest.files import IngestError, ingest_file

    try:
        source = ingest_file(
            session, project_id, body.path, title=body.title, license=body.license
        )
    except (IngestError, research.IntegrityError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {
        "id": source.id,
        "title": source.title,
        "access": str(source.access),
        "ingest": source.provider_metadata["ingest"],
    }


class ExcerptIn(BaseModel):
    text: str = Field(min_length=1)
    locator: str = Field(min_length=1)


@app.post("/sources/{source_id}/excerpts")
def capture_excerpt(source_id: str, body: ExcerptIn, session: Session = Depends(_session)):
    try:
        excerpt = research.capture_excerpt(
            session, source_id, text=body.text, locator=body.locator
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": excerpt.id, "locator": excerpt.locator, "checksum": excerpt.checksum}


class ClaimIn(BaseModel):
    text: str
    support: ClaimSupport
    excerpt_ids: list[str] = Field(default_factory=list)
    research_object_ids: list[str] = Field(default_factory=list)
    notes: str = ""


@app.post("/projects/{project_id}/claims")
def create_claim(project_id: str, body: ClaimIn, session: Session = Depends(_session)):
    try:
        claim = research.create_claim(session, project_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": claim.id, "support": str(claim.support)}


@app.get("/claims/{claim_id}/evidence")
def claim_evidence(claim_id: str, session: Session = Depends(_session)):
    if session.get(Claim, claim_id) is None:
        raise HTTPException(404, "claim not found")
    return [
        {
            "id": ev.id, "excerpt_id": ev.excerpt_id,
            "research_object_id": ev.research_object_id, "entailment": ev.entailment,
        }
        for ev in research.claim_evidence(session, claim_id)
    ]


# --- dialogue ---


class ThreadIn(BaseModel):
    title: str
    goal: str = ""
    pinned_object_ids: list[str] = Field(default_factory=list)
    pinned_source_ids: list[str] = Field(default_factory=list)


@app.post("/projects/{project_id}/threads")
def create_thread(project_id: str, body: ThreadIn, session: Session = Depends(_session)):
    try:
        thread = dialogue.create_thread(session, project_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": thread.id, "title": thread.title}


class TurnIn(BaseModel):
    content: str = Field(min_length=1)


@app.post("/threads/{thread_id}/turns")
def post_turn(thread_id: str, body: TurnIn, session: Session = Depends(_session)):
    try:
        _user, assistant = dialogue.post_user_turn(session, thread_id, body.content)
    except dialogue.DialogueError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    actions = session.scalars(
        select(ProposedAction).where(
            ProposedAction.thread_id == thread_id, ProposedAction.status == "proposed"
        )
    )
    return {
        "assistant": {
            "id": assistant.id, "content": assistant.content,
            "provenance": assistant.provenance,
        },
        "proposed_actions": [
            {"id": a.id, "kind": a.kind, "risk": a.risk, "payload": a.payload,
             "plan_hash": a.plan_hash}
            for a in actions
        ],
    }


@app.get("/threads/{thread_id}/turns")
def list_turns(thread_id: str, session: Session = Depends(_session)):
    if session.get(Thread, thread_id) is None:
        raise HTTPException(404, "thread not found")
    rows = session.scalars(
        select(Turn).where(Turn.thread_id == thread_id).order_by(Turn.created_at, Turn.id)
    )
    return [
        {"id": t.id, "role": t.role, "content": t.content, "provenance": t.provenance}
        for t in rows
    ]


# --- literature (P3) ---


class LitSearchIn(BaseModel):
    provider: str = "openalex"  # openalex | crossref
    query: str = Field(min_length=1)
    count: int = Field(default=10, ge=1, le=50)


@app.post("/projects/{project_id}/literature/search")
def literature_search(project_id: str, body: LitSearchIn, session: Session = Depends(_session)):
    try:
        saved, works = literature.run_search(
            session, project_id, provider=body.provider, query=body.query, count=body.count
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {
        "saved_search_id": saved.id,
        "works": [
            {
                "title": w.title, "authors": w.authors, "year": w.year, "venue": w.venue,
                "doi": w.doi, "url": w.url, "cited_by_count": w.cited_by_count,
                "has_abstract": bool(w.abstract), "provider": w.provider,
                "provider_id": w.provider_id,
            }
            for w in works
        ],
    }


class LitImportIn(BaseModel):
    provider: str
    query: str
    provider_id: str


@app.post("/projects/{project_id}/literature/import")
def literature_import(project_id: str, body: LitImportIn, session: Session = Depends(_session)):
    """Re-runs the search (cached/fake-safe) and imports the selected work by provider_id."""
    adapter = literature.get_scholarly_provider(body.provider)
    works = [w for w in adapter.search(body.query, count=25) if w.provider_id == body.provider_id]
    if not works:
        raise HTTPException(404, "work not found in search results")
    try:
        source, created = literature.import_work(session, project_id, works[0])
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"source_id": source.id, "created": created, "access": str(source.access)}


class ScreenIn(BaseModel):
    source_id: str
    state: str | None = None
    reason: str | None = None
    relationship: str | None = None
    question: str | None = None
    method: str | None = None
    result_summary: str | None = None
    limitations: str | None = None
    relevance: str | None = None


@app.post("/projects/{project_id}/literature/screen")
def literature_screen(project_id: str, body: ScreenIn, session: Session = Depends(_session)):
    data = body.model_dump()
    source_id = data.pop("source_id")
    try:
        entry = literature.set_screening(session, project_id, source_id, **data)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": entry.id, "state": entry.state}


@app.get("/projects/{project_id}/literature/matrix")
def get_literature_matrix(project_id: str, session: Session = Depends(_session)):
    return literature.literature_matrix(session, project_id)


class ContributionIn(BaseModel):
    title: str
    statement: str
    novelty: Novelty
    coverage_note: str
    closest_prior_source_ids: list[str] = Field(default_factory=list)


@app.post("/projects/{project_id}/contributions")
def assess_contribution(project_id: str, body: ContributionIn, session: Session = Depends(_session)):
    try:
        obj = literature.assess_contribution(session, project_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(obj)


# --- authoring (P4) ---


class CandidateIn(BaseModel):
    title: str
    paper_type: str
    central_question: str
    thesis: str
    audience: str = ""
    structure: str = "imrad"
    included_object_ids: list[str] = Field(default_factory=list)
    novelty_caveat: str = ""
    risks: str = ""
    missing_work: list[str] = Field(default_factory=list)


@app.post("/projects/{project_id}/paper-candidates")
def create_candidate(project_id: str, body: CandidateIn, session: Session = Depends(_session)):
    try:
        obj = authoring.create_paper_candidate(session, project_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(obj)


class ManuscriptIn(BaseModel):
    title: str
    from_candidate_id: str | None = None


@app.post("/projects/{project_id}/manuscripts")
def create_manuscript(project_id: str, body: ManuscriptIn, session: Session = Depends(_session)):
    try:
        obj = authoring.create_manuscript(session, project_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(obj)


class SectionIn(BaseModel):
    heading: str
    purpose: str = ""
    text: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    word_budget: int | None = None
    position: int | None = None


@app.post("/manuscripts/{manuscript_id}/sections")
def add_section(manuscript_id: str, body: SectionIn, session: Session = Depends(_session)):
    try:
        obj = authoring.add_section(session, manuscript_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(obj)


# --- audits + export (P5/P6) ---


@app.get("/manuscripts/{manuscript_id}/audit")
def run_audit(manuscript_id: str, session: Session = Depends(_session)):
    try:
        findings = audits.audit_manuscript(session, manuscript_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"findings": findings, "counts": _severity_counts(findings)}


def _severity_counts(findings: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return counts


@app.post("/manuscripts/{manuscript_id}/skeptical-review")
def run_skeptical_review(manuscript_id: str, session: Session = Depends(_session)):
    try:
        notes = audits.skeptical_review(session, manuscript_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return {"objections": [_object_out(n) for n in notes]}


class ExportIn(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["md", "tex", "html", "docx", "bib"])


@app.post("/manuscripts/{manuscript_id}/export")
def export_manuscript(manuscript_id: str, body: ExportIn, session: Session = Depends(_session)):
    try:
        result = export_service.export_manuscript(
            session, manuscript_id, formats=body.formats
        )
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return result


class ApproveIn(BaseModel):
    plan_hash: str


@app.post("/actions/{action_id}/approve")
def approve_action(action_id: str, body: ApproveIn, session: Session = Depends(_session)):
    try:
        action = dialogue.approve_action(session, action_id, plan_hash=body.plan_hash)
    except dialogue.DialogueError as exc:
        session.commit()  # persist invalidation if it happened
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return {"id": action.id, "status": str(action.status), "result": action.result}


@app.post("/actions/{action_id}/reject")
def reject_action(action_id: str, session: Session = Depends(_session)):
    try:
        action = dialogue.reject_action(session, action_id)
    except dialogue.DialogueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return {"id": action.id, "status": str(action.status)}
