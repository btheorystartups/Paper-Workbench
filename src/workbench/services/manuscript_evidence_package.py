"""Portable, checksummed manuscript-campaign evidence; never executes retained code."""

import hashlib
import json
import re

from .. import storage
from ..models import ResearchAgent, stable_hash
from . import manuscript_integrity, manuscript_literature


def _json(value):
    return (json.dumps(value, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def _safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("evidence receipt has an unsafe identifier")
    return value


def files_for(task, campaign, *, session=None):
    """Return only authenticated, bounded members for the current campaign."""
    receipts = campaign.body.get("verification_receipts", [])
    searches = campaign.body.get("search_receipts", [])
    sources = [{k: v for k, v in source.items() if k not in {"artifact", "extracted_artifact"}}
               for source in task.sources if source.get("source_id")]
    files = {
        "evidence/source-passages.json": _json(sources),
        "evidence/search-receipts.json": _json(searches),
        "evidence/verification-receipts.json": _json(receipts),
    }
    records = []
    for saved in campaign.body.get("reports", []):
        record = dict(saved)
        if session is not None:
            agent = session.get(ResearchAgent, record["agent_id"])
            if not agent or agent.deleted_at or agent.task_id != task.id:
                raise ValueError("retained specialist identity is unavailable")
            if stable_hash(agent.report) != record.get("report_sha256"):
                raise ValueError("retained specialist report differs from its accepted hash")
            record["report"] = agent.report
        records.append(record)
        if "report" in record and stable_hash(record["report"]) != record.get("report_sha256"):
            raise ValueError("retained specialist report differs from its accepted hash")
    latest = campaign.body.get("drafts", [])[-1] if campaign.body.get("drafts") else {}
    files["evidence/literature-coverage.json"] = _json(manuscript_literature.coverage_status(
        task.contract, sources, searches, candidate=latest.get("candidate"),
        reports=records, candidate_sha256=latest.get("candidate_sha256")))
    if latest:
        files["evidence/escaping-integrity.json"] = _json(manuscript_integrity.report(latest["candidate"]))
    index = []
    seen = set()
    for receipt in receipts:
        identifier = _safe_id(receipt.get("id"))
        if identifier in seen:
            raise ValueError("duplicate verification receipt identifier")
        seen.add(identifier)
        reproduction = receipt.get("reproduction") or {}
        ref = reproduction.get("implementation_artifact")
        if not ref:
            index.append({"id": identifier, "status": "implementation_unavailable",
                          "scope": receipt.get("scope")})
            continue
        implementation = storage.read_bytes(ref)
        digest = hashlib.sha256(implementation).hexdigest()
        if (digest != receipt.get("implementation_sha256")
                or digest != ref.get("sha256")
                or implementation.decode("utf-8") != reproduction.get("implementation_text")):
            raise ValueError("retained verification implementation differs from receipt")
        script = f"evidence/verification/{identifier}.py"
        expected = f"evidence/verification/{identifier}-expected.json"
        files[script] = implementation
        output = reproduction.get("expected_output")
        if isinstance(output, dict):
            files[expected] = _json(output)
        index.append({"id": identifier,
                      "status": "available" if isinstance(output, dict) else "expected_output_unavailable",
                      "script": script, "expected_output": expected if isinstance(output, dict) else None,
                      "sha256": digest, "scope": receipt.get("scope")})
    files["evidence/verification/index.json"] = _json(index)
    files["evidence/README.md"] = (
        "# Manuscript evidence\n\n"
        f"Retained source passages: {len(sources)}; search receipts: {len(searches)}; "
        f"verification receipts: {len(receipts)}; verifier implementations: "
        f"{sum('script' in row for row in index)}. "
        + ("Verifier files are supplied for inspection and optional reproduction. "
           if any('script' in row for row in index) else "No verifier implementation is supplied. ")
        + "Package generation never executes retained code. Compare deterministic output with "
        "an expected JSON file when supplied. Historical storage paths in receipts are provenance, "
        "not required reproduction inputs. Finite checks do not replace proofs or review. "
        "literature-coverage.json distinguishes search permission, requests, receipts, primary "
        "passage availability and required comparisons. escaping-integrity.json, when present, "
        "records heuristic diagnostics without repairing manuscript text.\n"
    ).encode("utf-8")
    files["evidence/specialist-records.json"] = _json([
        {**{key: record[key] for key in (
            "agent_id", "role", "iteration", "candidate_sha256", "report_sha256", "blockers", "report"
        ) if key in record}, "packet_sha256": record.get("packet", {}).get("packet_sha256"),
         "report_content_available": "report" in record}
        for record in records
    ])
    manifest = [{"file": name, "bytes": len(blob),
                 "sha256": hashlib.sha256(blob).hexdigest()}
                for name, blob in sorted(files.items())]
    files["evidence/manifest.json"] = _json({"format": "manuscript-evidence-v1", "files": manifest})
    return files


def verify_files(files):
    manifest = json.loads(files["evidence/manifest.json"])
    names = [row["file"] for row in manifest["files"]]
    if len(names) != len(set(names)) or set(names) != set(files) - {"evidence/manifest.json"}:
        raise ValueError("manuscript evidence manifest coverage mismatch")
    for row in manifest["files"]:
        name = row["file"]
        if (not name.startswith("evidence/") or ".." in name.split("/")
                or row["bytes"] != len(files[name])
                or row["sha256"] != hashlib.sha256(files[name]).hexdigest()):
            raise ValueError("manuscript evidence member differs from manifest")
    return manifest
