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
        "publication_packages",
        "compute_runs",
        "workspace_members",
        "federated_identities",
        "oidc_workspace_bindings",
        "api_credentials",
        "alembic_version",
    } <= tables
    # the credential columns that the legacy create_all DB was missing
    user_cols = {c["name"] for c in insp.get_columns("users")}
    assert {"email", "password_hash", "oidc_subject", "email_verified"} <= user_cols
    api_key_column = next(c for c in insp.get_columns("users") if c["name"] == "api_key")
    assert api_key_column["nullable"] is True

    db.reset_engine_for_tests()
    config.get_settings.cache_clear()


def test_tenant_migration_lifts_existing_project_owner(tmp_path, monkeypatch):
    db_path = tmp_path / "upgrade.sqlite3"
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{db_path}")
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from workbench import config, db

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    root = db._repo_root()
    alembic = Config(str(root / "alembic.ini"))
    alembic.set_main_option("script_location", str(root / "migrations"))
    alembic.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic, "e8b4c1d7a290")

    with db.get_engine().begin() as connection:
        connection.execute(
            text(
                "INSERT INTO workspaces (id, name, created_at, deleted_at) "
                "VALUES ('workspace1', 'Legacy', CURRENT_TIMESTAMP, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, workspace_id, name, description, created_at, deleted_at) "
                "VALUES ('project1', 'workspace1', 'Legacy project', '', "
                "CURRENT_TIMESTAMP, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, name, api_key, email, password_hash, oidc_subject, email_verified, "
                "created_at, deleted_at) VALUES "
                "('user1', 'Legacy owner', 'legacy-key', NULL, NULL, NULL, 0, "
                "CURRENT_TIMESTAMP, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO project_members "
                "(id, project_id, user_id, role, created_at, deleted_at) VALUES "
                "('member1', 'project1', 'user1', 'owner', CURRENT_TIMESTAMP, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, workspace_id, name, description, created_at, deleted_at) "
                "VALUES ('project2', 'workspace1', 'Second project', '', "
                "CURRENT_TIMESTAMP, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, name, api_key, email, password_hash, oidc_subject, email_verified, "
                "created_at, deleted_at) VALUES "
                "('user2', 'Second owner', 'legacy-key-2', NULL, NULL, NULL, 0, "
                "CURRENT_TIMESTAMP, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO project_members "
                "(id, project_id, user_id, role, created_at, deleted_at) VALUES "
                "('member2', 'project2', 'user2', 'owner', CURRENT_TIMESTAMP, NULL)"
            )
        )

    assert db.upgrade_to_head() == "alembic upgrade head"
    with db.get_engine().connect() as connection:
        row = connection.execute(
            text(
                "SELECT workspace_id, user_id, role FROM workspace_members "
                "WHERE workspace_id='workspace1' AND user_id='user1'"
            )
        ).one()
    assert tuple(row) == ("workspace1", "user1", "owner")
    with db.get_engine().connect() as connection:
        second = connection.execute(
            text(
                "SELECT role FROM workspace_members "
                "WHERE workspace_id='workspace1' AND user_id='user2'"
            )
        ).scalar_one()
    assert second == "member"

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
