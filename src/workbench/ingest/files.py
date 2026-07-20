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
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Source
from ..services import research
from ..vocab import SourceAccess

TEXT_SUFFIXES = {".md", ".txt", ".tex", ".bib", ".py", ".json", ".html", ".yaml", ".yml"}
MAX_EXTRACT_CHARS = 2_000_000


@dataclass
class ExtractionResult:
    text: str
    extractor: str
    confidence: str  # "exact" (lossless read) | "parsed" (structured) | "lossy" (pdf/ocr)
    detail: dict = field(default_factory=dict)


class IngestError(ValueError):
    pass


def _artifact_root() -> Path:
    return Path(get_settings().data_dir) / "artifacts"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path: Path) -> ExtractionResult:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
        return ExtractionResult(text=text[:MAX_EXTRACT_CHARS], extractor="raw-read", confidence="exact")
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
            text=text, extractor="csv-summary", confidence="parsed",
            detail={"rows": max(len(rows) - 1, 0), "columns": header},
        )
    if suffix == ".pdf":
        try:
            import pypdf
        except ImportError as exc:
            raise IngestError("pypdf not installed; cannot extract PDF text") from exc
        reader = pypdf.PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append(f"[extraction failed for page {i + 1}]")
        text = "\n\n".join(
            f"[page {i + 1}]\n{t}" for i, t in enumerate(pages)
        )[:MAX_EXTRACT_CHARS]
        return ExtractionResult(
            text=text, extractor=f"pypdf-{pypdf.__version__}", confidence="lossy",
            detail={"pages": len(reader.pages)},
        )
    raise IngestError(f"unsupported file type '{suffix}' (supported: text, csv, pdf)")


def ingest_file(
    session: Session,
    project_id: str,
    file_path: str | Path,
    *,
    title: str | None = None,
    license: str = "author-owned",
) -> Source:
    """Copy the file into the artifact store, extract text, register a Source with full
    provenance. Returns the Source; extracted text is stored beside the original."""
    path = Path(file_path)
    if not path.is_file():
        raise IngestError(f"file not found: {path}")

    checksum = _sha256_file(path)
    extraction = extract_text(path)

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
                "extraction_confidence": extraction.confidence,
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
