"""Shared data-only role packets and validators; no provider, filesystem or billing access."""

import json

from .bibliography import bibliography_markers as bibliography_markers
from .evaluation import Denied, digest
from .evidence_availability import _ambiguous_flags, _availability_rows, evidence_inventory


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
