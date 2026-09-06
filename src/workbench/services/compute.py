"""Review-gated local Python execution with reproducibility manifests.

This is deliberately not a general shell or a security sandbox. It runs only an ingested
``.py`` artifact with ``shell=False`` after hash-bound human approval and a second execution
confirmation. Network and descendant-process containment are honestly recorded as
unenforced. Successful output remains unreviewed until a human verifies and promotes it.
"""

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import get_settings
from ..models import ComputeRun, Project, ResearchObject, Source, stable_hash
from ..vocab import (
    ComputeNetworkPolicy,
    ComputeReviewState,
    ComputeState,
    ObjectKind,
    ResultStrength,
)
from . import research

NETWORK_POLICY = ComputeNetworkPolicy.REQUESTED_OFFLINE_UNENFORCED
PROMOTABLE_STRENGTHS = {
    ResultStrength.COMPUTATIONALLY_VERIFIED_WITHIN_SCOPE,
    ResultStrength.HEURISTICALLY_SUPPORTED,
    ResultStrength.CONJECTURED,
}


class ComputeError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_root() -> Path:
    return (Path(get_settings().data_dir) / "artifacts").resolve()


def _project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise ComputeError("project not found")
    return project


def _run(session: Session, run_id: str) -> ComputeRun:
    run = session.get(ComputeRun, run_id)
    if run is None or run.deleted_at is not None:
        raise ComputeError("compute run not found")
    return run


def _safe_name(value: str, fallback: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).name).strip(".-")
    return (name or fallback)[:120]


def _source_artifact(
    session: Session, project_id: str, source_id: str, *, script: bool = False
) -> tuple[Source, Path, dict]:
    source = session.get(Source, source_id)
    if source is None or source.deleted_at is not None or source.project_id != project_id:
        raise ComputeError(f"source {source_id} not found in project")
    ingest = (source.provider_metadata or {}).get("ingest") or {}
    raw_path = ingest.get("artifact_path")
    if not raw_path:
        raise ComputeError(f"source {source_id} is not an ingested file artifact")
    path = Path(raw_path)
    if path.is_symlink():
        raise ComputeError(f"source {source_id} artifact is not a regular file")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(_artifact_root())
    except (OSError, ValueError) as exc:
        raise ComputeError(f"source {source_id} artifact is missing or outside the artifact store") from exc
    if not resolved.is_file():
        raise ComputeError(f"source {source_id} artifact is not a regular file")
    if script and resolved.suffix.lower() != ".py":
        raise ComputeError("compute scripts must be ingested .py files")
    actual_hash = _sha256_file(resolved)
    recorded_hash = ingest.get("checksum_sha256")
    if not recorded_hash or actual_hash != recorded_hash:
        raise ComputeError(f"source {source_id} artifact checksum does not match ingestion provenance")
    descriptor = {
        "source_id": source.id,
        "title": source.title,
        "filename": resolved.name,
        "sha256": actual_hash,
        "size_bytes": resolved.stat().st_size,
    }
    return source, resolved, descriptor


def environment_manifest() -> dict:
    """Return a secret-free fingerprint of the interpreter and installed distributions."""
    packages: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            packages[name.lower()] = distribution.version
    package_rows = [
        {"name": name, "version": packages[name]} for name in sorted(packages)
    ]
    executable = Path(sys.executable).resolve()
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "executable_sha256": _sha256_file(executable),
        "packages": package_rows,
        "packages_sha256": stable_hash({"packages": package_rows}),
    }


def _binding(
    session: Session,
    project_id: str,
    *,
    script_source_id: str,
    input_source_ids: list[str],
    arguments: list[str],
    timeout_seconds: int,
    seed: int,
) -> tuple[dict, Path, list[tuple[Path, dict]]]:
    _source, script_path, script_descriptor = _source_artifact(
        session, project_id, script_source_id, script=True
    )
    inputs: list[tuple[Path, dict]] = []
    for index, source_id in enumerate(input_source_ids, start=1):
        _input_source, input_path, descriptor = _source_artifact(
            session, project_id, source_id
        )
        descriptor["staged_path"] = (
            f"inputs/{index:02d}-{_safe_name(descriptor['filename'], f'input-{index}')}"
        )
        inputs.append((input_path, descriptor))
    binding = {
        "schema_version": 1,
        "project_id": project_id,
        "script": script_descriptor,
        "inputs": [descriptor for _path, descriptor in inputs],
        "arguments": arguments,
        "timeout_seconds": timeout_seconds,
        "seed": seed,
        "network_policy": str(NETWORK_POLICY),
        "runner": {
            "kind": "local_python_subprocess",
            "shell": False,
            "package_installation": False,
            "filesystem_scope": "staged_work_directory_by_convention_unenforced",
            "descendant_process_containment": "unenforced",
        },
        "environment": environment_manifest(),
    }
    return binding, script_path, inputs


def create_run(
    session: Session,
    project_id: str,
    *,
    script_source_id: str,
    input_source_ids: list[str] | None = None,
    arguments: list[str] | None = None,
    timeout_seconds: int = 60,
    seed: int = 0,
) -> ComputeRun:
    project = _project(session, project_id)
    settings = get_settings()
    input_source_ids = input_source_ids or []
    arguments = arguments or []
    if script_source_id in input_source_ids:
        raise ComputeError("the script source must not also be an input source")
    if len(set(input_source_ids)) != len(input_source_ids):
        raise ComputeError("input source ids must be unique")
    if len(input_source_ids) > 50:
        raise ComputeError("at most 50 input sources may be staged")
    if not 1 <= timeout_seconds <= settings.compute_max_timeout_seconds:
        raise ComputeError(
            f"timeout_seconds must be between 1 and {settings.compute_max_timeout_seconds}"
        )
    if not -(2**31) <= seed < 2**31:
        raise ComputeError("seed must be a signed 32-bit integer")
    if len(arguments) > 32 or any(len(value) > 1000 or "\x00" in value for value in arguments):
        raise ComputeError("arguments are limited to 32 strings of at most 1000 characters")

    binding, _script_path, _inputs = _binding(
        session,
        project_id,
        script_source_id=script_source_id,
        input_source_ids=input_source_ids,
        arguments=arguments,
        timeout_seconds=timeout_seconds,
        seed=seed,
    )
    run = ComputeRun(
        project_id=project_id,
        script_source_id=script_source_id,
        state=ComputeState.PLANNED,
        review_state=ComputeReviewState.UNREVIEWED,
        network_policy=NETWORK_POLICY,
        plan_hash=stable_hash(binding),
        plan=binding,
    )
    session.add(run)
    session.flush()
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="plan_compute_run",
        object_type="compute_run",
        object_id=run.id,
        detail={"plan_hash": run.plan_hash, "network_policy": str(run.network_policy)},
    )
    return run


def _current_binding(session: Session, run: ComputeRun) -> tuple[dict, Path, list[tuple[Path, dict]]]:
    plan = run.plan or {}
    return _binding(
        session,
        run.project_id,
        script_source_id=run.script_source_id,
        input_source_ids=[item["source_id"] for item in plan.get("inputs", [])],
        arguments=list(plan.get("arguments", [])),
        timeout_seconds=int(plan.get("timeout_seconds", 0)),
        seed=int(plan.get("seed", 0)),
    )


def plan_status(session: Session, run: ComputeRun) -> dict:
    try:
        binding, _script_path, _inputs = _current_binding(session, run)
        current_hash = stable_hash(binding)
        return {
            "stale": current_hash != run.plan_hash,
            "current_plan_hash": current_hash,
            "reason": "plan inputs or Python environment changed"
            if current_hash != run.plan_hash
            else "",
        }
    except ComputeError as exc:
        return {"stale": True, "current_plan_hash": None, "reason": str(exc)}


def approve_run(
    session: Session,
    run_id: str,
    *,
    plan_hash: str,
    review_note: str,
    acknowledge_unenforced_isolation: bool,
) -> ComputeRun:
    run = _run(session, run_id)
    if run.state != ComputeState.PLANNED:
        raise ComputeError("only a planned compute run can be approved")
    if plan_hash != run.plan_hash:
        raise ComputeError("plan hash mismatch; review the current plan before approval")
    if not review_note.strip():
        raise ComputeError("approval requires a human review note")
    if not acknowledge_unenforced_isolation:
        raise ComputeError(
            "approval requires acknowledging that network and full process isolation are unenforced"
        )
    status = plan_status(session, run)
    if status["stale"]:
        raise ComputeError(f"compute plan is stale: {status['reason']}")
    run.state = ComputeState.APPROVED
    run.approval_note = review_note.strip()
    run.updated_at = datetime.now(UTC)
    project = _project(session, run.project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="approve_compute_run",
        object_type="compute_run",
        object_id=run.id,
        detail={"plan_hash": run.plan_hash, "isolation_acknowledged": True},
    )
    return run


def _minimal_environment(run: ComputeRun, work_dir: Path, output_dir: Path) -> dict[str, str]:
    allowed = ("SystemRoot", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP")
    environment = {name: os.environ[name] for name in allowed if os.environ.get(name)}
    environment.update(
        {
            "PYTHONHASHSEED": str(run.plan["seed"]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "TZ": "UTC",
            "WB_COMPUTE_SEED": str(run.plan["seed"]),
            "WB_COMPUTE_INPUT_MANIFEST": str(work_dir / "inputs-manifest.json"),
            "WB_COMPUTE_OUTPUT_DIR": str(output_dir),
            "WB_COMPUTE_NETWORK_POLICY": str(run.network_policy),
        }
    )
    return environment


def _store_bytes(payload: bytes, filename: str) -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    target_dir = _artifact_root() / digest[:2] / digest
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _safe_name(filename, "compute-artifact.bin")
    if not target.exists():
        target.write_bytes(payload)
    return {"artifact_path": str(target), "sha256": digest, "size_bytes": len(payload)}


def _capture_log(path: Path, filename: str, maximum: int) -> dict:
    size = path.stat().st_size
    with path.open("rb") as handle:
        payload = handle.read(maximum)
    stored = _store_bytes(payload, filename)
    return {**stored, "captured_bytes": len(payload), "original_bytes": size, "truncated": size > maximum}


def _capture_outputs(output_dir: Path) -> list[dict]:
    settings = get_settings()
    files: list[tuple[Path, str, int]] = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_symlink():
            raise ComputeError("symbolic links are not accepted as compute outputs")
        if path.is_file():
            relative = path.relative_to(output_dir).as_posix()
            files.append((path, relative, path.stat().st_size))
    if len(files) > settings.compute_max_output_files:
        raise ComputeError(
            f"compute output exceeds the {settings.compute_max_output_files}-file ceiling"
        )
    total = sum(size for _path, _relative, size in files)
    if total > settings.compute_max_output_bytes:
        raise ComputeError(
            f"compute output exceeds the {settings.compute_max_output_bytes}-byte ceiling"
        )
    outputs = []
    for path, relative, _size in files:
        stored = _store_bytes(path.read_bytes(), f"compute-{_safe_name(relative, 'output.bin')}")
        outputs.append(
            {
                "relative_path": relative,
                **stored,
                "evidence_state": "compute_unreviewed",
            }
        )
    return outputs


def execute_run(
    session: Session,
    run_id: str,
    *,
    plan_hash: str,
    confirm_local_execution: bool,
) -> ComputeRun:
    settings = get_settings()
    if not settings.compute_enabled:
        raise ComputeError("local compute execution is disabled by WB_COMPUTE_ENABLED")
    run = _run(session, run_id)
    if run.state != ComputeState.APPROVED:
        raise ComputeError("compute run must be approved before execution")
    if plan_hash != run.plan_hash:
        raise ComputeError("plan hash mismatch; execution refused")
    if not confirm_local_execution:
        raise ComputeError("explicit local execution confirmation is required")
    binding, script_path, inputs = _current_binding(session, run)
    if stable_hash(binding) != run.plan_hash:
        raise ComputeError("compute plan is stale; create and approve a new run")

    run_root = Path(settings.data_dir) / "compute" / "runs" / run.id
    if run_root.exists():
        raise ComputeError("compute run directory already exists; runs cannot be replayed in place")
    work_dir = run_root / "work"
    output_dir = work_dir / "outputs"
    output_dir.mkdir(parents=True)
    staged_script = work_dir / "script.py"
    shutil.copy2(script_path, staged_script)
    staged_inputs = []
    for input_path, descriptor in inputs:
        destination = work_dir / Path(descriptor["staged_path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, destination)
        staged_inputs.append({**descriptor, "path": descriptor["staged_path"]})
    input_manifest = {
        "schema_version": 1,
        "plan_hash": run.plan_hash,
        "inputs": staged_inputs,
        "output_directory": "outputs",
    }
    (work_dir / "inputs-manifest.json").write_text(
        json.dumps(input_manifest, indent=2), encoding="utf-8"
    )

    stdout_path = run_root / "stdout.log"
    stderr_path = run_root / "stderr.log"
    command = [sys.executable, "-B", "-s", str(staged_script), *run.plan["arguments"]]
    started_at = _now()
    run.state = ComputeState.RUNNING
    session.flush()
    timed_out = False
    exit_code: int | None = None
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            completed = subprocess.run(
                command,
                cwd=work_dir,
                env=_minimal_environment(run, work_dir, output_dir),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                timeout=run.plan["timeout_seconds"],
                check=False,
                shell=False,
                creationflags=creationflags,
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True

    failure_reason = ""
    try:
        outputs = _capture_outputs(output_dir)
    except ComputeError as exc:
        outputs = []
        failure_reason = str(exc)
    stdout_record = _capture_log(stdout_path, "compute-stdout.log", settings.compute_max_log_bytes)
    stderr_record = _capture_log(stderr_path, "compute-stderr.log", settings.compute_max_log_bytes)
    if timed_out:
        final_state = ComputeState.TIMED_OUT
        failure_reason = failure_reason or "execution exceeded the approved timeout"
    elif exit_code != 0 or failure_reason:
        final_state = ComputeState.FAILED
        failure_reason = failure_reason or f"process exited with code {exit_code}"
    else:
        final_state = ComputeState.SUCCEEDED

    execution = {
        "schema_version": 1,
        "started_at": started_at,
        "finished_at": _now(),
        "state": str(final_state),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "failure_reason": failure_reason,
        "command": ["<approved-python>", "-B", "-s", "script.py", *run.plan["arguments"]],
        "shell": False,
        "package_installation_performed": False,
        "network_policy": str(run.network_policy),
        "network_isolation_enforced": False,
        "filesystem_isolation_enforced": False,
        "descendant_process_containment_enforced": False,
        "environment": binding["environment"],
        "script": binding["script"],
        "inputs": binding["inputs"],
        "stdout": stdout_record,
        "stderr": stderr_record,
        "output_count": len(outputs),
    }
    execution["manifest_hash"] = stable_hash(execution)
    run.state = final_state
    run.execution = execution
    run.outputs = outputs
    run.updated_at = datetime.now(UTC)
    project = _project(session, run.project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="compute_runner",
        action="execute_compute_run",
        object_type="compute_run",
        object_id=run.id,
        detail={
            "plan_hash": run.plan_hash,
            "manifest_hash": execution["manifest_hash"],
            "state": str(final_state),
            "exit_code": exit_code,
            "output_count": len(outputs),
        },
    )
    return run


def review_run(
    session: Session, run_id: str, *, decision: str, review_note: str
) -> ComputeRun:
    run = _run(session, run_id)
    if run.state != ComputeState.SUCCEEDED:
        raise ComputeError("only a successful compute run can be reviewed")
    if run.review_state != ComputeReviewState.UNREVIEWED:
        raise ComputeError("compute run has already been reviewed")
    try:
        review_state = ComputeReviewState(decision)
    except ValueError as exc:
        raise ComputeError("decision must be verified or rejected") from exc
    if review_state == ComputeReviewState.UNREVIEWED:
        raise ComputeError("decision must be verified or rejected")
    if not review_note.strip():
        raise ComputeError("compute review requires a human note")
    run.review_state = review_state
    run.review_note = review_note.strip()
    run.updated_at = datetime.now(UTC)
    project = _project(session, run.project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="review_compute_run",
        object_type="compute_run",
        object_id=run.id,
        detail={"decision": str(review_state), "manifest_hash": run.execution["manifest_hash"]},
    )
    return run


def _verify_output_artifacts(run: ComputeRun) -> None:
    for output in run.outputs:
        path = Path(output["artifact_path"])
        if not path.is_file() or _sha256_file(path) != output["sha256"]:
            raise ComputeError(f"captured output is missing or changed: {output['relative_path']}")


def captured_file(
    session: Session,
    run_id: str,
    *,
    stream: str | None = None,
    output_index: int | None = None,
) -> tuple[Path, str]:
    """Resolve one recorded artifact after rechecking its store boundary and checksum."""
    run = _run(session, run_id)
    if (stream is None) == (output_index is None):
        raise ComputeError("choose exactly one captured log stream or output")
    if stream is not None:
        if stream not in {"stdout", "stderr"} or stream not in run.execution:
            raise ComputeError("captured log not found")
        record = run.execution[stream]
        filename = f"{stream}.log"
    else:
        if output_index is None or output_index < 0 or output_index >= len(run.outputs):
            raise ComputeError("captured output not found")
        record = run.outputs[output_index]
        filename = record["relative_path"]
    path = Path(record["artifact_path"])
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(_artifact_root())
    except (OSError, ValueError) as exc:
        raise ComputeError("captured artifact is missing or outside the artifact store") from exc
    if not resolved.is_file() or _sha256_file(resolved) != record["sha256"]:
        raise ComputeError("captured artifact is missing or changed")
    return resolved, _safe_name(filename, "compute-artifact.bin")


def promote_result(
    session: Session,
    run_id: str,
    *,
    title: str,
    summary: str,
    strength: ResultStrength | str = ResultStrength.COMPUTATIONALLY_VERIFIED_WITHIN_SCOPE,
) -> ResearchObject:
    run = _run(session, run_id)
    if run.state != ComputeState.SUCCEEDED or run.review_state != ComputeReviewState.VERIFIED:
        raise ComputeError("only a human-verified successful run can be promoted")
    if run.promoted_object_ids:
        raise ComputeError("this compute run has already been promoted")
    if not title.strip() or not summary.strip():
        raise ComputeError("promotion requires a title and human-authored summary")
    strength = ResultStrength(strength)
    if strength not in PROMOTABLE_STRENGTHS:
        raise ComputeError(
            "compute promotion strength must be computationally_verified_within_scope, "
            "heuristically_supported, or conjectured"
        )
    _verify_output_artifacts(run)
    result = research.create_object(
        session,
        run.project_id,
        kind=ObjectKind.RESULT,
        title=title.strip(),
        body={
            "plain": summary.strip(),
            "compute_run_id": run.id,
            "compute_plan_hash": run.plan_hash,
            "compute_manifest_hash": run.execution["manifest_hash"],
            "compute_review_state": str(run.review_state),
            "compute_review_note": run.review_note,
            "outputs": run.outputs,
            "network_policy": str(run.network_policy),
        },
        strength=strength,
        ai_suggested=False,
        actor="user",
    )
    run.promoted_object_ids = [result.id]
    run.updated_at = datetime.now(UTC)
    project = _project(session, run.project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user",
        action="promote_compute_result",
        object_type="compute_run",
        object_id=run.id,
        detail={
            "research_object_id": result.id,
            "strength": str(strength),
            "manifest_hash": run.execution["manifest_hash"],
        },
    )
    return result


def list_runs(session: Session, project_id: str) -> list[ComputeRun]:
    _project(session, project_id)
    return list(
        session.scalars(
            select(ComputeRun)
            .where(ComputeRun.project_id == project_id, ComputeRun.deleted_at.is_(None))
            .order_by(ComputeRun.created_at.desc())
        )
    )


def get_run(session: Session, run_id: str) -> ComputeRun:
    return _run(session, run_id)


def run_out(session: Session, run: ComputeRun) -> dict:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "script_source_id": run.script_source_id,
        "state": str(run.state),
        "review_state": str(run.review_state),
        "network_policy": str(run.network_policy),
        "plan_hash": run.plan_hash,
        "plan": run.plan,
        "plan_status": plan_status(session, run),
        "approval_note": run.approval_note,
        "execution": run.execution,
        "outputs": run.outputs,
        "review_note": run.review_note,
        "promoted_object_ids": run.promoted_object_ids,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }
