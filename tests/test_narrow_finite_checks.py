"""A perturbed edge must expose an axiom failure rather than a hardcoded pass."""

import importlib.util
from pathlib import Path


def test_corrupted_conditional_table_finds_counterexample():
    path = Path(__file__).parents[1] / "scripts" / "reproduce_narrow_finite_checks.py"
    spec = importlib.util.spec_from_file_location("narrow_finite_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    distance = [[0, 0, 3, 2], [1, 0, 2, 2], [2, 2, 0, 0], [2, 2, 1, 0]]
    result = module.check_instance(
        "perturbed", distance, ["c", "c", "d", "d"], [(0, 0), (0, 1), (1, 1), (2, 2), (2, 3), (3, 3)], 2
    )
    assert result["cross_cell_check"]["status"] == "failed"
    assert result["directed_ultrametric"]["passed"] is False
    assert [0, 1, 2] in result["directed_ultrametric"]["failing_triples"]
