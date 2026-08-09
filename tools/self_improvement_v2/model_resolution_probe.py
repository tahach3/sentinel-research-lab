"""Model resolution probe helper (P1/P2) — offline-testable scaffolding.

Live provider calls are operator runtime steps. This module builds the minimal
call contract (model pin, max_output_tokens, permit-ready params) and executes
through an injected transport so unit tests never need network/secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from tools.self_improvement_v2.agent_runtime_contract import (
    IMPLEMENTER_MODEL,
    IMPLEMENTER_PROVIDER,
    REVIEWER_MODEL,
    REVIEWER_PROVIDER,
)
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.pilot_budget import provider_call_params_with_token_ceiling

Role = Literal["implementer", "reviewer"]

DEFAULT_PROBE_PROMPT = "ping"
DEFAULT_MAX_OUTPUT_TOKENS = 8
DEFAULT_MAX_INPUT_TOKENS = 64


class ModelResolutionProbeError(WorkerError):
    def __init__(self, message: str) -> None:
        super().__init__(ERROR_CODES["MODEL_RESOLUTION_PROBE"], message, state="POLICY_REJECTED")


@dataclass(frozen=True)
class ModelResolutionRequest:
    role: Role
    provider: str
    model: str
    prompt: str = DEFAULT_PROBE_PROMPT
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    call_params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        params = provider_call_params_with_token_ceiling(
            dict(self.call_params),
            max_output_tokens=self.max_output_tokens,
        )
        return {
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "prompt": self.prompt,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "call_params": params,
        }


@dataclass(frozen=True)
class ModelResolutionResult:
    role: Role
    provider: str
    model: str
    resolved: bool
    authenticated: bool
    output_text: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "resolved": self.resolved,
            "authenticated": self.authenticated,
            "output_nonempty": bool(self.output_text.strip()),
            "error": self.error,
        }


Transport = Callable[[ModelResolutionRequest], ModelResolutionResult]


def build_model_resolution_probe(role: Role) -> ModelResolutionRequest:
    if role == "implementer":
        return ModelResolutionRequest(
            role="implementer",
            provider=IMPLEMENTER_PROVIDER,
            model=IMPLEMENTER_MODEL,
        )
    if role == "reviewer":
        return ModelResolutionRequest(
            role="reviewer",
            provider=REVIEWER_PROVIDER,
            model=REVIEWER_MODEL,
        )
    raise ModelResolutionProbeError(f"unknown probe role: {role}")


def run_model_resolution_probe(
    request: ModelResolutionRequest,
    *,
    transport: Transport,
) -> ModelResolutionResult:
    """Execute via injected transport. Live HTTP is an operator step, not default."""
    if transport is None:
        raise ModelResolutionProbeError("transport required (no implicit live network)")
    result = transport(request)
    if not isinstance(result, ModelResolutionResult):
        raise ModelResolutionProbeError("transport must return ModelResolutionResult")
    if result.model != request.model:
        raise ModelResolutionProbeError("transport mutated model pin")
    return result


def interpret_resolution_result(result: ModelResolutionResult) -> dict[str, Any]:
    """Map a result to Zone P pass/block guidance (offline)."""
    if not result.resolved or not result.authenticated or not result.output_text.strip():
        return {
            "verdict": "PROJECT_BLOCKED",
            "blocker": f"MODEL_UNRESOLVED - {result.role} model={result.model}",
            "error": result.error or "unresolved_or_empty",
        }
    return {
        "verdict": "CONTINUE",
        "blocker": None,
        "error": None,
    }


def offline_fake_transport(
    *,
    resolved: bool = True,
    authenticated: bool = True,
    output_text: str = "ok",
    error: str | None = None,
) -> Transport:
    def _transport(req: ModelResolutionRequest) -> ModelResolutionResult:
        return ModelResolutionResult(
            role=req.role,
            provider=req.provider,
            model=req.model,
            resolved=resolved,
            authenticated=authenticated,
            output_text=output_text if resolved and authenticated else "",
            error=error,
        )

    return _transport


def scriptable_interface_help() -> dict[str, str]:
    """Document the operator-facing interface without embedding secrets."""
    return {
        "build": "build_model_resolution_probe('implementer'|'reviewer')",
        "run": "run_model_resolution_probe(request, transport=...)",
        "live_note": (
            "Supply a transport that performs the minimal provider call with "
            "request.call_params (includes max_output_tokens). Do not substitute model IDs."
        ),
        "budget": "Obtain a /v2/provider-call-permit before the live transport call",
    }
