"""Canonical research-graph schema (Phase 0 decision record: canonical model).

Design rules:
- stable UUID string ids; workspace/project isolation on every row that needs scoping;
- soft delete via deleted_at; timestamps in UTC;
- provenance never optional: sources carry access level + license + acquisition,
  excerpts carry locator + checksum, AI turns carry model/prompt provenance;
- claims link to evidence explicitly; support states from vocab are NOT nullable.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .vocab import (
    ActionStatus,
    ClaimSupport,
    ObjectKind,
    Relation,
    ResultStrength,
    SourceAccess,
)


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


def stable_hash(payload: dict) -> str:
    """Deterministic hash for plan binding and audit (pattern from POP core/audit.py)."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class Base(DeclarativeBase):
    pass


class _Stamped:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class Workspace(_Stamped, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(200))


class Project(_Stamped, Base):
    __tablename__ = "projects"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")


class ResearchObject(_Stamped, Base):
    """One node of the research graph. `kind` from vocab.ObjectKind; kind-specific payload
    (formal statement, task state, dataset path, section text, ...) in `body` JSON."""

    __tablename__ = "research_objects"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[ObjectKind] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    strength: Mapped[ResultStrength | None] = mapped_column(String(60), default=None)
    ai_suggested: Mapped[bool] = mapped_column(default=False)
    accepted_by_user: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_objects_project_kind", "project_id", "kind"),)


class Edge(_Stamped, Base):
    """Typed relationship between two research objects (same project)."""

    __tablename__ = "edges"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    src_id: Mapped[str] = mapped_column(ForeignKey("research_objects.id"), index=True)
    dst_id: Mapped[str] = mapped_column(ForeignKey("research_objects.id"), index=True)
    relation: Mapped[Relation] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("src_id", "dst_id", "relation"),)


class Source(_Stamped, Base):
    """External source record. Snippets/search hits are discovery, never evidence:
    a Source becomes citable evidence only through Excerpts or verified metadata."""

    __tablename__ = "sources"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(600))
    authors: Mapped[str] = mapped_column(Text, default="")  # "A; B; C"
    year: Mapped[int | None] = mapped_column(default=None)
    venue: Mapped[str] = mapped_column(String(300), default="")
    doi: Mapped[str | None] = mapped_column(String(200), default=None, index=True)
    url: Mapped[str | None] = mapped_column(String(1000), default=None)
    access: Mapped[SourceAccess] = mapped_column(String(40))
    license: Mapped[str] = mapped_column(String(200), default="unknown")
    acquisition: Mapped[str] = mapped_column(String(200), default="")  # how we got it
    human_verified: Mapped[bool] = mapped_column(default=False)
    integrity_note: Mapped[str] = mapped_column(Text, default="")  # retraction/correction flags
    provider_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class Excerpt(_Stamped, Base):
    """Bounded quotation/extract from a Source with a durable locator and checksum."""

    __tablename__ = "excerpts"
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    locator: Mapped[str] = mapped_column(String(300))  # page/section/offset descriptor
    checksum: Mapped[str] = mapped_column(String(64))


class Claim(_Stamped, Base):
    """A substantive claim. Support state is mandatory; evidence links are checked by
    services.claims (an EXTERNAL_SOURCE/BOTH claim without excerpt evidence is rejected)."""

    __tablename__ = "claims"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    support: Mapped[ClaimSupport] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text, default="")


class ClaimEvidence(_Stamped, Base):
    __tablename__ = "claim_evidence"
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    excerpt_id: Mapped[str | None] = mapped_column(ForeignKey("excerpts.id"), default=None)
    research_object_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_objects.id"), default=None
    )
    entailment: Mapped[str] = mapped_column(String(40), default="asserted")  # asserted|verified


class Thread(_Stamped, Base):
    """Persistent research dialogue thread; summary is user-editable continuation state."""

    __tablename__ = "threads"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    goal: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    pinned_object_ids: Mapped[list] = mapped_column(JSON, default=list)
    pinned_source_ids: Mapped[list] = mapped_column(JSON, default=list)


class Turn(_Stamped, Base):
    __tablename__ = "turns"
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user|assistant|system
    content: Mapped[str] = mapped_column(Text)
    # AI provenance: model, provider, prompt hash, context object/source ids, usage.
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)


class ProposedAction(_Stamped, Base):
    """Dialogue conclusions become explicit reviewable actions; nothing mutates the graph
    silently (plan→confirm→execute→audit harness, pattern from POP command module)."""

    __tablename__ = "proposed_actions"
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    kind: Mapped[str] = mapped_column(String(60))  # e.g. create_object, link_objects
    risk: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    plan_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[ActionStatus] = mapped_column(String(20), default=ActionStatus.PROPOSED)
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class SavedSearch(_Stamped, Base):
    """A literature/discovery query with provenance: provider, filters, when last run.
    Results are imported explicitly as Sources — a search run never auto-creates evidence."""

    __tablename__ = "saved_searches"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))  # openalex|crossref|brave|fake
    query: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)
    last_result_count: Mapped[int] = mapped_column(default=0)
    protocol_note: Mapped[str] = mapped_column(Text, default="exploratory")  # never "systematic" by default


class LiteratureEntry(_Stamped, Base):
    """Screening decision + structured literature-matrix row for one Source."""

    __tablename__ = "literature_entries"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    state: Mapped[str] = mapped_column(String(20), default="unread")  # unread|maybe|include|exclude
    reason: Mapped[str] = mapped_column(Text, default="")
    # supports | contradicts | background
    relationship: Mapped[str] = mapped_column(String(20), default="background")
    question: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(Text, default="")
    result_summary: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[str] = mapped_column(Text, default="")
    relevance: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("project_id", "source_id"),)


class Embedding(_Stamped, Base):
    """Versioned embedding for one research object or source. Project-scoped retrieval
    only; similarity is a discovery signal, never evidence (ADR-5)."""

    __tablename__ = "embeddings"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(20))  # object|source
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(80))
    index_version: Mapped[int] = mapped_column(default=1)
    vector: Mapped[list] = mapped_column(JSON)
    text_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("target_type", "target_id", "model", "index_version"),)


class User(_Stamped, Base):
    """Collaboration identity. `api_key` is the local dev-token path; `email` +
    `password_hash` enable real password auth; `oidc_subject` links a federated identity.
    None of these are populated in local single-user mode until auth is enabled."""

    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(200))
    api_key: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, default=None)
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), unique=True, default=None)
    email_verified: Mapped[bool] = mapped_column(default=False)


class ProjectMember(_Stamped, Base):
    __tablename__ = "project_members"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # owner|coauthor|reviewer|editor

    __table_args__ = (UniqueConstraint("project_id", "user_id"),)


class VenueProfile(_Stamped, Base):
    """Journal/venue rules. `verified` must be set by a human before compliance audits
    treat the rules as authoritative; `rules_source` records where/when rules came from."""

    __tablename__ = "venue_profiles"
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(300))
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    rules_source: Mapped[str] = mapped_column(Text, default="")
    retrieved_at: Mapped[datetime | None] = mapped_column(default=None)
    verified: Mapped[bool] = mapped_column(default=False)


class Submission(_Stamped, Base):
    """Tracks a manuscript's journey to a venue through an explicit state machine.
    `history` is an append-only list of {at, from, to, note}; `revisions` holds
    response-to-reviewers documents. Nothing here submits anything externally — it is a
    record the researcher maintains."""

    __tablename__ = "submissions"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    manuscript_id: Mapped[str] = mapped_column(ForeignKey("research_objects.id"), index=True)
    venue_id: Mapped[str | None] = mapped_column(ForeignKey("venue_profiles.id"), default=None)
    venue_name: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(30), default="drafting")
    deadline: Mapped[str | None] = mapped_column(String(40), default=None)  # ISO date
    history: Mapped[list] = mapped_column(JSON, default=list)
    revisions: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class UsageEvent(_Stamped, Base):
    """One provider call's token usage, attributed to a project and a call kind.
    `simulated` rows (fake provider) are recorded for observability but never count
    toward a cost ceiling."""

    __tablename__ = "usage_events"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(60))  # dialogue|skeptical_review|outputs|...
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    simulated: Mapped[bool] = mapped_column(default=False)


class CostBudget(_Stamped, Base):
    """Per-project ceiling on live LLM token spend per UTC calendar month.
    ceiling 0 = unlimited. Enforcement is fail-closed: when the ceiling is reached,
    live calls raise before the provider is contacted."""

    __tablename__ = "cost_budgets"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), unique=True)
    monthly_token_ceiling: Mapped[int] = mapped_column(default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AuditEvent(_Stamped, Base):
    __tablename__ = "audit_events"
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(100))  # "user" | "assistant" | job name
    action: Mapped[str] = mapped_column(String(100))
    object_type: Mapped[str] = mapped_column(String(60))
    object_id: Mapped[str] = mapped_column(String(32))
    payload_hash: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
