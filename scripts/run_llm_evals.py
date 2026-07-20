"""Run the LLM-output-quality evals against the configured chat provider and write
docs/llm-eval-report.md. Fake mode = deterministic plumbing check; live mode = real
model measurement (uses your OpenAI/Anthropic key, one dialogue turn per scenario).

Run: python -X utf8 scripts/run_llm_evals.py
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "src")
os.environ.setdefault("WB_DATABASE_URL", "sqlite:///data/llm_evals.sqlite3")

from workbench import db, evals_llm  # noqa: E402


def main() -> None:
    Path("data/llm_evals.sqlite3").unlink(missing_ok=True)
    db.create_all()
    report = evals_llm.run(db.session_factory())

    lines = [
        "# LLM output-quality eval report",
        f"\nGenerated {datetime.now(UTC).isoformat()}",
        f"\nProvider mode: **{report.provider_mode}** · model: **{report.model}**",
        "\n> Regression signal on known failure modes (grounding, hallucinated citations,",
        "> prompt-injection, action safety, abstention). NOT a correctness certificate.\n",
        "| check | pass | total | pass rate |",
        "|---|---|---|---|",
    ]
    for name, b in report.per_check.items():
        rate = "n/a" if b["pass_rate"] is None else f"{b['pass_rate']:.2f}"
        lines.append(f"| {name} | {b['pass']} | {b['total']} | {rate} |")
    lines.append("\n## Scenarios\n")
    for r in report.results:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"- **{r['scenario']}** [{status}] checks={r['checks']}")
        lines.append(f"  - reply: {r['reply_preview']!r}")
    Path("docs/llm-eval-report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    sys.exit(0 if report.all_passed else 1)


if __name__ == "__main__":
    main()
