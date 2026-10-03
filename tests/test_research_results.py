"""Data-only report exports: privacy, saved partial work, and evidence integrity."""

import copy
import hashlib
import io
import json
import zipfile

import pytest
from pypdf import PdfReader

from workbench.services import export_service, research_results


@pytest.fixture()
def snapshot():
    return {
        "id": "task",
        "state": "failed_partial",
        "reviews": {},
        "contract": {"question": "Finite topology", "instructions": "PRIVATE_PROMPT"},
        "sources": [
            {
                "source_id": "source",
                "title": "Accepted source",
                "artifact": {"local_path": "C:/Users/private/SENSITIVE_PATH.pdf"},
            }
        ],
        "synthesis": {"summary": "Bounded result"},
        "agents": [
            {
                "id": "child",
                "role": "child",
                "state": "failed_partial",
                "assignment": {"question": "Check the two states", "instructions": "ASSIGNMENT_PROMPT"},
                "provenance": {"account_email": "private@example.com", "raw_events": "RAW_EVENT_SECRET"},
                "report": {},
                "checkpoints": [
                    {
                        "report": {
                            "summary": "Saved checkpoint evidence",
                            "findings": [
                                {
                                    "id": "f",
                                    "category": "unresolved",
                                    "statement": "Partial finding",
                                    "scope": "One finite example",
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }


def test_pdf_contains_saved_partial_evidence_without_private_fields(snapshot, monkeypatch):
    monkeypatch.setattr(
        export_service, "weasyprint_status", lambda: {"available": False, "error": "test fallback"}
    )
    before = copy.deepcopy(snapshot)
    result = research_results.render_results(snapshot)
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(result.data)).pages)
    assert "Saved checkpoint evidence" in text
    assert "last saved checkpoint (partial)" in text
    assert "Partial finding" in text
    assert "NOT PUBLICATION READY" in text
    for private in (
        "PRIVATE_PROMPT",
        "ASSIGNMENT_PROMPT",
        "RAW_EVENT_SECRET",
        "private@example.com",
        "SENSITIVE_PATH",
    ):
        assert private not in text
    assert snapshot == before


def test_hostile_html_is_text_and_cannot_create_fetching_elements(monkeypatch):
    captured = {}

    def renderer(title, document, paragraphs, mode):
        captured["html"] = document
        return object()

    monkeypatch.setattr(export_service, "_render_pdf", renderer)
    hostile = '<img src="https://invalid.example/track"><script>alert(1)</script>'
    research_results.render_sections("<svg onload=alert(1)>", [("Evidence", hostile)])
    assert "<img" not in captured["html"]
    assert "<script" not in captured["html"]
    assert "<svg" not in captured["html"]
    assert "&lt;img" in captured["html"]
    assert "&lt;script&gt;" in captured["html"]


def package_bytes(snapshot, corrupt=False):
    members = {
        "task_settings.json": {
            k: v for k, v in snapshot.items() if k not in {"sources", "synthesis", "agents", "reviews"}
        },
        "source_manifest.json": snapshot["sources"],
        "synthesis.json": snapshot["synthesis"],
        "reviews.json": {},
        "agent_lineage.json": snapshot["agents"],
        "agents/child/report.json": {},
        "agents/child/checkpoints.json": snapshot["agents"][0]["checkpoints"],
    }
    files = {name: json.dumps(value).encode() for name, value in members.items()}
    manifest = {
        "files": [
            {"file": name, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for name, value in files.items()
        ]
    }
    if corrupt:
        files["synthesis.json"] = b'{"summary":"tampered"}'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr("package_manifest.json", json.dumps(manifest))
    return output.getvalue()


def test_saved_package_checks_hashes_before_deriving_report(snapshot):
    original = package_bytes(snapshot)
    restored = research_results.snapshot_from_package(original)
    assert restored["input_package_sha256"] == hashlib.sha256(original).hexdigest()
    assert restored["agents"][0]["checkpoints"] == snapshot["agents"][0]["checkpoints"]
    with pytest.raises(ValueError, match="hash mismatch"):
        research_results.snapshot_from_package(package_bytes(snapshot, corrupt=True))
