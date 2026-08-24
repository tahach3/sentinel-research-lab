import pytest

from tests.self_improvement_v2.helpers import build_proposal
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.repair_policy import assert_repair_attempt_allowed, assert_repair_not_broadening


def test_repair_broadens_paths():
    parent = build_proposal("a" * 40, allowed_paths=["docs/**"])
    repair = build_proposal(
        "a" * 40,
        proposal_id="prop-r",
        repair_attempt=1,
        parent_proposal_id=parent["proposal_id"],
        allowed_paths=["docs/**", "tools/**"],
    )
    with pytest.raises(WorkerError) as ei:
        assert_repair_not_broadening(parent, repair)
    assert ei.value.code == "REPAIR_BROADENING"


def test_repair_changes_baseline():
    parent = build_proposal("a" * 40)
    repair = build_proposal(
        "b" * 40,
        proposal_id="prop-r",
        repair_attempt=1,
        parent_proposal_id=parent["proposal_id"],
    )
    with pytest.raises(WorkerError):
        assert_repair_not_broadening(parent, repair)


def test_repair_raises_risk():
    parent = build_proposal("a" * 40, risk_level="LOW")
    repair = build_proposal(
        "a" * 40,
        proposal_id="prop-r",
        repair_attempt=1,
        parent_proposal_id=parent["proposal_id"],
        risk_level="HIGH",
    )
    with pytest.raises(WorkerError):
        assert_repair_not_broadening(parent, repair)


def test_second_repair_attempt():
    with pytest.raises(WorkerError) as ei:
        assert_repair_attempt_allowed(2)
    assert ei.value.code == "REPAIR_LIMIT_REACHED"
