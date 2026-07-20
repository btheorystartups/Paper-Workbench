"""Domain rules: evidence integrity, provenance requirements, audit trail."""

import pytest
from sqlalchemy import select

from workbench.models import AuditEvent
from workbench.services import research
from workbench.vocab import ClaimSupport, ObjectKind, Relation, SourceAccess


def test_create_object_and_audit(session, project):
    obj = research.create_object(
        session, project.id, kind=ObjectKind.RESULT, title="CM no-reinflate speedup",
        strength="empirically_established",
    )
    session.commit()
    assert obj.accepted_by_user is True  # human-created
    events = list(session.scalars(select(AuditEvent)))
    assert any(e.object_id == obj.id and e.action == "create" for e in events)


def test_ai_suggested_object_needs_acceptance(session, project):
    obj = research.create_object(
        session, project.id, kind=ObjectKind.HYPOTHESIS, title="Maybe X", ai_suggested=True
    )
    assert obj.accepted_by_user is False
    research.accept_object(session, obj.id)
    assert obj.accepted_by_user is True


def test_full_text_source_requires_acquisition(session, project):
    with pytest.raises(research.IntegrityError, match="acquisition"):
        research.register_source(
            session, project.id, title="Some PDF",
            access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
        )
    src = research.register_source(
        session, project.id, title="Some PDF",
        access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
        acquisition="user supplied their own manuscript file",
    )
    assert src.id


def test_excerpt_rules(session, project):
    meta_src = research.register_source(
        session, project.id, title="Metadata-only record", access=SourceAccess.METADATA_ONLY
    )
    with pytest.raises(research.IntegrityError, match="metadata-only"):
        research.capture_excerpt(session, meta_src.id, text="quote", locator="p. 1")
    ok_src = research.register_source(
        session, project.id, title="Open paper", access=SourceAccess.EXCERPT_AVAILABLE
    )
    with pytest.raises(research.IntegrityError, match="locator"):
        research.capture_excerpt(session, ok_src.id, text="quote", locator="  ")
    excerpt = research.capture_excerpt(session, ok_src.id, text="quote", locator="p. 3, §2")
    assert len(excerpt.checksum) == 64


def test_claim_support_states_enforced(session, project):
    src = research.register_source(
        session, project.id, title="Paper", access=SourceAccess.EXCERPT_AVAILABLE
    )
    excerpt = research.capture_excerpt(session, src.id, text="…", locator="p. 2")
    result = research.create_object(
        session, project.id, kind=ObjectKind.RESULT, title="Benchmark result"
    )

    with pytest.raises(research.IntegrityError, match="excerpt"):
        research.create_claim(
            session, project.id, text="X is known", support=ClaimSupport.EXTERNAL_SOURCE
        )
    with pytest.raises(research.IntegrityError, match="research-object"):
        research.create_claim(
            session, project.id, text="We showed X", support=ClaimSupport.RESEARCH_RESULT
        )
    claim = research.create_claim(
        session, project.id, text="X matches prior work",
        support=ClaimSupport.BOTH, excerpt_ids=[excerpt.id], research_object_ids=[result.id],
    )
    evidence = research.claim_evidence(session, claim.id)
    assert {ev.excerpt_id for ev in evidence} >= {excerpt.id}
    assert {ev.research_object_id for ev in evidence} >= {result.id}

    # Unsupported/interpretation claims may exist without links — but keep their state.
    free = research.create_claim(
        session, project.id, text="This might matter", support=ClaimSupport.INTERPRETATION
    )
    assert free.support == ClaimSupport.INTERPRETATION


def test_cross_project_evidence_rejected(session, project):
    from workbench.services.research import create_project, create_workspace

    other_ws = create_workspace(session, "Other")
    other = create_project(session, other_ws.id, "Other project")
    src = research.register_source(
        session, other.id, title="Elsewhere", access=SourceAccess.EXCERPT_AVAILABLE
    )
    excerpt = research.capture_excerpt(session, src.id, text="q", locator="p. 1")
    with pytest.raises(research.IntegrityError, match="does not belong"):
        research.create_claim(
            session, project.id, text="Leaky", support=ClaimSupport.EXTERNAL_SOURCE,
            excerpt_ids=[excerpt.id],
        )


def test_link_objects_same_project_only(session, project):
    a = research.create_object(session, project.id, kind=ObjectKind.RESULT, title="A")
    b = research.create_object(session, project.id, kind=ObjectKind.QUESTION, title="B")
    edge = research.link_objects(session, project.id, a.id, b.id, Relation.RELATES_TO)
    assert edge.relation == Relation.RELATES_TO
