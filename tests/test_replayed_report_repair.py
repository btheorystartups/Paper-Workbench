"""A retained invalid report must obtain a real handle before bounded correction."""
import importlib.util
import os
from types import SimpleNamespace

import pytest

from workbench.services import manuscript_quality_runner as pipeline
from workbench.services.research_recovery import ReplayHandle
from workbench.services.research_runner import StopResearch

if os.environ.get('STAGE5_RUNNER_PATCH'):
    spec = importlib.util.spec_from_file_location(
        'workbench.services.stage5_runner_patch', os.environ['STAGE5_RUNNER_PATCH'])
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)


def test_invalid_saved_review_spawns_before_correction_send(monkeypatch):
    calls = []
    child = SimpleNamespace(id='reviewer', state='completed', report={}, provenance={})
    parent = SimpleNamespace(state='waiting')
    allocation = {'span_id': 'retained', 'reserved': 1000}
    replay = ReplayHandle(child, allocation, {'invalid': True})
    packet = {'packet_sha256': 'b' * 64}
    campaign = SimpleNamespace(body={
        'reports': [], 'audit_budget_plans': [], 'rejected_reports': [], 'drafts': [{}],
    })
    live = object()

    def retained(_runner, _campaign, _digest, _iteration, accepted):
        accepted.update(pipeline.SPECIALIST_ROLES)
        return [(child, replay, allocation, packet)]

    def validate(_raw, _packet):
        raise pipeline.quality.ReportValidationError([
            {'code': 'resolution_closure', 'message': 'Controlled closure contradiction'}])

    def spawn(agent):
        calls.append(('spawn', agent.id))
        return live

    def send(handle, agent, operation, grant, payload):
        assert handle is live and handle is not replay
        assert grant >= 1000 and operation == 'audit'
        assert payload['original_report'] == {'invalid': True}
        assert payload['report_corrections'][0]['code'] == 'resolution_closure'
        calls.append(('send', agent.id))
        raise StopResearch('failed_partial', 'controlled stop before any paid dispatch')

    runner = SimpleNamespace(task=SimpleNamespace(contract={'token_limit': 200000}, state='researching'),
        agents=[child], remaining_tokens=lambda: 200000, check=lambda: None,
        session=SimpleNamespace(commit=lambda: None), spawn=spawn, send=send,
        event=lambda *_args: {'invalid': True})
    monkeypatch.setattr(pipeline, 'retained_reviews', retained)
    monkeypatch.setattr(pipeline.quality, 'validate_report', validate)
    monkeypatch.setattr(pipeline, '_revision_budget', lambda *_args: {
        'review_role_reserves': {role: 1000 for role in pipeline.SPECIALIST_ROLES},
        'repair_reserve': 1000})
    monkeypatch.setattr(pipeline.research_trace, 'record', lambda *_args, **_kwargs: None)
    with pytest.raises(StopResearch, match='controlled stop'):
        pipeline._audit_wave(runner, parent, None, campaign, 'a' * 64, 1)
    assert calls == [('spawn', child.id), ('send', child.id)]
