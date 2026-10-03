"""Reproduce local handoffs with controlled fake agents, and save reviewable ZIPs.

Creates a NEW synthetic database in the requested empty output directory. Never reads
developer .env files, existing databases or credentials; never calls a model/provider.
"""

import argparse
import os
import sys
import threading
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    database = output / "acceptance.sqlite3"
    if database.exists():
        parser.error("choose a fresh output directory; existing databases are never overwritten")
    os.environ.update(
        WB_LOAD_DOTENV="false",
        WB_PROVIDER_MODE="fake",
        WB_LLM_PROVIDER="openai",
        WB_DATABASE_URL=f"sqlite:///{database}",
        WB_DATA_DIR=str(output / "data"),
        WB_DEPLOYMENT_MODE="local",
        WB_AUTH_REQUIRED="false",
    )
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from workbench import db
    from workbench.models import utcnow
    from workbench.providers.research_executor import ProcessResearchExecutor
    from workbench.research_contract import TaskBrief
    from workbench.services import research, research_runner, research_tasks

    pilot_path = root / "tests/fixtures/research-task-pilot-2026-09-30.zip"
    with zipfile.ZipFile(pilot_path) as pilot:
        contract = pilot.read("task_contract.md").decode()
    question = (
        contract.split("## Executed research question", 1)[1].split("## Inputs and scope", 1)[0].strip()
    )
    db.create_all()
    with db.session_factory()() as session:
        workspace = research.create_workspace(session, "Offline acceptance fixtures")
        project = research.create_project(session, workspace.id, "Paper Writer — offline acceptance")
        session.commit()
        for name, kind, flag in [
            ("lifting", "research", ""),
            ("literature", "literature_search", ""),
            ("proof-audit", "proof_audit", ""),
            ("partial", "research", "soft-token"),
        ]:
            task = research_tasks.create_task(
                session,
                project.id,
                TaskBrief(
                    question=question + ("\nControlled fixture: " + flag if flag else ""),
                    task_type=kind,
                    max_children=3,
                    deliverables=["research_report", "reviewer_report"],
                ),
            )
            research_tasks.attach(
                session,
                task,
                pilot_path.name,
                pilot_path.read_bytes(),
                version="2026-09-30 single-agent pilot; format reference only",
            )
            task.state, task.started_at = "planning", utcnow()
            session.commit()
            research_runner.run_task(
                task.id,
                threading.Event(),
                executor_factory=lambda mode: ProcessResearchExecutor(
                    mode, [sys.executable, str(root / "tests/fixtures/research_protocol_worker.py")]
                ),
            )
            session.expire_all()
            (output / (name + ".zip")).write_bytes(research_tasks.package(session, task))
            print(f"{name}: {task.state}; task={task.id}")
            expected = "limit_reached_partial" if flag else "completed"
            if task.state != expected:
                raise RuntimeError(f"acceptance failed: {name} returned {task.state}, expected {expected}")
        print(f"Project: {project.id}; synthetic database: {database}")


if __name__ == "__main__":
    main()
