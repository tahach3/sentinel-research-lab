"""Phase 1B agent-runtime contract tests — offline, no live Gemini/Groq calls."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE,
    IMPLEMENTER_AGENT_ID,
    IMPLEMENTER_MODEL,
    IMPLEMENTER_PROVIDER,
    REVIEWER_AGENT_CREDENTIAL_REFERENCE,
    REVIEWER_AGENT_ID,
    REVIEWER_MODEL,
    REVIEWER_PROVIDER,
    RUNTIME_IDENTITY_INDEPENDENCE_CLAIM,
    AgentRuntimeContractError,
    assert_identity_separation,
    assert_phase_1b_contract_surface,
    assert_workflow_agent_wiring,
    assert_workflow_meta_bindings,
    lookalike_credential_reference_cases,
    pinned_agent_runtime_contract,
    reject_nonexact_credential_reference,
    validate_agent_runtime_contract,
)
from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.schema_loader import SCHEMA_FILES, load_schema, worker_package_root


def test_schema_registered_and_draft_strict():
    assert "agent_runtime_contract" in SCHEMA_FILES
    schema = load_schema("agent_runtime_contract")
    assert schema["$schema"].endswith("draft/2020-12/schema")
    assert schema.get("additionalProperties") is False


def test_pinned_contract_validates():
    payload = validate_agent_runtime_contract()
    assert payload["phase"] == "1B"
    assert payload["wiring_status"] == "WORKFLOW_WIRED"
    assert payload["inactive_by_design"] is True
    assert payload["implementer"]["model"] == IMPLEMENTER_MODEL
    assert payload["independent_reviewer"]["model"] == REVIEWER_MODEL
    assert payload["implementer"]["provider"] == IMPLEMENTER_PROVIDER
    assert payload["independent_reviewer"]["provider"] == REVIEWER_PROVIDER
    assert payload["risk_authority"]["sole_authorizer"] is True
    assert payload["risk_authority"]["module"] == "tools.self_improvement_v2.risk_authority"


def test_identity_separation_rejects_same_credential():
    payload = pinned_agent_runtime_contract()
    payload["independent_reviewer"]["credential_reference"] = payload["implementer"][
        "credential_reference"
    ]
    with pytest.raises(AgentRuntimeContractError) as exc:
        assert_identity_separation(payload)
    assert exc.value.code == ERROR_CODES["SI2-REVIEW-SELF"]


def test_identity_separation_rejects_same_agent_id():
    payload = pinned_agent_runtime_contract()
    payload["independent_reviewer"]["agent_id"] = payload["implementer"]["agent_id"]
    with pytest.raises(AgentRuntimeContractError) as exc:
        validate_agent_runtime_contract(payload)
    assert exc.value.code == ERROR_CODES["SI2-REVIEW-SELF"]


def test_secret_literal_rejected_in_contract():
    payload = pinned_agent_runtime_contract()
    payload["implementer"]["credential_reference"] = "api_key=sk-live-not-a-real-secret-value"
    with pytest.raises(AgentRuntimeContractError) as exc:
        validate_agent_runtime_contract(payload)
    assert exc.value.code == ERROR_CODES["CREDENTIALS_IN_WORKFLOW"]
    assert "sk-live-not-a-real-secret-value" not in str(exc.value)


def test_workflow_meta_bindings_match_pins():
    meta = assert_workflow_meta_bindings()
    assert meta["implementerAgentId"] == IMPLEMENTER_AGENT_ID
    assert meta["reviewerAgentId"] == REVIEWER_AGENT_ID
    assert meta["implementerAgentCredentialReference"] == IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE
    assert meta["reviewerAgentCredentialReference"] == REVIEWER_AGENT_CREDENTIAL_REFERENCE
    assert meta["implementerModel"] == IMPLEMENTER_MODEL
    assert meta["reviewerModel"] == REVIEWER_MODEL
    assert meta["agentRuntimePhase"] == "1B"
    assert meta["agentRuntimeWiringStatus"] == "WORKFLOW_WIRED"
    assert meta["srlInactiveByDesign"] is True


def test_workflow_reject_active_true(tmp_path: Path):
    root = worker_package_root()
    path = root / "workflows/design/self_improvement_loop_v2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(data)
    mutated["active"] = True
    with pytest.raises(AgentRuntimeContractError) as exc:
        assert_workflow_meta_bindings(mutated)
    assert exc.value.code == ERROR_CODES["WORKFLOW_ACTIVE"]


def test_workflow_reject_operator_placeholder():
    root = worker_package_root()
    path = root / "workflows/design/self_improvement_loop_v2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(data)
    mutated["meta"]["implementerAgentCredentialReference"] = "OPERATOR_REQUIRED"
    with pytest.raises(AgentRuntimeContractError, match="not pinned"):
        assert_workflow_meta_bindings(mutated)


def test_workflow_reject_shared_credential_refs():
    root = worker_package_root()
    path = root / "workflows/design/self_improvement_loop_v2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(data)
    mutated["meta"]["reviewerAgentCredentialReference"] = mutated["meta"][
        "implementerAgentCredentialReference"
    ]
    with pytest.raises(AgentRuntimeContractError) as exc:
        assert_workflow_meta_bindings(mutated)
    assert exc.value.code == ERROR_CODES["SI2-REVIEW-SELF"]


def test_phase_1b_surface_offline_wired_inactive():
    result = assert_phase_1b_contract_surface()
    assert result["contract"]["wiring_status"] == "WORKFLOW_WIRED"
    assert result["contract"]["phase"] == "1B"
    assert result["workflow_wiring"]["runtime_identity_independence_proven"] is False
    assert RUNTIME_IDENTITY_INDEPENDENCE_CLAIM is False
    blob = json.dumps(result)
    assert "api_key=" not in blob.lower()
    assert "bearer " not in blob.lower()
    assert "SRL_WORKER_TOKEN=" not in blob
    root = worker_package_root()
    workflow = json.loads(
        (root / "workflows/design/self_improvement_loop_v2.json").read_text(encoding="utf-8")
    )
    assert workflow.get("active") is False
    node_types = {n.get("type") for n in workflow.get("nodes") or []}
    assert "@n8n/n8n-nodes-langchain.agent" in node_types
    assert "@n8n/n8n-nodes-langchain.lmChatGoogleGemini" in node_types
    assert "@n8n/n8n-nodes-langchain.lmChatGroq" in node_types
    assert "n8n-nodes-base.httpRequest" in node_types


@pytest.mark.parametrize(
    "pinned",
    [IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE, REVIEWER_AGENT_CREDENTIAL_REFERENCE],
)
def test_credential_reference_rejects_case_whitespace_unicode_lookalikes(pinned: str):
    for variant in lookalike_credential_reference_cases(pinned):
        if variant == pinned:
            continue
        with pytest.raises(AgentRuntimeContractError, match="exact pin"):
            reject_nonexact_credential_reference(variant, pinned)


def test_workflow_meta_rejects_credential_lookalikes():
    root = worker_package_root()
    path = root / "workflows/design/self_improvement_loop_v2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for variant in lookalike_credential_reference_cases(IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE):
        if variant == IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE:
            continue
        mutated = copy.deepcopy(data)
        mutated["meta"]["implementerAgentCredentialReference"] = variant
        with pytest.raises(AgentRuntimeContractError):
            assert_workflow_meta_bindings(mutated)


def test_provider_role_model_binding_rejects_cross_assignment():
    payload = pinned_agent_runtime_contract()
    payload["implementer"]["provider"] = REVIEWER_PROVIDER
    payload["independent_reviewer"]["provider"] = IMPLEMENTER_PROVIDER
    with pytest.raises(AgentRuntimeContractError):
        validate_agent_runtime_contract(payload)

    payload = pinned_agent_runtime_contract()
    payload["implementer"]["model"] = REVIEWER_MODEL
    payload["independent_reviewer"]["model"] = IMPLEMENTER_MODEL
    with pytest.raises(AgentRuntimeContractError):
        validate_agent_runtime_contract(payload)


def test_secret_like_rejected_in_workflow_nodes():
    root = worker_package_root()
    path = root / "workflows/design/self_improvement_loop_v2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(data)
    for node in mutated["nodes"]:
        if node.get("name") == "Implementer Gemini Chat Model":
            node["credentials"]["googlePalmApi"]["name"] = (
                "api_key=sk-live-not-a-real-secret-value"
            )
            break
    with pytest.raises(AgentRuntimeContractError) as exc:
        assert_workflow_agent_wiring(mutated)
    assert exc.value.code in {
        ERROR_CODES["CREDENTIALS_IN_WORKFLOW"],
        ERROR_CODES["SI2-AGENT-RUNTIME-CONTRACT"],
    }
    assert "sk-live-not-a-real-secret-value" not in str(exc.value)


def test_unknown_role_rejected_by_schema():
    payload = pinned_agent_runtime_contract()
    payload["approver"] = {"agent_id": "srl-approver"}
    with pytest.raises(Exception):
        validate_agent_runtime_contract(payload)
