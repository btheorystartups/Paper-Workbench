"""FastAPI surface (thin: validation + service calls; all rules live in services).

Run: uvicorn workbench.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, db
from .config import get_settings
from .models import Claim, ProposedAction, ResearchObject, Source, Thread, Turn
from .services import (
    audits,
    authoring,
    dialogue,
    export_service,
    figures,
    literature,
    outputs,
    paper_design,
    portfolio,
    research,
    security,
    semantic,
    submissions,
    venues,
)
from .vocab import ClaimSupport, Novelty, ObjectKind, SourceAccess


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Alembic is the schema source of truth; this builds a fresh DB or migrates a managed
    # one. (Tests call db.create_all() directly for speed.)
    db.upgrade_to_head()
    yield


app = FastAPI(title="Paper-Workbench", version="0.1.0", lifespan=lifespan)

_STATIC_DIR = __import__("pathlib").Path(__file__).parent / "web" / "static"
if _STATIC_DIR.is_dir():
    from fastapi.responses import RedirectResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def _root():
        return RedirectResponse("/ui/")


def _session():
    yield from db.get_session()


def _principal(
    session: Session = Depends(_session),
    authorization: str | None = Header(default=None),
):
    """Resolve the acting user from an optional `Authorization: Bearer <token>` header.
    In local mode (auth_required=false) an absent token yields the default local user."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    try:
        return auth.principal_from_bearer(session, token)
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc


def _require(session, project_id: str, user, minimum: str) -> None:
    """Enforce a project role — but only when auth is switched on. In local single-user
    mode this is a no-op so the workbench stays frictionless."""
    if not get_settings().auth_required:
        return
    try:
        security.require_role(session, project_id, user.id, minimum)
    except security.Forbidden as exc:
        raise HTTPException(403, str(exc)) from exc


# --- auth endpoints ---


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)


@app.post("/auth/register")
def auth_register(body: RegisterIn, session: Session = Depends(_session)):
    try:
        user = auth.register_local_user(
            session, name=body.name, email=body.email, password=body.password
        )
    except auth.AuthError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return {"id": user.id, "name": user.name, "email": user.email}


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/auth/login")
def auth_login(body: LoginIn, session: Session = Depends(_session)):
    try:
        user, token = auth.login_password(session, email=body.email, password=body.password)
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    session.commit()
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


class OidcLoginIn(BaseModel):
    id_token: str


@app.post("/auth/oidc/login")
def auth_oidc_login(body: OidcLoginIn, session: Session = Depends(_session)):
    try:
        user, token = auth.login_oidc(session, body.id_token)
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    session.commit()
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@app.get("/auth/me")
def auth_me(user=Depends(_principal)):
    return {"id": user.id, "name": user.name, "email": user.email,
            "oidc_linked": bool(user.oidc_subject)}


@app.get("/health")
def health():
    settings = get_settings()
    return {"status": "ok", "provider_mode": settings.provider_mode}


@app.get("/workspaces")
def list_workspaces(session: Session = Depends(_session)):
    from .models import Workspace

    return [
        {"id": w.id, "name": w.name}
        for w in session.scalars(select(Workspace).where(Workspace.deleted_at.is_(None)))
    ]


@app.get("/workspaces/{workspace_id}/projects")
def list_projects(workspace_id: str, session: Session = Depends(_session)):
    from .models import Project

    return [
        {"id": p.id, "name": p.name, "description": p.description}
        for p in session.scalars(
            select(Project).where(
                Project.workspace_id == workspace_id, Project.deleted_at.is_(None)
            )
        )
    ]


@app.get("/projects/{project_id}/sources")
def list_sources(project_id: str, session: Session = Depends(_session)):
    rows = session.scalars(
        select(Source).where(Source.project_id == project_id, Source.deleted_at.is_(None))
    )
    return [
        {
            "id": s.id, "title": s.title, "authors": s.authors, "year": s.year,
            "venue": s.venue, "doi": s.doi, "url": s.url, "access": str(s.access),
            "license": s.license, "human_verified": s.human_verified,
            "integrity_note": s.integrity_note,
        }
        for s in rows
    ]


@app.get("/sources/{source_id}/excerpts")
def list_excerpts(source_id: str, session: Session = Depends(_session)):
    from .models import Excerpt

    return [
        {"id": e.id, "text": e.text, "locator": e.locator, "checksum": e.checksum}
        for e in session.scalars(select(Excerpt).where(Excerpt.source_id == source_id))
    ]


@app.get("/projects/{project_id}/claims")
def list_claims(project_id: str, session: Session = Depends(_session)):
    out = []
    for c in session.scalars(
        select(Claim).where(Claim.project_id == project_id, Claim.deleted_at.is_(None))
    ):
        evidence = research.claim_evidence(session, c.id)
        out.append(
            {
                "id": c.id, "text": c.text, "support": str(c.support), "notes": c.notes,
                "evidence_count": len(evidence),
            }
        )
    return out


@app.get("/projects/{project_id}/threads")
def list_threads(project_id: str, session: Session = Depends(_session)):
    rows = session.scalars(
        select(Thread).where(Thread.project_id == project_id, Thread.deleted_at.is_(None))
    )
    return [
        {"id": t.id, "title": t.title, "goal": t.goal, "mode": t.mode,
         "parent_thread_id": t.parent_thread_id,
         "branched_from_turn_id": t.branched_from_turn_id,
         "pinned_object_ids": t.pinned_object_ids, "pinned_source_ids": t.pinned_source_ids}
        for t in rows
    ]


@app.get("/threads/{thread_id}/actions")
def list_actions(thread_id: str, session: Session = Depends(_session)):
    rows = session.scalars(
        select(ProposedAction).where(ProposedAction.thread_id == thread_id)
    )
    return [
        {"id": a.id, "kind": a.kind, "risk": a.risk, "payload": a.payload,
         "plan_hash": a.plan_hash, "status": str(a.status), "result": a.result}
        for a in rows
    ]


@app.post("/objects/{object_id}/accept")
def accept_object(object_id: str, session: Session = Depends(_session)):
    try:
        obj = research.accept_object(session, object_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return _object_out(obj)


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


@app.post("/projects/{project_id}/export")
def export_project_bundle(
    project_id: str, session: Session = Depends(_session), user=Depends(_principal),
):
    """Export the whole project (rows + referenced artifacts) as a checksummed ZIP."""
    from .services import transfer

    _require(session, project_id, user, "reviewer")
    try:
        result = transfer.export_project(session, project_id)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return result


class ImportIn(BaseModel):
    path: str
    workspace_id: str | None = None


@app.post("/projects/import")
def import_project_bundle(body: ImportIn, session: Session = Depends(_session)):
    """Restore a project bundle from a local ZIP path (refuses to overwrite)."""
    from .services import transfer

    try:
        result = transfer.import_project(
            session, body.path, workspace_id=body.workspace_id
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return result


# --- integrity watch ---


@app.post("/projects/{project_id}/integrity/check")
def integrity_check(
    project_id: str, session: Session = Depends(_session), user=Depends(_principal),
):
    """Run the retraction/correction watch over the project's DOI-bearing sources."""
    from .services import integrity

    _require(session, project_id, user, "editor")
    try:
        result = integrity.check_project_sources(session, project_id)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return result


# --- reporting-guideline checklists ---


@app.get("/guidelines")
def list_guideline_packs():
    from .services import guidelines

    return guidelines.list_packs()


class ChecklistIn(BaseModel):
    pack_id: str


@app.post("/manuscripts/{manuscript_id}/checklists")
def attach_checklist(
    manuscript_id: str, body: ChecklistIn, session: Session = Depends(_session),
):
    from .services import guidelines

    try:
        obj = guidelines.attach_checklist(session, manuscript_id, body.pack_id)
    except (guidelines.GuidelineError, research.IntegrityError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": obj.id, "title": obj.title, "items": obj.body["items"]}


@app.get("/manuscripts/{manuscript_id}/checklists")
def get_checklists(manuscript_id: str, session: Session = Depends(_session)):
    from .services import guidelines

    return [
        {"id": o.id, "pack_id": o.body["pack_id"], "pack_name": o.body["pack_name"],
         "pack_source": o.body["pack_source"], "items": o.body["items"]}
        for o in guidelines.checklists_for(session, manuscript_id)
    ]


class ChecklistItemIn(BaseModel):
    status: str
    location: str = ""
    note: str = ""


@app.post("/checklists/{checklist_id}/items/{item_id}")
def update_checklist_item(
    checklist_id: str, item_id: str, body: ChecklistItemIn,
    session: Session = Depends(_session),
):
    from .services import guidelines

    try:
        obj = guidelines.update_item(
            session, checklist_id, item_id,
            status=body.status, location=body.location, note=body.note,
        )
    except guidelines.GuidelineError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": obj.id, "items": obj.body["items"]}


# --- usage & cost budgets ---


@app.exception_handler(Exception)
async def _budget_handler(request, exc):
    from fastapi.responses import JSONResponse

    from .services.usage import BudgetExceeded

    if isinstance(exc, BudgetExceeded):
        return JSONResponse(status_code=402, content={"detail": str(exc)})
    raise exc


@app.get("/projects/{project_id}/usage")
def project_usage(project_id: str, session: Session = Depends(_session)):
    from .services import usage as usage_service

    try:
        return usage_service.month_usage(session, project_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


class BudgetIn(BaseModel):
    monthly_token_ceiling: int = Field(ge=0)
    note: str = ""


@app.post("/projects/{project_id}/budget")
def set_project_budget(
    project_id: str, body: BudgetIn,
    session: Session = Depends(_session), user=Depends(_principal),
):
    from .services import usage as usage_service

    _require(session, project_id, user, "owner")
    try:
        budget = usage_service.set_budget(
            session, project_id,
            monthly_token_ceiling=body.monthly_token_ceiling, note=body.note,
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"project_id": project_id,
            "monthly_token_ceiling": budget.monthly_token_ceiling, "note": budget.note}


# --- research objects ---


class ObjectIn(BaseModel):
    kind: ObjectKind
    title: str = Field(min_length=1, max_length=500)
    body: dict = Field(default_factory=dict)
    strength: str | None = None


@app.post("/projects/{project_id}/objects")
def create_object(
    project_id: str, body: ObjectIn,
    session: Session = Depends(_session), user=Depends(_principal),
):
    _require(session, project_id, user, "coauthor")
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
    mode: str = "explore"


@app.post("/projects/{project_id}/threads")
def create_thread(project_id: str, body: ThreadIn, session: Session = Depends(_session)):
    try:
        thread = dialogue.create_thread(session, project_id, **body.model_dump())
    except (research.IntegrityError, dialogue.DialogueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": thread.id, "title": thread.title, "mode": thread.mode}


class BranchIn(BaseModel):
    turn_id: str
    title: str | None = None


@app.post("/threads/{thread_id}/branch")
def branch_thread(thread_id: str, body: BranchIn, session: Session = Depends(_session)):
    try:
        branch = dialogue.branch_thread(
            session, thread_id, body.turn_id, title=body.title
        )
    except dialogue.DialogueError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": branch.id, "title": branch.title, "mode": branch.mode,
            "parent_thread_id": branch.parent_thread_id,
            "branched_from_turn_id": branch.branched_from_turn_id}


class ModeIn(BaseModel):
    mode: str


@app.post("/threads/{thread_id}/mode")
def set_thread_mode(thread_id: str, body: ModeIn, session: Session = Depends(_session)):
    try:
        thread = dialogue.set_mode(session, thread_id, body.mode)
    except dialogue.DialogueError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": thread.id, "mode": thread.mode}


@app.get("/dialogue/modes")
def list_dialogue_modes():
    return [{"mode": m, "description": d} for m, d in dialogue.MODES.items()]


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


class DesignIn(BaseModel):
    object_ids: list[str]
    audience: str = ""
    venue_class: str = ""
    constraints: str = ""
    n: int = Field(default=3, ge=1, le=5)


@app.post("/projects/{project_id}/paper-candidates/generate")
def generate_candidates(project_id: str, body: DesignIn, session: Session = Depends(_session)):
    try:
        cands = paper_design.generate_candidates(
            session, project_id, object_ids=body.object_ids, audience=body.audience,
            venue_class=body.venue_class, constraints=body.constraints, n=body.n,
        )
    except paper_design.DesignError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"candidates": [_object_out(c) for c in cands]}


class CompareIn(BaseModel):
    candidate_ids: list[str]


@app.post("/projects/{project_id}/paper-candidates/compare")
def compare_candidates(project_id: str, body: CompareIn, session: Session = Depends(_session)):
    try:
        return paper_design.compare_candidates(session, body.candidate_ids)
    except paper_design.DesignError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/paper-candidates/{candidate_id}/freeze")
def freeze_candidate(candidate_id: str, session: Session = Depends(_session)):
    try:
        obj = paper_design.freeze_candidate(session, candidate_id)
    except paper_design.DesignError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return _object_out(obj)


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
def add_section(
    manuscript_id: str, body: SectionIn,
    session: Session = Depends(_session), user=Depends(_principal),
):
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None:
        raise HTTPException(404, "manuscript not found")
    _require(session, manuscript.project_id, user, "editor")
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


class OutputIn(BaseModel):
    output_type: str


@app.post("/manuscripts/{manuscript_id}/outputs")
def generate_output(manuscript_id: str, body: OutputIn, session: Session = Depends(_session)):
    try:
        obj = outputs.generate_output(session, manuscript_id, body.output_type)
    except outputs.OutputError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(obj)


@app.get("/manuscripts/{manuscript_id}/outputs")
def list_outputs(manuscript_id: str, session: Session = Depends(_session)):
    return [
        {"id": o.id, "output_kind": o.body.get("output_kind"),
         "content": o.body.get("content"), "word_count": o.body.get("word_count"),
         "simulated": o.body.get("simulated"), "accepted_by_user": o.accepted_by_user}
        for o in outputs.list_outputs(session, manuscript_id)
    ]


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


# --- figures & tables (canonical data provenance) ---


class DatasetIn(BaseModel):
    name: str
    columns: list[str]
    rows: list[list]


@app.post("/projects/{project_id}/datasets")
def create_dataset(project_id: str, body: DatasetIn, session: Session = Depends(_session)):
    try:
        ds = figures.create_dataset(
            session, project_id, name=body.name, columns=body.columns, rows=body.rows
        )
    except (figures.FigureError, research.IntegrityError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(ds)


class FigureIn(BaseModel):
    title: str
    dataset_id: str
    spec: dict
    grayscale: bool = False


@app.post("/projects/{project_id}/figures")
def render_figure(project_id: str, body: FigureIn, session: Session = Depends(_session)):
    try:
        fig = figures.render_figure(
            session, project_id, title=body.title, dataset_id=body.dataset_id,
            spec=body.spec, grayscale=body.grayscale,
        )
    except (figures.FigureError, research.IntegrityError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(fig)


class TableIn(BaseModel):
    title: str
    dataset_id: str
    columns: list[str] | None = None


@app.post("/projects/{project_id}/tables")
def build_table(project_id: str, body: TableIn, session: Session = Depends(_session)):
    try:
        tbl = figures.build_table(
            session, project_id, title=body.title, dataset_id=body.dataset_id,
            columns=body.columns,
        )
    except (figures.FigureError, research.IntegrityError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _object_out(tbl)


@app.post("/artifacts/{artifact_id}/caption")
def generate_caption(artifact_id: str, session: Session = Depends(_session)):
    try:
        art = figures.generate_caption(session, artifact_id)
    except figures.FigureError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return {"id": art.id, "caption": art.body.get("caption"),
            "alt_text": art.body.get("alt_text"), "accepted_by_user": art.accepted_by_user}


@app.get("/figures/{figure_id}/image")
def figure_image(figure_id: str, session: Session = Depends(_session)):
    from fastapi.responses import FileResponse

    from .models import ResearchObject as _RO
    from .vocab import ObjectKind as _OK

    fig = session.get(_RO, figure_id)
    if fig is None or fig.kind != _OK.FIGURE:
        raise HTTPException(404, "figure not found")
    path = fig.body.get("png_path")
    if not path:
        raise HTTPException(404, "no rendered image")
    return FileResponse(path, media_type="image/png")


@app.get("/projects/{project_id}/artifacts/audit")
def audit_artifacts(project_id: str, session: Session = Depends(_session)):
    findings = figures.audit_artifacts(session, project_id)
    return {"findings": findings, "counts": _severity_counts(findings)}


# --- semantic retrieval (similarity, never evidence) ---


@app.post("/projects/{project_id}/semantic/index")
def semantic_index(project_id: str, session: Session = Depends(_session)):
    try:
        result = semantic.index_project(session, project_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return result


class SemanticSearchIn(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)


@app.post("/projects/{project_id}/semantic/search")
def semantic_search(project_id: str, body: SemanticSearchIn, session: Session = Depends(_session)):
    return semantic.semantic_search(session, project_id, body.query, top_k=body.top_k)


# --- open-access enrichment ---


@app.post("/sources/{source_id}/open-access")
def enrich_open_access(source_id: str, session: Session = Depends(_session)):
    try:
        info = literature.enrich_open_access(session, source_id)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return info


# --- venues ---


class VenueIn(BaseModel):
    workspace_id: str
    name: str
    rules: dict = Field(default_factory=dict)
    rules_source: str


@app.post("/venues")
def create_venue(body: VenueIn, session: Session = Depends(_session)):
    try:
        venue = venues.create_venue(
            session, body.workspace_id, name=body.name, rules=body.rules,
            rules_source=body.rules_source,
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": venue.id, "name": venue.name, "verified": venue.verified}


@app.post("/venues/{venue_id}/verify")
def verify_venue(venue_id: str, session: Session = Depends(_session)):
    try:
        venue = venues.verify_venue(session, venue_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return {"id": venue.id, "verified": venue.verified}


@app.get("/manuscripts/{manuscript_id}/venue-compliance/{venue_id}")
def venue_compliance(manuscript_id: str, venue_id: str, session: Session = Depends(_session)):
    try:
        findings = venues.audit_venue_compliance(session, manuscript_id, venue_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"findings": findings, "counts": _severity_counts(findings)}


# --- users / collaboration roles (local trust model) ---


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@app.post("/users")
def create_user(body: UserIn, session: Session = Depends(_session)):
    user = security.create_user(session, body.name)
    session.commit()
    return {"id": user.id, "name": user.name, "api_key": user.api_key}


class MemberIn(BaseModel):
    user_id: str
    role: str


@app.post("/projects/{project_id}/members")
def add_member(
    project_id: str, body: MemberIn,
    session: Session = Depends(_session), user=Depends(_principal),
):
    _require(session, project_id, user, "owner")
    try:
        member = security.add_member(session, project_id, body.user_id, body.role)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": member.id, "user_id": member.user_id, "role": member.role}


# --- submission tracking ---


class SubmissionIn(BaseModel):
    manuscript_id: str
    venue_id: str | None = None
    venue_name: str = ""
    deadline: str | None = None


@app.post("/projects/{project_id}/submissions")
def create_submission(project_id: str, body: SubmissionIn, session: Session = Depends(_session)):
    try:
        sub = submissions.create_submission(session, project_id, **body.model_dump())
    except submissions.SubmissionError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _submission_out(sub)


def _submission_out(sub) -> dict:
    return {
        "id": sub.id, "manuscript_id": sub.manuscript_id, "venue_name": sub.venue_name,
        "status": sub.status, "deadline": sub.deadline, "history": sub.history,
        "revisions": sub.revisions,
    }


@app.get("/projects/{project_id}/submissions")
def list_submissions(project_id: str, session: Session = Depends(_session)):
    return [_submission_out(s) for s in submissions.list_submissions(session, project_id)]


@app.get("/submissions/{submission_id}")
def get_submission(submission_id: str, session: Session = Depends(_session)):
    try:
        return _submission_out(submissions.get_submission(session, submission_id))
    except submissions.SubmissionError as exc:
        raise HTTPException(404, str(exc)) from exc


class TransitionIn(BaseModel):
    to_status: str
    note: str = ""


@app.post("/submissions/{submission_id}/transition")
def transition_submission(submission_id: str, body: TransitionIn, session: Session = Depends(_session)):
    try:
        sub = submissions.transition(session, submission_id, body.to_status, note=body.note)
    except submissions.SubmissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return _submission_out(sub)


class RevisionIn(BaseModel):
    summary: str
    response_to_reviewers: str
    changes: list[str] = Field(default_factory=list)


@app.post("/submissions/{submission_id}/revisions")
def add_revision(submission_id: str, body: RevisionIn, session: Session = Depends(_session)):
    try:
        sub = submissions.add_revision(session, submission_id, **body.model_dump())
    except submissions.SubmissionError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return _submission_out(sub)


# --- cross-project research memory (workspace-scoped) ---


@app.get("/workspaces/{workspace_id}/portfolio/unpublished-results")
def unpublished_results(workspace_id: str, session: Session = Depends(_session)):
    return portfolio.unpublished_results(session, workspace_id)


@app.get("/objects/{object_id}/usage")
def result_usage(object_id: str, session: Session = Depends(_session)):
    try:
        return portfolio.result_usage(session, object_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/saved-searches/{saved_search_id}/rerun")
def rerun_saved_search(saved_search_id: str, session: Session = Depends(_session)):
    try:
        saved, works = portfolio.rerun_saved_search(session, saved_search_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return {"saved_search_id": saved.id, "result_count": len(works)}


class WorkspaceSearchIn(BaseModel):
    query: str = Field(min_length=1)


@app.post("/workspaces/{workspace_id}/portfolio/search")
def workspace_search(workspace_id: str, body: WorkspaceSearchIn, session: Session = Depends(_session)):
    return portfolio.workspace_search(session, workspace_id, body.query)


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
