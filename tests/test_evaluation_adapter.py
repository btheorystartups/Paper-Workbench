import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from workbench.services.evaluation import AttemptLedger, Denied, digest, encoded
from workbench.services.evaluation_adapter import AdapterContract, EvaluationAdapter


def frame(text="Synthetic finding", *, final=True, tools=None, **extra):
    return {"response": {"text": text, "final": final, "tool_calls": tools or []}, **extra}


def tool(name, **arguments):
    return {"name": name, "arguments": arguments}


@pytest.fixture()
def contract():
    return AdapterContract(
        cost_ceiling=100_000,
        token_ceiling=100_000,
        verification_cost_reserve=20_000,
        verification_token_reserve=20_000,
        max_output_tokens=2_000,
    )


@pytest.fixture()
def factory(tmp_path, contract):
    def make(frames=None, *, limits=None, name="run", brief="Review the synthetic paper."):
        inputs = {
            "inputs/manuscript.tex": b"ALLOWED_SYNTHETIC_TEXT",
            "inputs/historical_verification_record.txt": b"UNVERIFIED_RECORD",
        }
        return EvaluationAdapter(
            tmp_path / name,
            inputs=inputs,
            expected={k: digest(v) for k, v in inputs.items()},
            brief=brief,
            contract=limits or contract,
            frames=frames or [frame()],
        )

    return make


def test_tool_roundtrip_reservation_and_frozen_receipts(factory, tmp_path, monkeypatch):
    run = factory(
        [frame(final=False, tools=[tool("read", alias="inputs/manuscript.tex")]), frame("Scoped result")]
    )
    from workbench.providers.evaluation_fake import ScriptedEvaluationProvider

    exchange = ScriptedEvaluationProvider.exchange

    def checked_exchange(provider, request):
        receipt = run.accounting()["attempts"][-1]
        assert receipt["state"] == "dispatched" and receipt["request_recorded"]
        assert receipt["reserved"] > 0 and receipt["tokens_reserved"] > 0
        assert receipt["request_hash"] == digest(encoded(request))
        return exchange(provider, request)

    monkeypatch.setattr(ScriptedEvaluationProvider, "exchange", checked_exchange)
    first = run.step()
    assert first["tools"][0]["result"] == "ALLOWED_SYNTHETIC_TEXT"
    assert "ALLOWED_SYNTHETIC_TEXT" not in encoded(run.provider_requests[0]).decode()
    run.step(phase="verification")
    assert "ALLOWED_SYNTHETIC_TEXT" in encoded(run.provider_requests[1]).decode()
    result = run.finish()
    assert result["outcome"] == "completed" and not result["live_ready"]
    captured = tmp_path / "run/capture"
    receipt = json.loads((captured / "receipt.json").read_text())
    for name, item in receipt["outputs"].items():
        assert digest((captured / name).read_bytes()) == item["sha256"]
    attempts = json.loads((captured / "accounting.json").read_text())["attempts"]
    assert [a["phase"] for a in attempts] == ["work", "verification"]
    assert all(a["state"] == "settled" and a["charged"] <= a["reserved"] for a in attempts)
    assert all(a["tokens_charged"] <= a["tokens_reserved"] and a["result_sha256"] for a in attempts)
    with pytest.raises(Denied):
        run.step()
    with pytest.raises(Denied):
        run.finish()


def test_live_settings_and_registry_cannot_change_transport(factory, monkeypatch):
    from workbench.providers import registry

    def forbidden(*args, **kwargs):
        pytest.fail("ambient provider registry was consulted")

    monkeypatch.setenv("WB_PROVIDER_MODE", "live")
    monkeypatch.setenv("WB_LLM_PROVIDER", "codex_local")
    monkeypatch.setattr(registry, "get_chat_provider", forbidden)
    run = factory()
    run.step()
    assert run.provider_requests[0]["model"] == "fake-byte-tokenizer-v1"
    assert run.finish()["outcome"] == "completed"


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "live"},
        {"model": "gpt-6-astra"},
        {"max_turns": True},
        {"input_rate": -1},
        {"max_seconds": 0},
    ],
)
def test_unsupported_contract_denied_before_creating_run(factory, contract, tmp_path, change):
    with pytest.raises(Denied):
        factory(limits=replace(contract, **change))
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("fault", ["timeout", "interrupt", "error"])
def test_unknown_dispatch_retains_reservation_and_prevents_restart(factory, tmp_path, fault):
    run = factory([{"fault": fault}])
    with pytest.raises(Denied, match="uncertain"):
        run.step()
    with pytest.raises(Denied, match="no automatic retry"):
        run.step(phase="verification")
    assert len(run.provider_requests) == 1
    ledger = AttemptLedger(tmp_path / "run/attempts.sqlite")
    attempt = ledger.snapshot()["attempts"][0]
    assert (
        attempt["state"] == "uncertain" and attempt["charged"] is None and attempt["tokens_charged"] is None
    )
    with pytest.raises(FileExistsError):
        factory()
    with pytest.raises(Denied, match="uncertain"):
        request = {"binding_hash": ledger.snapshot()["limits"]["binding_hash"], "phase": "verification"}
        ledger.reserve("retry", digest(encoded(request)), 1, tokens=1, phase="verification", request=request)
    assert run.finish()["outcome"] == "uncertain"


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": 1},
        {"input_tokens": True, "output_tokens": 1, "cost_units": 1},
        {"input_tokens": 100_000_000, "output_tokens": 1, "cost_units": 1},
    ],
)
def test_incomplete_or_false_usage_stops_without_releasing_budget(factory, usage):
    run = factory([frame(usage_override=usage)])
    with pytest.raises(Denied, match="uncertain"):
        run.step()
    assert run.accounting()["attempts"][0]["state"] == "uncertain"
    assert run.accounting()["attempts"][0]["charged"] is None


def test_hidden_tools_never_reach_provider_context_or_capture(factory, tmp_path):
    canary = "HIDDEN_CANARY_FOR_DENIAL_LOGS"
    run = factory(
        [
            frame(
                final=False,
                tools=[
                    tool("read", alias=f"C:/{canary}.txt"),
                    tool("network", url=f"https://{canary}"),
                    tool("shell", command=canary),
                    tool("cache_get", namespace=canary, key="secret"),
                    tool("conversation", id=canary),
                ],
            ),
            frame(),
        ]
    )
    assert all(r == {"ok": False, "error": "tool request denied"} for r in run.step()["tools"])
    run.step()
    assert canary not in encoded(run.provider_requests).decode()
    run.finish()
    assert all(canary not in p.read_text() for p in (tmp_path / "run/capture").iterdir())
    with sqlite3.connect(tmp_path / "run/attempts.sqlite") as connection:
        assert canary not in str(
            connection.execute("SELECT request_json,result_json FROM attempts").fetchall()
        )


def test_fresh_runs_do_not_share_conversations_or_cache(factory):
    first = factory([frame("FIRST_RUN_PRIVATE_TEXT")])
    first.step()
    second = factory([frame(final=False, tools=[tool("conversation")]), frame()], name="second")
    result = second.step()
    second.step()
    assert "FIRST_RUN_PRIVATE_TEXT" not in encoded(result).decode()
    assert "FIRST_RUN_PRIVATE_TEXT" not in encoded(second.provider_requests).decode()
    assert first.accounting()["limits"]["binding_hash"] != second.accounting()["limits"]["binding_hash"]


def test_protected_verification_and_single_remaining_turn(factory, contract):
    run = factory([frame(final=False), frame()], limits=replace(contract, max_turns=2))
    run.step()
    with pytest.raises(Denied, match="protected verification"):
        run.step()
    assert len(run.provider_requests) == 1
    run.step(phase="verification")
    assert run.state == "completed"


def test_work_reservation_denied_but_verification_is_available(factory, contract):
    run = factory(
        limits=replace(contract, verification_cost_reserve=99_999, verification_token_reserve=99_999)
    )
    with pytest.raises(Denied, match="budget"):
        run.step()
    assert run.state == "verification_only" and not run.provider_requests
    run.step(phase="verification")
    assert run.state == "completed"


def test_context_limit_prevents_dispatch(factory, contract):
    run = factory(limits=replace(contract, max_input_bytes=10), brief="short")
    with pytest.raises(Denied, match="input limit"):
        run.step()
    assert not run.provider_requests and run.accounting()["attempts"] == []
    assert run.finish()["outcome"] == "resource_limit"


def test_cancel_and_elapsed_wall_time_stop_before_dispatch(factory, monkeypatch):
    from workbench.services import evaluation_adapter

    run = factory()
    run.cancel()
    with pytest.raises(Denied):
        run.step()
    assert not run.provider_requests
    second = factory(name="second")
    monkeypatch.setattr(evaluation_adapter.time, "monotonic", lambda: float("inf"))
    with pytest.raises(Denied, match="resource limit"):
        second.step()
    assert not second.provider_requests
    assert second.finish()["outcome"] == "resource_limit"


def test_binding_substitution_is_detected_before_dispatch(factory, tmp_path):
    run = factory()
    (tmp_path / "run/binding.json").write_text("{}")
    with pytest.raises(Denied, match="binding changed"):
        run.step()
    assert not run.provider_requests


def test_bound_ledger_reserves_both_dimensions_across_connections(tmp_path):
    binding = digest(b"binding")
    ledger = AttemptLedger.create(
        tmp_path / "ledger.sqlite", ceiling=100, token_ceiling=10, binding_hash=binding
    )

    def reserve(i):
        request = {"binding_hash": binding, "phase": "work", "logical_request": i}
        try:
            AttemptLedger(ledger.path).reserve(str(i), digest(encoded(request)), 1, tokens=6, request=request)
            return str(i)
        except Denied:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = [value for value in pool.map(reserve, range(2)) if value is not None]
    assert len(winners) == 1
    ledger.dispatch(winners[0])
    with pytest.raises(Denied, match="cannot be dispatched"):
        ledger.dispatch(winners[0])
    ledger.reconcile(winners[0], 1, tokens=6, result={"status": "simulated"})
    request = {"binding_hash": binding, "phase": "work", "logical_request": "over"}
    with pytest.raises(Denied, match="budget"):
        ledger.reserve("over", digest(encoded(request)), 1, tokens=5, request=request)


def test_caller_rollback_does_not_erase_adapter_usage(factory, tmp_path):
    run = factory()
    with sqlite3.connect(tmp_path / "caller.sqlite") as caller:
        caller.execute("CREATE TABLE dummy (value INTEGER)")
        caller.execute("INSERT INTO dummy VALUES (1)")
        run.step()
        caller.rollback()
    persisted = AttemptLedger(tmp_path / "run/attempts.sqlite").snapshot()["attempts"]
    assert len(persisted) == 1 and persisted[0]["state"] == "settled" and persisted[0]["charged"] > 0


def test_old_ledger_is_refused_without_migration(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE limits (ceiling INTEGER)")
    before = path.read_bytes()
    with pytest.raises(Denied, match="unsupported ledger version"):
        AttemptLedger(path).snapshot()
    assert path.read_bytes() == before


def test_dispatch_survives_abrupt_process_exit(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from workbench.services import evaluation

    script = tmp_path / "crash.py"
    script.write_text("""import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from workbench.services.evaluation import AttemptLedger, digest, encoded
binding = digest(b"synthetic binding")
ledger = AttemptLedger.create(Path(sys.argv[2]), ceiling=100, token_ceiling=100, binding_hash=binding)
request = {"binding_hash": binding, "phase": "work"}
ledger.reserve("once", digest(encoded(request)), 10, tokens=10, request=request)
ledger.dispatch("once")
os._exit(17)
""")
    path = tmp_path / "crash.sqlite"
    environment = {
        k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(WB_LOAD_DOTENV="false", PYTHONDONTWRITEBYTECODE="1")
    process = subprocess.run(
        [sys.executable, "-I", "-B", str(script), str(Path(evaluation.__file__).parents[2]), str(path)],
        env=environment,
        timeout=15,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert process.returncode == 17, process.stderr.decode(errors="replace")
    ledger = AttemptLedger(path)
    saved = ledger.snapshot()
    assert saved["attempts"][0]["state"] == "dispatched"
    assert [e["state"] for e in saved["events"]] == ["pending", "dispatched"]
    request = {"binding_hash": saved["limits"]["binding_hash"], "phase": "verification"}
    with pytest.raises(Denied, match="pending attempt"):
        ledger.reserve("new", digest(encoded(request)), 1, tokens=1, phase="verification", request=request)
    with pytest.raises(Denied, match="cannot be dispatched"):
        ledger.dispatch("once")


@pytest.mark.parametrize("timeout", [False, True])
def test_accounting_write_failure_does_not_execute_tools_or_retry(factory, monkeypatch, timeout):
    response = (
        {"fault": "timeout"}
        if timeout
        else frame(final=False, tools=[tool("read", alias="inputs/manuscript.tex")])
    )
    run = factory([response])

    def failed_reconcile(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic persistence failure")

    monkeypatch.setattr(AttemptLedger, "reconcile", failed_reconcile)
    with pytest.raises(Denied, match="uncertain"):
        run.step()
    assert run.state == "uncertain" and len(run.provider_requests) == 1
    assert run.accounting()["attempts"][0]["state"] == "dispatched"
    with pytest.raises(Denied, match="no automatic retry"):
        run.step()
    assert run.finish()["outcome"] == "uncertain"


def test_tool_and_output_limits_preserve_usage(factory, contract):
    run = factory(
        [frame(final=False, tools=[tool("conversation"), tool("conversation")])],
        limits=replace(contract, max_tool_calls=1),
    )
    with pytest.raises(Denied, match="tool count limit"):
        run.step()
    assert run.accounting()["attempts"][0]["state"] == "settled"
    assert run.finish()["outcome"] == "resource_limit"
    oversized = factory([frame("x" * 3_000)], name="oversized")
    with pytest.raises(Denied, match="uncertain"):
        oversized.step()
    assert oversized.accounting()["attempts"][0]["charged"] is None


def test_tampered_ledger_limits_cannot_increase_budget(factory, tmp_path):
    run = factory()
    with sqlite3.connect(tmp_path / "run/attempts.sqlite") as connection:
        connection.execute("UPDATE limits SET ceiling=ceiling*2")
    with pytest.raises(Denied, match="ledger limits changed"):
        run.step()
    assert not run.provider_requests


def test_reconciliation_preserves_uncertainty_history_and_no_redispatch(factory, tmp_path):
    run = factory([{"fault": "timeout"}])
    with pytest.raises(Denied):
        run.step()
    ledger = AttemptLedger(tmp_path / "run/attempts.sqlite")
    attempt = ledger.snapshot()["attempts"][0]
    ledger.reconcile(attempt["id"], 1, tokens=1, result={"operator_reconciliation": "synthetic receipt"})
    assert [e["state"] for e in ledger.snapshot()["events"]] == [
        "pending",
        "dispatched",
        "uncertain",
        "settled",
    ]
    with pytest.raises(Denied, match="cannot be dispatched"):
        ledger.dispatch(attempt["id"])
    with pytest.raises(Denied, match="no automatic retry"):
        run.step()
