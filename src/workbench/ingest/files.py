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
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from .. import storage
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
    PLAIN = "plain"
    OCR = "ocr"


class PdfPageState(StrEnum):
    LAYOUT_TEXT = "layout_text"
    PLAIN_TEXT = "plain_text"
    DAMAGED_TEXT_UNRESOLVED = "damaged_text_unresolved"
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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _alnum_count(text: str) -> int:
    return sum(character.isalnum() for character in text)


def _pdf_text_issues(text: str) -> list[str]:
    """Detect evidence of broken font maps, never infer a replacement math symbol.

    An empty result does not certify equations: flattened exponents and missing
    symbols can look like ordinary text. Every PDF still requires visual review.
    """
    issues = []
    if any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in text):
        issues.append("control_glyphs")
    if any(unicodedata.category(c) == "Co" for c in text):
        issues.append("private_use_glyphs")
    if "\ufffd" in text:
        issues.append("replacement_glyphs")
    return issues


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
    if mode in {PdfExtractionMode.AUTO, PdfExtractionMode.OCR} and engine is None:
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
    cursor = 0

    for page_number, page in enumerate(reader.pages, start=1):
        layout_text = ""
        layout_error = ""
        plain_text = ""
        plain_error = ""
        try:
            plain_text = page.extract_text() or ""
        except Exception as exc:
            plain_error = f"{type(exc).__name__}: {exc}"
        if mode != PdfExtractionMode.PLAIN:
            try:
                layout_text = page.extract_text(extraction_mode="layout") or ""
            except Exception as exc:
                layout_error = f"{type(exc).__name__}: {exc}"

        # Large whitespace expansion can consume the document cap in a few pages.
        # Select a whole extraction; never splice guessed symbols between engines.
        inflated = len(layout_text) > max(2 * len(plain_text), len(plain_text) + 4000)
        use_plain = mode == PdfExtractionMode.PLAIN or bool(
            plain_text.strip() and (not layout_text.strip() or layout_error or inflated)
        )
        selected_text = plain_text if use_plain else layout_text
        selected_error = plain_error if use_plain else layout_error
        fallback_reason = (
            "layout_whitespace_expansion" if inflated and use_plain else
            "layout_unavailable" if use_plain and mode != PdfExtractionMode.PLAIN else None
        )

        alnum_chars = _alnum_count(selected_text)
        low_text = alnum_chars < PDF_OCR_MIN_ALNUM_CHARS
        text_issues = _pdf_text_issues(selected_text)
        should_ocr = mode == PdfExtractionMode.OCR or (
            mode == PdfExtractionMode.AUTO and (low_text or bool(text_issues))
        )
        if should_ocr:
            ocr_candidates += 1

        final_text = selected_text
        state = (
            (PdfPageState.PLAIN_TEXT if use_plain else PdfPageState.LAYOUT_TEXT)
            if not low_text
            else PdfPageState.LOW_TEXT_UNRESOLVED
        )
        if text_issues:
            state = PdfPageState.DAMAGED_TEXT_UNRESOLVED
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
        elif selected_error:
            state = PdfPageState.EXTRACTION_FAILED

        if layout_error:
            warnings.append(f"page {page_number}: layout extraction failed ({layout_error})")
        if plain_error:
            warnings.append(f"page {page_number}: plain extraction failed ({plain_error})")
        if fallback_reason:
            warnings.append(f"page {page_number}: plain text selected ({fallback_reason})")
        if should_ocr and engine is None:
            warnings.append(f"page {page_number}: OCR candidate but local OCR is unavailable")
        if ocr_error:
            warnings.append(f"page {page_number}: OCR failed ({ocr_error})")
        output_issues = _pdf_text_issues(final_text)
        if _alnum_count(final_text) < PDF_OCR_MIN_ALNUM_CHARS:
            output_issues.append("low_text")
        if output_issues:
            warnings.append(f"page {page_number}: unresolved text quality ({', '.join(output_issues)})")

        state_value = str(state)
        marker = f"[page {page_number} | {state_value}]\n"
        start = cursor + (2 if rendered_pages else 0)
        rendered_pages.append(marker + final_text)
        cursor = start + len(marker) + len(final_text)
        page_results.append(
            {
                "page": page_number,
                "state": state_value,
                "layout_alnum_chars": _alnum_count(layout_text),
                "selected_extractor": "ocr" if state == PdfPageState.OCR_UNREVIEWED else (
                    "plain" if use_plain else "layout"
                ),
                "fallback_reason": fallback_reason,
                "text_layer_issues": text_issues,
                "quality_issues": output_issues,
                "review_required": True,
                "start": start,
                "body_start": start + len(marker),
                "end": cursor,
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
    for result in page_results:
        result["retained_chars"] = max(0, min(result["end"], MAX_EXTRACT_CHARS) - result["start"])
        result["truncated"] = result["end"] > MAX_EXTRACT_CHARS
    if mode in {PdfExtractionMode.TEXT, PdfExtractionMode.PLAIN}:
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
        extractor=f"pypdf-page-aware-{pypdf.__version__}",
        confidence=confidence,
        detail={
            "pages": len(reader.pages),
            "format": "pdf",
            "offset_unit": "unicode_characters",
            "retained_pages": sum(p["retained_chars"] > 0 for p in page_results),
            "evidence_use": "discovery_only; verify formulas against original PDF",
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
    original_name: str | None = None,
    acquisition: str | None = None,
) -> Source:
    """Copy the file into the artifact store, extract text, register a Source with full
    provenance. Returns the Source; extracted text is stored beside the original."""
    path = Path(file_path)
    if not path.is_file():
        raise IngestError(f"file not found: {path}")

    display_name = original_name or path.name
    checksum = _sha256_file(path)
    extraction = extract_text(path, pdf_mode=pdf_mode, ocr_engine=ocr_engine)
    try:
        original_ref = storage.store_content(
            path.read_bytes(),
            filename=display_name,
            namespace="ingest/originals",
        )
        extracted_ref = storage.store_content(
            extraction.text.encode("utf-8"),
            filename="extracted.txt",
            namespace="ingest/extracted",
            content_type="text/plain; charset=utf-8",
        )
    except storage.ArtifactStorageError as exc:
        raise IngestError(str(exc)) from exc

    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    ingest_metadata = {
        "original_path": str(path) if original_name is None else display_name,
        "artifact": original_ref,
        "extracted_artifact": extracted_ref,
        "checksum_sha256": checksum,
        "size_bytes": path.stat().st_size,
        "extractor": extraction.extractor,
        "extraction_confidence": str(extraction.confidence),
        "extraction_detail": extraction.detail,
        "human_reviewed": False,
    }
    original_local = storage.local_path(original_ref)
    extracted_local = storage.local_path(extracted_ref)
    if original_local:
        ingest_metadata["artifact_path"] = original_local
    if extracted_local:
        ingest_metadata["extracted_path"] = extracted_local
    source = research.register_source(
        session,
        project_id,
        title=title or display_name,
        access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
        acquisition=acquisition or f"user file ingested from {path} (mtime {mtime})",
        license=license,
        url=None,
        provider_metadata={
            "ingest": ingest_metadata
        },
    )
    return source


def extracted_text_for(source: Source) -> str | None:
    meta = (source.provider_metadata or {}).get("ingest", {})
    reference = meta.get("extracted_artifact")
    if isinstance(reference, dict):
        try:
            return storage.read_bytes(reference).decode("utf-8")
        except (storage.ArtifactStorageError, UnicodeDecodeError):
            return None
    path = meta.get("extracted_path")
    if path:
        try:
            return storage.read_legacy_location(path).decode("utf-8")
        except (storage.ArtifactStorageError, UnicodeDecodeError):
            return None
    return None
