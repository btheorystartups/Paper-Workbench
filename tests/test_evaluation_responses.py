"""Actual SDK + owned subprocess, synthetic HTTP only. No credentials or app DB."""

import json
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from workbench.providers.evaluation_responses import MockResponsesProcess
from workbench.services.evaluation import AttemptLedger, Denied, digest, encoded
from workbench.services.evaluation_responses import (
    ResponsesContract,
    ResponsesEvaluation,
    measured_usage,
    participant_reply,
    request_body,
    response_identity,
)


@pytest.fixture
def contract():
    return ResponsesContract(
        model="synthetic-model",
        cost_ceiling=200_000,
        token_ceiling=200_000,
        verification_cost_reserve=40_000,
        verification_token_reserve=40_000,
    )


def response(contract, *, status="completed", text="Synthetic finding", final=True, tools=None, **changes):
    payload = {"text": text, "final": final, "tool_calls": tools or []}
    body = {
        "id": "resp_synthetic",
        "object": "response",
        "created_at": 1,
        "model": contract.model,
        "background": True,
        "store": False,
        "service_tier": "default",
        "reasoning": {"effort": "high"},
        "max_output_tokens": contract.max_output_tokens,
        "tools": [],
        "previous_response_id": None,
        "conversation": None,
        "status": status,
        "error": None,
        "incomplete_details": None,
        "output": [
            {
                "id": "msg_synthetic",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(payload), "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 120,
            "output_tokens": 80,
            "total_tokens": 200,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 50},
        },
    }
    body.update(changes)
    return {"body": body, "http_request_id": "req_synthetic"}


@pytest.fixture
def factory(tmp_path, contract):
    def make(*, limits=None, name="run"):
        inputs = {
            "inputs/manuscript.tex": b"ALLOWED_SYNTHETIC",
            "inputs/historical_verification_record.txt": b"UNVERIFIED_SYNTHETIC",
        }
        return ResponsesEvaluation(
            tmp_path / name,
            inputs=inputs,
            expected={k: digest(v) for k, v in inputs.items()},
            brief="Review the synthetic paper.",
            contract=limits or contract,
        )

    return make


def test_completed_sdk_roundtrip_capture_and_conservative_accounting(factory, contract, tmp_path):
    run = factory()
    reply = run.step([response(contract)])
    assert reply["state"] == "completed" and reply["text"] == "Synthetic finding"
    assert reply["cost_upper_units"] == 280  # no input-cache discount; reasoning counted once
    assert run.accounting()["attempts"][0]["tokens_charged"] == 200
    outcome = run.finish()
    assert outcome["simulated"] and not outcome["live_ready"]
    capture = tmp_path / "run/capture"
    manifest = json.loads((capture / "receipt.json").read_text())
    for name, record in manifest["outputs"].items():
        assert digest((capture / name).read_bytes()) == record["sha256"]
    events = json.loads((capture / "transport.json").read_text())
    sent = next(e["event"] for e in events if e["event"]["type"] == "transport_receipt")
    assert sent["http_request_id"] == "req_synthetic"
    assert sent["observed"][0]["retry_count"] == "0"
    assert sent["observed"][0]["path"] == "/v1/responses"
    assert "resp_synthetic" in encoded(events).decode()
    with pytest.raises(Denied):
        run.step([response(contract)])


def test_poll_preserves_ack_before_next_request(factory, contract, monkeypatch):
    run = factory()
    original = MockResponsesProcess.exchange

    def checked(transport, operation, **kwargs):
        if operation == "retrieve":
            assert any(
                e["event"].get("response_id") == "resp_synthetic" and e["event"]["type"] == "response"
                for e in run._events
            )
        assert run.accounting()["attempts"][0]["state"] == "dispatched"
        return original(transport, operation, **kwargs)

    monkeypatch.setattr(MockResponsesProcess, "exchange", checked)
    run.step([response(contract, status="queued", usage=None), response(contract)])
    assert run.state == "completed"


@pytest.mark.parametrize("fault", ["timeout", "exit", "server_error"])
def test_unknown_creation_keeps_full_reservation_without_retry(factory, contract, fault):
    run = factory()
    frame = (
        {"fault": fault}
        if fault != "server_error"
        else {
            "http_status": 500,
            "body": {"error": {"message": "synthetic", "type": "server_error"}},
        }
    )
    with pytest.raises(Denied, match="uncertain"):
        run.step([frame, response(contract)])
    attempt = run.accounting()["attempts"][0]
    assert attempt["charged"] is None and attempt["state"] == "uncertain"
    assert attempt["reserved"] == contract.maximum_cost
    assert len([e for e in run._events if e["event"]["type"] == "transport_request"]) == 1
    if fault == "server_error":
        assert any(e["event"].get("http_request_id") == "req_synthetic" for e in run._events)
    with pytest.raises(Denied):
        run.step([response(contract)])


def test_hung_poll_is_killed_and_unknown_usage_retained(factory, contract):
    limits = replace(contract, request_seconds=7)
    run = factory(limits=limits)
    start = time.monotonic()
    with pytest.raises(Denied):
        run.step([response(limits, status="queued", usage=None), {"fault": "hang"}])
    assert time.monotonic() - start < 12
    assert run.accounting()["attempts"][0]["charged"] is None


def test_cancel_does_not_wait_for_step_lock(factory, contract):
    run = factory()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run.step, [{"fault": "hang"}])
        until = time.monotonic() + 5
        while not run.accounting()["attempts"] and time.monotonic() < until:
            time.sleep(0.01)
        run.cancel()
        with pytest.raises(Denied):
            future.result(timeout=8)
    assert run.accounting()["attempts"][0]["charged"] is None


def test_poll_limit_sends_cancel_and_settles_measured_usage(factory, contract):
    limits = replace(contract, max_polls=1)
    run = factory(limits=limits)
    reply = run.step(
        [
            response(limits, status="queued", usage=None),
            response(limits, status="in_progress", usage=None),
            response(limits, status="cancelled"),
        ]
    )
    assert reply["state"] == "cancelled" and not reply["tools"]
    assert run.accounting()["attempts"][0]["state"] == "settled"
    operations = [e["event"]["operation"] for e in run._events if e["event"]["type"] == "transport_request"]
    assert operations == ["create", "retrieve", "cancel"]


def test_cancellation_timeout_does_not_release_reservation(factory, contract):
    limits = replace(contract, max_polls=1, cancel_seconds=1)
    run = factory(limits=limits)
    with pytest.raises(Denied):
        run.step(
            [
                response(limits, status="queued", usage=None),
                response(limits, status="in_progress", usage=None),
                {"fault": "hang"},
            ]
        )
    assert run.accounting()["attempts"][0]["state"] == "uncertain"


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "different"},
        {"usage": None},
        {"store": True},
        {"background": False},
        {"usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 4}},
        {"usage": {"input_tokens": 1, "output_tokens": 5000, "total_tokens": 5001}},
    ],
)
def test_invalid_identity_or_usage_fails_closed(factory, contract, changes):
    run = factory()
    with pytest.raises(Denied):
        run.step([response(contract, **changes)])
    assert run.accounting()["attempts"][0]["charged"] is None
    assert any(e["event"].get("reported_response_id") == "resp_synthetic" for e in run._events)


def test_wrong_response_on_poll_fails_closed(factory, contract):
    run = factory()
    with pytest.raises(Denied):
        run.step([response(contract, status="queued", usage=None), response(contract, id="resp_wrong")])
    assert run.state == "uncertain"


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled"])
def test_noncomplete_response_accounts_without_executing_tools(factory, contract, status):
    run = factory()
    reply = run.step(
        [
            response(
                contract,
                status=status,
                final=False,
                tools=[
                    {"name": "read", "arguments_json": '{"alias":"inputs/manuscript.tex"}'},
                ],
            )
        ]
    )
    assert reply["state"] == status and reply["tools"] == []
    assert run.accounting()["attempts"][0]["charged"] == 280


def test_invalid_scientific_payload_still_records_spend(factory, contract):
    run = factory()
    frame = response(contract)
    frame["body"]["output"][0]["content"][0]["text"] = "not JSON"
    assert run.step([frame])["state"] == "invalid_output"
    assert run.accounting()["attempts"][0]["state"] == "settled"


def test_two_input_tools_and_denied_arguments_never_enter_capture(factory, contract, tmp_path):
    run = factory()
    canary = "HIDDEN_PATH_CANARY"
    tools = [
        {"name": "read", "arguments_json": json.dumps({"alias": alias})}
        for alias in ["inputs/manuscript.tex", canary]
    ]
    first = run.step([response(contract, final=False, tools=tools)])
    assert first["tools"] == [
        {"ok": True, "tool": "read", "result": "ALLOWED_SYNTHETIC"},
        {"ok": False, "error": "tool request denied"},
    ]
    run.step([response(contract, id="resp_verification")], phase="verification")
    run.finish()
    for path in (tmp_path / "run/capture").iterdir():
        assert canary.encode() not in path.read_bytes()
    assert canary.encode() not in (tmp_path / "run/attempts.sqlite").read_bytes()


def test_receipt_failure_before_poll_stops_without_redispatch(factory, contract, monkeypatch):
    run = factory()
    journal = run._journal

    def fail_response(event):
        if event["type"] == "response":
            raise OSError("synthetic disk failure")
        journal(event)

    monkeypatch.setattr(run, "_journal", fail_response)
    with pytest.raises(Denied):
        run.step([response(contract, status="queued", usage=None), response(contract)])
    assert len([e for e in run._events if e["event"]["type"] == "transport_request"]) == 1
    assert run.accounting()["attempts"][0]["charged"] is None


def test_settlement_failure_retains_dispatched_record(factory, contract, monkeypatch):
    run = factory()

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic disk failure")

    monkeypatch.setattr(run._ledger, "reconcile", fail)
    with pytest.raises(Denied):
        run.step([response(contract)])
    assert run.accounting()["attempts"][0]["state"] == "dispatched"
    assert run.finish()["state"] == "uncertain"


def test_reserve_before_any_process_and_protected_verification(factory, contract, monkeypatch):
    limits = replace(contract, cost_ceiling=50_000, verification_cost_reserve=30_000)
    run = factory(limits=limits)
    with pytest.raises(Denied):
        run.step([response(limits)])
    assert run.state == "verification_only" and not run.accounting()["attempts"]
    assert run.step([response(limits)], phase="verification")["state"] == "completed"


def test_contract_and_ledger_tampering_refused(factory, contract):
    run = factory()
    run.contract = replace(contract, max_output_tokens=8000)
    with pytest.raises(Denied):
        run.step([response(contract)])
    assert not run.accounting()["attempts"]


def test_live_mode_and_ambient_configuration_cannot_enable_network(factory, contract, monkeypatch):
    monkeypatch.setenv("WB_PROVIDER_MODE", "live")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://hidden.invalid")
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_ENV_CANARY")
    with pytest.raises(Denied):
        replace(contract, mode="live").validate()
    with pytest.raises(Denied):
        MockResponsesProcess([], mode="live")
    run = factory()
    assert run.step([response(contract)])["state"] == "completed"


def test_request_envelope_has_no_ambient_context(contract):
    body = request_body(contract, [{"role": "user", "content": "admitted"}])
    assert body["store"] is False and body["background"] is True
    assert body["tools"] == [] and body["tool_choice"] == "none"
    assert body["truncation"] == "disabled" and body["service_tier"] == "default"
    assert body["reasoning"] == {"effort": "high"}
    assert "previous_response_id" not in body and "conversation" not in body


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": True, "output_tokens": 0, "total_tokens": 1},
        {
            "input_tokens": 2,
            "output_tokens": 3,
            "total_tokens": 5,
            "output_tokens_details": {"reasoning_tokens": 4},
        },
        {
            "input_tokens": 2,
            "output_tokens": 3,
            "total_tokens": 5,
            "input_tokens_details": {"cached_tokens": -1},
        },
    ],
)
def test_usage_validation_is_strict(contract, usage):
    with pytest.raises(Denied):
        measured_usage({"usage": usage}, contract)


def test_unexpected_builtin_tool_output_refused(contract):
    body = response(contract)["body"]
    body["output"] = [{"type": "web_search_call"}]
    with pytest.raises(Denied):
        participant_reply(body, contract)
    body["conversation"] = {"id": "prior_conversation"}
    with pytest.raises(Denied):
        response_identity(body, contract)


def test_dispatch_record_failure_never_starts_process(factory, contract, monkeypatch):
    run = factory()

    def fail(*args, **kwargs):
        raise OSError("synthetic write failure")

    def forbidden(*args, **kwargs):
        pytest.fail("process launched before dispatch was durable")

    monkeypatch.setattr(run._ledger, "dispatch", fail)
    monkeypatch.setattr(MockResponsesProcess, "start", forbidden)
    with pytest.raises(Denied):
        run.step([response(contract)])
    assert run.accounting()["attempts"][0]["charged"] is None


def test_completed_response_cannot_be_replayed_in_another_attempt(factory, contract):
    run = factory()
    run.step([response(contract, final=False)])
    with pytest.raises(Denied):
        run.step([response(contract)])
    assert [a["state"] for a in run.accounting()["attempts"]] == ["settled", "uncertain"]


def test_changed_journal_refuses_capture(factory):
    run = factory()
    run._journal({"type": "synthetic"})
    (run._directory / "event-0001.json").write_text("{}")
    with pytest.raises(Denied, match="journal changed"):
        run.finish()


def test_two_callers_cannot_dispatch_completed_run_twice(factory, contract):
    run = factory()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run.step, [response(contract)]) for _ in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result()["state"])
            except Denied:
                outcomes.append("denied")
    assert sorted(outcomes) == ["completed", "denied"]
    assert len(run.accounting()["attempts"]) == 1


def test_hard_custodian_exit_preserves_response_identity(tmp_path, contract):
    from workbench.services import evaluation_responses as module

    source = str(Path(module.__file__).resolve().parents[2])
    target = tmp_path / "crashed"
    fixture = response(contract, status="queued", usage=None)
    script = f"""
import os, sys
sys.path.insert(0, {source!r})
from workbench.services.evaluation_responses import ResponsesContract, ResponsesEvaluation
from workbench.services.evaluation import digest
c = ResponsesContract(model="synthetic-model", cost_ceiling=200000, token_ceiling=200000,
 verification_cost_reserve=40000, verification_token_reserve=40000)
inputs = {{"inputs/manuscript.tex": b"synthetic", "inputs/historical_verification_record.txt": b"synthetic"}}
run = ResponsesEvaluation({str(target)!r}, inputs=inputs, expected={{k:digest(v) for k,v in inputs.items()}},
 brief="synthetic", contract=c)
original = run._journal
def crash(event):
 original(event)
 if event["type"] == "response": os._exit(17)
run._journal = crash
run.step([{fixture!r}])
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script], capture_output=True, timeout=30, check=False
    )
    assert result.returncode == 17
    ledger = AttemptLedger(target / "attempts.sqlite")
    assert ledger.snapshot()["attempts"][0]["state"] == "dispatched"
    events = [json.loads(p.read_text()) for p in target.glob("event-*.json")]
    assert any(e["event"].get("response_id") == "resp_synthetic" for e in events)
    attempt = ledger.snapshot()["attempts"][0]
    with pytest.raises(Denied):
        ledger.dispatch(attempt["id"])


def test_unreviewed_sdk_refused_before_reservation(factory, contract, monkeypatch):
    from workbench.providers import evaluation_responses

    run = factory()
    monkeypatch.setattr(evaluation_responses, "version", lambda name: "unreviewed")
    with pytest.raises(Denied, match="reviewed evaluation SDK"):
        run.step([response(contract)])
    assert not run.accounting()["attempts"]
