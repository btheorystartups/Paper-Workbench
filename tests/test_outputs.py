"""Alternative outputs: grounded generation, review gate, provenance, listing."""

import pytest

from workbench.services import authoring, outputs, research
from workbench.vocab import ClaimSupport, ObjectKind, SourceAccess


@pytest.fixture()
def manuscript(session, project):
    src = research.register_source(
        session, project.id, title="Prior", access=SourceAccess.EXCERPT_AVAILABLE,
        authors="A. B.", year=2001, doi="10.1/z",
    )
    excerpt = research.capture_excerpt(session, src.id, text="q", locator="p.1")
    claim = research.create_claim(
        session, project.id, text="Cached CM reaches 2.42x cached bitset at n=16",
        support=ClaimSupport.EXTERNAL_SOURCE, excerpt_ids=[excerpt.id],
    )
    ms = authoring.create_manuscript(session, project.id, title="CM Evaluation")
    authoring.add_section(
        session, ms.id, heading="Results", purpose="report",
        text="Persistent caching changes the story.", claim_ids=[claim.id],
    )
    session.commit()
    return ms


def test_generate_each_output_type_is_ai_suggested(session, manuscript):
    for otype in outputs.OUTPUT_TYPES:
        obj = outputs.generate_output(session, manuscript.id, otype)
        assert obj.kind == ObjectKind.NOTE
        assert obj.ai_suggested is True
        assert obj.accepted_by_user is False  # enters the review gate
        assert obj.body["output_kind"] == otype
        assert obj.body["manuscript_id"] == manuscript.id
        assert obj.body["simulated"] is True  # fake provider in tests
        assert obj.body["content"]
        assert obj.body["human_reviewed"] is False


def test_output_links_to_manuscript(session, manuscript):
    from sqlalchemy import select

    from workbench.models import Edge
    from workbench.vocab import Relation

    obj = outputs.generate_output(session, manuscript.id, "conference_abstract")
    edge = session.scalars(
        select(Edge).where(Edge.src_id == obj.id, Edge.dst_id == manuscript.id)
    ).one()
    assert edge.relation == Relation.DERIVES_FROM


def test_invalid_type_and_empty_manuscript_rejected(session, project, manuscript):
    with pytest.raises(outputs.OutputError, match="output_type"):
        outputs.generate_output(session, manuscript.id, "haiku")
    empty = authoring.create_manuscript(session, project.id, title="Empty")
    with pytest.raises(outputs.OutputError, match="no sections"):
        outputs.generate_output(session, empty.id, "conference_abstract")


def test_list_outputs(session, manuscript):
    outputs.generate_output(session, manuscript.id, "poster_outline")
    outputs.generate_output(session, manuscript.id, "plain_language_summary")
    # an unrelated note must not show up
    research.create_object(session, manuscript.project_id, kind=ObjectKind.NOTE, title="scratch")
    listed = outputs.list_outputs(session, manuscript.id)
    kinds = {o.body["output_kind"] for o in listed}
    assert kinds == {"poster_outline", "plain_language_summary"}
