"""One explicitly authorized ChatGPT-plan acceptance run on a NEW synthetic database.

No API key, existing database, or .env is read. The result stays in the chosen
output directory. This script never retries or silently starts a second task.
"""

import argparse
import json
import os
import sys
import time
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--token-limit", type=int, default=24000)
    parser.add_argument("--time-limit-seconds", type=int, default=300)
    parser.add_argument("--max-children", type=int, choices=range(1, 4), default=1)
    parser.add_argument(
        "--narrow-lifting-one-source", action="store_true",
        help="keep the pilot lifting question, attach only research_report.md, and ask one finite check",
    )
    parser.add_argument("--confirm-chatgpt-plan", action="store_true")
    args = parser.parse_args()
    if not args.confirm_chatgpt_plan:
        parser.error("an explicit --confirm-chatgpt-plan flag is required")
    output = args.output.resolve()
    profile = args.profile.resolve(strict=True)
    if not profile.is_dir():
        parser.error("the dedicated Codex profile must be a directory")
    if output.exists() and any(output.iterdir()):
        parser.error("choose a new empty output directory")
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    worker = root / "src/workbench/providers/research_codex_worker.py"
    database = output / "acceptance.sqlite3"
    os.environ.update(
        WB_LOAD_DOTENV="false",
        WB_DATABASE_URL="sqlite:///" + database.as_posix(),
        WB_DATA_DIR=str(output / "data"),
        WB_DEPLOYMENT_MODE="local",
        WB_AUTH_REQUIRED="false",
        WB_RESEARCH_EXECUTOR_ENABLED="true",
        WB_RESEARCH_EXECUTOR_COMMAND=json.dumps([sys.executable, str(worker)]),
        WB_RESEARCH_CODEX_HOME=str(profile),
        WB_RESEARCH_CODEX_MODEL="gpt-5.5",
        WB_RESEARCH_CODEX_REASONING_EFFORT="low",
    )
    sys.path.insert(0, str(root / "src"))
    from workbench import db
    from workbench.research_contract import TaskBrief
    from workbench.services import research, research_runner, research_tasks

    pilot_path = root / "tests/fixtures/research-task-pilot-2026-09-30.zip"
    with zipfile.ZipFile(pilot_path) as pilot:
        contract = pilot.read("task_contract.md").decode()
        full_source_set = {
            name: pilot.read(name)
            for name in ("task_contract.md", "research_report.md", "search_log.md")
        }
        selected = (
            {"research_report.md": full_source_set["research_report.md"]}
            if args.narrow_lifting_one_source else full_source_set
        )
    question = (
        contract.split("## Executed research question", 1)[1]
        .split("## Inputs and scope", 1)[0].strip()
    )
    db.upgrade_to_head()
    with db.session_factory()() as session:
        workspace = research.create_workspace(session, "Live acceptance")
        project = research.create_project(session, workspace.id, "Paper Writer — live acceptance")
        task = research_tasks.create_task(
            session,
            project.id,
            TaskBrief(
                question=question,
                task_type="research",
                success_criteria=(
                    "NARROW ONE-SOURCE SCOPE: check only the finite asymmetric two-cell lifting "
                    "example stated in the supplied research_report.md. Verify exact cross-cell "
                    "distances and whether its positive-observation topology matches the stated "
                    "claim; cite the precise passage and give one explicit finite check. Do not "
                    "generalize beyond that example."
                    if args.narrow_lifting_one_source else
                    "Independently assess finite symmetric and asymmetric lifting claims "
                    "within the supplied pilot scope. Record proof attempts, counterexample "
                    "candidates, exact source locations, and unresolved issues."
                ),
                instructions=(
                    "NARROW ACCEPTANCE RUN: the original lifting question is retained, but this "
                    "run tests one finite asymmetric example from one accepted source only. "
                    "No symmetry comparison, general theorem, external literature, or novelty "
                    "assessment."
                    if args.narrow_lifting_one_source else
                    "The pilot is a single-agent preliminary reference, not established "
                    "proof or novelty. Audit its claims independently."
                ),
                executor="process",
                allow_best_effort_tokens=True,
                token_limit=args.token_limit,
                time_limit_seconds=args.time_limit_seconds,
                max_children=args.max_children,
            ),
        )
        for name, data in selected.items():
            research_tasks.attach(
                session, task, name, data,
                version=(
                    "2026-09-30 single-agent pilot; unreviewed format reference; narrow one-source scope"
                    if args.narrow_lifting_one_source else
                    "2026-09-30 single-agent pilot; unreviewed format reference"
                ),
            )
        session.commit()
        research_runner.start(session, task, acknowledge_live_execution=True)
        task_id = task.id
    terminal = {
        "completed", "limit_reached_partial", "failed_partial",
        "cancelled_partial", "interrupted_partial",
    }
    until = time.monotonic() + args.time_limit_seconds + 30
    state = None
    try:
        while time.monotonic() < until:
            with db.session_factory()() as session:
                state = research_tasks.task_for(session, project.id, task_id).state
            if state in terminal:
                break
            time.sleep(1)
        if state not in terminal:
            with db.session_factory()() as session:
                research_runner.cancel(
                    session, research_tasks.task_for(session, project.id, task_id)
                )
            research_runner.shutdown()
        with db.session_factory()() as session:
            task = research_tasks.task_for(session, project.id, task_id)
            archive = output / "lifting-live.zip"
            archive.write_bytes(research_tasks.package(session, task))
            print("Task:", task_id)
            print("State:", task.state)
            print("Token stopping:", task.ledger.get("token_limit_mode"))
            print("Actual reported tokens:", task.ledger.get("actual_tokens"))
            print("Estimated reservation:", task.ledger.get("estimated_tokens"))
            print("Live handoff verified:", task.ledger.get("live_handoff_verified"))
            print("Acceptance scope:", "NARROW: one finite asymmetric example, research_report.md only"
                  if args.narrow_lifting_one_source else "FULL: three pilot source files")
            print("Package:", archive)
    finally:
        research_runner.shutdown()


if __name__ == "__main__":
    main()
