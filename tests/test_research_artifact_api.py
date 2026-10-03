"""Read-only export routes use the existing local and tenant-isolated fixtures."""

import io
import json
import zipfile

from test_research_task_api import client as client
from test_tenant_auth import _register_login, _workspace_project
from test_tenant_auth import tenant_client as tenant_client

from workbench.services import export_service


def test_export_types_and_readiness_do_not_change_task(client, monkeypatch):
    monkeypatch.setattr(
        export_service, "weasyprint_status", lambda: {"available": False, "error": "test fallback"}
    )
    ws = client.post("/workspaces", json={"name": "Artifact fixture"}).json()
    project = client.post("/projects", json={"workspace_id": ws["id"], "name": "Research"}).json()
    root = f"/projects/{project['id']}"
    task = client.post(root + "/research-tasks", json={"question": "Unreviewed finite check"}).json()
    url = root + "/research-tasks/" + task["id"]
    before = client.get(url).json()
    pdf = client.get(url + "/results.pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    path = client.get(root + "/manuscript-path")
    assert path.status_code == 200, path.text
    assert isinstance(path.json()["stages"], list)
    markdown = client.get(root + "/manuscript-path/download")
    assert markdown.status_code == 200, markdown.text
    assert markdown.headers["content-type"].startswith("text/markdown")
    package = client.get(root + "/research-artifacts/download")
    assert package.status_code == 200, package.text
    assert package.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("package-manifest.json"))
        assert manifest["review_state"] == "unreviewed"
        assert manifest["external_submission_performed"] is False
    assert client.get(url).json() == before
    assert client.get(root + "/manuscript-path").json() == path.json()


def test_artifact_routes_preserve_project_and_tenant_scope(tenant_client):
    client = tenant_client
    _, first = _register_login(client, "artifact-first@example.com")
    _, second = _register_login(client, "artifact-second@example.com")
    _, project = _workspace_project(client, first, "Artifact research")
    _, other = _workspace_project(client, second, "Other artifact research")
    headers = {"Authorization": f"Bearer {first}"}
    other_headers = {"Authorization": f"Bearer {second}"}
    root = f"/projects/{project['id']}"
    task = client.post(root + "/research-tasks", headers=headers, json={"question": "Private check"}).json()
    suffixes = (
        f"/research-tasks/{task['id']}/results.pdf",
        "/manuscript-path",
        "/manuscript-path/download",
        "/research-artifacts/download",
    )
    for suffix in suffixes:
        assert client.get(root + suffix, headers=other_headers).status_code == 404
        assert client.get(root + suffix).status_code == 401
    wrong = f"/projects/{other['id']}/research-tasks/{task['id']}/results.pdf"
    assert client.get(wrong, headers=other_headers).status_code == 422
