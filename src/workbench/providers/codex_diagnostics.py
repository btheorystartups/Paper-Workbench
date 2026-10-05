"""Content-free diagnostics for the pinned app-server protocol; never retry policy."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from ..research_contract import ContractModel

ErrorCategory = Literal[
    "contextWindowExceeded",
    "sessionBudgetExceeded",
    "usageLimitExceeded",
    "rateLimitExceeded",
    "serverOverloaded",
    "cyberPolicy",
    "misalignmentPolicyViolation",
    "internalServerError",
    "unauthorized",
    "badRequest",
    "threadRollbackFailed",
    "sandboxError",
    "other",
    "httpConnectionFailed",
    "responseStreamConnectionFailed",
    "responseStreamDisconnected",
    "responseTooManyFailedAttempts",
    "activeTurnNotSteerable",
    "unknown",
]
HTTP_ERRORS = frozenset(
    {
        "httpConnectionFailed",
        "responseStreamConnectionFailed",
        "responseStreamDisconnected",
        "responseTooManyFailedAttempts",
    }
)
SIMPLE_ERRORS = frozenset(ErrorCategory.__args__) - HTTP_ERRORS - {"activeTurnNotSteerable", "unknown"}


class RuntimeErrorInfo(ContractModel):
    source: Literal["error_notification", "failed_turn"]
    category: ErrorCategory
    http_status_code: int | None = Field(default=None, ge=100, le=599, strict=True)
    will_retry: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def consistent_status(self):
        if self.http_status_code is not None and self.category not in HTTP_ERRORS:
            raise ValueError("HTTP status requires an HTTP error variant")
        if self.source == "failed_turn" and self.will_retry is not None:
            raise ValueError("failed turns do not declare retryability")
        return self


def normalize_runtime_error(error, *, source, will_retry=None):
    category, status = "unknown", None
    info = error.get("codexErrorInfo") if isinstance(error, dict) else None
    if isinstance(info, str) and info in SIMPLE_ERRORS:
        category = info
    elif isinstance(info, dict) and len(info) == 1:
        name = next(iter(info))
        if name in HTTP_ERRORS and isinstance(info[name], dict):
            category = name
            value = info[name].get("httpStatusCode")
            status = value if type(value) is int and 100 <= value <= 599 else None
        elif (
            name == "activeTurnNotSteerable"
            and isinstance(info[name], dict)
            and info[name].get("turnKind") in ("review", "compact")
        ):
            category = name
    return RuntimeErrorInfo(
        source=source,
        category=category,
        http_status_code=status,
        will_retry=will_retry if type(will_retry) is bool else None,
    ).model_dump()


Count = Annotated[int, Field(ge=0, le=100_000_000, strict=True)]
Seconds = Annotated[float, Field(ge=0, le=86400, strict=True, allow_inf_nan=False)]
Identity = Annotated[str, StringConstraints(min_length=1, max_length=200, strict=True)]


class StreamActivity(ContractModel):
    version: Literal[1] = 1
    call_span_id: Identity
    codex_thread_id: Identity
    codex_turn_id: Identity
    elapsed_seconds: Seconds
    notification_count: Count
    last_notification_seconds: Seconds | None
    reasoning_delta_count: Count
    reasoning_characters: Count
    last_reasoning_seconds: Seconds | None
    reasoning_item_open: bool = Field(strict=True)
    item_event_count: Count
    last_item_seconds: Seconds | None
    usage_event_count: Count
    last_usage_seconds: Seconds | None
    tool_request_count: Count
    last_tool_seconds: Seconds | None
    worker_heartbeat_count: Count
    last_heartbeat_seconds: Seconds | None
    max_heartbeat_gap_seconds: Seconds

    @model_validator(mode="after")
    def consistent_timings(self):
        pairs = (
            ("notification_count", "last_notification_seconds"),
            ("reasoning_delta_count", "last_reasoning_seconds"),
            ("item_event_count", "last_item_seconds"),
            ("usage_event_count", "last_usage_seconds"),
            ("tool_request_count", "last_tool_seconds"),
            ("worker_heartbeat_count", "last_heartbeat_seconds"),
        )
        for count_key, time_key in pairs:
            count, seconds = getattr(self, count_key), getattr(self, time_key)
            if (count == 0) != (seconds is None) or seconds is not None and seconds > self.elapsed_seconds:
                raise ValueError("activity timing is inconsistent")
        if not self.reasoning_delta_count and self.reasoning_characters:
            raise ValueError("reasoning counters are inconsistent")
        if (
            self.reasoning_delta_count + self.item_event_count + self.usage_event_count
            > self.notification_count
            or self.reasoning_item_open
            and not self.item_event_count
            or self.max_heartbeat_gap_seconds > self.elapsed_seconds
        ):
            raise ValueError("activity counters are inconsistent")
        return self


def activity_summary(activity, stream):
    """An inactivity observation is not evidence the provider stopped reasoning."""
    elapsed = activity["elapsed_seconds"]
    last = max(
        [
            0,
            *[
                activity[k] or 0
                for k in (
                    "last_reasoning_seconds",
                    "last_item_seconds",
                    "last_usage_seconds",
                    "last_tool_seconds",
                )
            ],
            stream.get("last_delta_seconds") or 0,
        ]
    )
    return {
        "notification_idle_seconds": round(elapsed - (activity["last_notification_seconds"] or 0), 3),
        "observable_progress_idle_seconds": round(elapsed - last, 3),
        "first_output_pending_seconds": round(elapsed, 3)
        if stream.get("first_delta_seconds") is None
        else None,
        "long_observable_silence": elapsed - last >= 120,
        "local_heartbeat_gap_observed": activity["max_heartbeat_gap_seconds"] >= 30,
        "notice": ("Local heartbeats do not establish provider progress. "
                   "No observed output or reasoning updates does not prove no computation occurred."),
    }
