"""Bounded call timelines. No prompts, credentials, exception messages or frame locals."""

import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from ..models import new_id

MAX_EVENTS = 2000


def stack():
    frames = []
    for frame in traceback.extract_stack(limit=20)[:-1]:
        path = Path(frame.filename).as_posix()
        if "/workbench/" in path:
            frames.append(
                {
                    "file": "workbench/" + path.split("/workbench/", 1)[1],
                    "function": frame.name,
                    "line": frame.lineno,
                }
            )
    return frames[-10:]


def record(runner, event, *, agent=None, span_id=None, parent_span_id=None, **detail):
    events = list(runner.task.ledger.get("call_trace", []))
    if len(events) >= MAX_EVENTS:
        raise ValueError("research trace event limit reached")
    row = {
        "sequence": len(events) + 1,
        "timestamp": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(time.monotonic() - runner.trace_started, 6),
        "event": event,
        "span_id": span_id or new_id(),
        "parent_span_id": parent_span_id or runner.task.id,
        "task_id": runner.task.id,
        "agent_id": agent.id if agent else None,
        "parent_agent_id": agent.parent_id if agent else None,
        "role": agent.assignment.get("specialist_role", agent.role) if agent else "controller",
        "call_stack": stack(),
        **detail,
    }
    runner.task.ledger = {**runner.task.ledger, "call_trace": [*events, row]}
    runner.session.commit()
    return row["span_id"]


def summary(events):
    starts = {e["span_id"]: e for e in events if e["event"] == "dispatch"}
    calls = []
    for event in events:
        if event["event"] in {"return", "operation_stopped"} and event["span_id"] in starts:
            first = starts[event["span_id"]]
            calls.append(
                {
                    "span_id": event["span_id"],
                    "agent_id": event["agent_id"],
                    "role": first["role"],
                    "operation": first["operation"],
                    "started_at": first["timestamp"],
                    "finished_at": event["timestamp"],
                    "duration_seconds": round(event["elapsed_seconds"] - first["elapsed_seconds"], 6),
                    "status": event["event"],
                    "actual_tokens": event.get("actual_tokens"),
                }
            )
    ended = {c["span_id"] for c in calls}
    for span, first in starts.items():
        if span not in ended:
            calls.append(
                {
                    "span_id": span,
                    "agent_id": first["agent_id"],
                    "role": first["role"],
                    "operation": first["operation"],
                    "started_at": first["timestamp"],
                    "status": "no_terminal_receipt",
                }
            )
    return {
        "calls": calls,
        "event_count": len(events),
        "notice": "Controller-observed timing; RPC dispatch and model execution are distinct. "
        "Stack frames contain function names and lines only.",
    }
