"""Live chat adapters: OpenAI (primary, per user's 'converse with GPT' requirement) and
Anthropic. Patterns copied from Nexus (raw-httpx Anthropic call in ai_email_service.py;
injectable-client JSON-validated OpenAI adapter in openai_llm.py) and POP (lazy SDK import).

Both adapters:
- receive a fully assembled system prompt + message list (context assembly and
  untrusted-content fencing happen in services.dialogue, not here);
- ask the model for an optional fenced JSON action block, parsed defensively — a reply
  is never trusted to be well-formed;
- return usage so cost is recorded in turn provenance.
"""

import json
import logging
import re

from .protocols import ChatResult

_logger = logging.getLogger("wb.llm")

_ACTION_BLOCK_RE = re.compile(r"```wb-actions\s*(.*?)\s*```", re.S)


def parse_action_block(text: str) -> tuple[str, list[dict]]:
    """Split a reply into prose and a validated list of proposed-action dicts.
    Malformed blocks are dropped (logged), never guessed at."""
    m = _ACTION_BLOCK_RE.search(text)
    if not m:
        return text, []
    prose = (text[: m.start()] + text[m.end():]).strip()
    try:
        raw = json.loads(m.group(1))
        actions = [
            a
            for a in raw
            if isinstance(a, dict) and isinstance(a.get("kind"), str) and "payload" in a
        ]
        return prose, actions
    except (json.JSONDecodeError, TypeError):
        _logger.warning("llm: dropping malformed wb-actions block")
        return prose, []


class OpenAIChatAdapter:
    def __init__(self, api_key: str, *, client=None) -> None:
        self._api_key = api_key
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI  # lazy: no hard dependency in fake mode

            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def chat(
        self, *, system: str, messages: list[dict], model: str, max_output_tokens: int
    ) -> ChatResult:
        client = self._ensure_client()
        response = client.responses.create(
            model=model,
            instructions=system,
            input=[{"role": m["role"], "content": m["content"]} for m in messages],
            max_output_tokens=max_output_tokens,
        )
        text = response.output_text or ""
        prose, actions = parse_action_block(text)
        usage = getattr(response, "usage", None)
        return ChatResult(
            text=prose,
            model=model,
            provider_request_id=getattr(response, "id", ""),
            proposed_actions=actions,
            usage=usage.model_dump() if hasattr(usage, "model_dump") else {},
        )


class AnthropicChatAdapter:
    """Raw httpx call (Nexus _call_claude pattern) — dependency-light, injectable."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, *, session=None, timeout: float = 120.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._session = session

    def _ensure_session(self):
        if self._session is None:
            import httpx

            self._session = httpx.Client(
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
            )
        return self._session

    def chat(
        self, *, system: str, messages: list[dict], model: str, max_output_tokens: int
    ) -> ChatResult:
        session = self._ensure_session()
        resp = session.post(
            self.API_URL,
            json={
                "model": model,
                "system": system,
                "messages": messages,
                "max_tokens": max_output_tokens,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        prose, actions = parse_action_block(text)
        return ChatResult(
            text=prose,
            model=data.get("model", model),
            provider_request_id=data.get("id", ""),
            proposed_actions=actions,
            usage=data.get("usage", {}),
        )
