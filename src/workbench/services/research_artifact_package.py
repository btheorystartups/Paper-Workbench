"""Private, versioned research handoffs; never publication approval or promotion."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ResearchObject, ResearchTask, stable_hash
from . import export_service, manuscript_path, math_typesetting, research, research_results, research_tasks
from .publication_packages import checksummed_zip


def _json(value) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=str).encode()


def _safe(value):
    if isinstance(value, str):
        return research_results.safe_text(value)
    if isinstance(value, dict):
        private_keys = {
            "instructions",
            "prompt",
            "prompts",
            "raw_events",
            "raw_event",
            "account_email",
            "local_path",
            "api_key",
            "password",
            "access_token",
            "secret",
        }
        return {
            research_results.safe_text(str(k)): _safe(v)
            for k, v in value.items()
            if str(k).lower() not in private_keys
        }
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _tex(text: str) -> str:
    return math_typesetting.latex_text(text, export_service._latex_escape)


def bundle(
    snapshots: list[dict],
    originals: dict[str, bytes],
    path: dict,
    version: int = 1,
    *,
    manuscript_records: list[dict] | None = None,
) -> bytes:
    """Build entirely in memory. Original task ZIPs remain byte-for-byte private."""
    if version < 1:
        raise ValueError("package version must be positive")
    ids = [str(s["id"]) for s in snapshots]
    if len(set(ids)) != len(ids) or set(ids) != set(originals):
        raise ValueError("each task snapshot requires one matching original ZIP")
    files: dict[str, bytes] = {}
    safe_path = _safe(path)
    files["path-to-manuscript.json"] = _json(safe_path)
    files["path-to-manuscript.md"] = manuscript_path.markdown(
        {
            "notice": "Advisory evidence assessment; no approval gates changed.",
            "publication_ready": False,
            **safe_path,
        }
    ).encode()
    files["manuscript/recorded-manuscripts.json"] = _json(_safe(manuscript_records or []))
    tasks, sources, citations, verification, reviews, boundaries = [], [], [], [], [], []
    renderer_records = {}
    for index, manuscript in enumerate(manuscript_records or [], 1):
        prefix = f"manuscript/recorded-{index:03d}"
        title = research_results.safe_text(manuscript["title"])
        content = [
            ("Export status", "Recorded manuscript snapshot; export confers no scientific or human approval.")
        ]
        content += [(s["title"], str(s["body"].get("text", ""))) for s in manuscript.get("sections", [])]
        content += [
            ("Claim " + c["id"] + " [support: " + c["support"] + "]", c["text"])
            for c in manuscript.get("claims", [])
        ]
        content += [
            ("Source " + s["id"], s["title"] + "; access: " + s["access"])
            for s in manuscript.get("sources", [])
        ]
        content = [(research_results.safe_text(h), research_results.safe_text(t)) for h, t in content]
        files[prefix + ".md"] = (
            "# " + title + "\n\n" + "\n\n".join("## " + h + "\n\n" + t for h, t in content)
        ).encode()
        files[prefix + ".tex"] = (
            "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T1]{fontenc}\n"
            "\\usepackage{amsmath,amssymb}\n\\begin{document}\n\\title{"
            + _tex(title)
            + "}\\author{}\\date{}\\maketitle\n"
            + "\n".join("\\section{" + _tex(h) + "}\n" + _tex(t) for h, t in content)
            + "\n\\end{document}\n"
        ).encode()
        result = research_results.render_sections(title, content)
        files[prefix + ".pdf"] = result.data
        renderer_records[prefix + ".pdf"] = {**result.manifest(), "latex_compiled": False}
    for index, snapshot in enumerate(snapshots, 1):
        task_id = str(snapshot["id"])
        # Generated filenames avoid trusting uploaded IDs as ZIP paths.
        prefix = f"tasks/task-{index:03d}"
        original_name = prefix + "/PRIVATE-original-research-task.zip"
        original = originals[task_id]
        files[original_name] = original
        rendered = research_results.render_results(snapshot)
        files[prefix + "/research-results.pdf"] = rendered.data
        renderer_records[prefix + "/research-results.pdf"] = rendered.manifest()
        tasks.append(
            {
                "task_id": task_id,
                "state": snapshot.get("state"),
                "original": original_name,
                "original_sha256": hashlib.sha256(original).hexdigest(),
                "original_is_private": True,
                "review_hash": snapshot.get("review_hash"),
            }
        )
        sources.append({"task_id": task_id, "sources": snapshot.get("sources", [])})
        reviews.append({"task_id": task_id, "reviews": snapshot.get("reviews", {})})
        files[prefix + "/synthesis.json"] = _json(_safe(snapshot.get("synthesis", {})))
        files[prefix + "/call-trace.json"] = _json(_safe(snapshot.get("ledger", {}).get("call_trace", [])))
        files[prefix + "/call-timing-summary.json"] = _json(
            _safe(snapshot.get("ledger", {}).get("trace_summary", {})))
        files[prefix + "/quality-assessment.json"] = _json(_safe(snapshot.get("quality")))
        files[prefix + "/readiness-report.json"] = _json(_safe(snapshot.get("readiness")))
        files[prefix + "/lineage-and-plans.json"] = _json(
            _safe(
                [
                    {k: agent.get(k) for k in ("id", "parent_id", "role", "state", "assignment")}
                    for agent in snapshot.get("agents", [])
                ]
            )
        )
        for agent in snapshot.get("agents", []):
            report = agent.get("report") or {}
            if not report and agent.get("checkpoints"):
                report = agent["checkpoints"][-1].get("report", {})
            aid = agent.get("id")
            citations.append({"task_id": task_id, "agent_id": aid, "citations": report.get("citations", [])})
            verification.append(
                {
                    "task_id": task_id,
                    "agent_id": aid,
                    "artifacts": report.get("verification_artifacts", []),
                    "proof_attempts": report.get("proof_attempts", []),
                    "failed_approaches": report.get("failed_approaches", []),
                }
            )
            for finding in report.get("findings", []):
                boundaries.append(
                    {
                        "task_id": task_id,
                        "agent_id": aid,
                        "finding": finding,
                        "application_certified": False,
                        "usage": "Unreviewed model assessment unless a current human review says otherwise; "
                        "export confers no approval.",
                    }
                )
    for name, data in (
        ("source-manifest", sources),
        ("citation-manifest", citations),
        ("verification-and-reproducibility", verification),
        ("review-decisions", reviews),
        ("claim-boundaries", boundaries),
    ):
        files[name + ".json"] = _json(_safe(data))
    outline = [
        (
            "Status and permitted use",
            "PROVISIONAL MANUSCRIPT OUTLINE — UNREVIEWED. "
            "This is a scaffold, not publication-ready prose. "
            "No proof, novelty, claim or submission approval is conferred.",
        ),
        (
            "Research question and scope",
            "\n\n".join(
                research_results.safe_text(
                    str(s.get("contract", {}).get("question", "Question not recorded."))
                )
                for s in snapshots
            )
            or "GAP: no research task is recorded.",
        ),
        (
            "Source coverage",
            "See source-manifest.json. GAP: establish full relevant source coverage, "
            "versions, and reliable locators.",
        ),
        (
            "Methods and finite checks",
            "See verification-and-reproducibility.json. GAP: independently reproduce checks and establish "
            "their exact limits. Saved task ZIPs retain source metadata and quoted evidence, not necessarily "
            "complete frozen source bytes; reacquire matching source hashes before reproduction.",
        ),
        (
            "Candidate results",
            "See task results PDFs and claim-boundaries.json. GAP: human assessment and claim/citation "
            "review before promoting findings into manuscript text.",
        ),
        (
            "Literature and novelty",
            "GAP: bounded search records do not establish novelty; "
            "complete literature review and record human assessment.",
        ),
        (
            "Discussion and limitations",
            "GAP: resolve scope conflicts, counterexamples, failed approaches "
            "and open questions in original reports.",
        ),
        (
            "Review and readiness",
            "See path-to-manuscript.json and review-decisions.json. GAP: skeptical review, authorship, "
            "declarations, venue checks and publication-package approval.",
        ),
    ]
    tex = (
        "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[T1]{fontenc}\n\\usepackage{amsmath,amssymb}\n\\begin{document}\n"
    )
    tex += "\\title{Provisional manuscript outline}\\author{}\\date{}\\maketitle\n"
    tex += "\n".join("\\section{" + _tex(title) + "}\n" + _tex(body) for title, body in outline)
    tex += "\n\\end{document}\n"
    files["manuscript/provisional-outline.tex"] = tex.encode()
    outline_pdf = research_results.render_sections("Provisional manuscript outline", outline)
    files["manuscript/provisional-outline.pdf"] = outline_pdf.data
    renderer_records["manuscript/provisional-outline.pdf"] = {
        **outline_pdf.manifest(),
        "latex_compiled": False,
        "note": "PDF and TeX share outline content; PDF uses the application renderer, not a TeX compiler.",
    }
    basis = stable_hash(
        {
            "snapshots": snapshots,
            "path": path,
            "manuscripts": manuscript_records or [],
            "originals": {k: hashlib.sha256(v).hexdigest() for k, v in originals.items()},
        }
    )
    files["history.json"] = _json(
        {
            "schema_version": 1,
            "package_version": version,
            "snapshot_version": basis,
            "events": [{"action": "export_unreviewed_snapshot", "approval_changed": False}],
            "previous_version": "not supplied",
        }
    )
    files["README_FIRST.md"] = (
        "# Research project artifact package\n\n"
        "PRIVATE ARCHIVE — DO NOT SHARE THE WHOLE ZIP. Original task ZIPs preserve provenance exactly "
        "and may contain private paths, prompts, account information or raw provider events. "
        "Only the separately sanitized research-results PDFs are intended for scientific review sharing.\n\n"
        "UNREVIEWED research handoff, not a publication-ready package. No human approval or scientific "
        "certification is implied. Completed execution does not establish proof or novelty. "
        "Partial tasks remain partial.\n\n"
        "Start with path-to-manuscript.md, then tasks/*/research-results.pdf. Read source-manifest.json, "
        "citation-manifest.json, verification-and-reproducibility.json, review-decisions.json "
        "and claim-boundaries.json. "
        "Original machine-readable reports, agent plans, provenance, synthesis and conflicts are preserved "
        "inside each PRIVATE-original-research-task.zip. "
        "The provisional manuscript outline marks evidence gaps.\n\n"
        "manuscript/recorded-manuscripts.json preserves any current manuscript bodies, sections and "
        "claim/source records. The provisional outline is a separate scaffold and does not replace them. "
        "No existing manuscript is automatically typeset or marked reviewed by this export.\n\n"
        "The outline PDF is generated from the same content as the TeX using the application renderer; "
        "it is not evidence of successful LaTeX compilation. Check package-manifest.json for file hashes and "
        "renderer details. history.json identifies this content-addressed snapshot; "
        "earlier exports are not overwritten.\n"
    ).encode()
    return checksummed_zip(
        files,
        {
            "format_version": 1,
            "package_version": version,
            "snapshot_version": basis,
            "kind": "research_project_artifacts",
            "review_state": "unreviewed",
            "shareable_archive": False,
            "external_submission_performed": False,
            "tasks": tasks,
            "renderers": renderer_records,
        },
    )


def project_bundle(session: Session, project_id: str) -> bytes:
    research._project(session, project_id)
    tasks = list(
        session.scalars(
            select(ResearchTask)
            .where(ResearchTask.project_id == project_id, ResearchTask.deleted_at.is_(None))
            .order_by(ResearchTask.created_at, ResearchTask.id)
        )
    )
    snapshots = [research_tasks.snapshot(session, task) for task in tasks]
    originals = {task.id: research_tasks.package(session, task, include_results_pdf=False) for task in tasks}
    manuscripts = []
    for obj in session.scalars(
        select(ResearchObject)
        .where(
            ResearchObject.project_id == project_id,
            ResearchObject.kind == "manuscript",
            ResearchObject.deleted_at.is_(None),
        )
        .order_by(ResearchObject.id)
    ):
        manuscript, sections, claims, sources = export_service._collect(session, obj.id)
        manuscripts.append(
            {
                "id": manuscript.id,
                "title": manuscript.title,
                "body": manuscript.body,
                "sections": [{"id": s.id, "title": s.title, "body": s.body} for s in sections],
                "claims": [
                    {"id": c.id, "text": c.text, "support": str(c.support), "notes": c.notes}
                    for c in claims.values()
                ],
                "sources": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "doi": s.doi,
                        "access": str(s.access),
                        "human_verified": s.human_verified,
                    }
                    for s in sources.values()
                ],
            }
        )
    return bundle(
        snapshots,
        originals,
        manuscript_path.build_project_path(session, project_id),
        manuscript_records=manuscripts,
    )
