"""Executable pilot budget enforcement: call permits, cost-by-construction, wall clock.

n8n (or any caller) must request a provider-call permit from the worker before each
provider invocation. The worker owns the counters and refuses the 7th call.
Repair limits remain in repair_policy — this module does not authorize risk.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

MAXIMUM_PILOT_COST_USD = 5.0
MAXIMUM_AGENT_CALLS = 6
PILOT_TIMEOUT_MINUTES = 30
PILOT_TIMEOUT_SECONDS = PILOT_TIMEOUT_MINUTES * 60

# Conservative default rate card (USD per token). Callers may supply tighter prices;
# construction always uses the provided rates × configured token ceilings × MAX_CALLS.
DEFAULT_PRICE_PER_INPUT_TOKEN_USD = 5.0e-6  # $5 / 1M tokens
DEFAULT_PRICE_PER_OUTPUT_TOKEN_USD = 1.5e-5  # $15 / 1M tokens

DEFAULT_MAX_INPUT_TOKENS = 8_000
DEFAULT_MAX_OUTPUT_TOKENS = 2_000


class BudgetError(WorkerError):
    def __init__(self, message: str, *, code: str | None = None, state: str = "POLICY_REJECTED") -> None:
        super().__init__(code or ERROR_CODES["PILOT_BUDGET_EXCEEDED"], message, state=state)


def worst_case_cost_usd(
    *,
    max_input_tokens: int,
    max_output_tokens: int,
    price_per_input_token_usd: float,
    price_per_output_token_usd: float,
    max_calls: int = MAXIMUM_AGENT_CALLS,
) -> float:
    if max_input_tokens < 0 or max_output_tokens < 0:
        raise BudgetError("token ceilings must be non-negative", code=ERROR_CODES["PILOT_BUDGET_INVALID"])
    if max_calls < 1:
        raise BudgetError("max_calls must be >= 1", code=ERROR_CODES["PILOT_BUDGET_INVALID"])
    if price_per_input_token_usd < 0 or price_per_output_token_usd < 0:
        raise BudgetError("prices must be non-negative", code=ERROR_CODES["PILOT_BUDGET_INVALID"])
    per_call = (
        max_input_tokens * price_per_input_token_usd
        + max_output_tokens * price_per_output_token_usd
    )
    return float(max_calls) * per_call


def assert_cost_by_construction(
    *,
    max_input_tokens: int,
    max_output_tokens: int,
    price_per_input_token_usd: float,
    price_per_output_token_usd: float,
    max_calls: int = MAXIMUM_AGENT_CALLS,
    max_cost_usd: float = MAXIMUM_PILOT_COST_USD,
) -> float:
    """Fail closed before any provider call when the constructed upper bound >= cap."""
    if max_output_tokens < 1:
        raise BudgetError(
            "max_output_tokens must be set (>= 1) for cost-by-construction",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    worst = worst_case_cost_usd(
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        price_per_input_token_usd=price_per_input_token_usd,
        price_per_output_token_usd=price_per_output_token_usd,
        max_calls=max_calls,
    )
    if worst >= max_cost_usd:
        raise BudgetError(
            f"cost-by-construction {worst:.6f} USD >= cap {max_cost_usd} USD",
            code=ERROR_CODES["PILOT_COST_BOUND"],
        )
    return worst


def provider_call_params_with_token_ceiling(
    params: dict[str, Any] | None,
    *,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Ensure max_output_tokens is present on provider call parameters where applicable."""
    if max_output_tokens < 1:
        raise BudgetError(
            "max_output_tokens required on provider calls",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    out = dict(params or {})
    out["max_output_tokens"] = int(max_output_tokens)
    # Common provider aliases — set only when absent so callers can pin one name.
    out.setdefault("maxOutputTokens", int(max_output_tokens))
    out.setdefault("max_tokens", int(max_output_tokens))
    return out


@dataclass
class PilotBudgetSession:
    session_id: str
    started_at_monotonic: float
    max_calls: int = MAXIMUM_AGENT_CALLS
    max_cost_usd: float = MAXIMUM_PILOT_COST_USD
    timeout_seconds: int = PILOT_TIMEOUT_SECONDS
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    price_per_input_token_usd: float = DEFAULT_PRICE_PER_INPUT_TOKEN_USD
    price_per_output_token_usd: float = DEFAULT_PRICE_PER_OUTPUT_TOKEN_USD
    worst_case_usd: float = 0.0
    calls_granted: int = 0
    closed: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def calls_remaining(self) -> int:
        return max(0, self.max_calls - self.calls_granted)


class PilotBudgetRegistry:
    """Process-local permit registry for the loopback worker."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, PilotBudgetSession] = {}
        self._clock = clock or time.monotonic

    def open_session(
        self,
        *,
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        price_per_input_token_usd: float = DEFAULT_PRICE_PER_INPUT_TOKEN_USD,
        price_per_output_token_usd: float = DEFAULT_PRICE_PER_OUTPUT_TOKEN_USD,
        max_calls: int = MAXIMUM_AGENT_CALLS,
        max_cost_usd: float = MAXIMUM_PILOT_COST_USD,
        timeout_seconds: int = PILOT_TIMEOUT_SECONDS,
        session_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> PilotBudgetSession:
        worst = assert_cost_by_construction(
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            price_per_input_token_usd=price_per_input_token_usd,
            price_per_output_token_usd=price_per_output_token_usd,
            max_calls=max_calls,
            max_cost_usd=max_cost_usd,
        )
        sid = session_id or f"budget-{uuid.uuid4().hex[:16]}"
        session = PilotBudgetSession(
            session_id=sid,
            started_at_monotonic=self._clock(),
            max_calls=max_calls,
            max_cost_usd=max_cost_usd,
            timeout_seconds=timeout_seconds,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            price_per_input_token_usd=price_per_input_token_usd,
            price_per_output_token_usd=price_per_output_token_usd,
            worst_case_usd=worst,
            meta=dict(meta or {}),
        )
        with self._lock:
            if sid in self._sessions:
                raise BudgetError("budget session already exists", code=ERROR_CODES["PILOT_BUDGET_INVALID"])
            self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> PilotBudgetSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise BudgetError("unknown budget session", code=ERROR_CODES["PILOT_BUDGET_INVALID"])
        return session

    def request_call_permit(
        self,
        session_id: str,
        *,
        max_output_tokens: int | None = None,
        max_input_tokens: int | None = None,
        call_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Grant one provider-call permit or refuse (7th call, clock, closed session)."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise BudgetError("unknown budget session", code=ERROR_CODES["PILOT_BUDGET_INVALID"])
            if session.closed:
                raise BudgetError("budget session closed", code=ERROR_CODES["PILOT_BUDGET_EXCEEDED"])

            elapsed = self._clock() - session.started_at_monotonic
            if elapsed > session.timeout_seconds:
                session.closed = True
                raise BudgetError(
                    f"pilot wall-clock exceeded ({session.timeout_seconds}s)",
                    code=ERROR_CODES["PILOT_WALL_CLOCK"],
                )

            if session.calls_granted >= session.max_calls:
                raise BudgetError(
                    f"provider call refused: max calls ({session.max_calls}) exhausted",
                    code=ERROR_CODES["PILOT_CALL_LIMIT"],
                )

            out_tokens = int(max_output_tokens if max_output_tokens is not None else session.max_output_tokens)
            in_tokens = int(max_input_tokens if max_input_tokens is not None else session.max_input_tokens)
            if out_tokens > session.max_output_tokens or in_tokens > session.max_input_tokens:
                raise BudgetError(
                    "call token ceiling exceeds session construction bounds",
                    code=ERROR_CODES["PILOT_COST_BOUND"],
                )
            # Re-check construction for this call's ceilings against remaining budget.
            remaining_calls = session.max_calls - session.calls_granted
            remaining_budget = session.max_cost_usd - (
                session.calls_granted
                * (
                    session.max_input_tokens * session.price_per_input_token_usd
                    + session.max_output_tokens * session.price_per_output_token_usd
                )
            )
            this_call_worst = (
                in_tokens * session.price_per_input_token_usd
                + out_tokens * session.price_per_output_token_usd
            )
            if this_call_worst > remaining_budget + 1e-12:
                raise BudgetError(
                    "call refused: constructed cost exceeds remaining pilot budget",
                    code=ERROR_CODES["PILOT_COST_BOUND"],
                )
            _ = remaining_calls  # clarity for reviewers; counter is authoritative

            session.calls_granted += 1
            permit_number = session.calls_granted
            bounded_params = provider_call_params_with_token_ceiling(call_params, max_output_tokens=out_tokens)
            return {
                "status": "GRANTED",
                "session_id": session.session_id,
                "permit_number": permit_number,
                "calls_granted": session.calls_granted,
                "calls_remaining": session.calls_remaining,
                "max_calls": session.max_calls,
                "max_output_tokens": out_tokens,
                "max_input_tokens": in_tokens,
                "wall_clock_remaining_seconds": max(0, int(session.timeout_seconds - elapsed)),
                "provider_call_params": bounded_params,
                "worst_case_session_usd": session.worst_case_usd,
            }

    def close(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.closed = True


# Module-level registry used by the runtime bridge (tests may replace).
_DEFAULT_REGISTRY = PilotBudgetRegistry()


def default_registry() -> PilotBudgetRegistry:
    return _DEFAULT_REGISTRY


def reset_default_registry_for_tests(*, clock: Callable[[], float] | None = None) -> PilotBudgetRegistry:
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = PilotBudgetRegistry(clock=clock)
    return _DEFAULT_REGISTRY
