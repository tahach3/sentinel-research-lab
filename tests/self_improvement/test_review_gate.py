"""Independent review gate tests."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.self_improvement.helpers import load_fixture
from tools.self_improvement.models import WorkerError
from tools.self_improvement.review_gate import assert_review_pass

ROOT = Path(__file__).resolve().parents[2]


def _proposal() -> dict:
    return {
        "proposal_id": "prop-pilot-001",
        "implementer_id": "srl-implementer-agent",
        "repair_attempt": 0,
    }


def test_self_review_rejected() -> None:
    review = load_fixture("review_pass.json")
    review["independent_from_implementer"] = False
    with pytest.raises(WorkerError) as exc:
        assert_review_pass(review, proposal=_proposal(), root=ROOT)
    assert exc.value.code == "SELF_REVIEW"

    review = load_fixture("review_pass.json")
    review["reviewer_id"] = "srl-implementer-agent"
    with pytest.raises(WorkerError) as exc2:
        assert_review_pass(review, proposal=_proposal(), root=ROOT)
    assert exc2.value.code == "SELF_REVIEW"


def test_missing_independent_review_and_not_pass() -> None:
    review = load_fixture("review_pass.json")
    del review["independent_from_implementer"]
    with pytest.raises(WorkerError) as missing:
        assert_review_pass(review, proposal=_proposal(), root=ROOT)
    assert missing.value.code in {"SCHEMA_INVALID", "MISSING_INDEPENDENT_REVIEW", "SELF_REVIEW"}

    review = load_fixture("review_pass.json")
    review["verdict"] = "ESCALATE"
    with pytest.raises(WorkerError) as exc:
        assert_review_pass(review, proposal=_proposal(), root=ROOT)
    assert exc.value.code == "REVIEW_NOT_PASS"


def test_second_repair_attempt_frozen() -> None:
    review = load_fixture("review_pass.json")
    review["verdict"] = "FINITE_REPAIR"
    review["repair_instructions"] = ["fix path"]
    proposal = _proposal()
    proposal["repair_attempt"] = 1
    with pytest.raises(WorkerError) as exc:
        assert_review_pass(review, proposal=proposal, root=ROOT)
    assert exc.value.code == "REPAIR_LIMIT_REACHED"
    assert exc.value.state == "REPAIR_LIMIT_REACHED"


def test_pass_review_accepted() -> None:
    review = load_fixture("review_pass.json")
    assert_review_pass(review, proposal=_proposal(), root=ROOT)
