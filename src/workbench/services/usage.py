"""Token-usage metering and per-project cost ceilings.

Rules:
- Every LLM chat/embedding call is attributed to a project and a call kind and recorded
  as a UsageEvent in the same transaction as the work it paid for.
- A CostBudget sets a ceiling on live token spend per UTC calendar month (0 = unlimited).
  Enforcement is fail-closed and happens BEFORE the provider is contacted.
- Simulated (fake-provider) usage is recorded for observability but never counts toward
  the ceiling — fakes cost nothing and must never block offline work.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import CostBudget, UsageEvent
from ..providers import registry
from . import research


class BudgetExceeded(RuntimeError):
    """The project's monthly token ceiling is reached; the live call was not made."""


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_usage(usage: dict | None) -> tuple[int, int, int]:
    """(input, output, total) from an OpenAI- or Anthropic-shaped usage dict."""
    usage = usage or {}
    inp = _int(usage.get("input_tokens") or usage.get("prompt_tokens"))
    out = _int(usage.get("output_tokens") or usage.get("completion_tokens"))
    total = _int(usage.get("total_tokens")) or inp + out
    return inp, out, total


def set_budget(
    session: Session, project_id: str, *, monthly_token_ceiling: int, note: str = ""
) -> CostBudget:
    project = research._project(session, project_id)
    if monthly_token_ceiling < 0:
        raise research.IntegrityError("ceiling must be >= 0 (0 = unlimited)")
    budget = session.scalar(select(CostBudget).where(CostBudget.project_id == project_id))
    if budget is None:
        budget = CostBudget(project_id=project_id)
        session.add(budget)
    budget.monthly_token_ceiling = monthly_token_ceiling
    budget.note = note
    session.flush()
    record_audit(
        session, workspace_id=project.workspace_id, actor="user", action="set_budget",
        object_type="cost_budget", object_id=budget.id,
        detail={"monthly_token_ceiling": monthly_token_ceiling},
    )
    return budget


def month_usage(session: Session, project_id: str) -> dict:
    """Current-UTC-month usage summary: live totals, ceiling, and per-kind breakdown."""
    research._project(session, project_id)
    budget = session.scalar(select(CostBudget).where(CostBudget.project_id == project_id))
    ceiling = budget.monthly_token_ceiling if budget else 0
    rows = session.execute(
        select(
            UsageEvent.kind,
            UsageEvent.simulated,
            func.count(UsageEvent.id),
            func.sum(UsageEvent.input_tokens),
            func.sum(UsageEvent.output_tokens),
            func.sum(UsageEvent.total_tokens),
        )
        .where(
            UsageEvent.project_id == project_id,
            UsageEvent.created_at >= _month_start().replace(tzinfo=None),
        )
        .group_by(UsageEvent.kind, UsageEvent.simulated)
    ).all()
    by_kind: dict[str, dict] = {}
    live_total = 0
    for kind, simulated, calls, inp, out, total in rows:
        entry = by_kind.setdefault(
            kind, {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                   "total_tokens": 0, "simulated_calls": 0}
        )
        if simulated:
            entry["simulated_calls"] += calls
        else:
            entry["calls"] += calls
            entry["input_tokens"] += _int(inp)
            entry["output_tokens"] += _int(out)
            entry["total_tokens"] += _int(total)
            live_total += _int(total)
    return {
        "month_start": _month_start().isoformat(),
        "live_total_tokens": live_total,
        "monthly_token_ceiling": ceiling,
        "remaining_tokens": max(ceiling - live_total, 0) if ceiling else None,
        "ceiling_reached": bool(ceiling) and live_total >= ceiling,
        "by_kind": by_kind,
    }


def check_budget(session: Session, project_id: str) -> None:
    """Raise BudgetExceeded if the project's live spend has reached its ceiling."""
    summary = month_usage(session, project_id)
    if summary["ceiling_reached"]:
        raise BudgetExceeded(
            f"project {project_id} has used {summary['live_total_tokens']} live tokens "
            f"this month, at/over its ceiling of {summary['monthly_token_ceiling']} — "
            "raise the ceiling (or set 0 for unlimited) to continue live calls"
        )


def record_usage(
    session: Session, project_id: str, *, provider: str, model: str, kind: str,
    usage: dict | None, simulated: bool,
) -> UsageEvent:
    inp, out, total = normalize_usage(usage)
    event = UsageEvent(
        project_id=project_id, provider=provider, model=model, kind=kind,
        input_tokens=inp, output_tokens=out, total_tokens=total, simulated=simulated,
    )
    session.add(event)
    return event


def charged_chat(
    session: Session, project_id: str, kind: str, *,
    system: str, messages: list[dict], max_output_tokens: int = 4096,
):
    """The single funnel for chat-model calls: budget check (fail-closed, before the
    provider is contacted) → provider call → usage recorded in-transaction."""
    from ..config import get_settings

    live = get_settings().provider_mode == "live"
    if live:
        check_budget(session, project_id)
    # Late-bound through the registry module so test monkeypatching keeps working.
    provider = registry.get_chat_provider()
    result = provider.chat(
        system=system, messages=messages, model=registry.chat_model_name(),
        max_output_tokens=max_output_tokens,
    )
    record_usage(
        session, project_id, provider=get_settings().llm_provider if live else "fake",
        model=result.model, kind=kind, usage=result.usage,
        simulated=result.model == "fake",
    )
    return result
