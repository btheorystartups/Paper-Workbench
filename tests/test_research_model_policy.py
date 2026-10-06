"""Role routing and bounded discovery controls; no model inference or public network."""

import json
import threading
import time
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from workbench import config
from workbench.models import ResearchObject, ResearchTask, utcnow
from workbench.providers.research_codex_worker import CodexResearchWorker, settings_from_environment
from workbench.providers.research_executor import ExecutorError
from workbench.providers.research_model_policy import default_role_policy, role_selection
from workbench.research_contract import LiteraturePlan, TaskBrief
from workbench.services import manuscript_acquisition, research_runner, research_tasks
from workbench.services.research_runner import Runner, StopResearch


@pytest.mark.parametrize("role,effort", [
    ("proof_method", "xhigh"), ("source_citation", "high"),
    ("literature_contribution", "high"), ("adversarial", "xhigh"),
    ("literature_discovery", "high"), ("author", "low"), ("research", "low"),
])
def test_worker_environment_selects_operator_role_before_preflight(tmp_path, monkeypatch, role, effort):
    monkeypatch.setenv("WB_RESEARCH_CODEX_HOME", str(tmp_path))
    monkeypatch.setenv("WB_RESEARCH_CODEX_ROLE", role)
    monkeypatch.delenv("WB_RESEARCH_CODEX_ROLE_POLICY", raising=False)
    monkeypatch.setenv("WB_RESEARCH_CODEX_MODEL", "gpt-5.5")
    monkeypatch.setenv("WB_RESEARCH_CODEX_REASONING_EFFORT", "low")
    settings = settings_from_environment()
    assert settings.worker_role == role
    assert settings.codex_local_model == ("gpt-5.5" if role in {"author", "research"} else "gpt-6-astra")
    assert settings.codex_local_reasoning_effort == effort


@pytest.mark.parametrize("policy", [{}, {"adversarial": {"model": "gpt-6-astra", "reasoning_effort": "none"}},
                                      {"invented_role": {"model": "gpt-6-astra", "reasoning_effort": "high"}}])
def test_invalid_or_missing_role_policy_fails_without_fallback(policy):
    with pytest.raises(ValueError):
        role_selection("adversarial", policy, model="gpt-5.5", effort="low")


def test_operator_can_configure_each_role_without_changing_author():
    policy = default_role_policy()
    policy["proof_method"]["reasoning_effort"] = "high"
    assert role_selection("proof_method", policy, model="gpt-5.5", effort="low")["reasoning_effort"] == "high"
    assert role_selection("author", policy, model="gpt-5.5", effort="low")["model"] == "gpt-5.5"
    assert config.Settings(_env_file=None).research_codex_role_policy["adversarial"].model == "gpt-6-astra"


@pytest.mark.parametrize("role,operation,packet_role", [
    ("author", "audit", "proof_method"),
    ("adversarial", "draft", None), ("adversarial", "audit", "source_citation"),
    ("literature_discovery", "audit", "literature_contribution"),
])
def test_assigned_worker_cannot_switch_roles(role, operation, packet_role):
    worker = CodexResearchWorker.__new__(CodexResearchWorker)
    worker.settings = SimpleNamespace(worker_role=role)
    with pytest.raises(ValueError, match="assigned research worker role"):
        worker.run("worker", operation, {"packet": {"role": packet_role}})


@pytest.mark.parametrize("kind", ["turn_started", "specialist_report"])
@pytest.mark.parametrize("key,value", [("model", "gpt-5.5"), ("reasoning_effort", "low")])
def test_controller_rejects_role_model_or_effort_fallback(monkeypatch, key, value, kind):
    expected = {"model": "gpt-6-astra", "reasoning_effort": "xhigh"}
    event = {"type": kind, "result": {}, "provenance": {
        **expected, key: value, "codex_thread_id": "reviewer", "codex_turn_id": "turn",
        "account_email": "controlled@example.invalid"}}
    runner = SimpleNamespace(task=SimpleNamespace(contract={"executor": "process"}), usage=lambda *args: None)
    agent = SimpleNamespace(provenance={"requested_model_policy": expected})
    with pytest.raises(ExecutorError, match="different model or reasoning effort"):
        Runner.event(runner, SimpleNamespace(poll=lambda: event), agent, {}, "specialist_report")


@pytest.mark.parametrize("options", [
    {"agent_literature_discovery": True},
    {"agent_literature_discovery": True, "allow_public_search": True},
    {"task_type": "manuscript", "agent_literature_discovery": True, "discovery_rounds": 3},
])
def test_discovery_requires_explicit_permission_and_bounded_contract(options):
    with pytest.raises(ValidationError):
        TaskBrief(question="Prior art", **options)


def discovery_runner(plans, *, tokens=240000, limit=8):
    agent = SimpleNamespace(id="discovery", state="running")
    sent, closed = [], []
    handle = SimpleNamespace(pid=123, close=lambda: closed.append(True))
    task = SimpleNamespace(contract={"allow_public_search": True, "token_limit": tokens,
        "discovery_rounds": 2, "discovery_query_limit": limit}, sources=[], ledger={})
    runner = SimpleNamespace(task=task, agents=[], allocations=[], remaining_tokens=lambda: tokens,
        check=lambda: None, new_agent=lambda *args: agent, spawn=lambda a: handle,
        session=SimpleNamespace(commit=lambda: None))
    runner.send = lambda h, a, op, allowance, payload: sent.append(payload) or {}
    runner.wait_parent = lambda *args: plans.pop(0)
    return runner, agent, sent, closed


def plan(query):
    return {"queries": [{"provider": "crossref", "query": query, "count": 5}],
            "rationale": "Search alternate terminology", "coverage_notes": ["Bounded discovery only"],
            "remaining_gaps": ["Full-text review required"]}


def test_discovery_refines_from_actual_receipts_and_keeps_contract_unchanged(monkeypatch):
    from workbench.services import research_trace
    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: None)
    runner, agent, sent, closed = discovery_runner([plan("foundational terminology"), plan("competing theorem")])
    before = json.dumps(runner.task.contract, sort_keys=True)
    searches = []
    campaign = SimpleNamespace(body={})
    manuscript_acquisition.discover(runner, campaign, searches,
        lambda query: searches.append({**query, "status": "completed", "results": [{"title": "Prior work"}]}))
    assert len(searches) == 2 and len(campaign.body["discovery_plans"]) == 2
    assert sent[0]["search_receipts"] == []
    assert sent[1]["search_receipts"][0]["results"] == [{"title": "Prior work"}]
    assert all(r["origin"] == "agent" and r["plan_sha256"] for r in searches)
    assert json.dumps(runner.task.contract, sort_keys=True) == before
    assert closed and agent.state == "completed"


@pytest.mark.parametrize("invalid", ["duplicate", "repeat", "too_many", "count"])
def test_invalid_discovery_plan_cannot_execute_searches(monkeypatch, invalid):
    from workbench.services import research_trace
    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: None)
    proposed = plan("known")
    existing = []
    limit = 8
    if invalid == "duplicate":
        proposed["queries"] *= 2
    elif invalid == "repeat":
        existing = [{"provider": "crossref", "query": " KNOWN  "}]
    elif invalid == "too_many":
        proposed["queries"].append({"provider": "openalex", "query": "second", "count": 2})
        limit = 1
    else:
        proposed["queries"][0]["count"] = 6
    runner, _, _, closed = discovery_runner([proposed], limit=limit)
    searched = []
    with pytest.raises(ValueError):
        manuscript_acquisition.discover(runner, SimpleNamespace(body={}), existing, searched.append)
    assert not searched and closed


def test_discovery_does_not_borrow_manuscript_reserves(monkeypatch):
    from workbench.services import research_trace
    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: None)
    runner, _, sent, closed = discovery_runner([plan("unused")], tokens=124000)
    with pytest.raises(StopResearch, match="insufficient tokens"):
        manuscript_acquisition.discover(runner, SimpleNamespace(body={}), [], lambda query: pytest.fail("search"))
    assert not sent and closed


def test_bounded_discovery_offline_end_to_end_is_labelled_simulated(session, project, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("WB_DEPLOYMENT_MODE", "local")
    config.get_settings.cache_clear()
    task = research_tasks.create_task(session, project.id, TaskBrief(question="Synthetic discovery",
        task_type="manuscript", executor="offline", token_limit=240000,
        allow_public_search=True, agent_literature_discovery=True))
    research_tasks.attach(session, task, "source.txt", b"Frozen source", version="fixture")
    task.state, task.started_at = "planning", utcnow()
    session.commit()
    research_runner.run_task(task.id, threading.Event())
    session.expire_all()
    task = session.get(ResearchTask, task.id)
    campaign = session.get(ResearchObject, task.synthesis["quality"]["campaign_id"])
    assert len(campaign.body["discovery_plans"]) == 2
    receipts = campaign.body["search_receipts"]
    assert len(receipts) == 2 and all(r["status"] == "simulated" and r["origin"] == "agent" for r in receipts)
    assert not task.ledger.get("live_handoff_verified")
    assert not task.synthesis["quality"]["agent_checks_complete"]
    research_runner.shutdown()


def test_empty_discovery_plan_stops_before_next_round(monkeypatch):
    from workbench.services import research_trace
    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: None)
    empty = plan("unused")
    empty["queries"] = []
    runner, agent, sent, closed = discovery_runner([empty])
    manuscript_acquisition.discover(runner, SimpleNamespace(body={}), [],
                                   lambda query: pytest.fail("unexpected search"))
    assert len(sent) == 1 and closed and agent.state == "completed"


def test_discovery_cancellation_closes_worker_without_dispatch(monkeypatch):
    from workbench.services import research_trace
    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: None)
    runner, _, sent, closed = discovery_runner([plan("unused")])

    def cancelled():
        raise StopResearch("cancelled", "controlled cancellation")

    runner.check = cancelled
    with pytest.raises(StopResearch, match="controlled cancellation"):
        manuscript_acquisition.discover(runner, SimpleNamespace(body={}), [],
                                       lambda query: pytest.fail("unexpected search"))
    assert not sent and closed


def test_search_receipt_caps_excess_provider_results(session, project, tmp_path, monkeypatch):
    from workbench.services import literature, research_trace
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "artifacts"))
    config.get_settings.cache_clear()
    monkeypatch.setattr(research_trace, "record", lambda *args, **kw: None)
    works = [SimpleNamespace(title=f"Work {i}", authors=[], year=2020, doi="", url="", provider_id=str(i))
             for i in range(7)]

    class ExcessResults:
        last_error = None
        _session = None

        def __init__(self, **kwargs):
            pass

        def search(self, *args, **kwargs):
            return works

    monkeypatch.setattr(manuscript_acquisition, "CrossrefAdapter", ExcessResults)
    monkeypatch.setattr(literature, "import_work", lambda s, pid, w: (
        SimpleNamespace(id=w.provider_id, access="metadata_only"), True))
    runner = SimpleNamespace(session=session, research_deadline=time.monotonic() + 60,
        check=lambda: None, task=SimpleNamespace(id="controlled", project_id=project.id,
        contract={"executor": "process", "allow_public_search": True,
                  "literature_queries": [{"provider": "crossref", "query": "topic", "count": 2}]}))
    campaign = SimpleNamespace(body={})
    manuscript_acquisition.collect(runner, SimpleNamespace(body={"source_ids": []}), campaign)
    receipt = campaign.body["search_receipts"][0]
    assert receipt["status"] == "completed" and len(receipt["results"]) == 2
    assert [r["source_id"] for r in receipt["results"]] == ["0", "1"]


@pytest.mark.parametrize("role,model,effort", [
    ("proof_method", "gpt-6-astra", "xhigh"),
    ("source_citation", "gpt-6-astra", "high"), ("author", "gpt-5.5", "low"),
])
def test_executor_passes_operator_role_and_policy_to_separate_worker(monkeypatch, role, model, effort):
    import sys
    from workbench.providers import research_executor
    captured = []
    settings = SimpleNamespace(deployment_mode="local", research_executor_enabled=True,
        research_executor_command=[sys.executable, "controlled.py"], research_codex_home="",
        research_codex_account_email="", research_codex_model="gpt-5.5",
        research_codex_reasoning_effort="low", research_codex_role_policy=default_role_policy())
    monkeypatch.setattr(research_executor, "get_settings", lambda: settings)
    caps = {"protocol": "research-process-v1", "executor": "controlled", "simulated": False,
            "child_agents": True, "structured_reports": True, "hard_total_token_limit": True,
            "bounded_wall_time": True, "no_external_writes": True}

    def process(command, identifier, environment):
        captured.append(environment)
        return SimpleNamespace(send=lambda *args: None, poll=lambda: {
            "type": "capabilities", "worker_pid": 123, "capabilities": caps})

    monkeypatch.setattr(research_executor, "AgentProcess", process)
    executor = research_executor.ProcessResearchExecutor("process")
    handle = executor.spawn("independent-worker", deadline=time.monotonic() + 10, role=role)
    assert captured[0]["WB_RESEARCH_CODEX_ROLE"] == role
    assert json.loads(captured[0]["WB_RESEARCH_CODEX_ROLE_POLICY"]) == default_role_policy()
    assert handle.requested_model_policy == {"role": role, "model": model, "reasoning_effort": effort}


@pytest.mark.parametrize("flags", [
    ["--allow-public-discovery"], ["--manuscript-finite-partitions", "--narrow-lifting-one-source"],
])
def test_acceptance_rejects_invalid_live_scope_before_setup(tmp_path, flags):
    import subprocess
    import sys
    from pathlib import Path
    script = Path(__file__).parents[1] / "scripts/research_live_acceptance.py"
    output = tmp_path / "must-not-exist"
    result = subprocess.run([sys.executable, str(script), str(output), "--profile", str(tmp_path),
                             "--confirm-chatgpt-plan", *flags], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert not output.exists()
