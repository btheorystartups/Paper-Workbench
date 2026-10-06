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


def finite_partition_inputs():
    """Synthetic specification for workflow acceptance, not primary-literature evidence."""
    question = "Write an expository manuscript on finite partitions and Boolean-valued function spaces."
    specification = """# Synthetic acceptance specification
This is a controlled test specification, not prior art or a scientific publication.
Let X be a finite nonempty carrier and P a partition of X into nonempty blocks.
Define F(P) as the Boolean-valued functions on X that are constant on every P block.
Prove the finite-carrier refinement/inclusion equivalence, with the direction explicit:
P refines Q if and only if F(Q) is a subset of F(P).
Prove |F(P)| = 2 raised to the number of P blocks.
Prove F(P) intersection F(Q) = F(P join Q), where join is common coarsening.
Supply independent arguments; the specification requests these checks, not their approval.
Historical false claim to explicitly reject: all such function spaces are ordered by inclusion.
Witness on X={0,1,2,3}: P={{0,1},{2,3}}, Q={{0,2},{1,3}}, f=(0,0,1,1).
The trusted finite_partitions_v1 receipt checks all pairs of partitions for carrier sizes 1-5.
That finite execution does not establish an unrestricted theorem or literature priority.
Keep the manuscript expository, with no novelty or exhaustive-literature claim.
Search metadata supplies discovery leads; unacquired full texts cannot support source entailment.
"""
    return question, {"finite-partitions-specification.md": specification.encode("utf-8")}


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
    parser.add_argument("--manuscript-finite-partitions", action="store_true",
                        help="exercise author, counter, four Astra reviewers and one bounded revision")
    parser.add_argument("--allow-public-discovery", action="store_true",
                        help="explicitly allow bounded agent-selected Crossref/OpenAlex searches")
    parser.add_argument("--confirm-chatgpt-plan", action="store_true")
    args = parser.parse_args()
    if not args.confirm_chatgpt_plan:
        parser.error("an explicit --confirm-chatgpt-plan flag is required")
    if args.manuscript_finite_partitions and args.narrow_lifting_one_source:
        parser.error("choose either finite-partition manuscript or narrow lifting acceptance")
    if args.allow_public_discovery and not args.manuscript_finite_partitions:
        parser.error("public discovery requires the finite-partition manuscript acceptance")
    attempt_started = time.monotonic()
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
        WB_RESEARCH_CODEX_MODEL="gpt-5.6-sol",
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
    if args.manuscript_finite_partitions:
        question, selected = finite_partition_inputs()
    db.upgrade_to_head()
    remaining_seconds = int(args.time_limit_seconds - (time.monotonic() - attempt_started))
    if remaining_seconds <= 0:
        raise TimeoutError("acceptance setup exhausted the time budget")
    with db.session_factory()() as session:
        workspace = research.create_workspace(session, "Live acceptance")
        project = research.create_project(session, workspace.id, "Paper Writer — live acceptance")
        task = research_tasks.create_task(
            session,
            project.id,
            TaskBrief(
                question=question,
                task_type="manuscript" if args.manuscript_finite_partitions else "research",
                manuscript_length={"min_words": 900, "max_words": 1200}
                if args.manuscript_finite_partitions else None,
                max_revision_cycles=1 if args.manuscript_finite_partitions else 2,
                allow_public_search=args.allow_public_discovery,
                agent_literature_discovery=args.allow_public_discovery,
                verification_routines=["finite_partitions_v1"] if args.manuscript_finite_partitions else [],
                success_criteria=(
                    "Complete a 900-1200-word expository manuscript within the finite scope. "
                    "Independently justify the three statements in the synthetic specification, "
                    "reject the historical false generalization, preserve actual verification/search "
                    "receipts, and complete four specialist reviews and any funded revision/re-review. "
                    "No novelty claim or inference from finite enumeration to arbitrary domains."
                    if args.manuscript_finite_partitions else
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
                    "Treat the synthetic specification as requirements, not evidence of correctness. "
                    "Give independent proofs within the finite scope and explicitly reject the supplied "
                    "false claim. Actual finite checking covers only carrier sizes 1-5. Distinguish "
                    "formal arguments from finite execution and literature metadata from full texts."
                    if args.manuscript_finite_partitions else
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
                time_limit_seconds=remaining_seconds,
                max_children=3 if args.manuscript_finite_partitions else args.max_children,
            ),
        )
        for name, data in selected.items():
            research_tasks.attach(
                session, task, name, data,
                version=(
                    "Synthetic finite-partition acceptance specification v1; not prior-art evidence"
                    if args.manuscript_finite_partitions else
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
    until = attempt_started + args.time_limit_seconds
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
            archive = output / (
                "manuscript-live.zip" if args.manuscript_finite_partitions else "lifting-live.zip")
            archive.write_bytes(research_tasks.package(session, task))
            print("Task:", task_id)
            print("State:", task.state)
            print("Token stopping:", task.ledger.get("token_limit_mode"))
            print("Actual reported tokens:", task.ledger.get("actual_tokens"))
            print("Estimated reservation:", task.ledger.get("estimated_tokens"))
            print("Live handoff verified:", task.ledger.get("live_handoff_verified"))
            print("Acceptance scope:", "Finite-partition manuscript with four-role review"
                  if args.manuscript_finite_partitions else
                  "NARROW: one finite asymmetric example, research_report.md only"
                  if args.narrow_lifting_one_source else "FULL: three pilot source files")
            print("Agent checks complete:", task.synthesis.get("quality", {}).get("agent_checks_complete"))
            print("Package:", archive)
    finally:
        research_runner.shutdown()


if __name__ == "__main__":
    main()
