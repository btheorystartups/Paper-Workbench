"""Derive a saved report and exercise exports on a NEW synthetic database, never an owner DB."""

import argparse
import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path


def verify_zip(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("package-manifest.json"))
        assert set(manifest["files"]) == set(archive.namelist()) - {"package-manifest.json"}
        for name, item in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == item["sha256"]
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--narrow-finite-checks",
        action="store_true",
        help="Add bounded recomputation for the exact approved narrow acceptance ZIP",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Must not exist; never overwrites an export"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    os.environ.update(
        WB_LOAD_DOTENV="false",
        WB_DATABASE_URL="sqlite:///" + (output / "synthetic.sqlite3").as_posix(),
        WB_DATA_DIR=str(output / "synthetic-data"),
        WB_PROVIDER_MODE="fake",
        WB_LLM_PROVIDER="openai",
        WB_AUTH_REQUIRED="false",
        WB_DEPLOYMENT_MODE="local",
        WB_RESEARCH_EXECUTOR_ENABLED="false",
    )
    from fastapi.testclient import TestClient

    from workbench import config, db
    from workbench.services import manuscript_path, research_artifact_package, research_results

    original = args.input.read_bytes()
    data = research_results.snapshot_from_package(original)
    path = manuscript_path.build_path_from_snapshot(data)
    rendered = research_results.render_results(data)
    (output / "results.pdf").write_bytes(rendered.data)
    package = research_artifact_package.bundle([data], {data["id"]: original}, path)
    manifest = verify_zip(package)
    (output / "research-artifacts-v1.zip").write_bytes(package)
    if args.narrow_finite_checks:
        expected = "62bbb8b55aed9a583ddf2f64031c6bfe901d2d4209b2f224244a89d02e6603d0"
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError("narrow finite checks apply only to the named frozen acceptance ZIP")
        from reproduce_narrow_finite_checks import reproduce

        from workbench.services.publication_packages import checksummed_zip

        check_output = json.dumps(reproduce(), indent=2, sort_keys=True).encode()
        script = Path(__file__).with_name("reproduce_narrow_finite_checks.py").read_bytes()
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            files = {
                name: archive.read(name) for name in archive.namelist() if name != "package-manifest.json"
            }
        files["reproducibility/reproduce_narrow_finite_checks.py"] = script
        files["reproducibility/narrow-finite-checks.json"] = check_output
        files["reproducibility/README.md"] = (
            b"# Local finite recomputation\n\n"
            b"Run `python reproduce_narrow_finite_checks.py` with Python 3.13. "
            b"No dependencies or source execution. Compare stdout JSON to narrow-finite-checks.json. "
            b"Only epsilon=1 and q=2 are evaluated. "
            b"The four-state example is conditional, not source-stated. "
            b"The one-cell example has no cross-cell pairs. These checks neither prove a general theorem "
            b"nor advance human review. Original model verification records remain unchanged.\n"
        )
        previous_sha = hashlib.sha256(package).hexdigest()
        history = json.loads(files["history.json"])
        history["package_version"] = 2
        history["previous_version"] = {"package_version": 1, "zip_sha256": previous_sha}
        history["events"].append({"action": "add_local_finite_recomputation", "approval_changed": False})
        basis = hashlib.sha256(
            json.dumps(
                {
                    "previous_snapshot": manifest["snapshot_version"],
                    "script_sha256": hashlib.sha256(script).hexdigest(),
                    "output_sha256": hashlib.sha256(check_output).hexdigest(),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        history["snapshot_version"] = basis
        files["history.json"] = json.dumps(history, indent=2).encode()
        files["README_FIRST.md"] += (
            b"\nVersion 2 adds independently computed, explicitly bounded local finite checks. "
            b"Read reproducibility/README.md; scientific and human-review gaps remain.\n"
        )
        metadata = {k: v for k, v in manifest.items() if k != "files"}
        metadata.update(package_version=2, snapshot_version=basis, previous_package_sha256=previous_sha)
        package = checksummed_zip(files, metadata)
        manifest = verify_zip(package)
        (output / "research-artifacts-v2.zip").write_bytes(package)
        (output / "narrow-finite-checks.json").write_bytes(check_output)
    (output / "path-to-manuscript.json").write_text(json.dumps(path, indent=2), encoding="utf-8")
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        for name in (
            "README_FIRST.md",
            "manuscript/provisional-outline.tex",
            "manuscript/provisional-outline.pdf",
        ):
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
        retained = archive.read("tasks/task-001/PRIVATE-original-research-task.zip")
        assert retained == original
    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    from workbench.main import app

    statuses = {}
    with TestClient(app) as client:
        ws = client.post("/workspaces", json={"name": "Artifact acceptance - synthetic"}).json()
        project = client.post(
            "/projects", json={"workspace_id": ws["id"], "name": "Synthetic export demo"}
        ).json()
        root = f"/projects/{project['id']}"
        task = client.post(
            root + "/research-tasks", json={"question": "Inspect synthetic finite evidence"}
        ).json()
        url = root + "/research-tasks/" + task["id"]
        before = client.get(root + "/manuscript-path").json()
        attachment = client.post(
            url + "/attachments", files={"file": ("synthetic.md", b"Synthetic input: 1 + 1 = 2.")}
        )
        assert attachment.status_code == 200
        assert client.post(url + "/start", json={}).status_code == 202
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            task = client.get(url).json()
            if task["state"] == "completed":
                break
            time.sleep(0.1)
        assert task["state"] == "completed", task["state"]
        for suffix, name in (
            (url + "/results.pdf", "synthetic-results.pdf"),
            (url + "/download", "synthetic-task.zip"),
            (root + "/research-artifacts/download", "synthetic-artifacts.zip"),
            (root + "/manuscript-path/download", "synthetic-path.md"),
        ):
            response = client.get(suffix)
            assert response.status_code == 200, response.text[:200]
            (output / name).write_bytes(response.content)
            statuses[name] = response.status_code
        after = client.get(root + "/manuscript-path").json()
        assert not before["publication_ready"] and not after["publication_ready"]
        assert before["counts"]["child_reports"] == 0 < after["counts"]["child_reports"]
        assert after["counts"]["valid_human_reviews"] == 0
        verify_zip((output / "synthetic-artifacts.zip").read_bytes())
        partial = client.post(root + "/research-tasks", json={"question": "Partial synthetic task"}).json()
        partial_url = root + "/research-tasks/" + partial["id"]
        assert client.post(partial_url + "/cancel").status_code == 200
        partial_pdf = client.get(partial_url + "/results.pdf")
        assert partial_pdf.status_code == 200
        (output / "partial-results.pdf").write_bytes(partial_pdf.content)
        partial_bundle = client.get(root + "/research-artifacts/download")
        assert partial_bundle.status_code == 200
        verify_zip(partial_bundle.content)
        (output / "synthetic-with-partial-artifacts.zip").write_bytes(partial_bundle.content)
    evidence = {
        "input_sha256": hashlib.sha256(original).hexdigest(),
        "input_unchanged": args.input.read_bytes() == original,
        "original_zip_preserved_exactly": True,
        "package_sha256": hashlib.sha256(package).hexdigest(),
        "package_file_count": len(manifest["files"]),
        "renderer": rendered.manifest(),
        "source_counts": path["counts"],
        "publication_ready": path["publication_ready"],
        "synthetic_api_downloads": statuses,
        "synthetic_progress_before": before["counts"],
        "synthetic_progress_after": after["counts"],
        "synthetic_project_id": project["id"],
        "synthetic_task_id": task["id"],
        "no_live_model_calls": True,
        "no_owner_database_access": True,
        "visual_check": "Required separately after rendering",
    }
    (output / "verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
