"""Offline integration checks use real OS processes and explicitly controlled fake agents."""

import hashlib
import io
import json
import stat
import sys
import threading
import time
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from workbench import config
from workbench.ingest.files import IngestError
from workbench.ingest.research_attachments import inspect_attachment
from workbench.models import Base, Claim, ResearchObject, ResearchTask, Source, Turn, stable_hash, utcnow
from workbench.providers.research_executor import ProcessResearchExecutor
from workbench.research_contract import AgentReport, TaskBrief
from workbench.services import (
    authoring,
    research,
    transfer,
)
from workbench.services import (
    research_runner as runner,
)
from workbench.services import (
    research_tasks as tasks,
)

WORKER = Path(__file__).parent / "fixtures" / "research_protocol_worker.py"
QUESTION = (
    "Let a finite latent ultrametric space be observed through nonempty balls. Can exact inter-cell "
    "distances be retained on refined signatures while the distance topology equals the ProLT "
    "positive-observation topology, for symmetric versus asymmetric generalized ultrametrics?"
)


@pytest.fixture(autouse=True)
def isolated_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WB_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WB_DEPLOYMENT_MODE", "local")
    config.get_settings.cache_clear()
    yield
    runner.shutdown()


def make_task(session, project, question=QUESTION, **settings):
    task = tasks.create_task(session, project.id, TaskBrief(question=question, **settings))
    tasks.attach(
        session,
        task,
        "paper-v0.3.tex",
        b"Section 2\nFinite ball quotient and observation refinement.",
        version="v0.3",
    )
    session.commit()
    return task


def run_controlled(session, task, *, args=None, cancel=None):
    task.state, task.started_at = "planning", utcnow()
    session.commit()
    runner.run_task(
        task.id,
        cancel or threading.Event(),
        executor_factory=lambda mode: ProcessResearchExecutor(
            mode,
            [sys.executable, str(WORKER), *(args or [])],
        ),
    )
    session.expire_all()
    return session.get(ResearchTask, task.id)


def test_lifting_parent_child_parent_and_default_package(session, project):
    task = run_controlled(session, make_task(session, project))
    assert task.state == "completed"
    agents = tasks.agents_for(session, task.id)
    parent = next(a for a in agents if a.role == "parent")
    children = [a for a in agents if a.role == "child"]
    assert len(children) == 3
    assert len({a.provenance["pid"] for a in agents}) == 4
    assert all(a.parent_id == parent.id and a.state == "completed" for a in children)
    assert f"Parent PID {parent.provenance['worker_pid']}" in task.synthesis["summary"]
    assert task.ledger["parent_integration_received"]
    assert task.ledger["live_handoff_verified"] is False
    assert task.ledger["actual_tokens"] == 380
    assert task.ledger["estimated_tokens"] == 0
    assert all(task.synthesis["report_hashes"][a.id] == stable_hash(a.report) for a in children)
    assert all(a.provenance["original_return"] == a.report for a in children)
    assert task.synthesis["comparisons"][0]["state"] == "conflict_or_scope_difference"
    assert session.scalars(select(Claim)).all() == []
    assert session.scalars(select(ResearchObject)).all() == []
    turns = session.scalars(select(Turn).where(Turn.thread_id == task.thread_id)).all()
    assert len(turns) == 2 and turns[-1].provenance["review_required"]
    with zipfile.ZipFile(io.BytesIO(tasks.package(session, task))) as archive:
        names = archive.namelist()
        for expected in (
            "README.md",
            "task_settings.json",
            "source_manifest.json",
            "agent_lineage.json",
            "search_log.json",
            "synthesis.json",
            "verification/index.json",
            "open_questions.md",
            "deliverables/research_report.md",
        ):
            assert expected in names
        for entry in json.loads(archive.read("package_manifest.json"))["files"]:
            assert hashlib.sha256(archive.read(entry["file"])).hexdigest() == entry["sha256"]


@pytest.mark.parametrize("kind", ["literature_search", "proof_audit"])
def test_other_task_types_and_requested_deliverables(session, project, kind):
    task = run_controlled(
        session,
        make_task(
            session, project, task_type=kind, deliverables=["paper", "reviewer_report"], max_children=2
        ),
    )
    assert task.state == "completed"
    reports = [a.report for a in tasks.agents_for(session, task.id) if a.role == "child"]
    assert all(kind in r["summary"] for r in reports)
    with zipfile.ZipFile(io.BytesIO(tasks.package(session, task))) as archive:
        assert archive.read("deliverables/paper.md").startswith(b"# UNREVIEWED")
        assert "deliverables/reviewer_report.md" in archive.namelist()


@pytest.mark.parametrize("flag", ["fail", "bad-report", "bad-plan", "bad-synthesis"])
def test_failure_preserves_completed_work(session, project, flag):
    task = run_controlled(session, make_task(session, project, QUESTION + " " + flag, max_children=2))
    assert task.state == "failed_partial"
    assert task.finished_at
    assert tasks.package(session, task).startswith(b"PK")
    with pytest.raises(tasks.TaskError, match="already started"):
        runner.start(session, task)


def test_capability_rejection_cannot_fall_back_to_chat(session, project):
    task = run_controlled(session, make_task(session, project), args=["bad-capabilities"])
    assert task.state == "failed_partial"
    assert len(tasks.agents_for(session, task.id)) == 1
    assert not task.synthesis["report_ids"]


def test_best_effort_live_protocol_needs_opt_in_and_distinct_model_threads(
    session, project, monkeypatch
):
    # This peer is controlled and offline. It tests the live *protocol gate* only.
    monkeypatch.setenv("WB_RESEARCH_EXECUTOR_ENABLED", "true")
    monkeypatch.setenv("WB_RESEARCH_EXECUTOR_COMMAND", json.dumps([sys.executable, str(WORKER)]))
    config.get_settings.cache_clear()
    refused = run_controlled(
        session,
        make_task(session, project, executor="process", max_children=2),
        args=["live-best-effort"],
    )
    assert refused.state == "failed_partial"
    accepted = run_controlled(
        session,
        make_task(
            session, project, executor="process", allow_best_effort_tokens=True, max_children=2
        ),
        args=["live-best-effort"],
    )
    assert accepted.state == "completed"
    assert accepted.ledger["token_limit_mode"] == "best_effort"
    assert accepted.ledger["live_handoff_verified"]
    agents = tasks.agents_for(session, accepted.id)
    parent = next(a for a in agents if a.role == "parent")
    children = [a for a in agents if a.role == "child"]
    assert parent.provenance["plan_model"]["codex_thread_id"] == parent.provenance[
        "synthesis_model"
    ]["codex_thread_id"]
    assert parent.provenance["active_model_turn"] == parent.provenance["synthesis_model"]
    assert accepted.contract["handoff_token_reserve"] == accepted.contract["token_limit"] // 4
    assert accepted.ledger["allocations"][0]["reserved"] == accepted.contract["token_limit"] // 4
    assert len({a.provenance["report_model"]["codex_thread_id"] for a in children}) == 2


def test_unknown_usage_is_conservative_estimate(session, project):
    task = run_controlled(session, make_task(session, project, QUESTION + " no-usage"))
    child_allowance = sum(a["reserved"] for a in task.ledger["allocations"] if a["phase"] == "research")
    assert task.state == "completed"
    assert task.ledger["actual_tokens"] == 80
    assert task.ledger["estimated_tokens"] == child_allowance
    assert task.ledger["usage_complete"] is False


def test_time_cutoff_without_child_work_does_not_start_model_integration(session, project):
    task = run_controlled(
        session,
        make_task(
            session, project, QUESTION + " silent-slow", max_children=1,
            time_limit_seconds=10,
        ),
    )
    assert task.state == "limit_reached_partial"
    assert [a["phase"] for a in task.ledger["allocations"]] == ["plan", "research"]
    assert task.synthesis["report_ids"] == []
    child = next(a for a in tasks.agents_for(session, task.id) if a.role == "child")
    progress = child.provenance["codex_progress"]
    assert progress["source"] == "codex_notification"
    assert progress["worker_heartbeat_count"] == 1
    assert progress["codex_notification_count"] == 3
    assert progress["codex_notification_types"]["item/agentMessage/delta"] == 1
    with zipfile.ZipFile(io.BytesIO(tasks.package(session, task))) as archive:
        packaged = json.loads(archive.read("agent_lineage.json"))
        packaged_child = next(a for a in packaged if a["id"] == child.id)
        assert packaged_child["provenance"]["codex_progress"] == progress
        assert "item/agentMessage/delta" in json.dumps(packaged_child["provenance"])
        assert "Controlled research" not in json.dumps(packaged_child["provenance"])


@pytest.mark.parametrize("flag", ["soft-token", "hard-token", "slow"])
def test_limits_preserve_checkpoints_and_handoff_reserve(session, project, flag):
    task = run_controlled(
        session,
        make_task(
            session, project, QUESTION + " " + flag, token_limit=2000, time_limit_seconds=10, max_children=2
        ),
    )
    assert task.state == "limit_reached_partial"
    agents = tasks.agents_for(session, task.id)
    assert any(a.checkpoints for a in agents)
    assert task.ledger["research_stopped"]
    assert tasks.snapshot(session, task)["research_can_continue"] is False
    if flag == "hard-token":
        assert not task.ledger.get("parent_integration_received")
    else:
        assert task.ledger["parent_integration_received"]
    with zipfile.ZipFile(io.BytesIO(tasks.package(session, task))) as archive:
        assert json.loads(archive.read("search_log.json"))
        assert b"limit_reached_partial" in archive.read("README.md")


def test_cancellation_mid_child_preserves_saved_checkpoint(session, project):
    task = make_task(session, project, QUESTION + " cancel", max_children=2)
    task.state, task.started_at = "planning", utcnow()
    session.commit()
    stop = threading.Event()
    thread = threading.Thread(
        target=runner.run_task,
        args=(task.id, stop),
        kwargs={
            "executor_factory": lambda mode: ProcessResearchExecutor(mode, [sys.executable, str(WORKER)])
        },
    )
    thread.start()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        session.expire_all()
        if any(a.checkpoints for a in tasks.agents_for(session, task.id)):
            break
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    session.expire_all()
    task = session.get(ResearchTask, task.id)
    assert task.state == "cancelled_partial"
    assert not task.ledger.get("parent_integration_received")
    assert any(a.checkpoints for a in tasks.agents_for(session, task.id))


def test_expired_crash_is_partial_and_never_restarted(session, project):
    task = make_task(session, project, time_limit_seconds=10)
    task.state, task.started_at = "researching", utcnow() - timedelta(seconds=25)
    session.commit()
    runner.recover_expired(session, task)
    assert task.state == "interrupted_partial"
    assert "no research resumed" in task.ledger["stop_reason"]


def archive_of(entries, *, compressed=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED) as archive:
        for name, data in entries:
            if isinstance(name, str):
                entry = zipfile.ZipInfo("placeholder")
                entry.filename = name
                entry.orig_filename = name
                entry.compress_type = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
                name = entry
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "name",
    [
        "../escape.md",
        "/abs.md",
        "C:/escape.md",
        "folder\\escape.md",
        "a/../x.md",
        "NUL.txt",
        "x.md:stream",
        "a./x.md",
    ],
)
def test_zip_rejects_unsafe_paths(name):
    with pytest.raises(IngestError, match="unsafe"):
        inspect_attachment("sources.zip", archive_of([(name, b"document")]))


def test_zip_symlink_collision_crc_and_bomb_rejected():
    link = zipfile.ZipInfo("link.md")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    for payload in [
        archive_of([(link, b"../../x")]),
        archive_of([("a.md", b"a"), ("A.md", b"b")]),
        archive_of([("a.md", b"0" * 100000)], compressed=True),
        archive_of([(f"{i}.md", b"x") for i in range(201)]),
    ]:
        with pytest.raises(IngestError):
            inspect_attachment("sources.zip", payload)
    corrupt = bytearray(archive_of([("a.md", b"unique content")]))
    corrupt[corrupt.index(b"unique content")] ^= 1
    with pytest.raises(IngestError):
        inspect_attachment("sources.zip", bytes(corrupt))


def test_zip_intake_provenance_idempotence_and_frozen_sources(session, project):
    task = tasks.create_task(session, project.id, TaskBrief(question="Literature scope"))
    payload = archive_of(
        [
            ("v1/paper.tex", b"old text"),
            ("v2/paper.tex", b"new text"),
            ("unsafe-to-run.py", b"raise RuntimeError('never execute')"),
            ("unknown.bin", b"opaque"),
        ]
    )
    tasks.attach(session, task, "bundle.zip", payload, version="mixed v1/v2; no current version asserted")
    session.commit()
    before = list(task.sources)
    assert len(before) == 4
    assert before[0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert before[0]["inventory"][-1]["disposition"] == "retained_in_archive_only"
    assert before[1]["sha256"] != before[2]["sha256"]
    assert before[1]["origin"]["member"] == "v1/paper.tex"
    assert before[1]["text"] == "old text"
    tasks.attach(session, task, "bundle.zip", payload, version="same")
    assert task.sources == before
    task.state = "completed"
    with pytest.raises(tasks.TaskError, match="frozen"):
        tasks.attach(session, task, "new.md", b"new", version="v2")


def test_report_categories_require_traceable_evidence():
    report = {
        "summary": "No results",
        "findings": [
            {
                "id": "f1",
                "claim_key": "q",
                "statement": "Nothing",
                "category": "nothing_found",
                "stance": "neutral",
                "scope": "bounded",
                "citation_ids": [],
                "verification_ids": [],
            }
        ],
        "citations": [],
        "proof_attempts": [],
        "failed_approaches": [],
        "unresolved_questions": [],
        "research_leads": [],
        "search_log": [],
        "verification_artifacts": [],
    }
    with pytest.raises(ValueError, match="recorded search"):
        AgentReport.model_validate(report)
    report["findings"][0]["category"] = "verified_result"
    with pytest.raises(ValueError, match="located evidence"):
        AgentReport.model_validate(report)


def test_review_gate_binds_reports_purpose_scope_and_target(session, project):
    task = run_controlled(session, make_task(session, project))
    agent = next(a for a in tasks.agents_for(session, task.id) if a.role == "child")
    digest = tasks.snapshot(session, task)["review_hash"]
    params = {"agent_id": agent.id, "finding_id": "f1", "purpose": "proof", "expected_hash": digest}
    with pytest.raises(tasks.TaskError, match="approval"):
        tasks.promote(session, task, **params)
    with pytest.raises(tasks.TaskError, match="offline"):
        tasks.review_finding(
            session, task, **params, decision="approved", note="Read proof", reviewer="human"
        )
    # Synthetic stored non-simulated task: tests approval logic without invoking a live executor.
    task.contract = {**task.contract, "executor": "process"}
    digest = tasks.snapshot(session, task)["review_hash"]
    params.update(expected_hash=digest)
    tasks.review_finding(
        session, task, **params, decision="approved", note="Checked stated finite scope", reviewer="human"
    )
    with pytest.raises(tasks.TaskError, match="approval"):
        tasks.promote(session, task, **{**params, "purpose": "novelty"})
    promoted = tasks.promote(session, task, **params)
    assert tasks.promote(session, task, **params) == promoted
    obj = session.get(ResearchObject, promoted["object_id"])
    assert obj.accepted_by_user and obj.body["original_report_hash"] == stable_hash(agent.report)
    assert obj.strength == "ai_suggested"
    assert obj.body["assessment"]["proof_review"] == "human_assessed_within_recorded_scope"
    assert obj.body["assessment"]["formal_verification"] == "not_established_by_use_approval"
    manuscript = authoring.create_manuscript(session, project.id, title="Local draft")
    params["purpose"] = "manuscript"
    tasks.review_finding(
        session, task, **params, decision="approved", note="Approved scoped prose", reviewer="human"
    )
    other = research.create_project(session, project.workspace_id, "Other")
    wrong = authoring.create_manuscript(session, other.id, title="Wrong project")
    with pytest.raises(tasks.TaskError, match="this project"):
        tasks.promote(session, task, **params, manuscript_id=wrong.id)
    result = tasks.promote(session, task, **params, manuscript_id=manuscript.id)
    assert session.get(ResearchObject, result["section_id"]).body["claim_ids"] == [result["claim_id"]]


def test_source_changes_cannot_rewrite_snapshot_and_project_transfer(session, project, tmp_path):
    task = run_controlled(session, make_task(session, project))
    original = task.sources[0]["sha256"]
    source = session.get(Source, task.sources[0]["source_id"])
    source.title = "Renamed after the task"
    source.provider_metadata = {
        **source.provider_metadata,
        "research_attachment": {"version": "v999", "origin": {"kind": "changed"}},
    }
    session.commit()
    assert task.sources[0]["version"] == "v0.3"
    assert task.sources[0]["title"] == "paper-v0.3.tex"
    result = transfer.export_project(session, project.id, out_path=str(tmp_path / "project.zip"))
    assert result["row_counts"]["research_tasks"] == 1
    assert result["row_counts"]["research_agents"] == 4
    with zipfile.ZipFile(result["path"]) as archive:
        exported = json.loads(archive.read("project.json"))
        assert exported["research_tasks"][0]["sources"][0]["sha256"] == original
        assert exported["research_agents"][0]["role"] == "parent"
    target_engine = create_engine(f"sqlite:///{tmp_path / 'restored.sqlite3'}")
    Base.metadata.create_all(target_engine)
    with Session(target_engine) as restored:
        restored_id = transfer.import_project(restored, result["path"])["project_id"]
        restored.commit()
        restored_task = restored.get(ResearchTask, task.id)
        assert restored_id == task.project_id
        assert restored_task.state == task.state
        assert restored_task.sources[0]["sha256"] == original
        assert len(tasks.agents_for(restored, task.id)) == 4
        assert tasks.package(restored, restored_task).startswith(b"PK")
    target_engine.dispose()


def test_reselected_document_keeps_version_and_origin(session, project):
    first = make_task(session, project)
    source_id = first.sources[0]["source_id"]
    second = tasks.create_task(
        session, project.id, TaskBrief(question="Independent audit", source_ids=[source_id])
    )
    assert second.sources[0]["version"] == "v0.3"
    assert second.sources[0]["origin"] == first.sources[0]["origin"]


def test_stale_approval_and_concurrent_revision_fail_closed(session, project):
    task = run_controlled(session, make_task(session, project))
    agent = next(a for a in tasks.agents_for(session, task.id) if a.role == "child")
    old_hash = tasks.snapshot(session, task)["review_hash"]
    task.synthesis = {**task.synthesis, "summary": "Changed for stale snapshot test"}
    with pytest.raises(tasks.TaskError, match="stale"):
        tasks.review_finding(
            session,
            task,
            agent_id=agent.id,
            finding_id="f1",
            expected_hash=old_hash,
            decision="rejected",
            purpose="finding",
            note="Review",
            reviewer="human",
        )
    session.commit()
    with Session(session.get_bind()) as other:
        stale = other.get(ResearchTask, task.id)
        tasks.lock_revision(session, task)
        session.commit()
        with pytest.raises(tasks.TaskError, match="concurrently"):
            tasks.lock_revision(other, stale)
