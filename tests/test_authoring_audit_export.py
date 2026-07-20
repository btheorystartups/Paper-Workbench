"""P4-P6: candidates, manuscripts, sections, audits, skeptical review, export."""

import json
from pathlib import Path

import pytest

from workbench.services import audits, authoring, export_service, research
from workbench.vocab import ClaimSupport, ObjectKind, SourceAccess


@pytest.fixture()
def manuscript_setup(session, project, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    src = research.register_source(
        session, project.id, title="Bryant 1986", access=SourceAccess.EXCERPT_AVAILABLE,
        authors="Bryant, R.", year=1986, venue="IEEE ToC", doi="10.1109/tc.1986.1676819",
    )
    excerpt = research.capture_excerpt(
        session, src.id, text="OBDDs give canonical forms.", locator="p. 677"
    )
    result = research.create_object(
        session, project.id, kind=ObjectKind.RESULT, title="Persistent cache speedup"
    )
    claim = research.create_claim(
        session, project.id,
        text="Cached CM reaches 2.42x cached bitset at n=16, consistent with prior canonical-form work",
        support=ClaimSupport.BOTH, excerpt_ids=[excerpt.id], research_object_ids=[result.id],
    )
    weak_claim = research.create_claim(
        session, project.id, text="CM will beat BDDs in all regimes",
        support=ClaimSupport.VERIFICATION_REQUIRED,
    )
    manuscript = authoring.create_manuscript(session, project.id, title="CM Evaluation Paper")
    session.commit()
    return {"src": src, "claim": claim, "weak": weak_claim, "ms": manuscript}


def test_candidate_validation(session, project):
    with pytest.raises(research.IntegrityError, match="paper_type"):
        authoring.create_paper_candidate(
            session, project.id, title="X", paper_type="thing",
            central_question="?", thesis="T",
        )
    cand = authoring.create_paper_candidate(
        session, project.id, title="CM benchmark paper", paper_type="computational",
        structure="algorithm_correctness_complexity_experiments",
        central_question="Is CM a useful Boolean IR?", thesis="Yes with caching",
        novelty_caveat="limited search", missing_work=["CUDD comparison at n=20"],
    )
    assert cand.body["frozen"] is False


def test_sections_and_ordering(session, manuscript_setup):
    ms = manuscript_setup["ms"]
    s1 = authoring.add_section(session, ms.id, heading="Introduction", purpose="motivate")
    s2 = authoring.add_section(
        session, ms.id, heading="Results", purpose="report",
        claim_ids=[manuscript_setup["claim"].id],
    )
    s0 = authoring.add_section(session, ms.id, heading="Abstract", position=0)
    ordered = [s.id for s in authoring.manuscript_sections(session, ms.id)]
    assert ordered == [s0.id, s1.id, s2.id]
    with pytest.raises(research.IntegrityError, match="claim"):
        authoring.add_section(session, ms.id, heading="Bad", claim_ids=["nope"])


def test_audit_findings(session, manuscript_setup):
    ms = manuscript_setup["ms"]
    authoring.add_section(
        session, ms.id, heading="Results", purpose="report",
        text="We observe a 2.42x speedup at n=16.",
        claim_ids=[manuscript_setup["claim"].id],
    )
    authoring.add_section(
        session, ms.id, heading="Discussion", text="Speedups exceed 1.5x in all cases.",
    )
    findings = audits.audit_manuscript(session, ms.id)
    codes = {f["code"] for f in findings}
    assert "section-unreferenced-numbers" in codes   # Discussion numbers, no claims
    assert "claim-verification-debt" in codes        # the VERIFICATION_REQUIRED claim
    assert "claim-source-unverified" in codes        # source not human-verified
    assert not any(f["code"] == "section-dangling-claim" for f in findings)


def test_skeptical_review_persists_ai_notes(session, manuscript_setup):
    ms = manuscript_setup["ms"]
    authoring.add_section(session, ms.id, heading="Results", text="stuff")
    notes = audits.skeptical_review(session, ms.id)
    session.commit()
    assert notes, "fake provider must yield at least one objection note"
    for n in notes:
        assert n.ai_suggested is True and n.accepted_by_user is False
        assert n.body["resolution"] == "open"


def test_export_bundle(session, manuscript_setup):
    ms = manuscript_setup["ms"]
    authoring.add_section(
        session, ms.id, heading="Results", purpose="report",
        text="Persistent caching changes the CM story.",
        claim_ids=[manuscript_setup["claim"].id],
    )
    result = export_service.export_manuscript(session, ms.id)
    files = result["files"]
    for fmt in ("md", "tex", "html", "docx", "bib", "manifest"):
        assert fmt in files and Path(files[fmt]).is_file(), fmt

    md = Path(files["md"]).read_text(encoding="utf-8")
    assert "[support: both]" in md            # support state survives export
    assert "bryant1986" in md                 # citation key rendered
    tex = Path(files["tex"]).read_text(encoding="utf-8")
    assert "\\cite{bryant1986}" in tex
    bib = Path(files["bib"]).read_text(encoding="utf-8")
    assert "@article{bryant1986" in bib and "doi = {10.1109/tc.1986.1676819}" in bib

    manifest = json.loads(Path(files["manifest"]).read_text(encoding="utf-8"))
    assert manifest["sources"]
    assert "export != submission/publication" in manifest["exported_by"]
    for entry in manifest["files"].values():
        assert len(entry["sha256"]) == 64
    # audit findings are embedded at export time (verification-debt claim exists)
    assert any(
        f["code"] == "claim-verification-debt" for f in manifest["audit_findings_at_export"]
    )
