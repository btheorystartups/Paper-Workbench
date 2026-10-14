"""Isolated stores/controlled workers; no real inference or user database."""
import copy

import pytest
from conftest import project as project
from conftest import session as session
from test_manuscript_continuation import continue_and_wait
from test_manuscript_continuation import grant_for as original_grant_for
from test_manuscript_quality import isolated as isolated
from test_manuscript_quality import run
from workbench.models import ResearchObject, stable_hash
from workbench.services import manuscript_quality as quality
from workbench.services import research_tasks
from workbench.services.manuscript_continuation import checkpoint
from workbench.services.manuscript_local_revision import LocalCandidateGrant, admit
from workbench.services.manuscript_quality_runner import _prior
from workbench.services.research_recovery import accounting


def grant_for(session, task, **options):
    options.setdefault('specialist_policy', {r: {'model': 'gpt-6-astra', 'reasoning_effort': 'high'}
        for r in ['proof_method', 'source_citation', 'literature_contribution', 'adversarial']})
    return original_grant_for(session, task, **options)


def proposal(session, task):
    campaign = quality.campaign_for(session, task.contract['quality_manuscript_id'])
    draft = copy.deepcopy(campaign.body['drafts'][-1]['candidate'])
    draft['sections'][0]['text'] += ' This local clarification stays within the finite model.'
    draft['responses'] = [{'comment_id': c['id'], 'response': 'Local clarification proposed.',
                           'changes': 'Finite scope is explicit; independent review pending.'}
                          for c in _prior(session, campaign)]
    return LocalCandidateGrant(expected_checkpoint_sha256=checkpoint(session, task)['checkpoint_sha256'],
        expected_candidate_sha256=campaign.body['drafts'][-1]['candidate_sha256'],
        expected_raw_candidate_sha256=stable_hash(campaign.body['drafts'][-1]['candidate']),
        candidate_sha256=stable_hash(draft), candidate=draft, request_id='local-test',
        prepared_by_thread_id='local-preparer-thread',
        authorization_reason='Explicit synthetic test approval',
        acknowledge_local_revision=True)


def test_admission_is_distinct_idempotent_and_preserves_originals(session, project):
    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    campaign = quality.campaign_for(session, task.contract['quality_manuscript_id'])
    parent = next(a for a in research_tasks.agents_for(session, task.id) if a.role == 'parent')
    originals = copy.deepcopy(parent.report)
    history = copy.deepcopy(campaign.body['drafts'])
    reports = copy.deepcopy(campaign.body['reports'])
    usage = accounting(task)
    grant = proposal(session, task)
    result = admit(session, task, grant, actor='test-author')
    assert not result['idempotent']
    assert parent.report == originals and campaign.body['drafts'][:-1] == history
    assert campaign.body['reports'] == reports and accounting(task) == usage
    assert result['receipt']['worker_calls'] == 0
    assert result['checkpoint']['stage'] == 'audit'
    assert result['checkpoint']['reusable_review_roles'] == []
    assert not task.ledger['parent_integration_received']
    assert not quality.assessment(session, campaign.body['manuscript_id'])['agent_checks_complete']
    events = [copy.deepcopy(session.get(ResearchObject, rid).body['events'])
              for rid in campaign.body['rounds']]
    assert admit(session, task, grant, actor='test-author')['idempotent']
    assert events == [session.get(ResearchObject, rid).body['events'] for rid in campaign.body['rounds']]
    assert 'local-preparer-thread' in quality.author_model_threads(parent)


@pytest.mark.parametrize('defect', ['base', 'raw', 'checkpoint', 'ack', 'response', 'evidence'])
def test_admission_refuses_changed_or_unbound_inputs(session, project, defect):
    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    grant = proposal(session, task)
    if defect == 'base':
        grant.expected_candidate_sha256 = '0' * 64
    elif defect == 'raw':
        grant.candidate_sha256 = '0' * 64
    elif defect == 'checkpoint':
        grant.expected_checkpoint_sha256 = '0' * 64
    elif defect == 'ack':
        grant.acknowledge_local_revision = False
    elif defect == 'response':
        grant.candidate.responses = []
        grant.candidate_sha256 = stable_hash(grant.candidate.model_dump())
    elif defect == 'evidence':
        grant.candidate.claims[0].source_ids = ['unknown-source']
        grant.candidate_sha256 = stable_hash(grant.candidate.model_dump())
    campaign = quality.campaign_for(session, task.contract['quality_manuscript_id'])
    old = copy.deepcopy(campaign.body)
    with pytest.raises((research_tasks.TaskError, quality.DraftValidationError)):
        admit(session, task, grant, actor='test-author')
    assert campaign.body == old


def test_changed_local_receipt_blocks_checkpoint(session, project):
    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    admit(session, task, proposal(session, task), actor='test-author')
    campaign = quality.campaign_for(session, task.contract['quality_manuscript_id'])
    body = copy.deepcopy(campaign.body)
    body['drafts'][-1]['local_revision']['raw_candidate_sha256'] = '0' * 64
    campaign.body = body
    session.commit()
    with pytest.raises(research_tasks.TaskError, match='local admission receipt'):
        checkpoint(session, task)


def test_changed_idempotency_payload_is_denied(session, project):
    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    grant = proposal(session, task)
    admit(session, task, grant, actor='test-author')
    grant.authorization_reason = 'Changed payload using the same request ID'
    with pytest.raises(research_tasks.TaskError, match='reused'):
        admit(session, task, grant, actor='test-author')


def test_failed_response_admission_rolls_back_the_entire_candidate(session, project, monkeypatch):
    from workbench.services import revision_review

    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    grant = proposal(session, task)
    campaign = quality.campaign_for(session, task.contract['quality_manuscript_id'])
    original = copy.deepcopy(campaign.body)
    original_revision = task.revision

    def fail(*args, **kwargs):
        raise research_tasks.TaskError('controlled response failure')

    monkeypatch.setattr(revision_review, 'respond', fail)
    with pytest.raises(research_tasks.TaskError, match='response failure'):
        admit(session, task, grant, actor='test-author')
    session.expire_all()
    assert campaign.body == original and task.revision == original_revision
    digest = revision_review.candidate_hash(session, campaign.body['manuscript_id'])
    assert digest == grant.expected_candidate_sha256


def test_local_review_continuation_dispatches_only_audits(session, project):
    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    admit(session, task, proposal(session, task), actor='test-author')
    with pytest.raises(research_tasks.TaskError, match='review-only'):
        from workbench.services.manuscript_continuation import prepare
        prepare(session, task, grant_for(session, task, max_revision_cycles=1))
    continue_and_wait(session, task, grant_for(session, task, max_revision_cycles=0))
    assert task.state == 'completed', task.ledger.get('stop_reason')
    assert len(task.ledger['allocations']) == 4
    assert {a['phase'] for a in task.ledger['allocations']} == {'audit'}
    assert task.synthesis['integration'] == 'controller_no_model_review_handoff'
    assert task.ledger['parent_integration_received'] and task.ledger['child_handoff_received']
    assert quality.assessment(session, task.contract['quality_manuscript_id'])['agent_checks_complete']


def test_assessment_projects_hash_bound_retained_literature(session, project):
    task = run(session, project, token_limit=240000, required_literature_comparisons=['Bounded comparison'])
    campaign = quality.campaign_for(session, task.contract['quality_manuscript_id'])
    assert all('report' not in r for r in campaign.body['reports'])
    state = quality.assessment(session, campaign.body['manuscript_id'])
    assert state['literature_coverage']['current_literature_report_available']


@pytest.mark.parametrize('roles,expected_corrections,limit', [(['source_citation'], 1, 1),
    (['proof_method', 'source_citation'], 0, 1),
    (['proof_method', 'source_citation'], 2, 2)])
def test_local_format_wave_is_measured_and_limited(
        session, project, monkeypatch, roles, expected_corrections, limit):
    from workbench.services import research_runner

    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    admit(session, task, proposal(session, task), actor='test-author')
    original = research_runner.Runner.event

    def defect(self, handle, agent, allocation, expected):
        raw = original(self, handle, agent, allocation, expected)
        if (raw and expected == 'specialist_report'
                and agent.assignment.get('specialist_role') in roles
                and allocation.get('operation_kind') != 'report_correction'):
            raw['covered_section_ids'].pop()
        return raw

    monkeypatch.setattr(research_runner.Runner, 'event', defect)
    continue_and_wait(session, task, grant_for(session, task, max_revision_cycles=0,
        max_report_corrections=limit))
    assert sum(a.get('operation_kind') == 'report_correction'
               for a in task.ledger['allocations']) == expected_corrections
    assert all(a['phase'] == 'audit' for a in task.ledger['allocations'])
    if len(roles) > limit:
        assert task.state == 'limit_reached_partial'
        assert 'only one shared' in task.ledger['stop_reason']
    else:
        assert task.state == 'completed', task.ledger.get('stop_reason')


def test_operator_policy_binds_every_local_reviewer_without_changing_defaults(session, project, monkeypatch):
    from workbench.providers.research_model_policy import default_role_policy
    from workbench.services import research_runner

    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    admit(session, task, proposal(session, task), actor='test-author')
    policy = {r: {'model': 'gpt-6-astra', 'reasoning_effort': 'high'} for r in
              ['proof_method', 'source_citation', 'literature_contribution', 'adversarial']}
    selected = []
    original = research_runner.Runner.spawn

    def capture(self, agent):
        handle = original(self, agent)
        selected.append(copy.deepcopy(handle.requested_model_policy))
        return handle

    monkeypatch.setattr(research_runner.Runner, 'spawn', capture)
    continue_and_wait(session, task, grant_for(session, task, max_revision_cycles=0,
        specialist_policy=policy))
    assert task.state == 'completed', task.ledger.get('stop_reason')
    campaign = quality.campaign_for(session, task.contract['quality_manuscript_id'])
    assert len(selected) == 4 and all(r['reasoning_effort'] == 'high' for r in selected)
    for record in campaign.body['reports'][-4:]:
        assert record['packet']['operator_model_policy'] == policy[record['role']]
    assert default_role_policy()['proof_method']['reasoning_effort'] == 'xhigh'


@pytest.mark.parametrize('policy', [None,
    {'proof_method': {'model': 'gpt-6-astra', 'reasoning_effort': 'high'}}])
def test_missing_operator_policy_stops_before_review_dispatch(session, project, policy):
    from workbench.services.manuscript_continuation import prepare

    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    admit(session, task, proposal(session, task), actor='test-author')
    with pytest.raises(research_tasks.TaskError, match='policy'):
        prepare(session, task, grant_for(session, task, max_revision_cycles=0, specialist_policy=policy))


def test_different_spawned_policy_is_denied_before_any_review_turn(session, project, monkeypatch):
    from workbench.services import research_runner

    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    admit(session, task, proposal(session, task), actor='test-author')
    original = research_runner.Runner.spawn

    def wrong_policy(self, agent):
        handle = original(self, agent)
        handle.requested_model_policy = {**handle.requested_model_policy, 'reasoning_effort': 'xhigh'}
        return handle

    monkeypatch.setattr(research_runner.Runner, 'spawn', wrong_policy)
    continue_and_wait(session, task, grant_for(session, task, max_revision_cycles=0))
    assert not task.ledger['allocations']
    assert 'before model dispatch' in task.ledger['stop_reason']


@pytest.mark.parametrize('scientific_blocker', [False, True])
def test_controller_checks_only_bound_completion_after_all_science_passes(
        session, project, monkeypatch, scientific_blocker):
    from workbench.services import research_runner, revision_review
    from workbench.services.manuscript_local_revision import verify_controller_completion

    task = run(session, project, 'revise', token_limit=240000, max_revision_cycles=0)
    campaign = quality.campaign_for(session, task.contract['quality_manuscript_id'])
    comments = [{'id': 'controller_' + str(i), 'specialist_role': role,
        'objection': 'Four independent current candidate reviews are not yet provided.',
        'acceptance_criterion': 'Provide all four current independent reviews before acceptance.'}
        for i, role in enumerate([
            'proof_method', 'source_citation', 'literature_contribution', 'adversarial'])]
    comments[0]['objection'] = (
        'Completion of the four fresh reviews is not established by the controller record.')
    review = revision_review.open_round(session, campaign.body['manuscript_id'],
        comments=comments, reviewer='controlled-procedural-review')
    quality.update_campaign(campaign, rounds=[*campaign.body['rounds'], review.id])
    session.commit()
    grant = proposal(session, task)
    grant.controller_completion_comments = {c['id']: stable_hash(c) for c in comments}
    result = admit(session, task, grant, actor='test-author')
    assert not verify_controller_completion(session, task, campaign, result['receipt']['candidate_sha256'])
    original = research_runner.Runner.event

    def controlled(self, handle, agent, allocation, expected):
        raw = original(self, handle, agent, allocation, expected)
        if raw and expected == 'specialist_report':
            for response in raw['resolutions']:
                if response['comment_id'].startswith('controller_'):
                    response.update(criterion_met=False, regression_passed=True, disposition='open')
            if scientific_blocker and agent.assignment['specialist_role'] == 'proof_method':
                raw['objections'].append({'id': 'science', 'severity': 'blocking',
                    'claim_ids': [raw['assessments'][0]['claim_id']],
                    'objection': 'Unproved scientific step.',
                    'acceptance_criterion': 'Supply the missing proof.'})
        return raw

    monkeypatch.setattr(research_runner.Runner, 'event', controlled)
    continue_and_wait(session, task, grant_for(session, task, max_revision_cycles=0))
    dispositions = revision_review.dispositions(session, review)
    assert set(dispositions.values()) == ({'open'} if scientific_blocker else {'resolved'})
    for record in campaign.body['reports'][-4:]:
        agent = next(a for a in research_tasks.agents_for(session, task.id) if a.id == record['agent_id'])
        assert all(r['disposition'] == 'open' for r in agent.report['resolutions']
                   if r['comment_id'].startswith('controller_'))
    state = quality.assessment(session, campaign.body['manuscript_id'])
    assert state['agent_checks_complete'] is not scientific_blocker
