"""Scholarly metadata providers: OpenAlex and Crossref (fresh builds — no donor code
existed). Both are keyless public APIs; we send a polite identification header/param.

Normalization: every provider returns ScholarlyWork; canonical identity is DOI
(lowercased, no https://doi.org/ prefix), falling back to normalized title+year.
Metadata is discovery-grade: imported Sources start as metadata_only/abstract_only and
human_verified=False. No provider is indispensable (ADR-3); all calls fail soft.
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

_logger = logging.getLogger("wb.scholarly")

MAILTO = "brian.droncheff@gmail.com"  # polite-pool identification, not authentication


@dataclass
class ScholarlyWork:
    title: str
    authors: list[str]
    year: int | None
    venue: str
    doi: str | None
    url: str | None
    abstract: str | None
    cited_by_count: int | None
    open_access_url: str | None
    license: str | None
    provider: str
    provider_id: str
    raw: dict = field(default_factory=dict)


def canonical_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi or None


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def work_key(work: ScholarlyWork) -> str:
    doi = canonical_doi(work.doi)
    if doi:
        return f"doi:{doi}"
    return f"title:{_norm_title(work.title)}|{work.year or ''}"


def dedupe(works: list[ScholarlyWork]) -> list[ScholarlyWork]:
    """Keep first occurrence per canonical key (callers order by preference)."""
    seen: set[str] = set()
    out = []
    for w in works:
        key = work_key(w)
        if key not in seen:
            seen.add(key)
            out.append(w)
    return out


class _HttpBase:
    def __init__(self, *, timeout: float = 30.0, session=None,
                 sleep: Callable[[float], None] = time.sleep,
                 rate_limit_seconds: float = 0.5) -> None:
        self._timeout = timeout
        self._session = session
        self._sleep = sleep
        self._rate = rate_limit_seconds
        self._last = 0.0

    def _ensure(self):
        if self._session is None:
            import httpx

            self._session = httpx.Client(
                headers={"User-Agent": f"PaperWorkbench/0.1 (mailto:{MAILTO})"}
            )
        return self._session

    def _get(self, url: str, params: dict) -> dict | None:
        wait = self._rate - (time.monotonic() - self._last)
        if wait > 0:
            self._sleep(wait)
        try:
            resp = self._ensure().get(url, params=params, timeout=self._timeout)
            self._last = time.monotonic()
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # fail soft
            _logger.warning("scholarly: %s failed: %s", url, exc)
            return None


def _invert_openalex_abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    positions = [(p, word) for word, ps in inv.items() for p in ps]
    if not positions:
        return None
    return " ".join(word for _p, word in sorted(positions))


class OpenAlexAdapter(_HttpBase):
    BASE = "https://api.openalex.org/works"

    def search(self, query: str, *, count: int = 10) -> list[ScholarlyWork]:
        data = self._get(self.BASE, {"search": query, "per-page": count, "mailto": MAILTO})
        if not data:
            return []
        works = []
        for item in data.get("results", []):
            oa = item.get("open_access") or {}
            primary = (item.get("primary_location") or {}) or {}
            source = (primary.get("source") or {}) or {}
            works.append(
                ScholarlyWork(
                    title=item.get("display_name") or "",
                    authors=[
                        (a.get("author") or {}).get("display_name", "")
                        for a in item.get("authorships", [])
                    ],
                    year=item.get("publication_year"),
                    venue=source.get("display_name") or "",
                    doi=canonical_doi(item.get("doi")),
                    url=primary.get("landing_page_url") or item.get("id"),
                    abstract=_invert_openalex_abstract(item.get("abstract_inverted_index")),
                    cited_by_count=item.get("cited_by_count"),
                    open_access_url=oa.get("oa_url"),
                    license=primary.get("license"),
                    provider="openalex",
                    provider_id=item.get("id", ""),
                    raw=item,
                )
            )
        return works


class CrossrefAdapter(_HttpBase):
    BASE = "https://api.crossref.org/works"

    def search(self, query: str, *, count: int = 10) -> list[ScholarlyWork]:
        data = self._get(self.BASE, {"query": query, "rows": count, "mailto": MAILTO})
        if not data:
            return []
        return [self._to_work(i) for i in data.get("message", {}).get("items", [])]

    def lookup_doi(self, doi: str) -> ScholarlyWork | None:
        doi = canonical_doi(doi) or ""
        if not doi:
            return None
        data = self._get(f"{self.BASE}/{doi}", {"mailto": MAILTO})
        if not data:
            return None
        return self._to_work(data.get("message", {}))

    @staticmethod
    def _to_work(item: dict) -> ScholarlyWork:
        year = None
        issued = (item.get("issued") or {}).get("date-parts") or [[None]]
        if issued and issued[0]:
            year = issued[0][0]
        licenses = item.get("license") or []
        return ScholarlyWork(
            title=(item.get("title") or [""])[0],
            authors=[
                " ".join(filter(None, [a.get("given"), a.get("family")]))
                for a in item.get("author", [])
            ],
            year=year,
            venue=(item.get("container-title") or [""])[0],
            doi=canonical_doi(item.get("DOI")),
            url=item.get("URL"),
            abstract=item.get("abstract"),
            cited_by_count=item.get("is-referenced-by-count"),
            open_access_url=None,
            license=licenses[0].get("URL") if licenses else None,
            provider="crossref",
            provider_id=item.get("DOI", ""),
            raw=item,
        )


class SemanticScholarAdapter(_HttpBase):
    """Semantic Scholar Graph API (keyless, shared rate pool — be gentle)."""

    BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
    FIELDS = "title,authors,year,venue,externalIds,url,abstract,citationCount,openAccessPdf"

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("rate_limit_seconds", 1.1)
        super().__init__(**kwargs)

    def search(self, query: str, *, count: int = 10) -> list[ScholarlyWork]:
        data = self._get(self.BASE, {"query": query, "limit": count, "fields": self.FIELDS})
        if not data:
            return []
        works = []
        for item in data.get("data", []):
            ext = item.get("externalIds") or {}
            oa = item.get("openAccessPdf") or {}
            works.append(
                ScholarlyWork(
                    title=item.get("title") or "",
                    authors=[a.get("name", "") for a in item.get("authors", [])],
                    year=item.get("year"),
                    venue=item.get("venue") or "",
                    doi=canonical_doi(ext.get("DOI")),
                    url=item.get("url"),
                    abstract=item.get("abstract"),
                    cited_by_count=item.get("citationCount"),
                    open_access_url=oa.get("url"),
                    license=oa.get("license"),
                    provider="semanticscholar",
                    provider_id=item.get("paperId", ""),
                    raw=item,
                )
            )
        return works


class UnpaywallAdapter(_HttpBase):
    """Unpaywall: lawful open-access location lookup by DOI (email-identified, keyless).
    Returns OA info only — it does not grant permission to copy arbitrary full text."""

    BASE = "https://api.unpaywall.org/v2"

    def lookup(self, doi: str) -> dict | None:
        doi = canonical_doi(doi) or ""
        if not doi:
            return None
        data = self._get(f"{self.BASE}/{doi}", {"email": MAILTO})
        if not data:
            return None
        best = data.get("best_oa_location") or {}
        return {
            "doi": doi,
            "is_oa": data.get("is_oa", False),
            "oa_status": data.get("oa_status"),
            "license": best.get("license"),
            "oa_url": best.get("url"),
            "version": best.get("version"),
            "checked_via": "unpaywall",
        }


class FakeScholarlyProvider:
    """Deterministic works for offline tests; includes a DOI-duplicate pair to exercise dedup."""

    def search(self, query: str, *, count: int = 10) -> list[ScholarlyWork]:
        base = ScholarlyWork(
            title=f"Graph-Based Algorithms for {query.title()}",
            authors=["R. E. Bryant"],
            year=1986,
            venue="IEEE Transactions on Computers",
            doi="10.1109/tc.1986.1676819",
            url="https://doi.org/10.1109/tc.1986.1676819",
            abstract="[FAKE] Simulated abstract.",
            cited_by_count=10000,
            open_access_url=None,
            license=None,
            provider="fake",
            provider_id="fake:1",
        )
        dup = ScholarlyWork(**{**base.__dict__, "provider": "fake2", "provider_id": "fake:2",
                               "raw": {}})
        other = ScholarlyWork(
            title=f"[FAKE] A Survey of {query.title()}",
            authors=["A. Author"],
            year=2020,
            venue="Fake Journal",
            doi=None,
            url="https://example.org/survey",
            abstract=None,
            cited_by_count=3,
            open_access_url="https://example.org/survey.pdf",
            license="cc-by",
            provider="fake",
            provider_id="fake:3",
        )
        return [base, dup, other][:count]
