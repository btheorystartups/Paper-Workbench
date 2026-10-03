"""The section conversation must preserve evidence and reject stale or foreign edits."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from workbench.models import Claim, ClaimEvidence, ProposedAction, ResearchObject, Source, utcnow
from workbench.providers.protocols import ChatResult
from workbench.services import authoring, dialogue, manuscript_chat, research, usage
from workbench.vocab import SourceAccess


@pytest.fixture()
def section_thread(session, project):
    source = research.register_source(
        session,
        project.id,
        title="Synthetic source",
        access=SourceAccess.FULL_TEXT_USER_SUPPLIED,
        acquisition="Synthetic fixture",
    )
    excerpt = research.capture_excerpt(
        session, source.id, text="Observed improvement: 12%.", locator="page 3"
    )
    claim = research.create_claim(
        session,
        project.id,
        text="The experiment improved by 12%.",
        support="external_source",
        excerpt_ids=[excerpt.id],
    )
    manuscript = authoring.create_manuscript(session, project.id, title="Synthetic paper")
    section = authoring.add_section(
        session,
        manuscript.id,
        heading="Discussion",
        text="Original draft.",
        purpose="Interpret the observed effect",
        claim_ids=[claim.id],
        word_budget=300,
    )
    thread = dialogue.create_thread(
        session,
        project.id,
        title="Discuss the findings",
        mode="act",
        manuscript_id=manuscript.id,
        section_id=section.id,
    )
    session.commit()
    return thread


def propose(session, thread, text="Revised prose with a caveat."):
    _, turn = dialogue.post_user_turn(session, thread.id, "revise: " + text)
    session.commit()
    return session.scalar(
        select(ProposedAction).where(ProposedAction.result["turn_id"].as_string() == turn.id)
    )


def test_context_contains_real_excerpts_and_support_without_unrelated_material(
    session, project, section_thread
):
    research.create_object(session, project.id, kind="note", title="Unpinned secret research")
    ctx = manuscript_chat.context(session, section_thread)
    assert {item["kind"] for item in ctx["items"]} >= {
        "manuscript",
        "section",
        "claim",
        "excerpt",
        "source_metadata",
        "evidence_link",
    }
    prompt = dialogue.assemble_system_prompt(session, section_thread)
    assert "Observed improvement: 12%." in prompt and "page 3" in prompt
    assert "external_source" in prompt and "asserted" in prompt
    assert "Unpinned secret research" not in prompt
    action = propose(session, section_thread)
    assert action.payload["context_hash"] == ctx["context_hash"]
    assert session.get(ResearchObject, section_thread.section_id).body["text"] == "Original draft."


def test_accept_revise_and_undo_are_explicit_and_preserve_evidence(session, section_thread):
    section = session.get(ResearchObject, section_thread.section_id)
    before = dict(section.body)
    claim = session.get(Claim, before["claim_ids"][0])
    evidence = session.scalar(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id))
    action = propose(session, section_thread)
    replacement = dialogue.revise_proposal(
        session, action.id, plan_hash=action.plan_hash, text="A human-adjusted interpretation."
    )
    session.commit()
    assert action.status == "invalidated"
    assert section.body == before
    dialogue.approve_action(session, replacement.id, plan_hash=replacement.plan_hash)
    session.commit()
    assert section.body == {**before, "text": "A human-adjusted interpretation."}
    assert section.accepted_by_user is True and section.ai_suggested is False
    assert claim.support == "external_source" and evidence.entailment == "asserted"
    undo = dialogue.revise_proposal(session, replacement.id, plan_hash=replacement.plan_hash, undo=True)
    session.commit()
    assert section.body["text"] == "A human-adjusted interpretation."
    dialogue.approve_action(session, undo.id, plan_hash=undo.plan_hash)
    session.commit()
    assert section.body == before
    assert replacement.result["before_text"] == "Original draft."
    assert replacement.result["after_text"] == "A human-adjusted interpretation."


@pytest.mark.parametrize("changed", ["section", "evidence", "membership", "source_deleted"])
def test_changed_context_invalidates_instead_of_overwriting(session, section_thread, changed):
    action = propose(session, section_thread)
    section = session.get(ResearchObject, section_thread.section_id)
    if changed == "section":
        # A different transaction modifies the section while this reviewer has a cached object.
        with Session(session.bind) as other:
            authoring.update_section(other, section.id, text="A concurrent author's edit.")
            other.commit()
    elif changed == "evidence":
        claim = session.get(Claim, section.body["claim_ids"][0])
        claim.support = "unsupported"
        session.commit()
    elif changed == "membership":
        manuscript = session.get(ResearchObject, section_thread.manuscript_id)
        manuscript.body = {**manuscript.body, "section_order": []}
        session.commit()
    else:
        source = session.scalar(select(Source))
        source.deleted_at = utcnow()
        session.commit()
    with pytest.raises(dialogue.DialogueError):
        dialogue.approve_action(session, action.id, plan_hash=action.plan_hash)
    session.commit()
    assert action.status == "invalidated"
    assert section.body["text"] != action.payload["text"]


def test_reject_duplicate_approval_and_undo_after_later_edit(session, section_thread):
    rejected = propose(session, section_thread, "Reject me.")
    dialogue.reject_action(session, rejected.id)
    session.commit()
    with pytest.raises(dialogue.DialogueError):
        dialogue.approve_action(session, rejected.id, plan_hash=rejected.plan_hash)
    accepted = propose(session, section_thread)
    dialogue.approve_action(session, accepted.id, plan_hash=accepted.plan_hash)
    session.commit()
    with pytest.raises(dialogue.DialogueError):
        dialogue.approve_action(session, accepted.id, plan_hash=accepted.plan_hash)
    authoring.update_section(session, section_thread.section_id, text="A later change.")
    session.commit()
    with pytest.raises(dialogue.DialogueError, match="changed since"):
        dialogue.revise_proposal(session, accepted.id, plan_hash=accepted.plan_hash, undo=True)


def test_foreign_section_or_mismatched_manuscript_is_rejected(session, project, section_thread):
    workspace = research.create_workspace(session, "Other tenant")
    other = research.create_project(session, workspace.id, "Other project")
    manuscript = authoring.create_manuscript(session, other.id, title="Foreign paper")
    section = authoring.add_section(session, manuscript.id, heading="Private", text="Foreign content")
    with pytest.raises(dialogue.DialogueError):
        dialogue.create_thread(
            session, project.id, title="Bad", manuscript_id=manuscript.id, section_id=section.id
        )
    with pytest.raises(dialogue.DialogueError):
        dialogue.create_thread(
            session,
            project.id,
            title="Bad",
            manuscript_id=section_thread.manuscript_id,
            section_id=section.id,
        )
    second = authoring.create_manuscript(session, project.id, title="Same project, different paper")
    with pytest.raises(dialogue.DialogueError):
        dialogue.create_thread(
            session, project.id, title="Bad", manuscript_id=second.id, section_id=section_thread.section_id
        )


@pytest.mark.parametrize(
    "payload", [[], {"section_id": "foreign", "text": "Overwrite"}, {"text": 12}, {"text": "x" * 30001}]
)
def test_malformed_model_edits_remain_unexecutable(session, section_thread, monkeypatch, payload):
    if isinstance(payload, dict) and "section_id" not in payload:
        payload = {**payload, "section_id": section_thread.section_id}
    monkeypatch.setattr(
        usage,
        "charged_chat",
        lambda *a, **kw: ChatResult(
            text="Bad proposal",
            model="fake",
            provider_request_id="synthetic",
            proposed_actions=[{"kind": "revise_section", "payload": payload}],
        ),
    )
    dialogue.post_user_turn(session, section_thread.id, "Please revise")
    session.commit()
    action = session.scalar(select(ProposedAction))
    assert action.risk == "unexecutable"
    with pytest.raises(dialogue.DialogueError, match="not executable"):
        dialogue.approve_action(session, action.id, plan_hash=action.plan_hash)


def test_metadata_only_and_deleted_evidence_are_never_included_as_text(session, section_thread):
    source = session.scalar(select(Source))
    source.access = SourceAccess.METADATA_ONLY
    session.commit()
    ctx = manuscript_chat.context(session, section_thread)
    assert not any(item["kind"] == "excerpt" for item in ctx["items"])
    assert ctx["warnings"]
    source.deleted_at = utcnow()
    session.commit()
    assert source.id not in {item["id"] for item in manuscript_chat.context(session, section_thread)["items"]}


def test_branch_preserves_section_and_oversize_context_fails_before_provider(
    session, section_thread, monkeypatch
):
    _, turn = dialogue.post_user_turn(session, section_thread.id, "Explain")
    branch = dialogue.branch_thread(session, section_thread.id, turn.id)
    assert branch.section_id == section_thread.section_id
    assert branch.manuscript_id == section_thread.manuscript_id
    section = session.get(ResearchObject, branch.section_id)
    section.body = {**section.body, "text": "x" * 90000}
    session.commit()

    def no_call(*args, **kwargs):
        pytest.fail("oversize context reached the provider")

    monkeypatch.setattr(usage, "charged_chat", no_call)
    with pytest.raises(dialogue.DialogueError, match="too large"):
        dialogue.post_user_turn(session, branch.id, "Summarize")


def test_http_context_brief_and_revision_flow(session, section_thread):
    from workbench.main import app

    with TestClient(app, raise_server_exceptions=True) as client:
        tid = section_thread.id
        ctx = client.get(f"/threads/{tid}/context")
        assert ctx.status_code == 200
        assert "Observed improvement" in ctx.json()["system_prompt"]
        assert (
            client.put(
                f"/threads/{tid}/brief", json={"summary": "Do not generalize beyond the pilot."}
            ).status_code
            == 200
        )
        reply = client.post(f"/threads/{tid}/turns", json={"content": "revise: A cautious interpretation."})
        assert reply.status_code == 200
        assert (
            reply.json()["assistant"]["provenance"]["manuscript_context"]["section_id"]
            == section_thread.section_id
        )
        action = reply.json()["proposed_actions"][0]
        revised = client.post(
            f"/actions/{action['id']}/revise",
            json={"plan_hash": action["plan_hash"], "text": "Reviewed prose."},
        )
        assert revised.status_code == 200
        action = revised.json()
        assert (
            client.post(
                f"/actions/{action['id']}/approve", json={"plan_hash": action["plan_hash"]}
            ).status_code
            == 200
        )
        undo = client.post(f"/actions/{action['id']}/undo", json={"plan_hash": action["plan_hash"]})
        assert undo.status_code == 200
        assert client.post(f"/actions/{undo.json()['id']}/reject").status_code == 200
