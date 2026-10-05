"""Pinned, bounded diagnostics; synthetic data only, never provider/model calls."""

import pytest
from pydantic import ValidationError

from workbench.providers.codex_diagnostics import (
    HTTP_ERRORS,
    SIMPLE_ERRORS,
    RuntimeErrorInfo,
    StreamActivity,
    activity_summary,
    normalize_runtime_error,
)


@pytest.mark.parametrize("category", sorted(SIMPLE_ERRORS))
def test_known_simple_errors_retain_only_structured_category(category):
    result = normalize_runtime_error({"message": "PRIVATE_MESSAGE", "additionalDetails": "PRIVATE_DETAILS",
        "codexErrorInfo": category, "misalignment": {"steer": "PRIVATE_STEER"}},
        source="error_notification", will_retry=True)
    assert result == {"source": "error_notification", "category": category, "http_status_code": None, "will_retry": True}
    assert "PRIVATE" not in str(result)


@pytest.mark.parametrize("category", sorted(HTTP_ERRORS))
@pytest.mark.parametrize("status,expected", [(429, 429), (503, 503), (99, None), (600, None), (True, None), ("503", None)])
def test_http_variants_keep_only_valid_status(category, status, expected):
    result = normalize_runtime_error({"codexErrorInfo": {category: {"httpStatusCode": status, "body": "PRIVATE"}}},
        source="error_notification", will_retry="PRIVATE")
    assert result["category"] == category and result["http_status_code"] == expected
    assert result["will_retry"] is None and "PRIVATE" not in str(result)


@pytest.mark.parametrize("value", [None, "PRIVATE_CATEGORY", {"PRIVATE_CATEGORY": {}},
    {"badRequest": {"message": "PRIVATE"}}, {"responseStreamDisconnected": {}, "PRIVATE": {}}, [], 123])
def test_unknown_or_malformed_error_data_does_not_leak(value):
    result = normalize_runtime_error({"codexErrorInfo": value}, source="failed_turn")
    assert result == {"source": "failed_turn", "category": "unknown", "http_status_code": None, "will_retry": None}


@pytest.mark.parametrize("kind,expected", [("review", "activeTurnNotSteerable"),
    ("compact", "activeTurnNotSteerable"), ("PRIVATE", "unknown"), (None, "unknown"), ([], "unknown")])
def test_non_steerable_turn_variant_requires_known_kind(kind, expected):
    result = normalize_runtime_error({"codexErrorInfo": {"activeTurnNotSteerable": {"turnKind": kind}}},
        source="failed_turn")
    assert result["category"] == expected and "PRIVATE" not in str(result)


@pytest.mark.parametrize("extra", [{"message": "PRIVATE"}, {"category": "PRIVATE"},
    {"http_status_code": 503}, {"will_retry": "false"}, {"http_status_code": True}])
def test_diagnostic_boundary_rejects_private_or_inconsistent_fields(extra):
    with pytest.raises(ValidationError):
        RuntimeErrorInfo.model_validate({"source": "error_notification", "category": "badRequest", **extra})


def activity_fixture(**changes):
    return {"version": 1, "call_span_id": "span1", "codex_thread_id": "thread1", "codex_turn_id": "turn1",
        "elapsed_seconds": 900.0, "notification_count": 3, "last_notification_seconds": 20.0,
        "reasoning_delta_count": 1, "reasoning_characters": 8, "last_reasoning_seconds": 10.0,
        "reasoning_item_open": True, "item_event_count": 1, "last_item_seconds": 1.0,
        "usage_event_count": 0, "last_usage_seconds": None, "tool_request_count": 0, "last_tool_seconds": None,
        "worker_heartbeat_count": 4, "last_heartbeat_seconds": 900.0, "max_heartbeat_gap_seconds": 880.0, **changes}


def test_local_gap_and_no_output_are_diagnostic_observations_not_reasoning_verdicts():
    activity = StreamActivity.model_validate(activity_fixture()).model_dump()
    summary = activity_summary(activity, {"first_delta_seconds": None, "last_delta_seconds": None})
    assert summary["local_heartbeat_gap_observed"] and summary["long_observable_silence"]
    assert summary["observable_progress_idle_seconds"] == 890
    assert summary["first_output_pending_seconds"] == 900
    assert summary["notification_idle_seconds"] == 880
    # A new reasoning delta demonstrates activity even without manuscript output.
    activity.update(reasoning_delta_count=2, notification_count=4, last_reasoning_seconds=899.0)
    assert not activity_summary(activity, {})["long_observable_silence"]


@pytest.mark.parametrize("changes", [{"reasoning_text": "PRIVATE"}, {"elapsed_seconds": float("nan")},
    {"last_notification_seconds": 901.0}, {"reasoning_delta_count": 0}, {"notification_count": 1},
    {"tool_request_count": 1}, {"worker_heartbeat_count": True}, {"max_heartbeat_gap_seconds": 901.0}])
def test_activity_schema_rejects_private_and_impossible_measurements(changes):
    with pytest.raises(ValidationError):
        StreamActivity.model_validate(activity_fixture(**changes))
