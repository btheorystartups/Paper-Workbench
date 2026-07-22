"""Cost budgets and usage metering: recording, monthly summary, fail-closed ceiling."""

import pytest

from workbench.models import UsageEvent
from workbench.services import dialogue, research, usage


def test_dialogue_records_simulated_usage(session, project):
    thread = dialogue.create_thread(session, project.id, title="T")
    dialogue.post_user_turn(session, thread.id, "hello")
    session.commit()
    events = session.query(UsageEvent).filter_by(project_id=project.id).all()
    assert len(events) == 1
    assert events[0].kind == "dialogue"
    assert events[0].simulated is True


def test_month_usage_summary_and_ceiling(session, project):
    usage.set_budget(session, project.id, monthly_token_ceiling=1000, note="pilot")
    usage.record_usage(session, project.id, provider="openai", model="gpt-4o",
                       kind="dialogue", usage={"input_tokens": 300, "output_tokens": 200},
                       simulated=False)
    usage.record_usage(session, project.id, provider="fake", model="fake",
                       kind="dialogue", usage={"input_tokens": 9999}, simulated=True)
    session.commit()
    summary = usage.month_usage(session, project.id)
    assert summary["live_total_tokens"] == 500  # simulated rows never count
    assert summary["monthly_token_ceiling"] == 1000
    assert summary["remaining_tokens"] == 500
    assert summary["ceiling_reached"] is False
    assert summary["by_kind"]["dialogue"]["simulated_calls"] == 1

    usage.record_usage(session, project.id, provider="openai", model="gpt-4o",
                       kind="skeptical_review", usage={"total_tokens": 600},
                       simulated=False)
    session.commit()
    with pytest.raises(usage.BudgetExceeded, match="ceiling"):
        usage.check_budget(session, project.id)


def test_fake_mode_never_blocked_by_ceiling(session, project):
    """Offline fakes cost nothing: a spent ceiling must not stop offline work."""
    usage.set_budget(session, project.id, monthly_token_ceiling=1)
    usage.record_usage(session, project.id, provider="openai", model="gpt-4o",
                       kind="dialogue", usage={"total_tokens": 5}, simulated=False)
    session.commit()
    thread = dialogue.create_thread(session, project.id, title="T")
    # provider_mode=fake in tests → charged_chat skips the budget gate
    dialogue.post_user_turn(session, thread.id, "still works offline")


def test_budget_validation(session, project):
    with pytest.raises(research.IntegrityError, match=">= 0"):
        usage.set_budget(session, project.id, monthly_token_ceiling=-5)
    b1 = usage.set_budget(session, project.id, monthly_token_ceiling=10)
    b2 = usage.set_budget(session, project.id, monthly_token_ceiling=20)
    assert b1.id == b2.id  # upsert, one budget row per project
    assert b2.monthly_token_ceiling == 20


def test_unlimited_when_no_budget(session, project):
    usage.record_usage(session, project.id, provider="openai", model="gpt-4o",
                       kind="dialogue", usage={"total_tokens": 10_000_000},
                       simulated=False)
    session.commit()
    usage.check_budget(session, project.id)  # no ceiling set → never raises
    assert usage.month_usage(session, project.id)["remaining_tokens"] is None
