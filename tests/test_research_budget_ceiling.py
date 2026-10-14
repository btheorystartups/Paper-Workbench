"""Budget boundary checks only; no model calls or persistent user data."""

import pytest
from pydantic import ValidationError

from workbench.research_contract import TaskBrief
from workbench.services.manuscript_continuation import ContinuationGrant


@pytest.mark.parametrize("tokens", [2000, 1000000, 1500000])
def test_authorized_ceiling_is_accepted(tokens):
    assert TaskBrief(question="Bounded research", token_limit=tokens).token_limit == tokens
    grant = ContinuationGrant(
        expected_checkpoint_sha256="a" * 64, token_limit=tokens,
        time_limit_seconds=7200, max_revision_cycles=1,
    )
    assert grant.token_limit == tokens
    assert not grant.acknowledge_live_execution


@pytest.mark.parametrize("tokens", [1999, 1500001])
def test_limits_outside_ceiling_are_rejected(tokens):
    with pytest.raises(ValidationError):
        TaskBrief(question="Bounded research", token_limit=tokens)
    with pytest.raises(ValidationError):
        ContinuationGrant(
            expected_checkpoint_sha256="a" * 64, token_limit=tokens,
            time_limit_seconds=7200, max_revision_cycles=1,
        )
