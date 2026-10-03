import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from workbench.services.evaluation import (
    AttemptLedger,
    Denied,
    Diagnostic,
    capture,
    container_command,
    digest,
)


def diagnostic():
    inputs = {
        "inputs/manuscript.tex": b"Synthetic manuscript\nA claim",
        "inputs/historical_verification_record.txt": b"An unverified historical count",
    }
    return Diagnostic(inputs, {k: digest(v) for k, v in inputs.items()}, brief="Review the admitted inputs")


@pytest.mark.parametrize(
    "alias",
    [
        "../hidden",
        "inputs/../hidden",
        "C:\\hidden.txt",
        "/etc/passwd",
        "inputs/manuscript.tex:secret",
        "inputs/link/hidden",
        "inputs/junction/hidden",
    ],
)
def test_read_has_no_host_path_interpretation(alias):
    run = diagnostic()
    with pytest.raises(Denied, match="tool request denied"):
        run.tool("read", alias=alias)
    receipt = run.freeze({"report.md": b"scoped report"})
    assert alias.encode() not in receipt
    assert json.loads(receipt)["trace"] == [{"event": "tool_denied"}]


def test_namespace_tools_and_immutable_capture(tmp_path):
    first, second = diagnostic(), diagnostic()
    assert "Synthetic manuscript" in first.tool("read", alias="inputs/manuscript.tex")
    assert first.tool("retrieve", query="claim")[0]["alias"] == "inputs/manuscript.tex"
    assert first.tool("retrieve", query="HIDDEN_CANARY") == []
    first.tool("cache_put", namespace=first.namespace, key="label", value="HIDDEN_CANARY")
    assert second.tool("cache_get", namespace=second.namespace, key="label") is None
    for name, args in [
        ("network", {"url": "https://hidden"}),
        ("shell", {"cmd": "read hidden"}),
        ("conversation", {"id": first.namespace}),
        ("cache_get", {"namespace": first.namespace, "key": "label"}),
    ]:
        with pytest.raises(Denied):
            second.tool(name, **args)
    assert "HIDDEN_CANARY" not in str(second.tool("conversation"))
    outputs = {"report.md": b"report"}
    receipt = second.freeze(outputs)
    assert b"HIDDEN_CANARY" not in receipt
    with pytest.raises(Denied):
        second.tool("read", alias="inputs/manuscript.tex")
    with pytest.raises(Denied):
        capture(tmp_path / "bad", receipt, {"report.md": b"substituted"})
    capture(tmp_path / "capture", receipt, outputs)
    with pytest.raises(FileExistsError):
        capture(tmp_path / "capture", receipt, outputs)


def test_input_identity_cannot_be_rewritten():
    inputs = {"inputs/manuscript.tex": b"one", "inputs/historical_verification_record.txt": b"two"}
    hashes = {k: digest(v) for k, v in inputs.items()}
    run = Diagnostic(inputs, hashes, brief="Review")
    inputs["inputs/manuscript.tex"] = b"substituted"
    hashes["inputs/manuscript.tex"] = "0" * 64
    assert run.tool("read", alias="inputs/manuscript.tex") == "one"
    with pytest.raises(Denied):
        Diagnostic(inputs, hashes, brief="Review")
    with pytest.raises(Denied):
        diagnostic().freeze({"../hidden.md": b"x"})


def test_concurrent_budget_uncertainty_and_caller_rollback(tmp_path):
    ledger = AttemptLedger.create(tmp_path / "attempts.sqlite", ceiling=10)

    def reserve(i):
        try:
            ledger.reserve(str(i), digest(str(i).encode()), 6)
            return str(i)
        except Denied:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = [v for v in pool.map(reserve, range(2)) if v is not None]
    assert len(winners) == 1
    # Timeout after an uncertain charge: reservation persists, replay cannot dispatch.
    ledger.reconcile(winners[0], None)
    with pytest.raises(Denied, match="reconcile"):
        ledger.reserve(winners[0], digest(b"same"), 1)
    with pytest.raises(Denied, match="uncertain"):
        ledger.reserve("retry", digest(b"retry"), 1)
    ledger.reconcile(winners[0], 4)
    with sqlite3.connect(tmp_path / "caller.sqlite") as caller:
        caller.execute("CREATE TABLE test (id INTEGER)")
        caller.execute("INSERT INTO test VALUES (1)")
        ledger.reserve("next", digest(b"next"), 6)
        caller.rollback()
    with pytest.raises(Denied, match="budget"):
        ledger.reserve("over", digest(b"over"), 1)
    with pytest.raises(Denied, match="already recorded"):
        AttemptLedger(tmp_path / "attempts.sqlite").reserve("next", digest(b"next"), 6)


def test_container_mount_recipe_and_hidden_inputs(tmp_path):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    for name in ("manuscript.tex", "historical_verification_record.txt", "runner.py"):
        (inputs / name).write_text("synthetic")
    args = dict(image="python@sha256:" + "a" * 64, input_dir=inputs, output_dir=outputs, run_id="b" * 32)
    cmd = container_command(**args)
    assert "--network=none" in cmd and "--read-only" in cmd and "--pull=never" in cmd
    assert sum("type=bind" in c for c in cmd) == 2
    (inputs / "hidden.txt").write_text("HIDDEN_CANARY")
    with pytest.raises(Denied, match="input set"):
        container_command(**args)


def test_symlink_denied_in_runtime_and_capture(tmp_path):
    target, link = tmp_path / "target", tmp_path / "link"
    target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("host does not grant symlink creation; junction tested separately on Windows")
    with pytest.raises(Denied, match="path denied"):
        capture(link / "capture", diagnostic().freeze({"report.md": b"report"}), {"report.md": b"report"})


def test_windows_junction_capture_denied(tmp_path):
    import os

    if os.name != "nt":
        pytest.skip("Windows junction test")
    import _winapi

    target, junction = tmp_path / "target", tmp_path / "junction"
    target.mkdir()
    _winapi.CreateJunction(str(target), str(junction))
    assert junction.is_junction()
    with pytest.raises(Denied, match="path denied"):
        capture(junction / "capture", diagnostic().freeze({"report.md": b"report"}), {"report.md": b"report"})
