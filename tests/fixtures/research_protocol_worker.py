"""Controlled protocol peer: deterministic fixtures, never model or network calls."""

import json
import os
import sys
import time


def model_provenance(kind):
    return {
        "codex_thread_id": f"controlled-thread-{os.getpid()}",
        "codex_turn_id": f"controlled-{kind}-{os.getpid()}",
        "account_email": "controlled@example.invalid",
        "model": "controlled-test-only",
    }


def emit(aid, kind, **payload):
    if "live-best-effort" in sys.argv and kind in {"plan", "report", "synthesis"}:
        payload["provenance"] = model_provenance(kind)
    print(json.dumps({"agent_id": aid, "type": kind, **payload}), flush=True)


def report(message):
    source_id = message["assignment"]["source_ids"][0]
    index = int(message["assignment"]["key"][-1])
    kind = message["contract"]["task_type"]
    statement = "The directed distance preserves inter-cell distances and the upper-set topology."
    category, stance = "verified_result", "supports"
    if index == 2:
        statement = "A finite symmetric ultrametric cannot produce the non-T1 split topology."
    if kind == "literature_search":
        statement, category = "Bonsangue et al. discuss generalized ultrametrics.", "apparent_prior_art"
    if kind == "proof_audit" and index == 2:
        statement, category, stance = (
            "A gap remains in the claimed lifting proof.",
            "counterexample_candidate",
            "opposes",
        )
    if index == 3:
        statement, category = "No originality established by this bounded search.", "nothing_found"
    citation = {
        "id": "source",
        "source_id": source_id,
        "locator": "section 2, lines 1-8",
        "access": "controlled fixture; supplied text only",
    }
    return {
        "summary": f"Controlled {kind} child {index}; PID {os.getpid()}",
        "findings": [
            {
                "id": "f1",
                "claim_key": "lifting",
                "statement": statement,
                "category": category,
                "stance": stance,
                "scope": "finite controlled test only",
                "citation_ids": ["source"],
                "verification_ids": ["finite-check"],
            }
        ],
        "citations": [citation],
        "proof_attempts": ["Examine both within-cell order and cross-cell triples."],
        "failed_approaches": ["Symmetry cannot distinguish the two directed zero distances."],
        "unresolved_questions": ["Novelty and unrestricted models remain unaudited."],
        "research_leads": ["Read the full generalized-ultrametric literature."],
        "search_log": [
            {
                "query": "generalized ultrametric preorder",
                "location": "pilot fixture",
                "outcome": "A prior-art lead; no new external search.",
                "coverage": "fixture only",
            }
        ],
        "verification_artifacts": [
            {
                "id": "finite-check",
                "description": "Recorded fixture check",
                "content": "Finite triangle and topology fixture passed; not a proof certificate.",
                "outcome": "passed_within_scope",
            }
        ],
    }


for line in sys.stdin:
    message = json.loads(line)
    aid, op = message["agent_id"], message["op"]
    if op == "hello":
        controlled_live = "live-best-effort" in sys.argv
        caps = {
            "protocol": "research-process-v1",
            "executor": "controlled-test-worker",
            "simulated": not controlled_live,
            "child_agents": True,
            "structured_reports": True,
            "hard_total_token_limit": not controlled_live,
            "best_effort_token_stopping": controlled_live,
            "bounded_wall_time": True,
            "no_external_writes": True,
        }
        if len(sys.argv) > 1 and sys.argv[1] == "bad-capabilities":
            caps["child_agents"] = False
        emit(aid, "capabilities", worker_pid=os.getpid(), capabilities=caps)
        continue
    question = message["contract"]["question"]
    control = question.rsplit(" ", 1)[-1]
    if "live-best-effort" in sys.argv:
        emit(aid, "turn_started", provenance=model_provenance({
            "research": "report", "integrate": "synthesis"
        }.get(op, op)))
    if op == "plan":
        plan = {
            "rationale": "Controlled parent decomposition",
            "assignments": [
                {
                    "key": f"child-{i + 1}",
                    "question": question,
                    "success_criteria": "Return a scoped report",
                    "instructions": "Independent controlled assignment",
                    "source_ids": [message["sources"][0]["source_id"]],
                }
                for i in range(message["contract"]["max_children"])
            ],
        }
        if control == "bad-plan":
            plan["assignments"][0]["source_ids"] = ["foreign-source"]
        emit(aid, "plan", result=plan, usage={"tokens": 50, "kind": "actual", "source": "fixture"})
    elif op == "research":
        result = report(message)
        index = int(message["assignment"]["key"][-1])
        if control == "silent-slow":
            emit(aid, "progress", progress={
                "source": "worker_heartbeat", "timestamp": "2026-09-30T00:00:00+00:00",
                "stage": "turn_stream", "elapsed_seconds": 3.0,
                "codex_notification_count": 2,
                "codex_notification_types": {"item/started": 1, "item/completed": 1},
            })
            emit(aid, "progress", progress={
                "source": "codex_notification", "timestamp": "2026-09-30T00:00:01+00:00",
                "stage": "turn_stream", "elapsed_seconds": 4.0,
                "codex_notification_count": 3,
                "codex_notification_types": {"item/started": 1, "item/completed": 1,
                                              "item/agentMessage/delta": 1},
            })
        if control != "silent-slow":
            emit(aid, "checkpoint", report=result)
        if control == "silent-slow":
            time.sleep(20)
        if index == 2 and control in {"slow", "cancel"}:
            time.sleep(20)
        if index == 2 and control == "fail":
            sys.exit(17)
        if index == 2 and control == "bad-report":
            result["findings"][0]["citation_ids"] = ["missing"]
        if control == "no-usage":
            emit(aid, "report", result=result)
        elif control == "hard-token":
            emit(
                aid,
                "usage",
                usage={"tokens": message["contract"]["token_limit"], "kind": "actual", "source": "fixture"},
            )
        elif index == 2 and control == "soft-token":
            emit(aid, "limit")
        else:
            emit(aid, "report", result=result, usage={"tokens": 100, "kind": "actual", "source": "fixture"})
    elif op == "integrate":
        synthesis = {
            "summary": f"Parent PID {os.getpid()} received {len(message['reports'])} child reports.",
            "report_ids": list(message["reports"]),
            "agreements": ["Scope is bounded."],
            "conflicts": [],
            "unresolved_questions": ["Scientific review still needed."],
            "deliverables": {d: "Controlled draft for " + d for d in message["contract"]["deliverables"]},
        }
        if control == "bad-synthesis":
            synthesis["report_ids"] = []
        emit(aid, "synthesis", result=synthesis, usage={"tokens": 30, "kind": "actual", "source": "fixture"})
