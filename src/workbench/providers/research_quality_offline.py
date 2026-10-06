"""Explicit transport fixtures for manuscript operations; never scientific evidence."""


def reply(operation, message):
    if operation == "discover":
        return {
            "queries": [{"provider": "crossref", "query": "OFFLINE discovery round "
                         + str(message["discovery_round"]), "count": 2}],
            "rationale": "Controlled discovery protocol only.",
            "coverage_notes": ["Simulated search; no scientific coverage established."],
            "remaining_gaps": ["Live search and full-text review remain required."],
        }
    if operation in {"draft", "revise"}:
        return {
            "title": "OFFLINE manuscript protocol demonstration",
            "sections": [
                {
                    "id": "scope",
                    "heading": "Scope",
                    "text": "No model research performed.",
                    "claim_ids": ["scope"],
                }
            ],
            "claims": [
                {
                    "id": "scope",
                    "statement": "This is a transport demonstration.",
                    "kind": "method",
                    "source_ids": [],
                    "verification_ids": [],
                }
            ],
            "novelty_claim": False,
            "limitations": ["Offline simulation only."],
            "responses": [
                {
                    "comment_id": c["id"],
                    "response": "Controlled fixture response.",
                    "changes": "Retained the offline simulation scope.",
                }
                for c in message.get("prior_comments", [])
            ],
        }
    packet = message["packet"]
    return {
        **{k: packet[k] for k in ("role", "candidate_sha256", "packet_sha256")},
        "covered_section_ids": [s["id"] for s in packet["candidate"]["sections"]],
        "assessments": [
            {
                "claim_id": c["id"],
                "status": "supported_within_scope",
                "rationale": "Controlled transport assertion only.",
                "passages": [],
                "verification_ids": [],
            }
            for c in packet["candidate"]["claims"]
        ],
        "objections": [],
        "coverage_flags": [],
        "resolutions": [
            {
                "comment_id": c["id"],
                "criterion_met": True,
                "regression_passed": True,
                "evidence": "Controlled fixture only.",
                "disposition": "resolved",
            }
            for c in packet["prior_comments"]
        ],
        "contribution_comparison": "Offline demonstration; no scientific contribution.",
        "summary": "OFFLINE simulation: no specialist model review performed.",
        "evidence_assertions": [],
        "historical_corrections": [],
        "adversarial_checks": [
            {"criterion": criterion, "challenge": "Controlled transport challenge only.",
             "outcome": "passed_within_scope", "rationale": "No scientific verification performed.",
             "claim_ids": [c["id"] for c in packet["candidate"]["claims"]]}
            for criterion in ("proof_stress", "source_entailment", "novelty_limits",
                              "scope_overclaim", "reproducibility")
        ] if packet["role"] == "adversarial" else [],
    }
