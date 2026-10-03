"""Shared data-only role packets and validators; no provider, filesystem or billing access."""

import json
import re

from .evaluation import Denied, digest


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate output field")
        value[key] = item
    return value


def _text(value, maximum=30000):
    if type(value) is not str or not value.strip() or len(value.encode()) > maximum:
        raise Denied("role text denied")
    return value


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise Denied("role output shape denied")


def _records(value, maximum=50):
    if type(value) is not list or len(value) > maximum:
        raise Denied("role records denied")
    return value


def evidence_inventory(packet):
    """Source-linked inventory of text available inside this exact packet."""
    artifacts = []

    def add(path, kind, value):
        if type(value) is str:
            data = value.encode("utf-8")
            artifacts.append({"path": path, "kind": kind, "sha256": digest(data), "utf8_bytes": len(data)})

    for alias, value in packet.get("admitted_original_evidence", {}).items():
        pointer = alias.replace("~", "~0").replace("/", "~1")
        add(f"/admitted_original_evidence/{pointer}", "original", value)
    add("/candidate_tex", "candidate", packet.get("candidate_tex"))
    for key in ("author_reports", "author_history", "before_after_candidates",
                "workflow_reports", "earlier_workflow_reports"):
        for index, row in enumerate(packet.get(key, [])):
            kind = "review_report" if "workflow_reports" in key else "author_report"
            add(f"/{key}/{index}/report", kind, row.get("report"))
    if "feedback" in packet:
        add("/feedback/report", "review_report", packet["feedback"].get("report"))
    return artifacts


def bibliography_markers(source):
    """Locate incomplete bibliography wording without supplying missing metadata."""
    if type(source) is not str:
        return []
    match = re.search(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", source, re.S)
    if match is None:
        return []
    patterns = (r"bibliographic details? to be checked", r"\b(?:TODO|TBD|citation needed)\b")
    return [
        {"line": source.count("\n", 0, match.start() + hit.start()) + 1, "marker": hit.group()}
        for pattern in patterns
        for hit in re.finditer(pattern, match.group(), re.I)
    ]


_EVIDENCE_PATH = re.compile(
    r"/(?:admitted_original_evidence/[^/]+|candidate_tex|feedback/report|"
    r"(?:author_reports|author_history|before_after_candidates|workflow_reports|"
    r"earlier_workflow_reports)/\d+/report)"
)
_AMBIGUOUS_ABSENCE = re.compile(
    r"(?:\b(?:report|evidence|author_history)\b.{0,90}"
    r"\b(?:absent|missing|unavailable|omitted|not (?:included|provided|supplied|present|available))\b|"
    r"\b(?:no|zero)\b.{0,40}\b(?:reports?|author_history entries)\b|"
    r"\b(?:packet|evidence)\b.{0,50}\b(?:lacks?|contains? no|contained no)\b.{0,40}"
    r"\b(?:reports?|author_history)\b)",
    re.I | re.S,
)
_CORRECTION_CUE = re.compile(
    r"\b(?:incorrect|mistaken|misstated|corrected|withdrawn|was wrong|is wrong|"
    r"actually (?:available|present|included|supplied))\b",
    re.I,
)


def _packet_scope(packet, scope):
    if scope == "current":
        return packet.get("evidence_artifacts", [])
    if type(scope) is not str or not re.fullmatch(r"[0-9a-f]{64}", scope):
        raise Denied("evidence packet scope denied")
    matches = [
        row for row in packet.get("earlier_packet_manifests", [])
        if row.get("packet_sha256") == scope
    ]
    if len(matches) != 1:
        raise Denied("evidence packet scope denied")
    return matches[0].get("evidence_artifacts", [])


def _availability_rows(value, packet):
    assertions = value.pop("evidence_assertions", [])
    corrections = value.pop("historical_corrections", [])
    if type(assertions) is not list or len(assertions) > 50:
        raise Denied("evidence assertions denied")
    if type(corrections) is not list or len(corrections) > 50:
        raise Denied("historical corrections denied")
    normalized_assertions = []
    for row in assertions:
        _shape(row, {"packet_scope", "artifact_path", "availability", "artifact_sha256"})
        path, availability = row["artifact_path"], row["availability"]
        if type(path) is not str or _EVIDENCE_PATH.fullmatch(path) is None:
            raise Denied("evidence artifact path denied")
        if availability not in {"available", "unavailable"}:
            raise Denied("evidence availability denied")
        artifacts = _packet_scope(packet, row["packet_scope"])
        matches = [item for item in artifacts if item.get("path") == path]
        if availability == "available":
            if (
                len(matches) != 1
                or type(row["artifact_sha256"]) is not str
                or row["artifact_sha256"] != matches[0].get("sha256")
            ):
                raise Denied("evidence availability assertion contradicted by packet")
        elif matches or row["artifact_sha256"] is not None:
            raise Denied("evidence availability assertion contradicted by packet")
        normalized_assertions.append(row)

    manifests = packet.get("earlier_packet_manifests", [])
    normalized_corrections = []
    for row in corrections:
        _shape(
            row,
            {"source_role", "packet_sha256", "artifact_path", "corrected_availability", "reason"},
        )
        _text(row["reason"], 4000)
        matches = [
            manifest for manifest in manifests
            if manifest.get("role") == row["source_role"]
            and manifest.get("packet_sha256") == row["packet_sha256"]
        ]
        if len(matches) != 1:
            raise Denied("historical correction packet denied")
        assertion = {
            "packet_scope": row["packet_sha256"],
            "artifact_path": row["artifact_path"],
            "availability": row["corrected_availability"],
            "artifact_sha256": None,
        }
        artifacts = _packet_scope(packet, row["packet_sha256"])
        present = [item for item in artifacts if item.get("path") == row["artifact_path"]]
        if present:
            assertion["artifact_sha256"] = present[0].get("sha256")
        _availability_rows({"evidence_assertions": [assertion]}, packet)
        normalized_corrections.append(row)
    return normalized_assertions, normalized_corrections


def _ambiguous_flags(value, *, role, packet_scope="current", corrections=()):
    flags = []
    has_correction = bool(corrections)
    for field in ("report", "candidate_tex"):
        source = value.get(field, "")
        if type(source) is not str:
            continue
        for match in _AMBIGUOUS_ABSENCE.finditer(source):
            start, end = max(0, match.start() - 120), min(len(source), match.end() + 120)
            context = source[start:end]
            resolved = has_correction and _CORRECTION_CUE.search(context) is not None
            flags.append({
                "code": "ambiguous_evidence_availability_prose",
                "source_role": role,
                "packet_scope": packet_scope,
                "field": field,
                "excerpt": " ".join(match.group().split())[:240],
                "resolved": resolved,
            })
    return flags


def role_packet(*, inputs, expected, brief, prior, arm, role, packet_history=()):
    packet = {
        "role": role,
        "mechanism": "ordinary reports" if arm == "B0" else "structured verification",
        "neutral_brief": brief,
        "original_inputs": dict(expected),
    }
    authors = [p for p in prior if "candidate_tex" in p]
    if authors:
        packet["candidate_tex"] = authors[-1]["candidate_tex"]
        packet["candidate_sha256"] = authors[-1]["candidate_sha256"]
    # Reviewers receive author reports, but no other reviewer's report.
    if role in {"review1", "review2"}:
        # A one-generation reviewer cannot spend its sole call fetching evidence.
        # Both arms receive exactly the same originals, with no hidden enrichment.
        packet["admitted_original_evidence"] = {alias: data.decode("utf-8") for alias, data in inputs.items()}
        packet["author_reports"] = [
            {"role": p["role"], "candidate_sha256": p["candidate_sha256"], "report": p["report"]}
            for p in authors
        ]
    if role.startswith("revision"):
        packet["feedback"] = prior[-1]
        packet["author_history"] = [{k: v for k, v in p.items() if k != "candidate_tex"} for p in authors]
        packet["earlier_workflow_reports"] = [p for p in prior[:-1] if p["role"].startswith("review")]
        packet["earlier_packet_manifests"] = list(packet_history)
    if role == "final":
        packet.pop("candidate_tex", None)  # Current source already appears in the before/after set.
        packet["before_after_candidates"] = authors
        packet["workflow_reports"] = [p for p in prior if p["role"].startswith("review")]
        packet["earlier_packet_manifests"] = list(packet_history)
    if authors:
        packet["bibliography_completion_markers"] = bibliography_markers(authors[-1]["candidate_tex"])
    author = role in {"initial", "revision1", "revision2"}
    packet["final_text_contract"] = (
        {"report": "nonempty text", "candidate_tex": "complete UTF-8 source"}
        if author
        else {"report": "nonempty text"}
    )
    packet["output_limits"] = {
        "report_utf8_bytes_max": 30000,
        "candidate_utf8_bytes_max": 128000,
        "issues_per_review_max": 50,
        "revision_records_max": 50,
        "final_verdicts_max": 100,
        "required": "nonempty strings; exact keys; valid JSON; no duplicate fields",
    }
    if arm == "B1":
        if author:
            packet["final_text_contract"]["records"] = (
                "one per supplied feedback issue (empty for initial): issue_id, disposition "
                "(repaired/narrowed/disputed/unresolved), reason, before_location, after_location, "
                "regression_check"
            )
        elif role != "final":
            packet["final_text_contract"]["issues"] = (
                "list: id (R1-1 etc for review1, R2-1 etc for review2), objection, location, "
                "evidence_sha256 (nonempty list of supplied candidate/original input hashes)"
            )
        else:
            packet["final_text_contract"]["verdicts"] = (
                "one per workflow issue: issue_id, status (supported/unsupported/unresolved), "
                "reason, regression_check"
            )
    packet["evidence_artifacts"] = evidence_inventory(packet)
    if role in {"review1", "review2", "revision1", "revision2", "final"}:
        packet["evidence_intake_instruction"] = (
            "Use source-linked evidence_artifacts to check availability claims. "
            "Any availability claim intended to support release must use evidence_assertions "
            "with an exact artifact_path and packet_scope ('current' or a supplied historical "
            "packet SHA-256). Use historical_corrections to correct an earlier role's claim; "
            "unstructured availability prose is accepted only with a review flag. "
            "Revision/final roles must compare claims with earlier_packet_manifests. "
            "A supplied report does not authenticate its execution assertions. "
            "Report bibliography_completion_markers as unresolved until source-checked."
        )
    if role in {"revision1", "revision2", "final"}:
        packet["final_text_contract"]["evidence_assertions"] = (
            "optional list; each item has packet_scope, artifact_path, availability "
            "(available/unavailable), and artifact_sha256 (required for available, null otherwise)"
        )
        packet["final_text_contract"]["historical_corrections"] = (
            "optional list; each item has source_role, packet_sha256, artifact_path, "
            "corrected_availability, and reason"
        )
    return packet


def role_result(text, *, expected, prior, arm, role, packet=None, scientific_status="synthetic_not_assessed"):
    value = json.loads(text, object_pairs_hook=unique_object)
    author = role in {"initial", "revision1", "revision2"}
    keys = {"report", "candidate_tex"} if author else {"report"}
    extra = "records" if author else "verdicts" if role == "final" else "issues"
    if arm == "B1":
        keys.add(extra)
    evidence_fields = {"evidence_assertions", "historical_corrections"} & set(value)
    if set(value) - evidence_fields != keys:
        raise Denied("role output shape denied")
    _text(value["report"])
    assertions, corrections = [], []
    if packet is not None:
        if packet.get("evidence_artifacts") != evidence_inventory(packet):
            raise Denied("packet evidence inventory changed")
        assertions, corrections = _availability_rows(value, packet)
    elif evidence_fields:
        raise Denied("evidence assertions require a packet")
    authors = [p for p in prior if "candidate_tex" in p]
    before = authors[-1]["candidate_sha256"] if authors else expected["inputs/manuscript.tex"]
    if author:
        _text(value["candidate_tex"], 128000)
        value["candidate_sha256"] = digest(value["candidate_tex"].encode())
    if arm == "B1":
        rows = _records(value[extra], maximum=100 if role == "final" else 50)
        if extra == "issues":
            prefix = "R1-" if role == "review1" else "R2-"
            for i, row in enumerate(rows, 1):
                _shape(row, {"id", "objection", "location", "evidence_sha256"})
                if row["id"] != f"{prefix}{i}":
                    raise Denied("issue identity denied")
                _text(row["objection"])
                _text(row["location"])
                evidence = row["evidence_sha256"]
                if (
                    type(evidence) is not list
                    or not 1 <= len(evidence) <= 3
                    or any(type(h) is not str or h not in {*expected.values(), before} for h in evidence)
                ):
                    raise Denied("issue evidence identity denied")
        else:
            expected = (
                []
                if role == "initial"
                else [i["id"] for p in prior if "issues" in p for i in p["issues"]]
                if role == "final"
                else [i["id"] for i in prior[-1]["issues"]]
            )
            identifiers = []
            for row in rows:
                fields = {"issue_id", "reason", "regression_check"}
                fields |= (
                    {"status"} if role == "final" else {"disposition", "before_location", "after_location"}
                )
                _shape(row, fields)
                for key in fields:
                    _text(row[key])
                identifiers.append(row["issue_id"])
                if role == "final":
                    if row["status"] not in {"supported", "unsupported", "unresolved"}:
                        raise Denied("verification status denied")
                else:
                    if row["disposition"] not in {"repaired", "narrowed", "disputed", "unresolved"}:
                        raise Denied("issue disposition denied")
                    row.update(before_sha256=before, after_sha256=value["candidate_sha256"])
            if len(identifiers) != len(set(identifiers)) or set(identifiers) != set(expected):
                raise Denied("issue coverage denied")
    if author:
        value["bibliography_completion_markers"] = bibliography_markers(value["candidate_tex"])
    elif role == "final" and authors:
        value["bibliography_completion_markers"] = bibliography_markers(authors[-1]["candidate_tex"])
    else:
        value["bibliography_completion_markers"] = []

    review_flags = _ambiguous_flags(value, role=role, corrections=corrections)
    if packet is not None and role == "final":
        manifests = {row["role"]: row for row in packet.get("earlier_packet_manifests", [])}
        for earlier in authors:
            manifest = manifests.get(earlier["role"])
            if manifest is None:
                continue
            packet_sha = manifest["packet_sha256"]
            historical = _ambiguous_flags(
                earlier,
                role=earlier["role"],
                packet_scope=packet_sha,
            )
            corrected = any(
                row["source_role"] == earlier["role"] and row["packet_sha256"] == packet_sha
                for row in corrections
            )
            if corrected:
                for flag in historical:
                    flag["resolved"] = True
            review_flags.extend(historical)

    unresolved_flags = [flag for flag in review_flags if not flag["resolved"]]
    blockers = []
    if value["bibliography_completion_markers"]:
        blockers.append({
            "code": "unresolved_bibliography_placeholders",
            "count": len(value["bibliography_completion_markers"]),
        })
    if unresolved_flags:
        blockers.append({"code": "evidence_availability_review_required", "count": len(unresolved_flags)})
    if role == "final" and any(row.get("status") == "unresolved" for row in value.get("verdicts", [])):
        blockers.append({"code": "unresolved_final_verdicts", "count": sum(
            row.get("status") == "unresolved" for row in value["verdicts"]
        )})
    value["evidence_assertions"] = assertions
    value["historical_corrections"] = corrections
    value["review_flags"] = review_flags
    value["diagnostic_status"] = "accepted"
    value["release_eligibility"] = {"eligible": not blockers, "blockers": blockers}
    return {**value, "role": role, "scientific_status": scientific_status}
