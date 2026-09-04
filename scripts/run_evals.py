"""Run the deterministic-audit eval harness and write docs/eval-report.md."""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "src")
os.environ["WB_PROVIDER_MODE"] = "fake"
os.environ["WB_DATABASE_URL"] = "sqlite:///data/evals.sqlite3"

from workbench import db, evals  # noqa: E402


def main() -> None:
    Path("data/evals.sqlite3").unlink(missing_ok=True)
    db.create_all()
    report = evals.run(db.session_factory())

    lines = [
        "# Audit eval report",
        f"\nGenerated {datetime.now(UTC).isoformat()} — deterministic audit layer only; "
        "LLM output quality is NOT measured here.\n",
        "| finding code | TP | FP | FN | precision | recall |",
        "|---|---|---|---|---|---|",
    ]
    for code, m in report["metrics"].items():
        fmt = lambda v: "n/a" if v is None else f"{v:.2f}"  # noqa: E731
        lines.append(
            f"| {code} | {m['tp']} | {m['fp']} | {m['fn']} | "
            f"{fmt(m['precision'])} | {fmt(m['recall'])} |"
        )
    lines.append("\n## Scenarios\n")
    for row in report["scenarios"]:
        status = "OK" if not row["missed"] and not row["false_hits"] else "FAIL"
        lines.append(f"- **{row['scenario']}** [{status}] expected={row['expected']} "
                     f"missed={row['missed']} false_hits={row['false_hits']}")
    Path("docs/eval-report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    failures = [r for r in report["scenarios"] if r["missed"] or r["false_hits"]]
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
