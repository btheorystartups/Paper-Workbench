"""Layout-aware PDF extraction and optional OCR remain explicit and review-gated."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from workbench.ingest import files
from workbench.ingest.files import (
    ExtractionConfidence,
    IngestError,
    OcrPageResult,
    PdfOcrStatus,
    PdfPageState,
    extract_text,
    ingest_file,
)
from workbench.services.export_service import _minimal_pdf


class FakeOcr:
    name = "fake-local-ocr"

    def __init__(self):
        self.pages: list[int] = []

    def extract_page(self, path: Path, page_number: int) -> OcrPageResult:
        assert path.is_file()
        self.pages.append(page_number)
        return OcrPageResult(
            text=f"OCR text for page {page_number}",
            engine=self.name,
            detail={"fixture": True},
        )


def _blank_pdf(path: Path, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        content = DecodedStreamObject()
        content.set_data(b"q Q")
        page[NameObject("/Contents")] = writer._add_object(content)
    with path.open("wb") as handle:
        writer.write(handle)


def _mixed_pdf(path: Path) -> None:
    born_digital = _minimal_pdf(
        "Born digital page",
        ["This page contains enough selectable text to exceed the transparent OCR threshold."],
    )
    reader = PdfReader(BytesIO(born_digital))
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    page = writer.add_blank_page(width=612, height=792)
    content = DecodedStreamObject()
    content.set_data(b"q Q")
    page[NameObject("/Contents")] = writer._add_object(content)
    with path.open("wb") as handle:
        writer.write(handle)


def test_auto_ocr_only_processes_low_text_pages(tmp_path):
    pdf = tmp_path / "mixed.pdf"
    _mixed_pdf(pdf)
    ocr = FakeOcr()

    result = extract_text(pdf, pdf_mode="auto", ocr_engine=ocr)

    assert ocr.pages == [2]
    assert result.confidence == ExtractionConfidence.MIXED_UNREVIEWED
    assert result.detail["ocr_status"] == PdfOcrStatus.APPLIED
    assert result.detail["review_required"] is True
    assert [page["state"] for page in result.detail["page_results"]] == [
        PdfPageState.LAYOUT_TEXT,
        PdfPageState.OCR_UNREVIEWED,
    ]
    assert "[page 1 | layout_text]" in result.text
    assert "[page 2 | ocr_unreviewed]\nOCR text for page 2" in result.text


def test_text_mode_records_unresolved_page_without_calling_ocr(tmp_path):
    pdf = tmp_path / "blank.pdf"
    _blank_pdf(pdf)
    ocr = FakeOcr()

    result = extract_text(pdf, pdf_mode="text", ocr_engine=ocr)

    assert ocr.pages == []
    assert result.confidence == ExtractionConfidence.LOSSY
    assert result.detail["ocr_status"] == PdfOcrStatus.NOT_REQUESTED
    assert result.detail["page_results"][0]["state"] == PdfPageState.LOW_TEXT_UNRESOLVED


def test_auto_mode_succeeds_honestly_when_local_ocr_is_unavailable(tmp_path, monkeypatch):
    pdf = tmp_path / "blank.pdf"
    _blank_pdf(pdf)
    monkeypatch.setattr(files, "default_ocr_engine", lambda: None)

    result = extract_text(pdf, pdf_mode="auto")

    assert result.detail["ocr_status"] == PdfOcrStatus.UNAVAILABLE
    assert result.detail["page_results"][0]["state"] == PdfPageState.LOW_TEXT_UNRESOLVED
    assert "OCR candidate but local OCR is unavailable" in result.detail["warnings"][0]


def test_forced_ocr_fails_closed_when_capability_is_unavailable(tmp_path, monkeypatch):
    pdf = tmp_path / "blank.pdf"
    _blank_pdf(pdf)
    monkeypatch.setattr(files, "default_ocr_engine", lambda: None)

    with pytest.raises(IngestError, match="requires the optional local OCR capability"):
        extract_text(pdf, pdf_mode="ocr")


def test_ingest_persists_page_level_ocr_provenance(
    session, project, tmp_path, monkeypatch
):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    pdf = tmp_path / "scan.pdf"
    _blank_pdf(pdf, pages=2)

    source = ingest_file(
        session,
        project.id,
        pdf,
        pdf_mode="ocr",
        ocr_engine=FakeOcr(),
    )
    metadata = source.provider_metadata["ingest"]

    assert metadata["extraction_confidence"] == ExtractionConfidence.OCR_UNREVIEWED
    assert metadata["extraction_detail"]["ocr_status"] == PdfOcrStatus.APPLIED
    assert len(metadata["extraction_detail"]["page_results"]) == 2
    assert metadata["human_reviewed"] is False
    assert files.extracted_text_for(source).startswith(
        "[page 1 | ocr_unreviewed]\nOCR text for page 1"
    )


def test_ingest_api_exposes_controlled_pdf_mode(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    _blank_pdf(pdf)
    monkeypatch.setenv("WB_DATABASE_URL", f"sqlite:///{tmp_path / 'pdf-api.sqlite3'}")
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WB_PROVIDER_MODE", "fake")
    from workbench import config, db
    from workbench.main import app

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    with TestClient(app) as client:
        workspace = client.post("/workspaces", json={"name": "WS"}).json()
        project = client.post(
            "/projects", json={"workspace_id": workspace["id"], "name": "P"}
        ).json()
        invalid = client.post(
            f"/projects/{project['id']}/ingest",
            json={"path": str(pdf), "pdf_mode": "guess"},
        )
        assert invalid.status_code == 422
        response = client.post(
            f"/projects/{project['id']}/ingest",
            json={"path": str(pdf), "pdf_mode": "text"},
        )
        assert response.status_code == 200
        detail = response.json()["ingest"]["extraction_detail"]
        assert detail["requested_mode"] == "text"
        assert detail["ocr_status"] == PdfOcrStatus.NOT_REQUESTED
        sources = client.get(f"/projects/{project['id']}/sources").json()
        assert sources[0]["ingest"]["extraction_detail"]["page_results"][0]["state"] == (
            PdfPageState.LOW_TEXT_UNRESOLVED
        )
    db.reset_engine_for_tests()
    config.get_settings.cache_clear()
