"""Expansion slice: semantic retrieval, venues, roles, portfolio, PDF/JATS export, evals."""

import pytest

from workbench.services import (
    authoring, literature, portfolio, research, security, semantic, venues,
)
from workbench.vocab import ClaimSupport, ObjectKind, SourceAccess


# --- semantic ---

def test_semantic_index_and_search_scoped(session, project):
    research.create_object(session, project.id, kind=ObjectKind.RESULT,
                           title="Persistent cache speedup for boolean evaluation")
    research.create_object(session, project.id, kind=ObjectKind.NOTE,
                           title="Grocery list for the weekend")
    info = semantic.index_project(session, project.id)
    assert info["indexed"] == 2 and info["model"] == "fake-hash-64"
    hits = semantic.semantic_search(session, project.id, "boolean cache evaluation")
    assert hits[0]["title"].startswith("Persistent cache")
    assert all(h["kind"] == "similarity" for h in hits)  # never evidence

    # other project sees nothing
    ws2 = research.create_workspace(session, "W2")
    p2 = research.create_project(session, ws2.id, "P2")
    assert semantic.semantic_search(session, p2.id, "boolean") == []


# --- venues ---

def test_venue_rules_and_compliance(session, project):
    with pytest.raises(research.IntegrityError, match="rules_source"):
        venues.create_venue(session, project.workspace_id, name="J", rules={}, rules_source=" ")
    with pytest.raises(research.IntegrityError, match="unknown rule"):
        venues.create_venue(session, project.workspace_id, name="J",
                            rules={"bogus": 1}, rules_source="site")
    venue = venues.create_venue(
        session, project.workspace_id, name="J. Boolean Computation",
        rules={"word_limit": 5, "required_sections": ["Abstract", "Results"],
               "ai_disclosure_required": True},
        rules_source="journal website 2026-07-20",
    )
    ms = authoring.create_manuscript(session, project.id, title="MS")
    authoring.add_section(session, ms.id, heading="Results",
                          text="one two three four five six seven")
    findings = venues.audit_venue_compliance(session, ms.id, venue.id)
    codes = {f["code"] for f in findings}
    assert {"venue-unverified", "venue-word-limit", "venue-missing-section",
            "venue-ai-disclosure"} <= codes
    # advisory (info) until verified
    assert all(f["severity"] == "info" for f in findings)
    venues.verify_venue(session, venue.id)
    findings2 = venues.audit_venue_compliance(session, ms.id, venue.id)
    assert any(f["severity"] == "warning" for f in findings2)


# --- roles ---

def test_roles_and_grace_mode(session, project):
    owner = security.create_user(session, "Brian")
    reviewer = security.create_user(session, "Rev")
    # grace mode: no members yet → anyone acting locally is owner
    security.require_role(session, project.id, owner.id, "owner")
    security.add_member(session, project.id, owner.id, "owner")
    security.add_member(session, project.id, reviewer.id, "reviewer")
    security.require_role(session, project.id, reviewer.id, "reviewer")
    with pytest.raises(security.Forbidden):
        security.require_role(session, project.id, reviewer.id, "coauthor")
    stranger = security.create_user(session, "S")
    with pytest.raises(security.Forbidden):
        security.require_role(session, project.id, stranger.id, "reviewer")


# --- portfolio ---

def test_portfolio_unpublished_and_usage(session, project):
    used = research.create_object(session, project.id, kind=ObjectKind.RESULT, title="Used result")
    unused = research.create_object(session, project.id, kind=ObjectKind.RESULT, title="Orphan result")
    claim = research.create_claim(
        session, project.id, text="c", support=ClaimSupport.RESEARCH_RESULT,
        research_object_ids=[used.id],
    )
    ms = authoring.create_manuscript(session, project.id, title="MS")
    section = authoring.add_section(session, ms.id, heading="R", claim_ids=[claim.id])

    unpub = portfolio.unpublished_results(session, project.workspace_id)
    ids = {r["object_id"] for r in unpub}
    assert unused.id in ids and used.id not in ids

    usage = portfolio.result_usage(session, used.id)
    assert usage["claims"] == [claim.id]
    assert usage["sections"][0]["section_id"] == section.id

    found = portfolio.workspace_search(session, project.workspace_id, "orphan")
    assert found and found[0]["id"] == unused.id


def test_rerun_saved_search(session, project):
    saved, works = literature.run_search(
        session, project.id, provider="openalex", query="boolean"
    )
    saved2, works2 = portfolio.rerun_saved_search(session, saved.id)
    assert saved2.query == saved.query and len(works2) == len(works)


# --- export pdf/jats ---

def test_pdf_and_jats_export(session, project, tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config
    config.get_settings.cache_clear()
    from workbench.services import export_service

    src = research.register_source(
        session, project.id, title="Prior", access=SourceAccess.EXCERPT_AVAILABLE,
        authors="A. B.", year=2001, doi="10.1/y",
    )
    excerpt = research.capture_excerpt(session, src.id, text="q", locator="p. 2")
    claim = research.create_claim(
        session, project.id, text="Supported claim (with parentheses)",
        support=ClaimSupport.EXTERNAL_SOURCE, excerpt_ids=[excerpt.id],
    )
    ms = authoring.create_manuscript(session, project.id, title="PDF Test")
    authoring.add_section(session, ms.id, heading="Results", text="Body text.",
                          claim_ids=[claim.id])
    result = export_service.export_manuscript(session, ms.id, formats=["pdf", "jats"])
    pdf = Path(result["files"]["pdf"]).read_bytes()
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    import pypdf
    reader = pypdf.PdfReader(str(result["files"]["pdf"]))
    text = "".join(p.extract_text() for p in reader.pages)
    assert "PDF Test" in text and "Supported claim" in text
    jats = Path(result["files"]["jats"]).read_text(encoding="utf-8")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(jats)
    assert root.tag == "article"
    assert "Supported claim" in jats and "mixed-citation" in jats


# --- evals ---

def test_eval_harness_all_green(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'ev.sqlite3'}")
    from workbench import config, db
    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    db.create_all()
    from workbench import evals
    report = evals.run(db.session_factory())
    for row in report["scenarios"]:
        assert not row["missed"], row
        assert not row["false_hits"], row
    for code, m in report["metrics"].items():
        assert m["recall"] in (None, 1.0), (code, m)
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
