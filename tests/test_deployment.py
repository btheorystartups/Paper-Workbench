"""Offline checks for PostgreSQL/Vercel deployment guardrails."""

import pytest


def _clear(monkeypatch):
    from workbench import config, db

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()


def _safe_vercel_env(monkeypatch):
    monkeypatch.setenv("WB_DEPLOYMENT_MODE", "vercel")
    monkeypatch.setenv("WB_DATABASE_URL", "postgresql://runtime.example/workbench")
    monkeypatch.setenv(
        "WB_MIGRATION_DATABASE_URL", "postgres://direct.example/workbench"
    )
    monkeypatch.setenv("WB_DB_POOL_MODE", "null")
    monkeypatch.setenv("WB_DATA_DIR", "/tmp/paper-workbench")
    monkeypatch.setenv("WB_RUN_MIGRATIONS_ON_STARTUP", "false")
    monkeypatch.setenv("WB_AUTH_REQUIRED", "true")
    monkeypatch.setenv("WB_AUTH_SECRET", "deployment-test-secret-0123456789-abcdef")
    monkeypatch.setenv("WB_AUTH_COOKIE_SESSIONS_ENABLED", "true")
    monkeypatch.setenv("WB_AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("WB_OIDC_MODE", "disabled")
    monkeypatch.setenv("WB_COMPUTE_ENABLED", "false")
    monkeypatch.setenv("WB_PDF_RENDERER", "minimal")
    monkeypatch.setenv("WB_ARTIFACT_STORAGE_BACKEND", "vercel_blob")


def test_database_urls_normalize_and_migration_prefers_direct(monkeypatch):
    _safe_vercel_env(monkeypatch)
    _clear(monkeypatch)
    from workbench import db

    assert db.runtime_database_url() == "postgresql+psycopg://runtime.example/workbench"
    assert db.migration_database_url() == "postgresql+psycopg://direct.example/workbench"


def test_neon_owned_database_names_are_safe_fallbacks(monkeypatch):
    monkeypatch.delenv("WB_DATABASE_URL", raising=False)
    monkeypatch.delenv("WB_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://runtime.example/workbench")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://direct.example/workbench")
    _clear(monkeypatch)
    from workbench import db

    assert db.runtime_database_url() == "postgresql+psycopg://runtime.example/workbench"
    assert db.migration_database_url() == "postgresql+psycopg://direct.example/workbench"
    assert db.normalize_database_url("sqlite:///data/test.db") == "sqlite:///data/test.db"
    _clear(monkeypatch)


def test_safe_vercel_configuration_is_accepted(monkeypatch):
    _safe_vercel_env(monkeypatch)
    _clear(monkeypatch)
    from workbench import deployment

    deployment.validate_deployment_configuration()
    assert deployment.should_run_startup_migrations() is False
    _clear(monkeypatch)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("WB_AUTH_REQUIRED", "false", "WB_AUTH_REQUIRED"),
        ("WB_AUTH_COOKIE_SESSIONS_ENABLED", "false", "COOKIE_SESSIONS"),
        ("WB_AUTH_COOKIE_SECURE", "false", "COOKIE_SECURE"),
        ("WB_DATABASE_URL", "sqlite:////tmp/workbench.db", "PostgreSQL"),
        ("WB_RUN_MIGRATIONS_ON_STARTUP", "true", "RUN_MIGRATIONS"),
        ("WB_DB_POOL_MODE", "default", "DB_POOL_MODE"),
        ("WB_DATA_DIR", "data", "DATA_DIR"),
        ("WB_COMPUTE_ENABLED", "true", "COMPUTE_ENABLED"),
        ("WB_PDF_RENDERER", "auto", "PDF_RENDERER"),
        ("WB_ARTIFACT_STORAGE_BACKEND", "local", "ARTIFACT_STORAGE_BACKEND"),
    ],
)
def test_vercel_configuration_fails_closed(monkeypatch, name, value, message):
    _safe_vercel_env(monkeypatch)
    monkeypatch.setenv(name, value)
    _clear(monkeypatch)
    from workbench import deployment

    with pytest.raises(deployment.DeploymentError, match=message):
        deployment.validate_deployment_configuration()
    _clear(monkeypatch)


def test_unknown_deployment_and_pool_modes_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DEPLOYMENT_MODE", "cloudish")
    _clear(monkeypatch)
    from workbench import db, deployment

    with pytest.raises(deployment.DeploymentError, match="local or vercel"):
        deployment.validate_deployment_configuration()

    monkeypatch.setenv("WB_DEPLOYMENT_MODE", "local")
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'bad-pool.db'}")
    monkeypatch.setenv("WB_DB_POOL_MODE", "mystery")
    _clear(monkeypatch)
    with pytest.raises(ValueError, match="WB_DB_POOL_MODE"):
        db.get_engine()
    _clear(monkeypatch)


def test_root_vercel_entrypoint_exports_fastapi_app():
    from fastapi import FastAPI

    import app as vercel_entrypoint

    assert isinstance(vercel_entrypoint.app, FastAPI)
