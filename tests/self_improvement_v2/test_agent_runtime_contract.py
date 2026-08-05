"""Phase 1A agent-runtime contract tests — offline, no live Gemini/Groq calls."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE,
    IMPLEMENTER_AGENT_ID,
    IMPLEMENTER_MODEL,
    REVIEWER_AGENT_CREDENTIAL_REFERENCE,
    REVIEWER_AGENT_ID,
    REVIEWER_MODEL,
    AgentRuntimeContractError,
    assert_identity_separation,
    assert_phase_1a_contract_surface,
    assert_workflow_meta_bindings,
    pinned_agent_runtime_contract,
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
    assert payload["phase"] == "1A"
    assert payload["wiring_status"] == "CONTRACT_ONLY"
    assert payload["inactive_by_design"] is True
    assert payload["implementer"]["model"] == IMPLEMENTER_MODEL
    assert payload["independent_reviewer"]["model"] == REVIEWER_MODEL
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


def test_workflow_meta_bindings_match_pins():
    meta = assert_workflow_meta_bindings()
    assert meta["implementerAgentId"] == IMPLEMENTER_AGENT_ID
    assert meta["reviewerAgentId"] == REVIEWER_AGENT_ID
    assert meta["implementerAgentCredentialReference"] == IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE
    assert meta["reviewerAgentCredentialReference"] == REVIEWER_AGENT_CREDENTIAL_REFERENCE
    assert meta["implementerModel"] == IMPLEMENTER_MODEL
    assert meta["reviewerModel"] == REVIEWER_MODEL
    assert meta["agentRuntimePhase"] == "1A"
    assert meta["agentRuntimeWiringStatus"] == "CONTRACT_ONLY"
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


def test_phase_1a_surface_offline():
    result = assert_phase_1a_contract_surface()
    assert result["contract"]["wiring_status"] == "CONTRACT_ONLY"
    blob = json.dumps(result)
    assert "api_key=" not in blob.lower()
    assert "bearer " not in blob.lower()
    # Stubs remain: Phase 1B not started — no langchain agent nodes required yet.
    root = worker_package_root()
    workflow = json.loads(
        (root / "workflows/design/self_improvement_loop_v2.json").read_text(encoding="utf-8")
    )
    node_types = {n.get("type") for n in workflow.get("nodes") or []}
    assert "@n8n/n8n-nodes-langchain.agent" not in node_types
