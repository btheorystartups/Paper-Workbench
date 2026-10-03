"""Guarded, idempotent migration of the known staging DB; default is read-only preflight.

Run through vercel env run from the dotenv-free operator directory. Credentials are used
only in memory; reports contain hostnames/revisions and constant error labels.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROJECT = "prj_a4tgpf6rsmYp7H3JroXUH4x6ERk3"
HOST = "ep-fragrant-violet-avjxe9qt.c-11.us-east-1.aws.neon.tech"
BEFORE = "f3a1c7e9b420"
AFTER = "a91d4e7b620f"


class MigrationGuardError(Exception):
    """Constant diagnostics only; database/URL exception details must not be printed."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--expected-database-host", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    report = {"project_id": PROJECT, "target_revision": AFTER, "executed": False}
    engine = None
    try:
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from sqlalchemy.pool import NullPool

        from workbench import config, db

        config._load_dotenv = lambda: None
        if args.confirm_project != PROJECT or args.expected_database_host != HOST:
            raise MigrationGuardError("target confirmation mismatch")
        link = json.loads((Path.cwd() / ".vercel" / "project.json").read_text())
        if link.get("projectId") != PROJECT or any(Path.cwd().glob(".env*")):
            raise MigrationGuardError("unsafe operator directory")
        raw_url = os.environ.get("WB_MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL_UNPOOLED", "")
        url = make_url(db.normalize_database_url(raw_url))
        if url.host != HOST or url.drivername != "postgresql+psycopg":
            raise MigrationGuardError("unexpected direct database target")
        report["database_host"] = url.host
        engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 30})
        with engine.connect() as connection:
            before = list(connection.scalars(text("SELECT version_num FROM alembic_version")))
        if before not in ([BEFORE], [AFTER]):
            raise MigrationGuardError("unexpected migration revision")
        report["before"] = before[0]
        if args.execute and before == [BEFORE]:
            db.migration_database_url = lambda: url.render_as_string(hide_password=False)
            alembic = Config(str(ROOT / "alembic.ini"))
            alembic.set_main_option("script_location", str(ROOT / "migrations"))
            command.upgrade(alembic, AFTER)
            report["executed"] = True
        with engine.connect() as connection:
            report["after"] = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if args.execute and report["after"] != AFTER:
            raise MigrationGuardError("migration verification failed")
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        if isinstance(exc, MigrationGuardError):
            report["error"] = str(exc)
    finally:
        if engine is not None:
            engine.dispose()
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
