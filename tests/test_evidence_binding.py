import copy

import pytest
from test_publication_packages import _approve
from test_publication_packages import manuscript as manuscript
from test_publication_packages import submission as submission

from workbench import storage
from workbench.models import ClaimEvidence, Excerpt, ResearchObject, Source, stable_hash, utcnow
from workbench.services import (
    authoring,
    evidence_basis,
    export_service,
    manuscript_path,
    publication_packages,
    research,
    revision_review,
)


@pytest.fixture()
def evidence(session, project, manuscript):
    source = Source(
        project_id=project.id,
        title="Synthetic source",
        authors="Test",
        human_verified=True,
        access="user_provided_full_text",
    )
    session.add(source)
    session.flush()
    excerpt = Excerpt(source_id=source.id, text="All test objects satisfy P", locator="p. 1", checksum="one")
    session.add(excerpt)
    result = research.create_object(
        session, project.id, kind="result", title="Synthetic proof", body={"proof": "A"}
    )
    dependency = research.create_object(
        session, project.id, kind="note", title="Hypothesis", body={"text": "P"}
    )
    edge = research.link_objects(session, project.id, result.id, dependency.id, "depends_on")
    session.flush()
    claim = research.create_claim(
        session,
        project.id,
        text="P",
        support="both",
        excerpt_ids=[excerpt.id],
        research_object_ids=[result.id],
    )
    authoring.add_section(
        session, manuscript.id, heading="Proof", purpose="result", text="Proof", claim_ids=[claim.id]
    )
    session.flush()
    return source, excerpt, result, dependency, edge, claim


@pytest.mark.parametrize(
    "mutation",
    [
        "text",
        "locator",
        "checksum",
        "result",
        "dependency",
        "edge",
        "role",
        "delete",
        "policy",
        "extraction",
        "check",
        "review",
    ],
)
def test_approval_binds_evidence_and_retains_history(session, submission, evidence, monkeypatch, mutation):
    source, excerpt, result, dependency, edge, claim = evidence
    package = _approve(
        session, publication_packages.create_package(session, submission.id, included_formats=["md"])
    )
    session.flush()
    historical = copy.deepcopy(package.snapshot)
    history = copy.deepcopy(package.history)
    if mutation in {"text", "locator", "checksum"}:
        setattr(excerpt, mutation, "changed")
    elif mutation == "result":
        result.body = {"proof": "wrong"}
    elif mutation == "dependency":
        dependency.body = {"text": "not P"}
    elif mutation == "edge":
        edge.relation = "contradicts"
    elif mutation == "role":
        session.query(ClaimEvidence).filter_by(claim_id=claim.id).first().entailment = "contradicts"
    elif mutation == "delete":
        excerpt.deleted_at = utcnow()
    elif mutation == "policy":
        monkeypatch.setattr(evidence_basis, "POLICY_VERSION", "next-policy")
    elif mutation == "extraction":
        source.provider_metadata = {"ingest": {"extractor": "changed-v2"}}
    else:
        research.create_object(
            session,
            source.project_id,
            kind="note",
            title=mutation,
            body={"manuscript_id": package.manuscript_id, "status": "failed"},
        )
    status = publication_packages.readiness(session, package.id)
    assert status["stale"] and not status["ready"]
    assert package.state == "approved" and package.snapshot == historical and package.history == history


def test_unrelated_project_material_does_not_change_approval(session, submission, evidence):
    package = _approve(
        session, publication_packages.create_package(session, submission.id, included_formats=["md"])
    )
    source = Source(
        project_id=submission.project_id,
        title="Unrelated",
        integrity_note="retracted",
        access="metadata_only",
    )
    session.add(source)
    research.create_object(session, submission.project_id, kind="figure", title="Orphan", body={})
    other = authoring.create_manuscript(session, submission.project_id, title="Other manuscript")
    research.create_object(
        session,
        submission.project_id,
        kind="note",
        title="Open unrelated review",
        body={"manuscript_id": other.id, "objection": "problem"},
    )
    assert publication_packages.readiness(session, package.id)["ready"]
    scoped = manuscript_path.build_project_path(
        session, submission.project_id, manuscript_id=submission.manuscript_id
    )
    assert scoped["scope"] == "manuscript"
    assert not manuscript_path.build_project_path(session, submission.project_id)["publication_ready"]


def test_source_bytes_are_verified(session, submission, evidence, tmp_path, monkeypatch):
    from workbench.config import get_settings

    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    source = evidence[0]
    reference = storage.store_content(
        b"original", filename="source.txt", namespace="sources", content_type="text/plain"
    )
    source.provider_metadata = {"ingest": {"artifact": reference}}
    package = _approve(
        session, publication_packages.create_package(session, submission.id, included_formats=["md"])
    )
    from pathlib import Path

    Path(storage.local_path(reference)).write_bytes(b"substitute")
    status = publication_packages.readiness(session, package.id)
    assert status["stale"] and status["blockers"]


@pytest.mark.parametrize("mode", ["race", "swap", "other_manifest"])
def test_export_race_and_substitution_rejected(session, submission, evidence, monkeypatch, tmp_path, mode):
    from workbench.config import get_settings

    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    package = _approve(
        session, publication_packages.create_package(session, submission.id, included_formats=["md"])
    )
    original = export_service.export_manuscript

    def export(*args, **kwargs):
        value = original(*args, **kwargs)
        if mode == "race":
            evidence[1].text = "changed during export"
        elif mode == "swap":
            value["artifact_refs"]["md"] = storage.store_content(
                b"substitute", filename="manuscript.md", namespace="exports", content_type="text/markdown"
            )
        else:
            import json

            manifest = json.loads(storage.read_bytes(value["artifact_refs"]["manifest"]))
            manifest["evidence_basis_hash"] = "0" * 64
            value["artifact_refs"]["manifest"] = storage.store_content(
                json.dumps(manifest).encode(),
                filename="manifest.json",
                namespace="exports",
                content_type="application/json",
            )
        return value

    monkeypatch.setattr(export_service, "export_manuscript", export)
    with pytest.raises(
        publication_packages.PackageError, match="changed during export|substituted|does not match"
    ):
        publication_packages.build_bundle(session, package.id)
    assert not package.builds


def test_revision_requires_effective_version_bound_verification(session, manuscript):
    review = revision_review.open_round(
        session,
        manuscript.id,
        reviewer="reviewer",
        comments=[
            {"id": "R1", "objection": "P is unsupported", "acceptance_criterion": "Supply proof or narrow P"}
        ],
    )
    revision_review.respond(
        session,
        review.id,
        comment_id="R1",
        author="author",
        response="Fixed everything",
        changes="No effective change",
    )
    assert revision_review.dispositions(session, review)["R1"] == "open"

    def verify(**overrides):
        args = dict(
            comment_id="R1",
            verifier="verifier",
            response_hash=stable_hash(review.body["events"][-1]),
            expected_candidate_hash=revision_review.candidate_hash(session, manuscript.id),
            expected_comment_hash=stable_hash(review.body["comments"][0]),
            criterion_met=False,
            regression_passed=True,
            evidence="The claim remains unsupported",
            disposition="resolved",
        )
        args.update(overrides)
        revision_review.verify(session, review.id, **args)

    with pytest.raises(research.IntegrityError, match="closure"):
        verify()
    verify(disposition="open")
    manuscript.body = {**manuscript.body, "scope": "P is a hypothesis"}
    revision_review.respond(
        session,
        review.id,
        comment_id="R1",
        author="author",
        response="Narrowed scope",
        changes="P is a hypothesis",
    )
    verify(criterion_met=True, evidence="Unsupported assertion withdrawn; adjacent claims checked")
    assert revision_review.dispositions(session, review)["R1"] == "resolved"
    manuscript.body = {**manuscript.body, "scope": "P is proven"}
    assert revision_review.dispositions(session, review)["R1"] == "open"
    revision_review.respond(
        session, review.id, comment_id="R1", author="author", response="Restored claim", changes="P is proven"
    )
    verify(disposition="regressed", regression_passed=False)
    assert revision_review.dispositions(session, review)["R1"] == "regressed"


def test_required_check_blocks_until_evidence_recorded(session, submission):
    check = research.create_object(
        session,
        submission.project_id,
        kind="note",
        title="Required check",
        body={"verification_status": "failed"},
    )
    paper = session.get(ResearchObject, submission.manuscript_id)
    paper.body = {**paper.body, "required_check_ids": [check.id]}
    package = publication_packages.create_package(session, submission.id, included_formats=["md"])
    from test_publication_packages import _complete_draft

    _complete_draft(session, package)
    assert any(
        "required-check-unverified" in b["message"]
        for b in publication_packages.readiness(session, package.id)["blockers"]
    )
    check.body = {"verification_status": "passed", "verification_evidence": "Synthetic test receipt"}
    _approve(session, package)
    check.body = {"verification_status": "failed", "verification_evidence": "Regression detected"}
    assert publication_packages.readiness(session, package.id)["stale"]


def test_second_approved_manuscript_is_unaffected(session, project, submission, evidence):
    from workbench.services import submissions

    first = _approve(
        session, publication_packages.create_package(session, submission.id, included_formats=["md"])
    )
    other = manuscript.__wrapped__(session, project)
    second_submission = submissions.create_submission(
        session, project.id, manuscript_id=other.id, venue_name="Test"
    )
    second = _approve(
        session, publication_packages.create_package(session, second_submission.id, included_formats=["md"])
    )
    evidence[1].text = "Changed supporting meaning"
    assert publication_packages.readiness(session, first.id)["stale"]
    assert publication_packages.readiness(session, second.id)["ready"]


def test_external_session_evidence_race_rejected(session, submission, evidence, monkeypatch, tmp_path):
    from sqlalchemy.orm import Session

    from workbench.config import get_settings

    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    package = _approve(
        session, publication_packages.create_package(session, submission.id, included_formats=["md"])
    )
    session.commit()
    original = export_service.export_manuscript

    def export(*args, **kwargs):
        value = original(*args, **kwargs)
        with Session(session.get_bind()) as other:
            other.get(Excerpt, evidence[1].id).text = "Changed concurrently"
            other.commit()
        return value

    monkeypatch.setattr(export_service, "export_manuscript", export)
    with pytest.raises(publication_packages.PackageError, match="changed during export"):
        publication_packages.build_bundle(session, package.id)


def test_package_captures_explicit_supplement(session, submission, tmp_path, monkeypatch):
    import io
    import json
    import zipfile

    from workbench.config import get_settings
    from workbench.services import figures

    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    data = figures.create_dataset(session, submission.project_id, name="Data", columns=["n"], rows=[[1]])
    table = figures.build_table(session, submission.project_id, title="Table", dataset_id=data.id)
    paper = session.get(ResearchObject, submission.manuscript_id)
    paper.body = {**paper.body, "artifact_ids": [table.id]}
    package = _approve(
        session, publication_packages.create_package(session, submission.id, included_formats=["md"])
    )
    result = publication_packages.build_bundle(session, package.id)
    # The captured package contains the bytes from the declared content-addressed supplement.
    with zipfile.ZipFile(io.BytesIO(storage.read_bytes(result["artifact"]))) as archive:
        name = f"manuscript/supplements/table_{table.id}.md"
        assert archive.read(name).decode() == table.body["markdown"]
        assert json.loads(archive.read("approval-snapshot.json"))["evidence_basis"]


def test_evidence_descriptor_cannot_read_arbitrary_host_file(session, evidence, submission, monkeypatch):
    source = evidence[0]
    source.provider_metadata = {
        "artifact": {
            "storage_backend": "local",
            "storage_key": "admitted.txt",
            "local_path": "C:/hidden-canary.txt",
            "sha256": "a" * 64,
        }
    }

    def forbidden_read(reference):
        pytest.fail("invalid descriptor reached the artifact reader")

    monkeypatch.setattr(storage, "read_bytes", forbidden_read)
    basis = evidence_basis.collect(session, submission.manuscript_id)
    assert basis["problems"]
