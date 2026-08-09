"""Model resolution probe helper — offline scaffolding (no live provider calls)."""

from __future__ import annotations

from tools.self_improvement_v2.agent_runtime_contract import IMPLEMENTER_MODEL, REVIEWER_MODEL
from tools.self_improvement_v2.model_resolution_probe import (
    build_model_resolution_probe,
    interpret_resolution_result,
    offline_fake_transport,
    run_model_resolution_probe,
    scriptable_interface_help,
)


def test_build_pins_implementer_and_reviewer() -> None:
    impl = build_model_resolution_probe("implementer")
    rev = build_model_resolution_probe("reviewer")
    assert impl.model == IMPLEMENTER_MODEL
    assert rev.model == REVIEWER_MODEL
    assert impl.max_output_tokens >= 1
    assert impl.to_dict()["call_params"]["max_output_tokens"] == impl.max_output_tokens


def test_run_with_fake_transport_success() -> None:
    req = build_model_resolution_probe("implementer")
    result = run_model_resolution_probe(req, transport=offline_fake_transport())
    assert result.resolved is True
    assert result.authenticated is True
    guidance = interpret_resolution_result(result)
    assert guidance["verdict"] == "CONTINUE"


def test_run_with_fake_transport_unresolved() -> None:
    req = build_model_resolution_probe("reviewer")
    result = run_model_resolution_probe(
        req,
        transport=offline_fake_transport(resolved=False, error="404 model not found"),
    )
    guidance = interpret_resolution_result(result)
    assert guidance["verdict"] == "PROJECT_BLOCKED"
    assert "MODEL_UNRESOLVED" in guidance["blocker"]


def test_scriptable_interface_documents_budget_gate() -> None:
    help_text = scriptable_interface_help()
    assert "provider-call-permit" in help_text["budget"]
    assert "transport" in help_text["run"]
