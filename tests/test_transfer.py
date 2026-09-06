"""Project export/import bundles: round-trip fidelity, checksum verification,
no-overwrite restore semantics, artifact path portability."""

import json
import zipfile
from pathlib import Path

import pytest

from workbench.ingest.files import ingest_file
from workbench.providers.scholarly import ScholarlyWork
from workbench.services import authoring, authorship, citation_graph, dialogue, research, transfer
from workbench.vocab import ClaimSupport, ObjectKind, Relation


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    yield tmp_path / "data"
    config.get_settings.cache_clear()


def _populate(session, project, tmp_path):
    obj = research.create_object(
        session, project.id, kind=ObjectKind.RESULT, title="Speedup 1.9x",
        body={"plain": "persistent cache gives 1.9x"},
    )
    obj2 = research.create_object(
        session, project.id, kind=ObjectKind.QUESTION, title="Why 1.9x?"
    )
    research.link_objects(session, project.id, obj2.id, obj.id, Relation.RELATES_TO)
    f = tmp_path / "notes.md"
    f.write_text("# Notes\ncache result", encoding="utf-8")
    source = ingest_file(session, project.id, f)
    excerpt = research.capture_excerpt(
        session, source.id, text="cache result", locator="l.2"
    )
    claim = research.create_claim(
        session, project.id, text="Caching helps.",
        support=ClaimSupport.EXTERNAL_SOURCE, excerpt_ids=[excerpt.id],
    )
    thread = dialogue.create_thread(session, project.id, title="T", goal="g")
    dialogue.post_user_turn(session, thread.id, "hello")
    session.commit()
    return obj, source, claim, thread


def test_export_import_round_trip(session, project, tmp_path, data_dir):
    obj, source, claim, thread = _populate(session, project, tmp_path)
    manuscript = authoring.create_manuscript(session, project.id, title="Portable manuscript")
    contributor = authorship.create_contributor(
        session, project.id, display_name="Ada Lovelace"
    )
    assignment = authorship.propose_assignment(
        session,
        manuscript.id,
        contributor_id=contributor.id,
        role="software",
        rationale="implemented the analysis",
    )
    authorship.review_assignment(
        session, assignment.id, state="confirmed", note="team confirmed"
    )
    proposal = authorship.suggest_order(session, manuscript.id)
    authorship.review_order_proposal(
        session, proposal.id, decision="approved", note="team approved"
    )
    source.doi = "10.1000/portable"
    citation_edges, _created = citation_graph.record_citations(
        session,
        project.id,
        source.id,
        direction="backward",
        provider="fixture",
        works=[
            ScholarlyWork(
                title="Unresolved reference",
                authors=[],
                year=2020,
                venue="",
                doi="10.1000/reference",
                url=None,
                abstract=None,
                cited_by_count=None,
                open_access_url=None,
                license=None,
                provider="fixture",
                provider_id="ref-1",
            )
        ],
        simulated=True,
    )
    result = transfer.export_project(session, project.id)
    session.commit()
    bundle = Path(result["path"])
    assert bundle.is_file()
    assert result["row_counts"]["research_objects"] >= 2
    assert result["row_counts"]["citation_edges"] == 1
    assert result["row_counts"]["contributors"] == 1
    assert result["row_counts"]["credit_assignments"] == 1
    assert result["row_counts"]["authorship_proposals"] == 1
    assert result["artifact_file_count"] >= 2  # original + extracted.txt

    # simulate a fresh machine: wipe artifacts and DB rows, re-import
    import shutil

    from workbench import config, db

    shutil.move(str(bundle), str(tmp_path / "bundle.zip"))
    shutil.rmtree(data_dir / "artifacts")
    db_path = tmp_path / "fresh.sqlite3"
    session.close()
    import os

    os.environ["WB_DATABASE_URL"] = f"sqlite:///{db_path}"
    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    db.create_all()
    fresh = db.session_factory()()
    try:
        out = transfer.import_project(fresh, tmp_path / "bundle.zip")
        fresh.commit()
        assert out["project_id"] == project.id
        # rows restored with preserved ids
        assert fresh.get(type(obj), obj.id).title == "Speedup 1.9x"
        restored_source = fresh.get(type(source), source.id)
        meta = restored_source.provider_metadata["ingest"]
        # artifact paths rewritten to local store and files restored
        assert Path(meta["artifact_path"]).is_file()
        assert Path(meta["extracted_path"]).read_text(encoding="utf-8").startswith("# Notes")
        assert fresh.get(type(claim), claim.id).text == "Caching helps."
        from sqlalchemy import select

        from workbench.models import AuthorshipProposal, CitationEdge, Contributor, Turn

        turns = list(fresh.scalars(select(Turn).where(Turn.thread_id == thread.id)))
        assert len(turns) >= 2
        assert fresh.get(CitationEdge, citation_edges[0].id).review_state == "provider_reported"
        assert fresh.get(Contributor, contributor.id).display_name == "Ada Lovelace"
        assert fresh.get(AuthorshipProposal, proposal.id).status == "approved"
    finally:
        fresh.close()


def test_import_refuses_existing_project(session, project, tmp_path, data_dir):
    _populate(session, project, tmp_path)
    result = transfer.export_project(session, project.id)
    session.commit()
    with pytest.raises(research.IntegrityError, match="already exists"):
        transfer.import_project(session, result["path"])


def test_import_rejects_tampered_bundle(session, project, tmp_path, data_dir):
    _populate(session, project, tmp_path)
    result = transfer.export_project(session, project.id)
    session.commit()
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(result["path"]) as zin, zipfile.ZipFile(tampered, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "project.json":
                rows = json.loads(data)
                rows["claims"][0]["text"] = "Caching definitely proves P=NP."
                data = json.dumps(rows).encode()
            zout.writestr(item, data)
    with pytest.raises(research.IntegrityError, match="checksum mismatch"):
        transfer.import_project(session, tampered)


def test_export_missing_project_rejected(session):
    with pytest.raises(research.IntegrityError, match="not found"):
        transfer.export_project(session, "nope")
