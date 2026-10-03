"""Explicit synthetic Preview-only resource check; never loads dotenv or creates users.

Run through `vercel env run -e preview -- <python> scripts/verify_staging_resources.py`.
The default is metadata-only preflight. Execution requires exact project and database
host confirmations. Output contains no credentials, URLs with credentials, or exceptions.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROJECT_ID = "prj_a4tgpf6rsmYp7H3JroXUH4x6ERk3"
BLOB_HOST = "hxwgjlfglmovclxl.private.blob.vercel-storage.com"
REVISION = "f3a1c7e9b420"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-project")
    parser.add_argument("--expected-database-host")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    report = {"project_id": PROJECT_ID, "mode": "execute" if args.execute else "preflight"}
    phase = "configuration"
    try:
        from sqlalchemy import create_engine, insert, select, text
        from sqlalchemy.engine import make_url
        from sqlalchemy.pool import NullPool

        from workbench import config, storage
        from workbench.db import normalize_database_url
        from workbench.models import Workspace

        # This operator tool consumes only injected environment values. In particular,
        # local dotenv files and the editable environment's older checkout are not used.
        config._load_dotenv = lambda: None
        link = json.loads((ROOT / ".vercel" / "project.json").read_text())
        if link.get("projectId") != PROJECT_ID:
            raise ValueError("project mismatch")
        raw_url = os.environ.get("WB_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        url = make_url(normalize_database_url(raw_url))
        if url.drivername != "postgresql+psycopg" or not (url.host or "").endswith(".neon.tech"):
            raise ValueError("not a Neon PostgreSQL endpoint")
        report["database_host"] = url.host  # endpoint name only, never the connection URL
        report["blob_credential_available"] = bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))
        if not args.execute:
            print(json.dumps(report, indent=2))
            return 0
        if args.confirm_project != PROJECT_ID or args.expected_database_host != url.host:
            raise ValueError("explicit resource confirmations required")
        if not report["blob_credential_available"]:
            raise ValueError("Blob credential unavailable")
        provider = os.environ.get("WB_PROVIDER_MODE", "")
        if provider not in {"", "fake"}:
            raise ValueError("live providers refused")
        # Sensitive custom values may be blank in env run. These explicit local values
        # select the adapter, not deployment configuration; health verifies the Function.
        settings = config.Settings(
            _env_ignore_empty=True,
            database_url=raw_url, provider_mode="fake", artifact_storage_backend="vercel_blob"
        )
        config.get_settings = lambda: settings
        storage.get_settings = lambda: settings
        phase = "database"
        engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 10})
        row_id = uuid4().hex
        report["synthetic_row_id"] = row_id
        try:
            with engine.connect() as connection:
                with connection.begin() as transaction:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    revisions = list(connection.scalars(text("SELECT version_num FROM alembic_version")))
                    if revisions != [REVISION]:
                        raise ValueError("unexpected migration revision")
                    report["alembic_revision"] = revisions[0]
                    connection.execute(insert(Workspace).values(id=row_id, name=f"synthetic-smoke-{row_id}"))
                    if connection.scalar(select(Workspace.id).where(Workspace.id == row_id)) != row_id:
                        raise ValueError("database readback mismatch")
                    transaction.rollback()
                if connection.scalar(select(Workspace.id).where(Workspace.id == row_id)) is not None:
                    raise ValueError("rollback verification failed")
                report["database_round_trip"] = "passed; synthetic workspace rolled back"
        finally:
            engine.dispose()
        phase = "blob"
        import httpx
        from vercel.blob import BlobClient

        payload = f"Paper-Workbench synthetic Preview smoke {row_id}\n".encode()
        key = storage.content_key(payload, filename="smoke.txt", namespace=f"staging-smoke/{row_id}")
        report["synthetic_blob_key"] = key
        report["synthetic_sha256"] = hashlib.sha256(payload).hexdigest()
        with BlobClient() as client:
            # Use the SDK's own credential parser to confirm the private store before writing.
            from vercel._internal.blob import extract_store_id_from_token

            store_id = extract_store_id_from_token(os.environ["BLOB_READ_WRITE_TOKEN"])
            if f"{store_id.lower()}.private.blob.vercel-storage.com" != BLOB_HOST:
                raise ValueError("Blob store mismatch")
            try:
                phase = "blob_write"
                reference = storage.store_content(
                    payload, filename="smoke.txt", namespace=f"staging-smoke/{row_id}"
                )
                if urlparse(reference.get("private_url", "")).hostname != BLOB_HOST:
                    raise ValueError("unexpected Blob host")
                phase = "blob_read"
                if storage.read_bytes(reference) != payload:
                    raise ValueError("Blob checksum mismatch")
                phase = "blob_idempotent_write"
                repeated = storage.store_content(
                    payload, filename="smoke.txt", namespace=f"staging-smoke/{row_id}"
                )
                if storage.read_bytes(repeated) != payload:
                    raise ValueError("idempotent write failed")
                phase = "blob_anonymous_denial"
                response = httpx.get(reference["private_url"], timeout=15, follow_redirects=False)
                if response.status_code not in {401, 403, 404}:
                    raise ValueError("private Blob exposed anonymously")
                report["anonymous_blob_status"] = response.status_code
                report["blob_round_trip"] = "passed; private, checksum verified, idempotent"
            finally:
                client.delete(key)
                remaining = client.list_objects(prefix=key, limit=1)
                if storage._field(remaining, "blobs", []):
                    raise ValueError("Blob cleanup verification failed")
                report["blob_cleanup"] = "deleted; exact key absent from listing"
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["failed_phase"] = phase
        report["error_type"] = type(exc).__name__
        report["cause_type"] = type(exc.__cause__).__name__ if exc.__cause__ else None
        if str(exc) in {
            "private Blob upload failed", "private Blob read failed", "artifact not found",
            "private Blob response had no content stream", "artifact checksum mismatch",
        }:
            report["adapter_error"] = str(exc)
        # Exception text/tracebacks can contain provider connection URLs and credentials.
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
