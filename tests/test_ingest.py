"""File ingestion: provenance, artifact copies, extraction labeling, rejection rules."""

from pathlib import Path

import pytest

from workbench.ingest.files import IngestError, extracted_text_for, ingest_file


def test_markdown_ingest_preserves_original_and_provenance(session, project, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()

    original = tmp_path / "notes.md"
    original.write_text("# CM Notes\nThe hinge identity holds.", encoding="utf-8")

    source = ingest_file(session, project.id, original, title="CM Notes")
    session.commit()

    meta = source.provider_metadata["ingest"]
    assert meta["extraction_confidence"] == "exact"
    assert meta["human_reviewed"] is False
    assert str(source.access) == "full_text_user_supplied"
    assert "user file ingested from" in source.acquisition

    # original untouched, artifact copy exists with same bytes
    assert original.read_text(encoding="utf-8").startswith("# CM Notes")
    artifact = Path(meta["artifact_path"])
    assert artifact.read_bytes() == original.read_bytes()
    assert "hinge identity" in extracted_text_for(source)


def test_csv_ingest_is_labeled_parsed(session, project, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    csv_file = tmp_path / "bench.csv"
    csv_file.write_text("n,method,ms\n8,cm,1.2\n8,bitset,0.6\n", encoding="utf-8")
    source = ingest_file(session, project.id, csv_file)
    meta = source.provider_metadata["ingest"]
    assert meta["extractor"] == "csv-summary"
    assert meta["extraction_detail"]["rows"] == 2
    assert "columns: n, method, ms" in extracted_text_for(source)


def test_unsupported_and_missing_files_rejected(session, project, tmp_path):
    with pytest.raises(IngestError, match="not found"):
        ingest_file(session, project.id, tmp_path / "nope.md")
    weird = tmp_path / "blob.xyz"
    weird.write_bytes(b"\x00\x01")
    with pytest.raises(IngestError, match="unsupported"):
        ingest_file(session, project.id, weird)
