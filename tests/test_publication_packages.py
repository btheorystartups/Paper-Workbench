"""Review-gated publication package lifecycle and local ZIP assembly."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from workbench.services import (
    authoring,
    authorship,
    publication_packages,
    submissions,
    venues,
)


@pytest.fixture()
def manuscript(session, project):
    manuscript = authoring.create_manuscript(session, project.id, title="Defensible paper")
    contributor = authorship.create_contributor(
        session,
        project.id,
        display_name="Ada Lovelace",
        given_names="Ada",
        family_name="Lovelace",
        corresponding=True,
    )
    assignment = authorship.propose_assignment(
        session,
        manuscript.id,
        contributor_id=contributor.id,
        role="software",
        degree="lead",
        rationale="implemented the analysis",
    )
    authorship.review_assignment(
        session, assignment.id, state="confirmed", note="team confirmed"
    )
    order = authorship.suggest_order(session, manuscript.id)
    authorship.review_order_proposal(
        session, order.id, decision="approved", note="team approved"
    )
    session.commit()
    return manuscript


@pytest.fixture()
def submission(session, project, manuscript):
    value = submissions.create_submission(
        session, project.id, manuscript_id=manuscript.id, venue_name="Journal of Tests"
    )
    session.commit()
    return value


def _complete_draft(session, package):
    publication_packages.set_cover_letter(
        session,
        package.id,
        text="Dear Editor,\n\nPlease consider this manuscript.",
        state="confirmed",
        review_note="authors reviewed the letter",
    )
    for kind in publication_packages.DECLARATION_TYPES:
        publication_packages.set_declaration(
            session,
            package.id,
            kind=kind,
            state="confirmed",
            text=f"Confirmed {kind.replace('_', ' ')} statement.",
            review_note="authors reviewed this declaration",
        )
    return package


def _approve(session, package):
    _complete_draft(session, package)
    publication_packages.prepare_for_review(session, package.id)
    publication_packages.review_package(
        session, package.id, decision="approved", note="complete package reviewed"
    )
    return package


def test_controlled_documents_and_review_notes(session, submission):
    package = publication_packages.create_package(
        session, submission.id, included_formats=["md", "jats", "md"]
    )
    assert package.included_formats == ["md", "jats"]
    assert {item["state"] for item in package.declarations} == {"missing"}

    with pytest.raises(publication_packages.PackageError, match="human review note"):
        publication_packages.set_cover_letter(
            session, package.id, text="Letter", state="confirmed"
        )
    with pytest.raises(publication_packages.PackageError, match="not_applicable"):
        publication_packages.set_declaration(
            session, package.id, kind="ethics", state="not_applicable"
        )
    with pytest.raises(publication_packages.PackageError, match="declaration kind"):
        publication_packages.set_declaration(
            session, package.id, kind="everything_is_fine", state="draft", text="x"
        )


def test_deterministic_cover_template_is_still_draft(session, submission):
    package = publication_packages.create_package(session, submission.id)
    publication_packages.draft_cover_letter(
        session,
        package.id,
        editor_name="Dr. Editor",
        significance="The work clarifies the tested result.",
        venue_fit="The topic matches the journal scope.",
    )
    assert package.cover_letter_state == "draft"
    assert "Dr. Editor" in package.cover_letter
    assert "Ada Lovelace" in package.cover_letter
    assert publication_packages.readiness(session, package.id)["ready"] is False


def test_prepare_and_approval_are_snapshot_bound(session, submission, manuscript):
    package = publication_packages.create_package(session, submission.id)
    with pytest.raises(publication_packages.PackageError, match="not review-ready"):
        publication_packages.prepare_for_review(session, package.id)
    _approve(session, package)
    assert package.state == "approved"
    assert package.basis_hash
    assert publication_packages.readiness(session, package.id)["stale"] is False

    authoring.add_section(session, manuscript.id, heading="New material", text="changed")
    status = publication_packages.readiness(session, package.id)
    assert status["stale"] is True
    with pytest.raises(publication_packages.PackageError, match="stale"):
        publication_packages.build_bundle(session, package.id)


def test_approved_bundle_is_checksummed_and_local_only(
    session, submission, tmp_path, monkeypatch
):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    submissions.add_revision(
        session,
        submission.id,
        summary="addressed reviewer comments",
        response_to_reviewers="Reviewer 1: revised as requested.",
        changes=["clarified methods"],
    )
    package = publication_packages.create_package(
        session, submission.id, included_formats=["md", "jats"]
    )
    _approve(session, package)
    result = publication_packages.build_bundle(session, package.id)
    bundle = Path(result["path"])
    assert bundle.is_file()
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == result["sha256"]
    assert result["external_submission_performed"] is False

    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert {
            "cover-letter.md",
            "declarations.md",
            "declarations.json",
            "venue-compliance.json",
            "response-to-reviewers.md",
            "package-manifest.json",
            "manuscript/manuscript.md",
            "manuscript/manuscript.jats.xml",
            "manuscript/manifest.json",
        } <= names
        manifest = json.loads(archive.read("package-manifest.json"))
        assert manifest["local_bundle_only"] is True
        assert manifest["external_submission_performed"] is False
        for name, entry in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == entry["sha256"]
        assert b"Author contributions (CRediT)" in archive.read("declarations.md")
    config.get_settings.cache_clear()


def test_new_approved_version_supersedes_old(session, submission):
    first = _approve(session, publication_packages.create_package(session, submission.id))
    second = _approve(session, publication_packages.create_package(session, submission.id))
    assert first.state == "superseded"
    assert second.state == "approved"
    assert second.version == 2
    assert first.history[-1]["to"] == "superseded"


def test_configured_missing_full_dtd_fails_closed(
    session, submission, tmp_path, monkeypatch
):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WB_JATS_DTD_PATH", str(tmp_path / "missing-jats.dtd"))
    from workbench import config

    config.get_settings.cache_clear()
    package = publication_packages.create_package(
        session, submission.id, included_formats=["jats"]
    )
    _approve(session, package)
    with pytest.raises(publication_packages.PackageError, match="JATS validation failed"):
        publication_packages.build_bundle(session, package.id)
    config.get_settings.cache_clear()


def test_verified_venue_snapshot_is_persistable(session, project, manuscript):
    venue = venues.create_venue(
        session,
        project.workspace_id,
        name="Verified Journal",
        rules={"word_limit": 5000},
        rules_source="journal instructions checked 2026-09-06",
    )
    venues.verify_venue(session, venue.id)
    submission = submissions.create_submission(
        session, project.id, manuscript_id=manuscript.id, venue_id=venue.id
    )
    package = publication_packages.create_package(session, submission.id)
    _complete_draft(session, package)
    publication_packages.prepare_for_review(session, package.id)
    session.commit()
    assert package.snapshot["venue"]["verified"] is True
    assert isinstance(package.snapshot["venue"]["retrieved_at"], str)


def test_publication_package_api_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'package-api.sqlite3'}")
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
        manuscript = client.post(
            f"/projects/{project['id']}/manuscripts", json={"title": "M"}
        ).json()
        submission = client.post(
            f"/projects/{project['id']}/submissions",
            json={"manuscript_id": manuscript["id"], "venue_name": "V"},
        ).json()
        package = client.post(
            f"/submissions/{submission['id']}/publication-packages",
            json={"included_formats": ["md"]},
        ).json()
        assert package["state"] == "draft"
        blocked = client.post(f"/publication-packages/{package['id']}/prepare", json={})
        assert blocked.status_code == 422
        listed = client.get(f"/projects/{project['id']}/publication-packages").json()
        assert [item["id"] for item in listed] == [package["id"]]
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
