import copy
from dataclasses import replace

import pytest

from workbench.providers.evaluation_gateway import BudgetedGateway, GatewayPermit, usd_binding
from workbench.services.evaluation import AttemptLedger, Denied, digest, encoded
from workbench.services.evaluation_costs import InputCount, PricedAttempt, Tariff, count_payload, nanos
from workbench.services.evaluation_responses import ResponsesContract, request_body


@pytest.fixture
def body():
    contract = ResponsesContract(
        model="synthetic-model",
        cost_ceiling=100000,
        token_ceiling=100000,
        verification_cost_reserve=25000,
        verification_token_reserve=25000,
    )
    return request_body(contract, [{"role": "user", "content": "Synthetic"}])


@pytest.fixture
def count(body):
    return InputCount.from_response(
        body,
        {"object": "response.input_tokens", "input_tokens": 300},
        client_request_id="count-1",
        http_request_id="req_synthetic",
    )


@pytest.fixture
def tariff():
    return Tariff(
        model="synthetic-model",
        input_nanos=20_000,
        cached_nanos=2_000,
        cache_write_nanos=25_000,
        output_nanos=75_000,
        auxiliary_request_nanos=11,
        source_url="https://developers.openai.com/api/docs/pricing",
        checked_date="2026-10-03",
        account_scope="standard-global-text-only",
        auxiliary_basis="synthetic fixture only; no account fee asserted",
    )


@pytest.mark.parametrize(
    "value,expected", [("0", 0), ("1", 1000000000), ("0.000000001", 1), ("30.00", 30000000000)]
)
def test_exact_usd(value, expected):
    assert nanos(value) == expected


@pytest.mark.parametrize("value", [0.1, True, "NaN", "-1", "1e2", "0.0000000001", "100000000000000"])
def test_invalid_usd_refused(value):
    with pytest.raises(Denied):
        nanos(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("instructions", "changed"),
        ("max_output_tokens", 5000),
        ("model", "different"),
        ("reasoning", {"effort": "low"}),
        ("text", {"format": {"type": "text"}}),
    ],
)
def test_count_bound_to_all_generation_fields(body, count, field, value):
    body[field] = value
    with pytest.raises(Denied):
        count.validate_request(body)


@pytest.mark.parametrize(
    "field,value",
    [
        ("previous_response_id", "resp_old"),
        ("conversation", "old"),
        (
            "input",
            [{"role": "user", "content": [{"type": "input_file", "file_url": "https://hidden.invalid"}]}],
        ),
        ("tools", [{"type": "web_search"}]),
        ("service_tier", "priority"),
        ("truncation", "auto"),
    ],
)
def test_unpriced_or_remote_capabilities_denied(body, field, value):
    body[field] = value
    with pytest.raises(Denied):
        count_payload(body)


def test_schema_instructions_and_tool_policy_included_in_count(body):
    projection = count_payload(body)
    assert projection["text"] == body["text"]
    assert projection["instructions"] == body["instructions"]
    assert projection["tools"] == []
    assert set(body) - set(projection) == {"max_output_tokens", "background", "store", "service_tier"}


def test_conservative_cache_and_long_context_cost(body, count, tariff):
    quote = tariff.reserve(body, count, maximum_auxiliary_requests=3)
    assert quote["cost_nanos"] == 300 * 47000 + 4000 * 75000 + 33
    settled = tariff.reconcile_upper(
        body,
        count,
        {
            "input_tokens": 300,
            "output_tokens": 100,
            "total_tokens": 400,
            "output_tokens_details": {"reasoning_tokens": 75},
        },
        auxiliary_requests=2,
        maximum_auxiliary_requests=3,
    )
    assert settled["cost_nanos"] == 300 * 47000 + 100 * 75000 + 22
    assert settled["tokens"] == 400


@pytest.mark.parametrize(
    "changes",
    [
        {"input_tokens": 299},
        {"input_tokens": 301},
        {"output_tokens": 5000},
        {"total_tokens": 999},
        {"input_tokens": True},
    ],
)
def test_usage_disagreement_fails_closed(body, count, tariff, changes):
    usage = {"input_tokens": 300, "output_tokens": 100, "total_tokens": 400, **changes}
    with pytest.raises(Denied):
        tariff.reconcile_upper(body, count, usage, auxiliary_requests=1, maximum_auxiliary_requests=3)


@pytest.mark.parametrize(
    "changes",
    [{"auxiliary_basis": ""}, {"account_scope": "regional"}, {"output_nanos": -1}, {"input_nanos": 0}],
)
def test_unqualified_tariff_refused(tariff, changes):
    with pytest.raises(Denied):
        replace(tariff, **changes).validate()


def test_priced_ledger_reserve_settle_and_protected_capacity(tmp_path, body, count, tariff):
    ledger = AttemptLedger.create(
        tmp_path / "ledger.sqlite",
        ceiling=nanos("1"),
        token_ceiling=10000,
        cost_reserve=nanos("0.5"),
        token_reserve=4500,
        binding_hash="a" * 64,
    )
    priced = PricedAttempt(
        ledger, attempt_id="attempt-1", body=body, count=count, tariff=tariff, maximum_auxiliary_requests=3
    )
    assert ledger.snapshot()["attempts"][0]["state"] == "pending"
    priced.dispatch()
    priced.reconcile({"input_tokens": 300, "output_tokens": 100, "total_tokens": 400}, auxiliary_requests=1)
    assert ledger.snapshot()["attempts"][0]["state"] == "settled"
    # Conservation includes protected resources, not just recorded actual spend.
    second = PricedAttempt(
        ledger, attempt_id="attempt-2", body=body, count=count, tariff=tariff, maximum_auxiliary_requests=3
    )
    second.dispatch()
    with pytest.raises(Denied):
        PricedAttempt(
            ledger,
            attempt_id="attempt-3",
            body=body,
            count=count,
            tariff=tariff,
            maximum_auxiliary_requests=3,
        )
    with pytest.raises(Denied):
        second.reconcile(None, auxiliary_requests=1)
    item = ledger.snapshot()["attempts"][1]
    assert item["state"] == "uncertain" and item["charged"] is None


def message(body, op, payload, identity="request-1"):
    return {
        "operation": op,
        "client_request_id": identity,
        "request_sha256": digest(encoded(body)),
        "payload": payload,
    }


def test_gateway_state_machine_and_owned_responses(body):
    permit = GatewayPermit(body, maximum_operations=4)
    with pytest.raises(Denied):
        permit.admit(message(body, "create", body))
    route = permit.admit(message(body, "count", count_payload(body)))
    assert route["path"] == "/v1/responses/input_tokens"
    with pytest.raises(Denied):
        permit.admit(message(body, "count", count_payload(body)))
    permit.acknowledge(success=True)
    permit.admit(message(body, "create", body, "request-2"))
    permit.acknowledge(success=True, response_id="resp_owned")
    with pytest.raises(Denied):
        permit.admit(message(body, "retrieve", {"response_id": "resp_other"}, "request-3"))
    assert (
        permit.admit(message(body, "retrieve", {"response_id": "resp_owned"}, "request-3"))["method"] == "GET"
    )
    permit.acknowledge(success=True)
    permit.admit(message(body, "cancel", {"response_id": "resp_owned"}, "request-4"))
    permit.acknowledge(success=True)
    with pytest.raises(Denied):
        permit.admit(message(body, "cancel", {"response_id": "resp_owned"}, "request-5"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("url", "https://hidden.invalid"),
        ("headers", {"Authorization": "injected"}),
        ("request_sha256", "b" * 64),
    ],
)
def test_gateway_cannot_choose_destination_or_auth(body, field, value):
    permit = GatewayPermit(body, maximum_operations=4)
    packet = message(body, "count", count_payload(body))
    packet[field] = value
    with pytest.raises(Denied):
        permit.admit(packet)


def test_gateway_failure_disables_generation(body):
    permit = GatewayPermit(body, maximum_operations=4)
    permit.admit(message(body, "count", count_payload(body)))
    permit.acknowledge(success=False)
    with pytest.raises(Denied):
        permit.admit(message(body, "create", body, "request-2"))


def test_gateway_body_is_detached_and_mutation_denied(body):
    original = copy.deepcopy(body)
    permit = GatewayPermit(body, maximum_operations=4)
    body["instructions"] = "changed"
    with pytest.raises(Denied):
        permit.admit(message(original, "count", count_payload(body)))


@pytest.mark.parametrize("changes", [{"source_url": None}, {"checked_date": None}, {"auxiliary_basis": True}])
def test_malformed_tariff_evidence_denied(tariff, changes):
    with pytest.raises(Denied):
        replace(tariff, **changes).validate()


def test_projection_and_gateway_route_are_detached(body):
    projection = count_payload(body)
    projection["input"][0]["content"] = "mutation"
    assert body["input"][0]["content"] == "Synthetic"
    permit = GatewayPermit(body, maximum_operations=4)
    payload = count_payload(body)
    route = permit.admit(message(body, "count", payload))
    payload["input"][0]["content"] = "mutation"
    assert route["payload"]["input"][0]["content"] == "Synthetic"


@pytest.fixture
def usd_ledger(tmp_path, tariff):
    return AttemptLedger.create(
        tmp_path / "usd.sqlite",
        ceiling=nanos("1"),
        token_ceiling=10000,
        cost_reserve=nanos("0.5"),
        token_reserve=4500,
        binding_hash=usd_binding(tariff, "a" * 64),
    )


def budgeted(body, tariff, ledger, attempt="gateway-1"):
    return BudgetedGateway(
        body, ledger=ledger, tariff=tariff, run_binding="a" * 64, attempt_id=attempt, maximum_operations=4
    )


def admit_count(gateway, body):
    gateway.admit(message(body, "count", count_payload(body)))


def acknowledge_count(gateway):
    gateway.acknowledge(
        success=True,
        result={"object": "response.input_tokens", "input_tokens": 300},
        http_request_id="req_count",
    )


def test_gateway_reserves_before_each_upstream_route(body, tariff, usd_ledger):
    gateway = budgeted(body, tariff, usd_ledger)
    admit_count(gateway, body)
    assert usd_ledger.snapshot()["attempts"][0]["state"] == "dispatched"
    assert usd_ledger.snapshot()["attempts"][0]["reserved"] == 11
    acknowledge_count(gateway)
    gateway.admit(message(body, "create", body, "request-2"))
    attempts = usd_ledger.snapshot()["attempts"]
    assert [a["state"] for a in attempts] == ["settled", "dispatched"]
    assert attempts[1]["reserved"] == 300 * 47000 + 4000 * 75000 + 22
    gateway.acknowledge(success=True, result={"id": "resp_owned"})
    gateway.admit(message(body, "retrieve", {"response_id": "resp_owned"}, "request-3"))
    gateway.acknowledge(success=True)
    gateway.settle({"input_tokens": 300, "output_tokens": 10, "total_tokens": 310})
    assert usd_ledger.snapshot()["attempts"][1]["charged"] == 300 * 47000 + 10 * 75000 + 11
    with pytest.raises(Denied):
        gateway.admit(message(body, "cancel", {"response_id": "resp_owned"}, "request-4"))


@pytest.mark.parametrize("stage", ["count", "create", "retrieve", "settle"])
def test_budgeted_uncertainty_blocks_new_generation(body, tariff, usd_ledger, stage):
    gateway = budgeted(body, tariff, usd_ledger)
    admit_count(gateway, body)
    if stage != "count":
        acknowledge_count(gateway)
        gateway.admit(message(body, "create", body, "request-2"))
    if stage in {"retrieve", "settle"}:
        gateway.acknowledge(success=True, result={"id": "resp_owned"})
    if stage == "retrieve":
        gateway.admit(message(body, "retrieve", {"response_id": "resp_owned"}, "request-3"))
    with pytest.raises(Denied):
        if stage == "settle":
            gateway.settle(None)
        else:
            gateway.acknowledge(success=False)
    assert usd_ledger.snapshot()["attempts"][-1]["state"] == "uncertain"
    with pytest.raises(Denied):
        admit_count(budgeted(body, tariff, usd_ledger, "gateway-2"), body)


def test_budgeted_count_without_provider_identity_retains_reservation(body, tariff, usd_ledger):
    gateway = budgeted(body, tariff, usd_ledger)
    admit_count(gateway, body)
    with pytest.raises(Denied):
        gateway.acknowledge(success=True, result={"object": "response.input_tokens", "input_tokens": 300})
    assert usd_ledger.snapshot()["attempts"][0]["state"] == "uncertain"


def test_budgeted_different_tariff_or_run_denied(body, tariff, usd_ledger):
    with pytest.raises(Denied):
        budgeted(body, replace(tariff, output_nanos=1), usd_ledger)
    with pytest.raises(Denied):
        BudgetedGateway(
            body,
            ledger=usd_ledger,
            tariff=tariff,
            run_binding="b" * 64,
            attempt_id="gateway-1",
            maximum_operations=4,
        )


def test_budgeted_insufficient_generation_budget_sends_no_route(tmp_path, body, tariff):
    ledger = AttemptLedger.create(
        tmp_path / "small.sqlite",
        ceiling=100,
        token_ceiling=10000,
        binding_hash=usd_binding(tariff, "a" * 64),
    )
    gateway = budgeted(body, tariff, ledger)
    admit_count(gateway, body)
    acknowledge_count(gateway)
    with pytest.raises(Denied):
        gateway.admit(message(body, "create", body, "request-2"))
    assert len(ledger.snapshot()["attempts"]) == 1


def test_budgeted_restart_cannot_redispatch_pending_count(body, tariff, usd_ledger):
    admit_count(budgeted(body, tariff, usd_ledger), body)
    with pytest.raises(Denied):
        admit_count(budgeted(body, tariff, usd_ledger), body)
