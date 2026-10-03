"""Vercel/FastAPI discovery entry point.

The project retains a src/ package layout locally; Vercel imports this root module after
installing dependencies, so make that source directory explicit without changing cwd.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from workbench.main import app  # noqa: E402, F401
