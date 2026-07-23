"""Reporting-guideline checklists: attach, item tracking, advisory audit findings."""

import pytest

from workbench.services import audits, authoring, guidelines


@pytest.fixture()
def manuscript(session, project):
    m = authoring.create_manuscript(session, project.id, title="M")
    session.commit()
    return m


def test_packs_listed():
    packs = {p["pack_id"]: p for p in guidelines.list_packs()}
    assert packs["prisma-2020"]["item_count"] == 27
    assert packs["consort-2010"]["item_count"] == 26  # 1a, 1b + items 2-25
    assert packs["strobe"]["item_count"] == 22
    for p in packs.values():
        assert p["source"]  # provenance mandatory


def test_attach_track_and_audit(session, manuscript):
    cl = guidelines.attach_checklist(session, manuscript.id, "prisma-2020")
    session.commit()
    assert all(i["status"] == "unaddressed" for i in cl.body["items"])

    # duplicate attach refused
    with pytest.raises(guidelines.GuidelineError, match="already attached"):
        guidelines.attach_checklist(session, manuscript.id, "prisma-2020")

    guidelines.update_item(session, cl.id, "1", status="addressed", location="Title")
    with pytest.raises(guidelines.GuidelineError, match="requires a note"):
        guidelines.update_item(session, cl.id, "24", status="not_applicable")
    guidelines.update_item(session, cl.id, "24", status="not_applicable",
                           note="no protocol was registered")
    session.commit()

    items = {i["id"]: i for i in session.get(type(cl), cl.id).body["items"]}
    assert items["1"]["status"] == "addressed"
    assert items["24"]["note"] == "no protocol was registered"

    findings = [f for f in audits.audit_manuscript(session, manuscript.id)
                if f["code"] == "checklist-items-open"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"  # always advisory
    assert "25 of 27" in findings[0]["message"]


def test_unknown_pack_and_item_rejected(session, manuscript):
    with pytest.raises(guidelines.GuidelineError, match="unknown guideline pack"):
        guidelines.attach_checklist(session, manuscript.id, "sqUIRE-9000")
    cl = guidelines.attach_checklist(session, manuscript.id, "strobe")
    with pytest.raises(guidelines.GuidelineError, match="not in checklist"):
        guidelines.update_item(session, cl.id, "99", status="addressed")
    with pytest.raises(guidelines.GuidelineError, match="status must be"):
        guidelines.update_item(session, cl.id, "1", status="done")


def test_fully_addressed_checklist_is_silent(session, manuscript):
    cl = guidelines.attach_checklist(session, manuscript.id, "strobe")
    for item in cl.body["items"]:
        guidelines.update_item(session, cl.id, item["id"], status="addressed",
                               location="somewhere")
    session.commit()
    assert guidelines.audit_checklists(session, manuscript.id) == []
