"""Provider registry (pattern from POP providers/registry.py): config selects fake vs
live; live requires explicit WB_PROVIDER_MODE=live AND a key, otherwise fake is used and
a warning is logged. No domain code constructs adapters directly.
"""

import logging

from ..config import anthropic_api_key, get_settings, openai_api_key
from .fakes import FakeChatProvider, FakeExtractionProvider, FakeSearchProvider
from .protocols import ChatProvider, ExtractionProvider, SearchProvider

_logger = logging.getLogger("wb.providers")


def provider_mode() -> str:
    return get_settings().provider_mode.lower()


def get_search_provider() -> SearchProvider:
    if provider_mode() == "live":
        from ..config import brave_api_key

        if brave_api_key():
            from .brave import build_from_settings

            return build_from_settings()
        _logger.warning("providers: live mode but no Brave key; using fake search")
    return FakeSearchProvider()


def get_extraction_provider() -> ExtractionProvider:
    # Live HTTP extraction arrives with the ingestion slice (P2); fake until then.
    return FakeExtractionProvider()


def get_chat_provider() -> ChatProvider:
    settings = get_settings()
    if provider_mode() == "live":
        if settings.llm_provider == "anthropic" and anthropic_api_key():
            from .llm import AnthropicChatAdapter

            return AnthropicChatAdapter(anthropic_api_key())
        if settings.llm_provider == "openai" and openai_api_key():
            from .llm import OpenAIChatAdapter

            return OpenAIChatAdapter(openai_api_key())
        _logger.warning("providers: live mode but no usable LLM key; using fake chat")
    return FakeChatProvider()


def chat_model_name() -> str:
    settings = get_settings()
    if provider_mode() != "live":
        return "fake"
    return settings.anthropic_model if settings.llm_provider == "anthropic" else settings.llm_model
