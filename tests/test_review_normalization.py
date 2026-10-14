"""Hash-bound conservative normalization never strengthens scientific judgments."""
import copy
from types import SimpleNamespace

import pytest

from workbench.models import stable_hash
from workbench.services.manuscript_quality_runner import _correction_grants
from workbench.services.research_recovery import (
    normalization_authority,
    normalize_review_report,
)
from workbench.services.research_runner import StopResearch
from workbench.services.research_tasks import TaskError


def report():
    return {'assessments': [{'status': 'unresolved', 'rationale': 'Unchanged science'}],
            'resolutions': [{'comment_id': 'R1', 'criterion_met': False,
                'regression_passed': True, 'evidence': 'Criterion unmet',
                'disposition': 'justified_rejection'}]}


def test_default_and_unapproved_hash_preserve_original():
    raw = report()
    assert normalize_review_report(raw, {}) == (raw, None)
    assert normalize_review_report(raw, {'a' * 64: ['R1']}) == (raw, None)


def test_approved_change_is_exact_and_original_is_immutable():
    raw, before = report(), report()
    derived, receipt = normalize_review_report(raw, {stable_hash(raw): ['R1']})
    assert raw == before and derived['resolutions'][0]['disposition'] == 'open'
    restored = copy.deepcopy(derived)
    restored['resolutions'][0]['disposition'] = 'justified_rejection'
    assert restored == raw
    assert receipt['source_report_sha256'] == stable_hash(raw)
    assert receipt['derived_report_sha256'] == stable_hash(derived)


@pytest.mark.parametrize('criterion,regression', [(False, False), (True, False), (True, True)])
def test_unapproved_boolean_combinations_cannot_be_normalized(criterion, regression):
    raw = report()
    raw['resolutions'][0].update(criterion_met=criterion, regression_passed=regression)
    with pytest.raises(TaskError):
        normalize_review_report(raw, {stable_hash(raw): ['R1']})


@pytest.mark.parametrize('ids', [[], ['missing'], ['R1', 'R1']])
def test_missing_or_duplicate_approval_denied(ids):
    raw = report()
    with pytest.raises(TaskError):
        normalize_review_report(raw, {stable_hash(raw): ids})


def test_original_normalization_authority_survives_continuation_history():
    grant = {stable_hash(report()): ['R1']}
    task = SimpleNamespace(ledger={'previous_runs': [{'ledger': {
        'continuation': {'normalization_approvals': grant}}}]})
    assert normalization_authority(task) == grant


def test_corrections_have_individual_input_and_output_grants(monkeypatch):
    from workbench.providers import research_codex_worker as worker
    monkeypatch.setattr(worker, 'json_prompt', lambda _op, payload: str(payload['packet']['input']))
    monkeypatch.setattr(worker, 'prompt_token_count', lambda text: int(text) if text.isdigit() else 10)
    child = SimpleNamespace(provenance={'report_attempts': [{'report': {}, 'report_sha256': 'a' * 64}]})
    corrections = [(child, None, {'input': 10000}, []), (child, None, {'input': 20000}, [])]
    assert _correction_grants(corrections, 80000, 50000) == [20000, 30000]
    with pytest.raises(StopResearch, match='capacity requires'):
        _correction_grants(corrections, 32000, 50000)
