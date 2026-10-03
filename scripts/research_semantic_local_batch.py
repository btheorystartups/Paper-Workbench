"""Plan, or explicitly execute, one backed-up semantic cache batch on a named local project."""

import argparse
import json
import os
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Requires the operator's authorization")
    args = parser.parse_args()
    plan = {"database": str(args.database.resolve()), "data_dir": str(args.data_dir.resolve()),
            "project_name": args.project_name, "output": str(args.output.resolve()),
            "actions": ["Identify one exact, non-deleted project name; stop if ambiguous",
                        "Create a consistent private SQLite backup",
                        "Index at most 512 missing/changed research cards using the pinned local model",
                        "Save a private four-query retrieval preview and index receipt"],
            "paid_api_calls": 0, "research_agents": 0, "migrations": 0,
            "automatic_continuation": False}
    if not args.execute:
        print(json.dumps({"plan_only_database_not_opened": True, **plan}, indent=2))
        return
    if not args.database.is_file() or not args.data_dir.is_dir():
        raise ValueError("Existing database and data directory are required")
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ.update(WB_LOAD_DOTENV="false", WB_DATA_DIR=str(args.data_dir.resolve()),
                      WB_DATABASE_URL="sqlite:///" + args.database.resolve().as_posix(),
                      WB_PROVIDER_MODE="fake", WB_LLM_PROVIDER="openai")
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from workbench import config
    from workbench.models import Project
    from workbench.providers.research_embeddings import get_local_provider
    from workbench.services.research_retrieval import retrieve
    from workbench.services.research_semantic import index_project

    config.get_settings.cache_clear()
    get_local_provider()  # Fail before opening the database if model setup is incomplete.
    engine = create_engine(os.environ["WB_DATABASE_URL"])
    try:
        with Session(engine) as session:
            matches = list(session.scalars(select(Project).where(
                Project.name == args.project_name, Project.deleted_at.is_(None))))
            if len(matches) != 1:
                raise ValueError("Project name is missing or ambiguous; no cache changes made")
            project_id = matches[0].id
        with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(args.output / "PRIVATE-before-index.sqlite3") as backup:
                source.backup(backup)
        with Session(engine) as session:
            receipt = index_project(session, project_id)
            previews = [retrieve(session, project_id, query, mode="hybrid", recall="broad") for query in (
                "finite ultrametric observations", "asymmetric refinement preserves inter-cell distances",
                "prior art on non-Hausdorff distance topologies", "counterexamples to symmetric lifts")]
            session.commit()
        for filename, value in [("index-receipt.json", {**plan, "project_id": project_id, "result": receipt}),
                                ("PRIVATE-retrieval-previews.json", previews)]:
            (args.output / filename).write_text(json.dumps(value, indent=2), encoding="utf-8")
        print(json.dumps({"project_id": project_id, "result": receipt, "output": str(args.output)}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
