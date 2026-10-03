"""Live HTTP extraction provider: SSRF-validated fetch + deterministic HTML parsing.
Every URL passes assert_safe_url (DNS-rebinding-aware) before any socket opens; failures
return a fetch_ok=False page, never an exception (discovery is advisory)."""

import hashlib
import logging
from urllib.parse import urljoin

from ..ingest.safe_fetch import UnsafeUrlError, assert_safe_url, parse_html
from .protocols import ExtractedPage

_logger = logging.getLogger("wb.extract")

MAX_BYTES = 5_000_000
MAX_REDIRECTS = 4


class HttpExtractionProvider:
    def __init__(self, *, timeout: float = 30.0, session=None) -> None:
        self._timeout = timeout
        self._session = session

    def _ensure_session(self):
        if self._session is None:
            import httpx

            self._session = httpx.Client(
                follow_redirects=False,
                headers={"User-Agent": "PaperWorkbench/0.1 (research tool)"},
            )
        return self._session

    def fetch(self, url: str) -> ExtractedPage:
        try:
            safe_url = assert_safe_url(url)
        except UnsafeUrlError as exc:
            return ExtractedPage(
                url=url,
                content_hash="",
                extracted_text="",
                fetch_ok=False,
                error=f"unsafe url: {exc}",
            )
        try:
            client = self._ensure_session()
            current_url = safe_url
            response = None
            body_bytes = b""
            for _redirect in range(MAX_REDIRECTS + 1):
                with client.stream(
                    "GET", current_url, timeout=self._timeout, follow_redirects=False
                ) as candidate:
                    if candidate.status_code in {301, 302, 303, 307, 308}:
                        location = candidate.headers.get("location")
                        if not location:
                            raise ValueError("redirect response has no Location header")
                        current_url = assert_safe_url(urljoin(current_url, location))
                        continue
                    candidate.raise_for_status()
                    chunks: list[bytes] = []
                    received = 0
                    for chunk in candidate.iter_bytes():
                        received += len(chunk)
                        if received > MAX_BYTES:
                            raise ValueError(f"response exceeds {MAX_BYTES} byte intake limit")
                        chunks.append(chunk)
                    body_bytes = b"".join(chunks)
                    response = candidate
                    break
            if response is None:
                raise ValueError(f"URL exceeded {MAX_REDIRECTS} redirects")
            body = body_bytes.decode(response.encoding or "utf-8", errors="replace")
        except Exception as exc:  # network — fail soft
            _logger.warning("extract: fetch failed url=%s error=%s", safe_url, exc)
            return ExtractedPage(
                url=safe_url,
                content_hash="",
                extracted_text="",
                fetch_ok=False,
                error=str(exc),
            )
        parsed = parse_html(body)
        return ExtractedPage(
            url=current_url,
            content_hash=hashlib.sha256(body_bytes).hexdigest(),
            extracted_text=parsed.text,
            http_metadata={
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "redirects_followed": _redirect,
                "byte_count": len(body_bytes),
            },
            title=parsed.title,
            publisher=parsed.publisher,
            author=parsed.author,
            published_at=parsed.published_at,
        )
