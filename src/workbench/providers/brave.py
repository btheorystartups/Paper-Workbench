"""Brave Search adapter — copied from POP Card Studio providers/brave.py (itself adapted
from Nexus), now owned by Paper-Workbench; imports nothing from either project.

Mechanics preserved: retry/backoff on 429/5xx, per-request rate limiting, fail-soft empty
result on error, snippet-only (snippets are discovery, never evidence). Added here: an
optional JSON-file response cache (mechanic from Nexus brave_search.py) so repeated
literature queries don't burn quota.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from ..config import get_settings
from .protocols import SearchResult

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
_logger = logging.getLogger("wb.brave")

_RETRYABLE = {429, 500, 502, 503, 504}


class BraveSearchAdapter:
    """SearchProvider. Never raises on API failure — returns [] and logs (discovery is
    advisory; a failed search must not break the research workflow)."""

    def __init__(
        self,
        api_key: str,
        *,
        rate_limit_seconds: float = 1.1,
        timeout: float = 20.0,
        max_retries: int = 3,
        cache_dir: str | None = None,
        session=None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._rate_limit = rate_limit_seconds
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep
        self._last_request_at = 0.0
        self._session = session
        self._cache_dir = Path(cache_dir) if cache_dir else None
        if self._session is None and api_key:
            import httpx

            self._session = httpx.Client(
                headers={"Accept": "application/json", "X-Subscription-Token": api_key}
            )

    def search(self, query: str, *, filters: dict | None = None) -> list[SearchResult]:
        if not self._api_key or self._session is None:
            _logger.warning("brave: no API key configured; returning no results")
            return []
        count = (filters or {}).get("count", 5)
        cached = self._cache_load(query, count)
        if cached is not None:
            return _parse(cached)
        wait = self._rate_limit - (time.monotonic() - self._last_request_at)
        if wait > 0:
            self._sleep(wait)
        params = {"q": query, "count": count}
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._session.get(BRAVE_API_URL, params=params, timeout=self._timeout)
                self._last_request_at = time.monotonic()
                if resp.status_code in _RETRYABLE and attempt < self._max_retries:
                    self._sleep(2 ** (attempt - 1))
                    continue
                resp.raise_for_status()
                data = resp.json()
                self._cache_save(query, count, data)
                return _parse(data)
            except Exception as exc:  # network/parse — fail soft
                _logger.warning("brave: attempt=%d error=%s", attempt, exc)
                if attempt < self._max_retries:
                    self._sleep(2**attempt)
        _logger.error("brave: search failed query=%r", query)
        return []

    # --- response cache (fetched_at recorded; discovery data, never evidence) ---

    def _cache_path(self, query: str, count: int) -> Path | None:
        if self._cache_dir is None:
            return None
        key = hashlib.sha256(f"{query}|{count}".encode()).hexdigest()[:32]
        return self._cache_dir / f"brave_{key}.json"

    def _cache_load(self, query: str, count: int) -> dict | None:
        path = self._cache_path(query, count)
        if path is None or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        except Exception:
            return None

    def _cache_save(self, query: str, count: int, data: dict) -> None:
        path = self._cache_path(query, count)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"query": query, "count": count, "fetched_at": time.time(), "response": data}
                ),
                encoding="utf-8",
            )
        except OSError:
            pass  # cache is best-effort


def _parse(data: dict) -> list[SearchResult]:
    results: list[SearchResult] = []
    for i, item in enumerate(data.get("web", {}).get("results", []), start=1):
        url = item.get("url", "")
        results.append(
            SearchResult(
                rank=i,
                title=item.get("title", ""),
                url=url,
                publisher=urlparse(url).netloc.lower().removeprefix("www.") or None,
                snippet=item.get("description", ""),
                provider_payload={"provider": "brave"},
            )
        )
    return results


def build_from_settings() -> BraveSearchAdapter:
    from ..config import brave_api_key

    settings = get_settings()
    return BraveSearchAdapter(
        brave_api_key(),
        rate_limit_seconds=settings.brave_rate_limit_seconds,
        cache_dir=str(Path(settings.data_dir) / "cache"),
    )
