"""Startup schema management: alembic upgrade_to_head builds the full current schema and
is what the app runs at boot (regression for the stale-dev-DB /auth/me 500)."""


def test_upgrade_to_head_builds_full_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'fresh.sqlite3'}")
    from sqlalchemy import inspect

    from workbench import config, db

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()

    which = db.upgrade_to_head()
    assert which == "alembic upgrade head"

    insp = inspect(db.get_engine())
    tables = set(insp.get_table_names())
    # every mapped table plus alembic bookkeeping
    assert {
        "users",
        "submissions",
        "venue_profiles",
        "embeddings",
        "citation_edges",
        "contributors",
        "credit_assignments",
        "authorship_proposals",
        "alembic_version",
    } <= tables
    # the credential columns that the legacy create_all DB was missing
    user_cols = {c["name"] for c in insp.get_columns("users")}
    assert {"email", "password_hash", "oidc_subject", "email_verified"} <= user_cols

    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


def test_legacy_unmanaged_db_is_not_clobbered(tmp_path, monkeypatch):
    """A create_all() DB with no alembic_version must not have its tables recreated."""
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    from sqlalchemy import inspect

    from workbench import config, db

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    db.create_all()  # simulate a legacy DB built without alembic

    which = db.upgrade_to_head()
    assert which == "create_all (legacy unmanaged DB)"
    assert "alembic_version" not in set(inspect(db.get_engine()).get_table_names())

    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
