"""Settings. Env-only secrets (pattern copied from POP Card Studio keys.py/config.py):
API keys are read from the environment, never stored in domain tables, never logged.

Defaults resolve to offline fakes. Explicit codex_local opt-in independently selects
local ChatGPT generation; search and extraction still follow WB_PROVIDER_MODE.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_dotenv() -> None:
    """Best-effort .env loader (cwd upward, 3 levels). setdefault only: real env wins."""
    here = Path.cwd()
    for candidate in [here, *here.parents[:3]]:
        for name in (".env", ".env.local"):
            path = candidate / name
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WB_", extra="ignore")

    database_url: str = "sqlite:///data/workbench.sqlite3"
    # A direct/non-pooled URL may be supplied for the separately-run Alembic command.
    # Runtime requests continue to use database_url (normally the provider's pooled URL).
    migration_database_url: str = ""
    db_pool_mode: str = "default"  # "default" | "null"
    data_dir: str = "data"

    # "local" retains the standalone workstation behavior. "vercel" enables strict
    # serverless guardrails and is never inferred merely from ambient Vercel variables.
    deployment_mode: str = "local"  # "local" | "vercel"
    run_migrations_on_startup: bool = True
    artifact_storage_backend: str = "local"  # "local" | "vercel_blob"
    artifact_max_read_bytes: int = 100_000_000
    upload_max_bytes: int = 4_000_000

    # "fake" (default, offline) or "live" (requires keys below).
    provider_mode: str = "fake"

    # Independent of chat providers. Live research needs an operator-installed worker
    # implementing research-process-v1; no API-key or codex_local fallback.
    research_executor_enabled: bool = False
    research_executor_command: list[str] = Field(default_factory=list)
    research_codex_home: str = ""
    research_codex_account_email: str = ""
    research_codex_model: str = "gpt-5.5"
    research_codex_reasoning_effort: str = "low"

    # Discovery / search
    brave_rate_limit_seconds: float = 1.1

    # LLM
    llm_provider: str = "openai"  # "openai" | "anthropic"
    llm_model: str = "gpt-5.2"
    anthropic_model: str = "claude-sonnet-5"
    llm_max_output_tokens: int = 4096

    # Local single-user Codex is independent of API provider mode; explicit opt-in.
    codex_local_enabled: bool = False
    codex_local_gate_secret: SecretStr = Field(default=SecretStr(""), exclude=True)
    codex_local_home: str = ""
    codex_local_account_email: str = ""
    codex_local_workspace_id: str = ""
    codex_local_model: str = "gpt-5.6-sol"
    codex_local_reasoning_effort: str = "xhigh"
    codex_local_timeout_seconds: float = Field(default=120.0, gt=0, allow_inf_nan=False)
    # Application text limits in o200k_base tokens, NOT account-usage ceilings.
    codex_local_max_input_tokens: PositiveInt = 200_000
    codex_local_max_output_tokens: PositiveInt = 1_000_000

    # Auth (off by default — local single-user needs no credentials)
    auth_required: bool = False
    auth_secret: str = "dev-insecure-secret"  # MUST be overridden when auth_required
    auth_ttl_minutes: int = 720
    auth_allow_registration: bool = False
    auth_password_login_enabled: bool = True
    auth_bootstrap_token: str = ""
    auth_token_issuer: str = "paper-workbench"
    auth_token_audience: str = "paper-workbench-api"
    auth_clock_skew_seconds: int = 30
    auth_cookie_sessions_enabled: bool = False
    auth_cookie_secure: bool = True
    auth_cookie_name: str = "wb_session"
    auth_csrf_cookie_name: str = "wb_csrf"

    # OIDC is deliberately independent of AI/search provider mode. Production must set
    # mode=live; fake accepts deterministic JSON claims only for offline/local tests and
    # is refused whenever enforced auth is enabled.
    oidc_mode: str = "disabled"  # "disabled" | "fake" | "live"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_allowed_algorithms: str = "RS256,ES256"
    oidc_jwks_timeout_seconds: float = 5.0
    oidc_require_https: bool = True
    oidc_tenant_claim: str = ""
    oidc_allow_email_linking: bool = False
    oidc_allow_jit_provisioning: bool = False
    oidc_allow_jit_membership: bool = False
    oidc_browser_enabled: bool = False
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_authorization_url: str = ""
    oidc_token_url: str = ""
    oidc_redirect_uri: str = ""
    oidc_scope: str = "openid profile email"
    oidc_flow_cookie_name: str = "wb_oidc_flow"
    oidc_flow_ttl_minutes: int = 10

    # Export
    pdf_renderer: str = "auto"  # "auto" | "weasyprint" | "minimal"
    # Optional stricter/venue-specific DTD. Empty = bundled official JATS 1.3 Archiving DTD.
    jats_dtd_path: str = ""

    # Local compute. Execution still requires hash-bound approval and per-run confirmation.
    compute_enabled: bool = True
    compute_max_timeout_seconds: int = 300
    compute_max_output_files: int = 100
    compute_max_output_bytes: int = 50_000_000
    compute_max_log_bytes: int = 1_000_000
    compute_container_runtime: str = "docker"
    compute_container_default_image: str = ""
    compute_container_max_memory_mb: int = 4096
    compute_container_max_cpus: float = 4.0
    compute_container_max_pids: int = 256


def brave_api_key() -> str:
    return os.environ.get("WB_BRAVE_SEARCH_API_KEY") or os.environ.get(
        "BRAVE_SEARCH_API_KEY", ""
    )


def openai_api_key() -> str:
    # Accept the user's actual .env spellings, most specific first.
    return (
        os.environ.get("WB_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPEN_AI_API_KEY", "")
    )


def openai_model_override() -> str:
    return os.environ.get("OPENAI_MODEL", "")


def anthropic_api_key() -> str:
    return os.environ.get("WB_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Test and evaluation runners must be able to prove they did not inherit local keys
    # or configuration from a developer checkout.
    if os.environ.get("WB_LOAD_DOTENV", "true").strip().lower() not in {"0", "false", "no"}:
        _load_dotenv()
    # Vercel's Neon integration owns these conventional names. Explicit WB_ values
    # always win, while the aliases avoid copying database secrets into second variables.
    overrides: dict[str, str] = {}
    if not os.environ.get("WB_DATABASE_URL") and os.environ.get("DATABASE_URL"):
        overrides["database_url"] = os.environ["DATABASE_URL"]
    if not os.environ.get("WB_MIGRATION_DATABASE_URL") and os.environ.get(
        "DATABASE_URL_UNPOOLED"
    ):
        overrides["migration_database_url"] = os.environ["DATABASE_URL_UNPOOLED"]
    return Settings(**overrides)
