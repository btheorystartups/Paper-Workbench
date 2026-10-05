"""Read-only evidence inventory; execution completion never implies scientific approval.

The snapshot entry point also works on an exported task without importing its database.
All links point to read endpoints; this module never exports files or starts models.
"""

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Claim, ComputeRun, PublicationPackage, ResearchObject, ResearchTask, stable_hash
from ..vocab import ObjectKind
from . import audits, authoring, evidence_basis, publication_packages, research, research_tasks


def valid_reviews(task: dict) -> list[dict]:
    """Return only current, report-bound human approvals for existing findings."""
    if task.get("contract", {}).get("executor") == "offline":
        return []
    if task.get("state") not in research_tasks.TERMINAL or not task.get("review_hash"):
        return []
    agents = {a["id"]: a for a in task.get("agents", []) if a.get("role") == "child"}
    result = []
    for key, review in task.get("reviews", {}).items():
        parts = key.split(":")
        if len(parts) != 3:
            continue
        agent_id, finding_id, purpose = parts
        agent = agents.get(agent_id)
        if not agent:
            continue
        finding = next(
            (f for f in agent.get("report", {}).get("findings", []) if f.get("id") == finding_id), None
        )
        if not finding or purpose not in {"finding", "proof", "novelty", "manuscript"}:
            continue
        if purpose in {"proof", "novelty"} and finding.get("category") != "verified_result":
            continue
        if (
            review.get("decision") == "approved"
            and review.get("purpose") == purpose
            and review.get("snapshot_hash") == task["review_hash"]
            and review.get("report_hash") == stable_hash(agent.get("report", {}))
            and str(review.get("note", "")).strip()
            and str(review.get("reviewer", "")).strip()
        ):
            result.append({"agent_id": agent_id, "finding_id": finding_id, "purpose": purpose, **review})
    return result


def _stage(key, label, state, evidence, blockers, action):
    return {
        "id": key,
        "label": label,
        "state": state,
        "evidence": evidence,
        "blockers": blockers,
        "next_action": action,
    }


def build_path_from_snapshots(
    tasks: list[dict], manuscript_evidence: dict | None = None, *, project_id: str | None = None
) -> dict:
    """Aggregate all saved tasks and optional recorded authoring/package evidence.

    manuscript_evidence is collected by build_project_path; absent evidence remains
    missing. A PDF of results is not evidence of a typeset, reviewed manuscript.
    """
    recorded = manuscript_evidence or {}
    project_id = project_id or (tasks[0].get("project_id") if tasks else None)
    links = [
        {
            "label": f"Research task {t.get('id', '')} ({t.get('state', 'unknown')})",
            "url": f"/projects/{t.get('project_id')}/research-tasks/{t.get('id')}",
        }
        for t in tasks
    ]
    sources = [s for t in tasks for s in t.get("sources", [])]
    source_keys = {s.get("sha256") or s.get("source_id") or stable_hash(s) for s in sources}
    children = [a for t in tasks for a in t.get("agents", []) if a.get("role") == "child"]
    final_reports = [a["report"] for a in children if a.get("report")]
    checkpoints = [
        a["checkpoints"][-1]["report"]
        for a in children
        if not a.get("report") and a.get("checkpoints") and a["checkpoints"][-1].get("report")
    ]
    reports = final_reports + checkpoints
    report_links = [
        {
            "label": f"Agent {a['id']}: " + ("final report" if a.get("report") else "latest checkpoint"),
            "url": f"/projects/{t.get('project_id')}/research-tasks/{t.get('id')}",
        }
        for t in tasks
        for a in t.get("agents", [])
        if a.get("role") == "child" and (a.get("report") or a.get("checkpoints"))
    ]
    findings = [f for r in reports for f in r.get("findings", [])]
    citations = [c for r in reports for c in r.get("citations", [])]
    checks = [v for r in reports for v in r.get("verification_artifacts", [])]
    searches = [s for r in reports for s in r.get("search_log", [])]
    reviews = [r for t in tasks for r in valid_reviews(t)]
    conflicts = [c for t in tasks for c in t.get("synthesis", {}).get("conflicts", [])]
    conflicts.extend(
        c
        for t in tasks
        for c in t.get("synthesis", {}).get("comparisons", [])
        if c.get("state") == "conflict_or_scope_difference"
    )
    partial = any(t.get("state") != "completed" for t in tasks)
    simulated = any(t.get("contract", {}).get("executor") == "offline" for t in tasks)
    reviewed_findings = sum(
        len({(r["agent_id"], r["finding_id"]) for r in valid_reviews(t) if r["purpose"] == "manuscript"})
        for t in tasks
    )
    source_blockers = []
    if not sources:
        source_blockers.append("No frozen source coverage is recorded.")
    elif len(source_keys) == 1:
        source_blockers.append("Coverage is limited to one source; broader coverage is unverified.")
    stages = [
        _stage(
            "source_coverage",
            "Source coverage",
            "recorded" if sources else "missing",
            links,
            source_blockers,
            "Review source access, versions, locators and coverage gaps.",
        )
    ]
    stages.append(
        _stage(
            "independent_agent_work",
            "Independent agent work",
            "recorded" if reports else "missing",
            report_links,
            (["Some tasks are unfinished or partial; preserve available reports."] if partial else [])
            + (["Offline agents are simulations, not live independent research."] if simulated else []),
            "Inspect original child reports and parent/child lineage before planning more research.",
        )
    )
    proof_reviews = [r for r in reviews if r["purpose"] == "proof"]
    stages.append(
        _stage(
            "proof_checks",
            "Proof or counterexample checks",
            "needs_review" if checks else "missing",
            links,
            ([] if proof_reviews else ["No current hash-bound human proof review is recorded."])
            + (["Agent disagreements require resolution."] if conflicts else []),
            "Independently reproduce checks and review each proof or counterexample within its scope.",
        )
    )
    novelty_reviews = [r for r in reviews if r["purpose"] == "novelty"]
    stages.append(
        _stage(
            "literature_novelty",
            "Literature and novelty review",
            "recorded" if novelty_reviews else "needs_review" if searches else "missing",
            links,
            []
            if novelty_reviews
            else ["Search records do not establish novelty; human assessment is missing."],
            "Review literature coverage and record a bounded novelty decision.",
        )
    )
    claim_blockers = []
    if not findings or reviewed_findings < len(findings):
        claim_blockers.append("Not every finding has a current human manuscript-use approval.")
    if not recorded.get("claim_count"):
        claim_blockers.append("No claims are recorded in the project claim ledger.")
    stages.append(
        _stage(
            "claim_citation_review",
            "Claim/citation review",
            "recorded"
            if not claim_blockers
            else "needs_review"
            if findings or recorded.get("claim_count")
            else "missing",
            links + recorded.get("claim_links", []),
            claim_blockers,
            "Review exact statements, citations and locators; promote only approved bounded findings.",
        )
    )
    manuscripts = recorded.get("manuscripts", [])
    manuscript_links = [{"label": m["title"], "url": f"/manuscripts/{m['id']}/audit"} for m in manuscripts]
    sections = sum(m.get("section_count", 0) for m in manuscripts)
    stages.append(
        _stage(
            "manuscript_sections",
            "Manuscript outline and sections",
            "recorded" if sections else "missing",
            manuscript_links,
            [] if sections else ["No manuscript sections are recorded."],
            "Develop an argument outline with claim links and explicit gaps; review all provisional prose.",
        )
    )
    skeptical = recorded.get("skeptical_reviews", [])
    skeptical_resolved = bool(skeptical) and all(
        s.get("accepted_by_user")
        and s.get("body", {}).get("response")
        and s.get("body", {}).get("resolution") == "resolved"
        for s in skeptical
    )
    stages.append(
        _stage(
            "skeptical_review",
            "Skeptical review",
            "recorded" if skeptical_resolved else "needs_review" if skeptical else "missing",
            manuscript_links,
            []
            if skeptical_resolved
            else ["Skeptical objections require documented human responses."]
            if skeptical
            else ["No skeptical manuscript review is recorded."],
            "Assess objections, record responses, and re-audit the revised manuscript.",
        )
    )
    reproductions = [
        r
        for r in recorded.get("compute_runs", [])
        if r.get("state") == "succeeded"
        and r.get("review_state") == "verified"
        and r.get("review_note")
        and r.get("manifest_hash")
    ]
    stages.append(
        _stage(
            "reproducibility",
            "Reproducibility",
            "recorded" if reproductions else "needs_review" if checks else "missing",
            links
            + [
                {"label": "Human-reviewed compute run", "url": f"/compute-runs/{r['id']}"}
                for r in reproductions
            ],
            []
            if reproductions
            else ["Recorded finite checks are not human-reviewed reproductions or general proof."],
            "Reproduce verification artifacts with pinned inputs and record scope and outcomes.",
        )
    )
    builds = recorded.get("builds", [])
    pdf_builds = [b for b in builds + recorded.get("exports", []) if "pdf" in b.get("formats", [])]
    stages.append(
        _stage(
            "typesetting",
            "Typesetting",
            "recorded" if pdf_builds else "missing",
            [{"label": b.get("label", "Recorded publication bundle"), "url": b["url"]} for b in pdf_builds],
            [] if pdf_builds else ["No recorded manuscript PDF export or publication build is available."],
            "Export and visually inspect the manuscript PDF, references and equations.",
        )
    )
    packages = recorded.get("packages", [])
    approved = [
        p
        for p in packages
        if p.get("state") == "approved" and p.get("ready") and not p.get("stale") and p.get("build_count", 0)
    ]
    publication_ready = (
        bool(approved) and not claim_blockers and not partial and not simulated and not conflicts
    )
    active_packages = [p for p in packages if p.get("state") not in {"rejected", "superseded"}]
    blockers = [b["message"] for p in active_packages for b in p.get("blockers", [])] if not approved else []
    blockers.extend(b for stage in stages for b in stage["blockers"])
    audit_blockers = [
        f["message"]
        for m in manuscripts
        for f in m.get("audit_findings", [])
        if f.get("severity") in {"error", "blocker"}
    ]
    blockers.extend(audit_blockers)
    publication_ready = publication_ready and not blockers
    if not approved:
        blockers.append("No current approved, built publication package is recorded.")
    blockers.extend(claim_blockers)
    if partial or simulated or conflicts:
        blockers.append("Incomplete, simulated or conflicting research remains unresolved.")
    stages.append(
        _stage(
            "publication_readiness",
            "Publication readiness",
            "ready" if publication_ready else "blocked",
            [
                {"label": f"Package version {p['version']}", "url": f"/publication-packages/{p['id']}"}
                for p in packages
            ],
            list(dict.fromkeys(blockers)),
            "Resolve evidence, authorship and declarations; request human approval of a frozen version.",
        )
    )
    return {
        "project_id": project_id,
        "publication_ready": publication_ready,
        "publication_package_approved": bool(approved),
        "basis_hash": stable_hash({"tasks": tasks, "manuscript_evidence": recorded}),
        "counts": {
            "tasks": len(tasks),
            "sources": len(source_keys),
            "child_reports": len(final_reports),
            "checkpoint_reports": len(checkpoints),
            "findings": len(findings),
            "citations": len(citations),
            "verification_artifacts": len(checks),
            "valid_human_reviews": len(reviews),
            "manuscripts": len(manuscripts),
            "sections": sections,
        },
        "stages": stages,
        "notice": "Recorded progress is not scientific verification, novelty certification, "
        "or publication approval.",
    }


def build_path_from_snapshot(task_snapshot: dict, manuscript_evidence: dict | None = None) -> dict:
    return build_path_from_snapshots([task_snapshot], manuscript_evidence)


def _recorded_exports(manuscripts: list[dict]) -> list[dict]:
    """Read only bounded known export files, never arbitrary manifest paths or DBs."""
    root = (Path(get_settings().data_dir) / "exports").resolve()
    exports = []
    for manuscript in manuscripts:
        folder = (root / manuscript["id"]).resolve()
        if folder.parent != root:
            continue
        manifest_path, pdf = folder / "manifest.json", folder / "manuscript.pdf"
        try:
            if manifest_path.resolve().parent != folder or pdf.resolve().parent != folder:
                continue
            if manifest_path.stat().st_size > 4_000_000 or pdf.stat().st_size > 64_000_000:
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = manifest.get("files", {}).get("pdf", {})
            if (
                manifest.get("manuscript_id") == manuscript["id"]
                and entry.get("path") == "manuscript.pdf"
                and hashlib.sha256(pdf.read_bytes()).hexdigest() == entry.get("sha256")
            ):
                exports.append(
                    {
                        "formats": ["pdf"],
                        "label": "Checksummed manuscript export (recheck freshness)",
                        "url": f"/manuscripts/{manuscript['id']}/audit",
                    }
                )
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return exports


def build_project_path(session: Session, project_id: str, *, manuscript_id: str | None = None) -> dict:
    """Read existing records and local export receipts; never initialize databases or run models."""
    research._project(session, project_id)
    basis = None
    if manuscript_id:
        manuscript = session.get(ResearchObject, manuscript_id)
        if not manuscript or manuscript.project_id != project_id:
            raise research.IntegrityError("manuscript not found in project")
        basis = evidence_basis.collect(session, manuscript_id)

    def relevant(row):
        return basis is None or row.id in evidence_basis.ids(basis, type(row))
    tasks = [
        research_tasks.snapshot(session, t)
        for t in session.scalars(
            select(ResearchTask)
            .where(ResearchTask.project_id == project_id, ResearchTask.deleted_at.is_(None))
            .order_by(ResearchTask.id)
        ) if relevant(t)
    ]
    objects = list(
        session.scalars(
            select(ResearchObject).where(
                ResearchObject.project_id == project_id, ResearchObject.deleted_at.is_(None)
            )
        )
    )
    objects = [o for o in objects if relevant(o)]
    manuscripts = [
        {
            "id": m.id,
            "title": m.title,
            "section_count": len(authoring.manuscript_sections(session, m.id)),
            "audit_findings": audits.audit_manuscript(session, m.id),
        }
        for m in objects
        if m.kind == ObjectKind.MANUSCRIPT
    ]
    packages, builds = [], []
    for p in session.scalars(
        select(PublicationPackage).where(
            PublicationPackage.project_id == project_id, PublicationPackage.deleted_at.is_(None)
        )
    ):
        if manuscript_id and p.manuscript_id != manuscript_id:
            continue
        packages.append(
            {
                "id": p.id,
                "version": p.version,
                "state": p.state,
                "build_count": len(p.builds),
                **publication_packages.readiness(session, p.id),
            }
        )
        builds.extend(
            {"formats": p.included_formats, "url": f"/publication-packages/{p.id}/builds/{i}/download"}
            for i, _ in enumerate(p.builds)
        )
    claims = list(session.scalars(select(Claim).where(Claim.project_id == project_id)))
    claims = [c for c in claims if relevant(c)]
    recorded = {
        "manuscripts": manuscripts,
        "claim_count": len(claims),
        "claim_links": [{"label": "Project claim ledger", "url": f"/projects/{project_id}/claims"}],
        "skeptical_reviews": [
            {"id": o.id, "body": o.body, "accepted_by_user": o.accepted_by_user}
            for o in objects
            if o.kind == ObjectKind.NOTE
            and o.body.get("objection")
            and o.body.get("manuscript_id") in {m["id"] for m in manuscripts}
        ],
        "compute_runs": [
            {
                "id": r.id,
                "state": r.state,
                "review_state": r.review_state,
                "review_note": r.review_note,
                "manifest_hash": r.execution.get("manifest_hash"),
            }
            for r in session.scalars(
                select(ComputeRun).where(ComputeRun.project_id == project_id, ComputeRun.deleted_at.is_(None))
            ) if relevant(r)
        ],
        "packages": packages,
        "builds": builds,
        "exports": _recorded_exports(manuscripts),
    }
    result = build_path_from_snapshots(tasks, recorded, project_id=project_id)
    result["scope"] = "manuscript" if manuscript_id else "project_inventory"
    result["manuscript_id"] = manuscript_id
    if manuscript_id:
        from .manuscript_quality import assessment

        result["quality"] = assessment(session, manuscript_id)
        from .manuscript_readiness import report

        result["readiness"] = report(session, manuscript_id)
        if result["quality"]["required"]:
            result["stages"].append(_stage(
                "specialist_review", "Complete manuscript specialist review",
                "recorded" if result["quality"]["agent_checks_complete"] else "blocked", [],
                result["quality"]["blockers"], "Review the manuscript-specific specialist evidence."))
            if result["quality"]["blockers"]:
                result["publication_ready"] = False
    if manuscript_id is None:
        result["publication_ready"] = False
        result["notice"] += " Select a manuscript for manuscript-specific readiness."
    return result


def markdown(path: dict) -> str:
    lines = [
        "# Path to manuscript",
        "",
        path["notice"],
        "",
        "Publication ready: " + ("yes" if path["publication_ready"] else "no"),
        "",
    ]
    for stage in path["stages"]:
        lines.extend([f"## {stage['label']}: {stage['state']}", ""])
        lines.extend(f"- Blocker: {b}" for b in stage["blockers"])
        lines.extend(f"- Evidence: [{e['label']}]({e['url']})" for e in stage["evidence"])
        lines.extend(["", "Next action: " + stage["next_action"], ""])
    return "\n".join(lines)
