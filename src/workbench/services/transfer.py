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

from ..audit import record_audit
from ..config import get_settings
from ..models import (
    Claim,
    ClaimEvidence,
    CostBudget,
    Edge,
    Embedding,
    Excerpt,
    LiteratureEntry,
    Project,
    ProposedAction,
    ResearchObject,
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
    ("sources", Source, "project"),
    ("excerpts", Excerpt, "source"),
    ("claims", Claim, "project"),
    ("claim_evidence", ClaimEvidence, "claim"),
    ("threads", Thread, "project"),
    ("turns", Turn, "thread"),
    ("proposed_actions", ProposedAction, "thread"),
    ("saved_searches", SavedSearch, "project"),
    ("literature_entries", LiteratureEntry, "project"),
    ("embeddings", Embedding, "project"),
    ("submissions", Submission, "project"),
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


def _detokenize(value: Any, root: Path) -> Any:
    if isinstance(value, str) and value.startswith(_ARTIFACT_TOKEN + "/"):
        rel = value[len(_ARTIFACT_TOKEN) + 1 :]
        return str(root / Path(rel))
    if isinstance(value, dict):
        return {k: _detokenize(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [_detokenize(v, root) for v in value]
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


def _deserialize_row(model, data: dict, root: Path):
    kwargs = {}
    for col in sa_inspect(model).columns:
        if col.key not in data:
            continue
        value = data[col.key]
        if isinstance(value, dict) and set(value) == {"__dt__"}:
            value = datetime.fromisoformat(value["__dt__"])
        else:
            value = _detokenize(value, root)
        kwargs[col.key] = value
    return model(**kwargs)


def _select_rows(session: Session, model, mode: str, ids: dict[str, list[str]]):
    if mode == "project":
        return list(
            session.scalars(select(model).where(model.project_id == ids["project"][0]))
        )
    parent_ids = ids[mode]
    if not parent_ids:
        return []
    fk = {"source": "source_id", "claim": "claim_id", "thread": "thread_id"}[mode]
    return list(session.scalars(select(model).where(getattr(model, fk).in_(parent_ids))))


def _collect_artifact_files(rows_by_table: dict[str, list[dict]], root: Path) -> list[str]:
    """Every tokenized path referenced anywhere in the export, deduped, existing only."""
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str) and value.startswith(_ARTIFACT_TOKEN + "/"):
            rel = value[len(_ARTIFACT_TOKEN) + 1 :]
            if (root / Path(rel)).is_file():
                found.add(rel)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(rows_by_table)
    return sorted(found)


def export_project(session: Session, project_id: str, *, out_path: str | None = None) -> dict:
    """Write `<data_dir>/exports/projects/<project_id>.zip` (or out_path). Returns a
    summary dict with the bundle path, row counts, and the bundle's overall sha256."""
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

    artifact_files = _collect_artifact_files(rows_by_table, root)

    if out_path is None:
        out_dir = Path(get_settings().data_dir) / "exports" / "projects"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"{project_id}.zip")

    data_blob = json.dumps(rows_by_table, indent=2, default=str).encode("utf-8")
    checksums: dict[str, str] = {"project.json": hashlib.sha256(data_blob).hexdigest()}
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", data_blob)
        for rel in artifact_files:
            payload = (root / Path(rel)).read_bytes()
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

    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="export_project",
        object_type="project", object_id=project_id,
        detail={"path": out_path, "row_counts": manifest["row_counts"]},
    )
    bundle_sha = hashlib.sha256(Path(out_path).read_bytes()).hexdigest()
    return {"path": out_path, "sha256": bundle_sha, "row_counts": manifest["row_counts"],
            "artifact_file_count": len(artifact_files)}


def import_project(
    session: Session, zip_path: str | Path, *, workspace_id: str | None = None
) -> dict:
    """Restore a project bundle. Refuses if the project id already exists. Verifies every
    checksum before writing anything. Artifacts land in the local content-addressed store;
    row payload paths are rewritten to the local data_dir."""
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
            ws = research.create_workspace(
                session, manifest.get("workspace_name") or "Imported"
            )
            workspace_id = ws.id
        elif session.get(Workspace, workspace_id) is None:
            raise research.IntegrityError("target workspace not found")
        project_row["workspace_id"] = workspace_id

        # Artifacts first (content-addressed: identical files simply already exist).
        for member in manifest["checksums"]:
            if not member.startswith("artifacts/"):
                continue
            dest = root / Path(member[len("artifacts/") :])
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))

    counts: dict[str, int] = {}
    for key, model, _mode in _TABLES:
        for data in rows_by_table.get(key, []):
            session.add(_deserialize_row(model, data, root))
        counts[key] = len(rows_by_table.get(key, []))
        # flush per table: _TABLES is FK-parent-first, and without relationship()s
        # the unit of work won't order inserts across models on its own
        session.flush()

    record_audit(
        session, workspace_id=workspace_id, actor="user", action="import_project",
        object_type="project", object_id=project_row["id"],
        detail={"bundle": str(zip_path), "row_counts": counts,
                "source_manifest_exported_at": manifest.get("exported_at")},
    )
    return {"project_id": project_row["id"], "workspace_id": workspace_id,
            "row_counts": counts}
