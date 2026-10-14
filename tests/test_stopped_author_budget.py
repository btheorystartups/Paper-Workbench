"""Observed interrupted usage must inform recovery without releasing protected reserves."""

from types import SimpleNamespace

from workbench.services.manuscript_quality_runner import _revision_budget


def test_stopped_actual_author_usage_is_forecast_and_review_capacity_is_preserved():
    allocation = {"phase": "revise", "agent_id": "author", "operation_kind": "revise",
                  "actual_tokens": 315588, "usage_kind": "actual"}
    runner = SimpleNamespace(
        task=SimpleNamespace(contract={"token_limit": 650000},
                             ledger={"previous_runs": [{"ledger": {"allocations": [allocation]}}]}),
        allocations=[], agents=[], remaining_tokens=lambda: 650000,
    )
    plan = _revision_budget(runner)
    assert plan["minimum_author_grant"] == 394485
    assert plan["capacity_status"] == "funded"
    assert plan["author_grant"] > 650000 // 4
    assert sum(plan[key] for key in
               ("author_grant", "review_reserve", "repair_reserve", "handoff_reserve",
                "unallocated_contingency")) == 650000
    allocation["usage_kind"] = "estimated"
    assert _revision_budget(runner)["minimum_author_grant"] == 12000


def test_insufficient_recovery_capacity_preserves_all_future_reserves():
    runner = SimpleNamespace(
        task=SimpleNamespace(contract={"token_limit": 100000}),
        allocations=[{"phase": "revise", "agent_id": "author",
                      "actual_tokens": 315588, "usage_kind": "actual"}],
        agents=[], remaining_tokens=lambda: 100000,
    )
    plan = _revision_budget(runner)
    assert plan["capacity_status"] == "insufficient_tokens"
    assert plan["author_grant"] == 0
    assert plan["minimum_author_grant"] == 394485
