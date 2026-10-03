"""Synthetic manuscript-size and polling regressions; no real manuscript fixture."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from test_evaluation_responses import response

from workbench.providers.evaluation_responses import MockResponsesProcess
from workbench.services.evaluation import Denied, digest, encoded
from workbench.services.evaluation_responses import ResponsesContract, ResponsesEvaluation


def make_run(tmp_path, **changes):
    contract = ResponsesContract(
        model="synthetic-model",
        cost_ceiling=200000,
        token_ceiling=200000,
        verification_cost_reserve=40000,
        verification_token_reserve=40000,
    )
    contract = replace(contract, **changes)
    # Escaping makes this exceed 100,000 bytes on the wire, like the admitted source.
    inputs = {
        "inputs/manuscript.tex": ("\\\\" * 30000).encode(),
        "inputs/historical_verification_record.txt": b"SYNTHETIC_RECORD",
    }
    run = ResponsesEvaluation(
        tmp_path / "run",
        inputs=inputs,
        expected={k: digest(v) for k, v in inputs.items()},
        brief="Synthetic",
        contract=contract,
    )
    return run, contract


def test_full_synthetic_manuscript_read_fits_explicit_launch_limits(tmp_path):
    run, contract = make_run(tmp_path, max_tool_result_bytes=128000, max_context_bytes=500000)
    payload = {
        "text": "Reviewing",
        "final": False,
        "tool_calls": [{"name": "read", "arguments": {"alias": "inputs/manuscript.tex"}}],
    }
    result = run._apply_tools(payload)
    assert result[0]["ok"]
    assert 100000 < len(encoded(result[0]["result"])) < 128000
    assert len(run._messages) == 4


@pytest.mark.parametrize("interval", [-1, True, 31, 0.5])
def test_invalid_poll_interval_denied(tmp_path, interval):
    with pytest.raises(Denied):
        make_run(tmp_path, poll_interval_seconds=interval)


def test_polling_waits_before_retrieve(tmp_path, monkeypatch):
    run, contract = make_run(tmp_path, poll_interval_seconds=1)
    original = MockResponsesProcess.exchange
    observed = {}

    def timed(transport, operation, **kwargs):
        if operation == "retrieve":
            observed["retrieve_started"] = time.monotonic()
        reply = original(transport, operation, **kwargs)
        if operation == "create":
            observed["create_received"] = time.monotonic()
        return reply

    monkeypatch.setattr(MockResponsesProcess, "exchange", timed)
    run.step([response(contract, status="queued", usage=None), response(contract)])
    assert observed["retrieve_started"] - observed["create_received"] >= 0.95


def test_cancellation_interrupts_long_poll_wait(tmp_path, monkeypatch):
    run, contract = make_run(tmp_path, poll_interval_seconds=30, max_seconds=60, request_seconds=50)
    original = MockResponsesProcess.exchange
    observed = []

    def cancel_after_create(transport, operation, **kwargs):
        reply = original(transport, operation, **kwargs)
        observed.append(operation)
        if operation == "create":
            run.cancel()
        return reply

    monkeypatch.setattr(MockResponsesProcess, "exchange", cancel_after_create)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(
            run.step,
            [response(contract, status="queued", usage=None), response(contract, status="cancelled")],
        )
        reply = future.result(timeout=20)
    assert reply["state"] == "cancelled" and observed == ["create", "cancel"]


def test_poll_wait_respects_attempt_deadline(tmp_path, monkeypatch):
    run, contract = make_run(tmp_path, poll_interval_seconds=30)
    calls = []
    original = run._cancel.wait

    def recorded(timeout=None):
        calls.append(timeout)
        # Simulate an immediate operator cancellation after observing the bounded wait.
        run.cancel()
        return original(0)

    monkeypatch.setattr(run._cancel, "wait", recorded)
    reply = run.step(
        [response(contract, status="queued", usage=None), response(contract, status="cancelled")]
    )
    assert reply["state"] == "cancelled"
    assert len(calls) == 1 and 0 <= calls[0] <= contract.request_seconds
