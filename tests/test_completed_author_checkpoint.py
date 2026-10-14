"""Invalid completed author output remains unaccepted but recoverable with bound usage."""

import json
from types import SimpleNamespace

import pytest
from test_research_codex_worker import ControlledCodexClient, prepared_worker

from workbench.providers import research_codex_worker as worker_module
from workbench.providers.research_executor import ExecutorError
from workbench.services.manuscript_quality import DraftValidationError, validate_draft
from workbench.services.research_runner import Runner


@pytest.mark.parametrize("defect,code", [
    ("section", "manuscript_duplicate_ids"),
    ("coverage", "manuscript_claim_coverage"),
    ("response", "manuscript_duplicate_responses"),
])
def test_completed_invalid_author_output_precedes_validation_failure(monkeypatch, defect, code):
    draft = {
        "title": "Bounded example", "novelty_claim": False, "limitations": ["Finite example"],
        "sections": [{"id": "s", "heading": "Example", "text": "Finite assertion.", "claim_ids": ["c"]}],
        "claims": [{"id": "c", "statement": "Finite assertion.", "kind": "method",
                    "source_ids": [], "verification_ids": []}],
        "responses": [],
    }
    if defect == "section":
        draft["sections"].append(dict(draft["sections"][0]))
    elif defect == "coverage":
        draft["sections"][0]["claim_ids"] = []
    else:
        draft["responses"] = [{"comment_id": "r", "response": "Response", "changes": "Changes"}] * 2
    output = json.dumps(draft)
    client = ControlledCodexClient()
    client.events[1]["params"]["item"]["text"] = output
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    worker = prepared_worker(client)
    worker.run("author", "draft", {"call_span_id": "span", "token_limit": 10000,
                                 "time_limit_seconds": 20})
    returned = next(fields for args, fields in emitted if args[1] == "draft")
    assert returned["provenance"]["author_schema_diagnostics"]["errors"] == [{"code": code, "path": []}]
    checkpoint = next(fields for args, fields in emitted if args[1] == "output_checkpoint")
    receipt = next(fields for args, fields in emitted if args[1] == "turn_usage_receipt")
    assert checkpoint["text"] == output and checkpoint["complete_message"] is True
    assert receipt["usage"]["tokens"] == 83 and receipt["usage"]["kind"] == "actual"
    assert returned["result"] == draft
    with pytest.raises(DraftValidationError) as error:
        validate_draft(SimpleNamespace(), SimpleNamespace(), returned["result"])
    assert error.value.issues[0]["code"] == "draft_schema"
    assert sum(method == "turn/start" for method, _ in client.calls) == 1


@pytest.mark.parametrize("wrong_binding", [False, True])
def test_completed_usage_receipt_is_bound_before_releasing_reservation(wrong_binding):
    identity = {"codex_thread_id": "thread", "codex_turn_id": "turn",
                "account_email": "fixture@example.invalid", "model": "fixture"}
    agent = SimpleNamespace(provenance={"active_model_turn": identity})
    allocation = {"span_id": "span", "phase": "revise", "reserved": 1000}
    runner = SimpleNamespace(
        task=SimpleNamespace(contract={"executor": "process"}),
        session=SimpleNamespace(commit=lambda: None), save_ledger=lambda: None,
    )
    runner.validate_result_identity = lambda *args: Runner.validate_result_identity(runner, *args)
    runner.usage = lambda *args: Runner.usage(runner, *args)
    event = {"type": "turn_usage_receipt", "call_span_id": "foreign" if wrong_binding else "span",
             "operation": "revise", "provenance": identity,
             "usage": {"tokens": 83, "kind": "actual", "source": "fixture"}}
    if wrong_binding:
        with pytest.raises(ExecutorError):
            Runner.event(runner, SimpleNamespace(poll=lambda: event), agent, allocation, "draft")
        assert "final_actual" not in allocation
    else:
        assert Runner.event(runner, SimpleNamespace(poll=lambda: event), agent, allocation, "draft") is None
        assert allocation["final_actual"] and allocation["actual_tokens"] == 83
        assert not hasattr(agent, "report")
