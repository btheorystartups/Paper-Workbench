from copy import deepcopy

import pytest

from workbench.models import stable_hash
from workbench.services import authoring, manuscript_path


def snapshot():
    report = {
        "findings": [{"id": "f1", "category": "verified_result"}],
        "citations": [{"id": "c1", "locator": "page 1"}],
        "verification_artifacts": [{"id": "v1", "outcome": "passed_within_scope"}],
    }
    return {
        "id": "t1",
        "project_id": "p1",
        "state": "completed",
        "contract": {"executor": "process"},
        "sources": [{"source_id": "s1"}],
        "synthesis": {},
        "review_hash": "hash",
        "reviews": {},
        "agents": [{"id": "a1", "role": "child", "report": report}],
    }


def approve(task, purpose="manuscript"):
    task["reviews"][f"a1:f1:{purpose}"] = {
        "decision": "approved",
        "purpose": purpose,
        "note": "Checked within recorded scope",
        "reviewer": "Human",
        "snapshot_hash": task["review_hash"],
        "report_hash": stable_hash(task["agents"][0]["report"]),
    }


def test_completed_narrow_run_is_not_manuscript_ready():
    result = manuscript_path.build_path_from_snapshot(snapshot())
    assert len(result["stages"]) == 10
    assert not result["publication_ready"]
    assert result["counts"]["valid_human_reviews"] == 0
    assert result["stages"][0]["blockers"]
    assert "Publication ready: no" in manuscript_path.markdown(result)
    assert all("next_action" in s and "evidence" in s for s in result["stages"])


def test_review_is_bound_to_snapshot_report_and_existing_finding():
    task = snapshot()
    approve(task)
    assert len(manuscript_path.valid_reviews(task)) == 1
    changed = deepcopy(task)
    changed["review_hash"] = "new"
    assert not manuscript_path.valid_reviews(changed)
    changed = deepcopy(task)
    changed["agents"][0]["report"]["summary"] = "changed"
    assert not manuscript_path.valid_reviews(changed)
    changed = deepcopy(task)
    changed["reviews"]["a1:missing:manuscript"] = changed["reviews"].pop("a1:f1:manuscript")
    assert not manuscript_path.valid_reviews(changed)
    task["contract"]["executor"] = "offline"
    assert not manuscript_path.valid_reviews(task)


def test_partial_and_multiple_tasks_preserve_all_evidence():
    first, second = snapshot(), snapshot()
    second["id"] = "t2"
    second["state"] = "failed_partial"
    result = manuscript_path.build_path_from_snapshots([first, second])
    assert result["counts"]["tasks"] == 2
    assert result["counts"]["findings"] == 2
    assert result["counts"]["sources"] == 1
    assert result["stages"][1]["blockers"]
    assert len(result["stages"][1]["evidence"]) == 2


def test_project_inventory_reads_sections_without_export_or_models(session, project):
    ms = authoring.create_manuscript(session, project.id, title="Provisional outline")
    authoring.add_section(session, ms.id, heading="Open gaps", text="Evidence needed.")
    result = manuscript_path.build_project_path(session, project.id)
    assert result["counts"]["sections"] == 1
    assert result["stages"][5]["state"] == "recorded"
    assert not result["publication_ready"]
    assert result["stages"][8]["state"] == "missing"


def test_stale_publication_approval_is_not_ready():
    task = snapshot()
    approve(task)
    evidence = {
        "claim_count": 1,
        "packages": [
            {"id": "p", "version": 1, "state": "approved", "ready": True, "stale": True, "build_count": 1}
        ],
    }
    result = manuscript_path.build_path_from_snapshot(task, evidence)
    assert not result["publication_ready"]
    evidence["packages"][0]["stale"] = False
    result = manuscript_path.build_path_from_snapshot(task, evidence)
    assert result["publication_package_approved"]
    assert not result["publication_ready"]


def test_proof_and_novelty_require_verified_category():
    task = snapshot()
    task["agents"][0]["report"]["findings"][0]["category"] = "conjecture"
    approve(task, "proof")
    assert not manuscript_path.valid_reviews(task)


def test_deterministic_conflicts_are_visible_when_parent_omits_them():
    task = snapshot()
    task["synthesis"] = {
        "conflicts": [],
        "comparisons": [{"state": "conflict_or_scope_difference", "findings": []}],
    }
    result = manuscript_path.build_path_from_snapshot(task)
    assert "Agent disagreements require resolution." in result["stages"][2]["blockers"]


def test_checkpoint_counts_are_labelled_and_not_double_counted():
    task = snapshot()
    report = task["agents"][0].pop("report")
    task["agents"][0]["checkpoints"] = [{"report": report}, {"report": report}]
    result = manuscript_path.build_path_from_snapshot(task)
    assert result["counts"]["checkpoint_reports"] == 1
    assert result["counts"]["child_reports"] == 0
    assert result["counts"]["findings"] == 1
    assert "latest checkpoint" in result["stages"][1]["evidence"][0]["label"]
    task["agents"][0]["report"] = report
    result = manuscript_path.build_path_from_snapshot(task)
    assert result["counts"]["checkpoint_reports"] == 0
    assert result["counts"]["findings"] == 1


def ready_fixture():
    task = snapshot()
    task["sources"].append({"source_id": "s2"})
    for purpose in ("manuscript", "proof", "novelty"):
        approve(task, purpose)
    evidence = {
        "claim_count": 1,
        "manuscripts": [{"id": "m", "title": "Draft", "section_count": 1}],
        "skeptical_reviews": [
            {"accepted_by_user": True, "body": {"response": "Addressed", "resolution": "resolved"}}
        ],
        "compute_runs": [
            {
                "id": "r",
                "state": "succeeded",
                "review_state": "verified",
                "review_note": "Checked",
                "manifest_hash": "hash",
            }
        ],
        "exports": [{"formats": ["pdf"], "url": "/manuscripts/m/audit"}],
        "packages": [
            {"id": "p", "version": 2, "state": "approved", "ready": True, "stale": False, "build_count": 1},
            {"id": "old", "version": 1, "state": "rejected", "blockers": [{"message": "Old"}]},
        ],
    }
    return task, evidence


@pytest.mark.parametrize(
    "gap", ["proof", "novelty", "skeptical_reviews", "compute_runs", "exports", "manuscripts"]
)
def test_approved_package_cannot_hide_missing_required_stage(gap):
    task, evidence = ready_fixture()
    assert manuscript_path.build_path_from_snapshot(task, evidence)["publication_ready"]
    if gap in {"proof", "novelty"}:
        task["reviews"].pop(f"a1:f1:{gap}")
    else:
        evidence[gap] = []
    result = manuscript_path.build_path_from_snapshot(task, evidence)
    assert result["publication_package_approved"]
    assert not result["publication_ready"]
    assert result["stages"][-1]["blockers"]


def test_existing_export_and_actual_skeptic_notes_are_recorded(session, project, tmp_path, monkeypatch):
    from workbench import config
    from workbench.services import audits, export_service

    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WB_PDF_RENDERER", "minimal")
    config.get_settings.cache_clear()
    ms = authoring.create_manuscript(session, project.id, title="Outline")
    authoring.add_section(session, ms.id, heading="Gap", text="Evidence needed.")
    export_service.export_manuscript(session, ms.id, formats=["pdf"])
    audits.skeptical_review(session, ms.id)
    result = manuscript_path.build_project_path(session, project.id)
    assert result["stages"][6]["state"] == "needs_review"
    assert result["stages"][8]["state"] == "recorded"
    config.get_settings.cache_clear()
