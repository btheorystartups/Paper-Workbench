"""JATS DTD validation + PDF renderer selection/fallback."""

from pathlib import Path

import pytest

from workbench.services import authoring, export_service, research
from workbench.services.jats import validate_jats
from workbench.vocab import ClaimSupport, SourceAccess


def test_jats_subset_dtd_validates_real_output():
    from workbench.services.export_service import _jats_xml

    class _MS:
        id = "m1"
        title = "A & B < C study"

    class _Sec:
        id = "s1"
        title = "Results"
        body = {"text": "Body text", "claim_ids": []}

    xml = _jats_xml(_MS(), [_Sec()], {}, {}, session=None)
    result = validate_jats(xml)
    assert result.well_formed is True
    assert result.method == "dtd-subset"
    assert result.valid is True, result.errors


def test_jats_validation_catches_structural_violation():
    bad = "<article><body><sec><p>no title element</p></sec></body></article>"
    result = validate_jats(bad)
    # well-formed XML but violates the DTD (sec requires a title first, front missing)
    assert result.well_formed is True
    assert result.valid is False
    assert result.errors


def test_jats_rejects_malformed_xml():
    result = validate_jats("<article><unclosed>")
    assert result.well_formed is False
    assert result.valid is False


def test_pdf_auto_falls_back_to_minimal(session, project, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    ms = authoring.create_manuscript(session, project.id, title="PDF")
    authoring.add_section(session, ms.id, heading="Intro", text="hello world")

    # On this box WeasyPrint/GTK is absent → auto must fall back, and say so.
    assert export_service.weasyprint_available() is False
    result = export_service.export_manuscript(session, ms.id, formats=["pdf", "jats"])
    assert result["pdf_renderer"] == "minimal"
    assert result["jats_validation"]["valid"] is True
    pdf = Path(result["files"]["pdf"]).read_bytes()
    assert pdf.startswith(b"%PDF-1.4")


def test_pdf_weasyprint_mode_errors_when_unavailable(session, project, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WB_PDF_RENDERER", "weasyprint")
    from workbench import config

    config.get_settings.cache_clear()
    ms = authoring.create_manuscript(session, project.id, title="PDF2")
    authoring.add_section(session, ms.id, heading="Intro", text="x")
    if not export_service.weasyprint_available():
        with pytest.raises(research.IntegrityError, match="WeasyPrint/GTK is unavailable"):
            export_service.export_manuscript(session, ms.id, formats=["pdf"])
    config.get_settings.cache_clear()


def test_manifest_records_renderer_and_validation(session, project, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    src = research.register_source(
        session, project.id, title="Prior", access=SourceAccess.EXCERPT_AVAILABLE,
        authors="A. B.", year=2001, doi="10.1/y",
    )
    excerpt = research.capture_excerpt(session, src.id, text="q", locator="p.1")
    claim = research.create_claim(
        session, project.id, text="c", support=ClaimSupport.EXTERNAL_SOURCE,
        excerpt_ids=[excerpt.id],
    )
    ms = authoring.create_manuscript(session, project.id, title="M")
    authoring.add_section(session, ms.id, heading="Results", text="t", claim_ids=[claim.id])
    result = export_service.export_manuscript(session, ms.id, formats=["pdf", "jats"])
    import json

    manifest = json.loads(Path(result["files"]["manifest"]).read_text(encoding="utf-8"))
    assert manifest["pdf_renderer"] in ("minimal", "weasyprint")
    assert manifest["jats_validation"]["method"] in ("dtd-subset", "well-formed-only")
