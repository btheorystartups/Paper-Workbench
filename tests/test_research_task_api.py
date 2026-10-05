"""Browser-facing local flow and tenant boundaries; no live executor or real user data."""

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_tenant_auth import _register_login, _workspace_project
from test_tenant_auth import tenant_client as tenant_client

from workbench import config, db

PILOT = Path(__file__).parent / "fixtures" / "research-task-pilot-2026-09-30.zip"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'local.sqlite3'}")
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
    monkeypatch.setenv("WB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WB_LOAD_DOTENV", "false")
    monkeypatch.setenv("WB_AUTH_REQUIRED", "false")
    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    from workbench.main import app

    with TestClient(app) as local:
        yield local
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


def test_pilot_zip_through_real_application_endpoints(client):
    with zipfile.ZipFile(PILOT) as pilot:
        contract = pilot.read("task_contract.md").decode()
    question = (
        contract.split("## Executed research question", 1)[1].split("## Inputs and scope", 1)[0].strip()
    )
    workspace = client.post("/workspaces", json={"name": "Acceptance fixture"}).json()
    project = client.post("/projects", json={"workspace_id": workspace["id"], "name": "Paper Writer"}).json()
    root = f"/projects/{project['id']}/research-tasks"
    created = client.post(root, json={"question": question})
    assert created.status_code == 200, created.text
    task = created.json()
    url = root + "/" + task["id"]
    uploaded = client.post(
        url + "/attachments",
        files={"file": (PILOT.name, PILOT.read_bytes())},
        data={"version": "single-agent pilot 2026-09-30; format reference"},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert len(uploaded.json()["sources"]) == 11
    assert client.post(url + "/attachments", files={"file": ("../bad.md", b"text")}).status_code == 422
    assert client.post(url + "/start", json={}).status_code == 202
    assert client.post(url + "/start", json={}).status_code == 422
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        task = client.get(url).json()
        if task["state"] == "completed":
            break
        assert task["state"] in {"planning", "researching", "integrating"}, task
        time.sleep(0.05)
    assert task["state"] == "completed"
    assert len(task["agents"]) == 4
    assert task["ledger"]["parent_integration_received"]
    assert task["ledger"]["actual_tokens"] == 0
    assert task["ledger"]["live_handoff_verified"] is False
    assert client.post(url + "/attachments", files={"file": ("new.md", b"changed")}).status_code == 422
    result = client.get(url + "/download")
    assert result.status_code == 200
    assert result.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert json.loads(archive.read("task_settings.json"))["contract"]["question"] == question
        assert b"OFFLINE SIMULATION" in archive.read("README.md")
    html = client.get("/ui/")
    assert 'src="/ui/research.js"' in html.text
    assert client.get("/ui/research.js").status_code == 200
    trace = client.get(url + "/call-trace")
    assert trace.status_code == 200 and trace.json()["events"]
    assert len(trace.json()["rpc_calls"]) == 4


def test_unconfigured_live_executor_and_invalid_limits_fail_closed(client):
    ws = client.post("/workspaces", json={"name": "Local"}).json()
    project = client.post("/projects", json={"workspace_id": ws["id"], "name": "Paper Writer"}).json()
    root = f"/projects/{project['id']}/research-tasks"
    for values in [
        {"token_limit": 0},
        {"time_limit_seconds": -1},
        {"max_children": 100},
        {"question": "   "},
    ]:
        assert client.post(root, json={"question": "Audit a proof", **values}).status_code == 422
    task = client.post(root, json={"question": "Audit a proof", "executor": "process"}).json()
    assert client.post(root + "/" + task["id"] + "/start", json={}).status_code == 422
    refused = client.post(root + "/" + task["id"] + "/start", json={"acknowledge_live_execution": True})
    assert refused.status_code == 422
    assert "not configured" in refused.text
    assert client.get(root + "/" + task["id"]).json()["agents"] == []


def test_research_routes_enforce_tenant_boundaries(tenant_client):
    client = tenant_client
    _, first = _register_login(client, "research-first@example.com")
    _, second = _register_login(client, "research-second@example.com")
    _, project = _workspace_project(client, first, "Research")
    _, other = _workspace_project(client, second, "Other research")
    headers = {"Authorization": f"Bearer {first}"}
    other_headers = {"Authorization": f"Bearer {second}"}
    root = f"/projects/{project['id']}/research-tasks"
    task = client.post(root, headers=headers, json={"question": "Private research"}).json()
    url = root + "/" + task["id"]
    for suffix in ("", "/download", "/call-trace"):
        assert client.get(url + suffix, headers=other_headers).status_code == 404
        assert client.get(url + suffix).status_code == 401
    for suffix, body in (("/start", {}), ("/cancel", None), ("/reviews", {}), ("/promote", {})):
        assert client.post(url + suffix, json=body, headers=other_headers).status_code == 404
    wrong = f"/projects/{other['id']}/research-tasks/{task['id']}"
    assert client.get(wrong, headers=other_headers).status_code == 422
    assert (
        client.post(
            url + "/attachments", headers=other_headers, files={"file": ("attempt.md", b"no")}
        ).status_code
        == 404
    )


def test_manuscript_length_contract_round_trips_and_rejects_reversed_bounds(client):
    ws = client.post("/workspaces", json={"name": "Length fixture"}).json()
    project = client.post("/projects", json={"workspace_id": ws["id"], "name": "Length fixture"}).json()
    root = f"/projects/{project['id']}/research-tasks"
    request = {"question": "Bounded manuscript", "task_type": "manuscript",
               "manuscript_length": {"min_words": 900, "max_words": 1200}}
    created = client.post(root, json=request)
    assert created.status_code == 200, created.text
    assert created.json()["contract"]["manuscript_length"] == {
        "min_words": 900, "max_words": 1200, "counting_policy": "section-text-whitespace-v1"}
    request["manuscript_length"] = {"min_words": 1200, "max_words": 900}
    assert client.post(root, json=request).status_code == 422
