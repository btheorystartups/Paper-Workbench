"""Durable authorization and operation identity; never infer unknown usage as zero."""

import os
from copy import deepcopy
from datetime import UTC, datetime

from ..models import stable_hash, utcnow
from ..research_contract import ContractModel, Field
from .research_tasks import TaskError

PIPELINE_VERSION = "manuscript-recovery-v2"
OPERATIONS = ("plan", "research", "discover", "draft", "revise", "audit", "integrate")


def normalization_authority(task):
    """Only explicit, hash-bound continuation approvals authorize derived reports."""
    approved = {}
    current = getattr(task, "ledger", {})
    for ledger in [*(run["ledger"] for run in current.get("previous_runs", [])), current]:
        approved.update(ledger.get("continuation", {}).get("normalization_approvals", {}))
    return approved


def normalize_review_report(raw, approvals):
    source = stable_hash(raw)
    if source not in approvals:
        return raw, None
    identifiers = approvals[source]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise TaskError("normalization requires distinct explicitly approved comment IDs")
    result = deepcopy(raw)
    changes = []
    for row in result["resolutions"]:
        if row["comment_id"] not in identifiers:
            continue
        if (row["disposition"] != "justified_rejection"
                or row["criterion_met"] is not False or row["regression_passed"] is not True):
            raise TaskError("normalization differs from the approved conservative transformation")
        changes.append({"comment_id": row["comment_id"], "from": row["disposition"], "to": "open"})
        row["disposition"] = "open"
    if sorted(row["comment_id"] for row in changes) != sorted(identifiers):
        raise TaskError("approved normalization comments are missing or duplicated")
    return result, {"policy": "explicit-inconsistent-rejection-to-open-v1",
                    "source_report_sha256": source, "derived_report_sha256": stable_hash(result),
                    "changes": changes}


def owner_is_gone(pid):
    """Read process liveness only. Unknown/access-denied means wait conservatively."""
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 87
        kernel.CloseHandle(handle)
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


class AuthorizationGrant(ContractModel):
    token_ceiling: int = Field(ge=2000, le=100_000_000, strict=True)
    time_ceiling_seconds: int = Field(ge=10, le=604800, strict=True)
    max_operation_attempts: int = Field(default=2, ge=1, le=4, strict=True)
    reason: str = Field(min_length=1, max_length=2000)


def charge(row):
    actual = row.get("actual_tokens") or 0
    return actual if row.get("final_actual") else max(row["reserved"], actual)


def historical_allocations(task):
    return [row for run in task.ledger.get("previous_runs", [])
            for row in run["ledger"].get("allocations", [])]


def accounting(task, allocations=None):
    rows = [*historical_allocations(task),
            *(task.ledger.get("allocations", []) if allocations is None else allocations)]
    known = sum(row.get("actual_tokens") or 0 for row in rows)
    charged = sum(map(charge, rows))
    return {"known_tokens": known, "charged_tokens": charged, "held_tokens": charged - known}


def elapsed_seconds(task):
    def duration(start, end):
        if not start:
            return 0
        start = datetime.fromisoformat(start) if isinstance(start, str) else start
        end = datetime.fromisoformat(end) if isinstance(end, str) else end or utcnow()
        start = start.replace(tzinfo=UTC) if start.tzinfo is None else start
        end = end.replace(tzinfo=UTC) if end.tzinfo is None else end
        return max(0, (end - start).total_seconds())

    return sum(duration(run.get("started_at"), run.get("finished_at"))
               for run in task.ledger.get("previous_runs", [])) + duration(
                   getattr(task, "started_at", None), getattr(task, "finished_at", None))


def envelope(grant):
    return {"version": 1, **grant.model_dump(), "allowed_operations": list(OPERATIONS),
            "authorized_at": utcnow().isoformat(), "time_policy": "run-wall-time",
            "token_enforcement": "reservation admission; provider stopping may be best-effort"}


def initial_authorization(task):
    return envelope(AuthorizationGrant(token_ceiling=task.contract["token_limit"],
        time_ceiling_seconds=task.contract["time_limit_seconds"], reason="Explicit initial task start"))


def continuation_authorization(task, grant):
    authority = envelope(grant.authorization) if grant.authorization else task.ledger.get("authorization")
    if not authority:
        raise TaskError("saved task needs an explicit aggregate authorization before continuation")
    remaining = authority["token_ceiling"] - accounting(task)["charged_tokens"]
    if grant.token_limit > remaining:
        raise TaskError("continuation grant exceeds remaining aggregate token authorization")
    if grant.time_limit_seconds > authority["time_ceiling_seconds"] - elapsed_seconds(task):
        raise TaskError("continuation grant exceeds remaining aggregate time authorization")
    return authority


def operation_key(phase, payload):
    # Changing a time/token grant cannot reset a retry counter. A real input or
    # implementation change can produce a new, separately reviewable operation.
    packet = payload.get("packet", {})
    return stable_hash({"version": PIPELINE_VERSION, "phase": phase,
        "candidate": payload.get("original_draft_sha256") or payload.get("previous_candidate_sha256")
                     or packet.get("candidate_sha256"),
        "packet": packet.get("packet_sha256"), "section_recovery": payload.get("section_recovery"),
        "assignment": payload.get("assignment"), "reviewed_candidate": payload.get("reviewed_candidate"),
        "issues": payload.get("draft_corrections") or payload.get("report_corrections"),
        "sources": [(s.get("source_id"), s.get("full_extracted_sha256", s.get("sha256")))
                    for s in payload.get("sources", [])]})


def admit_operation(task, phase, payload, allocations):
    authority = task.ledger.get("authorization")
    if authority and phase not in authority["allowed_operations"]:
        raise TaskError("operation outside authorized scope")
    key = operation_key(phase, payload)
    attempts = [row for row in [*historical_allocations(task), *allocations]
                if row.get("operation_key") == key and row.get("dispatch_state") != "not_attempted"]
    if (any(row.get("dispatch_state") in {"intent", "sent", "started"} for row in attempts)
            and not task.ledger.get("continuation", {}).get("retry_uncertain_operations")):
        raise TaskError("previous dispatch outcome is unresolved; automatic redispatch denied")
    if len(attempts) >= (authority or {}).get("max_operation_attempts", 2):
        raise TaskError("persistent operation attempt limit reached")
    return key


class ReplayHandle:
    """A saved return can traverse the ordinary validation path without dispatch."""

    def __init__(self, agent, allocation, result):
        self.pid = agent.provenance.get("pid")
        self.event = {"type": "specialist_report", "result": result,
                      "call_span_id": allocation["span_id"],
                      "provenance": agent.provenance.get("specialist_report_model")
                      or agent.provenance.get("invalid_return_model")}

    def poll(self):
        event, self.event = self.event, None
        return event

    def close(self):
        pass


def retained_reviews(runner, campaign, candidate, iteration, accepted_roles):
    if {"proof_method", "source_citation", "literature_contribution", "adversarial"} <= accepted_roles:
        return []
    rows = []
    allocations = [*historical_allocations(runner.task), *runner.allocations]
    for agent in runner.agents:
        role = agent.assignment.get("specialist_role")
        if (not role or role in accepted_roles or agent.assignment.get("candidate_sha256") != candidate
                or agent.assignment.get("iteration") != iteration):
            continue
        dispatch = next((d for d in reversed(campaign.body.get("dispatches", []))
                         if d["agent_id"] == agent.id), None)
        if not dispatch or dispatch["packet"]["packet_sha256"] != agent.assignment.get("packet_sha256"):
            continue
        outputs = [*agent.provenance.get("returned_outputs", []),
                   *agent.provenance.get("invalid_returns", [])]
        for output in reversed(outputs):
            allocation = next((a for a in allocations
                               if a.get("span_id") == output.get("call_span_id")), None)
            raw = output.get("result")
            if (output.get("operation") == "audit" and output.get("identity_verified") is True
                    and allocation and allocation["agent_id"] == agent.id and isinstance(raw, dict)
                    and stable_hash(raw) == output.get("result_sha256")):
                rows.append((agent, ReplayHandle(agent, allocation, raw), allocation, dispatch["packet"]))
                packet = dispatch["packet"]
                if (stable_hash({k: v for k, v in packet.items() if k != "packet_sha256"})
                        != packet["packet_sha256"]):
                    raise TaskError("retained review packet changed; replay denied before dispatch")
                accepted_roles.add(role)
                break
    return rows
