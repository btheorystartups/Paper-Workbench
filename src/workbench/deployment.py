"""Deployment-mode validation.

Local Paper-Workbench stays frictionless. Internet-facing/serverless operation must be
selected explicitly and fails closed if a workstation-only behavior remains enabled.
"""

from pathlib import PurePosixPath

from .config import get_settings
from .db import runtime_database_url


class DeploymentError(RuntimeError):
    pass


def validate_deployment_configuration() -> None:
    settings = get_settings()
    mode = settings.deployment_mode.strip().lower()
    if mode not in {"local", "vercel"}:
        raise DeploymentError("WB_DEPLOYMENT_MODE must be local or vercel")
    if mode == "local":
        return

    problems: list[str] = []
    if not settings.auth_required:
        problems.append("WB_AUTH_REQUIRED must be true")
    if not settings.auth_cookie_sessions_enabled:
        problems.append("WB_AUTH_COOKIE_SESSIONS_ENABLED must be true")
    if not settings.auth_cookie_secure:
        problems.append("WB_AUTH_COOKIE_SECURE must be true")
    if runtime_database_url().startswith("sqlite"):
        problems.append("WB_DATABASE_URL must use PostgreSQL")
    if settings.run_migrations_on_startup:
        problems.append("WB_RUN_MIGRATIONS_ON_STARTUP must be false")
    if settings.db_pool_mode.strip().lower() != "null":
        problems.append("WB_DB_POOL_MODE must be null")
    if settings.compute_enabled:
        problems.append("WB_COMPUTE_ENABLED must be false")
    if settings.pdf_renderer.strip().lower() != "minimal":
        problems.append("WB_PDF_RENDERER must be minimal")
    if settings.artifact_storage_backend.strip().lower() != "vercel_blob":
        problems.append("WB_ARTIFACT_STORAGE_BACKEND must be vercel_blob")

    # Vercel Functions only permit runtime writes below /tmp. Durable artifact storage is
    # added separately; this directory is strictly scratch space in deployment mode.
    data_dir = PurePosixPath(settings.data_dir.replace("\\", "/"))
    if not data_dir.is_absolute() or data_dir.parts[:2] != ("/", "tmp"):
        problems.append("WB_DATA_DIR must be an absolute path below /tmp")

    if problems:
        raise DeploymentError("unsafe Vercel configuration: " + "; ".join(problems))


def should_run_startup_migrations() -> bool:
    return get_settings().run_migrations_on_startup
