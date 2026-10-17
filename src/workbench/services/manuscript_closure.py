"""Versioned editorial closure contract and controller-owned decision gate."""

import difflib
import hashlib
import json

from pydantic import ValidationError
from sqlalchemy import select

from .. import storage
from ..models import ResearchAgent, stable_hash
from ..research_contract import ClosureReport
from . import manuscript_evidence_package, manuscript_integrity
from . import manuscript_quality as quality

POLICY = "editorial-closure-v1"
QUALITY_POLICY = "manuscript-quality-v3-editorial"
DIMENSIONS = frozenset({
    "terminology", "scope_and_purpose", "proof_and_dependency_closure",
    "source_and_attribution", "evidence_access", "reader_completeness", "presentation",
})
FINDING_BINDING = ("id", "category", "dimension", "affected_sections", "requirement_ids",
                   "problem", "acceptance_criterion", "evidence_paths")


def enabled(task):
    return task.contract.get("quality_policy") == QUALITY_POLICY


def scope_for(task):
    """Freeze obligations before a reviewer can propose additions."""
    requirements = {
        "genre": {"paper_type": task.contract["paper_type"]},
        "purpose": task.contract["success_criteria"],
        "task_instructions": task.contract.get("instructions", ""),
        "length": task.contract.get("manuscript_length"),
        "evidence": {"verification_routines": task.contract.get("verification_routines", []),
                     "compute_run_ids": task.contract.get("compute_run_ids", [])},
        "literature": {"required_comparisons": task.contract.get("required_literature_comparisons") or [],
                       "public_search_permitted": bool(task.contract.get("allow_public_search")),
                       "queries": task.contract.get("literature_queries", []),
                       "agent_discovery_requested": bool(task.contract.get("agent_literature_discovery"))},
    }
    return {"policy": POLICY, "reader": "reader of the declared paper type",
            "requirements": requirements,
            "presentation_delivery": {"primary_artifact": "manuscript.md",
                                      "pdf_preview_required": False},
            "optional_additions_selected": [], "not_applicable_dimensions": []}


def packet_for(task, campaign, candidate_sha256, reviewer_id, phase, *, specialist_records=(), session=None):
    candidate = campaign.body["drafts"][-1]["candidate"]
    scope = campaign.body.get("closure_scope") or scope_for(task)
    files = manuscript_evidence_package.files_for(task, campaign, session=session)
    manifest = manuscript_evidence_package.verify_files(files)
    preflight = (campaign.body.get("closure_reports") or [{}])[0]
    prior = preflight.get("report", {}).get("findings", [])
    preflight_candidate = next((d["candidate"] for d in campaign.body["drafts"]
        if d["candidate_sha256"] == preflight.get("candidate_sha256")), None)
    manuscript_text = quality.draft_text(candidate)
    scope_bytes = json.dumps(scope, indent=2, default=str).encode("utf-8")
    payload = {
        "policy": POLICY, "phase": phase, "reviewer_id": reviewer_id,
        "candidate": candidate, "candidate_sha256": candidate_sha256,
        "manuscript_text": manuscript_text,
        "scope": scope, "scope_sha256": stable_hash(scope),
        "evidence_manifest": manifest, "evidence_manifest_sha256": stable_hash(manifest),
        "evidence_files": {name: blob.decode("utf-8") for name, blob in files.items()
                           if name.endswith((".json", ".md", ".py"))}
        | {"editorial/scope.json": scope_bytes.decode("utf-8")},
        "prior_findings": prior if phase == "confirmation" else [],
        "repair_record": campaign.body.get("closure_repair"),
        "preflight_candidate_sha256": preflight.get("candidate_sha256"),
        "candidate_diff": "".join(difflib.unified_diff(
            quality.draft_text(preflight_candidate).splitlines(keepends=True)
            if preflight_candidate else [], manuscript_text.splitlines(keepends=True),
            fromfile="preflight", tofile="current")) if phase == "confirmation" else "",
        "specialist_records": list(specialist_records),
        "delivery_manifest": {
            "manuscript.md": hashlib.sha256(manuscript_text.encode("utf-8")).hexdigest(),
            "editorial/scope.json": hashlib.sha256(scope_bytes).hexdigest(),
            **{row["file"]: row["sha256"] for row in manifest["files"]},
            "evidence/manifest.json": hashlib.sha256(files["evidence/manifest.json"]).hexdigest(),
        },
    }
    return {**payload, "packet_sha256": stable_hash(payload)}


def evaluate(raw, packet, *, assigned_reviewer_id, reviewer_thread_id, writer_thread_ids,
             specialists_current=False, artifacts_verified=False, budget_exhausted=False):
    """Structural gate; truthful semantic judgments still require model evaluation."""
    def result(status, reasons):
        return {"status": status, "reasons": sorted(set(reasons)), "publication_approval": False}

    if raw is None:
        return result("limit_reached_partial" if budget_exhausted else "not_assessed",
                      ["closure report unavailable"])
    try:
        report = ClosureReport.model_validate(raw).model_dump()
    except ValidationError:
        return result("invalid_report", ["closure report schema invalid"])
    for field in ("candidate_sha256", "packet_sha256", "scope_sha256", "evidence_manifest_sha256"):
        if report[field] != packet[field]:
            return result("stale_report", [field + " differs from frozen packet"])
    errors = []
    if report["phase"] != packet["phase"] or report["policy"] != POLICY:
        errors.append("phase or policy differs from assignment")
    if (report["reviewer_id"] != assigned_reviewer_id
            or assigned_reviewer_id != packet["reviewer_id"]
            or not reviewer_thread_id or reviewer_thread_id in writer_thread_ids):
        errors.append("independent assigned reviewer identity required")
    section_ids = {s["id"] for s in packet["candidate"]["sections"]}
    requirement_ids = set(packet["scope"]["requirements"])
    if (set(report["reviewed_sections"]) != section_ids
            or len(report["reviewed_sections"]) != len(section_ids)):
        errors.append("exact section coverage required")
    if (set(report["reviewed_requirements"]) != requirement_ids
            or len(report["reviewed_requirements"]) != len(requirement_ids)):
        errors.append("exact requirement coverage required")
    if {c["dimension"] for c in report["checks"]} != DIMENSIONS:
        errors.append("all seven dimensions required")
    known_paths = set(packet["delivery_manifest"])
    for item in [*report["checks"], *report["findings"]]:
        if any(path.split("#", 1)[0] not in known_paths for path in item["evidence_paths"]):
            errors.append("finding cites an unavailable delivery member")
    for check in report["checks"]:
        if (check["outcome"] == "not_applicable"
                and check["dimension"] not in packet["scope"]["not_applicable_dimensions"]):
            errors.append("not-applicable dimension is outside frozen scope")
        if (check["outcome"] == "unresolved" and not any(
                f["category"] != "optional_improvement"
                and f["disposition"] in {"open", "deferred"}
                for f in report["findings"])):
            errors.append("unresolved report needs an actionable required finding")
    prior = {f["id"]: f for f in packet["prior_findings"]}
    findings = {f["id"]: f for f in report["findings"]}
    if len(findings) != len(report["findings"]) or not set(prior) <= set(findings):
        errors.append("finding IDs are duplicate or missing")
    for finding in report["findings"]:
        if not set(finding["affected_sections"]) <= section_ids:
            errors.append("finding references unknown section")
        if not set(finding["requirement_ids"]) <= requirement_ids:
            errors.append("finding references unknown requirement")
        if finding["category"] == "required_completion" and not finding["requirement_ids"]:
            errors.append("required completion lacks frozen requirement")
        old = prior.get(finding["id"])
        if old and any(finding[key] != old[key] for key in FINDING_BINDING):
            errors.append("prior finding substance changed")
        if not old and finding["disposition"] in {"resolved", "justified_rejection"}:
            errors.append("new finding cannot self-resolve")
        if (old and old["category"] != "optional_improvement"
                and finding["disposition"] == "justified_rejection"):
            errors.append("prior required finding needs a recorded repair, not unilateral rejection")
        if (old and old["category"] != "optional_improvement"
                and finding["disposition"] == "resolved"
                and (packet["candidate_sha256"] == packet["preflight_candidate_sha256"]
                     or not packet.get("repair_record")
                     or packet["repair_record"].get("candidate_sha256") != packet["candidate_sha256"]
                     or finding["id"] not in packet["repair_record"].get("finding_ids", []))):
            errors.append("required finding has no recorded repair on this candidate")
    if errors:
        return result("invalid_report", errors)
    blockers = [c["dimension"] for c in report["checks"] if c["outcome"] == "unresolved"]
    if manuscript_integrity.candidate_issues(packet["candidate"]):
        blockers.append("candidate has suspected escaping damage")
    blockers.extend(f["id"] for f in report["findings"]
                    if f["category"] != "optional_improvement" and f["disposition"] in {"open", "deferred"})
    if packet["phase"] == "confirmation":
        if not specialists_current:
            blockers.append("current specialist acceptance unavailable")
        if not artifacts_verified:
            blockers.append("delivery artifact verification unavailable")
    if blockers:
        return result("limit_reached_partial" if budget_exhausted else "needs_revision", blockers)
    if packet["phase"] == "preflight":
        return result("preflight_complete", [])
    advisory = any(f["category"] == "optional_improvement"
                   and f["disposition"] in {"open", "deferred"} for f in report["findings"])
    return result("ready_for_human_review_with_advisories" if advisory
                  else "ready_for_human_review", [])


def display(record):
    if not record:
        return {"status": "not_assessed", "dimensions": [], "findings": [],
                "rendered_preview": "not_assessed"}
    report = record.get("report") or {}
    return {"status": record.get("status", "not_assessed"),
            "rendered_preview": "not_assessed",
            "candidate_sha256": record.get("candidate_sha256"),
            "dimensions": [{"dimension": c["dimension"], "status": c["outcome"],
                            "reason": c["rationale"], "evidence_paths": c["evidence_paths"]}
                           for c in report.get("checks", [])],
            "findings": report.get("findings", []), "reasons": record.get("reasons", [])}


def current_status(session, task, campaign, candidate_sha256, specialists_current):
    """Recompute a saved confirmation from current authenticated records and payload bytes."""
    records = campaign.body.get("closure_reports", [])
    calls = campaign.body.get("closure_calls", [])
    if not records:
        return display(None)
    if (len(records) != 2 or len(calls) != 2
            or [r.get("phase") for r in records] != ["preflight", "confirmation"]
            or [r.get("phase") for r in calls] != ["preflight", "confirmation"]):
        return {"status": "invalid_report", "dimensions": [], "findings": [],
                "reasons": ["two distinct closure calls and reports are required"]}
    for record, call in zip(records, calls, strict=True):
        agent = session.get(ResearchAgent, record.get("agent_id"))
        if (not agent or agent.deleted_at or agent.task_id != task.id
                or agent.assignment.get("role") != "editorial_closure"
                or agent.assignment.get("phase") != record["phase"]
                or agent.assignment.get("packet_sha256") != record.get("packet_sha256")
                or call.get("agent_id") != agent.id
                or call.get("packet_sha256") != record.get("packet_sha256")
                or stable_hash(record.get("report")) != record.get("report_sha256")
                or stable_hash(agent.report) != record.get("report_sha256")):
            return {"status": "invalid_report", "dimensions": [], "findings": [],
                    "reasons": ["closure assignment or saved report changed"]}
        requested = agent.provenance.get("requested_model_policy")
        model = agent.provenance.get("closure_report_model", {})
        if requested and (requested.get("role") != "editorial_closure" or any(
                requested.get(key) != model.get(key) for key in ("model", "reasoning_effort"))):
            return {"status": "invalid_report", "dimensions": [], "findings": [],
                    "reasons": ["closure reviewer model policy changed"]}
    record = records[-1]
    if record["candidate_sha256"] != candidate_sha256:
        return {"status": "stale_report", "dimensions": [], "findings": [],
                "reasons": ["closure candidate changed"]}
    try:
        specialists = [{"agent_id": r["agent_id"], "role": r["role"],
                        "candidate_sha256": r["candidate_sha256"],
                        "report_sha256": r["report_sha256"], "blockers": r["blockers"]}
                       for r in campaign.body["reports"][-4:]]
        packet = packet_for(task, campaign, candidate_sha256, record["agent_id"],
                            "confirmation", specialist_records=specialists, session=session)
    except (KeyError, ValueError, OSError, UnicodeError, storage.ArtifactStorageError):
        return {"status": "stale_report", "dimensions": [], "findings": [],
                "reasons": ["closure delivery evidence is unavailable"]}
    if packet["packet_sha256"] != record["packet_sha256"]:
        return {"status": "stale_report", "dimensions": [], "findings": [],
                "reasons": ["closure packet changed"]}
    agent = session.get(ResearchAgent, record["agent_id"])
    reviewer_thread = (agent.provenance.get("closure_report_model", {}).get("codex_thread_id")
                       if task.contract["executor"] != "offline" else agent.id)
    authors = [session.get(ResearchAgent, d["author_id"]) for d in campaign.body["drafts"]]
    forbidden = set().union(*(quality.author_model_threads(a) for a in authors if a))
    forbidden.update(a.provenance.get("specialist_report_model", {}).get("codex_thread_id")
                     for a in session.scalars(select(ResearchAgent).where(ResearchAgent.task_id == task.id))
                     if a.id != agent.id)
    index = json.loads(packet["evidence_files"]["evidence/verification/index.json"])
    decision = evaluate(record["report"], packet, assigned_reviewer_id=agent.id,
        reviewer_thread_id=reviewer_thread, writer_thread_ids=forbidden,
        specialists_current=specialists_current,
        artifacts_verified=all(row.get("status") == "available" for row in index))
    if decision["status"] != record["status"]:
        return {"status": "stale_report", "dimensions": [], "findings": [],
                "reasons": ["closure decision differs from current controller state"]}
    return display(record)
