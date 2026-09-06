"""Review-gated CRediT roles and authorship-order assistance."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from workbench.services import audits, authoring, authorship, export_service, research


@pytest.fixture()
def manuscript(session, project):
    manuscript = authoring.create_manuscript(session, project.id, title="Controlled authorship")
    session.commit()
    return manuscript


def _person(session, project, name, **kwargs):
    return authorship.create_contributor(
        session, project.id, display_name=name, **kwargs
    )


def _confirmed(session, manuscript, contributor, role, degree="equal"):
    assignment = authorship.propose_assignment(
        session,
        manuscript.id,
        contributor_id=contributor.id,
        role=role,
        degree=degree,
        rationale=f"documented {role} work",
    )
    authorship.review_assignment(
        session, assignment.id, state="confirmed", note="confirmed by project team"
    )
    return assignment


def test_contributor_identity_and_orcid_validation(session, project):
    contributor = _person(
        session,
        project,
        "Josiah Carberry",
        given_names="Josiah",
        family_name="Carberry",
        orcid="https://orcid.org/0000-0002-1825-0097",
        affiliation="Brown University",
        corresponding=True,
    )
    session.commit()
    assert contributor.orcid == "0000-0002-1825-0097"
    assert authorship.list_contributors(session, project.id) == [contributor]

    with pytest.raises(research.IntegrityError, match="checksum"):
        _person(session, project, "Invalid", orcid="0000-0002-1825-0098")


def test_assignments_start_proposed_and_require_human_review(session, project, manuscript):
    contributor = _person(session, project, "A. Researcher")
    assignment = authorship.propose_assignment(
        session,
        manuscript.id,
        contributor_id=contributor.id,
        role="software",
        degree="lead",
        rationale="implemented and tested the software",
        origin="assistant",
    )
    assert assignment.state == "proposed"
    assert assignment.origin == "assistant"

    with pytest.raises(research.IntegrityError, match="review note"):
        authorship.review_assignment(session, assignment.id, state="confirmed", note="")
    authorship.review_assignment(
        session, assignment.id, state="confirmed", note="reviewed against commit history"
    )
    assert assignment.state == "confirmed"
    assert [item["to"] for item in assignment.history] == ["proposed", "confirmed"]

    with pytest.raises(research.IntegrityError, match="already has"):
        authorship.propose_assignment(
            session,
            manuscript.id,
            contributor_id=contributor.id,
            role="software",
            rationale="duplicate",
        )


def test_controlled_vocabularies_and_project_scope(session, project, manuscript):
    contributor = _person(session, project, "A")
    with pytest.raises(research.IntegrityError, match="role must be"):
        authorship.propose_assignment(
            session,
            manuscript.id,
            contributor_id=contributor.id,
            role="did_everything",
            rationale="not controlled",
        )
    with pytest.raises(research.IntegrityError, match="degree must be"):
        authorship.propose_assignment(
            session,
            manuscript.id,
            contributor_id=contributor.id,
            role="methodology",
            degree="major",
            rationale="not controlled",
        )

    ws = research.create_workspace(session, "Other")
    other_project = research.create_project(session, ws.id, "Other")
    outsider = _person(session, other_project, "Outsider")
    with pytest.raises(research.IntegrityError, match="not found in project"):
        authorship.propose_assignment(
            session,
            manuscript.id,
            contributor_id=outsider.id,
            role="methodology",
            rationale="wrong project",
        )


def test_suggestion_uses_confirmed_roles_and_blocks_disputes(session, project, manuscript):
    alice = _person(session, project, "Alice")
    bob = _person(session, project, "Bob")
    _confirmed(session, manuscript, alice, "conceptualization", "lead")
    _confirmed(session, manuscript, bob, "software", "equal")
    _confirmed(session, manuscript, bob, "validation", "equal")
    proposal = authorship.suggest_order(session, manuscript.id)
    assert proposal.ordered_contributor_ids == [alice.id, bob.id]
    assert proposal.status == "proposed"
    assert proposal.method == "confirmed_credit_heuristic_v1"

    disputed = authorship.propose_assignment(
        session,
        manuscript.id,
        contributor_id=alice.id,
        role="funding_acquisition",
        rationale="team disagrees",
    )
    authorship.review_assignment(session, disputed.id, state="disputed", note="disputed by team")
    with pytest.raises(research.IntegrityError, match="resolve disputed"):
        authorship.suggest_order(session, manuscript.id)


def test_human_approval_is_required_and_snapshot_bound(session, project, manuscript):
    alice = _person(session, project, "Alice")
    bob = _person(session, project, "Bob")
    _confirmed(session, manuscript, alice, "conceptualization", "lead")
    _confirmed(session, manuscript, bob, "software", "equal")
    proposal = authorship.suggest_order(session, manuscript.id)

    assert authorship.export_credit(session, manuscript.id)["status"] == "not_approved"
    with pytest.raises(research.IntegrityError, match="review note"):
        authorship.review_order_proposal(session, proposal.id, decision="approved", note="")
    authorship.review_order_proposal(
        session, proposal.id, decision="approved", note="all contributors agreed"
    )
    exported = authorship.export_credit(session, manuscript.id)
    assert exported["status"] == "human_approved"
    assert [item["display_name"] for item in exported["authors"]] == ["Alice", "Bob"]

    # Any later contribution-state change invalidates the frozen basis rather than silently
    # retaining an outdated authorship statement.
    extra = authorship.propose_assignment(
        session,
        manuscript.id,
        contributor_id=bob.id,
        role="visualization",
        rationale="created plots",
    )
    authorship.review_assignment(session, extra.id, state="confirmed", note="plots reviewed")
    assert authorship.export_credit(session, manuscript.id)["status"] == "not_approved"
    codes = {item["code"] for item in audits.audit_manuscript(session, manuscript.id)}
    assert "authorship-order-stale" in codes


def test_stale_proposal_cannot_be_approved(session, project, manuscript):
    contributor = _person(session, project, "A")
    assignment = _confirmed(session, manuscript, contributor, "methodology")
    proposal = authorship.suggest_order(session, manuscript.id)
    authorship.review_assignment(
        session, assignment.id, state="disputed", note="new disagreement"
    )
    with pytest.raises(research.IntegrityError, match="stale"):
        authorship.review_order_proposal(
            session, proposal.id, decision="approved", note="attempted approval"
        )


def test_manual_order_still_requires_confirmed_roles(session, project, manuscript):
    contributor = _person(session, project, "A")
    proposal = authorship.create_order_proposal(
        session,
        manuscript.id,
        ordered_contributor_ids=[contributor.id],
        rationale="team-selected order",
    )
    with pytest.raises(research.IntegrityError, match="confirmed CRediT role"):
        authorship.review_order_proposal(
            session, proposal.id, decision="approved", note="team agreed"
        )


def test_export_renders_only_approved_authorship(
    session, project, manuscript, tmp_path, monkeypatch
):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    contributor = _person(
        session, project, "Ada Lovelace", given_names="Ada", family_name="Lovelace"
    )
    _confirmed(session, manuscript, contributor, "software", "lead")
    proposal = authorship.suggest_order(session, manuscript.id)

    first = export_service.export_manuscript(session, manuscript.id, formats=["md", "jats"])
    first_manifest = json.loads(Path(first["files"]["manifest"]).read_text(encoding="utf-8"))
    assert first_manifest["authorship"]["status"] == "not_approved"
    assert "Ada Lovelace" not in Path(first["files"]["md"]).read_text(encoding="utf-8")

    authorship.review_order_proposal(
        session, proposal.id, decision="approved", note="team reviewed and approved"
    )
    second = export_service.export_manuscript(
        session, manuscript.id, formats=["md", "tex", "html", "docx", "pdf", "jats"]
    )
    md = Path(second["files"]["md"]).read_text(encoding="utf-8")
    tex = Path(second["files"]["tex"]).read_text(encoding="utf-8")
    html = Path(second["files"]["html"]).read_text(encoding="utf-8")
    jats = Path(second["files"]["jats"]).read_text(encoding="utf-8")
    manifest = json.loads(Path(second["files"]["manifest"]).read_text(encoding="utf-8"))
    assert "Ada Lovelace" in md
    assert "Ada Lovelace" in tex
    assert "Ada Lovelace" in html
    assert "Author contributions (CRediT)" in md
    assert '<role vocab="CRediT"' in jats
    assert Path(second["files"]["docx"]).stat().st_size > 0
    assert Path(second["files"]["pdf"]).read_bytes().startswith(b"%PDF")
    assert manifest["authorship"]["status"] == "human_approved"
    assert second["jats_validation"]["valid"] is True
    config.get_settings.cache_clear()


def test_credit_api_review_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'credit-api.sqlite3'}")
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
        contributor = client.post(
            f"/projects/{project['id']}/contributors",
            json={"display_name": "Ada Lovelace"},
        ).json()
        assignment_response = client.post(
            f"/manuscripts/{manuscript['id']}/credit-assignments",
            json={
                "contributor_id": contributor["id"],
                "role": "software",
                "degree": "lead",
                "rationale": "implemented the software",
            },
        )
        assert assignment_response.status_code == 200
        assignment = assignment_response.json()
        blocked = client.post(
            f"/manuscripts/{manuscript['id']}/authorship-proposals/suggest", json={}
        )
        assert blocked.status_code == 422
        reviewed = client.post(
            f"/credit-assignments/{assignment['id']}/review",
            json={"state": "confirmed", "note": "team confirmed"},
        )
        assert reviewed.json()["state"] == "confirmed"
        proposal = client.post(
            f"/manuscripts/{manuscript['id']}/authorship-proposals/suggest", json={}
        ).json()
        approved = client.post(
            f"/authorship-proposals/{proposal['id']}/review",
            json={"decision": "approved", "note": "team approved"},
        )
        assert approved.json()["status"] == "approved"
        credit = client.get(f"/manuscripts/{manuscript['id']}/credit").json()
        assert credit["approved_order"] == [contributor["id"]]
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
