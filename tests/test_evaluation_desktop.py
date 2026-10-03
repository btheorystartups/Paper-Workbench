"""Synthetic native-tool event receipts; never calls an agent or provider."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from workbench.services.evaluation import Denied, digest
from workbench.services.evaluation_desktop import DesktopDispatch


@pytest.fixture
def factory(tmp_path):
    def make(**changes):
        kwargs = dict(
            prompt="SYNTHETIC_PACKET",
            arm="qualification",
            role="initial",
            model="gpt-6-astra",
            reasoning_effort="high",
            output_kind="candidate",
            diagnostic_limits_acknowledged=True,
        )
        kwargs.update(changes)
        return DesktopDispatch(tmp_path / "stage", **kwargs)

    return make


def test_dispatch_capture_and_unknown_usage(factory):
    stage = factory()
    request = stage.begin_spawn()
    assert request["fork_turns"] == "none" and request["model"] == "gpt-6-astra"
    assert (stage._directory / "spawn-attempt.json").is_file()
    request["message"] = "mutation"
    assert "SYNTHETIC_PACKET" in json.loads((stage._directory / "spawn-request.json").read_text())["message"]
    stage.attach("/root/test_agent")
    value = stage.complete(
        observed_agent_id="/root/test_agent",
        raw_text=json.dumps({"report": "Synthetic", "candidate_tex": "SOURCE"}),
    )
    assert value["candidate_tex"] == "SOURCE"
    receipt = json.loads((stage._directory / "receipt.json").read_text())
    for name, sha in receipt["artifacts"].items():
        assert digest((stage._directory / name).read_bytes()) == sha
    completion = json.loads((stage._directory / "completion.json").read_text())
    assert completion["per_stage_credits"] is None and completion["per_stage_tokens"] is None
    assert receipt["binding"]["strict_pilot_qualified"] is False
    with pytest.raises(Denied):
        stage.begin_spawn()
    with pytest.raises(FileExistsError):
        factory()


@pytest.mark.parametrize(
    "text",
    [
        "{}",
        "not json",
        '{"report":"", "candidate_tex":"x"}',
        '{"report":"R","candidate_tex":"S","../escape":"x"}',
    ],
)
def test_invalid_result_preserved_without_candidate(factory, text):
    stage = factory()
    stage.begin_spawn()
    stage.attach("/root/test")
    with pytest.raises(Denied):
        stage.complete(observed_agent_id="/root/test", raw_text=text)
    assert stage.state == "invalid_output"
    assert (stage._directory / "raw-response.txt").read_text() == text
    assert not (stage._directory / "candidate.tex").exists()


def test_wrong_agent_cannot_promote_output(factory):
    stage = factory()
    stage.begin_spawn()
    stage.attach("/root/expected")
    with pytest.raises(Denied):
        stage.complete(observed_agent_id="/root/other", raw_text='{"report":"S","candidate_tex":"S"}')
    assert not (stage._directory / "candidate.tex").exists()


def test_pending_spawn_is_not_retried_and_stop_is_not_settlement(factory):
    stage = factory()
    stage.begin_spawn()
    with pytest.raises(Denied):
        stage.begin_spawn()
    stage.stop(reason="spawn_uncertain")
    assert stage.state == "partial"
    result = json.loads((stage._directory / "stop.json").read_text())
    assert result["remote_stop_attested"] is False and result["per_stage_credits"] is None
    with pytest.raises(Denied):
        stage.attach("/root/late")


def test_frozen_prompt_tampering_blocks_spawn(factory):
    stage = factory()
    (stage._directory / "prompt.txt").write_text("CHANGED")
    with pytest.raises(Denied):
        stage.begin_spawn()


def test_capture_failure_is_uncertain_not_free_or_retryable(factory, monkeypatch):
    stage = factory()
    stage.begin_spawn()
    stage.attach("/root/test")
    original = stage._save

    def fail(name, data):
        if name == "candidate.tex":
            raise OSError("synthetic disk failure")
        original(name, data)

    monkeypatch.setattr(stage, "_save", fail)
    with pytest.raises(OSError):
        stage.complete(observed_agent_id="/root/test", raw_text='{"report":"S","candidate_tex":"S"}')
    assert stage.state == "uncertain"
    with pytest.raises(Denied):
        stage.begin_spawn()


def test_concurrent_spawn_attempts_only_return_one_request(factory):
    stage = factory()

    def begin():
        try:
            return stage.begin_spawn()
        except Denied:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: begin(), range(2)))
    assert sum(r is not None for r in results) == 1


def test_limits_cannot_be_implicitly_accepted(factory):
    with pytest.raises(Denied):
        factory(diagnostic_limits_acknowledged=False)


def test_duplicate_json_fields_are_not_promoted(factory):
    stage = factory()
    stage.begin_spawn()
    stage.attach("/root/test")
    with pytest.raises(Denied):
        stage.complete(
            observed_agent_id="/root/test",
            raw_text='{"report":"R","candidate_tex":"FIRST","candidate_tex":"SECOND"}',
        )
    assert stage.state == "invalid_output"
    assert not (stage._directory / "candidate.tex").exists()


def test_mid_capture_tampering_prevents_acceptance_receipt(factory, monkeypatch):
    stage = factory()
    stage.begin_spawn()
    stage.attach("/root/test")
    save = stage._save

    def tamper(name, data):
        save(name, data)
        if name == "candidate.tex":
            (stage._directory / "prompt.txt").write_text("TAMPERED")

    monkeypatch.setattr(stage, "_save", tamper)
    with pytest.raises(Denied):
        stage.complete(observed_agent_id="/root/test", raw_text='{"report":"R","candidate_tex":"S"}')
    assert stage.state == "uncertain"
    assert not (stage._directory / "receipt.json").exists()


def test_receipt_failure_has_no_successful_completion_marker(factory, monkeypatch):
    stage = factory()
    stage.begin_spawn()
    stage.attach("/root/test")
    save = stage._save

    def fail(name, data):
        if name == "receipt.json":
            raise OSError("synthetic receipt failure")
        save(name, data)

    monkeypatch.setattr(stage, "_save", fail)
    with pytest.raises(OSError):
        stage.complete(observed_agent_id="/root/test", raw_text='{"report":"R","candidate_tex":"S"}')
    completion = json.loads((stage._directory / "completion.json").read_text())
    assert completion["accepted"] is False and completion["state"] == "capture_pending"
    assert stage.state == "uncertain" and not (stage._directory / "receipt.json").exists()
