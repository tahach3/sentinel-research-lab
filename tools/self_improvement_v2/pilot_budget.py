"""Executable pilot budget enforcement: call permits, cost-by-construction, wall clock.

n8n (or any caller) must request a provider-call permit from the worker before each
provider invocation. Permits are single-use nonces bound to session, role, provider,
credential, model, and token ceilings. Consume-then-authorize is one-shot: after
assert_provider_call_authorized succeeds once, the nonce cannot authorize again.
"""

from __future__ import annotations

import math
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from tools.self_improvement_v2.agent_runtime_contract import (
    IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE,
    IMPLEMENTER_MODEL,
    IMPLEMENTER_PROVIDER,
    REVIEWER_AGENT_CREDENTIAL_REFERENCE,
    REVIEWER_MODEL,
    REVIEWER_PROVIDER,
)
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

MAXIMUM_PILOT_COST_USD = 5.0
MAXIMUM_AGENT_CALLS = 6
PILOT_TIMEOUT_MINUTES = 30
PILOT_TIMEOUT_SECONDS = PILOT_TIMEOUT_MINUTES * 60

# Immutable server-owned rate card (USD per token). Callers never set price authority.
SERVER_OWNED_PRICE_PER_INPUT_TOKEN_USD = 5.0e-6  # $5 / 1M tokens
SERVER_OWNED_PRICE_PER_OUTPUT_TOKEN_USD = 1.5e-5  # $15 / 1M tokens
# Back-compat aliases (same objects / values).
DEFAULT_PRICE_PER_INPUT_TOKEN_USD = SERVER_OWNED_PRICE_PER_INPUT_TOKEN_USD
DEFAULT_PRICE_PER_OUTPUT_TOKEN_USD = SERVER_OWNED_PRICE_PER_OUTPUT_TOKEN_USD

DEFAULT_MAX_INPUT_TOKENS = 8_000
DEFAULT_MAX_OUTPUT_TOKENS = 2_000

PERMIT_ROLES = frozenset({"implementer", "reviewer"})
TOKEN_ALIASES = ("max_output_tokens", "maxOutputTokens", "max_tokens")

ROLE_BOUND_IDENTITY: dict[str, dict[str, str]] = {
    "implementer": {
        "provider": IMPLEMENTER_PROVIDER,
        "credential_reference": IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE,
        "model": IMPLEMENTER_MODEL,
    },
    "reviewer": {
        "provider": REVIEWER_PROVIDER,
        "credential_reference": REVIEWER_AGENT_CREDENTIAL_REFERENCE,
        "model": REVIEWER_MODEL,
    },
}


class BudgetError(WorkerError):
    def __init__(self, message: str, *, code: str | None = None, state: str = "POLICY_REJECTED") -> None:
        super().__init__(code or ERROR_CODES["PILOT_BUDGET_EXCEEDED"], message, state=state)


def _reject_non_finite(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise BudgetError(
            f"{name} must be a finite number",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    number = float(value)
    if not math.isfinite(number):
        raise BudgetError(
            f"{name} must be finite (NaN/Inf rejected)",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    return number


def open_budget_hard_caps(
    *,
    max_calls: int,
    max_cost_usd: float,
    timeout_seconds: int,
    price_per_input_token_usd: float,
    price_per_output_token_usd: float,
) -> None:
    """Server-side hard caps — reject invalid maxima; never clamp zeros to defaults."""
    if not isinstance(max_calls, int) or isinstance(max_calls, bool):
        raise BudgetError(
            "max_calls must be an integer",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    if max_calls > MAXIMUM_AGENT_CALLS or max_calls < 1:
        raise BudgetError(
            f"max_calls must be 1..{MAXIMUM_AGENT_CALLS} (server hard cap)",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    cost = _reject_non_finite("max_cost_usd", max_cost_usd)
    if cost > MAXIMUM_PILOT_COST_USD or cost <= 0:
        raise BudgetError(
            f"max_cost_usd must be > 0 and <= {MAXIMUM_PILOT_COST_USD} (server hard cap)",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
        raise BudgetError(
            "timeout_seconds must be an integer",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    if timeout_seconds > PILOT_TIMEOUT_SECONDS or timeout_seconds < 1:
        raise BudgetError(
            f"timeout_seconds must be 1..{PILOT_TIMEOUT_SECONDS} (server hard cap)",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    price_in = _reject_non_finite("price_per_input_token_usd", price_per_input_token_usd)
    price_out = _reject_non_finite("price_per_output_token_usd", price_per_output_token_usd)
    if price_in <= 0 or price_out <= 0:
        raise BudgetError(
            "prices must be > 0 (zero/absurd prices that make worst_case $0 are rejected)",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )


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
    price_in = _reject_non_finite("price_per_input_token_usd", price_per_input_token_usd)
    price_out = _reject_non_finite("price_per_output_token_usd", price_per_output_token_usd)
    if price_in <= 0 or price_out <= 0:
        raise BudgetError(
            "prices must be > 0 (zero/absurd prices that make worst_case $0 are rejected)",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    per_call = max_input_tokens * price_in + max_output_tokens * price_out
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
    max_cost = _reject_non_finite("max_cost_usd", max_cost_usd)
    worst = worst_case_cost_usd(
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        price_per_input_token_usd=price_per_input_token_usd,
        price_per_output_token_usd=price_per_output_token_usd,
        max_calls=max_calls,
    )
    if worst <= 0:
        raise BudgetError(
            "cost-by-construction worst_case must be > 0",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    if worst >= max_cost:
        raise BudgetError(
            f"cost-by-construction {worst:.6f} USD >= cap {max_cost} USD",
            code=ERROR_CODES["PILOT_COST_BOUND"],
        )
    return worst


def provider_call_params_with_token_ceiling(
    params: dict[str, Any] | None,
    *,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Ensure token ceilings are present and consistent across provider aliases."""
    if max_output_tokens < 1:
        raise BudgetError(
            "max_output_tokens required on provider calls",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    out = dict(params or {})
    ceiling = int(max_output_tokens)
    conflicts = [
        key
        for key in TOKEN_ALIASES
        if key in out and int(out[key]) != ceiling
    ]
    if conflicts:
        raise BudgetError(
            f"token alias conflict for {', '.join(conflicts)} vs max_output_tokens={ceiling}",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    for key in TOKEN_ALIASES:
        out[key] = ceiling
    return out


def _server_owned_identity(role: str) -> dict[str, str]:
    identity = ROLE_BOUND_IDENTITY.get(role)
    if identity is None:
        raise BudgetError(
            f"permit role must be one of {sorted(PERMIT_ROLES)}",
            code=ERROR_CODES["PILOT_BUDGET_INVALID"],
        )
    return dict(identity)


def _bind_call_params_to_role(
    role: str,
    call_params: dict[str, Any] | None,
    *,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Overwrite provider/credential/model with server-owned role identity; reject swaps."""
    identity = _server_owned_identity(role)
    raw = dict(call_params or {})
    for key, expected in identity.items():
        if key in raw and raw[key] not in (None, "", expected):
            raise BudgetError(
                f"permit {key} mismatch vs server-owned role identity",
                code=ERROR_CODES["PILOT_PERMIT_INVALID"],
            )
    bounded = provider_call_params_with_token_ceiling(raw, max_output_tokens=max_output_tokens)
    bounded["role"] = role
    bounded["provider"] = identity["provider"]
    bounded["credential_reference"] = identity["credential_reference"]
    bounded["model"] = identity["model"]
    return bounded


@dataclass
class IssuedPermit:
    permit_nonce: str
    session_id: str
    role: str
    provider: str
    credential_reference: str
    model: str
    max_input_tokens: int
    max_output_tokens: int
    provider_call_params: dict[str, Any]
    permit_number: int
    consumed: bool = False
    authorization_spent: bool = False


@dataclass
class PilotBudgetSession:
    session_id: str
    started_at_monotonic: float
    max_calls: int = MAXIMUM_AGENT_CALLS
    max_cost_usd: float = MAXIMUM_PILOT_COST_USD
    timeout_seconds: int = PILOT_TIMEOUT_SECONDS
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    price_per_input_token_usd: float = SERVER_OWNED_PRICE_PER_INPUT_TOKEN_USD
    price_per_output_token_usd: float = SERVER_OWNED_PRICE_PER_OUTPUT_TOKEN_USD
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
        self._permits: dict[str, IssuedPermit] = {}
        self._clock = clock or time.monotonic

    def open_session(
        self,
        *,
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        price_per_input_token_usd: float | None = None,
        price_per_output_token_usd: float | None = None,
        max_calls: int = MAXIMUM_AGENT_CALLS,
        max_cost_usd: float = MAXIMUM_PILOT_COST_USD,
        timeout_seconds: int = PILOT_TIMEOUT_SECONDS,
        session_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> PilotBudgetSession:
        # Caller prices are never authoritative — validate finiteness if supplied, then ignore.
        if price_per_input_token_usd is not None:
            _reject_non_finite("price_per_input_token_usd", price_per_input_token_usd)
        if price_per_output_token_usd is not None:
            _reject_non_finite("price_per_output_token_usd", price_per_output_token_usd)
        price_in = SERVER_OWNED_PRICE_PER_INPUT_TOKEN_USD
        price_out = SERVER_OWNED_PRICE_PER_OUTPUT_TOKEN_USD
        max_cost = _reject_non_finite("max_cost_usd", max_cost_usd)
        open_budget_hard_caps(
            max_calls=max_calls,
            max_cost_usd=max_cost,
            timeout_seconds=timeout_seconds,
            price_per_input_token_usd=price_in,
            price_per_output_token_usd=price_out,
        )
        worst = assert_cost_by_construction(
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            price_per_input_token_usd=price_in,
            price_per_output_token_usd=price_out,
            max_calls=max_calls,
            max_cost_usd=max_cost,
        )
        sid = session_id or f"budget-{uuid.uuid4().hex[:16]}"
        session = PilotBudgetSession(
            session_id=sid,
            started_at_monotonic=self._clock(),
            max_calls=max_calls,
            max_cost_usd=max_cost,
            timeout_seconds=timeout_seconds,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            price_per_input_token_usd=price_in,
            price_per_output_token_usd=price_out,
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
        role: str,
        max_output_tokens: int | None = None,
        max_input_tokens: int | None = None,
        call_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue one single-use permit nonce bound to role + server-owned provider identity."""
        if role not in PERMIT_ROLES:
            raise BudgetError(
                f"permit role must be one of {sorted(PERMIT_ROLES)}",
                code=ERROR_CODES["PILOT_BUDGET_INVALID"],
            )
        identity = _server_owned_identity(role)
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

            bounded_params = _bind_call_params_to_role(
                role, call_params, max_output_tokens=out_tokens
            )
            session.calls_granted += 1
            permit_number = session.calls_granted
            nonce = secrets.token_urlsafe(24)
            issued = IssuedPermit(
                permit_nonce=nonce,
                session_id=session.session_id,
                role=role,
                provider=identity["provider"],
                credential_reference=identity["credential_reference"],
                model=identity["model"],
                max_input_tokens=in_tokens,
                max_output_tokens=out_tokens,
                provider_call_params=bounded_params,
                permit_number=permit_number,
                consumed=False,
                authorization_spent=False,
            )
            self._permits[nonce] = issued
            return {
                "status": "GRANTED",
                "session_id": session.session_id,
                "permit_number": permit_number,
                "permit_nonce": nonce,
                "role": role,
                "provider": identity["provider"],
                "credential_reference": identity["credential_reference"],
                "model": identity["model"],
                "consumed": False,
                "calls_granted": session.calls_granted,
                "calls_remaining": session.calls_remaining,
                "max_calls": session.max_calls,
                "max_output_tokens": out_tokens,
                "max_input_tokens": in_tokens,
                "wall_clock_remaining_seconds": max(0, int(session.timeout_seconds - elapsed)),
                "provider_call_params": bounded_params,
                "worst_case_session_usd": session.worst_case_usd,
            }

    def consume_call_permit(
        self,
        session_id: str,
        *,
        permit_nonce: str,
        role: str,
        provider: str | None = None,
        credential_reference: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Consume a single-use permit nonce. Required before a provider call proceeds."""
        if role not in PERMIT_ROLES:
            raise BudgetError(
                f"permit role must be one of {sorted(PERMIT_ROLES)}",
                code=ERROR_CODES["PILOT_BUDGET_INVALID"],
            )
        if not isinstance(permit_nonce, str) or not permit_nonce:
            raise BudgetError("permit_nonce required", code=ERROR_CODES["PILOT_BUDGET_INVALID"])
        identity = _server_owned_identity(role)
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
            issued = self._permits.get(permit_nonce)
            if issued is None or issued.session_id != session_id:
                raise BudgetError(
                    "unknown or unbound permit_nonce",
                    code=ERROR_CODES["PILOT_PERMIT_INVALID"],
                )
            if issued.role != role:
                raise BudgetError(
                    "permit role mismatch",
                    code=ERROR_CODES["PILOT_PERMIT_INVALID"],
                )
            for label, actual, expected in (
                ("provider", provider, identity["provider"]),
                ("credential_reference", credential_reference, identity["credential_reference"]),
                ("model", model, identity["model"]),
            ):
                if actual is not None and actual != expected:
                    raise BudgetError(
                        f"permit {label} mismatch vs server-owned role identity",
                        code=ERROR_CODES["PILOT_PERMIT_INVALID"],
                    )
            if issued.provider != identity["provider"] or issued.model != identity["model"]:
                raise BudgetError(
                    "permit identity binding mismatch",
                    code=ERROR_CODES["PILOT_PERMIT_INVALID"],
                )
            if issued.consumed:
                raise BudgetError(
                    "permit_nonce already consumed (single-use)",
                    code=ERROR_CODES["PILOT_PERMIT_CONSUMED"],
                )
            issued.consumed = True
            return {
                "status": "CONSUMED",
                "session_id": session_id,
                "permit_nonce": permit_nonce,
                "role": role,
                "provider": issued.provider,
                "credential_reference": issued.credential_reference,
                "model": issued.model,
                "permit_number": issued.permit_number,
                "provider_call_params": dict(issued.provider_call_params),
            }

    def assert_provider_call_authorized(
        self,
        session_id: str,
        *,
        role: str,
        permit_nonce: str | None = None,
        provider: str | None = None,
        credential_reference: str | None = None,
        model: str | None = None,
    ) -> None:
        """One-shot authorize: succeeds once after consume, then invalidates the nonce."""
        if role not in PERMIT_ROLES:
            raise BudgetError(
                f"permit role must be one of {sorted(PERMIT_ROLES)}",
                code=ERROR_CODES["PILOT_BUDGET_INVALID"],
            )
        identity = _server_owned_identity(role)
        with self._lock:
            if session_id not in self._sessions:
                raise BudgetError("unknown budget session", code=ERROR_CODES["PILOT_BUDGET_INVALID"])
            if not permit_nonce:
                raise BudgetError(
                    "provider call refused: permit_nonce required for one-shot authorize",
                    code=ERROR_CODES["PILOT_PERMIT_NOT_CONSUMED"],
                )
            issued = self._permits.get(permit_nonce)
            if (
                issued is None
                or issued.session_id != session_id
                or issued.role != role
                or not issued.consumed
            ):
                raise BudgetError(
                    "provider call refused: valid consumed permit_nonce required",
                    code=ERROR_CODES["PILOT_PERMIT_NOT_CONSUMED"],
                )
            if issued.authorization_spent:
                raise BudgetError(
                    "permit_nonce authorization already spent (one-shot)",
                    code=ERROR_CODES["PILOT_PERMIT_CONSUMED"],
                )
            for label, actual, expected in (
                ("provider", provider, identity["provider"]),
                ("credential_reference", credential_reference, identity["credential_reference"]),
                ("model", model, identity["model"]),
            ):
                if actual is not None and actual != expected:
                    raise BudgetError(
                        f"provider call refused: {label} mismatch",
                        code=ERROR_CODES["PILOT_PERMIT_INVALID"],
                    )
            if (
                issued.provider != identity["provider"]
                or issued.credential_reference != identity["credential_reference"]
                or issued.model != identity["model"]
            ):
                raise BudgetError(
                    "provider call refused: permit identity binding mismatch",
                    code=ERROR_CODES["PILOT_PERMIT_INVALID"],
                )
            # Atomic consume-and-authorize: this assert is the one-shot gate.
            issued.authorization_spent = True

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
