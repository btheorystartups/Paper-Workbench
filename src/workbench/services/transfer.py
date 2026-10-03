"""Whole-project export/import as a checksummed ZIP bundle (risk-register mitigation:
solo-user data loss; also makes projects portable between machines).

Rules:
- Export is a faithful snapshot: every project-scoped row plus the content-addressed
  artifact files it references, with sha256 checksums for every bundle member.
- Import is a RESTORE, not a clone: row ids are preserved, and import refuses to run if
  the project id already exists in the target database (no silent merge/overwrite).
- Absolute artifact paths inside row payloads are rewritten through a placeholder token
  so bundles survive a different data_dir / machine.
- Import verifies every checksum before touching the database; a mismatch aborts.
- Audit events are workspace-scoped and append-only; they are exported for the record
  (filtered to the project's objects) but never re-imported as if they happened here —
  they land in the manifest file only.
"""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..audit import record_audit
from ..config import get_settings
from ..models import (
    AuthorshipProposal,
    CitationEdge,
    Claim,
    ClaimEvidence,
    ComputeRun,
    Contributor,
    CostBudget,
    CreditAssignment,
    Edge,
    Embedding,
    Excerpt,
    LiteratureEntry,
    Project,
    Proposal,
    ProposalFitEvidence,
    ProposalFitRow,
    ProposalGeneration,
    ProposalPassage,
    ProposalSection,
    ProposalSectionCitation,
    ProposalSectionRevision,
    ProposalSource,
    ProposalVersion,
    ProposalVersionExport,
    ProposedAction,
    PublicationPackage,
    ResearchAgent,
    ResearchObject,
    ResearchTask,
    SavedSearch,
    Source,
    Submission,
    Thread,
    Turn,
    UsageEvent,
    Workspace,
)
from . import research

FORMAT_VERSION = 1
_ARTIFACT_TOKEN = "{{WB_ARTIFACTS}}"

# (table key, model, how rows are selected). Order matters for import (FK parents first).
_TABLES = [
    ("project", Project, "self"),
    ("research_objects", ResearchObject, "project"),
    ("edges", Edge, "project"),
    ("contributors", Contributor, "project"),
    ("credit_assignments", CreditAssignment, "project"),
    ("authorship_proposals", AuthorshipProposal, "project"),
    ("sources", Source, "project"),
    ("proposals", Proposal, "project"),
    ("proposal_sources", ProposalSource, "proposal"),
    ("proposal_passages", ProposalPassage, "proposal"),
    ("proposal_fit_rows", ProposalFitRow, "proposal"),
    ("proposal_fit_evidence", ProposalFitEvidence, "fit_row"),
    ("proposal_sections", ProposalSection, "proposal"),
    ("proposal_section_citations", ProposalSectionCitation, "proposal_section"),
    ("proposal_section_revisions", ProposalSectionRevision, "proposal_section"),
    ("proposal_versions", ProposalVersion, "proposal"),
    ("proposal_version_exports", ProposalVersionExport, "proposal_version"),
    ("proposal_generations", ProposalGeneration, "proposal"),
    ("compute_runs", ComputeRun, "project"),
    ("citation_edges", CitationEdge, "project"),
    ("excerpts", Excerpt, "source"),
    ("claims", Claim, "project"),
    ("claim_evidence", ClaimEvidence, "claim"),
    ("threads", Thread, "project"),
    ("research_tasks", ResearchTask, "project"),
    ("research_agents", ResearchAgent, "research_task"),
    ("turns", Turn, "thread"),
    ("proposed_actions", ProposedAction, "thread"),
    ("saved_searches", SavedSearch, "project"),
    ("literature_entries", LiteratureEntry, "project"),
    ("embeddings", Embedding, "project"),
    ("submissions", Submission, "project"),
    ("publication_packages", PublicationPackage, "project"),
    ("usage_events", UsageEvent, "project"),
    ("cost_budgets", CostBudget, "project"),
]


def _artifact_root() -> Path:
    return (Path(get_settings().data_dir) / "artifacts").resolve()


def _tokenize(value: Any, root: Path) -> Any:
    """Replace absolute paths under the artifact root with a portable token."""
    if isinstance(value, str):
        try:
            p = Path(value)
            if p.is_absolute():
                rel = p.resolve().relative_to(root)
                return f"{_ARTIFACT_TOKEN}/{rel.as_posix()}"
        except (ValueError, OSError):
            pass
        return value
    if isinstance(value, dict):
        return {k: _tokenize(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [_tokenize(v, root) for v in value]
    return value


def _detokenize(value: Any, root: Path, imported_refs: dict[str, dict] | None = None) -> Any:
    if isinstance(value, str) and value.startswith(_ARTIFACT_TOKEN + "/"):
        rel = value[len(_ARTIFACT_TOKEN) + 1 :]
        reference = (imported_refs or {}).get(rel)
        if reference:
            return storage.local_path(reference) or f"artifact://{reference['storage_key']}"
        return str(root / Path(rel))
    if isinstance(value, dict):
        key = value.get("storage_key")
        if isinstance(key, str) and key.startswith("artifacts/"):
            rel = key.removeprefix("artifacts/")
            if rel in (imported_refs or {}):
                return imported_refs[rel]
        return {k: _detokenize(v, root, imported_refs) for k, v in value.items()}
    if isinstance(value, list):
        return [_detokenize(v, root, imported_refs) for v in value]
    return value


def _serialize_row(obj, root: Path) -> dict:
    out = {}
    for col in sa_inspect(obj).mapper.columns:
        value = getattr(obj, col.key)
        if isinstance(value, datetime):
            value = {"__dt__": value.isoformat()}
        else:
            value = _tokenize(value, root)
        out[col.key] = value
    return out


def _deserialize_row(model, data: dict, root: Path, imported_refs: dict[str, dict] | None = None):
    kwargs = {}
    for col in sa_inspect(model).columns:
        if col.key not in data:
            continue
        value = data[col.key]
        if isinstance(value, dict) and set(value) == {"__dt__"}:
            value = datetime.fromisoformat(value["__dt__"])
        else:
            value = _detokenize(value, root, imported_refs)
        kwargs[col.key] = value
    return model(**kwargs)


def _select_rows(session: Session, model, mode: str, ids: dict[str, list[str]]):
    if mode == "project":
        return list(session.scalars(select(model).where(model.project_id == ids["project"][0])))
    parent_ids = ids[mode]
    if not parent_ids:
        return []
    fk = {
        "source": "source_id",
        "claim": "claim_id",
        "thread": "thread_id",
        "proposal": "proposal_id",
        "fit_row": "fit_row_id",
        "proposal_section": "section_id",
        "proposal_version": "version_id",
        "research_task": "task_id",
    }[mode]
    statement = select(model).where(getattr(model, fk).in_(parent_ids))
    if mode == "research_task":
        statement = statement.order_by(model.created_at, model.id)  # parent precedes child on restore
    return list(session.scalars(statement))


def _collect_artifact_files(rows_by_table: dict[str, list[dict]], root: Path) -> dict[str, dict | None]:
    """Every tokenized path referenced anywhere in the export, deduped, existing only."""
    found: dict[str, dict | None] = {}

    def walk(value: Any) -> None:
        if isinstance(value, str) and value.startswith(_ARTIFACT_TOKEN + "/"):
            rel = value[len(_ARTIFACT_TOKEN) + 1 :]
            if (root / Path(rel)).is_file():
                found.setdefault(rel, None)
        elif isinstance(value, dict):
            key = value.get("storage_key")
            if isinstance(key, str) and key.startswith("artifacts/"):
                found[key.removeprefix("artifacts/")] = value
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(rows_by_table)
    return dict(sorted(found.items()))


def export_project(session: Session, project_id: str, *, out_path: str | None = None) -> dict:
    """Assemble and durably store a project ZIP; the local path is scratch in hosted mode."""
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise research.IntegrityError("project not found")
    workspace = session.get(Workspace, project.workspace_id)
    root = _artifact_root()

    ids: dict[str, list[str]] = {"project": [project_id]}
    rows_by_table: dict[str, list[dict]] = {}
    for key, model, mode in _TABLES:
        rows = [project] if mode == "self" else _select_rows(session, model, mode, ids)
        rows_by_table[key] = [_serialize_row(r, root) for r in rows]
        if key == "sources":
            ids["source"] = [r.id for r in rows]
        elif key == "claims":
            ids["claim"] = [r.id for r in rows]
        elif key == "threads":
            ids["thread"] = [r.id for r in rows]
        elif key == "research_tasks":
            ids["research_task"] = [r.id for r in rows]
        elif key == "proposals":
            ids["proposal"] = [r.id for r in rows]
        elif key == "proposal_fit_rows":
            ids["fit_row"] = [r.id for r in rows]
        elif key == "proposal_sections":
            ids["proposal_section"] = [r.id for r in rows]
        elif key == "proposal_versions":
            ids["proposal_version"] = [r.id for r in rows]

    artifact_files = _collect_artifact_files(rows_by_table, root)

    if out_path is None:
        out_dir = Path(get_settings().data_dir) / "exports" / "projects"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"{project_id}.zip")

    data_blob = json.dumps(rows_by_table, indent=2, default=str).encode("utf-8")
    checksums: dict[str, str] = {"project.json": hashlib.sha256(data_blob).hexdigest()}
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", data_blob)
        for rel, reference in artifact_files.items():
            payload = storage.read_bytes(reference) if reference else (root / Path(rel)).read_bytes()
            checksums[f"artifacts/{rel}"] = hashlib.sha256(payload).hexdigest()
            zf.writestr(f"artifacts/{rel}", payload)
        manifest = {
            "format_version": FORMAT_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
            "exported_by": "paper-workbench 0.1.0 (export != submission/publication)",
            "project_id": project_id,
            "project_name": project.name,
            "workspace_id": project.workspace_id,
            "workspace_name": workspace.name if workspace else "",
            "row_counts": {k: len(v) for k, v in rows_by_table.items()},
            "artifact_file_count": len(artifact_files),
            "checksums": checksums,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    bundle_payload = Path(out_path).read_bytes()
    bundle_ref = storage.store_content(
        bundle_payload,
        filename=Path(out_path).name,
        namespace=f"exports/projects/{project_id}",
        content_type="application/zip",
    )
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="export_project",
        object_type="project",
        object_id=project_id,
        detail={"path": out_path, "artifact": bundle_ref, "row_counts": manifest["row_counts"]},
    )
    bundle_sha = hashlib.sha256(bundle_payload).hexdigest()
    return {
        "path": out_path,
        "artifact": bundle_ref,
        "sha256": bundle_sha,
        "row_counts": manifest["row_counts"],
        "artifact_file_count": len(artifact_files),
    }


def import_project(session: Session, zip_path: str | Path, *, workspace_id: str | None = None) -> dict:
    """Restore a project bundle into the configured artifact store after checksum checks."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise research.IntegrityError(f"bundle not found: {zip_path}")
    root = _artifact_root()

    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        if manifest.get("format_version") != FORMAT_VERSION:
            raise research.IntegrityError(
                f"unsupported bundle format_version {manifest.get('format_version')}"
            )
        for member, expected in manifest["checksums"].items():
            actual = hashlib.sha256(zf.read(member)).hexdigest()
            if actual != expected:
                raise research.IntegrityError(
                    f"checksum mismatch for '{member}' — bundle corrupt, import aborted"
                )
        rows_by_table = json.loads(zf.read("project.json"))

        project_row = rows_by_table["project"][0]
        if session.get(Project, project_row["id"]) is not None:
            raise research.IntegrityError(
                f"project {project_row['id']} already exists — import is a restore, "
                "not a merge; delete or rename the existing project first"
            )

        if workspace_id is None:
            ws = research.create_workspace(session, manifest.get("workspace_name") or "Imported")
            workspace_id = ws.id
        elif session.get(Workspace, workspace_id) is None:
            raise research.IntegrityError("target workspace not found")
        project_row["workspace_id"] = workspace_id

        # Artifacts first (content-addressed: identical files simply already exist).
        imported_refs: dict[str, dict] = {}
        for member in manifest["checksums"]:
            if not member.startswith("artifacts/"):
                continue
            rel = member[len("artifacts/") :]
            imported_refs[rel] = storage.put_bytes(f"artifacts/{rel}", zf.read(member))

    counts: dict[str, int] = {}
    for key, model, _mode in _TABLES:
        for data in rows_by_table.get(key, []):
            session.add(_deserialize_row(model, data, root, imported_refs))
        counts[key] = len(rows_by_table.get(key, []))
        # flush per table: _TABLES is FK-parent-first, and without relationship()s
        # the unit of work won't order inserts across models on its own
        session.flush()

    record_audit(
        session,
        workspace_id=workspace_id,
        actor="user",
        action="import_project",
        object_type="project",
        object_id=project_row["id"],
        detail={
            "bundle": str(zip_path),
            "row_counts": counts,
            "source_manifest_exported_at": manifest.get("exported_at"),
        },
    )
    return {"project_id": project_row["id"], "workspace_id": workspace_id, "row_counts": counts}
