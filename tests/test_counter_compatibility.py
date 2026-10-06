"""Pure compatibility review, synthetic configuration and pre-dispatch failures."""

from types import SimpleNamespace

import pytest

from workbench.config import Settings
from workbench.providers.codex_local import runtime_overrides
from workbench.providers.counter_compatibility import CounterCompatibilityError, counter_capability
from workbench.providers.research_codex_worker import failure_metadata, settings_from_environment


@pytest.mark.parametrize(
    "model,runtime,reason",
    [
        ("gpt-5.6-sol", "0.154.0", "unreviewed_runtime"),
        ("PRIVATE_MODEL", "0.160.1", "unreviewed_model"),
        ("gpt-5.5", "PRIVATE_RUNTIME", "unreviewed_runtime"),
    ],
)
def test_review_blocks_incompatible_or_unknown_transport_without_raw_values(model, runtime, reason):
    with pytest.raises(CounterCompatibilityError) as caught:
        counter_capability(model, runtime)
    metadata = failure_metadata(caught.value)
    assert metadata["counter_failure_reason"] == reason
    assert "PRIVATE" not in str(metadata) and "PRIVATE" not in str(caught.value)


def test_compatible_review_is_separate_from_actual_invocation():
    assert counter_capability("gpt-5.6-sol", "0.160.1") == {
        "runtime_version": "0.160.1",
        "model": "gpt-5.6-sol",
        "reviewed_dispatch": "direct_namespaced_function",
        "verification": "pinned_runtime_offline",
        "successful_invocation_received": False,
    }


def test_defaults_agree_and_explicit_override_is_not_silently_changed(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_RESEARCH_CODEX_HOME", str(tmp_path))
    monkeypatch.delenv("WB_RESEARCH_CODEX_MODEL", raising=False)
    monkeypatch.delenv("WB_RESEARCH_CODEX_REASONING_EFFORT", raising=False)
    assert Settings.model_fields["research_codex_model"].default == "gpt-5.6-sol"
    assert settings_from_environment().codex_local_model == "gpt-5.6-sol"
    assert settings_from_environment().codex_local_reasoning_effort == "low"
    monkeypatch.setenv("WB_RESEARCH_CODEX_MODEL", "gpt-5.5")
    assert settings_from_environment().codex_local_model == "gpt-5.5"
    assert Settings.model_fields["codex_local_model"].default == "gpt-5.6-sol"


def test_direct_counter_namespace_is_opt_in_to_restricted_research_worker():
    selection = SimpleNamespace(codex_local_model="gpt-5.6-sol",
                                codex_local_reasoning_effort="low", codex_local_workspace_id=None)
    ordinary = runtime_overrides(selection)
    research = runtime_overrides(selection, counter_namespace=True)
    assert "features.code_mode.direct_only_tool_namespaces" not in ordinary
    assert research["features.code_mode.direct_only_tool_namespaces"] == ["paper_counter"]
    assert all(research[key] == ordinary[key] for key in ordinary)
    assert research["features.code_mode_host"] is False
    assert research["features.code_mode.enabled"] is False
    assert research["sandbox_mode"] == "read-only"


def test_mutated_error_reason_is_not_serialized():
    error = CounterCompatibilityError("unreviewed_model")
    error.reason = "PRIVATE"
    assert failure_metadata(error) == {"error_class": "CounterCompatibilityError"}


@pytest.mark.parametrize(
    "reason,stage,error_class,accepted",
    [
        ("model_requires_code_mode", "input_check", "CounterCompatibilityError", True),
        ("unreviewed_model", "input_check", "CounterCompatibilityError", True),
        ("PRIVATE", "input_check", "CounterCompatibilityError", False),
        ([], "input_check", "CounterCompatibilityError", False),
        ("unreviewed_model", "turn_stream", "CounterCompatibilityError", False),
        ("unreviewed_model", "input_check", "ValueError", False),
    ],
)
def test_controller_only_persists_bound_safe_compatibility_failure(
    monkeypatch, reason, stage, error_class, accepted
):
    from workbench.providers.research_executor import ExecutorError
    from workbench.services import research_trace
    from workbench.services.research_runner import Runner

    traces = []
    monkeypatch.setattr(research_trace, "record", lambda *args, **kwargs: traces.append(kwargs))
    runner = SimpleNamespace(usage=lambda *args: None, session=SimpleNamespace(commit=lambda: None))
    agent = SimpleNamespace(provenance={})
    event = {"type": "error", "stage": stage, "error_class": error_class, "counter_failure_reason": reason}
    with pytest.raises(ExecutorError):
        Runner.event(runner, SimpleNamespace(poll=lambda: event), agent, {"span_id": "span"}, "draft")
    assert ("worker_counter_failure_reason" in agent.provenance) is accepted
    assert ("counter_failure_reason" in traces[0]) is accepted
    assert traces[0]["span_id"] == "span" and "PRIVATE" not in str(agent.provenance)
