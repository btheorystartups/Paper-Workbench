"""Acceptance setup failures must occur before live dispatch or store creation."""

import os
import runpy
import sys
from pathlib import Path

import pytest

from workbench.services import research_results
from workbench.services.research import IntegrityError


def test_acceptance_missing_math_runtime_stops_before_database_or_model(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setattr(sys, "path", sys.path.copy())
    script = Path(__file__).parents[1] / "scripts/research_live_acceptance.py"
    output = tmp_path / "acceptance"
    monkeypatch.setattr(sys, "argv", [str(script), str(output), "--profile", str(tmp_path),
                                    "--confirm-chatgpt-plan", "--manuscript-finite-partitions"])
    from workbench import db

    monkeypatch.setattr(db, "upgrade_to_head", lambda: pytest.fail("database setup was reached"))

    def missing_renderer(*args):
        raise IntegrityError("Math PDF requires Node.js and npm ci in src/workbench/math_runtime.")

    monkeypatch.setattr(research_results, "render_sections", missing_renderer)
    with pytest.raises(IntegrityError, match="Math PDF requires"):
        runpy.run_path(str(script))["main"]()
    assert not (output / "acceptance.sqlite3").exists()
    assert not (output / "data").exists()
