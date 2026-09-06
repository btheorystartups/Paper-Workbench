"""File ingestion (P2): heterogeneous research materials → Source records with full
provenance, originals preserved byte-for-byte.

Rules (Phase 0 canonical model):
- The original file is COPIED into the artifact store under its content hash; ingestion
  never mutates or moves user files.
- Extraction is best-effort and honestly labeled: extractor name/version and a
  confidence tag land in provider_metadata; extracted text is never presented as verified.
- Ingested files are user-supplied → SourceAccess.FULL_TEXT_USER_SUPPLIED with an
  acquisition note recording the original path and mtime.
"""

import csv
import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Source
from ..services import research
from ..vocab import SourceAccess

TEXT_SUFFIXES = {".md", ".txt", ".tex", ".bib", ".py", ".json", ".html", ".yaml", ".yml"}
MAX_EXTRACT_CHARS = 2_000_000
PDF_OCR_MIN_ALNUM_CHARS = 40


class ExtractionConfidence(StrEnum):
    EXACT = "exact"
    PARSED = "parsed"
    LOSSY = "lossy"
    OCR_UNREVIEWED = "ocr_unreviewed"
    MIXED_UNREVIEWED = "mixed_unreviewed"


class PdfExtractionMode(StrEnum):
    AUTO = "auto"
    TEXT = "text"
    OCR = "ocr"


class PdfPageState(StrEnum):
    LAYOUT_TEXT = "layout_text"
    OCR_UNREVIEWED = "ocr_unreviewed"
    LOW_TEXT_UNRESOLVED = "low_text_unresolved"
    EXTRACTION_FAILED = "extraction_failed"


class PdfOcrStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    NOT_NEEDED = "not_needed"
    APPLIED = "applied"
    UNAVAILABLE = "unavailable"
    PARTIAL_FAILURE = "partial_failure"


@dataclass
class ExtractionResult:
    text: str
    extractor: str
    confidence: ExtractionConfidence
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OcrPageResult:
    text: str
    engine: str
    detail: dict = field(default_factory=dict)


class OcrEngine(Protocol):
    name: str

    def extract_page(self, path: Path, page_number: int) -> OcrPageResult: ...


class PyMuPdfTesseractOcr:
    """Optional local OCR engine. PyMuPDF and local Tesseract data are never auto-installed."""

    name = "pymupdf-tesseract"

    def __init__(self, pymupdf_module, *, language: str = "eng", dpi: int = 300):
        self._pymupdf = pymupdf_module
        self.language = language
        self.dpi = dpi

    def extract_page(self, path: Path, page_number: int) -> OcrPageResult:
        with self._pymupdf.open(path) as document:
            page = document.load_page(page_number - 1)
            text_page = page.get_textpage_ocr(
                language=self.language,
                dpi=self.dpi,
                full=True,
            )
            text = page.get_text("text", textpage=text_page, sort=True)
        return OcrPageResult(
            text=text,
            engine=self.name,
            detail={"language": self.language, "dpi": self.dpi},
        )


class IngestError(ValueError):
    pass


def default_ocr_engine() -> OcrEngine | None:
    """Return the optional local OCR adapter when PyMuPDF is installed.

    Tesseract availability is confirmed only when a page is processed; failures are
    explicit page-level provenance in auto mode and fatal in forced OCR mode.
    """
    try:
        import pymupdf
    except ImportError:
        return None
    return PyMuPdfTesseractOcr(pymupdf)


def _artifact_root() -> Path:
    return Path(get_settings().data_dir) / "artifacts"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _alnum_count(text: str) -> int:
    return sum(character.isalnum() for character in text)


def _extract_pdf(
    path: Path,
    *,
    mode: PdfExtractionMode,
    ocr_engine: OcrEngine | None,
) -> ExtractionResult:
    try:
        import pypdf
    except ImportError as exc:
        raise IngestError("pypdf not installed; cannot extract PDF text") from exc

    reader = pypdf.PdfReader(str(path))
    engine = ocr_engine
    if mode != PdfExtractionMode.TEXT and engine is None:
        engine = default_ocr_engine()
    if mode == PdfExtractionMode.OCR and engine is None:
        raise IngestError(
            "pdf_mode=ocr requires the optional local OCR capability "
            "(install paper-workbench[ocr] and local Tesseract language data)"
        )

    rendered_pages: list[str] = []
    page_results: list[dict] = []
    warnings: list[str] = []
    ocr_applied = 0
    ocr_failures = 0
    ocr_candidates = 0

    for page_number, page in enumerate(reader.pages, start=1):
        layout_text = ""
        layout_error = ""
        try:
            layout_text = page.extract_text(extraction_mode="layout") or ""
        except Exception as exc:
            layout_error = f"{type(exc).__name__}: {exc}"

        alnum_chars = _alnum_count(layout_text)
        low_text = alnum_chars < PDF_OCR_MIN_ALNUM_CHARS
        should_ocr = mode == PdfExtractionMode.OCR or (
            mode == PdfExtractionMode.AUTO and low_text
        )
        if should_ocr:
            ocr_candidates += 1

        final_text = layout_text
        state = (
            PdfPageState.LAYOUT_TEXT
            if not low_text
            else PdfPageState.LOW_TEXT_UNRESOLVED
        )
        ocr_detail: dict = {}
        page_ocr_engine: str | None = None
        ocr_error = ""
        if should_ocr and engine is not None:
            try:
                ocr_result = engine.extract_page(path, page_number)
                final_text = ocr_result.text
                ocr_detail = ocr_result.detail
                page_ocr_engine = ocr_result.engine
                state = PdfPageState.OCR_UNREVIEWED
                ocr_applied += 1
            except Exception as exc:
                ocr_failures += 1
                ocr_error = f"{type(exc).__name__}: {exc}"
                if mode == PdfExtractionMode.OCR:
                    raise IngestError(
                        f"OCR failed for PDF page {page_number}: {ocr_error}"
                    ) from exc
        elif layout_error:
            state = PdfPageState.EXTRACTION_FAILED

        if layout_error:
            warnings.append(f"page {page_number}: layout extraction failed ({layout_error})")
        if should_ocr and engine is None:
            warnings.append(f"page {page_number}: OCR candidate but local OCR is unavailable")
        if ocr_error:
            warnings.append(f"page {page_number}: OCR failed ({ocr_error})")

        state_value = str(state)
        rendered_pages.append(f"[page {page_number} | {state_value}]\n{final_text}")
        page_results.append(
            {
                "page": page_number,
                "state": state_value,
                "layout_alnum_chars": alnum_chars,
                "output_chars": len(final_text),
                "ocr_attempted": should_ocr and engine is not None,
                "ocr_engine": page_ocr_engine or (
                    engine.name if should_ocr and engine is not None else None
                ),
                "ocr_detail": ocr_detail,
                "warning": ocr_error or layout_error or None,
            }
        )

    full_text = "\n\n".join(rendered_pages)
    truncated = len(full_text) > MAX_EXTRACT_CHARS
    if mode == PdfExtractionMode.TEXT:
        ocr_status = PdfOcrStatus.NOT_REQUESTED
    elif not ocr_candidates:
        ocr_status = PdfOcrStatus.NOT_NEEDED
    elif engine is None:
        ocr_status = PdfOcrStatus.UNAVAILABLE
    elif ocr_failures:
        ocr_status = PdfOcrStatus.PARTIAL_FAILURE
    else:
        ocr_status = PdfOcrStatus.APPLIED

    if ocr_applied == len(reader.pages) and ocr_applied:
        confidence = ExtractionConfidence.OCR_UNREVIEWED
    elif ocr_applied:
        confidence = ExtractionConfidence.MIXED_UNREVIEWED
    else:
        confidence = ExtractionConfidence.LOSSY

    return ExtractionResult(
        text=full_text[:MAX_EXTRACT_CHARS],
        extractor=f"pypdf-layout-{pypdf.__version__}",
        confidence=confidence,
        detail={
            "pages": len(reader.pages),
            "requested_mode": str(mode),
            "layout_extractor": f"pypdf-{pypdf.__version__}",
            "ocr_status": str(ocr_status),
            "ocr_engine": engine.name if engine is not None else None,
            "ocr_threshold_alnum_chars": PDF_OCR_MIN_ALNUM_CHARS,
            "review_required": True,
            "truncated": truncated,
            "warnings": warnings,
            "page_results": page_results,
        },
    )


def extract_text(
    path: Path,
    *,
    pdf_mode: PdfExtractionMode | str = PdfExtractionMode.AUTO,
    ocr_engine: OcrEngine | None = None,
) -> ExtractionResult:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
        return ExtractionResult(
            text=text[:MAX_EXTRACT_CHARS],
            extractor="raw-read",
            confidence=ExtractionConfidence.EXACT,
        )
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            rows = list(reader)
        header = rows[0] if rows else []
        preview = "\n".join(", ".join(r) for r in rows[:20])
        text = (
            f"CSV file: {path.name}\ncolumns: {', '.join(header)}\n"
            f"rows (excl. header): {max(len(rows) - 1, 0)}\n\nFirst rows:\n{preview}"
        )
        return ExtractionResult(
            text=text,
            extractor="csv-summary",
            confidence=ExtractionConfidence.PARSED,
            detail={"rows": max(len(rows) - 1, 0), "columns": header},
        )
    if suffix == ".pdf":
        try:
            mode = PdfExtractionMode(pdf_mode)
        except ValueError as exc:
            raise IngestError(
                f"invalid PDF extraction mode '{pdf_mode}' "
                f"(expected: {', '.join(PdfExtractionMode)})"
            ) from exc
        return _extract_pdf(path, mode=mode, ocr_engine=ocr_engine)
    raise IngestError(f"unsupported file type '{suffix}' (supported: text, csv, pdf)")


def ingest_file(
    session: Session,
    project_id: str,
    file_path: str | Path,
    *,
    title: str | None = None,
    license: str = "author-owned",
    pdf_mode: PdfExtractionMode | str = PdfExtractionMode.AUTO,
    ocr_engine: OcrEngine | None = None,
) -> Source:
    """Copy the file into the artifact store, extract text, register a Source with full
    provenance. Returns the Source; extracted text is stored beside the original."""
    path = Path(file_path)
    if not path.is_file():
        raise IngestError(f"file not found: {path}")

    checksum = _sha256_file(path)
    extraction = extract_text(path, pdf_mode=pdf_mode, ocr_engine=ocr_engine)

    artifact_dir = _artifact_root() / checksum[:2] / checksum
    artifact_dir.mkdir(parents=True, exist_ok=True)
    original_copy = artifact_dir / path.name
    if not original_copy.exists():
        shutil.copy2(path, original_copy)
    extracted_path = artifact_dir / "extracted.txt"
    extracted_path.write_text(extraction.text, encoding="utf-8")

    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    source = research.register_source(
        session,
        project_id,
        title=title or path.name,
        access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
        acquisition=f"user file ingested from {path} (mtime {mtime})",
        license=license,
        url=None,
        provider_metadata={
            "ingest": {
                "original_path": str(path),
                "artifact_path": str(original_copy),
                "extracted_path": str(extracted_path),
                "checksum_sha256": checksum,
                "size_bytes": path.stat().st_size,
                "extractor": extraction.extractor,
                "extraction_confidence": str(extraction.confidence),
                "extraction_detail": extraction.detail,
                "human_reviewed": False,
            }
        },
    )
    return source


def extracted_text_for(source: Source) -> str | None:
    meta = (source.provider_metadata or {}).get("ingest", {})
    path = meta.get("extracted_path")
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8")
    return None
