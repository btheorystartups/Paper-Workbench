"""Provider protocols (copied and adapted from POP Card Studio providers/protocols.py).

Adapters implement these; domain records never depend on a concrete provider. Fakes ship
first so every workflow is testable offline; live adapters activate only with keys +
WB_PROVIDER_MODE=live.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SearchResult:
    rank: int
    title: str
    url: str
    publisher: str | None
    snippet: str  # discovery only — never evidence (ADR-5)
    provider_payload: dict = field(default_factory=dict)


@dataclass
class ExtractedPage:
    url: str
    content_hash: str
    extracted_text: str
    http_metadata: dict = field(default_factory=dict)
    title: str | None = None
    publisher: str | None = None
    author: str | None = None
    published_at: str | None = None  # ISO-8601 string if discoverable
    fetch_ok: bool = True
    error: str | None = None


@dataclass
class ChatResult:
    """One assistant reply. `proposed_actions` are structured suggestions the model made;
    they are persisted as ProposedAction rows, never executed directly."""

    text: str
    model: str
    provider_request_id: str
    proposed_actions: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


class SearchProvider(Protocol):
    def search(self, query: str, *, filters: dict | None = None) -> list[SearchResult]: ...


class ExtractionProvider(Protocol):
    def fetch(self, url: str) -> ExtractedPage: ...


class ChatProvider(Protocol):
    def chat(
        self,
        *,
        system: str,
        messages: list[dict],
        model: str,
        max_output_tokens: int,
    ) -> ChatResult: ...
