"""Research task intake, immutable source snapshots, review and portable handoffs."""

import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import storage
from ..audit import record_audit
from ..config import get_settings
from ..ingest.files import IngestError, extracted_text_for, ingest_file
from ..ingest.research_attachments import MAX_EXPANDED_BYTES, inspect_attachment
from ..models import ResearchAgent, ResearchTask, Source, Turn, stable_hash, utcnow
from ..research_contract import TaskBrief
from . import authoring, dialogue, research

TERMINAL = {
    "completed",
    "limit_reached_partial",
    "failed_partial",
    "cancelled_partial",
    "interrupted_partial",
}
MAX_SOURCE_CHARS = 120000
MAX_CONTEXT_CHARS = 400000


class TaskError(ValueError):
    pass


def task_for(session: Session, project_id: str, task_id: str) -> ResearchTask:
    research._project(session, project_id)
    task = session.get(ResearchTask, task_id)
    if task is None or task.project_id != project_id or task.deleted_at is not None:
        raise TaskError("research task not found in project")
    return task


def agents_for(session: Session, task_id: str) -> list[ResearchAgent]:
    return list(
        session.scalars(
            select(ResearchAgent)
            .where(ResearchAgent.task_id == task_id)
            .order_by(ResearchAgent.created_at, ResearchAgent.id)
        )
    )


def audit(session: Session, task: ResearchTask, action: str, detail: dict):
    project = research._project(session, task.project_id)
    record_audit(
        session,
        workspace_id=project.workspace_id,
        actor="user"
        if action
        in {
            "create_research_task",
            "attach_research_sources",
            "review_research_finding",
            "promote_research_finding",
        }
        else "research_runner",
        action=action,
        object_type="research_task",
        object_id=task.id,
        detail=detail,
    )


def source_snapshot(source: Source, *, version: str = "unspecified", origin: dict | None = None) -> dict:
    meta = source.provider_metadata.get("ingest", {})
    attachment = source.provider_metadata.get("research_attachment", {})
    if origin is None and attachment:
        version = attachment.get("version", version)
        origin = attachment.get("origin")
    if not meta.get("artifact") or not meta.get("extracted_artifact"):
        raise TaskError("select ingested documents with preserved originals and extracted text")
    original = storage.read_bytes(meta["artifact"])
    digest = hashlib.sha256(original).hexdigest()
    if digest != meta.get("checksum_sha256"):
        raise TaskError("source original hash differs from its ingestion provenance")
    text = extracted_text_for(source)
    if text is None:
        raise TaskError("source extracted text is missing or failed its hash check")
    return {
        "source_id": source.id,
        "title": source.title,
        "authors": source.authors,
        "year": source.year,
        "venue": source.venue,
        "doi": source.doi,
        "url": source.url,
        "version": version,
        "version_status": "user_declared" if version != "unspecified" else "not_established",
        "sha256": digest,
        "bytes": len(original),
        "artifact": meta["artifact"],
        "extracted_artifact": meta["extracted_artifact"],
        "access": str(source.access),
        "license": source.license,
        "acquisition": source.acquisition,
        "human_verified": source.human_verified,
        "extraction_confidence": meta.get("extraction_confidence"),
        "extraction_detail": meta.get("extraction_detail", {}),
        "origin": origin or {"kind": "existing_project_source", "original_name": meta.get("original_path")},
        "text": text[:MAX_SOURCE_CHARS],
        "context_truncated": len(text) > MAX_SOURCE_CHARS,
        "full_extracted_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "snapshot_at": utcnow().isoformat(),
    }


def validate_sources(sources: list[dict]):
    documents = [s for s in sources if s.get("source_id")]
    if len(documents) > 40 or sum(s["bytes"] for s in documents) > MAX_EXPANDED_BYTES:
        raise TaskError("task source count or total size exceeds the intake limit")
    if sum(len(s.get("text", "")) for s in documents) > MAX_CONTEXT_CHARS:
        raise TaskError("task source context is too large; select fewer documents")
    if len({s["source_id"] for s in documents}) != len(documents):
        raise TaskError("a source may only be attached once")


def create_task(session: Session, project_id: str, brief: TaskBrief) -> ResearchTask:
    research._project(session, project_id)
    sources = []
    for source_id in brief.source_ids:
        source = session.get(Source, source_id)
        if source is None or source.project_id != project_id or source.deleted_at is not None:
            raise TaskError("source not found in project")
        sources.append(source_snapshot(source))
    contract = brief.normalized()
    if brief.reuse_prior_research:
        from .research_retrieval import retrieve

        context = retrieve(session, project_id, brief.question, brief.coverage_topics,
                           mode=brief.retrieval_mode, recall=brief.retrieval_recall)
        existing = {s["source_id"] for s in sources}
        passages = {}
        for card in context["cards"]:
            if card["kind"] == "source_passage":
                origin = card["origins"][0]
                passages.setdefault(origin["source_id"], []).append((card, origin))
        for source_id, entries in passages.items():
            if source_id in existing:
                continue
            source = session.get(Source, source_id)
            frozen = source_snapshot(source)
            for card, origin in entries:
                if frozen["text"][origin["start"]:origin["end"]] != card["text"]:
                    raise TaskError("retrieved source changed; preview and create again")
            frozen["text"] = "\n\n".join(o["locator"] + "\n" + c["text"] for c, o in entries)
            frozen["context_truncated"] = True
            frozen["context_mode"] = "retrieved passages only"
            frozen["retrieval_passages"] = [
                {"card_id": c["id"], "start": o["start"], "end": o["end"],
                 "text_sha256": c["text_sha256"]} for c, o in entries]
            sources.append(frozen)
        contract["retrieval"] = context
    validate_sources(sources)
    thread = dialogue.create_thread(
        session, project_id, title="Research: " + brief.question[:280], goal=brief.question
    )
    task = ResearchTask(
        project_id=project_id, thread_id=thread.id, contract=contract, sources=sources
    )
    session.add(task)
    session.flush()
    session.add(
        Turn(
            thread_id=thread.id,
            role="user",
            content=brief.question,
            provenance={"research_task_id": task.id, "contract_hash": stable_hash(task.contract)},
        )
    )
    audit(session, task, "create_research_task", {"contract_hash": stable_hash(task.contract)})
    return task


def attach(
    session: Session, task: ResearchTask, filename: str, payload: bytes, *, version: str
) -> list[dict]:
    if task.state != "draft":
        raise TaskError("sources are frozen once execution starts; create a new task for another version")
    if len(payload) > get_settings().upload_max_bytes:
        raise TaskError("attachment exceeds the configured upload size limit")
    if not version.strip() or len(version) > 200:
        raise TaskError("supply a version label or 'unspecified'")
    inventory, documents = inspect_attachment(filename, payload)
    if sum(s.get("bytes", 0) for s in task.sources) + len(payload) > 2 * MAX_EXPANDED_BYTES:
        raise TaskError("task attachment size exceeds intake limit")
    digest = hashlib.sha256(payload).hexdigest()
    if any(s.get("attachment_sha256") == digest for s in task.sources):
        return task.sources  # Idempotent retry of identical upload.
    archive_ref = storage.store_content(payload, filename=Path(filename).name, namespace="research/intake")
    additions = []
    if inventory:
        additions.append(
            {
                "kind": "archive",
                "name": filename,
                "sha256": digest,
                "attachment_sha256": digest,
                "bytes": len(payload),
                "version": version,
                "artifact": archive_ref,
                "inventory": inventory,
            }
        )
    with tempfile.TemporaryDirectory(prefix="wb-research-intake-") as directory:
        for index, (name, data) in enumerate(documents):
            # Generated disk names only. No archive path is ever used for extraction.
            path = Path(directory) / f"document-{index}{Path(name).suffix.lower()}"
            path.write_bytes(data)
            try:
                source = ingest_file(
                    session,
                    task.project_id,
                    path,
                    title=name,
                    original_name=name,
                    pdf_mode="text",
                    license="user-supplied; not assessed",
                    acquisition=f"research task {task.id}; upload {filename}; version {version}"[:200],
                )
            except IngestError as exc:
                raise TaskError(str(exc)) from exc
            snapshot = source_snapshot(
                source,
                version=version,
                origin={
                    "kind": "zip_member" if inventory else "upload",
                    "attachment_name": filename,
                    "attachment_sha256": digest,
                    "member": name,
                },
            )
            snapshot["attachment_sha256"] = digest
            source.provider_metadata = {
                **source.provider_metadata,
                "research_attachment": {"version": version, "origin": snapshot["origin"]},
            }
            additions.append(snapshot)
    sources = task.sources + additions
    validate_sources(sources)
    # Concurrent start/upload must not silently change the frozen input snapshot.
    changed = session.execute(
        update(ResearchTask)
        .where(
            ResearchTask.id == task.id,
            ResearchTask.state == "draft",
            ResearchTask.revision == task.revision,
        )
        .values(sources=sources, revision=task.revision + 1)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise TaskError("task changed while uploading; retry against the current task")
    session.expire(task)
    audit(session, task, "attach_research_sources", {"attachment_sha256": digest, "version": version})
    return task.sources


def agent_dict(agent: ResearchAgent) -> dict:
    return {
        "id": agent.id,
        "parent_id": agent.parent_id,
        "role": agent.role,
        "state": agent.state,
        "assignment": agent.assignment,
        "report": agent.report,
        "checkpoints": agent.checkpoints,
        "provenance": agent.provenance,
    }


def snapshot(session: Session, task: ResearchTask) -> dict:
    agents = [agent_dict(a) for a in agents_for(session, task.id)]
    quality = None
    readiness = None
    if task.contract.get("quality_manuscript_id"):
        from .manuscript_quality import assessment

        quality = assessment(session, task.contract["quality_manuscript_id"])
        from .manuscript_readiness import report

        readiness = report(session, task.contract["quality_manuscript_id"])
    return {
        "id": task.id,
        "project_id": task.project_id,
        "thread_id": task.thread_id,
        "state": task.state,
        "contract": task.contract,
        "sources": [{k: v for k, v in s.items() if k != "text"} for s in task.sources],
        "ledger": task.ledger,
        "synthesis": task.synthesis,
        "reviews": task.reviews,
        "agents": agents,
        "cancel_requested": task.cancel_requested,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "review_hash": review_hash(task, agents),
        "research_can_continue": task.state not in TERMINAL,
        "quality": quality,
        "readiness": readiness,
    }


def review_hash(task: ResearchTask, agents: list[dict]) -> str:
    return stable_hash(
        {
            "contract": task.contract,
            "sources": task.sources,
            "state": task.state,
            "synthesis": task.synthesis,
            "reports": {a["id"]: a["report"] for a in agents if a["role"] == "child"},
        }
    )


def finding_for(session: Session, task: ResearchTask, agent_id: str, finding_id: str):
    agent = session.get(ResearchAgent, agent_id)
    if not agent or agent.task_id != task.id or agent.role != "child":
        raise TaskError("child report not found in task")
    finding = next((f for f in agent.report.get("findings", []) if f["id"] == finding_id), None)
    if not finding:
        raise TaskError("finding not found in original child report")
    return agent, finding


def lock_revision(session: Session, task: ResearchTask):
    """Compare-and-swap prevents duplicate promotions and lost concurrent reviews."""
    changed = session.execute(
        update(ResearchTask)
        .where(
            ResearchTask.id == task.id,
            ResearchTask.revision == task.revision,
        )
        .values(revision=task.revision + 1)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise TaskError("task changed concurrently; reload before reviewing or promoting")
    session.expire(task, ["revision"])


def review_finding(
    session: Session,
    task: ResearchTask,
    *,
    agent_id: str,
    finding_id: str,
    expected_hash: str,
    decision: str,
    purpose: str,
    note: str,
    reviewer: str,
) -> dict:
    if task.state not in TERMINAL:
        raise TaskError("finish or stop the task before reviewing its findings")
    current = snapshot(session, task)["review_hash"]
    if expected_hash != current:
        raise TaskError("review snapshot is stale")
    agent, finding = finding_for(session, task, agent_id, finding_id)
    if not note.strip():
        raise TaskError("human review requires a substantive review note")
    if decision not in {"approved", "rejected"} or purpose not in {
        "finding",
        "proof",
        "novelty",
        "manuscript",
    }:
        raise TaskError("invalid review decision or purpose")
    if decision == "approved" and task.contract["executor"] == "offline":
        raise TaskError("offline simulated findings cannot be promoted; obtain real evidence in a new task")
    if (
        decision == "approved"
        and purpose in {"proof", "novelty"}
        and finding["category"] != "verified_result"
    ):
        raise TaskError(
            "proof or novelty review requires a verified-within-scope result and human assessment"
        )
    key = f"{agent_id}:{finding_id}:{purpose}"
    if task.reviews.get(key, {}).get("promotion"):
        raise TaskError("already promoted; existing review and provenance are immutable")
    lock_revision(session, task)
    review = {
        "snapshot_hash": current,
        "report_hash": stable_hash(agent.report),
        "decision": decision,
        "purpose": purpose,
        "note": note.strip(),
        "reviewer": reviewer,
        "at": utcnow().isoformat(),
    }
    previous = task.reviews.get(key)
    task.reviews = {**task.reviews, key: review}
    audit(session, task, "review_research_finding", {"key": key, "review": review, "previous": previous})
    return review


def promote(
    session: Session,
    task: ResearchTask,
    *,
    agent_id: str,
    finding_id: str,
    purpose: str,
    expected_hash: str,
    manuscript_id: str | None = None,
) -> dict:
    key = f"{agent_id}:{finding_id}:{purpose}"
    review = task.reviews.get(key, {})
    if (
        task.state not in TERMINAL
        or review.get("decision") != "approved"
        or expected_hash != snapshot(session, task)["review_hash"]
        or review.get("snapshot_hash") != expected_hash
    ):
        raise TaskError("current hash-bound human approval is required before promotion")
    if review.get("promotion"):
        return review["promotion"]
    agent, finding = finding_for(session, task, agent_id, finding_id)
    if stable_hash(agent.report) != review["report_hash"]:
        raise TaskError("original report changed after approval")
    lock_revision(session, task)
    if purpose == "manuscript":
        from ..models import ResearchObject

        manuscript = session.get(ResearchObject, manuscript_id) if manuscript_id else None
        if not manuscript or manuscript.project_id != task.project_id or manuscript.kind != "manuscript":
            raise TaskError("select a manuscript from this project")
    obj = research.create_object(
        session,
        task.project_id,
        kind="result" if purpose == "proof" else "note",
        title=finding["statement"][:500],
        ai_suggested=True,
        strength="ai_suggested",
        body={
            "finding": finding,
            "assessment": {
                "use_approval": "approved",
                "proof_review": (
                    "human_assessed_within_recorded_scope" if purpose == "proof" else "not_assessed"
                ),
                "finite_verification": "not_established_by_use_approval",
                "formal_verification": "not_established_by_use_approval",
            },
            "research_task_id": task.id,
            "agent_id": agent_id,
            "original_report_hash": stable_hash(agent.report),
            "review": review,
            "source_manifest": [{k: v for k, v in s.items() if k != "text"} for s in task.sources],
            "novelty": "human_assessed_within_recorded_scope" if purpose == "novelty" else "not_assessed",
        },
    )
    research.accept_object(session, obj.id)
    result = {"object_id": obj.id}
    if purpose == "manuscript":
        claim = research.create_claim(
            session,
            task.project_id,
            text=finding["statement"],
            support="research_result",
            research_object_ids=[obj.id],
            notes="Human-reviewed research finding; scope: " + finding["scope"],
        )
        section = authoring.add_section(
            session,
            manuscript_id,
            heading="Reviewed research finding",
            text=finding["statement"] + "\n\nScope: " + finding["scope"],
            claim_ids=[claim.id],
        )
        result.update(claim_id=claim.id, section_id=section.id)
    task.reviews = {**task.reviews, key: {**review, "promotion": result}}
    audit(session, task, "promote_research_finding", {"key": key, **result})
    return result


def report_markdown(agent: dict) -> str:
    report = agent["report"]
    lines = [
        f"# Agent {agent['id']}",
        f"State: {agent['state']}",
        report.get("summary", "No report received."),
    ]
    for field, values in report.items():
        if field == "summary":
            continue
        lines += ["", "## " + field.replace("_", " "), "```json", json.dumps(values, indent=2), "```"]
    return "\n".join(lines)


def package(session: Session, task: ResearchTask, *, include_results_pdf: bool = True) -> bytes:
    data = snapshot(session, task)
    complete = task.state == "completed"
    status = task.state if task.state in TERMINAL else "in_progress_checkpoint_partial"
    files: dict[str, bytes] = {}

    def add(name: str, value):
        files[name] = (value if isinstance(value, str) else json.dumps(value, indent=2, default=str)).encode()

    add(
        "README.md",
        f"# Research handoff\n\nStatus: {status}\n\n{task.contract['question']}\n\n"
        + (
            "OFFLINE SIMULATION: no live model research was performed.\n\n"
            if task.contract["executor"] == "offline"
            else "Executor results require human scientific review.\n\n"
        )
        + (
            "Token stopping was best effort: an in-flight model turn could exceed its "
            "allowance. Reported usage and estimates are labeled in task_settings.json.\n\n"
            if task.ledger.get("token_limit_mode") == "best_effort"
            else ""
        )
        + "A completed workflow does not establish proof or novelty. Original reports are preserved.\n\n"
        + (
            "Research has stopped. This package includes only work saved before the cutoff.\n\n"
            if task.state in TERMINAL
            else "This is a snapshot of work completed so far.\n\n"
        )
        + task.synthesis.get("summary", "No synthesis available yet.")
        + "\n\nRead task_settings.json, agent_lineage.json, source_manifest.json, search_log.json, "
        "agents/, synthesis.json, verification/, open_questions.md and reviews.json. "
        "Requested deliverables are unreviewed drafts, never automatically manuscript text.\n",
    )
    add(
        "task_settings.json",
        {k: v for k, v in data.items() if k not in {"agents", "sources", "synthesis", "reviews"}},
    )
    add("source_manifest.json", data["sources"])
    add(
        "agent_lineage.json",
        [{k: v for k, v in a.items() if k not in {"report", "checkpoints"}} for a in data["agents"]],
    )
    add("synthesis.json", task.synthesis)
    add(
        "synthesis.md",
        "# Parent synthesis\n\n"
        + task.synthesis.get("summary", "Not yet available.")
        + "\n\n```json\n"
        + json.dumps(task.synthesis, indent=2)
        + "\n```\n",
    )
    add("reviews.json", task.reviews)
    if task.contract.get("quality_policy"):
        from .manuscript_quality import campaign_export

        add("manuscript-quality.json", campaign_export(session, task))
        add("readiness-report.json", data["readiness"])
    add("call-trace.json", task.ledger.get("call_trace", []))
    add("call-timing-summary.json", task.ledger.get("trace_summary", {}))
    searches, open_questions, verification_index = [], [], []
    for agent in data["agents"]:
        aid = agent["id"]
        add(f"agents/{aid}/report.json", agent["report"])
        add(f"agents/{aid}/report.md", report_markdown(agent))
        add(f"agents/{aid}/checkpoints.json", agent["checkpoints"])
        if agent["role"] != "child":
            continue
        report = agent["report"] or (agent["checkpoints"][-1]["report"] if agent["checkpoints"] else {})
        searches += [{"agent_id": aid, **s} for s in report.get("search_log", [])]
        open_questions += report.get("unresolved_questions", [])
        for index, artifact in enumerate(report.get("verification_artifacts", [])):
            name = f"verification/{aid}-{index}.json"
            add(name, artifact)
            verification_index.append({"agent_id": aid, "path": name, "id": artifact["id"]})
    open_questions += task.synthesis.get("unresolved_questions", [])
    open_questions += [
        f"Unfinished ({item['state']}): {item['assignment'].get('question', 'assignment')}"
        for item in task.synthesis.get("unfinished_assignments", [])
    ]
    if not complete:
        open_questions.append(
            "Work not completed before this snapshot: " + task.ledger.get("stop_reason", status)
        )
    add("search_log.json", searches)
    add("verification/index.json", verification_index)
    add(
        "open_questions.md",
        "# Open questions\n\n" + "\n".join("- " + q for q in dict.fromkeys(open_questions)),
    )
    for name in task.contract["deliverables"]:
        body = task.synthesis.get("deliverables", {}).get(name)
        add(
            f"deliverables/{name}.md",
            "# UNREVIEWED RESEARCH DRAFT\n\n"
            + (body or f"Requested {name} was not completed. See the saved reports and open questions."),
        )
    if include_results_pdf:
        from .research_results import render_results

        rendered = render_results(data)
        files["results.pdf"] = rendered.data
        add("results-rendering.json", rendered.manifest())
    add(
        "package_manifest.json",
        {
            "format_version": 1,
            "status": status,
            "files": [
                {"file": name, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                for name, blob in sorted(files.items())
            ],
        },
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, blob in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, blob)
    return buffer.getvalue()
