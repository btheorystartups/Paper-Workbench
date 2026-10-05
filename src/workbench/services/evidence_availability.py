"""Packet-specific evidence availability and historical correction checks; data only."""

import re

from .evaluation import Denied, digest


def _text(value, maximum=30000):
    if type(value) is not str or not value.strip() or len(value.encode()) > maximum:
        raise Denied("role text denied")
    return value


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise Denied("role output shape denied")


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
    add("/task_specification", "task_specification", packet.get("task_specification"))
    # Structured manuscripts carry complete section text once, without a second
    # rendered copy. Keep the legacy evaluation-packet path above unchanged.
    for index, section in enumerate(packet.get("candidate", {}).get("sections", [])):
        add(f"/candidate/sections/{index}/text", "candidate", section.get("text"))
    for key in (
        "author_reports",
        "author_history",
        "before_after_candidates",
        "workflow_reports",
        "earlier_workflow_reports",
    ):
        for index, row in enumerate(packet.get(key, [])):
            kind = "review_report" if "workflow_reports" in key else "author_report"
            add(f"/{key}/{index}/report", kind, row.get("report"))
    if "feedback" in packet:
        add("/feedback/report", "review_report", packet["feedback"].get("report"))
    for index, receipt in enumerate(packet.get("verification_receipts", [])):
        add(f"/verification_receipts/{index}/reproduction/implementation_text",
            "reviewed_verifier", receipt.get("reproduction", {}).get("implementation_text"))
    return artifacts


_EVIDENCE_PATH = re.compile(
    r"/(?:admitted_original_evidence/[^/]+|candidate_tex|task_specification|"
    r"candidate/sections/\d+/text|feedback/report|"
    r"verification_receipts/\d+/reproduction/implementation_text|"
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
    matches = [row for row in packet.get("earlier_packet_manifests", []) if row.get("packet_sha256") == scope]
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
            manifest
            for manifest in manifests
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
            flags.append(
                {
                    "code": "ambiguous_evidence_availability_prose",
                    "source_role": role,
                    "packet_scope": packet_scope,
                    "field": field,
                    "excerpt": " ".join(match.group().split())[:240],
                    "resolved": resolved,
                }
            )
    return flags
