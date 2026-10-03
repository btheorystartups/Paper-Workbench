"""Versioned, manuscript-local approval dependencies. No provider calls or writes.

Dependencies are explicit: section claims, claim evidence, typed graph edges, and
the reference fields below. Unlinked project material is never publication evidence.
"""

import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import inspect, select

from .. import storage
from ..config import get_settings
from ..models import (
    Claim,
    ClaimEvidence,
    ComputeRun,
    Edge,
    Excerpt,
    ResearchAgent,
    ResearchObject,
    ResearchTask,
    Source,
    stable_hash,
)
from . import authoring, research

POLICY_VERSION = "manuscript-evidence-v1"
REFERENCE_FIELDS = {
    "claim_ids": Claim,
    "source_ids": Source,
    "excerpt_ids": Excerpt,
    "artifact_ids": ResearchObject,
    "required_check_ids": ResearchObject,
    "dependency_ids": ResearchObject,
    "included_object_ids": ResearchObject,
    "from_candidate_id": ResearchObject,
    "section_order": ResearchObject,
    "dataset_id": ResearchObject,
    "compute_run_id": ComputeRun,
    "research_task_id": ResearchTask,
}


def read_artifact(reference: dict) -> bytes:
    """Approval checks may read the configured artifact store, never arbitrary host paths."""
    settings = get_settings()
    backend = reference.get("storage_backend", settings.artifact_storage_backend)
    if backend != settings.artifact_storage_backend or not re.fullmatch(
        r"[0-9a-f]{64}", str(reference.get("sha256", ""))
    ):
        raise storage.ArtifactStorageError("artifact identity or backend denied")
    if backend == "local":
        path = storage._local_path(str(reference.get("storage_key", "")))
        declared = Path(reference.get("local_path") or path).absolute()
        if declared != path or any(p.is_symlink() or p.is_junction() for p in [declared, *declared.parents]):
            raise storage.ArtifactStorageError("artifact path denied")
    return storage.read_bytes(reference)


def record(row):
    # JSON roundtrip detaches mutable values from ORM objects and normalizes dates.
    return json.loads(
        json.dumps(
            {column.key: getattr(row, column.key) for column in inspect(row).mapper.column_attrs},
            default=str,
        )
    )


def collect(session, manuscript_id: str, *, verify_artifacts: bool = True) -> dict:
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None or manuscript.kind != "manuscript" or manuscript.deleted_at:
        raise research.IntegrityError("manuscript not found")
    session.flush()
    rows, edges, problems, artifacts = {}, {}, [], {}
    pending = [(ResearchObject, manuscript_id)]
    pending += [(ResearchObject, s.id) for s in authoring.manuscript_sections(session, manuscript_id)]
    project_objects = list(
        session.scalars(
            select(ResearchObject).where(
                ResearchObject.project_id == manuscript.project_id, ResearchObject.deleted_at.is_(None)
            )
        )
    )
    # Reviewer notes and explicitly attached artifacts/checks belong to this version scope.
    pending += [
        (ResearchObject, o.id) for o in project_objects if o.body.get("manuscript_id") == manuscript_id
    ]
    project_edges = list(
        session.scalars(
            select(Edge).where(Edge.project_id == manuscript.project_id, Edge.deleted_at.is_(None))
        )
    )

    def references(value):
        if isinstance(value, dict):
            if "storage_key" in value:
                key = stable_hash(value)
                if verify_artifacts and key not in artifacts:
                    try:
                        if not value.get("sha256"):
                            raise ValueError("unversioned artifact")
                        payload = read_artifact(value)
                        artifacts[key] = {
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "bytes": len(payload),
                        }
                    except (OSError, ValueError, storage.ArtifactStorageError):
                        artifacts[key] = {"invalid": True}
                        problems.append("missing, changed or unversioned artifact")
            for key, item in value.items():
                if key in REFERENCE_FIELDS and item:
                    values = item if isinstance(item, list) else [item]
                    pending.extend((REFERENCE_FIELDS[key], i) for i in values if isinstance(i, str))
                references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)

    while pending:
        cls, identifier = pending.pop()
        key = f"{cls.__tablename__}:{identifier}"
        if key in rows:
            continue
        row = session.get(cls, identifier)
        if (
            row is None
            or row.deleted_at
            or getattr(row, "project_id", manuscript.project_id) != manuscript.project_id
        ):
            rows[key] = {"id": identifier, "unavailable": True}
            problems.append(f"unavailable dependency {key}")
            continue
        if cls is ResearchObject and row.kind == "manuscript" and row.id != manuscript_id:
            rows[key] = {"id": identifier, "unavailable": True}
            problems.append("cross-manuscript dependency requires an explicit result")
            continue
        rows[key] = record(row)
        if cls is Source:
            ingest = row.provider_metadata.get("ingest", {})
            for path_key, reference_key in [
                ("artifact_path", "artifact"),
                ("extracted_path", "extracted_artifact"),
            ]:
                if ingest.get(path_key) and not ingest.get(reference_key):
                    problems.append("legacy source bytes require content-addressed reingestion")
        if cls is ResearchObject:
            for path_key, reference_key in [("png_path", "png_artifact"), ("svg_path", "svg_artifact")]:
                if row.body.get(path_key) and not row.body.get(reference_key):
                    problems.append("legacy figure bytes require content-addressed reingestion")
        references(rows[key])
        if cls is Claim:
            pending.extend(
                (ClaimEvidence, ev.id)
                for ev in session.scalars(
                    select(ClaimEvidence).where(
                        ClaimEvidence.claim_id == row.id, ClaimEvidence.deleted_at.is_(None)
                    )
                )
            )
        elif cls is ClaimEvidence:
            pending.extend(
                (c, i) for c, i in [(Excerpt, row.excerpt_id), (ResearchObject, row.research_object_id)] if i
            )
        elif cls is Excerpt:
            pending.append((Source, row.source_id))
        elif cls is ResearchTask:
            pending.extend(
                (ResearchAgent, a.id)
                for a in session.scalars(
                    select(ResearchAgent).where(
                        ResearchAgent.task_id == row.id, ResearchAgent.deleted_at.is_(None)
                    )
                )
            )
        elif cls is ComputeRun:
            pending.append((Source, row.script_source_id))
        elif cls is ResearchObject:
            for edge in project_edges:
                target = None
                if edge.src_id == row.id and edge.relation in {"depends_on", "derives_from", "cites"}:
                    target = edge.dst_id
                if edge.dst_id == row.id and edge.relation in {"supports", "contradicts", "part_of"}:
                    target = edge.src_id
                if target:
                    edges[edge.id] = record(edge)
                    pending.append((ResearchObject, target))
    return {
        "policy_version": POLICY_VERSION,
        "records": {k: rows[k] for k in sorted(rows)},
        "edges": [edges[k] for k in sorted(edges)],
        "artifacts": {k: artifacts[k] for k in sorted(artifacts)},
        "problems": sorted(set(problems)),
    }


def ids(basis: dict, cls) -> set[str]:
    prefix = cls.__tablename__ + ":"
    return {value["id"] for key, value in basis["records"].items() if key.startswith(prefix)}
