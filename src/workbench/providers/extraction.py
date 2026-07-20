"""Live HTTP extraction provider: SSRF-validated fetch + deterministic HTML parsing.
Every URL passes assert_safe_url (DNS-rebinding-aware) before any socket opens; failures
return a fetch_ok=False page, never an exception (discovery is advisory)."""

import hashlib
import logging

from ..ingest.safe_fetch import UnsafeUrlError, assert_safe_url, parse_html
from .protocols import ExtractedPage

_logger = logging.getLogger("wb.extract")

MAX_BYTES = 5_000_000


class HttpExtractionProvider:
    def __init__(self, *, timeout: float = 30.0, session=None) -> None:
        self._timeout = timeout
        self._session = session

    def _ensure_session(self):
        if self._session is None:
            import httpx

            self._session = httpx.Client(
                follow_redirects=True,
                headers={"User-Agent": "PaperWorkbench/0.1 (research tool)"},
            )
        return self._session

    def fetch(self, url: str) -> ExtractedPage:
        try:
            safe_url = assert_safe_url(url)
        except UnsafeUrlError as exc:
            return ExtractedPage(
                url=url, content_hash="", extracted_text="", fetch_ok=False,
                error=f"unsafe url: {exc}",
            )
        try:
            resp = self._ensure_session().get(safe_url, timeout=self._timeout)
            resp.raise_for_status()
            body = resp.content[:MAX_BYTES].decode(resp.encoding or "utf-8", errors="replace")
        except Exception as exc:  # network — fail soft
            _logger.warning("extract: fetch failed url=%s error=%s", safe_url, exc)
            return ExtractedPage(
                url=safe_url, content_hash="", extracted_text="", fetch_ok=False,
                error=str(exc),
            )
        parsed = parse_html(body)
        return ExtractedPage(
            url=safe_url,
            content_hash=hashlib.sha256(body.encode()).hexdigest(),
            extracted_text=parsed.text,
            http_metadata={"status": resp.status_code, "content_type": resp.headers.get("content-type", "")},
            title=parsed.title,
            publisher=parsed.publisher,
            author=parsed.author,
            published_at=parsed.published_at,
        )
