"""Priced supervisor integration: actual SDK, synthetic HTTP and isolated ledgers."""

import json
from dataclasses import replace

import pytest
from test_evaluation_responses import response

from workbench.providers.evaluation_responses import MockResponsesProcess
from workbench.services.evaluation import AttemptLedger, BudgetDenied, Denied, digest
from workbench.services.evaluation_costs import Tariff, nanos
from workbench.services.evaluation_responses import ResponsesContract, ResponsesEvaluation


@pytest.fixture
def contract():
    return ResponsesContract(
        model="synthetic-model",
        cost_ceiling=nanos("2"),
        token_ceiling=100000,
        verification_cost_reserve=nanos("0.5"),
        verification_token_reserve=20000,
    )


@pytest.fixture
def tariff():
    return Tariff(
        model="synthetic-model",
        input_nanos=20000,
        cached_nanos=2000,
        cache_write_nanos=25000,
        output_nanos=75000,
        auxiliary_request_nanos=11,
        source_url="https://developers.openai.com/api/docs/pricing",
        checked_date="2026-10-03",
        account_scope="standard-global-text-only",
        auxiliary_basis="synthetic fee bound only",
    )


@pytest.fixture
def factory(tmp_path, contract, tariff):
    def make(limits=None):
        inputs = {
            "inputs/manuscript.tex": b"ALLOWED_SYNTHETIC",
            "inputs/historical_verification_record.txt": b"UNVERIFIED_SYNTHETIC",
        }
        return ResponsesEvaluation(
            tmp_path / "run",
            inputs=inputs,
            expected={k: digest(v) for k, v in inputs.items()},
            brief="Synthetic review",
            contract=limits or contract,
            tariff=tariff,
        )

    return make


def count_frame(tokens=120):
    return {
        "body": {"object": "response.input_tokens", "input_tokens": tokens},
        "http_request_id": "req_count",
    }


def test_priced_sdk_roundtrip_with_durable_count_and_poll(factory, contract, monkeypatch, tmp_path):
    run = factory()
    original = MockResponsesProcess.exchange
    seen = []

    def checked(transport, operation, **kwargs):
        attempts = run.accounting()["attempts"]
        assert attempts[-1]["state"] == "dispatched"
        if operation == "create":
            assert attempts[0]["state"] == "settled"
        seen.append(operation)
        return original(transport, operation, **kwargs)

    monkeypatch.setattr(MockResponsesProcess, "exchange", checked)
    result = run.step([count_frame(), response(contract, status="queued", usage=None), response(contract)])
    assert seen == ["count", "create", "retrieve"]
    assert result["cost_upper_units"] == 120 * 47000 + 80 * 75000 + 11
    assert result["cost_basis"] == "nano_usd_upper"
    attempts = run.accounting()["attempts"]
    assert [a["charged"] for a in attempts] == [11, result["cost_upper_units"]]
    assert [a["state"] for a in attempts] == ["settled", "settled"]
    assert run.finish()["state"] == "completed"
    # Reopen the actual durable ledger rather than trusting the object's memory.
    reopened = AttemptLedger(tmp_path / "run/attempts.sqlite")
    assert reopened.snapshot() == run.accounting()
    events = json.loads((tmp_path / "run/capture/transport.json").read_text())
    assert [e["event"]["operation"] for e in events if e["event"]["type"] == "transport_receipt"] == seen
    assert any(e["event"]["type"] == "settled" for e in events)


@pytest.mark.parametrize("fault", ["timeout", "exit", "redirect", "malformed"])
@pytest.mark.parametrize("at_count", [True, False])
def test_upstream_failure_never_runs_tools_or_retries(factory, contract, fault, at_count):
    frame = (
        {"fault": fault}
        if fault in {"timeout", "exit"}
        else (
            {"http_status": 302, "body": {}, "redirect_location": "https://hidden.invalid/forbidden"}
            if fault == "redirect"
            else {"body": {"invalid": True}}
        )
    )
    run = factory()
    frames = [frame] if at_count else [count_frame(), frame]
    frames.append(
        response(contract, tools=[{"name": "read", "arguments_json": '{"alias":"inputs/manuscript.tex"}'}])
    )
    with pytest.raises(Denied, match="uncertain"):
        run.step(frames)
    attempts = run.accounting()["attempts"]
    assert len(attempts) == (1 if at_count else 2)
    assert attempts[-1]["state"] == "uncertain" and attempts[-1]["charged"] is None
    assert run._tools == 0
    with pytest.raises(Denied):
        run.step([count_frame(), response(contract)])
    assert run.finish()["state"] == "uncertain"


@pytest.mark.parametrize(
    "changes", [{"model": "wrong"}, {"store": True}, {"id": "../invalid"}, {"usage": None}]
)
def test_untrusted_terminal_evidence_cannot_release_reservation(factory, contract, changes):
    run = factory()
    with pytest.raises(Denied, match="uncertain"):
        run.step([count_frame(), response(contract, **changes)])
    assert run.accounting()["attempts"][-1]["state"] == "uncertain"
    assert run._tools == 0


def test_insufficient_generation_budget_releases_no_create(factory, contract):
    limits = replace(contract, cost_ceiling=nanos("0.2"), verification_cost_reserve=nanos("0.1"))
    run = factory(limits)
    with pytest.raises(BudgetDenied):
        run.step([count_frame(), response(limits)])
    assert run.state == "verification_only"
    assert len(run.accounting()["attempts"]) == 1
    assert run.accounting()["attempts"][0]["state"] == "settled"
    operations = [e["event"]["operation"] for e in run._events if e["event"]["type"] == "transport_request"]
    assert operations == ["count"]


def test_bound_count_replaces_synthetic_input_allowance(factory, contract):
    # The priced path uses the exact count, not the previous synthetic ceiling.
    limits = replace(contract, input_token_allowance=1)
    run = factory(limits)
    assert run.step([count_frame(), response(limits)])["state"] == "completed"


def test_valid_tool_request_runs_only_after_priced_settlement(factory, contract):
    run = factory()
    reply = run.step(
        [
            count_frame(),
            response(
                contract,
                final=False,
                tools=[{"name": "read", "arguments_json": '{"alias":"inputs/manuscript.tex"}'}],
            ),
        ]
    )
    assert reply["tools"][0]["ok"]
    assert all(a["state"] == "settled" for a in run.accounting()["attempts"])
    second = response(contract, id="resp_second")
    assert run.step([count_frame(), second])["state"] == "completed"
    assert len(run.accounting()["attempts"]) == 4


def test_tariff_or_private_journal_mutation_blocks_new_dispatch(factory, contract, tmp_path):
    run = factory()
    run.step([count_frame(), response(contract, final=False)])
    (tmp_path / "run/event-0001.json").write_text("{}")
    with pytest.raises(Denied, match="journal changed"):
        run.step([count_frame(), response(contract)])
    assert len(run.accounting()["attempts"]) == 2


def test_count_mismatch_remains_uncertain(factory, contract):
    run = factory()
    with pytest.raises(Denied, match="uncertain"):
        run.step([count_frame(121), response(contract)])
    assert run.accounting()["attempts"][-1]["state"] == "uncertain"


def test_missing_count_http_identity_remains_uncertain(factory, contract):
    run = factory()
    frame = count_frame()
    frame["http_request_id"] = ""
    with pytest.raises(Denied, match="uncertain"):
        run.step([frame, response(contract)])
    assert run.accounting()["attempts"][0]["state"] == "uncertain"


@pytest.mark.parametrize("operation", ["count", "create"])
def test_absent_sdk_http_identity_cannot_settle(factory, contract, monkeypatch, operation):
    original = MockResponsesProcess.exchange

    def without_identity(transport, op, **kwargs):
        reply = original(transport, op, **kwargs)
        if op == operation:
            reply["http_request_id"] = None
        return reply

    monkeypatch.setattr(MockResponsesProcess, "exchange", without_identity)
    run = factory()
    with pytest.raises(Denied, match="uncertain"):
        run.step([count_frame(), response(contract)])
    assert run.accounting()["attempts"][-1]["state"] == "uncertain"


def test_priced_poll_exhaustion_cancels_with_reserved_fee(factory, contract):
    limits = replace(contract, max_polls=1)
    run = factory(limits)
    reply = run.step(
        [
            count_frame(),
            response(limits, status="queued", usage=None),
            response(limits, status="in_progress", usage=None),
            response(limits, status="cancelled"),
        ]
    )
    assert reply["state"] == "cancelled" and reply["tools"] == []
    assert reply["cost_upper_units"] == 120 * 47000 + 80 * 75000 + 22


def test_priced_invalid_payload_settles_without_tool_dispatch(factory, contract):
    run = factory()
    frame = response(contract)
    frame["body"]["output"][0]["content"][0]["text"] = "invalid JSON"
    assert run.step([count_frame(), frame])["state"] == "invalid_output"
    assert all(a["state"] == "settled" for a in run.accounting()["attempts"])
    assert run._tools == 0
