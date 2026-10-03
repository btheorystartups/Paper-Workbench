"""Cache/tenancy/contradiction regressions. Stub vectors exercise control flow only."""

import pytest
from sqlalchemy import select
from test_research_retrieval import artifacts as artifacts
from test_research_retrieval import seed
from test_research_task_api import client as client
from test_tenant_auth import _register_login, _workspace_project
from test_tenant_auth import tenant_client as tenant_client

from workbench.models import Embedding, ResearchAgent
from workbench.providers.research_embeddings import SemanticUnavailable
from workbench.research_contract import Assignment, TaskBrief
from workbench.services import research, research_retrieval, research_semantic, research_tasks


class Stub:
    model = "test-only-semantic-vectors"
    dimensions = 3

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [[1., 0., 0.] if any(t in text.lower() for t in ("topology", "compactness"))
                else [0., 1., 0.] for text in texts]


@pytest.fixture()
def provider(monkeypatch):
    stub = Stub()
    monkeypatch.setattr(research_semantic, "get_local_provider", lambda: stub)
    return stub


def test_incremental_cache_and_semantic_only_match(session, project, provider):
    seed(session, project)
    first = research_semantic.index_project(session, project.id)
    assert first["embedded_now"] > 0 and first["remaining"] == 0
    calls = len(provider.calls)
    again = research_semantic.index_project(session, project.id)
    assert again["embedded_now"] == 0 and len(provider.calls) == calls
    assert again["reused"] == first["embedded_now"]
    assert not research_retrieval.retrieve(session, project.id, "compactness")["cards"]
    result = research_retrieval.retrieve(session, project.id, "compactness", mode="hybrid")
    assert result["cards"] and result["semantic"]["status"] == "ready"
    assert all(c["match"]["semantic"] and not c["match"]["lexical"] for c in result["cards"])
    task = research_tasks.create_task(session, project.id, TaskBrief(
        question="compactness", reuse_prior_research=True, retrieval_mode="hybrid"))
    assert task.contract["retrieval"]["semantic"]["model"] == provider.model


def test_index_batch_limit_and_deleted_cache_cleanup(session, project, provider, monkeypatch):
    task, _ = seed(session, project)
    monkeypatch.setattr(research_semantic, "MAX_INDEX_CARDS", 1)
    result = research_semantic.index_project(session, project.id)
    assert result["embedded_now"] == 1 and result["remaining"] > 0
    following = research_semantic.index_project(session, project.id)
    assert following["remaining"] == result["remaining"] - 1
    other = research.create_project(session, project.workspace_id, "Other")
    assert not research_retrieval.retrieve(session, other.id, "compactness", mode="hybrid")["cards"]
    from workbench.models import Source, utcnow
    for source in task.sources:
        session.get(Source, source["source_id"]).deleted_at = utcnow()
    task.deleted_at = utcnow()
    research_semantic.index_project(session, project.id)
    assert not list(session.scalars(select(Embedding).where(Embedding.project_id == project.id)))


def test_stale_corrupt_vectors_and_model_separation(session, project, provider):
    seed(session, project)
    research_semantic.index_project(session, project.id)
    rows = list(session.scalars(select(Embedding)))
    for row in rows:
        row.vector = [float("nan")] * 3
    session.flush()
    result = research_retrieval.retrieve(session, project.id, "compactness", mode="hybrid")
    assert not result["cards"] and result["semantic"]["status"] == "index_required"
    assert research_semantic.index_project(session, project.id)["embedded_now"] == len(rows)
    provider.model = "different-model"
    assert research_retrieval.retrieve(session, project.id, "compactness", mode="hybrid")[
        "semantic"]["status"] == "index_required"


def test_unavailable_does_not_call_paid_provider(session, project, monkeypatch):
    seed(session, project)
    def unavailable():
        raise SemanticUnavailable("test missing local model")
    monkeypatch.setattr(research_semantic, "get_local_provider", unavailable)
    result = research_retrieval.retrieve(session, project.id, "topology", mode="hybrid")
    assert result["cards"] and result["semantic"]["status"] == "unavailable"
    with pytest.raises(SemanticUnavailable):
        research_semantic.index_project(session, project.id)


def test_same_statement_different_citations_remains_distinct(session, project):
    task, agent = seed(session, project)
    report = agent.checkpoints[-1]["report"]
    other = {**report, "citations": [{"id": "c1", "source_id": "another", "locator": "different"}]}
    session.add(ResearchAgent(task_id=task.id, role="child", state="completed", assignment={}, report=other))
    session.flush()
    cards, _ = research_retrieval.collect(session, project.id)
    findings = [c for c in cards if c["kind"] == "prior_finding"]
    assert len(findings) == 2
    assert {c["citations"][0]["locator"] for c in findings} == {"line 1", "different"}


def test_overlap_groups_preserve_opposing_claims_and_have_one_owner():
    assignments = [Assignment(key=k, question="topology", instructions="audit", success_criteria="proof",
                              source_ids=[]) for k in ("a", "b")]
    cards = [{"id": "yes", "text": "Every closed subset is compact."},
             {"id": "no", "text": "Not every closed subset is compact."}]
    lanes = research_retrieval.allocate(assignments, {"cards": cards,
        "potential_overlap": [{"card_ids": ["yes", "no"], "similarity": .99}]})
    assert sorted(len(v) for v in lanes.values()) == [0, 2]
    assert sorted(c["id"] for lane in lanes.values() for c in lane) == ["no", "yes"]


def test_semantic_text_excludes_filename_and_structural_keys():
    card = {"kind": "source_passage", "text": "An actual passage", "origins": [{"title": "random.txt"}]}
    assert research_semantic.search_text(card) == "An actual passage"
    card.update(kind="prior_finding",
                text='{"statement": "claim", "scope": "finite", "category": "unresolved"}')
    assert research_semantic.search_text(card) == "claim\nfinite"


def test_invalid_batch_does_not_destroy_existing_index(session, project, provider):
    seed(session, project)
    research_semantic.index_project(session, project.id)
    before = [(r.id, r.vector) for r in session.scalars(select(Embedding))]
    provider.model = "new-version"
    provider.embed = lambda texts: []
    with pytest.raises(ValueError, match="Invalid embedding batch"):
        research_semantic.index_project(session, project.id)
    assert before == [(r.id, r.vector) for r in session.scalars(select(Embedding))]


def test_broad_candidates_are_labeled_weak(monkeypatch):
    card = {"id": "card", "kind": "source_passage", "text": "nectarine", "origins": [{"source_id": "s"}]}
    monkeypatch.setattr(research_retrieval, "collect", lambda *_: ([card.copy()], {}))
    monkeypatch.setattr(research_semantic, "score", lambda *_: (
        {"card": [.3]}, {"card": [1., 0.]}, {"status": "ready"}))
    assert not research_retrieval.retrieve(None, "p", "plum", mode="hybrid")["cards"]
    broad = research_retrieval.retrieve(None, "p", "plum", mode="hybrid", recall="broad")
    assert broad["cards"][0]["match"]["weak_semantic_lead"]


def test_index_route_is_project_scoped(tenant_client, provider):
    client = tenant_client
    _, token_a = _register_login(client, "semantic-a@example.test")
    _, project = _workspace_project(client, token_a, "A")
    _, token_b = _register_login(client, "semantic-b@example.test")
    root = f"/projects/{project['id']}/research-retrieval"
    assert client.post(root + "/index", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404
    response = client.post(root + "/index", headers={"Authorization": f"Bearer {token_a}"})
    assert response.status_code == 200 and response.json()["embedded_now"] == 0
