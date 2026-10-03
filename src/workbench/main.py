"""FastAPI surface (thin: validation + service calls; all rules live in services).

Run: uvicorn workbench.main:app --reload
"""

import io
import secrets
import tempfile
import zipfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, db, deployment, research_api, storage
from .audit import record_audit
from .codex_boundary import CodexLocalBoundary
from .config import get_settings
from .models import (
    AuthorshipProposal,
    Claim,
    CreditAssignment,
    Project,
    Proposal,
    ProposalSection,
    ProposalVersion,
    ProposedAction,
    ResearchObject,
    Source,
    Thread,
    Turn,
)
from .providers.codex_access import LOCAL_NOTICE, CodexLocalError, validate_configuration
from .services import (
    audits,
    authoring,
    authorship,
    citation_graph,
    compute,
    dialogue,
    export_service,
    figures,
    literature,
    manuscript_chat,
    outputs,
    paper_design,
    portfolio,
    proposals,
    publication_packages,
    research,
    security,
    semantic,
    source_dedup,
    submissions,
    venues,
)
from .vocab import ClaimSupport, Novelty, ObjectKind, ResultStrength, SourceAccess


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Alembic is the schema source of truth; this builds a fresh DB or migrates a managed
    # one. (Tests call db.create_all() directly for speed.)
    auth.validate_auth_configuration()
    deployment.validate_deployment_configuration()
    if get_settings().llm_provider == "codex_local":
        validate_configuration()
        from .providers import codex_access

        if not codex_access._loopback_listener_verified:
            raise CodexLocalError("codex_local requires the dedicated loopback launcher")
    if deployment.should_run_startup_migrations():
        db.upgrade_to_head()
    try:
        yield
    finally:
        from .services import research_runner

        research_runner.shutdown()


app = FastAPI(title="Paper-Workbench", version="0.1.0", lifespan=lifespan)


@app.exception_handler(CodexLocalError)
async def _codex_local_error(_request: Request, exc: CodexLocalError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/providers/codex-local/config")
def codex_local_configuration():
    settings = get_settings()
    return {"selected": settings.llm_provider == "codex_local", "enabled": settings.codex_local_enabled,
            "local_only": True, "notice": LOCAL_NOTICE}


@app.get("/providers/codex-local/account")
def codex_local_account():
    from .providers.registry import get_chat_provider

    if get_settings().llm_provider != "codex_local":
        raise CodexLocalError("codex_local is not selected")
    return get_chat_provider().account_status()

_PUBLIC_PATHS = {
    "/health",
    "/auth/config",
    "/auth/register",
    "/auth/login",
    "/auth/oidc/login",
    "/auth/oidc/start",
    "/auth/oidc/callback",
}


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


@app.middleware("http")
async def _production_auth_boundary(request: Request, call_next):
    """Fail closed before endpoint code for every non-public production request."""
    settings = get_settings()
    path = request.url.path
    if (
        not settings.auth_required
        or request.method == "OPTIONS"
        or path in _PUBLIC_PATHS
        or path == "/"
        or path == "/ui"
        or path.startswith("/ui/")
    ):
        return await call_next(request)

    bearer_token = _bearer_token(request.headers.get("authorization"))
    cookie_token = request.cookies.get(settings.auth_cookie_name)
    token = bearer_token or cookie_token
    session = db.session_factory()()
    try:
        if cookie_token and not bearer_token and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            auth.verify_csrf(
                cookie_token,
                request.cookies.get(settings.auth_csrf_cookie_name),
                request.headers.get("x-csrf-token"),
            )
        principal = auth.principal_from_bearer(session, token)
        required_scope = security.required_api_scope(path, request.method)
        auth.require_api_scope(principal, required_scope)
        security.authorize_request_scope(
            session,
            path=path,
            method=request.method,
            user_id=principal.id,
            bound_workspace_id=principal.workspace_id,
        )
        session.commit()  # persists only API-key last-used metadata on read requests
        request.state.principal = principal
    except auth.AuthError as exc:
        session.rollback()
        status = 401 if "authentication" in str(exc) or "bearer" in str(exc) else 403
        return JSONResponse(status_code=status, content={"detail": str(exc)})
    except security.HiddenResource as exc:
        session.rollback()
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    except security.Forbidden as exc:
        session.rollback()
        return JSONResponse(status_code=403, content={"detail": str(exc)})
    finally:
        session.close()
    return await call_next(request)


app.add_middleware(CodexLocalBoundary)

_STATIC_DIR = __import__("pathlib").Path(__file__).parent / "web" / "static"
if _STATIC_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def _root():
        return RedirectResponse("/ui/")


def _session():
    yield from db.get_session()


async def _bounded_upload(file: UploadFile) -> bytes:
    """Read one request upload without exceeding the configured serverless body budget."""
    maximum = get_settings().upload_max_bytes
    payload = bytearray()
    try:
        while True:
            chunk = await file.read(min(1 << 20, maximum + 1))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > maximum:
                raise HTTPException(413, "upload exceeds WB_UPLOAD_MAX_BYTES")
    finally:
        await file.close()
    return bytes(payload)


def _download_response(payload: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{Path(filename).name}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _principal(
    request: Request,
    session: Session = Depends(_session),
    authorization: str | None = Header(default=None),
):
    """Resolve the acting user from an optional `Authorization: Bearer <token>` header.
    In local mode (auth_required=false) an absent token yields the default local user."""
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return principal
    token = _bearer_token(authorization)
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
        security.require_role(
            session,
            project_id,
            user.id,
            minimum,
            bound_workspace_id=user.workspace_id,
        )
    except security.HiddenResource as exc:
        raise HTTPException(404, str(exc)) from exc
    except security.Forbidden as exc:
        raise HTTPException(403, str(exc)) from exc


def _require_workspace(session, workspace_id: str, user, minimum: str) -> None:
    if not get_settings().auth_required:
        return
    try:
        security.require_workspace_role(
            session,
            workspace_id,
            user.id,
            minimum,
            bound_workspace_id=user.workspace_id,
        )
    except security.HiddenResource as exc:
        raise HTTPException(404, str(exc)) from exc
    except security.Forbidden as exc:
        raise HTTPException(403, str(exc)) from exc


# --- auth endpoints ---


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)


@app.post("/auth/register")
def auth_register(
    body: RegisterIn,
    session: Session = Depends(_session),
    x_workbench_bootstrap: str | None = Header(default=None),
):
    try:
        auth.authorize_registration(session, x_workbench_bootstrap)
        user = auth.register_local_user(session, name=body.name, email=body.email, password=body.password)
    except auth.AuthError as exc:
        status = 403 if "registration is disabled" in str(exc) else 409
        raise HTTPException(status, str(exc)) from exc
    session.commit()
    return {"id": user.id, "name": user.name, "email": user.email}


class LoginIn(BaseModel):
    email: str
    password: str
    workspace_id: str | None = None


def _set_auth_cookies(response: Response, token: str, csrf_token: str) -> None:
    settings = get_settings()
    max_age = settings.auth_ttl_minutes * 60
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": max_age,
    }
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        httponly=True,
        **common,
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        csrf_token,
        httponly=False,
        **common,
    )


def _delete_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.delete_cookie(settings.auth_csrf_cookie_name, path="/")


def _login_result(user, token: str, response: Response, csrf_token: str | None) -> dict:
    settings = get_settings()
    result = {
        "authenticated": True,
        "token_type": "cookie" if settings.auth_cookie_sessions_enabled else "bearer",
        "user_id": user.id,
        "workspace_id": auth.decode_access_token(token).get("wid"),
    }
    if settings.auth_cookie_sessions_enabled:
        assert csrf_token is not None
        _set_auth_cookies(response, token, csrf_token)
    else:
        result["access_token"] = token
    return result


@app.post("/auth/login")
def auth_login(body: LoginIn, response: Response, session: Session = Depends(_session)):
    if get_settings().auth_required and not get_settings().auth_password_login_enabled:
        raise HTTPException(403, "password login is disabled")
    csrf_token = secrets.token_urlsafe(32) if get_settings().auth_cookie_sessions_enabled else None
    try:
        user, token = auth.login_password(
            session,
            email=body.email,
            password=body.password,
            workspace_id=body.workspace_id,
            csrf_token=csrf_token,
        )
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    session.commit()
    return _login_result(user, token, response, csrf_token)


class OidcLoginIn(BaseModel):
    id_token: str
    workspace_id: str | None = None


@app.post("/auth/oidc/login")
def auth_oidc_login(body: OidcLoginIn, response: Response, session: Session = Depends(_session)):
    csrf_token = secrets.token_urlsafe(32) if get_settings().auth_cookie_sessions_enabled else None
    try:
        user, token = auth.login_oidc(
            session,
            body.id_token,
            workspace_id=body.workspace_id,
            csrf_token=csrf_token,
        )
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    session.commit()
    return _login_result(user, token, response, csrf_token)


@app.get("/auth/config")
def auth_config():
    settings = get_settings()
    return {
        "auth_required": settings.auth_required,
        "password_login_enabled": settings.auth_password_login_enabled,
        "registration_enabled": settings.auth_allow_registration,
        "cookie_sessions_enabled": settings.auth_cookie_sessions_enabled,
        "csrf_cookie_name": settings.auth_csrf_cookie_name,
        "oidc_browser_enabled": settings.oidc_browser_enabled,
        "oidc_start_path": "/auth/oidc/start",
        "deployment_mode": settings.deployment_mode,
        "upload_max_bytes": settings.upload_max_bytes,
    }


@app.get("/auth/oidc/start", include_in_schema=False)
def auth_oidc_start(return_to: str = "/ui/"):
    settings = get_settings()
    try:
        authorization_url, flow_cookie = auth.start_oidc_browser_flow(return_to)
    except auth.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    response = RedirectResponse(authorization_url, status_code=302)
    response.set_cookie(
        settings.oidc_flow_cookie_name,
        flow_cookie,
        max_age=settings.oidc_flow_ttl_minutes * 60,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
        path="/auth/oidc/callback",
    )
    return response


@app.get("/auth/oidc/callback", include_in_schema=False)
def auth_oidc_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    session: Session = Depends(_session),
):
    settings = get_settings()
    if error:
        raise HTTPException(401, "identity provider denied authorization")
    if not code or not state:
        raise HTTPException(400, "OIDC callback is missing required parameters")
    flow_cookie = request.cookies.get(settings.oidc_flow_cookie_name)
    if not flow_cookie:
        raise HTTPException(400, "OIDC flow cookie is missing or expired")
    try:
        flow = auth.decode_oidc_browser_flow(flow_cookie, state)
        id_token = auth.exchange_oidc_authorization_code(code, flow.code_verifier)
        csrf_token = secrets.token_urlsafe(32)
        user, token = auth.login_oidc(
            session,
            id_token,
            csrf_token=csrf_token,
            expected_nonce=flow.nonce,
        )
    except auth.AuthError as exc:
        session.rollback()
        raise HTTPException(401, str(exc)) from exc
    session.commit()
    response = RedirectResponse(flow.return_to, status_code=303)
    _set_auth_cookies(response, token, csrf_token)
    response.delete_cookie(settings.oidc_flow_cookie_name, path="/auth/oidc/callback")
    return response


@app.post("/auth/logout")
def auth_logout(request: Request, response: Response, session: Session = Depends(_session)):
    settings = get_settings()
    bearer = _bearer_token(request.headers.get("authorization"))
    cookie = request.cookies.get(settings.auth_cookie_name)
    token = bearer or cookie
    if token:
        try:
            if cookie and not bearer:
                auth.verify_csrf(
                    cookie,
                    request.cookies.get(settings.auth_csrf_cookie_name),
                    request.headers.get("x-csrf-token"),
                )
            auth.revoke_access_token(session, token)
        except auth.AuthError as exc:
            raise HTTPException(401, "logout requires a valid session token") from exc
        session.commit()
    _delete_auth_cookies(response)
    return {"authenticated": False}


@app.get("/auth/me")
def auth_me(session: Session = Depends(_session), user=Depends(_principal)):
    from .models import FederatedIdentity

    oidc_linked = session.scalars(
        select(FederatedIdentity).where(
            FederatedIdentity.user_id == user.id,
            FederatedIdentity.deleted_at.is_(None),
        )
    ).first()
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "oidc_linked": bool(oidc_linked or user.oidc_subject),
        "workspace_id": user.workspace_id,
        "auth_method": user.auth_method,
    }


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "provider_mode": settings.provider_mode,
        "chat_provider": "codex_local" if settings.llm_provider == "codex_local" else settings.provider_mode,
        "auth_required": settings.auth_required,
        "oidc_mode": settings.oidc_mode,
        "deployment_mode": settings.deployment_mode,
    }


@app.get("/workspaces")
def list_workspaces(session: Session = Depends(_session), user=Depends(_principal)):
    from .models import Workspace, WorkspaceMember

    query = select(Workspace).where(Workspace.deleted_at.is_(None))
    if get_settings().auth_required:
        query = (
            query.join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.deleted_at.is_(None),
            )
            .distinct()
        )
        if user.workspace_id:
            query = query.where(Workspace.id == user.workspace_id)
    return [{"id": w.id, "name": w.name} for w in session.scalars(query)]


@app.get("/workspaces/{workspace_id}/projects")
def list_projects(
    workspace_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .models import Project

    _require_workspace(session, workspace_id, user, "viewer")
    return [
        {"id": p.id, "name": p.name, "description": p.description}
        for p in session.scalars(
            select(Project).where(Project.workspace_id == workspace_id, Project.deleted_at.is_(None))
        )
    ]


@app.get("/projects/{project_id}/sources")
def list_sources(project_id: str, session: Session = Depends(_session)):
    rows = session.scalars(select(Source).where(Source.project_id == project_id, Source.deleted_at.is_(None)))
    return [
        {
            "id": s.id,
            "title": s.title,
            "authors": s.authors,
            "year": s.year,
            "venue": s.venue,
            "doi": s.doi,
            "url": s.url,
            "access": str(s.access),
            "license": s.license,
            "human_verified": s.human_verified,
            "integrity_note": s.integrity_note,
            "ingest": (s.provider_metadata or {}).get("ingest"),
        }
        for s in rows
    ]


@app.get("/projects/{project_id}/sources/duplicates")
def source_duplicate_candidates(project_id: str, session: Session = Depends(_session)):
    try:
        return source_dedup.find_duplicate_candidates(session, project_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


class SourceMergeIn(BaseModel):
    retained_source_id: str
    duplicate_source_id: str
    plan_hash: str = Field(min_length=64, max_length=64)
    review_note: str = Field(min_length=1, max_length=2000)


@app.post("/projects/{project_id}/sources/merge")
def merge_duplicate_sources(
    project_id: str,
    body: SourceMergeIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require(session, project_id, user, "editor")
    try:
        result = source_dedup.merge_duplicate_sources(session, project_id, **body.model_dump())
    except research.IntegrityError as exc:
        status = 409 if "plan changed" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    session.commit()
    return result


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
    for c in session.scalars(select(Claim).where(Claim.project_id == project_id, Claim.deleted_at.is_(None))):
        evidence = research.claim_evidence(session, c.id)
        out.append(
            {
                "id": c.id,
                "text": c.text,
                "support": str(c.support),
                "notes": c.notes,
                "evidence_count": len(evidence),
            }
        )
    return out


@app.get("/projects/{project_id}/threads")
def list_threads(project_id: str, session: Session = Depends(_session)):
    rows = session.scalars(select(Thread).where(Thread.project_id == project_id, Thread.deleted_at.is_(None)))
    return [
        {
            "id": t.id,
            "title": t.title,
            "goal": t.goal,
            "mode": t.mode,
            "summary": t.summary,
            "manuscript_id": t.manuscript_id,
            "section_id": t.section_id,
            "parent_thread_id": t.parent_thread_id,
            "branched_from_turn_id": t.branched_from_turn_id,
            "pinned_object_ids": t.pinned_object_ids,
            "pinned_source_ids": t.pinned_source_ids,
        }
        for t in rows
    ]


@app.get("/threads/{thread_id}/actions")
def list_actions(thread_id: str, session: Session = Depends(_session)):
    rows = session.scalars(select(ProposedAction).where(ProposedAction.thread_id == thread_id))
    return [
        {
            "id": a.id,
            "kind": a.kind,
            "risk": a.risk,
            "payload": a.payload,
            "plan_hash": a.plan_hash,
            "status": str(a.status),
            "result": a.result,
        }
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
def create_workspace(
    body: WorkspaceIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    if user.workspace_id:
        raise HTTPException(403, "workspace-bound credentials cannot create tenants")
    ws = research.create_workspace(session, body.name)
    security.add_workspace_member(session, ws.id, user.id, "owner")
    session.commit()
    return {"id": ws.id, "name": ws.name}


class ProjectIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


@app.post("/projects")
def create_project(
    body: ProjectIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require_workspace(session, body.workspace_id, user, "member")
    try:
        project = research.create_project(session, body.workspace_id, body.name, body.description)
        security.add_member(session, project.id, user.id, "owner")
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": project.id, "name": project.name}


@app.post("/projects/{project_id}/export")
def export_project_bundle(
    project_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
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


@app.post("/projects/{project_id}/export/download")
def download_project_bundle(
    project_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    """Assemble and return an authorized project-transfer ZIP."""
    from .services import transfer

    _require(session, project_id, user, "reviewer")
    result = transfer.export_project(session, project_id)
    session.commit()
    payload = storage.read_bytes(result["artifact"])
    return _download_response(payload, f"paper-workbench-{project_id}.zip", "application/zip")


class ImportIn(BaseModel):
    path: str
    workspace_id: str | None = None


@app.post("/projects/import")
def import_project_bundle(
    body: ImportIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    """Restore a project bundle from a local ZIP path (refuses to overwrite)."""
    from .services import transfer

    if body.workspace_id:
        _require_workspace(session, body.workspace_id, user, "member")
    elif user.workspace_id:
        raise HTTPException(403, "workspace-bound credentials cannot create tenants")
    try:
        result = transfer.import_project(session, body.path, workspace_id=body.workspace_id)
        if body.workspace_id is None:
            security.add_workspace_member(session, result["workspace_id"], user.id, "owner")
        security.add_member(session, result["project_id"], user.id, "owner")
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return result


@app.post("/projects/import/upload")
async def import_uploaded_project_bundle(
    file: Annotated[UploadFile, File()],
    workspace_id: Annotated[str | None, Form()] = None,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    """Restore a bounded browser-uploaded project ZIP without trusting a server path."""
    from .services import transfer

    if workspace_id:
        _require_workspace(session, workspace_id, user, "member")
    elif user.workspace_id:
        raise HTTPException(403, "workspace-bound credentials cannot create tenants")
    payload = await _bounded_upload(file)
    scratch_root = Path(get_settings().data_dir)
    scratch_root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="wb-import-", dir=scratch_root) as temp_dir:
            bundle_path = Path(temp_dir) / "project.zip"
            bundle_path.write_bytes(payload)
            result = transfer.import_project(session, bundle_path, workspace_id=workspace_id)
            if workspace_id is None:
                security.add_workspace_member(session, result["workspace_id"], user.id, "owner")
            security.add_member(session, result["project_id"], user.id, "owner")
    except (OSError, zipfile.BadZipFile, research.IntegrityError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return result


# --- integrity watch ---


@app.post("/projects/{project_id}/integrity/check")
def integrity_check(
    project_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
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
    manuscript_id: str,
    body: ChecklistIn,
    session: Session = Depends(_session),
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
        {
            "id": o.id,
            "pack_id": o.body["pack_id"],
            "pack_name": o.body["pack_name"],
            "pack_source": o.body["pack_source"],
            "items": o.body["items"],
        }
        for o in guidelines.checklists_for(session, manuscript_id)
    ]


class ChecklistItemIn(BaseModel):
    status: str
    location: str = ""
    note: str = ""


@app.post("/checklists/{checklist_id}/items/{item_id}")
def update_checklist_item(
    checklist_id: str,
    item_id: str,
    body: ChecklistItemIn,
    session: Session = Depends(_session),
):
    from .services import guidelines

    try:
        obj = guidelines.update_item(
            session,
            checklist_id,
            item_id,
            status=body.status,
            location=body.location,
            note=body.note,
        )
    except guidelines.GuidelineError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": obj.id, "items": obj.body["items"]}


# --- usage & cost budgets ---


@app.exception_handler(storage.ArtifactStorageError)
async def _artifact_storage_handler(_request: Request, exc: storage.ArtifactStorageError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


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
    project_id: str,
    body: BudgetIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .services import usage as usage_service

    _require(session, project_id, user, "owner")
    try:
        budget = usage_service.set_budget(
            session,
            project_id,
            monthly_token_ceiling=body.monthly_token_ceiling,
            note=body.note,
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {
        "project_id": project_id,
        "monthly_token_ceiling": budget.monthly_token_ceiling,
        "note": budget.note,
    }


# --- research objects ---


class ObjectIn(BaseModel):
    kind: ObjectKind
    title: str = Field(min_length=1, max_length=500)
    body: dict = Field(default_factory=dict)
    strength: str | None = None


@app.post("/projects/{project_id}/objects")
def create_object(
    project_id: str,
    body: ObjectIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require(session, project_id, user, "coauthor")
    try:
        obj = research.create_object(
            session,
            project_id,
            kind=body.kind,
            title=body.title,
            body=body.body,
            strength=body.strength,
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
        "id": o.id,
        "kind": str(o.kind),
        "title": o.title,
        "body": o.body,
        "strength": o.strength,
        "ai_suggested": o.ai_suggested,
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


@app.get("/projects/{project_id}/sources/{source_id}/original")
def source_original_pdf(
    project_id: str, source_id: str, session: Session = Depends(_session),
    user=Depends(_principal),
):
    """Serve only the preserved, checksum-verified PDF within its project."""
    from . import storage

    _require(session, project_id, user, "viewer")
    source = session.get(Source, source_id)
    if source is None or source.project_id != project_id or source.deleted_at is not None:
        raise HTTPException(404, "source not found")
    reference = (source.provider_metadata or {}).get("ingest", {}).get("artifact")
    if not isinstance(reference, dict):
        raise HTTPException(404, "preserved original unavailable")
    try:
        payload = storage.read_bytes(reference)
    except storage.ArtifactStorageError as exc:
        raise HTTPException(404, "preserved original unavailable or corrupt") from exc
    if not payload.startswith(b"%PDF-"):
        raise HTTPException(415, "preserved original is not a PDF")
    return Response(content=payload, media_type="application/pdf", headers={
        "Content-Disposition": 'inline; filename="original.pdf"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


class IngestIn(BaseModel):
    path: str
    title: str | None = None
    license: str = "author-owned"
    pdf_mode: Literal["auto", "text", "plain", "ocr"] = "auto"


@app.post("/projects/{project_id}/ingest")
def ingest_local_file(project_id: str, body: IngestIn, session: Session = Depends(_session)):
    """Ingest a local file (single-user local deployment; the path is the user's own disk)."""
    from .ingest.files import IngestError, ingest_file

    try:
        source = ingest_file(
            session,
            project_id,
            body.path,
            title=body.title,
            license=body.license,
            pdf_mode=body.pdf_mode,
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


@app.post("/projects/{project_id}/ingest/upload")
async def ingest_uploaded_file(
    project_id: str,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    license: Annotated[str, Form()] = "author-owned",
    pdf_mode: Annotated[Literal["auto", "text", "plain", "ocr"], Form()] = "auto",
    session: Session = Depends(_session),
):
    """Ingest a bounded browser upload; originals become private durable artifacts."""
    from .ingest.files import IngestError, ingest_file

    settings = get_settings()
    filename = Path(file.filename or "upload.bin").name
    if not filename or filename in {".", ".."}:
        raise HTTPException(422, "uploaded filename is invalid")
    payload = await _bounded_upload(file)
    scratch_root = Path(settings.data_dir)
    scratch_root.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix[:16]
    try:
        with tempfile.TemporaryDirectory(prefix="wb-upload-", dir=scratch_root) as temp_dir:
            temp_path = Path(temp_dir) / f"upload{suffix}"
            temp_path.write_bytes(payload)
            source = ingest_file(
                session,
                project_id,
                temp_path,
                title=title,
                license=license,
                pdf_mode=pdf_mode,
                original_name=filename,
                acquisition=(
                    f"user file uploaded through Paper-Workbench as {filename} "
                    f"at {datetime.now(UTC).isoformat()}"
                ),
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
        excerpt = research.capture_excerpt(session, source_id, text=body.text, locator=body.locator)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": excerpt.id, "locator": excerpt.locator, "checksum": excerpt.checksum}


# --- evidence-grounded proposals ---


class ProposalBriefIn(BaseModel):
    client_question: str = Field(min_length=1, max_length=20_000)
    audience: str = Field(default="", max_length=10_000)
    aims: str = Field(default="", max_length=20_000)
    success_criteria: str = Field(default="", max_length=20_000)
    constraints: str = Field(default="", max_length=20_000)
    known_resources: str = Field(default="", max_length=20_000)
    unanswered_questions: str = Field(default="", max_length=20_000)


class ProposalIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    kind: Literal["research_collaboration", "applied_client_pilot"]
    brief: ProposalBriefIn


class ProposalBriefUpdateIn(ProposalBriefIn):
    expected_revision: int = Field(ge=0)


class ProposalSourceIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=32)
    collection: Literal["author", "client", "background"]


class ProposalUrlIn(BaseModel):
    url: str = Field(min_length=1, max_length=2_000)
    collection: Literal["author", "client", "background"]
    title: str | None = Field(default=None, max_length=600)


class ProposalPassageCorrectionIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=1_400)
    locator: str = Field(min_length=1, max_length=300)


class ProposalRetrieveIn(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    collections: list[Literal["author", "client", "background"]] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=24)


class ProposalGenerationIn(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=100)
    # This is a deliberate per-request authorization boundary for future live use.  It
    # defaults off, so a configured provider cannot be invoked accidentally.
    use_live: bool = False
    needs: list[str] = Field(default_factory=list, max_length=50)


class ProposalSectionUpdateIn(BaseModel):
    text: str = Field(max_length=30_000)
    expected_revision: int = Field(ge=0)
    citation_ids: list[str] | None = Field(default=None, max_length=24)


class ProposalSectionReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    expected_revision: int = Field(ge=0)


class ProposalUndoIn(BaseModel):
    expected_revision: int = Field(ge=0)


class ProposalVersionIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    review_note: str = Field(min_length=1, max_length=10_000)
    expected_draft_revision: int = Field(ge=0)
    approve_all: bool = False


class ProposalCompareIn(BaseModel):
    left_version_id: str = Field(min_length=1, max_length=32)
    right_version_id: str = Field(min_length=1, max_length=32)


class ProposalExportIn(BaseModel):
    formats: list[Literal["md", "html", "docx", "pdf"]] = Field(
        default_factory=lambda: ["md", "html", "docx"]
    )


def _proposal_http(exc: Exception) -> HTTPException:
    detail = str(exc)
    status = 409 if any(token in detail for token in ("changed", "stale", "idempotency")) else 422
    return HTTPException(status, detail)


@app.get("/projects/{project_id}/proposals")
def list_proposals(project_id: str, session: Session = Depends(_session), user=Depends(_principal)):
    _require(session, project_id, user, "reviewer")
    return [
        proposals.proposal_out(session, proposal)
        for proposal in session.scalars(
            select(Proposal)
            .where(Proposal.project_id == project_id, Proposal.deleted_at.is_(None))
            .order_by(Proposal.created_at, Proposal.id)
        )
    ]


@app.post("/projects/{project_id}/proposals")
def create_proposal(
    project_id: str, body: ProposalIn, session: Session = Depends(_session), user=Depends(_principal)
):
    _require(session, project_id, user, "editor")
    try:
        proposal = proposals.create_proposal(
            session, project_id, title=body.title, kind=body.kind, brief=body.brief.model_dump()
        )
    except (proposals.ProposalError, ValueError) as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return proposals.proposal_out(session, proposal, include_detail=True)


@app.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, session: Session = Depends(_session), user=Depends(_principal)):
    try:
        proposal = proposals._proposal(session, proposal_id)
    except proposals.ProposalError as exc:
        raise HTTPException(404, str(exc)) from exc
    _require(session, proposal.project_id, user, "reviewer")
    return proposals.proposal_out(session, proposal, include_detail=True)


@app.put("/proposals/{proposal_id}/brief")
def update_proposal_brief(
    proposal_id: str,
    body: ProposalBriefUpdateIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        proposal = proposals.update_brief(
            session,
            proposal_id,
            brief=body.model_dump(exclude={"expected_revision"}),
            expected_revision=body.expected_revision,
        )
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return proposals.proposal_out(session, proposal)


@app.post("/proposals/{proposal_id}/sources")
def add_proposal_source(
    proposal_id: str,
    body: ProposalSourceIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        member = proposals.add_source(session, proposal_id, **body.model_dump())
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return {"id": member.id, "source_id": member.source_id, "collection": member.collection}


@app.post("/proposals/{proposal_id}/sources/url")
def add_proposal_url(
    proposal_id: str,
    body: ProposalUrlIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        result = proposals.ingest_url(session, proposal_id, **body.model_dump())
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return result


@app.post("/proposals/{proposal_id}/passages/index")
def index_proposal_passages(
    proposal_id: str,
    source_id: str | None = None,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        result = proposals.index_passages(session, proposal_id, source_id=source_id)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return result


@app.post("/proposals/{proposal_id}/passages/correct")
def correct_proposal_passage(
    proposal_id: str,
    body: ProposalPassageCorrectionIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        passage = proposals.correct_excerpt(session, proposal_id, **body.model_dump())
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return {
        "id": passage.id,
        "locator": passage.locator,
        "checksum": passage.checksum,
        "manual_correction": passage.manual_correction,
    }


@app.delete("/proposals/{proposal_id}/passages/{passage_id}")
def remove_proposal_passage(
    proposal_id: str,
    passage_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        proposals.delete_passage(session, proposal_id, passage_id)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return {"deleted": passage_id}


@app.post("/proposals/{proposal_id}/retrieve")
def retrieve_proposal_passages(
    proposal_id: str,
    body: ProposalRetrieveIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "reviewer")
        return proposals.retrieve(
            session, proposal_id, body.query, collections=set(body.collections) or None, top_k=body.top_k
        )
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc


@app.get("/proposals/{proposal_id}/evidence-pack")
def proposal_evidence_pack(
    proposal_id: str,
    selected_section_id: str | None = None,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "reviewer")
        return proposals.evidence_pack(session, proposal_id, selected_section_id=selected_section_id)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc


@app.post("/proposals/{proposal_id}/fit-matrix/generate")
def generate_proposal_fit_matrix(
    proposal_id: str,
    body: ProposalGenerationIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        result = proposals.generate_fit_matrix(
            session,
            proposal_id,
            idempotency_key=body.idempotency_key,
            needs=body.needs or None,
            use_live=body.use_live,
        )
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return result


@app.post("/proposals/{proposal_id}/outline/generate")
def generate_proposal_outline(
    proposal_id: str,
    body: ProposalGenerationIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        result = proposals.generate_outline(
            session, proposal_id, idempotency_key=body.idempotency_key, use_live=body.use_live
        )
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return result


@app.post("/proposals/{proposal_id}/draft/generate")
def generate_proposal_draft(
    proposal_id: str,
    body: ProposalGenerationIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        result = proposals.generate_draft(
            session, proposal_id, idempotency_key=body.idempotency_key, use_live=body.use_live
        )
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return result


@app.post("/proposals/{proposal_id}/generations/{generation_id}/cancel")
def cancel_proposal_generation(
    proposal_id: str,
    generation_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "editor")
        generation = proposals.cancel_generation(session, proposal_id, generation_id)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return proposals.generation_out(generation)


@app.put("/proposal-sections/{section_id}")
def update_proposal_section(
    section_id: str,
    body: ProposalSectionUpdateIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    section = session.get(ProposalSection, section_id)
    if section is None:
        raise HTTPException(404, "proposal section not found")
    try:
        proposal = proposals._proposal(session, section.proposal_id)
        _require(session, proposal.project_id, user, "editor")
        section = proposals.update_section(session, section_id, **body.model_dump())
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return next(item for item in proposals.sections(session, proposal.id) if item["id"] == section.id)


@app.post("/proposal-sections/{section_id}/review")
def review_proposal_section(
    section_id: str,
    body: ProposalSectionReviewIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    section = session.get(ProposalSection, section_id)
    if section is None:
        raise HTTPException(404, "proposal section not found")
    try:
        proposal = proposals._proposal(session, section.proposal_id)
        _require(session, proposal.project_id, user, "editor")
        section = proposals.review_section(session, section_id, **body.model_dump())
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return next(item for item in proposals.sections(session, proposal.id) if item["id"] == section.id)


@app.post("/proposal-sections/{section_id}/undo")
def undo_proposal_section(
    section_id: str,
    body: ProposalUndoIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    section = session.get(ProposalSection, section_id)
    if section is None:
        raise HTTPException(404, "proposal section not found")
    try:
        proposal = proposals._proposal(session, section.proposal_id)
        _require(session, proposal.project_id, user, "editor")
        section = proposals.undo_section(session, section_id, expected_revision=body.expected_revision)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return next(item for item in proposals.sections(session, proposal.id) if item["id"] == section.id)


@app.post("/proposals/{proposal_id}/versions")
def save_proposal_version(
    proposal_id: str,
    body: ProposalVersionIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "coauthor")
        version = proposals.save_version(session, proposal_id, **body.model_dump())
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return proposals.version_out(session, version, include_snapshot=True)


@app.get("/proposals/{proposal_id}/versions")
def list_proposal_versions(proposal_id: str, session: Session = Depends(_session), user=Depends(_principal)):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "reviewer")
        return proposals.versions(session, proposal_id)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc


@app.post("/proposals/{proposal_id}/versions/compare")
def compare_proposal_versions(
    proposal_id: str,
    body: ProposalCompareIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        proposal = proposals._proposal(session, proposal_id)
        _require(session, proposal.project_id, user, "reviewer")
        return proposals.compare_versions(session, proposal_id, body.left_version_id, body.right_version_id)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc


@app.get("/proposal-versions/{version_id}")
def get_proposal_version(version_id: str, session: Session = Depends(_session), user=Depends(_principal)):
    version = session.get(ProposalVersion, version_id)
    if version is None:
        raise HTTPException(404, "proposal version not found")
    try:
        proposal = proposals._proposal(session, version.proposal_id)
        _require(session, proposal.project_id, user, "reviewer")
        return proposals.version_out(session, version, include_snapshot=True)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc


@app.post("/proposal-versions/{version_id}/export")
def export_proposal_version(
    version_id: str,
    body: ProposalExportIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    version = session.get(ProposalVersion, version_id)
    if version is None:
        raise HTTPException(404, "proposal version not found")
    try:
        proposal = proposals._proposal(session, version.proposal_id)
        _require(session, proposal.project_id, user, "coauthor")
        result = proposals.export_version(session, version_id, formats=body.formats)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return result


@app.post("/proposal-versions/{version_id}/export/download")
def download_proposal_version_export(
    version_id: str,
    body: ProposalExportIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    version = session.get(ProposalVersion, version_id)
    if version is None:
        raise HTTPException(404, "proposal version not found")
    try:
        proposal = proposals._proposal(session, version.proposal_id)
        _require(session, proposal.project_id, user, "coauthor")
        payload, filename = proposals.export_download(session, version_id, formats=body.formats)
    except proposals.ProposalError as exc:
        raise _proposal_http(exc) from exc
    session.commit()
    return _download_response(payload, filename, "application/zip")


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
            "id": ev.id,
            "excerpt_id": ev.excerpt_id,
            "research_object_id": ev.research_object_id,
            "entailment": ev.entailment,
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
    manuscript_id: str | None = None
    section_id: str | None = None


@app.post("/projects/{project_id}/threads")
def create_thread(project_id: str, body: ThreadIn, session: Session = Depends(_session)):
    try:
        thread = dialogue.create_thread(session, project_id, **body.model_dump())
    except (research.IntegrityError, dialogue.DialogueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": thread.id, "title": thread.title, "mode": thread.mode}


@app.get("/threads/{thread_id}/context")
def thread_context(thread_id: str, session: Session = Depends(_session)):
    thread = session.get(Thread, thread_id)
    if thread is None or thread.deleted_at is not None:
        raise HTTPException(404, "thread not found")
    try:
        snapshot = manuscript_chat.context(session, thread)
        prompt = dialogue.assemble_system_prompt(session, thread, snapshot=snapshot)
    except (manuscript_chat.ManuscriptChatError, dialogue.DialogueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        **snapshot,
        "goal": thread.goal,
        "summary": thread.summary,
        "system_prompt": prompt,
        "recent_turn_limit": dialogue.RECENT_TURNS,
    }


class ThreadBriefIn(BaseModel):
    summary: str = Field(max_length=12_000)


@app.put("/threads/{thread_id}/brief")
def update_thread_brief(thread_id: str, body: ThreadBriefIn, session: Session = Depends(_session)):
    thread = session.get(Thread, thread_id)
    if thread is None or thread.deleted_at is not None:
        raise HTTPException(404, "thread not found")
    thread.summary = body.summary
    project = research._project(session, thread.project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="update_brief",
        object_type="thread",
        object_id=thread.id,
        detail={"summary": body.summary},
    )
    session.commit()
    return {"id": thread.id, "summary": thread.summary}


class BranchIn(BaseModel):
    turn_id: str
    title: str | None = None


@app.post("/threads/{thread_id}/branch")
def branch_thread(thread_id: str, body: BranchIn, session: Session = Depends(_session)):
    try:
        branch = dialogue.branch_thread(session, thread_id, body.turn_id, title=body.title)
    except dialogue.DialogueError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {
        "id": branch.id,
        "title": branch.title,
        "mode": branch.mode,
        "parent_thread_id": branch.parent_thread_id,
        "branched_from_turn_id": branch.branched_from_turn_id,
    }


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
            "id": assistant.id,
            "content": assistant.content,
            "provenance": assistant.provenance,
        },
        "proposed_actions": [
            {"id": a.id, "kind": a.kind, "risk": a.risk, "payload": a.payload, "plan_hash": a.plan_hash}
            for a in actions
        ],
    }


@app.get("/threads/{thread_id}/turns")
def list_turns(thread_id: str, session: Session = Depends(_session)):
    if session.get(Thread, thread_id) is None:
        raise HTTPException(404, "thread not found")
    rows = session.scalars(select(Turn).where(Turn.thread_id == thread_id).order_by(Turn.created_at, Turn.id))
    return [{"id": t.id, "role": t.role, "content": t.content, "provenance": t.provenance} for t in rows]


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
                "title": w.title,
                "authors": w.authors,
                "year": w.year,
                "venue": w.venue,
                "doi": w.doi,
                "url": w.url,
                "cited_by_count": w.cited_by_count,
                "has_abstract": bool(w.abstract),
                "provider": w.provider,
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


class CitationDiscoverIn(BaseModel):
    provider: Literal["semanticscholar"] = "semanticscholar"
    direction: Literal["backward", "forward"] = "backward"
    count: int = Field(default=20, ge=1, le=100)


@app.post("/projects/{project_id}/sources/{source_id}/citations/discover")
def discover_source_citations(
    project_id: str,
    source_id: str,
    body: CitationDiscoverIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require(session, project_id, user, "editor")
    try:
        result = citation_graph.discover_citations(session, project_id, source_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return result


@app.get("/projects/{project_id}/sources/{source_id}/citation-graph")
def get_source_citation_graph(
    project_id: str,
    source_id: str,
    depth: int = 2,
    max_nodes: int = 100,
    include_rejected: bool = False,
    session: Session = Depends(_session),
):
    try:
        return citation_graph.citation_graph(
            session,
            project_id,
            source_id,
            depth=depth,
            max_nodes=max_nodes,
            include_rejected=include_rejected,
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc


class CitationResolveIn(BaseModel):
    endpoint: Literal["citing", "cited"]
    source_id: str
    review_note: str = Field(min_length=1, max_length=2000)


@app.post("/projects/{project_id}/citations/{edge_id}/resolve")
def resolve_citation_endpoint(
    project_id: str,
    edge_id: str,
    body: CitationResolveIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require(session, project_id, user, "editor")
    try:
        edge = citation_graph.resolve_edge(session, project_id, edge_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return citation_graph.edge_out(session, edge)


class CitationReviewIn(BaseModel):
    state: Literal["human_verified", "rejected"]
    review_note: str = Field(min_length=1, max_length=2000)


@app.post("/projects/{project_id}/citations/{edge_id}/review")
def review_citation_edge(
    project_id: str,
    edge_id: str,
    body: CitationReviewIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require(session, project_id, user, "editor")
    try:
        edge = citation_graph.review_edge(session, project_id, edge_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return citation_graph.edge_out(session, edge)


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
            session,
            project_id,
            object_ids=body.object_ids,
            audience=body.audience,
            venue_class=body.venue_class,
            constraints=body.constraints,
            n=body.n,
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


class ContributorIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=300)
    given_names: str = Field(default="", max_length=200)
    family_name: str = Field(default="", max_length=200)
    orcid: str | None = Field(default=None, max_length=40)
    affiliation: str = ""
    corresponding: bool = False


@app.get("/projects/{project_id}/contributors")
def list_contributors(project_id: str, session: Session = Depends(_session)):
    try:
        return [authorship.contributor_out(c) for c in authorship.list_contributors(session, project_id)]
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/projects/{project_id}/contributors")
def create_contributor(
    project_id: str,
    body: ContributorIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require(session, project_id, user, "coauthor")
    try:
        contributor = authorship.create_contributor(session, project_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return authorship.contributor_out(contributor)


class CreditAssignmentIn(BaseModel):
    contributor_id: str
    role: str
    degree: str = "equal"
    rationale: str = Field(min_length=1)


@app.get("/manuscripts/{manuscript_id}/credit")
def manuscript_credit(manuscript_id: str, session: Session = Depends(_session)):
    try:
        return authorship.manuscript_credit(session, manuscript_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/manuscripts/{manuscript_id}/credit-assignments")
def propose_credit_assignment(
    manuscript_id: str,
    body: CreditAssignmentIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None:
        raise HTTPException(404, "manuscript not found")
    _require(session, manuscript.project_id, user, "coauthor")
    try:
        assignment = authorship.propose_assignment(
            session, manuscript_id, **body.model_dump(), origin="human"
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return authorship.assignment_out(assignment)


class CreditReviewIn(BaseModel):
    state: Literal["confirmed", "disputed", "declined"]
    note: str = Field(min_length=1)


@app.post("/credit-assignments/{assignment_id}/review")
def review_credit_assignment(
    assignment_id: str,
    body: CreditReviewIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    assignment = session.get(CreditAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(404, "CRediT assignment not found")
    _require(session, assignment.project_id, user, "coauthor")
    try:
        assignment = authorship.review_assignment(session, assignment_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return authorship.assignment_out(assignment)


class AuthorshipProposalIn(BaseModel):
    ordered_contributor_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)


@app.post("/manuscripts/{manuscript_id}/authorship-proposals")
def propose_authorship_order(
    manuscript_id: str,
    body: AuthorshipProposalIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None:
        raise HTTPException(404, "manuscript not found")
    _require(session, manuscript.project_id, user, "coauthor")
    try:
        proposal = authorship.create_order_proposal(session, manuscript_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return authorship.proposal_out(proposal)


@app.post("/manuscripts/{manuscript_id}/authorship-proposals/suggest")
def suggest_authorship_order(
    manuscript_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None:
        raise HTTPException(404, "manuscript not found")
    _require(session, manuscript.project_id, user, "coauthor")
    try:
        proposal = authorship.suggest_order(session, manuscript_id)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return authorship.proposal_out(proposal)


class AuthorshipReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=1)


@app.post("/authorship-proposals/{proposal_id}/review")
def review_authorship_order(
    proposal_id: str,
    body: AuthorshipReviewIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    proposal = session.get(AuthorshipProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "authorship proposal not found")
    _require(session, proposal.project_id, user, "coauthor")
    try:
        proposal = authorship.review_order_proposal(session, proposal_id, **body.model_dump())
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return authorship.proposal_out(proposal)


class SectionIn(BaseModel):
    heading: str
    purpose: str = ""
    text: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    word_budget: int | None = None
    position: int | None = None


@app.post("/manuscripts/{manuscript_id}/sections")
def add_section(
    manuscript_id: str,
    body: SectionIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
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
        {
            "id": o.id,
            "output_kind": o.body.get("output_kind"),
            "content": o.body.get("content"),
            "word_count": o.body.get("word_count"),
            "simulated": o.body.get("simulated"),
            "accepted_by_user": o.accepted_by_user,
        }
        for o in outputs.list_outputs(session, manuscript_id)
    ]


class ExportIn(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["md", "tex", "html", "docx", "bib"])


@app.post("/manuscripts/{manuscript_id}/export")
def export_manuscript(manuscript_id: str, body: ExportIn, session: Session = Depends(_session)):
    try:
        result = export_service.export_manuscript(session, manuscript_id, formats=body.formats)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return result


@app.post("/manuscripts/{manuscript_id}/export/download")
def download_manuscript_export(manuscript_id: str, body: ExportIn, session: Session = Depends(_session)):
    """Build and return the requested manuscript formats as an authorized ZIP."""
    try:
        result = export_service.export_manuscript(session, manuscript_id, formats=body.formats)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, reference in sorted(result["artifact_refs"].items()):
            filename = Path(result["files"][name]).name
            archive.writestr(filename, storage.read_bytes(reference))
    return _download_response(archive_bytes.getvalue(), f"manuscript-{manuscript_id}.zip", "application/zip")


# --- figures & tables (canonical data provenance) ---


class DatasetIn(BaseModel):
    name: str
    columns: list[str]
    rows: list[list]


@app.post("/projects/{project_id}/datasets")
def create_dataset(project_id: str, body: DatasetIn, session: Session = Depends(_session)):
    try:
        ds = figures.create_dataset(session, project_id, name=body.name, columns=body.columns, rows=body.rows)
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
            session,
            project_id,
            title=body.title,
            dataset_id=body.dataset_id,
            spec=body.spec,
            grayscale=body.grayscale,
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
            session,
            project_id,
            title=body.title,
            dataset_id=body.dataset_id,
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
    return {
        "id": art.id,
        "caption": art.body.get("caption"),
        "alt_text": art.body.get("alt_text"),
        "accepted_by_user": art.accepted_by_user,
    }


@app.get("/figures/{figure_id}/image")
def figure_image(figure_id: str, session: Session = Depends(_session)):
    from fastapi.responses import FileResponse

    from .models import ResearchObject as _RO
    from .vocab import ObjectKind as _OK

    fig = session.get(_RO, figure_id)
    if fig is None or fig.kind != _OK.FIGURE:
        raise HTTPException(404, "figure not found")
    reference = fig.body.get("png_artifact")
    if isinstance(reference, dict):
        try:
            payload = storage.read_bytes(reference)
        except storage.ArtifactStorageError as exc:
            raise HTTPException(404, str(exc)) from exc
        return Response(
            content=payload,
            media_type="image/png",
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )
    path = fig.body.get("png_path")
    if not path:
        raise HTTPException(404, "no rendered image")
    if str(path).startswith("artifact://"):
        try:
            return Response(
                content=storage.read_legacy_location(str(path)),
                media_type="image/png",
                headers={"Cache-Control": "private, no-store"},
            )
        except storage.ArtifactStorageError as exc:
            raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="image/png")


@app.get("/projects/{project_id}/artifacts/audit")
def audit_artifacts(project_id: str, session: Session = Depends(_session)):
    findings = figures.audit_artifacts(session, project_id)
    return {"findings": findings, "counts": _severity_counts(findings)}


# --- reproducible local compute (explicit approval + human review) ---


class ComputeRunIn(BaseModel):
    script_source_id: str
    input_source_ids: list[str] = Field(default_factory=list, max_length=50)
    arguments: list[str] = Field(default_factory=list, max_length=32)
    timeout_seconds: int = Field(default=60, ge=1)
    seed: int = Field(default=0, ge=-(2**31), lt=2**31)
    executor: Literal["local_python", "docker"] = "local_python"
    container_image: str = ""
    memory_mb: int = Field(default=512, ge=64)
    cpus: float = Field(default=1.0, ge=0.1)
    pids_limit: int = Field(default=64, ge=16)


@app.post("/projects/{project_id}/compute-runs")
def create_compute_run(
    project_id: str,
    body: ComputeRunIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require(session, project_id, user, "coauthor")
    try:
        run = compute.create_run(session, project_id, **body.model_dump())
    except compute.ComputeError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return compute.run_out(session, run)


@app.get("/projects/{project_id}/compute-runs")
def list_compute_runs(project_id: str, session: Session = Depends(_session)):
    try:
        return [compute.run_out(session, run) for run in compute.list_runs(session, project_id)]
    except compute.ComputeError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/compute-runs/{run_id}")
def get_compute_run(run_id: str, session: Session = Depends(_session)):
    try:
        return compute.run_out(session, compute.get_run(session, run_id))
    except compute.ComputeError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/compute-runs/{run_id}/logs/{stream}")
def get_compute_log(run_id: str, stream: Literal["stdout", "stderr"], session: Session = Depends(_session)):
    from fastapi.responses import FileResponse

    try:
        path, filename = compute.captured_file(session, run_id, stream=stream)
    except compute.ComputeError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="text/plain; charset=utf-8", filename=filename)


@app.get("/compute-runs/{run_id}/outputs/{output_index}")
def get_compute_output(run_id: str, output_index: int, session: Session = Depends(_session)):
    from fastapi.responses import FileResponse

    try:
        path, filename = compute.captured_file(session, run_id, output_index=output_index)
    except compute.ComputeError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


class ComputeApprovalIn(BaseModel):
    plan_hash: str = Field(min_length=64, max_length=64)
    review_note: str = Field(min_length=1, max_length=4000)
    acknowledge_unenforced_isolation: Literal[True]


@app.post("/compute-runs/{run_id}/approve")
def approve_compute_run(
    run_id: str,
    body: ComputeApprovalIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        run = compute.get_run(session, run_id)
        _require(session, run.project_id, user, "coauthor")
        compute.approve_run(session, run_id, **body.model_dump())
    except compute.ComputeError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return compute.run_out(session, run)


class ComputeExecutionIn(BaseModel):
    plan_hash: str = Field(min_length=64, max_length=64)
    confirm_local_execution: Literal[True]


@app.post("/compute-runs/{run_id}/execute")
def execute_compute_run(
    run_id: str,
    body: ComputeExecutionIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        run = compute.get_run(session, run_id)
        _require(session, run.project_id, user, "coauthor")
        compute.execute_run(session, run_id, **body.model_dump())
    except compute.ComputeError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return compute.run_out(session, run)


class ComputeReviewIn(BaseModel):
    decision: Literal["verified", "rejected"]
    review_note: str = Field(min_length=1, max_length=4000)


@app.post("/compute-runs/{run_id}/review")
def review_compute_run(
    run_id: str,
    body: ComputeReviewIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        run = compute.get_run(session, run_id)
        _require(session, run.project_id, user, "reviewer")
        compute.review_run(session, run_id, **body.model_dump())
    except compute.ComputeError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return compute.run_out(session, run)


class ComputePromotionIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=20_000)
    strength: ResultStrength = ResultStrength.COMPUTATIONALLY_VERIFIED_WITHIN_SCOPE


@app.post("/compute-runs/{run_id}/promote")
def promote_compute_result(
    run_id: str,
    body: ComputePromotionIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        run = compute.get_run(session, run_id)
        _require(session, run.project_id, user, "coauthor")
        result = compute.promote_result(session, run_id, **body.model_dump())
    except (compute.ComputeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return _object_out(result)


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
def create_venue(
    body: VenueIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require_workspace(session, body.workspace_id, user, "admin")
    try:
        venue = venues.create_venue(
            session,
            body.workspace_id,
            name=body.name,
            rules=body.rules,
            rules_source=body.rules_source,
        )
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": venue.id, "name": venue.name, "verified": venue.verified}


@app.post("/venues/{venue_id}/verify")
def verify_venue(
    venue_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .models import VenueProfile

    existing = session.get(VenueProfile, venue_id)
    if existing is None:
        raise HTTPException(404, "venue not found")
    _require_workspace(session, existing.workspace_id, user, "admin")
    try:
        venue = venues.verify_venue(session, venue_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    return {"id": venue.id, "verified": venue.verified}


@app.get("/manuscripts/{manuscript_id}/venue-compliance/{venue_id}")
def venue_compliance(
    manuscript_id: str,
    venue_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .models import Project, VenueProfile

    manuscript = session.get(ResearchObject, manuscript_id)
    venue = session.get(VenueProfile, venue_id)
    project = session.get(Project, manuscript.project_id) if manuscript else None
    if venue is None or project is None or venue.workspace_id != project.workspace_id:
        raise HTTPException(404, "venue not found")
    _require_workspace(session, venue.workspace_id, user, "viewer")
    try:
        findings = venues.audit_venue_compliance(session, manuscript_id, venue_id)
    except research.IntegrityError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"findings": findings, "counts": _severity_counts(findings)}


# --- users, tenant membership, and scoped credentials ---


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@app.post("/users")
def create_user(body: UserIn, session: Session = Depends(_session)):
    if get_settings().auth_required:
        raise HTTPException(403, "legacy user creation is available only in local mode")
    user = security.create_user(session, body.name)
    session.commit()
    return {"id": user.id, "name": user.name, "api_key": user.api_key}


class MemberIn(BaseModel):
    user_id: str
    role: str


@app.post("/projects/{project_id}/members")
def add_member(
    project_id: str,
    body: MemberIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require(session, project_id, user, "owner")
    try:
        member = security.add_member(session, project_id, body.user_id, body.role)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    project = session.get(Project, project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor=user.id,
        action="grant_project_role",
        object_type="project_member",
        object_id=member.id,
        detail={"target_user_id": member.user_id, "role": member.role},
    )
    session.commit()
    return {"id": member.id, "user_id": member.user_id, "role": member.role}


class WorkspaceMemberIn(BaseModel):
    user_id: str
    role: str


@app.get("/workspaces/{workspace_id}/members")
def list_workspace_members(
    workspace_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .models import WorkspaceMember

    _require_workspace(session, workspace_id, user, "admin")
    rows = session.scalars(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.deleted_at.is_(None),
        )
    )
    return [{"user_id": row.user_id, "role": row.role} for row in rows]


@app.post("/workspaces/{workspace_id}/members")
def add_workspace_member(
    workspace_id: str,
    body: WorkspaceMemberIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require_workspace(session, workspace_id, user, "owner")
    try:
        member = security.add_workspace_member(session, workspace_id, body.user_id, body.role)
    except research.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    record_audit(
        session,
        workspace_id=workspace_id,
        actor=user.id,
        action="grant_workspace_role",
        object_type="workspace_member",
        object_id=member.id,
        detail={"target_user_id": member.user_id, "role": member.role},
    )
    session.commit()
    return {"id": member.id, "user_id": member.user_id, "role": member.role}


class OidcBindingIn(BaseModel):
    tenant_key: str = Field(min_length=1, max_length=500)
    default_role: str = "member"


@app.get("/workspaces/{workspace_id}/oidc-bindings")
def list_oidc_bindings(
    workspace_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .models import OidcWorkspaceBinding

    _require_workspace(session, workspace_id, user, "owner")
    rows = session.scalars(
        select(OidcWorkspaceBinding).where(
            OidcWorkspaceBinding.workspace_id == workspace_id,
            OidcWorkspaceBinding.deleted_at.is_(None),
        )
    )
    return [
        {
            "id": row.id,
            "issuer": row.issuer,
            "tenant_key": row.tenant_key,
            "default_role": row.default_role,
        }
        for row in rows
    ]


@app.post("/workspaces/{workspace_id}/oidc-bindings")
def create_oidc_binding(
    workspace_id: str,
    body: OidcBindingIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .models import OidcWorkspaceBinding

    _require_workspace(session, workspace_id, user, "owner")
    settings = get_settings()
    if settings.oidc_mode != "live" or not settings.oidc_issuer:
        raise HTTPException(422, "live OIDC issuer must be configured before binding")
    if body.default_role not in security.WORKSPACE_ROLE_RANK:
        raise HTTPException(422, "invalid default workspace role")
    if body.default_role in {"admin", "owner"}:
        raise HTTPException(422, "OIDC JIT bindings cannot grant admin or owner")
    existing = session.scalars(
        select(OidcWorkspaceBinding).where(
            OidcWorkspaceBinding.issuer == settings.oidc_issuer,
            OidcWorkspaceBinding.tenant_key == body.tenant_key,
        )
    ).first()
    if existing and existing.workspace_id != workspace_id:
        raise HTTPException(409, "issuer tenant key is already bound")
    if existing:
        existing.default_role = body.default_role
        existing.deleted_at = None
        binding = existing
    else:
        binding = OidcWorkspaceBinding(
            workspace_id=workspace_id,
            issuer=settings.oidc_issuer,
            tenant_key=body.tenant_key,
            default_role=body.default_role,
        )
        session.add(binding)
        session.flush()
    record_audit(
        session,
        workspace_id=workspace_id,
        actor=user.id,
        action="bind_oidc_tenant",
        object_type="oidc_workspace_binding",
        object_id=binding.id,
        detail={
            "issuer": binding.issuer,
            "tenant_key": binding.tenant_key,
            "default_role": binding.default_role,
        },
    )
    session.commit()
    return {
        "id": binding.id,
        "issuer": binding.issuer,
        "tenant_key": binding.tenant_key,
        "default_role": binding.default_role,
    }


class ApiCredentialIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])
    expires_at: datetime | None = None


@app.get("/workspaces/{workspace_id}/api-keys")
def list_api_credentials(
    workspace_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .models import ApiCredential

    _require_workspace(session, workspace_id, user, "viewer")
    rows = session.scalars(
        select(ApiCredential).where(
            ApiCredential.workspace_id == workspace_id,
            ApiCredential.user_id == user.id,
            ApiCredential.deleted_at.is_(None),
        )
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "key_prefix": row.key_prefix,
            "scopes": row.scopes,
            "expires_at": row.expires_at,
            "revoked_at": row.revoked_at,
            "last_used_at": row.last_used_at,
        }
        for row in rows
    ]


@app.post("/workspaces/{workspace_id}/api-keys")
def create_api_credential(
    workspace_id: str,
    body: ApiCredentialIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    _require_workspace(session, workspace_id, user, "viewer")
    if user.auth_method == "api_key" and "admin" not in user.scopes:
        raise HTTPException(403, "creating API credentials requires admin scope")
    if "admin" in body.scopes:
        _require_workspace(session, workspace_id, user, "owner")
    expires_at = body.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at and expires_at <= datetime.now(UTC):
        raise HTTPException(422, "expires_at must be in the future")
    try:
        credential, token = auth.create_api_credential(
            session,
            user_id=user.id,
            workspace_id=workspace_id,
            name=body.name,
            scopes=body.scopes,
            expires_at=expires_at,
        )
    except auth.AuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    record_audit(
        session,
        workspace_id=workspace_id,
        actor=user.id,
        action="create_api_credential",
        object_type="api_credential",
        object_id=credential.id,
        detail={"name": credential.name, "scopes": credential.scopes},
    )
    session.commit()
    return {
        "id": credential.id,
        "name": credential.name,
        "key_prefix": credential.key_prefix,
        "scopes": credential.scopes,
        "api_key": token,
        "warning": "This credential is shown once and cannot be recovered.",
    }


@app.post("/api-keys/{credential_id}/revoke")
def revoke_api_credential(
    credential_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    from .models import ApiCredential

    credential = session.get(ApiCredential, credential_id)
    if credential is None or credential.deleted_at is not None:
        raise HTTPException(404, "API credential not found")
    if credential.user_id != user.id:
        _require_workspace(session, credential.workspace_id, user, "owner")
    credential.revoked_at = datetime.now(UTC)
    record_audit(
        session,
        workspace_id=credential.workspace_id,
        actor=user.id,
        action="revoke_api_credential",
        object_type="api_credential",
        object_id=credential.id,
        detail={"owner_user_id": credential.user_id},
    )
    session.commit()
    return {"id": credential.id, "revoked": True}


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
        "id": sub.id,
        "manuscript_id": sub.manuscript_id,
        "venue_name": sub.venue_name,
        "status": sub.status,
        "deadline": sub.deadline,
        "history": sub.history,
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


# --- review-gated publication packages ---


class PublicationPackageIn(BaseModel):
    included_formats: list[str] = Field(
        default_factory=lambda: ["md", "tex", "html", "docx", "bib", "pdf", "jats"]
    )


@app.post("/submissions/{submission_id}/publication-packages")
def create_publication_package(
    submission_id: str,
    body: PublicationPackageIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        submission = submissions.get_submission(session, submission_id)
        _require(session, submission.project_id, user, "coauthor")
        package = publication_packages.create_package(
            session, submission_id, included_formats=body.included_formats
        )
        session.commit()
        return publication_packages.package_out(session, package)
    except (submissions.SubmissionError, publication_packages.PackageError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/projects/{project_id}/publication-packages")
def list_publication_packages(project_id: str, session: Session = Depends(_session)):
    try:
        packages = publication_packages.list_packages(session, project_id=project_id)
        return [publication_packages.package_out(session, package) for package in packages]
    except publication_packages.PackageError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/publication-packages/{package_id}")
def get_publication_package(package_id: str, session: Session = Depends(_session)):
    try:
        package = publication_packages.get_package(session, package_id)
        return publication_packages.package_out(session, package)
    except publication_packages.PackageError as exc:
        raise HTTPException(404, str(exc)) from exc


class CoverLetterIn(BaseModel):
    text: str = Field(min_length=1)
    state: Literal["draft", "confirmed"] = "draft"
    review_note: str = ""


@app.post("/publication-packages/{package_id}/cover-letter")
def set_package_cover_letter(
    package_id: str,
    body: CoverLetterIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        package = publication_packages.get_package(session, package_id)
        _require(session, package.project_id, user, "coauthor")
        publication_packages.set_cover_letter(session, package_id, **body.model_dump())
        session.commit()
        return publication_packages.package_out(session, package)
    except publication_packages.PackageError as exc:
        raise HTTPException(422, str(exc)) from exc


class CoverLetterTemplateIn(BaseModel):
    significance: str = Field(min_length=1)
    venue_fit: str = Field(min_length=1)
    editor_name: str = "Editor"


@app.post("/publication-packages/{package_id}/cover-letter/template")
def draft_package_cover_letter(
    package_id: str,
    body: CoverLetterTemplateIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        package = publication_packages.get_package(session, package_id)
        _require(session, package.project_id, user, "coauthor")
        publication_packages.draft_cover_letter(session, package_id, **body.model_dump())
        session.commit()
        return publication_packages.package_out(session, package)
    except publication_packages.PackageError as exc:
        raise HTTPException(422, str(exc)) from exc


class DeclarationIn(BaseModel):
    kind: str
    state: Literal["draft", "confirmed", "not_applicable"]
    text: str = ""
    review_note: str = ""


@app.post("/publication-packages/{package_id}/declarations")
def set_package_declaration(
    package_id: str,
    body: DeclarationIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        package = publication_packages.get_package(session, package_id)
        _require(session, package.project_id, user, "coauthor")
        publication_packages.set_declaration(session, package_id, **body.model_dump())
        session.commit()
        return publication_packages.package_out(session, package)
    except publication_packages.PackageError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/publication-packages/{package_id}/prepare")
def prepare_publication_package(
    package_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        package = publication_packages.get_package(session, package_id)
        _require(session, package.project_id, user, "coauthor")
        publication_packages.prepare_for_review(session, package_id)
        session.commit()
        return publication_packages.package_out(session, package)
    except publication_packages.PackageError as exc:
        raise HTTPException(422, str(exc)) from exc


class PublicationPackageReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=1)


@app.post("/publication-packages/{package_id}/review")
def review_publication_package(
    package_id: str,
    body: PublicationPackageReviewIn,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        package = publication_packages.get_package(session, package_id)
        _require(session, package.project_id, user, "coauthor")
        publication_packages.review_package(session, package_id, **body.model_dump())
        session.commit()
        return publication_packages.package_out(session, package)
    except publication_packages.PackageError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/publication-packages/{package_id}/builds/{build_index}/download")
def download_publication_package(
    package_id: str,
    build_index: int,
    session: Session = Depends(_session),
):
    try:
        package = publication_packages.get_package(session, package_id)
    except publication_packages.PackageError as exc:
        raise HTTPException(404, str(exc)) from exc
    builds = list(package.builds)
    if build_index < 0 or build_index >= len(builds):
        raise HTTPException(404, "publication package build not found")
    build = builds[build_index]
    reference = build.get("artifact")
    if not isinstance(reference, dict):
        path = Path(str(build.get("path") or ""))
        if not path.is_file():
            raise HTTPException(404, "publication package artifact not found")
        payload = path.read_bytes()
    else:
        try:
            payload = storage.read_bytes(reference)
        except storage.ArtifactStorageError as exc:
            raise HTTPException(404, str(exc)) from exc
    filename = Path(str(build.get("filename") or "publication-package.zip")).name
    return _download_response(payload, filename, "application/zip")


@app.post("/publication-packages/{package_id}/build")
def build_publication_package(
    package_id: str,
    session: Session = Depends(_session),
    user=Depends(_principal),
):
    try:
        package = publication_packages.get_package(session, package_id)
        _require(session, package.project_id, user, "coauthor")
        result = publication_packages.build_bundle(session, package_id)
        session.commit()
        return result
    except publication_packages.PackageError as exc:
        raise HTTPException(409, str(exc)) from exc


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


class ReviseEditIn(ApproveIn):
    text: str = Field(max_length=manuscript_chat.MAX_SECTION_CHARS)


@app.post("/actions/{action_id}/revise")
def revise_edit(action_id: str, body: ReviseEditIn, session: Session = Depends(_session)):
    try:
        action = dialogue.revise_proposal(session, action_id, **body.model_dump())
    except dialogue.DialogueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return {"id": action.id, "plan_hash": action.plan_hash}


@app.post("/actions/{action_id}/undo")
def undo_edit(action_id: str, body: ApproveIn, session: Session = Depends(_session)):
    try:
        action = dialogue.revise_proposal(session, action_id, plan_hash=body.plan_hash, undo=True)
    except dialogue.DialogueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return {"id": action.id, "plan_hash": action.plan_hash}


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


research_api.install(app, _session, _principal, _require, _bounded_upload, _download_response)
