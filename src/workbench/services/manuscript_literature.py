"""Bounded coverage status and required comparison checks; no acquisition side effects."""

from collections import Counter

from ..models import stable_hash

PRIMARY_ACCESS = frozenset({"excerpt_available", "full_text_authorized", "full_text_user_supplied"})


def primary_passage_available(source):
    return (source.get("access") in PRIMARY_ACCESS and bool(source.get("text", "").strip())
            and not source.get("context_truncated"))


def _matched_primary_passage(passage, sources):
    source = sources.get(passage["source_id"])
    return (source is not None and primary_passage_available(source)
            and bool(passage["quotation"].strip())
            and " ".join(passage["quotation"].split()) in " ".join(source["text"].split()))


def comparison_checks(report, packet):
    """Return structural issues and unmet obligations without judging scientific entailment."""
    required = packet.get("task_requirements", {}).get("required_literature_comparisons") or []
    rows = report.get("literature_comparisons", [])
    issues, blockers = [], []
    if report["role"] != "literature_contribution":
        if rows:
            issues.append({"code": "literature_comparisons", "path": "/literature_comparisons",
                           "message": "Only the literature/contribution reviewer supplies comparisons."})
        return issues, blockers
    labels = [row["requirement"] for row in rows]
    if len(labels) != len(set(labels)) or set(labels) != set(required):
        issues.append({"code": "literature_comparisons", "path": "/literature_comparisons",
                       "message": "Assess each required_literature_comparisons entry exactly once, "
                       "using its exact text, even without a novelty claim. Return unresolved when "
                       "the frozen sources cannot support a comparison.", "required": required})
    sources = {s["source_id"]: {**s, "text": packet["admitted_original_evidence"].get(s["source_id"], "")}
               for s in packet["source_manifest"]}
    for index, row in enumerate(rows):
        if row["status"] == "unresolved":
            blockers.append("required literature comparison unresolved: " + row["requirement"])
        if row["status"] == "supported_within_scope" and not row["passages"]:
            blockers.append("required literature comparison lacks primary passages: " + row["requirement"])
        for pindex, passage in enumerate(row["passages"]):
            source = sources.get(passage["source_id"])
            path = f"/literature_comparisons/{index}/passages/{pindex}"
            if (source is None
                    or " ".join(passage["quotation"].split())
                    not in " ".join(source["text"].split())):
                issues.append({"code": "comparison_passage", "path": path,
                               "message": "Comparison quotation must occur in the named frozen source."})
            elif not primary_passage_available(source):
                blockers.append("required comparison has only limited source access: " + row["requirement"])
    return issues, blockers


def coverage_status(contract, sources, searches, *, candidate=None, reports=(), candidate_sha256=None):
    """Report receipt facts separately from source availability and reviewer assertions."""
    required = contract.get("required_literature_comparisons") or []
    queries = contract.get("literature_queries") or []
    discovery = bool(contract.get("agent_literature_discovery"))
    counts = dict(sorted(Counter(r.get("status", "unknown") for r in searches).items()))
    requested = bool(queries or discovery)
    current = [r for r in reports if candidate_sha256 and r.get("candidate_sha256") == candidate_sha256
               and r.get("report") and stable_hash(r["report"]) == r.get("report_sha256")]
    literature = [r for r in current if r.get("role") == "literature_contribution"]
    comparisons = literature[-1]["report"].get("literature_comparisons", []) if literature else []
    source_map = {s["source_id"]: s for s in sources if s.get("source_id")}
    cited_primary = {p["source_id"] for record in current
                     for row in [*record["report"].get("assessments", []),
                                 *record["report"].get("literature_comparisons", [])]
                     for p in row.get("passages", []) if _matched_primary_passage(p, source_map)}
    reviewed = {row["requirement"]: row for row in comparisons}
    obligations = []
    for item in required:
        row = reviewed.get(item, {})
        passages = row.get("passages", [])
        reported = row.get("status", "not_assessed")
        supported = bool(passages) and all(_matched_primary_passage(p, source_map) for p in passages)
        obligations.append({
            "requirement": item,
            "reviewer_reported_status": reported,
            "status": ("unresolved" if reported == "supported_within_scope" and not supported
                       else reported),
            "passages": passages,
        })
    gaps = []
    if not requested and not searches:
        gaps.append("Public search was not requested; permission alone does not execute a search.")
    if requested and not searches:
        gaps.append("Requested search has no execution receipt.")
    if any(r.get("status") != "completed" for r in searches):
        gaps.append("Some search receipts are incomplete, failed or simulated.")
    if any(row["status"] != "supported_within_scope" for row in obligations):
        gaps.append("Required literature comparisons remain unassessed or unresolved.")
    if contract.get("paper_type") == "research" and candidate and not candidate.get("novelty_claim"):
        gaps.append("Research purpose with no novelty claim: reviewer must assess the declared contribution "
                    "and required scope; do not infer or impose originality.")
    frozen = [s for s in sources if s.get("source_id")]
    return {
        "policy": "manuscript-literature-coverage-v1",
        "paper_type": contract.get("paper_type"),
        "public_search_permitted": bool(contract.get("allow_public_search")),
        "search_requested": requested,
        "explicit_query_count": len(queries),
        "agent_discovery_requested": discovery,
        "receipt_status_counts": counts,
        "completed_search_count": counts.get("completed", 0),
        "discovered_source_ids": sorted({
            r["source_id"] for receipt in searches for r in receipt.get("results", [])
            if r.get("source_id")
        }),
        "frozen_sources": [{
            "source_id": s["source_id"],
            "access": s.get("access", "not_established"),
            "primary_passage_available": primary_passage_available(s),
            "inspection_status": (
                "primary_passage_cited_in_current_review"
                if s["source_id"] in cited_primary else "not_recorded"
            ),
            "authors": s.get("authors") or [],
            "byline_status": (
                "metadata_recorded_not_verified" if s.get("authors") else "not_established"
            ),
            "publication_status": s.get("publication_status") or "not_established",
        } for s in frozen],
        "required_comparisons": obligations,
        "current_literature_report_available": bool(literature),
        "gaps": gaps,
        "notice": (
            "Search results and metadata are discovery leads. Available primary text is not proof that "
            "it was inspected. Comparison passages are reviewer assertions, not a deterministic "
            "entailment or priority check. Empty searches never establish novelty."
        ),
    }
