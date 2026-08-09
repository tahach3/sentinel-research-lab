"""Adversarial proofs for pilot call/cost/wall-clock budget enforcement."""

from __future__ import annotations

import pytest

from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.pilot_budget import (
    MAXIMUM_AGENT_CALLS,
    BudgetError,
    PilotBudgetRegistry,
    assert_cost_by_construction,
    provider_call_params_with_token_ceiling,
    reset_default_registry_for_tests,
)


def test_cost_by_construction_rejects_unbounded_worst_case() -> None:
    with pytest.raises(BudgetError) as exc:
        assert_cost_by_construction(
            max_input_tokens=1_000_000,
            max_output_tokens=1_000_000,
            price_per_input_token_usd=1e-3,
            price_per_output_token_usd=1e-3,
            max_calls=6,
            max_cost_usd=5.0,
        )
    assert exc.value.code == ERROR_CODES["PILOT_COST_BOUND"]


def test_cost_by_construction_requires_max_output_tokens() -> None:
    with pytest.raises(BudgetError) as exc:
        assert_cost_by_construction(
            max_input_tokens=100,
            max_output_tokens=0,
            price_per_input_token_usd=1e-6,
            price_per_output_token_usd=1e-6,
        )
    assert exc.value.code == ERROR_CODES["PILOT_BUDGET_INVALID"]


def test_provider_params_set_max_output_tokens() -> None:
    params = provider_call_params_with_token_ceiling({"temperature": 0}, max_output_tokens=256)
    assert params["max_output_tokens"] == 256
    assert params["max_tokens"] == 256


def test_seventh_provider_call_refused() -> None:
    """Adversarial proof: after 6 grants, the 7th permit is refused."""
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="pilot-budget-adv-1")
    assert session.max_calls == MAXIMUM_AGENT_CALLS
    for i in range(MAXIMUM_AGENT_CALLS):
        permit = reg.request_call_permit(session.session_id)
        assert permit["status"] == "GRANTED"
        assert permit["permit_number"] == i + 1
        assert permit["provider_call_params"]["max_output_tokens"] >= 1
    with pytest.raises(BudgetError) as exc:
        reg.request_call_permit(session.session_id)
    assert exc.value.code == ERROR_CODES["PILOT_CALL_LIMIT"]
    assert "max calls" in exc.value.message.lower() or "refused" in exc.value.message.lower()


def test_wall_clock_refuses_after_timeout() -> None:
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    reg = PilotBudgetRegistry(clock=now)
    session = reg.open_session(session_id="pilot-budget-clock", timeout_seconds=30)
    reg.request_call_permit(session.session_id)
    clock["t"] = 31.0
    with pytest.raises(BudgetError) as exc:
        reg.request_call_permit(session.session_id)
    assert exc.value.code == ERROR_CODES["PILOT_WALL_CLOCK"]


def test_open_session_fails_when_construction_exceeds_cap() -> None:
    reg = PilotBudgetRegistry()
    with pytest.raises(BudgetError) as exc:
        reg.open_session(
            session_id="too-expensive",
            max_input_tokens=500_000,
            max_output_tokens=500_000,
            price_per_input_token_usd=1e-4,
            price_per_output_token_usd=1e-4,
        )
    assert exc.value.code == ERROR_CODES["PILOT_COST_BOUND"]


def test_default_registry_reset_for_tests() -> None:
    reg = reset_default_registry_for_tests()
    session = reg.open_session(session_id="default-reg")
    assert session.calls_remaining == MAXIMUM_AGENT_CALLS
