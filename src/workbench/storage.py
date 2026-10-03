"""Content-addressed local or private-Vercel-Blob artifact storage.

Descriptors contain keys and checksums, never credentials. Private Blob access always goes
through the server-side SDK; raw Blob URLs are provenance metadata, not browser download URLs.
"""

import hashlib
import mimetypes
import os
import re
import secrets
from pathlib import Path, PurePosixPath
from typing import Any

from .config import get_settings


class ArtifactStorageError(RuntimeError):
    pass


def _backend() -> str:
    backend = get_settings().artifact_storage_backend.strip().lower()
    if backend not in {"local", "vercel_blob"}:
        raise ArtifactStorageError(
            "WB_ARTIFACT_STORAGE_BACKEND must be local or vercel_blob"
        )
    return backend


def _safe_key(key: str) -> str:
    raw = key.replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ArtifactStorageError("artifact storage key must be a safe relative path")
    normalized = raw.strip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ArtifactStorageError("artifact storage key must be a safe relative path")
    return path.as_posix()


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name[:180] or "artifact.bin"


def content_key(payload: bytes, *, filename: str, namespace: str = "artifacts") -> str:
    digest = hashlib.sha256(payload).hexdigest()
    return _safe_key(
        f"artifacts/{_safe_key(namespace)}/{digest[:2]}/{digest}/{_safe_filename(filename)}"
    )


def _local_path(key: str) -> Path:
    root = Path(get_settings().data_dir).resolve()
    path = (root / Path(_safe_key(key))).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ArtifactStorageError("artifact path escaped the configured data directory") from exc
    return path


def _field(value: Any, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _new_blob_client():
    try:
        from vercel.blob import BlobClient
    except ImportError as exc:
        raise ArtifactStorageError(
            "private Vercel Blob storage requires the 'vercel>=0.5.0' Python package"
        ) from exc
    return BlobClient()


def _descriptor(
    *,
    backend: str,
    key: str,
    digest: str,
    size: int,
    content_type: str,
    local_path: str | None = None,
    url: str | None = None,
    etag: str | None = None,
) -> dict:
    result = {
        "storage_backend": backend,
        "storage_key": key,
        "sha256": digest,
        "size_bytes": size,
        "content_type": content_type,
    }
    if local_path:
        result["local_path"] = local_path
    if url:
        result["private_url"] = url
    if etag:
        result["etag"] = etag
    return result


def put_bytes(
    key: str,
    payload: bytes,
    *,
    content_type: str | None = None,
) -> dict:
    key = _safe_key(key)
    digest = hashlib.sha256(payload).hexdigest()
    media_type = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
    backend = _backend()
    if backend == "local":
        path = _local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ArtifactStorageError("content-addressed artifact collision")
        else:
            temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
            try:
                temporary.write_bytes(payload)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return _descriptor(
            backend=backend,
            key=key,
            digest=digest,
            size=len(payload),
            content_type=media_type,
            local_path=str(path),
        )

    client = _new_blob_client()
    try:
        uploaded = client.put(
            key,
            payload,
            access="private",
            add_random_suffix=False,
            overwrite=False,
            content_type=media_type,
        )
    except Exception as exc:
        # Repeated content-addressed writes are idempotent. Confirm the existing bytes before
        # accepting a failed create; authentication/network errors therefore still fail closed.
        candidate = _descriptor(
            backend=backend,
            key=key,
            digest=digest,
            size=len(payload),
            content_type=media_type,
        )
        try:
            if hashlib.sha256(read_bytes(candidate)).hexdigest() == digest:
                return candidate
        except ArtifactStorageError:
            pass
        raise ArtifactStorageError("private Blob upload failed") from exc
    return _descriptor(
        backend=backend,
        key=key,
        digest=digest,
        size=len(payload),
        content_type=media_type,
        url=_field(uploaded, "url"),
        etag=_field(uploaded, "etag"),
    )


def store_content(
    payload: bytes,
    *,
    filename: str,
    namespace: str = "content",
    content_type: str | None = None,
) -> dict:
    return put_bytes(
        content_key(payload, filename=filename, namespace=namespace),
        payload,
        content_type=content_type,
    )


def read_bytes(reference: dict) -> bytes:
    key = _safe_key(str(reference.get("storage_key") or ""))
    expected = str(reference.get("sha256") or "")
    declared_size = int(reference.get("size_bytes") or 0)
    maximum = get_settings().artifact_max_read_bytes
    if maximum < 1 or (declared_size and declared_size > maximum):
        raise ArtifactStorageError("artifact exceeds the configured read limit")

    backend = str(reference.get("storage_backend") or _backend()).strip().lower()
    if backend == "local":
        path_text = reference.get("local_path")
        candidate = Path(path_text) if path_text else None
        path = candidate if candidate is not None and candidate.is_absolute() else _local_path(key)
        if not path.is_file():
            raise ArtifactStorageError("artifact not found")
        if path.stat().st_size > maximum:
            raise ArtifactStorageError("artifact exceeds the configured read limit")
        payload = path.read_bytes()
    elif backend == "vercel_blob":
        try:
            client = _new_blob_client()
            # Current Python SDKs buffer get().content. Refuse known oversized objects
            # before downloading, then check the actual bytes as well. Older streaming
            # result shapes remain supported for compatible clients.
            metadata = client.head(key)
            if int(_field(metadata, "size", 0) or 0) > maximum:
                raise ArtifactStorageError("artifact exceeds the configured read limit")
            result = client.get(key, access="private")
            if result is None or _field(result, "status_code") != 200:
                raise ArtifactStorageError("artifact not found")
            content = _field(result, "content")
            if isinstance(content, bytes):
                payload = content
            else:
                stream = _field(result, "stream")
                if stream is None:
                    raise ArtifactStorageError("private Blob response had no content stream")
                chunks: list[bytes] = []
                size = 0
                for chunk in stream:
                    size += len(chunk)
                    if size > maximum:
                        raise ArtifactStorageError("artifact exceeds the configured read limit")
                    chunks.append(chunk)
                payload = b"".join(chunks)
        except ArtifactStorageError:
            raise
        except Exception as exc:
            raise ArtifactStorageError("private Blob read failed") from exc
    else:
        raise ArtifactStorageError("artifact descriptor has an unsupported storage backend")

    if len(payload) > maximum:
        raise ArtifactStorageError("artifact exceeds the configured read limit")
    if expected and hashlib.sha256(payload).hexdigest() != expected:
        raise ArtifactStorageError("artifact checksum mismatch")
    return payload


def local_path(reference: dict) -> str | None:
    if reference.get("storage_backend") != "local":
        return None
    return str(reference.get("local_path") or _local_path(str(reference["storage_key"])))


def read_legacy_location(value: str) -> bytes:
    """Read a pre-descriptor local path or an import-generated artifact:// location."""
    if value.startswith("artifact://"):
        return read_bytes(
            {
                "storage_backend": _backend(),
                "storage_key": value.removeprefix("artifact://"),
            }
        )
    path = Path(value)
    if not path.is_file():
        raise ArtifactStorageError("artifact not found")
    return path.read_bytes()
