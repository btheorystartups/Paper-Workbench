"""Controlled production protocol peer. Never calls a model or external network."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "workbench" / "providers"))
from research_quality_offline import reply


def emit(aid, kind, **payload):
    print(json.dumps({"agent_id": aid, "type": kind, **payload}), flush=True)


for line in sys.stdin:
    m = json.loads(line)
    aid, op = m["agent_id"], m["op"]
    if op == "hello":
        emit(
            aid,
            "capabilities",
            worker_pid=os.getpid(),
            capabilities={
                "protocol": "research-process-v1",
                "executor": "controlled-manuscript-test",
                "simulated": False,
                "child_agents": True,
                "structured_reports": True,
                "hard_total_token_limit": True,
                "bounded_wall_time": True,
                "no_external_writes": True,
            },
        )
        continue
    provenance = {
        "codex_thread_id": "controlled-" + ("shared" if "shared" in sys.argv else aid),
        "codex_turn_id": op + aid,
        "account_email": "controlled@example.invalid",
        "model": "controlled-test-only",
    }
    emit(aid, "turn_started", provenance=provenance)
    if op == "discover":
        result = reply(op, m)
    elif op == "integrate":
        result = {
            "summary": "Controlled handoff",
            "report_ids": list(m["reports"]),
            "agreements": [],
            "conflicts": [],
            "unresolved_questions": [],
            "deliverables": {"research_report": "Controlled fixture."},
        }
    else:
        result = reply(op, m)
        if op in {"draft", "revise"} and "scope_inventory" in sys.argv:
            result["sections"][0]["text"] = (
                "The refinement equivalence holds for finite nonempty carriers. "
                "Finiteness is unnecessary for the separating-function proof.")
            result["claims"][0].update(kind="theorem", statement=(
                "The refinement equivalence holds for arbitrary nonempty carriers."
                if op == "revise" else "The refinement equivalence holds for finite nonempty carriers."))
        if op in {"draft", "revise"} and any(flag in sys.argv for flag in (
                "length_response_contract", "author_response_contract")):
            assert m["expected_response_ids"] == sorted(c["id"] for c in m["prior_comments"])
        if op in {"draft", "revise"} and "length_response_contract" in sys.argv:
            if m.get("draft_corrections"):
                assert m["expected_response_ids"] == []
                assert m["draft_corrections"][0]["code"] == "manuscript_length"
                result["sections"][0]["text"] = " ".join(["word"] * 1045)
            elif op == "draft":
                result["sections"][0]["text"] = " ".join(["word"] * 811)
        if op in {"draft", "revise"} and (
            "draft_repair_stuck" in sys.argv or (
                any(flag in sys.argv for flag in ("draft_repair", "draft_repair_budget"))
                and not m.get("draft_corrections")
            )
        ):
            result["claims"][0]["verification_ids"] = ["search-1"]
            result["claims"][0]["source_ids"] = ["unfrozen-source"]
        if op == "revise":
            result["sections"][0]["text"] += " Scope clarified."
            if "revise_repair" in sys.argv and not m.get("draft_corrections"):
                result["claims"][0]["verification_ids"] = ["search-1"]
        if op == "audit":
            if "rolling_review" in sys.argv and m["packet"]["role"] in {"source_citation", "literature_contribution"}:
                import time

                time.sleep(1.5)
            if ("scope_inventory" in sys.argv and m["packet"]["role"] == "source_citation"
                    and not m["packet"]["prior_comments"]):
                result["coverage_flags"] = ["The broader domain asserted in prose is missing from the claim statement."]
                result["objections"] = [{"id": "scope-inventory", "severity": "blocking", "claim_ids": ["scope"],
                    "objection": "The finite-scope claim does not record the prose's arbitrary-carrier extension.",
                    "acceptance_criterion": "Record arbitrary nonempty carriers in the mapped claim or remove the extension."}]
            if "stream_failure" in sys.argv and m["packet"]["role"] == "proof_method":
                emit(aid, "error", stage="turn_stream", error_class="WorkerStreamError",
                     failure_code="runtime_error", message="PRIVATE_RUNTIME_MESSAGE")
                continue
            if "runtime_diagnostics" in sys.argv and m["packet"]["role"] == "proof_method":
                stream = {"call_span_id": m["call_span_id"], "codex_thread_id": provenance["codex_thread_id"],
                    "codex_turn_id": provenance["codex_turn_id"], "delta_count": 0, "characters": 0,
                    "utf8_bytes": 0, "first_delta_seconds": None, "last_delta_seconds": None,
                    "elapsed_seconds": 900.0, "prompt_tokens": 14000, "prompt_counting_policy": "o200k_base",
                    "completed_text_characters": 0, "completed_text_utf8_bytes": 0, "finished": True}
                activity = {"version": 1, **{k: stream[k] for k in ("call_span_id", "codex_thread_id", "codex_turn_id", "elapsed_seconds")},
                    "notification_count": 3, "last_notification_seconds": 899.0,
                    "reasoning_delta_count": 0, "reasoning_characters": 0, "last_reasoning_seconds": None,
                    "reasoning_item_open": True, "item_event_count": 2, "last_item_seconds": 1.0,
                    "usage_event_count": 0, "last_usage_seconds": None,
                    "tool_request_count": 0, "last_tool_seconds": None,
                    "worker_heartbeat_count": 7, "last_heartbeat_seconds": 899.0, "max_heartbeat_gap_seconds": 880.0}
                emit(aid, "progress", progress={"source": "worker_heartbeat", "stage": "turn_stream",
                    "timestamp": "2026-10-05T00:00:00+00:00", "elapsed_seconds": 900.0,
                    "codex_notification_count": 3, "codex_notification_types": {"item/started": 2, "error": 1},
                    "stream": stream, "activity": activity})
                emit(aid, "error", stage="turn_stream", error_class="WorkerStreamError", failure_code="runtime_error",
                    runtime_error={"source": "error_notification", "category": "responseStreamDisconnected",
                        "http_status_code": 503, "will_retry": True}, message="PRIVATE_RUNTIME_MESSAGE")
                continue
            if ("adversarial_revision" in sys.argv and m["packet"]["role"] == "adversarial"
                    and not m["packet"]["prior_comments"]):
                check = result["adversarial_checks"][0]
                check.update(outcome="unresolved", objection_id="boundary",
                             rationale="Boundary assumptions need clarification.")
                result["objections"] = [{"id": "boundary", "severity": "blocking",
                    "claim_ids": check["claim_ids"], "objection": "Clarify boundary assumptions.",
                    "acceptance_criterion": "Explicitly delimit boundary assumptions in scope."}]
            if "fail" in sys.argv:
                emit(aid, "error", stage="turn_stream", error_class="ValueError")
                continue
            if "revise" in sys.argv and not m["packet"]["prior_comments"]:
                result["objections"] = [
                    {
                        "id": "scope",
                        "objection": "Clarify the scope.",
                        "acceptance_criterion": "State scope clarified.",
                        "severity": "blocking",
                        "claim_ids": [],
                    }
                ]
            if "ambiguous_evidence" in sys.argv:
                result["summary"] += " The packet lacks the author report."
            if "coverage" in sys.argv:
                result["covered_section_ids"] = []
            if (m["packet"]["role"] == "proof_method" and (
                "report_repair_stuck" in sys.argv or
                (any(flag in sys.argv for flag in ("report_repair", "report_repair_budget"))
                 and not m.get("report_corrections"))
            )):
                result["covered_section_ids"] = []
                result["assessments"][0]["verification_ids"] = ["invented"]
            if (m["packet"]["role"] == "proof_method" and m["packet"]["prior_comments"] and (
                "re_review_repair_stuck" in sys.argv or
                (any(flag in sys.argv for flag in ("re_review_report_repair", "tight_re_review_repair"))
                 and not m.get("report_corrections"))
            )):
                result["covered_section_ids"] = []
                result["assessments"][0]["verification_ids"] = ["invented"]
    emit(
        aid,
        {"audit": "specialist_report", "integrate": "synthesis", "discover": "literature_plan"}.get(op, "draft"),
        result=result,
        provenance=provenance,
        usage={"tokens": (m["token_limit"] - 1
                          if op == "audit" and (("initial_review_near_grant" in sys.argv
                                                 and not m.get("report_corrections"))
                            or ("tight_re_review_repair" in sys.argv and m.get("report_corrections"))) else
                          (13676 if op == "draft" else 31799 if op == "revise" else
                           ({"proof_method": 22087, "source_citation": 23503,
                             "literature_contribution": 24506, "adversarial": 100} if m["packet"]["prior_comments"] else
                            {"proof_method": 18442, "source_citation": 18777,
                             "literature_contribution": 18785, "adversarial": 100})[m["packet"]["role"]]
                           if op == "audit" else 100) if "observed_nine" in sys.argv else
                          m["token_limit"] - 1 if "draft_repair_budget" in sys.argv else
                          13411 if "budget_pause" in sys.argv and op == "draft" else
                          18000 if "budget_pause" in sys.argv and op == "audit" else
                          m["token_limit"] - 1 if "report_repair_budget" in sys.argv else
                          (22000 if m["packet"]["role"] == "source_citation" else 18000)
                          if op == "audit" and "unequal_review" in sys.argv else
                          19555 if op == "audit" and "large_review" in sys.argv else 100),
               "kind": "actual", "source": "fixture"},
    )
