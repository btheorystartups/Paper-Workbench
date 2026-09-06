"""Duplicate-source discovery is deterministic; merging is explicit and provenance-safe."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from workbench.models import AuditEvent, Embedding, Excerpt, LiteratureEntry
from workbench.services import audits, dialogue, literature, research, source_dedup
from workbench.vocab import SourceAccess


def _source(session, project, *, title, doi=None, year=None, access=SourceAccess.METADATA_ONLY):
    return research.register_source(
        session,
        project.id,
        title=title,
        doi=doi,
        year=year,
        access=access,
        acquisition="user supplied" if access == SourceAccess.FULL_TEXT_USER_SUPPLIED else "",
    )


def test_detects_controlled_duplicate_signals(session, project):
    first = _source(session, project, title="A Study: Results", doi="10.1000/ABC", year=2025)
    second = _source(
        session,
        project,
        title="A study — results",
        doi="https://doi.org/10.1000/abc",
        year=2025,
    )
    _source(session, project, title="Unrelated", year=2025)

    candidates = source_dedup.find_duplicate_candidates(session, project.id)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert {candidate["source_a"]["id"], candidate["source_b"]["id"]} == {first.id, second.id}
    assert candidate["signals"] == [
        "same_doi",
        "same_normalized_title",
        "same_title_year",
    ]
    assert candidate["merge_allowed"] is True
    assert candidate["review_required"] is True
    assert len(candidate["plan_hash"]) == 64


def test_conflicting_identifiers_block_merge(session, project):
    _source(session, project, title="Shared Title", doi="10.1/one", year=2024)
    _source(session, project, title="Shared title", doi="10.1/two", year=2024)
    candidate = source_dedup.find_duplicate_candidates(session, project.id)[0]
    assert candidate["merge_allowed"] is False
    assert candidate["blockers"] == ["conflicting_doi"]


def test_merge_moves_evidence_entries_pins_and_invalidates_embeddings(session, project):
    retained = _source(session, project, title="Canonical", doi="10.1000/x", year=2024)
    duplicate = _source(
        session,
        project,
        title="Canonical",
        doi="10.1000/X",
        year=2024,
        access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
    )
    excerpt = research.capture_excerpt(session, duplicate.id, text="Evidence", locator="p. 4")
    claim = research.create_claim(
        session,
        project.id,
        text="Supported claim",
        support="external_source",
        excerpt_ids=[excerpt.id],
    )
    literature.set_screening(
        session,
        project.id,
        duplicate.id,
        state="include",
        relationship="supports",
        reason="relevant",
    )
    thread = dialogue.create_thread(
        session,
        project.id,
        title="Pinned",
        pinned_source_ids=[duplicate.id, retained.id],
    )
    session.add(
        Embedding(
            project_id=project.id,
            target_type="source",
            target_id=retained.id,
            model="fake",
            index_version=1,
            vector=[1.0],
            text_hash="a" * 64,
        )
    )
    session.flush()
    candidate = source_dedup.find_duplicate_candidates(session, project.id)[0]

    result = source_dedup.merge_duplicate_sources(
        session,
        project.id,
        retained_source_id=retained.id,
        duplicate_source_id=duplicate.id,
        plan_hash=candidate["plan_hash"],
        review_note="Same DOI checked by the researcher.",
    )

    assert result["moved_excerpts"] == 1
    assert session.get(Excerpt, excerpt.id).source_id == retained.id
    assert research.claim_evidence(session, claim.id)[0].excerpt_id == excerpt.id
    entry = session.scalar(select(LiteratureEntry).where(LiteratureEntry.project_id == project.id))
    assert entry.source_id == retained.id and entry.state == "include"
    assert thread.pinned_source_ids == [retained.id]
    assert session.scalar(select(Embedding).where(Embedding.project_id == project.id)) is None
    assert duplicate.deleted_at is not None
    assert retained.access == SourceAccess.FULL_TEXT_USER_SUPPLIED
    assert retained.provider_metadata["duplicate_merges"][0]["merged_source"]["id"] == duplicate.id
    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "merge_duplicate")
    ).one()
    assert event.detail["duplicate_source_id"] == duplicate.id
    assert source_dedup.find_duplicate_candidates(session, project.id) == []


def test_merge_requires_current_plan_and_review_note(session, project):
    first = _source(session, project, title="Same", doi="10.2/x", year=2020)
    second = _source(session, project, title="Same", doi="10.2/x", year=2020)
    candidate = source_dedup.find_duplicate_candidates(session, project.id)[0]
    with pytest.raises(research.IntegrityError, match="review note"):
        source_dedup.merge_duplicate_sources(
            session,
            project.id,
            retained_source_id=first.id,
            duplicate_source_id=second.id,
            plan_hash=candidate["plan_hash"],
            review_note="",
        )
    first.title = "Changed after review"
    with pytest.raises(research.IntegrityError, match="plan changed"):
        source_dedup.merge_duplicate_sources(
            session,
            project.id,
            retained_source_id=first.id,
            duplicate_source_id=second.id,
            plan_hash=candidate["plan_hash"],
            review_note="Reviewed.",
        )


def test_literature_conflict_blocks_without_mutation(session, project):
    first = _source(session, project, title="Same", doi="10.3/x", year=2020)
    second = _source(session, project, title="Same", doi="10.3/x", year=2020)
    literature.set_screening(session, project.id, first.id, state="include")
    literature.set_screening(session, project.id, second.id, state="exclude")
    candidate = source_dedup.find_duplicate_candidates(session, project.id)[0]
    with pytest.raises(research.IntegrityError, match="literature entries conflict"):
        source_dedup.merge_duplicate_sources(
            session,
            project.id,
            retained_source_id=first.id,
            duplicate_source_id=second.id,
            plan_hash=candidate["plan_hash"],
            review_note="Identity checked.",
        )
    assert second.deleted_at is None


def test_duplicate_candidates_surface_in_audit(session, project):
    _source(session, project, title="Same", doi="10.4/x", year=2020)
    _source(session, project, title="Same", doi="10.4/x", year=2020)
    findings = audits.audit_sources(session, project.id)
    duplicates = [finding for finding in findings if finding["code"] == "source-duplicate-candidate"]
    assert len(duplicates) == 1
    assert "review required" in duplicates[0]["message"]


def test_duplicate_api_requires_review_and_merges(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'dedup-api.sqlite3'}")
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
        source_payload = {
            "title": "Same source",
            "access": "metadata_only",
            "doi": "10.5/same",
            "year": 2022,
        }
        first = client.post(
            f"/projects/{project['id']}/sources", json=source_payload
        ).json()
        second = client.post(
            f"/projects/{project['id']}/sources", json=source_payload
        ).json()
        candidates = client.get(
            f"/projects/{project['id']}/sources/duplicates"
        ).json()
        assert len(candidates) == 1
        bad = client.post(
            f"/projects/{project['id']}/sources/merge",
            json={
                "retained_source_id": first["id"],
                "duplicate_source_id": second["id"],
                "plan_hash": "0" * 64,
                "review_note": "Reviewed identity.",
            },
        )
        assert bad.status_code == 409
        merged = client.post(
            f"/projects/{project['id']}/sources/merge",
            json={
                "retained_source_id": first["id"],
                "duplicate_source_id": second["id"],
                "plan_hash": candidates[0]["plan_hash"],
                "review_note": "Reviewed DOI and title.",
            },
        )
        assert merged.status_code == 200
        assert len(client.get(f"/projects/{project['id']}/sources").json()) == 1
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
