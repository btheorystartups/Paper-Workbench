"""Deterministic fakes. Default providers (WB_PROVIDER_MODE=fake): the entire system runs
and tests offline, and every fake response is clearly labeled as simulated in provenance.
"""

import hashlib
import json

from .protocols import ChatResult, ExtractedPage, SearchResult


class FakeSearchProvider:
    def search(self, query: str, *, filters: dict | None = None) -> list[SearchResult]:
        count = (filters or {}).get("count", 3)
        seed = hashlib.sha256(query.encode()).hexdigest()[:8]
        return [
            SearchResult(
                rank=i,
                title=f"[FAKE] Result {i} for '{query}'",
                url=f"https://example.org/{seed}/{i}",
                publisher="example.org",
                snippet=f"Simulated snippet {i} for query '{query}'. Discovery only.",
                provider_payload={"provider": "fake"},
            )
            for i in range(1, count + 1)
        ]


class FakeExtractionProvider:
    def fetch(self, url: str) -> ExtractedPage:
        text = f"[FAKE] Simulated page text for {url}."
        return ExtractedPage(
            url=url,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
            extracted_text=text,
            title=f"[FAKE] Page at {url}",
            publisher="example.org",
            fetch_ok=True,
        )


class FakeChatProvider:
    """Echoes the grounding contract: replies reference the context object ids it was
    given and propose no actions unless the last user message contains 'propose:'.
    Deterministic so dialogue tests can assert exact behavior."""

    def chat(
        self,
        *,
        system: str,
        messages: list[dict],
        model: str,
        max_output_tokens: int,
    ) -> ChatResult:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        context_ids = sorted(set(_extract_context_ids(system)))
        # Cite context using the same [ctx:ID] convention the real model is instructed to
        # use, so the fake is a faithful stand-in for a grounded, injection-safe model.
        cited = ", ".join(f"[ctx:{c}]" for c in context_ids) if context_ids else "none"
        reply = (
            "[FAKE-MODEL] This is a simulated reply (no live provider configured). "
            f"Context objects visible: {cited}. "
            f"You said: {last_user[:200]}"
        )
        actions: list[dict] = []
        if "propose:" in last_user:
            title = last_user.split("propose:", 1)[1].strip() or "Untitled suggestion"
            actions.append(
                {
                    "kind": "create_object",
                    "payload": {"kind": "task", "title": title, "body": {}},
                    "basis": context_ids,
                }
            )
        digest = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]
        return ChatResult(
            text=reply,
            model="fake",
            provider_request_id=f"fake-{digest}",
            proposed_actions=actions,
            usage={"simulated": True},
        )


def _extract_context_ids(system: str) -> list[str]:
    ids = []
    for line in system.splitlines():
        if line.startswith("- [ctx:"):
            ids.append(line.split("]", 1)[0].removeprefix("- [ctx:"))
    return ids
