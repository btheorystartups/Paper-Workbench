"""Retraction/correction watch: flagging, human-note protection, failed-lookup honesty."""

from workbench.services import audits, integrity, research
from workbench.vocab import SourceAccess


def _src(session, project, doi, note=""):
    s = research.register_source(
        session, project.id, title=f"Work {doi}", access=SourceAccess.METADATA_ONLY,
        doi=doi,
    )
    if note:
        s.integrity_note = note
    return s


def test_watch_flags_retracted_and_corrected(session, project):
    retracted = _src(session, project, "10.1000/retracted.1")
    corrected = _src(session, project, "10.1000/corrected.2")
    clean = _src(session, project, "10.1000/fine.3")
    nodoi = research.register_source(
        session, project.id, title="No DOI", access=SourceAccess.METADATA_ONLY,
    )
    assert nodoi.doi is None
    session.commit()

    result = integrity.check_project_sources(session, project.id)
    session.commit()
    assert result["checked"] == 3
    assert result["flagged"] == 2
    assert result["skipped_no_doi"] == 1

    assert "retraction" in retracted.integrity_note
    assert retracted.integrity_note.startswith("[integrity-watch]")
    assert retracted.provider_metadata["integrity"]["last_check"] == "flagged"
    assert "correction" in corrected.integrity_note
    assert clean.integrity_note == ""
    assert clean.provider_metadata["integrity"]["last_check"] == "clean"

    # the existing audit finding fires for flagged sources
    codes = [f for f in audits.audit_sources(session, project.id)
             if f["code"] == "source-integrity-flag"]
    assert {f["object_id"] for f in codes} == {retracted.id, corrected.id}


def test_failed_lookup_is_not_clean(session, project):
    failing = _src(session, project, "10.1000/failing.9")
    session.commit()
    result = integrity.check_project_sources(session, project.id)
    assert result["failed"] == 1
    assert result["flagged"] == 0
    assert failing.provider_metadata["integrity"]["last_check"] == "failed"
    assert failing.integrity_note == ""


def test_human_note_never_overwritten(session, project):
    src = _src(session, project, "10.1000/retracted.7", note="hand-checked: disputed data")
    session.commit()
    integrity.check_project_sources(session, project.id)
    assert src.integrity_note == "hand-checked: disputed data"
    # but the watch's evidence still lands in metadata
    assert src.provider_metadata["integrity"]["last_check"] == "flagged"
    assert src.provider_metadata["integrity"]["updates"][0]["type"] == "retraction"


def test_flag_survives_later_clean_check(session, project):
    """A found notice is never un-flagged automatically (provider glitches happen)."""
    src = _src(session, project, "10.1000/retracted.5")
    session.commit()
    integrity.check_project_sources(session, project.id)
    assert src.integrity_note.startswith("[integrity-watch]")
    src.doi = "10.1000/now-clean.5"  # simulate the provider no longer reporting it
    session.commit()
    integrity.check_project_sources(session, project.id)
    assert src.integrity_note.startswith("[integrity-watch]")  # still flagged
    assert src.provider_metadata["integrity"]["updates"]  # evidence retained
