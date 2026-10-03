import hashlib
import io
import json
import zipfile

import pytest

from workbench.services import export_service, research_artifact_package, research_results
from workbench.services.publication_packages import PackageError, checksummed_zip


@pytest.fixture()
def minimal_renderer(monkeypatch):
    monkeypatch.setattr(
        export_service,
        "weasyprint_status",
        lambda: {"available": False, "version": None, "error": "test uses deterministic fallback"},
    )


def test_bundle_preserves_original_and_checksums_with_private_boundary(minimal_renderer):
    snapshot = {
        "id": "task-1",
        "state": "limit_reached_partial",
        "contract": {"question": "A bounded question"},
        "sources": [
            {
                "source_id": "s1",
                "title": "Pilot",
                "artifact": {"local_path": "C:/Users/private/secret.pdf", "sha256": "abcd"},
            }
        ],
        "synthesis": {"summary": "Unfinished work", "instructions": "PRIVATE PROMPT"},
        "agents": [
            {
                "id": "child",
                "role": "child",
                "state": "failed_partial",
                "assignment": {},
                "report": {},
                "checkpoints": [
                    {
                        "report": {
                            "findings": [
                                {
                                    "id": "f1",
                                    "statement": "Candidate",
                                    "scope": "Finite only",
                                    "category": "conjecture",
                                }
                            ],
                            "verification_artifacts": [
                                {
                                    "id": "v1",
                                    "outcome": "passed_within_scope",
                                    "description": "Finite test",
                                    "content": "2+2=4",
                                }
                            ],
                            "citations": [{"id": "c1", "source_id": "s1", "locator": "p. 2"}],
                        }
                    }
                ],
            }
        ],
        "reviews": {},
    }
    original = b"exact original private bytes, account@example.com"
    payload = research_artifact_package.bundle([snapshot], {"task-1": original}, {"stages": []})
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("package-manifest.json"))
        assert manifest["shareable_archive"] is False
        assert manifest["review_state"] == "unreviewed"
        assert set(manifest["files"]) == set(archive.namelist()) - {"package-manifest.json"}
        for name, details in manifest["files"].items():
            blob = archive.read(name)
            assert hashlib.sha256(blob).hexdigest() == details["sha256"]
            assert len(blob) == details["bytes"]
        task = manifest["tasks"][0]
        assert archive.read(task["original"]) == original
        assert task["state"] == "limit_reached_partial"
        assert b"DO NOT SHARE" in archive.read("README_FIRST.md")
        assert archive.read("tasks/task-001/research-results.pdf").startswith(b"%PDF")
        assert archive.read("manuscript/provisional-outline.pdf").startswith(b"%PDF")
        assert b"GAP:" in archive.read("manuscript/provisional-outline.tex")
        assert b"local_path" not in archive.read("source-manifest.json")
        assert b"PRIVATE PROMPT" not in archive.read("tasks/task-001/synthesis.json")
        assert b"Finite only" in archive.read("claim-boundaries.json")
        assert b"passed_within_scope" in archive.read("verification-and-reproducibility.json")
        assert manifest["renderers"]["manuscript/provisional-outline.pdf"]["latex_compiled"] is False


def test_bundle_snapshot_identity_changes_with_evidence(minimal_renderer):
    def identity(state):
        snapshot = {"id": "t", "state": state, "contract": {}, "agents": []}
        data = research_artifact_package.bundle([snapshot], {"t": b"original"}, {"stages": []})
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return json.loads(archive.read("package-manifest.json"))["snapshot_version"]

    assert identity("completed") != identity("failed_partial")
    with pytest.raises(ValueError, match="matching original"):
        research_artifact_package.bundle([{"id": "t"}], {}, {})


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "a\\b", "a//b"])
def test_shared_zip_rejects_unsafe_members(name):
    with pytest.raises(PackageError, match="unsafe"):
        checksummed_zip({name: b"inert"}, {})


def test_shared_zip_reproducible_and_no_self_checksum():
    first = checksummed_zip({"a.txt": b"a"}, {"format_version": 1})
    assert first == checksummed_zip({"a.txt": b"a"}, {"format_version": 1})
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        manifest = json.loads(archive.read("package-manifest.json"))
        assert list(manifest["files"]) == ["a.txt"]


def test_saved_package_export_and_current_manuscript(session, project, minimal_renderer):
    from workbench.research_contract import TaskBrief
    from workbench.services import authoring, research_tasks

    task = research_tasks.create_task(session, project.id, TaskBrief(question="Synthetic bounded task"))
    manuscript = authoring.create_manuscript(session, project.id, title="Current manuscript")
    authoring.add_section(session, manuscript.id, heading="Introduction", text="Recorded prose")
    original = research_tasks.package(session, task, include_results_pdf=False)
    snapshot = research_results.snapshot_from_package(original)
    payload = research_artifact_package.bundle([snapshot], {snapshot["id"]: original}, {"stages": []})
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.read("tasks/task-001/PRIVATE-original-research-task.zip") == original
    project_payload = research_artifact_package.project_bundle(session, project.id)
    with zipfile.ZipFile(io.BytesIO(project_payload)) as archive:
        records = json.loads(archive.read("manuscript/recorded-manuscripts.json"))
        assert records[0]["id"] == manuscript.id
        assert b"Recorded prose" in archive.read("manuscript/recorded-manuscripts.json")
        assert b"Recorded prose" in archive.read("manuscript/recorded-001.tex")
        assert archive.read("manuscript/recorded-001.pdf").startswith(b"%PDF")
