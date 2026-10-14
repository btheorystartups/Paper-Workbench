"""Metadata intake and frozen source semantics, using an isolated offline API."""

import hashlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from workbench import config, db

    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'intake.sqlite3'}")
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("WB_DEPLOYMENT_MODE", "local")
    monkeypatch.setenv("WB_AUTH_REQUIRED", "false")
    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    from workbench.main import app

    with TestClient(app) as local:
        yield local
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


@pytest.mark.parametrize("explicit", [False, True])
def test_ingest_metadata_is_frozen_without_upgrading_excerpt_access(client, tmp_path, explicit):
    workspace = client.post("/workspaces", json={"name": "Intake test"}).json()
    project = client.post("/projects", json={"workspace_id": workspace["id"], "name": "R4"}).json()
    root = f"/projects/{project['id']}"
    payload = b"# Selected primary passage\nOnly this paragraph is supplied.\n"
    path = tmp_path / "excerpt.md"
    path.write_bytes(payload)
    body = {"path": str(path), "title": "Selected passage", "license": "limited cited excerpt"}
    if explicit:
        body.update(access="excerpt_available", authors="A. Author", year=2022, venue="Example journal",
                    doi="10.1234/example", url="https://example.org/original", version="preprint v1")
    result = client.post(root + "/ingest", json=body)
    assert result.status_code == 200, result.text
    task = client.post(root + "/research-tasks", json={
        "question": "Stage only", "source_ids": [result.json()["id"]]})
    assert task.status_code == 200, task.text
    frozen = task.json()["sources"][0]
    assert frozen["sha256"] == hashlib.sha256(payload).hexdigest()
    assert frozen["access"] == ("excerpt_available" if explicit else "full_text_user_supplied")
    assert frozen["authors"] == ("A. Author" if explicit else "")
    assert frozen["year"] == (2022 if explicit else None)
    assert frozen["doi"] == ("10.1234/example" if explicit else None)
    assert frozen["url"] == ("https://example.org/original" if explicit else None)
    assert frozen["version"] == ("preprint v1" if explicit else "unspecified")
    assert frozen["human_verified"] is False
    assert task.json()["state"] == "draft" and task.json()["agents"] == []
    assert path.read_bytes() == payload


def test_invalid_access_rejected_before_ingestion(client, tmp_path):
    workspace = client.post("/workspaces", json={"name": "Intake test"}).json()
    project = client.post("/projects", json={"workspace_id": workspace["id"], "name": "R4"}).json()
    root = f"/projects/{project['id']}"
    path = tmp_path / "excerpt.md"
    path.write_text("Selected text", encoding="utf-8")
    response = client.post(root + "/ingest", json={"path": str(path), "access": "invented_access"})
    assert response.status_code == 422
    assert client.get(root + "/sources").json() == []
