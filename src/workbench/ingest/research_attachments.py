"""Bounded ZIP inspection; member names are metadata, never extraction paths."""

import hashlib
import io
import re
import stat
import unicodedata
import zipfile
from pathlib import PurePosixPath

from .files import TEXT_SUFFIXES, IngestError

MAX_MEMBERS = 200
MAX_MEMBER_BYTES = 8_000_000
MAX_EXPANDED_BYTES = 40_000_000
MAX_RATIO = 100
ACCEPTED = TEXT_SUFFIXES | {".pdf", ".csv"}


def safe_name(name: str) -> str:
    if not name or len(name) > 300 or "\\" in name or any(ord(c) < 32 for c in name):
        raise IngestError("unsafe attachment path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in name.rstrip("/").split("/")):
        raise IngestError("unsafe attachment path")
    for part in path.parts:
        if (
            ":" in part
            or part.endswith((".", " "))
            or re.match(
                r"^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)",
                part,
                re.I,
            )
        ):
            raise IngestError("unsafe attachment path")
    return name


def inspect_attachment(filename: str, payload: bytes) -> tuple[list[dict], list[tuple[str, bytes]]]:
    """Validate the complete archive before reading any member; check CRCs and actual sizes.

    Non-document members are inventoried and hashed but not ingested or executed.
    Nested archives are not recursively expanded. Original ZIP bytes are retained by caller.
    """
    safe_name(filename)
    if PurePosixPath(filename).suffix.lower() != ".zip":
        if PurePosixPath(filename).suffix.lower() not in ACCEPTED:
            raise IngestError("unsupported attachment type")
        if len(payload) > MAX_MEMBER_BYTES:
            raise IngestError("attachment exceeds member size limit")
        return [], [(filename, payload)]
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_MEMBERS:
                raise IngestError("ZIP member count exceeds limit or ZIP is empty")
            seen, expanded = set(), 0
            for entry in entries:
                safe_name(entry.orig_filename)  # ZipInfo normalizes/truncates some names on Windows.
                safe_name(entry.filename)
                key = unicodedata.normalize("NFC", entry.filename).rstrip("/").casefold()
                if key in seen:
                    raise IngestError("ZIP has duplicate or colliding paths")
                seen.add(key)
                mode = entry.external_attr >> 16
                if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise IngestError("ZIP links and special files are prohibited")
                if entry.flag_bits & 1 or entry.compress_type not in {
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                }:
                    raise IngestError("encrypted or unsupported ZIP compression")
                expanded += entry.file_size
                if (
                    entry.file_size > MAX_MEMBER_BYTES
                    or expanded > MAX_EXPANDED_BYTES
                    or entry.file_size > MAX_RATIO * max(1, entry.compress_size)
                ):
                    raise IngestError("ZIP expansion exceeds safety limits")
            inventory, documents = [], []
            for entry in entries:
                if entry.is_dir():
                    continue
                with archive.open(entry) as stream:
                    data = stream.read(MAX_MEMBER_BYTES + 1)
                if len(data) != entry.file_size or len(data) > MAX_MEMBER_BYTES:
                    raise IngestError("ZIP member expanded size mismatch")
                accepted = PurePosixPath(entry.filename).suffix.lower() in ACCEPTED
                inventory.append(
                    {
                        "name": entry.filename,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "disposition": "document" if accepted else "retained_in_archive_only",
                    }
                )
                if accepted:
                    documents.append((entry.filename, data))
            if not documents:
                raise IngestError("ZIP contains no accepted documents")
            return inventory, documents
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, OSError) as exc:
        raise IngestError("invalid or unsupported ZIP") from exc
