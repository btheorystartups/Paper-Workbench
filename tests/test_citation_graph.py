"""Citation traversal is project-scoped, provenance-rich, and discovery-only."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from workbench.models import AuditEvent, CitationEdge, Claim, Excerpt, Source
from workbench.providers.scholarly import ScholarlyWork, SemanticScholarAdapter
from workbench.services import audits, citation_graph, literature, research, source_dedup
from workbench.vocab import SourceAccess


def _source(session, project, title: str, doi: str | None = None):
    return research.register_source(
        session,
        project.id,
        title=title,
        doi=doi,
        access=SourceAccess.METADATA_ONLY,
    )


def _work(
    *,
    title: str = "Related work",
    doi: str | None = "10.7777/related",
    provider: str = "semanticscholar",
    provider_id: str = "paper-related",
):
    return ScholarlyWork(
        title=title,
        authors=["R. Author"],
        year=2021,
        venue="Journal",
        doi=doi,
        url="https://example.org/work",
        abstract=None,
        cited_by_count=2,
        open_access_url=None,
        license=None,
        provider=provider,
        provider_id=provider_id,
    )


def test_fake_discovery_creates_edges_not_sources_or_evidence(session, project):
    anchor = _source(session, project, "Anchor", "10.1000/anchor")

    result = citation_graph.discover_citations(
        session, project.id, anchor.id, direction="backward"
    )

    assert result["simulated"] is True
    assert result["discovery_only"] is True
    assert result["edges_created"] == 2
    assert len(list(session.scalars(select(Source).where(Source.project_id == project.id)))) == 1
    assert list(session.scalars(select(Claim).where(Claim.project_id == project.id))) == []
    assert list(session.scalars(select(Excerpt))) == []
    edges = list(session.scalars(select(CitationEdge)))
    assert {edge.resolution_state for edge in edges} == {"cited_unresolved"}
    assert all(edge.review_state == "provider_reported" for edge in edges)
    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "discover_citations")
    ).one()
    assert event.detail["discovery_only"] is True
    codes = {finding["code"] for finding in audits.audit_sources(session, project.id)}
    assert {"citation-endpoint-unresolved", "citation-relation-unreviewed"} <= codes


def test_existing_doi_source_resolves_and_repeated_discovery_appends_observation(
    session, project
):
    anchor = _source(session, project, "Anchor", "10.1000/anchor")
    related = _source(session, project, "Reference", "10.7777/related")
    work = _work()

    first, created = citation_graph.record_citations(
        session,
        project.id,
        anchor.id,
        direction="backward",
        provider="semanticscholar",
        works=[work],
        simulated=False,
    )
    second, created_again = citation_graph.record_citations(
        session,
        project.id,
        anchor.id,
        direction="backward",
        provider="semanticscholar",
        works=[work],
        simulated=False,
    )

    assert created == 1 and created_again == 0
    assert first[0].id == second[0].id
    assert first[0].cited_source_id == related.id
    assert first[0].resolution_state == "resolved"
    assert len(first[0].observations) == 2


def test_imported_work_resolves_exact_identifier_without_verifying_edge(session, project):
    anchor = _source(session, project, "Anchor", "10.1000/anchor")
    work = _work()
    edges, _created = citation_graph.record_citations(
        session,
        project.id,
        anchor.id,
        direction="backward",
        provider="semanticscholar",
        works=[work],
        simulated=False,
    )
    assert edges[0].resolution_state == "cited_unresolved"

    imported, created = literature.import_work(session, project.id, work)

    assert created is True
    assert edges[0].cited_source_id == imported.id
    assert edges[0].resolution_state == "resolved"
    assert edges[0].review_state == "provider_reported"


def test_manual_resolution_requires_note_and_blocks_identifier_conflict(session, project):
    anchor = _source(session, project, "Anchor", "10.1000/anchor")
    wrong = _source(session, project, "Wrong", "10.9999/wrong")
    edges, _created = citation_graph.record_citations(
        session,
        project.id,
        anchor.id,
        direction="backward",
        provider="semanticscholar",
        works=[_work()],
        simulated=False,
    )
    with pytest.raises(research.IntegrityError, match="identifier conflicts"):
        citation_graph.resolve_edge(
            session,
            project.id,
            edges[0].id,
            endpoint="cited",
            source_id=wrong.id,
            review_note="Checked manually.",
        )
    with pytest.raises(research.IntegrityError, match="self-edge"):
        citation_graph.resolve_edge(
            session,
            project.id,
            edges[0].id,
            endpoint="cited",
            source_id=anchor.id,
            review_note="Incorrectly selected the anchor.",
        )

    title_only = _work(doi=None, provider="", provider_id="", title="Title-only work")
    title_edges, _created = citation_graph.record_citations(
        session,
        project.id,
        anchor.id,
        direction="backward",
        provider="manual-import",
        works=[title_only],
        simulated=False,
    )
    with pytest.raises(research.IntegrityError, match="review note"):
        citation_graph.resolve_edge(
            session,
            project.id,
            title_edges[0].id,
            endpoint="cited",
            source_id=wrong.id,
            review_note="",
        )
    citation_graph.resolve_edge(
        session,
        project.id,
        title_edges[0].id,
        endpoint="cited",
        source_id=wrong.id,
        review_note="Compared the full bibliographic record.",
    )
    assert title_edges[0].resolution_state == "resolved"
    assert title_edges[0].review_state == "provider_reported"


def test_review_state_controls_default_graph_visibility(session, project):
    anchor = _source(session, project, "Anchor", "10.1000/anchor")
    edges, _created = citation_graph.record_citations(
        session,
        project.id,
        anchor.id,
        direction="forward",
        provider="semanticscholar",
        works=[_work()],
        simulated=False,
    )
    with pytest.raises(research.IntegrityError, match="review note"):
        citation_graph.review_edge(
            session, project.id, edges[0].id, state="rejected", review_note=""
        )
    citation_graph.review_edge(
        session,
        project.id,
        edges[0].id,
        state="rejected",
        review_note="Provider joined the wrong paper.",
    )
    assert citation_graph.citation_graph(session, project.id, anchor.id)["edges"] == []
    visible = citation_graph.citation_graph(
        session, project.id, anchor.id, include_rejected=True
    )
    assert visible["edges"][0]["review_state"] == "rejected"


def test_bounded_traversal_and_project_isolation(session, project):
    anchor = _source(session, project, "Anchor", "10.1000/anchor")
    middle = _source(session, project, "Middle", "10.1000/middle")
    end = _source(session, project, "End", "10.1000/end")
    citation_graph.record_citations(
        session,
        project.id,
        anchor.id,
        direction="forward",
        provider="fixture",
        works=[_work(title=middle.title, doi=middle.doi)],
        simulated=True,
    )
    citation_graph.record_citations(
        session,
        project.id,
        middle.id,
        direction="forward",
        provider="fixture",
        works=[_work(title=end.title, doi=end.doi)],
        simulated=True,
    )
    one_hop = citation_graph.citation_graph(session, project.id, anchor.id, depth=1)
    two_hops = citation_graph.citation_graph(session, project.id, anchor.id, depth=2)
    assert len(one_hop["edges"]) == 1
    assert len(two_hops["edges"]) == 2
    capped = citation_graph.citation_graph(
        session, project.id, anchor.id, depth=2, max_nodes=2
    )
    assert capped["truncated"] is True
    assert len(capped["nodes"]) == 2 and len(capped["edges"]) == 1

    other_workspace = research.create_workspace(session, "Other")
    other_project = research.create_project(session, other_workspace.id, "Other")
    with pytest.raises(research.IntegrityError, match="root source"):
        citation_graph.citation_graph(session, other_project.id, anchor.id)


def test_duplicate_merge_repoints_citation_endpoints(session, project):
    retained = _source(session, project, "Anchor", "10.1000/anchor")
    duplicate = _source(session, project, "Anchor", "10.1000/anchor")
    edges, _created = citation_graph.record_citations(
        session,
        project.id,
        duplicate.id,
        direction="backward",
        provider="fixture",
        works=[_work()],
        simulated=True,
    )
    candidate = source_dedup.find_duplicate_candidates(session, project.id)[0]

    result = source_dedup.merge_duplicate_sources(
        session,
        project.id,
        retained_source_id=retained.id,
        duplicate_source_id=duplicate.id,
        plan_hash=candidate["plan_hash"],
        review_note="Same DOI and title checked.",
    )

    assert edges[0].citing_source_id == retained.id
    assert result["citation_edges_updated"] == 1


def test_semantic_scholar_adapter_normalizes_reference_payload():
    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "S2-1",
                            "title": "Reference",
                            "authors": [{"name": "A. Author"}],
                            "year": 2020,
                            "venue": "Venue",
                            "externalIds": {"DOI": "10.1234/REF"},
                            "url": "https://example.org/ref",
                            "citationCount": 8,
                        }
                    }
                ]
            }

    class StubClient:
        def get(self, *_args, **_kwargs):
            return StubResponse()

    adapter = SemanticScholarAdapter(session=StubClient(), rate_limit_seconds=0)
    works = adapter.citations("10.1000/anchor", direction="backward", count=5)
    assert len(works) == 1
    assert works[0].doi == "10.1234/ref"
    assert works[0].provider_id == "S2-1"


def test_citation_api_discovers_traverses_and_reviews(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'citation-api.sqlite3'}")
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
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
            f"/projects/{project['id']}/sources",
            json={"title": "Anchor", "access": "metadata_only", "doi": "10.1000/anchor"},
        ).json()
        discovery = client.post(
            f"/projects/{project['id']}/sources/{source['id']}/citations/discover",
            json={"provider": "semanticscholar", "direction": "backward", "count": 2},
        )
        assert discovery.status_code == 200
        payload = discovery.json()
        assert payload["simulated"] is True and payload["edges_created"] == 2
        graph = client.get(
            f"/projects/{project['id']}/sources/{source['id']}/citation-graph"
        ).json()
        assert graph["discovery_only"] is True and len(graph["edges"]) == 2
        reviewed = client.post(
            f"/projects/{project['id']}/citations/{graph['edges'][0]['id']}/review",
            json={"state": "human_verified", "review_note": "Checked bibliographic record."},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["review_state"] == "human_verified"
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
