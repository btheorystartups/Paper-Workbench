"""P3: scholarly normalization/dedup, import rules, screening, novelty guardrails."""

import pytest

from workbench.providers.scholarly import (
    CrossrefAdapter,
    FakeScholarlyProvider,
    canonical_doi,
    dedupe,
)
from workbench.services import literature, research
from workbench.vocab import Novelty


def test_canonical_doi():
    assert canonical_doi("https://doi.org/10.1109/TC.1986.1676819") == "10.1109/tc.1986.1676819"
    assert canonical_doi("  10.1000/ABC ") == "10.1000/abc"
    assert canonical_doi(None) is None
    assert canonical_doi("") is None


def test_dedupe_by_doi_and_title():
    works = FakeScholarlyProvider().search("boolean matrices")
    assert len(works) == 3  # includes a DOI duplicate
    assert len(dedupe(works)) == 2


def test_crossref_normalization():
    item = {
        "title": ["A Paper"], "DOI": "10.1/X",
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "issued": {"date-parts": [[1843, 1]]},
        "container-title": ["Journal"], "URL": "https://doi.org/10.1/x",
        "is-referenced-by-count": 7,
    }
    work = CrossrefAdapter._to_work(item)
    assert work.doi == "10.1/x"
    assert work.authors == ["Ada Lovelace"]
    assert work.year == 1843


def test_search_and_import_flow(session, project):
    saved, works = literature.run_search(
        session, project.id, provider="openalex", query="boolean matrices"
    )
    assert saved.last_result_count == 2  # deduped
    assert saved.protocol_note == "exploratory"  # never "systematic" by default

    src, created = literature.import_work(session, project.id, works[0])
    assert created is True
    assert str(src.access) == "abstract_only"  # fake work has an abstract
    assert src.human_verified is False
    # re-import same DOI → dedup to existing
    src2, created2 = literature.import_work(session, project.id, works[0])
    assert created2 is False and src2.id == src.id


def test_screening_and_matrix(session, project):
    _saved, works = literature.run_search(
        session, project.id, provider="openalex", query="q"
    )
    src, _ = literature.import_work(session, project.id, works[0])
    with pytest.raises(research.IntegrityError, match="state"):
        literature.set_screening(session, project.id, src.id, state="bogus")
    literature.set_screening(
        session, project.id, src.id, state="include", relationship="supports",
        reason="canonical BDD reference", method="ROBDD construction",
    )
    matrix = literature.literature_matrix(session, project.id)
    assert matrix[0]["state"] == "include"
    assert matrix[0]["human_verified"] is False


def test_novelty_requires_coverage_note(session, project):
    with pytest.raises(research.IntegrityError, match="coverage"):
        literature.assess_contribution(
            session, project.id, title="CM as IR", statement="CM is a novel Boolean IR",
            novelty=Novelty.APPARENTLY_NOVEL_LIMITED_SEARCH, coverage_note="  ",
        )
    obj = literature.assess_contribution(
        session, project.id, title="CM as IR", statement="CM is a novel Boolean IR",
        novelty=Novelty.APPARENTLY_NOVEL_LIMITED_SEARCH,
        coverage_note="OpenAlex+Crossref keyword search 2026-07; no BDD-adjacent sweep yet",
    )
    assert obj.body["provisional"] is True
    assert obj.body["novelty"] == "apparently_novel_limited_search"
