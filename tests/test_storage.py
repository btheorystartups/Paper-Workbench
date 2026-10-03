"""Content-addressed local/private-Blob storage without live calls."""

import hashlib
import io
import json
import zipfile
from types import SimpleNamespace

import pytest


class FakeBlobClient:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key, payload, **options):
        assert options["access"] == "private"
        assert options["add_random_suffix"] is False
        assert options["overwrite"] is False
        if key in self.objects:
            raise RuntimeError("already exists")
        self.objects[key] = payload
        return SimpleNamespace(url=f"https://private.invalid/{key}", etag="fake-etag")

    def get(self, key, **options):
        assert options["access"] == "private"
        payload = self.objects.get(key)
        if payload is None:
            return None
        return SimpleNamespace(status_code=200, stream=iter([payload]))

    def head(self, key):
        return SimpleNamespace(size=len(self.objects[key]))


def _reset(monkeypatch, tmp_path, backend="local"):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WB_ARTIFACT_STORAGE_BACKEND", backend)
    from workbench import config

    config.get_settings.cache_clear()


def test_local_content_addressed_storage_is_idempotent(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    from workbench import storage

    first = storage.store_content(b"evidence", filename="paper.txt", namespace="ingest")
    second = storage.store_content(b"evidence", filename="paper.txt", namespace="ingest")
    assert first == second
    assert first["storage_backend"] == "local"
    assert first["storage_key"].startswith("artifacts/ingest/")
    assert storage.read_bytes(first) == b"evidence"
    assert storage.read_legacy_location(first["local_path"]) == b"evidence"


def test_private_blob_storage_is_private_idempotent_and_checksum_checked(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path, "vercel_blob")
    from workbench import storage

    client = FakeBlobClient()
    monkeypatch.setattr(storage, "_new_blob_client", lambda: client)
    first = storage.store_content(b"evidence", filename="paper.txt", namespace="ingest")
    second = storage.store_content(b"evidence", filename="paper.txt", namespace="ingest")
    assert first["storage_backend"] == "vercel_blob"
    assert first["private_url"].startswith("https://private.invalid/")
    assert second["sha256"] == first["sha256"]
    assert storage.read_bytes(first) == b"evidence"

    corrupted = {**first, "sha256": "0" * 64}
    with pytest.raises(storage.ArtifactStorageError, match="checksum mismatch"):
        storage.read_bytes(corrupted)


def test_private_blob_buffered_sdk_result_and_actual_read_limit(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path, "vercel_blob")
    monkeypatch.setenv("WB_ARTIFACT_MAX_READ_BYTES", "8")
    from workbench import storage

    client = FakeBlobClient()
    monkeypatch.setattr(storage, "_new_blob_client", lambda: client)
    reference = storage.store_content(b"evidence", filename="paper.txt")
    monkeypatch.setattr(
        client, "get", lambda *a, **kw: SimpleNamespace(status_code=200, content=b"evidence")
    )
    assert storage.read_bytes(reference) == b"evidence"
    # Even inaccurate metadata cannot let a larger buffered result pass the limit.
    monkeypatch.setattr(
        client, "get", lambda *a, **kw: SimpleNamespace(status_code=200, content=b"evidence!")
    )
    with pytest.raises(storage.ArtifactStorageError, match="read limit"):
        storage.read_bytes(reference)


def test_private_blob_head_refuses_oversized_read_before_get(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path, "vercel_blob")
    monkeypatch.setenv("WB_ARTIFACT_MAX_READ_BYTES", "4")
    from workbench import storage

    client = FakeBlobClient()
    monkeypatch.setattr(storage, "_new_blob_client", lambda: client)
    reference = storage.store_content(b"evidence", filename="paper.txt")
    reference["size_bytes"] = 0
    monkeypatch.setattr(client, "get", lambda *a, **kw: pytest.fail("must reject before get"))
    with pytest.raises(storage.ArtifactStorageError, match="read limit"):
        storage.read_bytes(reference)


def test_local_read_limit_checks_actual_file_size(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    monkeypatch.setenv("WB_ARTIFACT_MAX_READ_BYTES", "4")
    from workbench import storage

    reference = storage.store_content(b"evidence", filename="paper.txt")
    reference["size_bytes"] = 0
    with pytest.raises(storage.ArtifactStorageError, match="read limit"):
        storage.read_bytes(reference)


def test_ingest_round_trips_extracted_text_through_private_blob(session, tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path, "vercel_blob")
    from workbench import storage
    from workbench.ingest.files import extracted_text_for, ingest_file
    from workbench.services import research

    client = FakeBlobClient()
    monkeypatch.setattr(storage, "_new_blob_client", lambda: client)
    workspace = research.create_workspace(session, "Blob workspace")
    project = research.create_project(session, workspace.id, "Blob project")
    source_path = tmp_path / "evidence.txt"
    source_path.write_text("controlled evidence", encoding="utf-8")
    source = ingest_file(session, project.id, source_path)
    ingest = source.provider_metadata["ingest"]
    assert ingest["artifact"]["storage_backend"] == "vercel_blob"
    assert "artifact_path" not in ingest
    assert extracted_text_for(source) == "controlled evidence"


def test_bounded_browser_upload_uses_artifact_store(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'upload.sqlite3'}")
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "upload-data"))
    monkeypatch.setenv("WB_ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("WB_UPLOAD_MAX_BYTES", "32")
    monkeypatch.setenv("WB_AUTH_REQUIRED", "false")
    from fastapi.testclient import TestClient

    from workbench import config, db
    from workbench.main import app

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    with TestClient(app) as api:
        workspace = api.post("/workspaces", json={"name": "Upload workspace"}).json()
        project = api.post(
            "/projects",
            json={"workspace_id": workspace["id"], "name": "Upload project"},
        ).json()
        uploaded = api.post(
            f"/projects/{project['id']}/ingest/upload",
            files={"file": ("evidence.txt", b"controlled evidence", "text/plain")},
            data={"license": "author-owned", "pdf_mode": "auto"},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["ingest"]["artifact"]["storage_backend"] == "local"
        too_large = api.post(
            f"/projects/{project['id']}/ingest/upload",
            files={"file": ("large.txt", b"x" * 33, "text/plain")},
        )
        assert too_large.status_code == 413
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


def _reidentify_empty_project_bundle(payload: bytes, project_id: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    rows = json.loads(members["project.json"])
    assert len(rows["project"]) == 1
    rows["project"][0]["id"] = project_id
    members["project.json"] = json.dumps(rows, indent=2, default=str).encode()
    manifest = json.loads(members["manifest.json"])
    manifest["project_id"] = project_id
    manifest["checksums"]["project.json"] = hashlib.sha256(members["project.json"]).hexdigest()
    members["manifest.json"] = json.dumps(manifest, indent=2).encode()
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in members.items():
            target.writestr(name, content)
    return result.getvalue()


def test_hosted_downloads_and_uploaded_project_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'transfer-api.sqlite3'}")
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "transfer-data"))
    monkeypatch.setenv("WB_ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("WB_UPLOAD_MAX_BYTES", "2000000")
    monkeypatch.setenv("WB_AUTH_REQUIRED", "false")
    from fastapi.testclient import TestClient

    from workbench import config, db
    from workbench.main import app

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    with TestClient(app) as api:
        workspace = api.post("/workspaces", json={"name": "Transfer workspace"}).json()
        project = api.post(
            "/projects",
            json={"workspace_id": workspace["id"], "name": "Transfer project"},
        ).json()
        project_download = api.post(f"/projects/{project['id']}/export/download", json={})
        assert project_download.status_code == 200
        assert project_download.headers["content-type"] == "application/zip"
        assert "attachment" in project_download.headers["content-disposition"]

        manuscript = api.post(
            f"/projects/{project['id']}/manuscripts", json={"title": "Hosted export"}
        ).json()
        manuscript_download = api.post(
            f"/manuscripts/{manuscript['id']}/export/download", json={"formats": ["md"]}
        )
        assert manuscript_download.status_code == 200
        with zipfile.ZipFile(io.BytesIO(manuscript_download.content)) as archive:
            assert {"manuscript.md", "manifest.json"} <= set(archive.namelist())

        restored_id = "project-restored-by-upload"
        bundle = _reidentify_empty_project_bundle(project_download.content, restored_id)
        restored = api.post(
            "/projects/import/upload",
            files={"file": ("project.zip", bundle, "application/zip")},
        )
        assert restored.status_code == 200
        assert restored.json()["project_id"] == restored_id
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


@pytest.mark.parametrize("key", ["", "../secret", "/absolute", "folder/../../secret"])
def test_unsafe_storage_keys_are_rejected(tmp_path, monkeypatch, key):
    _reset(monkeypatch, tmp_path)
    from workbench import storage

    with pytest.raises(storage.ArtifactStorageError, match="safe relative path"):
        storage.put_bytes(key, b"nope")
