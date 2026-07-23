"""Thread branching and explicit dialogue modes."""

import pytest
from sqlalchemy import select

from workbench.models import ProposedAction, Turn
from workbench.services import dialogue


def _turns(session, tid):
    return list(session.scalars(
        select(Turn).where(Turn.thread_id == tid).order_by(Turn.created_at, Turn.id)
    ))


def test_mode_in_system_prompt_and_settable(session, project):
    thread = dialogue.create_thread(session, project.id, title="T", mode="challenge")
    assert "MODE challenge" in dialogue.assemble_system_prompt(session, thread)
    dialogue.set_mode(session, thread.id, "plan")
    assert "MODE plan" in dialogue.assemble_system_prompt(session, thread)
    with pytest.raises(dialogue.DialogueError, match="unknown mode"):
        dialogue.set_mode(session, thread.id, "vibes")
    with pytest.raises(dialogue.DialogueError, match="unknown mode"):
        dialogue.create_thread(session, project.id, title="T2", mode="vibes")


def test_branch_copies_history_up_to_turn(session, project):
    thread = dialogue.create_thread(session, project.id, title="Main", goal="g",
                                    mode="compare")
    dialogue.post_user_turn(session, thread.id, "first")
    dialogue.post_user_turn(session, thread.id, "second")
    session.commit()
    turns = _turns(session, thread.id)
    assert len(turns) == 4  # 2 user + 2 assistant
    fork_at = turns[1]  # first assistant reply

    branch = dialogue.branch_thread(session, thread.id, fork_at.id, title="Alt")
    session.commit()
    assert branch.parent_thread_id == thread.id
    assert branch.branched_from_turn_id == fork_at.id
    assert branch.mode == "compare"
    assert branch.goal == "g"

    copied = _turns(session, branch.id)
    assert [t.content for t in copied] == [t.content for t in turns[:2]]
    assert copied[0].provenance["copied_from_turn_id"] == turns[0].id
    # original thread untouched
    assert len(_turns(session, thread.id)) == 4


def test_branches_evolve_independently(session, project):
    thread = dialogue.create_thread(session, project.id, title="Main")
    dialogue.post_user_turn(session, thread.id, "shared question")
    session.commit()
    fork_at = _turns(session, thread.id)[-1]
    branch = dialogue.branch_thread(session, thread.id, fork_at.id)
    dialogue.post_user_turn(session, branch.id, "branch-only follow-up")
    session.commit()
    assert len(_turns(session, branch.id)) == 4
    assert len(_turns(session, thread.id)) == 2


def test_branch_does_not_copy_proposed_actions(session, project):
    thread = dialogue.create_thread(session, project.id, title="Main")
    # the fake provider proposes an action for content containing "task"
    dialogue.post_user_turn(session, thread.id, "please add a task for benchmarking")
    session.commit()
    fork_at = _turns(session, thread.id)[-1]
    branch = dialogue.branch_thread(session, thread.id, fork_at.id)
    session.commit()
    branch_actions = list(session.scalars(
        select(ProposedAction).where(ProposedAction.thread_id == branch.id)
    ))
    assert branch_actions == []


def test_branch_rejects_foreign_turn(session, project):
    a = dialogue.create_thread(session, project.id, title="A")
    b = dialogue.create_thread(session, project.id, title="B")
    dialogue.post_user_turn(session, a.id, "hi")
    session.commit()
    foreign = _turns(session, a.id)[0]
    with pytest.raises(dialogue.DialogueError, match="turn not found"):
        dialogue.branch_thread(session, b.id, foreign.id)
