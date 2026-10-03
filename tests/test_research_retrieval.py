"""Synthetic local evidence only; no owner DB or model calls."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from test_delegated_research import run_controlled
from test_research_task_api import client as client
from test_tenant_auth import _register_login, _workspace_project
from test_tenant_auth import tenant_client as tenant_client

from workbench import config
from workbench.models import ResearchAgent, Source, stable_hash
from workbench.research_contract import Assignment, TaskBrief
from workbench.services import research_retrieval as retrieval
from workbench.services import research_tasks as tasks


@pytest.fixture(autouse=True)
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    config.get_settings.cache_clear()


def seed(session, project):
    task = tasks.create_task(session, project.id, TaskBrief(question="Finite topology"))
    tasks.attach(session, task, "topology.txt", b"Ultrametric topology with finite balls.", version="v1")
    tasks.attach(session, task, "asymmetry.txt", b"Asymmetric refinement counterexample.", version="v2")
    task.state = "failed_partial"
    agent = ResearchAgent(task_id=task.id, role="child", state="failed", assignment={},
        checkpoints=[{"report": {
            "findings": [{"id": "f1", "statement": "Finite topology needs a proof",
                          "scope": "finite balls", "category": "unresolved", "citation_ids": ["c1"]}],
            "citations": [{"id": "c1", "source_id": task.sources[0]["source_id"], "locator": "line 1"}],
            "search_log": [{"query": "finite topology", "location": "attached paper",
                            "coverage": "one paper", "outcome": "nothing conclusive"}],
            "unresolved_questions": ["Does asymmetric refinement preserve topology?"],
        }}])
    session.add(agent)
    session.commit()
    return task, agent


def test_retrieval_preserves_lineage_and_is_deterministic(session, project):
    task, agent = seed(session, project)
    result = retrieval.retrieve(session, project.id, "finite topology asymmetric refinement",
                                ["finite topology", "asymmetric refinement", "astronomy"])
    assert result == retrieval.retrieve(session, project.id, result["query"], result["topics"])
    assert {c["kind"] for c in result["cards"]} == {
        "source_passage", "prior_finding", "recorded_search", "open_question"}
    prior = next(c for c in result["cards"] if c["kind"] == "prior_finding")
    assert prior["origins"][0]["partial"] and prior["origins"][0]["simulated"]
    assert prior["origins"][0]["report_hash"] == stable_hash(agent.checkpoints[-1]["report"])
    assert prior["citations"][0]["locator"] == "line 1"
    assert not result["coverage"][-1]["matching_card_ids"]
    assert result["context_characters"] <= 18000
    assert not retrieval.retrieve(session, project.id, "astronomy")["cards"]


def test_exact_dedup_versions_corruption_deleted_and_project_scope(session, project):
    task, _ = seed(session, project)
    source = session.get(Source, task.sources[0]["source_id"])
    duplicate = Source(project_id=project.id, title="Another version", access=source.access,
        provider_metadata={**source.provider_metadata, "research_attachment": {"version": "v3"}})
    session.add(duplicate)
    session.commit()
    result = retrieval.retrieve(session, project.id, "ultrametric")
    assert result["scan"]["exact_duplicates_removed"] == 1
    assert {o["version"] for o in result["cards"][0]["origins"]} == {"v1", "v3"}
    from workbench.services import research
    other = research.create_project(session, project.workspace_id, "Empty project")
    assert not retrieval.retrieve(session, other.id, "ultrametric")["cards"]
    from workbench.models import utcnow
    duplicate.deleted_at = utcnow()
    source.provider_metadata = {"ingest": {**source.provider_metadata["ingest"],
        "extracted_artifact": {**source.provider_metadata["ingest"]["extracted_artifact"],
                               "sha256": "0" * 64}}}
    session.commit()
    result = retrieval.retrieve(session, project.id, "ultrametric")
    assert not result["cards"]
    assert result["scan"]["skipped_sources"]


def test_freeze_source_passages_and_archive_context(session, project):
    seed(session, project)
    task = tasks.create_task(session, project.id, TaskBrief(
        question="finite topology asymmetric refinement", reuse_prior_research=True))
    session.commit()
    assert len(task.sources) == 2
    assert all(s["context_mode"] == "retrieved passages only" for s in task.sources)
    frozen = json.dumps(task.contract, sort_keys=True)
    source = session.get(Source, task.sources[0]["source_id"])
    source.title = "Changed later"
    session.commit()
    assert json.dumps(task.contract, sort_keys=True) == frozen
    with zipfile.ZipFile(io.BytesIO(tasks.package(session, task, include_results_pdf=False))) as z:
        contract = json.loads(z.read("task_settings.json"))["contract"]
        assert contract["retrieval"] == task.contract["retrieval"]
    for card in task.contract["retrieval"]["cards"]:
        assert card["text_sha256"] == hashlib.sha256(card["text"].encode()).hexdigest()


def test_assignment_ownership_and_context_isolation():
    assignments = [Assignment(key=k, question=q, success_criteria=q, instructions="Bounded audit",
                              source_ids=[]) for k, q in [("a", "topology"), ("b", "asymmetry")]]
    context = {"snapshot_hash": "hash", "cards": [
        {"id": "one", "text": "topology finite balls"},
        {"id": "two", "text": "asymmetry counterexample"}]}
    lanes = retrieval.allocate(assignments, context)
    assert [c["id"] for c in lanes["a"]] == ["one"]
    assert [c["id"] for c in lanes["b"]] == ["two"]
    child = retrieval.child_contract({"retrieval": context, "question": "both"}, lanes["a"])
    assert "two" not in json.dumps(child)


def test_diversity_and_hard_context_bound(monkeypatch):
    cards = [{"id": str(i), "kind": "source_passage", "text": text,
              "origins": [{"source_id": source}]} for i, (text, source) in enumerate([
                  ("topology finite balls", "a"), ("topology finite balls another", "a"),
                  ("asymmetric refinement", "b")])]
    monkeypatch.setattr(retrieval, "collect", lambda *_: (cards, {}))
    selected = retrieval.retrieve(None, "project", "topology asymmetric", limit=2)
    assert {c["origins"][0]["source_id"] for c in selected["cards"]} == {"a", "b"}
    bounded = retrieval.retrieve(None, "project", "topology asymmetric", max_chars=1)
    assert not bounded["cards"] and bounded["selection_limited"]


def test_controlled_worker_records_exclusive_ownership(session, project):
    seed(session, project)
    task = tasks.create_task(session, project.id, TaskBrief(
        question="finite topology asymmetric refinement", reuse_prior_research=True))
    session.commit()
    task = run_controlled(session, task)
    assert task.state == "completed", task.ledger
    owned = [key for lane in task.ledger["retrieval_allocation"].values() for key in lane]
    assert len(owned) == len(set(owned)) == len(task.contract["retrieval"]["cards"])


def test_preview_api_and_task_freeze(client):
    ws = client.post("/workspaces", json={"name": "Retrieval fixture"}).json()
    project = client.post("/projects", json={"workspace_id": ws["id"], "name": "Paper"}).json()
    base = f"/projects/{project['id']}"
    task = client.post(base + "/research-tasks", json={"question": "Finite topology"}).json()
    client.post(base + "/research-tasks/" + task["id"] + "/attachments",
                files={"file": ("finite.txt", b"Finite topology and balls.")})
    preview = client.post(base + "/research-retrieval", json={"query": "finite topology"})
    assert preview.status_code == 200 and preview.json()["cards"]
    created = client.post(base + "/research-tasks", json={
        "question": "finite topology", "reuse_prior_research": True})
    assert created.status_code == 200
    assert created.json()["contract"]["retrieval"]["snapshot_hash"] == preview.json()["snapshot_hash"]
    assert client.post(base + "/research-retrieval", json={"query": " "}).status_code == 422


def test_preview_enforces_tenant_boundary(tenant_client):
    client = tenant_client
    _, token_a = _register_login(client, "retrieve-a@example.test")
    _, project = _workspace_project(client, token_a, "A")
    _, token_b = _register_login(client, "retrieve-b@example.test")
    response = client.post(f"/projects/{project['id']}/research-retrieval", json={"query": "secret"},
                           headers={"Authorization": f"Bearer {token_b}"})
    assert response.status_code in {403, 404}


def test_pdf_passages_include_late_pages_and_preserve_offsets(session, project):
    task = tasks.create_task(session, project.id, TaskBrief(question="Late PDF page"))
    text = "[page 1 | layout_text]\n" + "early text " * 12000
    text += "\n\n[page 2 | damaged_text_unresolved]\nLate topology theorem \x00" + " details" * 300
    tasks.attach(session, task, "extraction.txt", text.encode(), version="fixture")
    source = session.get(Source, task.sources[0]["source_id"])
    meta = source.provider_metadata["ingest"]
    source.provider_metadata = {"ingest": {**meta, "extractor": "pypdf-page-aware-test",
        "extraction_detail": {"format": "pdf", "truncated": False}}}
    session.commit()
    cards, scan = retrieval.collect(session, project.id)
    assert not scan["scan_limited"]
    late = [c for c in cards if c["origins"][0]["pdf_pages"] == [2]]
    assert late and late[0]["origins"][0]["start"] > 120000
    assert "control_glyphs" in late[0]["origins"][0]["quality_issues"]
    for card in cards:
        origin = card["origins"][0]
        assert card["text"] == text[origin["start"]:origin["end"]]
        assert len(origin["pdf_pages"]) == 1
        assert origin["review_required"] and origin["original_url"].endswith("/original")
    assert all("[page 2" not in c["text"] for c in cards if c["origins"][0]["pdf_pages"] == [1])


def test_source_limit_and_card_limit_are_reported(session, project, monkeypatch):
    seed(session, project)
    monkeypatch.setattr(retrieval, "SOURCE_CHARS", 10)
    _, scan = retrieval.collect(session, project.id)
    assert scan["scan_limited"]
    assert any("source_character_limit" in s["reasons"] for s in scan["truncated_sources"])
    monkeypatch.setattr(retrieval, "SOURCE_CHARS", 2000000)
    monkeypatch.setattr(retrieval, "MAX_CARDS", 1)
    _, scan = retrieval.collect(session, project.id)
    assert scan["scan_limited"]
    assert any("card_limit" in s["reasons"] for s in scan["truncated_sources"])


def test_original_pdf_endpoint_checks_scope_and_integrity(client):
    from workbench.services.export_service import _minimal_pdf

    ws = client.post("/workspaces", json={"name": "PDF viewer"}).json()
    project = client.post("/projects", json={"workspace_id": ws["id"], "name": "P"}).json()
    other = client.post("/projects", json={"workspace_id": ws["id"], "name": "Other"}).json()
    payload = _minimal_pdf("Title", ["Mathematical evidence remains unreviewed."])
    uploaded = client.post(f"/projects/{project['id']}/ingest/upload",
        files={"file": ("paper.pdf", payload)}, data={"pdf_mode": "plain"})
    assert uploaded.status_code == 200, uploaded.text
    source = uploaded.json()
    url = f"/projects/{project['id']}/sources/{source['id']}/original"
    response = client.get(url)
    assert response.status_code == 200 and response.content == payload
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert client.get(f"/projects/{other['id']}/sources/{source['id']}/original").status_code == 404
    Path(source["ingest"]["artifact_path"]).write_bytes(b"tampered PDF")
    assert client.get(url).status_code == 404


def test_original_pdf_endpoint_enforces_tenant_boundary(tenant_client):
    from workbench.services.export_service import _minimal_pdf

    client = tenant_client
    _, token_a = _register_login(client, "pdf-a@example.test")
    _, project = _workspace_project(client, token_a, "A")
    uploaded = client.post(f"/projects/{project['id']}/ingest/upload",
        files={"file": ("paper.pdf", _minimal_pdf("Title", ["Evidence"]))},
        data={"pdf_mode": "plain"}, headers={"Authorization": f"Bearer {token_a}"})
    assert uploaded.status_code == 200, uploaded.text
    _, token_b = _register_login(client, "pdf-b@example.test")
    response = client.get(f"/projects/{project['id']}/sources/{uploaded.json()['id']}/original",
        headers={"Authorization": f"Bearer {token_b}"})
    assert response.status_code in {403, 404}
