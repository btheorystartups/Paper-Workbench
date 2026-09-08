"""Workspace-tenant and project authorization.

A workspace is the tenant boundary. Authentication-required deployments must pass both
workspace membership and project-role checks; local mode retains the historical bootstrap
behavior. Direct resource routes are resolved back to their owning project here so a caller
cannot bypass isolation by substituting an object/source/thread identifier.
"""

import re
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    ApiCredential,
    AuthorshipProposal,
    Claim,
    ComputeRun,
    CreditAssignment,
    Project,
    ProjectMember,
    ProposedAction,
    PublicationPackage,
    ResearchObject,
    SavedSearch,
    Source,
    Submission,
    Thread,
    User,
    VenueProfile,
    Workspace,
    WorkspaceMember,
)
from . import research

ROLE_RANK = {"reviewer": 1, "editor": 2, "coauthor": 3, "owner": 4}
WORKSPACE_ROLE_RANK = {"viewer": 1, "member": 2, "admin": 3, "owner": 4}


class Forbidden(PermissionError):
    pass


class HiddenResource(LookupError):
    """Missing or outside the caller's tenant; both intentionally become HTTP 404."""


@dataclass(frozen=True)
class ResourceScope:
    workspace_id: str
    project_id: str | None = None


def create_user(session: Session, name: str) -> User:
    """Legacy local-mode identity creation with a plaintext development key."""
    user = User(name=name, api_key=secrets.token_hex(16))
    session.add(user)
    session.flush()
    return user


def default_user(session: Session) -> User:
    """Local single-user bootstrap: first user is auto-created with a stable dev key."""
    user = session.scalars(select(User).where(User.deleted_at.is_(None))).first()
    if user is None:
        user = User(name="local-user", api_key="dev-local")
        session.add(user)
        session.flush()
    return user


def resolve_principal(session: Session, api_key: str | None) -> User:
    """Compatibility helper for local-mode callers; production uses ``workbench.auth``."""
    if not api_key:
        return default_user(session)
    user = session.scalars(
        select(User).where(User.api_key == api_key, User.deleted_at.is_(None))
    ).first()
    if user is None:
        raise Forbidden("unknown API key")
    return user


def add_workspace_member(
    session: Session, workspace_id: str, user_id: str, role: str
) -> WorkspaceMember:
    if role not in WORKSPACE_ROLE_RANK:
        raise research.IntegrityError(
            f"workspace role must be one of {sorted(WORKSPACE_ROLE_RANK)}"
        )
    if session.get(Workspace, workspace_id) is None:
        raise research.IntegrityError("workspace not found")
    if session.get(User, user_id) is None:
        raise research.IntegrityError("user not found")
    existing = session.scalars(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).first()
    if existing:
        existing.role = role
        existing.deleted_at = None
        return existing
    member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
    session.add(member)
    session.flush()
    return member


def workspace_role_of(session: Session, workspace_id: str, user_id: str) -> str | None:
    member = session.scalars(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.deleted_at.is_(None),
        )
    ).first()
    return member.role if member else None


def require_workspace_role(
    session: Session,
    workspace_id: str,
    user_id: str,
    minimum: str,
    *,
    bound_workspace_id: str | None = None,
) -> str:
    if minimum not in WORKSPACE_ROLE_RANK:
        raise ValueError(f"unknown workspace role: {minimum}")
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise HiddenResource("workspace not found")
    if bound_workspace_id and workspace_id != bound_workspace_id:
        raise HiddenResource("workspace not found")
    role = workspace_role_of(session, workspace_id, user_id)
    if role is None:
        raise HiddenResource("workspace not found")
    if WORKSPACE_ROLE_RANK[role] < WORKSPACE_ROLE_RANK[minimum]:
        raise Forbidden(f"requires workspace role >= {minimum}; you have {role}")
    return role


def add_member(session: Session, project_id: str, user_id: str, role: str) -> ProjectMember:
    if role not in ROLE_RANK:
        raise research.IntegrityError(f"role must be one of {sorted(ROLE_RANK)}")
    project = session.get(Project, project_id)
    if project is None:
        raise research.IntegrityError("project not found")
    if session.get(User, user_id) is None:
        raise research.IntegrityError("user not found")
    if workspace_role_of(session, project.workspace_id, user_id) is None:
        add_workspace_member(session, project.workspace_id, user_id, "member")
    existing = session.scalars(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
    ).first()
    if existing:
        existing.role = role
        existing.deleted_at = None
        return existing
    member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    session.add(member)
    session.flush()
    return member


def role_of(session: Session, project_id: str, user_id: str) -> str | None:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        return None
    workspace_role = workspace_role_of(session, project.workspace_id, user_id)
    if workspace_role in {"admin", "owner"}:
        return "owner"
    member = session.scalars(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.deleted_at.is_(None),
        )
    ).first()
    if member:
        return member.role
    if not get_settings().auth_required:
        any_member = session.scalars(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.deleted_at.is_(None),
            )
        ).first()
        return "owner" if any_member is None else None
    return None


def require_role(
    session: Session,
    project_id: str,
    user_id: str,
    minimum: str,
    *,
    bound_workspace_id: str | None = None,
) -> None:
    if minimum not in ROLE_RANK:
        raise ValueError(f"unknown project role: {minimum}")
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HiddenResource("project not found")
    if not get_settings().auth_required:
        role = role_of(session, project_id, user_id)
        if role is None or ROLE_RANK[role] < ROLE_RANK[minimum]:
            raise Forbidden(f"requires role >= {minimum}; you have {role or 'no membership'}")
        return
    require_workspace_role(
        session,
        project.workspace_id,
        user_id,
        "viewer",
        bound_workspace_id=bound_workspace_id,
    )
    role = role_of(session, project_id, user_id)
    if role is None:
        raise HiddenResource("project not found")
    if ROLE_RANK[role] < ROLE_RANK[minimum]:
        raise Forbidden(f"requires role >= {minimum}; you have {role}")


_DIRECT_PROJECT_MODELS = {
    "objects": ResearchObject,
    "paper-candidates": ResearchObject,
    "manuscripts": ResearchObject,
    "artifacts": ResearchObject,
    "figures": ResearchObject,
    "checklists": ResearchObject,
    "sources": Source,
    "claims": Claim,
    "threads": Thread,
    "saved-searches": SavedSearch,
    "credit-assignments": CreditAssignment,
    "authorship-proposals": AuthorshipProposal,
    "compute-runs": ComputeRun,
    "submissions": Submission,
    "publication-packages": PublicationPackage,
}


def request_resource_scope(session: Session, path: str) -> ResourceScope | None:
    """Resolve a routed API path to its tenant/project without trusting caller input."""
    if path == "/projects/import":
        return None
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None
    root, resource_id = parts[0], parts[1]
    if root == "workspaces":
        workspace = session.get(Workspace, resource_id)
        return ResourceScope(workspace.id) if workspace else None
    if root == "projects":
        project = session.get(Project, resource_id)
        return ResourceScope(project.workspace_id, project.id) if project else None
    if root == "venues":
        venue = session.get(VenueProfile, resource_id)
        return ResourceScope(venue.workspace_id) if venue else None
    if root == "api-keys":
        credential = session.get(ApiCredential, resource_id)
        return ResourceScope(credential.workspace_id) if credential else None
    model = _DIRECT_PROJECT_MODELS.get(root)
    if model is not None:
        record = session.get(model, resource_id)
        if record is None:
            return None
        project = session.get(Project, record.project_id)
        return ResourceScope(project.workspace_id, project.id) if project else None
    if root == "actions":
        project_id = session.scalar(
            select(Thread.project_id)
            .join(ProposedAction, ProposedAction.thread_id == Thread.id)
            .where(ProposedAction.id == resource_id)
        )
        if project_id:
            project = session.get(Project, project_id)
            return ResourceScope(project.workspace_id, project.id) if project else None
    return None


_EDITOR_PATHS = (
    re.compile(r"^/projects/[^/]+/sources/merge$"),
    re.compile(r"^/projects/[^/]+/integrity/check$"),
    re.compile(r"^/projects/[^/]+/sources/[^/]+/citations/discover$"),
    re.compile(r"^/projects/[^/]+/citations/[^/]+/(resolve|review)$"),
    re.compile(r"^/manuscripts/[^/]+/sections$"),
)
_REVIEWER_POST_PATHS = (
    re.compile(r"^/projects/[^/]+/paper-candidates/compare$"),
    re.compile(r"^/projects/[^/]+/semantic/search$"),
    re.compile(r"^/compute-runs/[^/]+/review$"),
)
_READ_ONLY_POST_PATHS = (
    re.compile(r"^/projects/[^/]+/paper-candidates/compare$"),
    re.compile(r"^/projects/[^/]+/semantic/search$"),
    re.compile(r"^/workspaces/[^/]+/portfolio/search$"),
)


def minimum_project_role(path: str, method: str) -> str:
    if method in {"GET", "HEAD"}:
        return "reviewer"
    if any(pattern.match(path) for pattern in _REVIEWER_POST_PATHS):
        return "reviewer"
    if any(pattern.match(path) for pattern in _EDITOR_PATHS):
        return "editor"
    if re.match(r"^/projects/[^/]+/(members|budget)$", path):
        return "owner"
    return "coauthor"


def required_api_scope(path: str, method: str) -> str:
    if method in {"GET", "HEAD"} or any(
        pattern.match(path) for pattern in _READ_ONLY_POST_PATHS
    ):
        return "read"
    if (
        path.startswith("/venues")
        or path.endswith("/members")
        or path.endswith("/budget")
        or path.endswith("/oidc-bindings")
    ):
        return "admin"
    return "write"


def authorize_request_scope(
    session: Session,
    *,
    path: str,
    method: str,
    user_id: str,
    bound_workspace_id: str | None,
) -> None:
    scope = request_resource_scope(session, path)
    if scope is None:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {
            *_DIRECT_PROJECT_MODELS,
            "actions",
            "api-keys",
            "projects",
            "venues",
            "workspaces",
        }:
            raise HiddenResource("resource not found")
        return
    if scope.project_id:
        require_role(
            session,
            scope.project_id,
            user_id,
            minimum_project_role(path, method),
            bound_workspace_id=bound_workspace_id,
        )
        return
    minimum = "viewer"
    if method not in {"GET", "HEAD"} and re.match(
        r"^/workspaces/[^/]+/(members|oidc-bindings)$", path
    ):
        minimum = "owner"
    require_workspace_role(
        session,
        scope.workspace_id,
        user_id,
        minimum,
        bound_workspace_id=bound_workspace_id,
    )
