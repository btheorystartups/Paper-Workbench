"""End-to-end API path: workspace → project → source/excerpt → claim → thread →
turn → proposed action → approve. Runs fully offline on fakes."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'api.sqlite3'}")
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
    from workbench import config, db

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    from workbench.main import app

    with TestClient(app) as c:
        yield c
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


def test_full_vertical_path(client):
    ws = client.post("/workspaces", json={"name": "WS"}).json()
    project = client.post(
        "/projects", json={"workspace_id": ws["id"], "name": "CM"}
    ).json()

    # evidence rules surface as 422s through the API
    bad = client.post(
        f"/projects/{project['id']}/sources",
        json={"title": "PDF", "access": "full_text_user_supplied"},
    )
    assert bad.status_code == 422

    source = client.post(
        f"/projects/{project['id']}/sources",
        json={
            "title": "Bryant 1986", "access": "excerpt_available",
            "authors": "Bryant, R.", "year": 1986,
        },
    ).json()
    excerpt = client.post(
        f"/sources/{source['id']}/excerpts",
        json={"text": "Graph-based algorithms…", "locator": "p. 677"},
    ).json()
    obj = client.post(
        f"/projects/{project['id']}/objects",
        json={"kind": "result", "title": "Cache speedup 1.9x"},
    ).json()
    claim = client.post(
        f"/projects/{project['id']}/claims",
        json={
            "text": "CM caching outperforms naive re-evaluation, consistent with prior art",
            "support": "both",
            "excerpt_ids": [excerpt["id"]],
            "research_object_ids": [obj["id"]],
        },
    )
    assert claim.status_code == 200
    evidence = client.get(f"/claims/{claim.json()['id']}/evidence").json()
    assert len(evidence) == 2

    thread = client.post(
        f"/projects/{project['id']}/threads",
        json={"title": "Direction", "pinned_object_ids": [obj["id"]]},
    ).json()
    turn = client.post(
        f"/threads/{thread['id']}/turns",
        json={"content": "propose: Compare against CUDD at n=18"},
    ).json()
    assert turn["assistant"]["provenance"]["simulated"] is True
    assert len(turn["proposed_actions"]) == 1

    action = turn["proposed_actions"][0]
    approved = client.post(
        f"/actions/{action['id']}/approve", json={"plan_hash": action["plan_hash"]}
    ).json()
    assert approved["status"] == "executed"

    objects = client.get(f"/projects/{project['id']}/objects").json()
    tasks = [o for o in objects if o["kind"] == "task"]
    assert len(tasks) == 1 and tasks[0]["ai_suggested"] is True

    # wrong plan hash on a fresh proposal → 409 and invalidation
    turn2 = client.post(
        f"/threads/{thread['id']}/turns", json={"content": "propose: Another task"}
    ).json()
    action2 = turn2["proposed_actions"][0]
    conflict = client.post(f"/actions/{action2['id']}/approve", json={"plan_hash": "x"})
    assert conflict.status_code == 409
