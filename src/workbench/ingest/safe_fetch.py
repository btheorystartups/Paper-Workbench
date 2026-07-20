"""SSRF guard and URL canonicalization for page retrieval.

Copied verbatim from POP Card Studio modules/research/safe_fetch.py (self-contained; no
internal imports); now owned by Paper-Workbench. Pure/synchronous validation plus a small
HTML→text+metadata extractor. Actual network egress is performed by the configured
ExtractionProvider adapter; in fake mode no socket is opened at all.
"""

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrlError(ValueError):
    """Raised when a URL fails SSRF validation. Callers quarantine, never fetch."""


def canonicalize_url(url: str) -> str:
    """Lowercase scheme/host, strip fragments and default ports, drop trailing dot.
    Kept deliberately conservative: canonicalization is for dedup/identity, not rewriting."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    netloc = host
    if parsed.port and not (
        (scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)
    ):
        netloc = f"{host}:{parsed.port}"
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def _ip_is_blocked(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        # cloud metadata endpoint
        or str(addr) == "169.254.169.254"
    )


def assert_safe_url(url: str, *, resolver=socket.getaddrinfo, resolve: bool = True) -> str:
    """Validate scheme and literal-IP hosts, then (when `resolve`) resolve the hostname and
    reject private/link-local/metadata addresses (DNS-rebinding-aware: every resolved address
    must be public). Returns the canonical URL. Raises UnsafeUrlError otherwise.

    `resolve=False` skips hostname DNS but still blocks literal private IPs — used in fake
    provider mode, where no socket is ever opened, so tests stay fully offline. Live retrieval
    always resolves.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"scheme '{parsed.scheme}' not allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("missing host")
    # Literal IP hosts are always checked; hostnames are resolved only when `resolve`.
    try:
        ipaddress.ip_address(host)
        candidates = [host]
    except ValueError:
        if not resolve:
            return canonicalize_url(url)
        try:
            infos = resolver(host, None)
        except socket.gaierror as exc:
            raise UnsafeUrlError(f"DNS resolution failed for {host}") from exc
        candidates = [info[4][0] for info in infos]
    if not candidates:
        raise UnsafeUrlError(f"no addresses resolved for {host}")
    for ip in candidates:
        if _ip_is_blocked(ip):
            raise UnsafeUrlError(f"host resolves to blocked address {ip}")
    return canonicalize_url(url)


# --- Lightweight HTML extraction (bibliographic metadata + normalized text) ---

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_ENTITY_MAP = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&apos;": "'"}


def _clean(text: str) -> str:
    for ent, ch in _ENTITY_MAP.items():
        text = text.replace(ent, ch)
    return " ".join(text.split())


def _meta(html: str, *names: str) -> str | None:
    for name in names:
        m = re.search(
            rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\']',
            html,
            re.I | re.S,
        )
        if m:
            return _clean(m.group(1)) or None
    return None


@dataclass
class ParsedHtml:
    title: str | None
    publisher: str | None
    author: str | None
    published_at: str | None
    text: str


def parse_html(html: str) -> ParsedHtml:
    """Extract title, publisher, author, publication date, and normalized text using
    OpenGraph/standard meta tags. Deterministic and dependency-free (no readability lib)."""
    body = _SCRIPT_STYLE_RE.sub(" ", html)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    return ParsedHtml(
        title=_meta(html, "og:title") or (_clean(title_m.group(1)) if title_m else None),
        publisher=_meta(html, "og:site_name", "publisher"),
        author=_meta(html, "author", "article:author"),
        published_at=_meta(html, "article:published_time", "og:published_time", "date"),
        text=_clean(_TAG_RE.sub(" ", body)),
    )
