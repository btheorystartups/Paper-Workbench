"""Collaboration roles (local trust model — honest scope: this is single-machine
role bookkeeping with API-key identities, not hardened multi-tenant auth. The schema
and checks are the migration path to real auth later).

Roles (ascending capability): reviewer < editor < coauthor < owner.
- reviewer: read + comments/objections
- editor: edit manuscript text/sections
- coauthor: everything except membership/venue admin and deletion
- owner: all
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project, ProjectMember, User
from . import research

ROLE_RANK = {"reviewer": 1, "editor": 2, "coauthor": 3, "owner": 4}


class Forbidden(PermissionError):
    pass


def create_user(session: Session, name: str) -> User:
    user = User(name=name, api_key=secrets.token_hex(16))
    session.add(user)
    session.flush()
    return user


def default_user(session: Session) -> User:
    """Local single-user bootstrap: first user is auto-created with a stable dev key."""
    user = session.scalars(select(User)).first()
    if user is None:
        user = User(name="local-user", api_key="dev-local")
        session.add(user)
        session.flush()
    return user


def resolve_principal(session: Session, api_key: str | None) -> User:
    if not api_key:
        return default_user(session)
    user = session.scalars(select(User).where(User.api_key == api_key)).first()
    if user is None:
        raise Forbidden("unknown API key")
    return user


def add_member(session: Session, project_id: str, user_id: str, role: str) -> ProjectMember:
    if role not in ROLE_RANK:
        raise research.IntegrityError(f"role must be one of {sorted(ROLE_RANK)}")
    if session.get(Project, project_id) is None:
        raise research.IntegrityError("project not found")
    if session.get(User, user_id) is None:
        raise research.IntegrityError("user not found")
    existing = session.scalars(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
    ).first()
    if existing:
        existing.role = role
        return existing
    member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    session.add(member)
    session.flush()
    return member


def role_of(session: Session, project_id: str, user_id: str) -> str | None:
    member = session.scalars(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
    ).first()
    if member:
        return member.role
    # Bootstrap rule: a project with NO members at all is owned by whoever acts on it
    # (local single-user mode). The first explicit add_member ends this grace mode.
    any_member = session.scalars(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    ).first()
    return "owner" if any_member is None else None


def require_role(session: Session, project_id: str, user_id: str, minimum: str) -> None:
    role = role_of(session, project_id, user_id)
    if role is None or ROLE_RANK[role] < ROLE_RANK[minimum]:
        raise Forbidden(
            f"requires role >= {minimum}; you have {role or 'no membership'}"
        )
