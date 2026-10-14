"""Pure regression fixtures: no provider, API, database or manuscript mutation."""
import importlib.util
import os

import pytest

from workbench.models import stable_hash
from workbench.providers.research_quality_offline import reply
from workbench.services import manuscript_quality as quality

if os.environ.get('STAGE5_QUALITY_PATCH'):
    spec = importlib.util.spec_from_file_location(
        'workbench.services.stage5_quality_patch', os.environ['STAGE5_QUALITY_PATCH'])
    quality = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality)


def fixture():
    packet = {'role': 'proof_method', 'candidate_sha256': 'a' * 64,
              'packet_sha256': 'b' * 64,
              'candidate': {'claims': [], 'sections': [], 'novelty_claim': False},
              'prior_comments': [{'id': 'R1'}], 'search_receipts': [],
              'source_manifest': [], 'verification_receipts': []}
    packet['packet_sha256'] = stable_hash({key: value for key, value in packet.items()
                                          if key != 'packet_sha256'})
    return packet, reply('audit', {'packet': packet})


@pytest.mark.parametrize('disposition', ['resolved', 'justified_rejection'])
@pytest.mark.parametrize('criterion,regression', [(False, False), (False, True), (True, False)])
def test_inconsistent_closure_enters_report_repair(disposition, criterion, regression):
    packet, report = fixture()
    report['resolutions'][0].update(disposition=disposition, criterion_met=criterion,
                                    regression_passed=regression)
    with pytest.raises(quality.ReportValidationError) as caught:
        quality.validate_report(report, packet)
    assert any(issue['code'] == 'resolution_closure' and
               issue['path'] == '/resolutions/0/disposition' for issue in caught.value.issues)


@pytest.mark.parametrize('disposition,criterion,regression', [
    ('resolved', True, True), ('justified_rejection', True, True),
    ('open', False, True), ('open', False, False), ('regressed', True, False),
])
def test_valid_dispositions_remain_unchanged(disposition, criterion, regression):
    packet, report = fixture()
    report['resolutions'][0].update(disposition=disposition, criterion_met=criterion,
                                    regression_passed=regression)
    validated, _, _ = quality.validate_report(report, packet)
    assert validated['resolutions'] == report['resolutions']


def test_blank_resolution_evidence_enters_report_repair():
    packet, report = fixture()
    report['resolutions'][0]['evidence'] = '   '
    with pytest.raises(quality.ReportValidationError) as caught:
        quality.validate_report(report, packet)
    assert any(issue['code'] == 'report_schema' for issue in caught.value.issues)
