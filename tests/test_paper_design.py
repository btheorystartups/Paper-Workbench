"""Multi-candidate paper design: distinct candidates, parser, compare, freeze, manuscript."""

import pytest

from workbench.services import authoring, paper_design, research
from workbench.vocab import ObjectKind, ResultStrength


@pytest.fixture()
def objects(session, project):
    r1 = research.create_object(session, project.id, kind=ObjectKind.RESULT,
                                title="Persistent cache 2.42x at n=16",
                                strength=ResultStrength.EMPIRICALLY_ESTABLISHED)
    r2 = research.create_object(session, project.id, kind=ObjectKind.RESULT,
                                title="No-reinflate reduces IR cost")
    q = research.create_object(session, project.id, kind=ObjectKind.QUESTION,
                               title="Is CM a useful Boolean IR?")
    session.commit()
    return [r1, r2, q]


def test_generate_produces_n_distinct_candidates(session, project, objects):
    ids = [o.id for o in objects]
    cands = paper_design.generate_candidates(session, project.id, object_ids=ids, n=3)
    assert len(cands) == 3
    # each is a review-gated paper_candidate with a distinct angle
    assert all(c.kind == ObjectKind.PAPER_CANDIDATE for c in cands)
    assert all(c.ai_suggested and not c.accepted_by_user for c in cands)
    angles = [c.body["angle"] for c in cands]
    assert len(set(angles)) == 3  # genuinely different angles
    recs = {c.body["recommendation"] for c in cands}
    assert len(recs) >= 2  # not all the same recommendation
    # the "focused" angle narrows the included objects
    focused = next(c for c in cands if c.body["angle"] == "focused")
    assert len(focused.body["included_object_ids"]) == 1


def test_generate_requires_valid_objects(session, project):
    with pytest.raises(paper_design.DesignError, match="at least one"):
        paper_design.generate_candidates(session, project.id, object_ids=[])
    with pytest.raises(paper_design.DesignError, match="not in project"):
        paper_design.generate_candidates(session, project.id, object_ids=["nope"])


def test_parse_candidates_defensive():
    good = ('prefix {"candidates": [{"title": "A", "paper_type": "computational"}, '
            '{"title": "B"}]} suffix')
    parsed = paper_design._parse_candidates(good)
    assert [c["title"] for c in parsed] == ["A", "B"]
    # entries without a title are dropped; junk yields []
    assert paper_design._parse_candidates("not json") == []
    assert paper_design._parse_candidates('{"candidates": "oops"}') == []
    assert paper_design._parse_candidates('{"candidates": [{"no_title": 1}]}') == []


def test_store_maps_unknown_types_to_custom(session, project, objects):
    obj = paper_design._store_candidate(
        session, project.id,
        {"title": "X", "paper_type": "bogus", "structure": "bogus",
         "recommendation": "bogus", "included_object_ids": [objects[0].id, "outsider"]},
        angle="comprehensive",
    )
    assert obj.body["paper_type"] == "custom"
    assert obj.body["structure"] == "custom"
    assert obj.body["recommendation"] is None
    # only in-project ids are kept
    assert obj.body["included_object_ids"] == [objects[0].id]


def test_compare_and_freeze_then_manuscript(session, project, objects):
    cands = paper_design.generate_candidates(session, project.id,
                                             object_ids=[o.id for o in objects], n=3)
    comparison = paper_design.compare_candidates(session, [c.id for c in cands])
    assert "recommendation" in comparison["fields"]
    assert set(comparison["matrix"]["angle"].keys()) == {c.id for c in cands}

    chosen = cands[0]
    frozen = paper_design.freeze_candidate(session, chosen.id)
    assert frozen.body["frozen"] is True
    assert frozen.accepted_by_user is True
    # others remain unfrozen proposals
    assert session.get(type(cands[1]), cands[1].id).body["frozen"] is False

    ms = authoring.create_manuscript(session, project.id, title="From candidate",
                                     from_candidate_id=chosen.id)
    assert ms.body["from_candidate_id"] == chosen.id


def test_live_path_used_when_model_returns_json(session, project, objects, monkeypatch):
    """If the chat provider returns candidate JSON, those candidates are used (not the
    deterministic fallback)."""
    from workbench.providers.protocols import ChatResult

    class _JsonProvider:
        def chat(self, **_kw):
            return ChatResult(
                text='{"candidates": [{"title": "LLM Paper One", "paper_type": "comparative"},'
                     '{"title": "LLM Paper Two", "recommendation": "technical_note"}]}',
                model="stub", provider_request_id="r1",
            )

    monkeypatch.setattr(paper_design, "get_chat_provider", lambda: _JsonProvider(), raising=False)
    import workbench.providers.registry as reg
    monkeypatch.setattr(reg, "get_chat_provider", lambda: _JsonProvider())
    monkeypatch.setattr(reg, "chat_model_name", lambda: "stub")

    cands = paper_design.generate_candidates(session, project.id,
                                             object_ids=[o.id for o in objects], n=2)
    titles = {c.title for c in cands}
    assert titles == {"LLM Paper One", "LLM Paper Two"}
    assert all(c.body["model"] == "stub" for c in cands)
