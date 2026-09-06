"""Offline tests for the review-gated local compute runner."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from workbench.ingest.files import ingest_file
from workbench.services import compute
from workbench.vocab import ComputeReviewState, ComputeState, ObjectKind, ResultStrength


@pytest.fixture()
def compute_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("WB_DATA_DIR", str(data_dir))
    from workbench import config

    config.get_settings.cache_clear()
    yield data_dir
    config.get_settings.cache_clear()


def _ingest_script(session, project, tmp_path, text: str):
    script = tmp_path / "analysis.py"
    script.write_text(text, encoding="utf-8")
    return ingest_file(session, project.id, script, title="Approved analysis script")


def test_plan_requires_ingested_python_and_hash_binds_environment(
    session, project, tmp_path, compute_data_dir
):
    text_file = tmp_path / "not-code.txt"
    text_file.write_text("not code", encoding="utf-8")
    source = ingest_file(session, project.id, text_file)
    with pytest.raises(compute.ComputeError, match="ingested .py"):
        compute.create_run(session, project.id, script_source_id=source.id)

    script_source = _ingest_script(session, project, tmp_path, "print('ok')\n")
    run = compute.create_run(
        session,
        project.id,
        script_source_id=script_source.id,
        arguments=["--mode", "test"],
        seed=41,
    )
    assert run.state == ComputeState.PLANNED
    assert run.plan["runner"]["shell"] is False
    assert run.plan["runner"]["package_installation"] is False
    assert run.plan["environment"]["executable_sha256"]
    assert run.plan["environment"]["packages_sha256"]
    assert len(run.plan_hash) == 64

    with pytest.raises(compute.ComputeError, match="acknowledging"):
        compute.approve_run(
            session,
            run.id,
            plan_hash=run.plan_hash,
            review_note="reviewed",
            acknowledge_unenforced_isolation=False,
        )
    script_source.title = "Changed after planning"
    assert compute.plan_status(session, run)["stale"] is True
    with pytest.raises(compute.ComputeError, match="stale"):
        compute.approve_run(
            session,
            run.id,
            plan_hash=run.plan_hash,
            review_note="reviewed",
            acknowledge_unenforced_isolation=True,
        )


def test_successful_run_is_unreviewed_until_verified_and_promoted(
    session, project, tmp_path, compute_data_dir, monkeypatch
):
    input_file = tmp_path / "values.txt"
    input_file.write_text("2,3,5", encoding="utf-8")
    input_source = ingest_file(session, project.id, input_file)
    script_source = _ingest_script(
        session,
        project,
        tmp_path,
        """import json
import os
from pathlib import Path

manifest = json.loads(Path(os.environ["WB_COMPUTE_INPUT_MANIFEST"]).read_text())
values = [int(value) for value in Path(manifest["inputs"][0]["path"]).read_text().split(",")]
output = Path(os.environ["WB_COMPUTE_OUTPUT_DIR"]) / "sum.json"
output.write_text(json.dumps({"sum": sum(values), "seed": os.environ["WB_COMPUTE_SEED"]}))
print("computed", sum(values))
print("secret-visible", bool(os.environ.get("OPENAI_API_KEY")))
""",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-enter-child-environment")
    run = compute.create_run(
        session,
        project.id,
        script_source_id=script_source.id,
        input_source_ids=[input_source.id],
        timeout_seconds=10,
        seed=7,
    )
    compute.approve_run(
        session,
        run.id,
        plan_hash=run.plan_hash,
        review_note="script and input reviewed",
        acknowledge_unenforced_isolation=True,
    )
    with pytest.raises(compute.ComputeError, match="explicit local execution"):
        compute.execute_run(
            session, run.id, plan_hash=run.plan_hash, confirm_local_execution=False
        )
    compute.execute_run(
        session, run.id, plan_hash=run.plan_hash, confirm_local_execution=True
    )

    assert run.state == ComputeState.SUCCEEDED
    assert run.review_state == ComputeReviewState.UNREVIEWED
    assert run.execution["network_isolation_enforced"] is False
    assert run.execution["package_installation_performed"] is False
    assert run.outputs[0]["evidence_state"] == "compute_unreviewed"
    output = json.loads(Path(run.outputs[0]["artifact_path"]).read_text(encoding="utf-8"))
    assert output == {"sum": 10, "seed": "7"}
    stdout = Path(run.execution["stdout"]["artifact_path"]).read_text(encoding="utf-8")
    assert "computed 10" in stdout
    assert "secret-visible False" in stdout
    assert "must-not-enter-child-environment" not in stdout

    with pytest.raises(compute.ComputeError, match="human-verified"):
        compute.promote_result(
            session, run.id, title="Sum", summary="The sum was 10."
        )
    compute.review_run(
        session,
        run.id,
        decision="verified",
        review_note="inspected the script, inputs, logs, and sum.json",
    )
    output_path = Path(run.outputs[0]["artifact_path"])
    original_output = output_path.read_bytes()
    output_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(compute.ComputeError, match="missing or changed"):
        compute.promote_result(
            session, run.id, title="Tampered", summary="This must not be promoted."
        )
    output_path.write_bytes(original_output)
    result = compute.promote_result(
        session,
        run.id,
        title="Verified sum",
        summary="The approved computation returned a sum of 10.",
    )
    assert result.kind == ObjectKind.RESULT
    assert result.strength == ResultStrength.COMPUTATIONALLY_VERIFIED_WITHIN_SCOPE
    assert result.accepted_by_user is True
    assert result.body["compute_manifest_hash"] == run.execution["manifest_hash"]
    assert run.promoted_object_ids == [result.id]
    with pytest.raises(compute.ComputeError, match="already been promoted"):
        compute.promote_result(session, run.id, title="Duplicate", summary="No.")


def test_failure_and_timeout_never_become_reviewable(
    session, project, tmp_path, compute_data_dir
):
    failing_source = _ingest_script(
        session, project, tmp_path, "raise SystemExit(3)\n"
    )
    failing = compute.create_run(session, project.id, script_source_id=failing_source.id)
    compute.approve_run(
        session,
        failing.id,
        plan_hash=failing.plan_hash,
        review_note="reviewed failing fixture",
        acknowledge_unenforced_isolation=True,
    )
    compute.execute_run(
        session, failing.id, plan_hash=failing.plan_hash, confirm_local_execution=True
    )
    assert failing.state == ComputeState.FAILED
    assert failing.execution["exit_code"] == 3
    with pytest.raises(compute.ComputeError, match="successful"):
        compute.review_run(session, failing.id, decision="verified", review_note="no")

    timeout_source = _ingest_script(
        session, project, tmp_path, "import time\ntime.sleep(5)\n"
    )
    timed = compute.create_run(
        session, project.id, script_source_id=timeout_source.id, timeout_seconds=1
    )
    compute.approve_run(
        session,
        timed.id,
        plan_hash=timed.plan_hash,
        review_note="reviewed timeout fixture",
        acknowledge_unenforced_isolation=True,
    )
    compute.execute_run(
        session, timed.id, plan_hash=timed.plan_hash, confirm_local_execution=True
    )
    assert timed.state == ComputeState.TIMED_OUT
    assert timed.execution["timed_out"] is True


def test_compute_api_preserves_both_human_gates(tmp_path, monkeypatch):
    data_dir = tmp_path / "api-data"
    monkeypatch.setenv("WB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'compute-api.sqlite3'}")
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
    script = tmp_path / "api-script.py"
    script.write_text(
        "import os\nfrom pathlib import Path\n"
        "Path(os.environ['WB_COMPUTE_OUTPUT_DIR'], 'ok.txt').write_text('ok')\n",
        encoding="utf-8",
    )
    from workbench import config, db
    from workbench.main import app

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    with TestClient(app) as client:
        workspace = client.post("/workspaces", json={"name": "WS"}).json()
        project = client.post(
            "/projects", json={"workspace_id": workspace["id"], "name": "P"}
        ).json()
        source = client.post(
            f"/projects/{project['id']}/ingest", json={"path": str(script)}
        ).json()
        run = client.post(
            f"/projects/{project['id']}/compute-runs",
            json={"script_source_id": source["id"], "timeout_seconds": 10},
        ).json()
        unapproved = client.post(
            f"/compute-runs/{run['id']}/execute",
            json={"plan_hash": run["plan_hash"], "confirm_local_execution": True},
        )
        assert unapproved.status_code == 409
        approved = client.post(
            f"/compute-runs/{run['id']}/approve",
            json={
                "plan_hash": run["plan_hash"],
                "review_note": "reviewed API fixture",
                "acknowledge_unenforced_isolation": True,
            },
        )
        assert approved.status_code == 200
        executed = client.post(
            f"/compute-runs/{run['id']}/execute",
            json={"plan_hash": run["plan_hash"], "confirm_local_execution": True},
        ).json()
        assert executed["state"] == "succeeded"
        assert executed["review_state"] == "unreviewed"
        assert client.get(f"/compute-runs/{run['id']}/logs/stdout").status_code == 200
        output_response = client.get(f"/compute-runs/{run['id']}/outputs/0")
        assert output_response.status_code == 200
        assert output_response.content == b"ok"
        reviewed = client.post(
            f"/compute-runs/{run['id']}/review",
            json={"decision": "verified", "review_note": "checked ok.txt"},
        ).json()
        assert reviewed["review_state"] == "verified"
        promoted = client.post(
            f"/compute-runs/{run['id']}/promote",
            json={"title": "API result", "summary": "The fixture wrote ok.txt."},
        ).json()
        assert promoted["kind"] == "result"
        assert promoted["strength"] == "computationally_verified_within_scope"
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
