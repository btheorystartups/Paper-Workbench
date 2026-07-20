"""Settings. Env-only secrets (pattern copied from POP Card Studio keys.py/config.py):
API keys are read from the environment, never stored in domain tables, never logged.

`WB_PROVIDER_MODE=fake` (the default) guarantees zero external calls — every provider
resolves to a deterministic fake, so the whole system runs and tests offline.
"""

import os
from functools import lru_cache
from pathlib import Path

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
    data_dir: str = "data"

    # "fake" (default, offline) or "live" (requires keys below).
    provider_mode: str = "fake"

    # Discovery / search
    brave_rate_limit_seconds: float = 1.1

    # LLM
    llm_provider: str = "openai"  # "openai" | "anthropic"
    llm_model: str = "gpt-5.2"
    anthropic_model: str = "claude-sonnet-5"
    llm_max_output_tokens: int = 4096


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
    _load_dotenv()
    return Settings()
