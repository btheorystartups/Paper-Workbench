"""Audit-in-transaction (pattern from POP core/audit.py): every consequential mutation
records an AuditEvent in the same session/transaction as the mutation itself.
"""

from sqlalchemy.orm import Session

from .models import AuditEvent, stable_hash


def record_audit(
    session: Session,
    *,
    workspace_id: str,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    detail: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        workspace_id=workspace_id,
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        payload_hash=stable_hash(detail or {}),
        detail=detail or {},
    )
    session.add(event)
    return event
