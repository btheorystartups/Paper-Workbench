"""Constrained section generation preserves the retained candidate and restores references."""

import copy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_research_codex_worker import ControlledCodexClient, prepared_worker

from workbench.models import stable_hash
from workbench.providers import research_codex_worker as worker_module
from workbench.research_contract import SectionRecoveryText
from workbench.services.manuscript_quality import validate_draft


def retained():
    return {"title": "Retained case", "novelty_claim": False, "limitations": ["Finite fixture"],
            "sections": [
                {"id": "S0", "heading": "Analysis", "text": " ".join(["a"] * 6100), "claim_ids": ["C1"]},
                {"id": "S9", "heading": "References", "text": " ".join(["reference"] * 175), "claim_ids": []},
            ],
            "claims": [{"id": "C1", "statement": "A bounded case.", "kind": "method",
                        "source_ids": [], "verification_ids": []}],
            "responses": []}


SPEC = {"discussion_id": "S9", "reference_id": "S10", "discussion_heading": "Discussion"}


@pytest.mark.parametrize("count,accepted", [(999, False), (1000, True), (1300, True), (1301, False)])
def test_section_word_range_is_enforced(count, accepted):
    data = {"text": " ".join(["word"] * count), "claim_ids": ["C1"]}
    if accepted:
        assert len(SectionRecoveryText.model_validate(data).text.split()) == count
    else:
        with pytest.raises(ValidationError):
            SectionRecoveryText.model_validate(data)


def test_merge_preserves_base_and_passes_full_draft_gate():
    base = retained()
    unchanged = copy.deepcopy(base)
    result = worker_module.assemble_section_recovery(
        base, {"text": " ".join(["word"] * 1100), "claim_ids": ["C1"]}, SPEC)
    assert base == unchanged
    assert result["claims"] == base["claims"] and result["responses"] == base["responses"]
    assert result["sections"][0] == base["sections"][0]
    assert result["sections"][-1] == {**base["sections"][-1], "id": "S10"}
    task = SimpleNamespace(sources=[], contract={"paper_type": "research",
        "manuscript_length": {"min_words": 7000, "max_words": 10000,
                              "counting_policy": "section-text-whitespace-v1"}})
    campaign = SimpleNamespace(body={"verification_receipts": [],
                                     "drafts": [{"candidate": {**base, "sections": [
                                         base["sections"][0], {**base["sections"][1], "id": "S10"}]}}]})
    assert validate_draft(task, campaign, result, expected_response_ids=[])["title"] == base["title"]


def test_worker_records_generated_section_and_assembled_return(monkeypatch):
    base = retained()
    section = {"text": " ".join(["word"] * 1100), "claim_ids": ["C1"]}
    client = ControlledCodexClient()
    client.events[1]["params"]["item"]["text"] = json.dumps(section)
    worker = prepared_worker(client)
    worker.thread_id = None
    worker.ensure_thread = lambda *_args, **_kwargs: setattr(worker, "thread_id", "parent-thread")
    message = {"call_span_id": "span", "token_limit": 30000, "time_limit_seconds": 20,
               "original_draft": base, "original_draft_sha256": stable_hash(base),
               "draft_corrections": [{"code": "manuscript_length"}], "section_recovery": SPEC,
               "recovery_claim_ids": ["C1"], "expected_response_ids": []}
    message["author_return_checkpoint"] = {"checkpoint_sha256": "a" * 64,
        "draft_sha256": stable_hash(base), "evidence_sha256": worker_module.author_evidence_hash(message)}
    prompt = worker_module.json_prompt("revise", message)
    assert "ONLY the requested discussion" in prompt and "Write the COMPLETE manuscript" not in prompt
    emitted = []
    monkeypatch.setattr(worker_module, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    worker.run("author", "revise", message)
    returned = next(fields for args, fields in emitted if args[1] == "draft")
    receipt = returned["provenance"]["section_recovery"]
    assert receipt["base_draft_sha256"] == stable_hash(base)
    assert receipt["generated_section"] == section
    assert receipt["assembled_draft_sha256"] == stable_hash(returned["result"])
    assert len(returned["result"]["sections"]) == 3
    assert sum(method == "turn/start" for method, _ in client.calls) == 1
