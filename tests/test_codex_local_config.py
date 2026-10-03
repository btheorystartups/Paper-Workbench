"""Pending Codex limits are configurable; selecting the adapter fails closed."""

import pytest
from pydantic import ValidationError

from workbench.config import Settings
from workbench.providers import registry
from workbench.providers.fakes import FakeChatProvider


@pytest.fixture(autouse=True)
def isolated_codex_limits(monkeypatch):
    monkeypatch.delenv("WB_CODEX_LOCAL_MAX_INPUT_TOKENS", raising=False)
    monkeypatch.delenv("WB_CODEX_LOCAL_MAX_OUTPUT_TOKENS", raising=False)


def test_default_limits_preserve_existing_chat_configuration():
    settings = Settings(provider_mode="fake", llm_provider="openai")
    assert settings.codex_local_max_input_tokens == 200_000
    assert settings.codex_local_max_output_tokens == 1_000_000
    assert settings.llm_max_output_tokens == 4096


def test_limits_are_editable_via_environment(monkeypatch):
    monkeypatch.setenv("WB_CODEX_LOCAL_MAX_INPUT_TOKENS", "150000")
    monkeypatch.setenv("WB_CODEX_LOCAL_MAX_OUTPUT_TOKENS", "800000")
    settings = Settings()
    assert settings.codex_local_max_input_tokens == 150_000
    assert settings.codex_local_max_output_tokens == 800_000


@pytest.mark.parametrize("suffix", ["INPUT", "OUTPUT"])
@pytest.mark.parametrize("value", ["0", "-1", "1.5", "unlimited", ""])
def test_limits_reject_invalid_configuration(monkeypatch, suffix, value):
    monkeypatch.setenv(f"WB_CODEX_LOCAL_MAX_{suffix}_TOKENS", value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("mode", ["fake", "live"])
def test_codex_selection_never_falls_back_or_reads_api_keys(monkeypatch, mode):
    settings = Settings(provider_mode=mode, llm_provider="codex_local")
    monkeypatch.setattr(registry, "get_settings", lambda: settings)

    def unexpected_fallback(*args, **kwargs):
        pytest.fail("Codex selection must fail before fallback or API-key lookup")

    monkeypatch.setattr(registry, "FakeChatProvider", unexpected_fallback)
    monkeypatch.setattr(registry, "openai_api_key", unexpected_fallback)
    monkeypatch.setattr(registry, "anthropic_api_key", unexpected_fallback)
    with pytest.raises(RuntimeError, match="codex_local is disabled"):
        registry.get_chat_provider()


def test_existing_offline_provider_is_unchanged(monkeypatch):
    settings = Settings(provider_mode="fake", llm_provider="openai")
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    assert isinstance(registry.get_chat_provider(), FakeChatProvider)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_timeout_must_be_finite_and_positive(timeout):
    with pytest.raises(ValidationError):
        Settings(codex_local_timeout_seconds=timeout)
