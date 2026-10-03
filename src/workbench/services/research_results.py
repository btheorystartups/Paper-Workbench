"""Readable, data-only research snapshots. Never executes source text or changes reviews."""

import hashlib
import html
import io
import json
import re
import zipfile

from ..models import stable_hash
from . import export_service


def safe_text(value) -> str:
    """Defence in depth for free text; structured secrets are excluded by projection."""
    text = str(value)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email omitted]", text)
    text = re.sub(
        r"(?i)(?:[a-z]:[\\/]|\\\\[\w.-]+[\\/])[^\s<>\"']+", "[private path omitted]", text
    )
    text = re.sub(r"/(?:home|Users|tmp|var|mnt)/[^\s<>\"']+", "[private path omitted]", text)
    text = re.sub(r"(?i)(?:bearer\s+|sk-)[A-Za-z0-9_.-]+", "[credential omitted]", text)
    text = re.sub(
        r"(?i)\b(api[_ -]?key|password|access[_ -]?token|secret)\s*[:=]\s*\S+",
        r"\1=[credential omitted]",
        text,
    )
    # Credential-bearing URL queries/fragments are unnecessary for source identification.
    text = re.sub(r"(https?://[^\s?#]+)[?#][^\s]+", r"\1 [URL parameters omitted]", text)
    return text


def snapshot_from_package(payload: bytes) -> dict:
    """Read bounded JSON members in memory; verify the saved package before deriving output."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if len(infos) > 2000 or sum(i.file_size for i in infos) > 100_000_000:
            raise ValueError("research package exceeds export input limits")
        if len({i.filename for i in infos}) != len(infos):
            raise ValueError("duplicate package member")
        if archive.testzip() is not None:
            raise ValueError("research package CRC mismatch")
        manifest = json.loads(archive.read("package_manifest.json"))
        expected = {item["file"] for item in manifest["files"]}
        if expected != set(archive.namelist()) - {"package_manifest.json"}:
            raise ValueError("research package manifest coverage mismatch")
        for item in manifest["files"]:
            blob = archive.read(item["file"])
            if hashlib.sha256(blob).hexdigest() != item["sha256"]:
                raise ValueError("research package hash mismatch")
        data = json.loads(archive.read("task_settings.json"))
        data["sources"] = json.loads(archive.read("source_manifest.json"))
        data["synthesis"] = json.loads(archive.read("synthesis.json"))
        data["reviews"] = json.loads(archive.read("reviews.json"))
        data["agents"] = json.loads(archive.read("agent_lineage.json"))
        for agent in data["agents"]:
            aid = agent["id"]
            agent["report"] = json.loads(archive.read(f"agents/{aid}/report.json"))
            agent["checkpoints"] = json.loads(archive.read(f"agents/{aid}/checkpoints.json"))
        data["input_package_sha256"] = hashlib.sha256(payload).hexdigest()
        return data


def saved_report(agent: dict) -> tuple[dict, str]:
    if agent.get("report"):
        return agent["report"], "final report"
    checkpoints = agent.get("checkpoints", [])
    if checkpoints:
        return checkpoints[-1].get("report", {}), "last saved checkpoint (partial)"
    return {}, "no report saved"


def report_sections(data: dict) -> list[tuple[str, str]]:
    """Explicit allowlist: no contracts/instructions, raw events or full provenance dumps."""
    contract, synthesis = data.get("contract", {}), data.get("synthesis", {})
    sources, agents = data.get("sources", []), data.get("agents", [])
    sections = []

    def add(title, text):
        sections.append((safe_text(title), safe_text(text or "None recorded.")))

    add(
        "Status and safe use",
        "UNREVIEWED MODEL FINDINGS - NOT PUBLICATION READY\n"
        f"Task state: {data.get('state', 'unknown')}. Source count: {len(sources)}. "
        + ("NARROW ONE-SOURCE SCOPE. " if len(sources) == 1 else "")
        + ("OFFLINE SIMULATION: no live research. " if contract.get("executor") == "offline" else "")
        + "Completion describes workflow execution, not scientific validity. Model 'verified_result' "
        "and 'passed_within_scope' labels are unreviewed assessments, not human certification. "
        "This report does not promote claims or approve manuscript use.",
    )
    add("Research question", contract.get("question"))
    for a in agents:
        if a.get("role") == "child":
            add("Exact assigned scope - " + a["id"], a.get("assignment", {}).get("question"))
    add(
        "Source coverage",
        "\n\n".join(
            f"Source {s.get('source_id', s.get('id', '?'))}: {s.get('title', s.get('name', 'Untitled'))}\n"
            f"Version: {s.get('version', 'unspecified')}; access: {s.get('access', 'unspecified')}\n"
            f"SHA-256: {s.get('sha256', 'not recorded')}; extracted text SHA-256: "
            f"{s.get('full_extracted_sha256', 'not recorded')}\n"
            f"Context truncated: {s.get('context_truncated', False)}; "
            f"extraction confidence: {s.get('extraction_confidence', 'unspecified')}"
            for s in sources
        ),
    )
    add("Parent synthesis (unreviewed)", synthesis.get("summary", "No parent synthesis saved."))
    for field in ("agreements", "conflicts", "unresolved_questions"):
        add("Parent " + field.replace("_", " "), "\n\n".join(synthesis.get(field, [])))
    for group in synthesis.get("comparisons", []):
        add(
            "Deterministic comparison - " + group.get("claim_key", ""),
            group.get("state", "uncompared")
            + "\n"
            + "\n\n".join(
                f"{f.get('agent_id')}: {f.get('statement')}\nScope: {f.get('scope')}"
                for f in group.get("findings", [])
            ),
        )
    for agent in agents:
        if agent.get("role") != "child":
            continue
        report, status = saved_report(agent)
        aid = agent["id"]
        add(f"Agent {aid} - {status}", report.get("summary", "No saved findings; assignment is unfinished."))
        for f in report.get("findings", []):
            add(
                f"Finding {f['id']} - {f['category']} (model assessment)",
                f"{f['statement']}\n\nScope: {f['scope']}\nStance: {f.get('stance', 'unspecified')}\n"
                f"Citations: {', '.join(f.get('citation_ids', [])) or 'none'}\n"
                f"Checks: {', '.join(f.get('verification_ids', [])) or 'none'}",
            )
        for c in report.get("citations", []):
            add(
                f"Citation {c['id']} (agent {aid})",
                f"Source: {c.get('source_id') or c.get('url')}\n"
                f"Locator: {c.get('locator')}\nAccess: {c.get('access')}",
            )
        for v in report.get("verification_artifacts", []):
            add(
                f"Finite check {v['id']} - {v['outcome']} (reported, not rerun)",
                f"{v['description']}\n\n{v['content']}",
            )
        for field in ("proof_attempts", "failed_approaches", "unresolved_questions", "research_leads"):
            add(f"Agent {aid} - {field.replace('_', ' ')}", "\n\n".join(report.get(field, [])))
        for s in report.get("search_log", []):
            add(
                "Recorded search and coverage",
                "\n".join(
                    f"{key.replace('_', ' ').title()}: {s.get(key, 'unspecified')}"
                    for key in ("query", "location", "outcome", "coverage")
                ),
            )
    reviews = data.get("reviews", {})
    add(
        "Human review status",
        f"Recorded decisions: {len(reviews)}. "
        "Approval is purpose-specific and must match the current snapshot and original report hashes. "
        "No approval is inferred from this export.\n\n"
        + "\n\n".join(
            f"{key}: {r.get('decision')}; purpose {r.get('purpose')}; "
            f"snapshot current: {r.get('snapshot_hash') == data.get('review_hash')}; "
            f"note: {r.get('note', '')}"
            for key, r in reviews.items()
        ),
    )
    add(
        "Unfinished work",
        "\n\n".join(
            f"{a.get('state')}: {a.get('assignment', {}).get('question', 'assignment')}"
            for a in agents
            if a.get("state") != "completed"
        )
        + (
            "\nSnapshot is partial; only saved work is included. "
            + data.get("ledger", {}).get("stop_reason", "")
            if data.get("state") != "completed"
            else ""
        ),
    )
    add(
        "Lineage and reproducibility",
        f"Task ID: {data.get('id')}\n"
        f"Snapshot review hash: {data.get('review_hash', 'not recorded')}\n"
        f"Input ZIP SHA-256: {data.get('input_package_sha256', 'generated from saved project snapshot')}\n"
        "No model calls or verification code were executed during export. Original machine-readable "
        "reports and full provenance remain in the restricted evidence archive. Source manifests "
        "and quoted passages alone do not supply complete source text for independent reproduction.\n\n"
        + "\n\n".join(
            f"{a['role']} {a['id']}; parent {a.get('parent_id') or 'none'}; state {a.get('state')}; "
            f"report hash {stable_hash(a.get('report', {}))}"
            for a in agents
        ),
    )
    return sections


def render_sections(title: str, sections: list[tuple[str, str]], mode="auto"):
    title = safe_text(title)
    sections = [(safe_text(h), safe_text(t)) for h, t in sections]
    content = "".join(
        "<section><h2>"
        + html.escape(heading)
        + "</h2>"
        + "".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in text.split("\n\n"))
        + "</section>"
        for heading, text in sections
    )
    css = export_service._PUBLICATION_PDF_CSS + (
        "p {overflow-wrap:anywhere} h2 {font-size:12pt} body {font-size:10pt} section {break-inside:auto}"
    )
    document = (
        f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head>'
        f'<body><div class="title-block"><h1>{html.escape(title)}</h1>'
        "<p>Evidence handoff | Unreviewed research</p></div>" + content + "</body></html>"
    )
    paragraphs = [f"{heading}\n{text}" for heading, text in sections]
    return export_service._render_pdf(title, document, paragraphs, mode)


def render_results(snapshot: dict):
    return render_sections("Delegated research results", report_sections(snapshot))
