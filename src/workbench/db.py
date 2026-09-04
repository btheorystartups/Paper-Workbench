"""Engine/session factory. SQLite by default; schema stays Postgres-compatible (ADR-1/2).

Migrations: Alembic arrives with the first post-P1 schema change; P1 bootstraps via
create_all (recorded in the continuation ledger as a provisional shortcut).
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        if url.startswith("sqlite:///"):
            db_path = Path(url.removeprefix("sqlite:///"))
            if db_path.parent and str(db_path.parent) not in (".", ""):
                db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, future=True)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _record):  # SQLite FKs are off by default
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def session_factory() -> sessionmaker:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = session_factory()()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    from . import models

    models.Base.metadata.create_all(get_engine())


def _repo_root() -> Path:
    # src/workbench/db.py -> repo root is two parents up from the package dir
    return Path(__file__).resolve().parents[2]


def upgrade_to_head() -> str:
    """Bring the configured database to the latest schema via Alembic — the source of
    truth for schema. On a brand-new DB this builds everything from base; on an
    Alembic-managed DB it applies pending migrations. Falls back to create_all() when
    Alembic is unavailable. Returns which path ran.

    A pre-existing DB built by create_all() (tables but no alembic_version) predates the
    migration tree; we cannot safely infer its revision, so we do NOT guess. We log a
    clear warning and run create_all() (which adds any wholly-new tables but cannot alter
    existing ones) — such a DB should be recreated or hand-migrated.
    """
    import logging

    root = _repo_root()
    ini = root / "alembic.ini"
    try:
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import inspect
    except ImportError:
        create_all()
        return "create_all (alembic unavailable)"
    if not ini.is_file():
        create_all()
        return "create_all (no alembic.ini)"

    engine = get_engine()
    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        logging.getLogger("wb.db").warning(
            "database has tables but no alembic_version: it predates migrations. "
            "Running create_all() (cannot alter existing tables). Recreate or hand-migrate "
            "this DB, or run 'alembic upgrade head' after stamping the correct revision."
        )
        create_all()
        return "create_all (legacy unmanaged DB)"

    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")
    return "alembic upgrade head"


def reset_engine_for_tests() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
