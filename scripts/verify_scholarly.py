"""One-shot scholarly-provider verification (2 live metadata reads, keyless public APIs).

Run: python scripts/verify_scholarly.py
"""

import sys

sys.path.insert(0, "src")

from workbench.providers.scholarly import CrossrefAdapter, OpenAlexAdapter  # noqa: E402


def main() -> None:
    oa = OpenAlexAdapter().search("binary decision diagram boolean function", count=3)
    print(f"openalex: {len(oa)} works")
    for w in oa:
        print(f"  {w.year} {w.title[:60]}  doi={w.doi}  cited_by={w.cited_by_count}")

    cr = CrossrefAdapter().lookup_doi("10.1109/TC.1986.1676819")
    if cr:
        print(f"crossref lookup: {cr.title[:60]} ({cr.year}) doi={cr.doi} venue={cr.venue}")
    else:
        print("crossref lookup: FAILED")


if __name__ == "__main__":
    main()
