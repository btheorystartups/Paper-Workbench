import re
from pathlib import Path

from workbench.config import Settings


def test_env_example_covers_every_setting_without_active_secrets():
    example = (Path(__file__).parents[1] / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"(?m)^#?\s*(WB_[A-Z0-9_]+)=", example))
    expected = {f"WB_{name.upper()}" for name in Settings.model_fields}

    assert expected <= documented
    for secret in (
        "WB_OPENAI_API_KEY",
        "WB_ANTHROPIC_API_KEY",
        "WB_CODEX_LOCAL_GATE_SECRET",
        "WB_AUTH_SECRET",
        "WB_AUTH_BOOTSTRAP_TOKEN",
        "WB_OIDC_CLIENT_SECRET",
        "BLOB_READ_WRITE_TOKEN",
    ):
        assert re.search(rf"(?m)^#\s*{secret}=$", example)


def test_active_env_example_values_parse(monkeypatch):
    example = (Path(__file__).parents[1] / ".env.example").read_text(encoding="utf-8")
    active = dict(re.findall(r"(?m)^(WB_[A-Z0-9_]+)=(.*)$", example))
    for key, value in active.items():
        monkeypatch.setenv(key, value)

    settings = Settings()

    assert settings.provider_mode == "fake"
    assert settings.llm_provider == "openai"
    assert settings.research_executor_enabled is False
    assert settings.research_executor_command == []
    assert settings.codex_local_enabled is False
    assert settings.auth_required is False
    assert settings.oidc_mode == "disabled"
