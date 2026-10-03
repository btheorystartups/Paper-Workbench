"""Synthetic paired workflow tests; no real manuscript, account or default DB."""

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from test_evaluation_responses import response

from workbench.providers.evaluation_responses import MockResponsesProcess
from workbench.services.evaluation import AttemptLedger, Denied, digest, encoded
from workbench.services.evaluation_costs import Tariff
from workbench.services.evaluation_pair import SCHEDULE, PairedEvaluation
from workbench.services.evaluation_responses import ResponsesContract


@pytest.fixture
def factory(tmp_path):
    def make(tariff=None, **changes):
        inputs = {
            "inputs/manuscript.tex": b"ORIGINAL_SYNTHETIC_SOURCE",
            "inputs/historical_verification_record.txt": b"UNVERIFIED_RECORD",
        }
        contract = ResponsesContract(
            model="synthetic-model",
            cost_ceiling=200000,
            token_ceiling=40000,
            verification_cost_reserve=50000,
            verification_token_reserve=10000,
            max_turns=12,
            max_tool_calls=50,
            input_token_allowance=1000,
            max_output_tokens=400,
            max_seconds=300,
        )
        return PairedEvaluation(
            tmp_path / "pair",
            inputs=inputs,
            expected={k: digest(v) for k, v in inputs.items()},
            brief="Neutral synthetic brief",
            contract=replace(contract, **changes),
            tariff=tariff,
        )

    return make


def payload(pair):
    arm, role = ("B0", "B1")[pair._arm], SCHEDULE[pair._index][0]
    report = f"{arm}_{role}_PRIVATE_FINDING"
    if role in {"initial", "revision1", "revision2"}:
        value = {"report": report, "candidate_tex": f"{arm}_{role}_CANDIDATE"}
        if arm == "B1":
            value["records"] = (
                []
                if role == "initial"
                else [
                    {
                        "issue_id": "R1-1" if role == "revision1" else "R2-1",
                        "disposition": "unresolved",
                        "reason": "Synthetic limitation",
                        "before_location": "line 1",
                        "after_location": "line 1",
                        "regression_check": "Not executed",
                    }
                ]
            )
    else:
        value = {"report": report}
        if arm == "B1" and role != "final":
            value["issues"] = [
                {
                    "id": "R1-1" if role == "review1" else "R2-1",
                    "objection": "Synthetic issue",
                    "location": "line 1",
                    "evidence_sha256": [pair._packet(arm, role)["candidate_sha256"]],
                }
            ]
        elif arm == "B1":
            value["verdicts"] = [
                {
                    "issue_id": i,
                    "status": "unresolved",
                    "reason": "Synthetic",
                    "regression_check": "Not executed",
                }
                for i in ("R1-1", "R2-1")
            ]
    return value


def frame(pair, value=None, **changes):
    return response(pair._contract, text=json.dumps(value if value is not None else payload(pair)), **changes)


def test_full_pair_actual_sdk_fresh_contexts_grants_and_export(factory, monkeypatch):
    pair = factory()
    original = MockResponsesProcess.exchange
    seen = []
    namespaces = set()

    def inspect(transport, operation, **kwargs):
        if operation == "create":
            arm = ("B0", "B1")[pair._arm]
            attempts = pair.accounting()[arm]["attempts"]
            assert attempts[-1]["state"] == "dispatched"  # Parent held before child HTTP.
            active = pair._active
            assert active._diagnostic.namespace not in namespaces
            namespaces.add(active._diagnostic.namespace)
            body = kwargs["body"]
            assert len(body["input"]) == 2 and body["tools"] == []
            assert active._diagnostic.tool("conversation")[0]["content"] == body["input"][0]["content"]
            assert active._diagnostic._cache == {}
            seen.append((arm, SCHEDULE[pair._index][0], body["input"][0]["content"]))
        return original(transport, operation, **kwargs)

    monkeypatch.setattr(MockResponsesProcess, "exchange", inspect)
    for _ in range(12):
        pair.step([frame(pair)])
    assert pair.state == "completed" and len(namespaces) == 12
    for arm, role, prompt in seen:
        other = "B1" if arm == "B0" else "B0"
        assert f"{other}_" not in prompt
        if role.startswith("review"):
            assert f"{arm}_initial_PRIVATE_FINDING" in prompt
            assert f"{arm}_review1_PRIVATE_FINDING" not in prompt
            assert "ORIGINAL_SYNTHETIC_SOURCE" in prompt
            assert "UNVERIFIED_RECORD" in prompt
        if role == "final":
            assert f"{arm}_review1_PRIVATE_FINDING" in prompt
            assert f"{arm}_review2_PRIVATE_FINDING" in prompt
    accounting = pair.accounting()
    for arm, ledger in accounting.items():
        attempts = ledger["attempts"]
        assert len(attempts) == 6 and all(a["state"] == "settled" for a in attempts)
        spent = tokens = work_spent = 0
        for attempt in attempts:
            assert spent + attempt["reserved"] <= 200000
            assert tokens + attempt["tokens_reserved"] <= 40000
            if attempt["phase"] == "work":
                assert work_spent + attempt["reserved"] <= 150000
                work_spent += attempt["charged"]
            spent += attempt["charged"]
            tokens += attempt["tokens_charged"]
        assert attempts[1]["reserved"] > 50000 // 3  # Settled unused work capacity carries forward.
        assert sum(a["charged"] for a in attempts) == 6 * 280
        assert AttemptLedger(pair._directory / f"{arm}.sqlite").snapshot() == ledger
    source = (pair._directory / "B1-revision1-result.json").read_bytes()
    revision_result = json.loads(source)
    row = revision_result["records"][0]
    assert row["before_sha256"] == digest(b"B1_initial_CANDIDATE")
    assert row["after_sha256"] == digest(b"B1_revision1_CANDIDATE")
    assert revision_result["diagnostic_status"] == "accepted"
    final_result = json.loads((pair._directory / "B1-final-result.json").read_bytes())
    assert not final_result["release_eligibility"]["eligible"]
    assert {row["code"] for row in final_result["release_eligibility"]["blockers"]} == {
        "unresolved_final_verdicts"
    }
    assert pair.finish()["state"] == "completed"
    assert (pair._directory / "capture/B1-candidate.tex").read_bytes() == b"B1_revision2_CANDIDATE"
    assert pair._inputs["inputs/manuscript.tex"] == b"ORIGINAL_SYNTHETIC_SOURCE"
    with pytest.raises(Denied):
        pair.finish()


def test_generation_slots_cannot_spill_into_next_role(factory):
    pair = factory()
    for i in range(3):
        pair.step([frame(pair, final=False, id=f"resp_{i}")])
    assert pair.state == "stopped_partial"
    assert len(pair.accounting()["B0"]["attempts"]) == 1
    assert not pair.accounting()["B1"]["attempts"]
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert pair.finish()["state"] == "stopped_partial"
    assert not (pair._directory / "capture/B0-candidate.tex").exists()


def test_uncertain_usage_keeps_entire_parent_grant_and_stops_pair(factory):
    pair = factory()
    with pytest.raises(Denied):
        pair.step([{"fault": "exit"}])
    attempt = pair.accounting()["B0"]["attempts"][0]
    assert attempt["state"] == "uncertain" and attempt["reserved"] == 50000
    assert attempt["charged"] is None and pair.state == "uncertain"
    assert pair.finish()["state"] == "uncertain"
    with pytest.raises(FileExistsError):
        factory()


@pytest.mark.parametrize("mutation", ["../escape.tex", "report", "extra"])
def test_invalid_role_output_is_charged_but_never_promoted(factory, mutation):
    pair = factory()
    value = payload(pair)
    if mutation == "report":
        value["report"] = ""
    else:
        value[mutation] = "UNTRUSTED"
    with pytest.raises(Denied):
        pair.step([frame(pair, value)])
    assert pair.accounting()["B0"]["attempts"][0]["charged"] == 280
    assert pair.state == "stopped_partial"
    assert not (pair._directory / "B0-initial-candidate.tex").exists()


def test_frozen_candidate_tampering_prevents_next_dispatch(factory, monkeypatch):
    pair = factory()
    pair.step([frame(pair)])
    (pair._directory / "B0-initial-candidate.tex").write_bytes(b"TAMPERED")
    monkeypatch.setattr(MockResponsesProcess, "start", lambda *a, **k: pytest.fail("must not dispatch"))
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert len(pair.accounting()["B0"]["attempts"]) == 1


def test_protected_money_and_token_limits_cannot_be_changed(factory, monkeypatch):
    pair = factory()
    with sqlite3.connect(pair._directory / "B0.sqlite") as conn:
        conn.execute("UPDATE limits SET cost_reserve=0")
    monkeypatch.setattr(MockResponsesProcess, "start", lambda *a, **k: pytest.fail("must not dispatch"))
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert not pair.accounting()["B0"]["attempts"]


def test_cancel_before_dispatch_and_no_resume(factory):
    pair = factory()
    pair.cancel()
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert not pair.accounting()["B0"]["attempts"]


def test_concurrent_calls_are_serial_and_stage_selected_by_controller(factory):
    pair = factory()
    first = frame(pair)
    second = frame(pair, {"report": "Fresh report"})
    with ThreadPoolExecutor(2) as pool:
        # Submit second while first owns the lock; waiting call cannot choose another arm.
        started = threading.Event()
        original = pair._start

        def start():
            original()
            started.set()

        pair._start = start
        a = pool.submit(pair.step, [first])
        assert started.wait(10)
        b = pool.submit(pair.step, [second])
        a.result(timeout=30)
        b.result(timeout=30)
    assert pair.status()["stage"] == "revision1"
    assert [a["phase"] for a in pair.accounting()["B0"]["attempts"]] == ["work", "verification"]


@pytest.mark.parametrize(
    "change",
    [
        dict(max_turns=13),
        dict(max_tool_calls=51),
        dict(verification_cost_reserve=40000),
        dict(verification_token_reserve=9999),
    ],
)
def test_asymmetric_or_unprotected_allocations_rejected(factory, change):
    with pytest.raises(Denied):
        factory(**change)


def test_structured_issue_coverage_and_evidence_rejected(factory):
    pair = factory()
    # Unit-level adversarial packets need no provider dispatch.
    pair._arm = 1
    pair._index = 1
    initial = {
        "role": "initial",
        "report": "S",
        "candidate_tex": "S",
        "candidate_sha256": digest(b"S"),
        "records": [],
    }
    pair._save("B1-initial-result.json", encoded(initial))
    pair._stage_results["B1"].append("B1-initial-result.json")
    value = payload(pair)
    value["issues"][0]["evidence_sha256"] = ["f" * 64]
    with pytest.raises(Denied, match="evidence"):
        pair._validate_result(json.dumps(value), "B1", "review1")
    value = payload(pair)
    review = pair._validate_result(json.dumps(value), "B1", "review1")
    pair._save("B1-review1-result.json", encoded(review))
    pair._stage_results["B1"].append("B1-review1-result.json")
    pair._index = 2
    value = payload(pair)
    value["records"] = []
    with pytest.raises(Denied, match="coverage"):
        pair._validate_result(json.dumps(value), "B1", "revision1")


def test_parent_reservation_survives_child_creation_failure(factory, monkeypatch):
    pair = factory()

    def fail(*args, **kwargs):
        raise OSError("synthetic failure")

    monkeypatch.setattr("workbench.services.evaluation_pair.ResponsesEvaluation", fail)
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert pair.state == "uncertain"
    assert pair.accounting()["B0"]["attempts"][0]["state"] == "dispatched"
    assert pair.finish()["state"] == "uncertain"


def test_priced_child_count_and_generation_both_settle_parent(factory):
    tariff = Tariff(
        model="synthetic-model",
        input_nanos=1,
        cached_nanos=1,
        cache_write_nanos=1,
        output_nanos=2,
        auxiliary_request_nanos=3,
        source_url="https://developers.openai.com/api/docs/pricing",
        checked_date="2026-10-03",
        account_scope="standard-global-text-only",
        auxiliary_basis="synthetic fixture only",
    )
    pair = factory(tariff=tariff)
    pair.step(
        [
            {
                "body": {"object": "response.input_tokens", "input_tokens": 120},
                "http_request_id": "req_count",
            },
            frame(pair),
        ]
    )
    charge = pair.accounting()["B0"]["attempts"][0]
    assert charge["charged"] == 523 and charge["tokens_charged"] == 200
    assert pair.finish()["state"] == "stopped_partial"


def test_wall_clock_expiry_does_not_start_child(factory, monkeypatch):
    pair = factory()
    pair._deadlines["B0"] = 0
    monkeypatch.setattr(MockResponsesProcess, "start", lambda *a, **k: pytest.fail("must not dispatch"))
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert not pair.accounting()["B0"]["attempts"]


def test_insufficient_child_reservation_sends_no_http(factory, monkeypatch):
    pair = factory(input_token_allowance=100000)
    monkeypatch.setattr(MockResponsesProcess, "start", lambda *a, **k: pytest.fail("must not dispatch"))
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert pair.accounting()["B0"]["attempts"][0]["charged"] == 0


def test_candidate_capture_failure_keeps_parent_grant(factory, monkeypatch):
    pair = factory()
    save = pair._save

    def fail_candidate(name, data):
        if name.endswith("candidate.tex"):
            raise OSError("synthetic disk failure")
        save(name, data)

    monkeypatch.setattr(pair, "_save", fail_candidate)
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert pair.state == "uncertain"
    assert pair.accounting()["B0"]["attempts"][0]["charged"] is None
    assert pair._stage_results["B0"] == []


def test_tampering_during_child_does_not_promote_next_result(factory, monkeypatch):
    pair = factory()
    pair.step([frame(pair)])
    original = MockResponsesProcess.exchange

    def tamper(transport, operation, **kwargs):
        result = original(transport, operation, **kwargs)
        (pair._directory / "B0-initial-result.json").write_bytes(b"{}")
        return result

    monkeypatch.setattr(MockResponsesProcess, "exchange", tamper)
    with pytest.raises(Denied):
        pair.step([frame(pair)])
    assert len(pair._stage_results["B0"]) == 1


def test_priced_review_cannot_borrow_protected_future_grants(factory, monkeypatch):
    tariff = Tariff(
        model="synthetic-model",
        input_nanos=100,
        cached_nanos=100,
        cache_write_nanos=100,
        output_nanos=100,
        auxiliary_request_nanos=3,
        source_url="https://developers.openai.com/api/docs/pricing",
        checked_date="2026-10-03",
        account_scope="standard-global-text-only",
        auxiliary_basis="synthetic fixture only",
    )
    pair = factory(tariff=tariff, max_output_tokens=100)
    count = {"body": {"object": "response.input_tokens", "input_tokens": 120}, "http_request_id": "req_count"}
    pair.step([count, frame(pair)])
    assert pair.accounting()["B0"]["attempts"][0]["charged"] == 44003
    original = MockResponsesProcess.exchange
    seen = []

    def observe(transport, operation, **kwargs):
        seen.append(operation)
        return original(transport, operation, **kwargs)

    monkeypatch.setattr(MockResponsesProcess, "exchange", observe)
    with pytest.raises(Denied):
        pair.step([count, frame(pair)])
    assert seen == ["count"]  # Count fee is charged; oversized generation never dispatches.
    attempts = pair.accounting()["B0"]["attempts"]
    assert attempts[1]["charged"] == 3 and attempts[1]["reserved"] < 23000
    assert pair.state == "stopped_partial"
