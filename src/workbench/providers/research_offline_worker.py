"""Controlled OFFLINE fake. Exercises processes and messages, never calls a model.

Kept standalone so workers can run with a minimal environment and empty working dir.
"""

import json
import os
import sys

from research_quality_offline import reply as manuscript_reply


def emit(agent_id, kind, **payload):
    print(json.dumps({"agent_id": agent_id, "type": kind, **payload}), flush=True)


def main():
    for line in sys.stdin:
        message = json.loads(line)
        agent_id = message["agent_id"]
        operation = message["op"]
        if operation == "hello":
            emit(
                agent_id,
                "capabilities",
                worker_pid=os.getpid(),
                capabilities={
                    "protocol": "research-process-v1",
                    "executor": "offline-controlled-worker",
                    "simulated": True,
                    "child_agents": True,
                    "structured_reports": True,
                    "hard_total_token_limit": True,
                    "bounded_wall_time": True,
                    "no_external_writes": True,
                },
            )
        elif operation in {"draft", "revise", "audit", "discover"}:
            emit(agent_id, "literature_plan" if operation == "discover"
                 else "specialist_report" if operation == "audit" else "draft",
                 result=manuscript_reply(operation, message),
                 usage={"tokens": 0, "kind": "actual", "source": "offline; no model invoked"})
        elif operation == "plan":
            contract = message["contract"]
            roles = {
                "research": ["constructive argument", "independent boundary audit", "prior art search"],
                "literature_search": ["primary source search", "coverage and exclusion audit"],
                "proof_audit": ["independent proof audit", "counterexample search"],
            }[contract["task_type"]][: contract["max_children"]]
            plan = {
                "rationale": "Controlled offline decomposition; no model judgement.",
                "assignments": [
                    {
                        "key": f"assignment-{index + 1}",
                        "question": role + ": " + contract["question"],
                        "success_criteria": contract["success_criteria"],
                        "instructions": contract["instructions"],
                        "source_ids": [s["source_id"] for s in message["sources"] if s.get("source_id")],
                    }
                    for index, role in enumerate(roles)
                ],
            }
            emit(agent_id, "plan", result=plan, usage={"tokens": 0, "kind": "actual", "source": "offline"})
        elif operation == "research":
            report = {
                "summary": "Controlled offline handoff completed. No model research was performed.",
                "findings": [],
                "citations": [],
                "proof_attempts": [],
                "failed_approaches": [],
                "unresolved_questions": [message["assignment"]["question"]],
                "research_leads": ["Run this bounded assignment with an authorized live agent executor."],
                "search_log": [
                    {
                        "query": message["assignment"]["question"],
                        "location": "offline protocol fixture",
                        "outcome": "No external search run.",
                        "coverage": "Transport demonstration only; no literature coverage.",
                    }
                ],
                "verification_artifacts": [],
            }
            emit(agent_id, "checkpoint", report=report)
            emit(
                agent_id,
                "report",
                result=report,
                usage={"tokens": 0, "kind": "actual", "source": "offline; no model invoked"},
            )
        elif operation == "integrate":
            synthesis = {
                "summary": "Offline parent received the child reports. The research question remains open.",
                "report_ids": list(message["reports"]),
                "agreements": [],
                "conflicts": [],
                "unresolved_questions": ["Live research and scientific verification remain required."],
                "deliverables": {
                    name: "Offline draft placeholder. No research claims have been established."
                    for name in message["contract"]["deliverables"]
                },
            }
            emit(
                agent_id,
                "synthesis",
                result=synthesis,
                usage={"tokens": 0, "kind": "actual", "source": "offline"},
            )
        else:
            emit(agent_id, "error", code="unsupported_operation")


if __name__ == "__main__":
    main()
