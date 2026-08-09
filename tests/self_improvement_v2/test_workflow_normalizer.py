"""A14 workflow normalizer — four required proofs + unknown-field fail-closed."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.self_improvement_v2.agent_runtime_contract import design_workflow_path
from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.workflow_normalizer import (
    IGNORED_FIELDS,
    MATERIAL_FIELDS,
    WorkflowNormalizerError,
    assert_workflows_materially_equivalent,
    material_fingerprint,
    normalize_workflow,
    workflows_materially_equivalent,
)


@pytest.fixture()
def design_workflow() -> dict:
    path = design_workflow_path()
    return json.loads(path.read_text(encoding="utf-8"))


def test_allowlists_are_explicit() -> None:
    assert "node" in MATERIAL_FIELDS and "node" in IGNORED_FIELDS
    assert "id" in IGNORED_FIELDS["node"]
    assert "position" in IGNORED_FIELDS["node"]
    assert "name" in MATERIAL_FIELDS["node"]
    assert "type" in MATERIAL_FIELDS["node"]


def test_unknown_field_fails(design_workflow: dict) -> None:
    mutated = copy.deepcopy(design_workflow)
    mutated["unexpectedChromeField"] = True
    with pytest.raises(WorkflowNormalizerError) as exc:
        normalize_workflow(mutated)
    assert exc.value.code == ERROR_CODES["WORKFLOW_NORMALIZER"]
    assert "unknown field" in exc.value.message.lower()


def test_neg_model_id_change_fails(design_workflow: dict) -> None:
    mutated = copy.deepcopy(design_workflow)
    for node in mutated["nodes"]:
        if node.get("name") == "Implementer Gemini Chat Model":
            node["parameters"]["modelName"] = "models/gemini-1.5-flash"
            break
    else:
        pytest.fail("implementer chat model node missing")
    assert workflows_materially_equivalent(design_workflow, design_workflow)
    assert not workflows_materially_equivalent(design_workflow, mutated)
    with pytest.raises(WorkflowNormalizerError):
        assert_workflows_materially_equivalent(design_workflow, mutated)


def test_neg_credential_name_change_fails(design_workflow: dict) -> None:
    mutated = copy.deepcopy(design_workflow)
    for node in mutated["nodes"]:
        if node.get("name") == "Implementer Gemini Chat Model":
            node["credentials"]["googlePalmApi"]["name"] = "SRL Implementer — WRONG"
            break
    else:
        pytest.fail("implementer chat model node missing")
    assert not workflows_materially_equivalent(design_workflow, mutated)


def test_neg_edge_redirect_fails(design_workflow: dict) -> None:
    mutated = copy.deepcopy(design_workflow)
    # Redirect Candidate Schema Validation success edge to a failure terminal.
    edges = mutated["connections"]["Candidate Schema Validation"]["main"]
    assert edges[0][0]["node"] == "Open Pilot Budget"
    edges[0][0]["node"] = "Terminal FAILED_FROZEN"
    assert not workflows_materially_equivalent(design_workflow, mutated)


def test_pos_coords_ids_timestamps_pass(design_workflow: dict) -> None:
    mutated = copy.deepcopy(design_workflow)
    mutated["id"] = "live-instance-workflow-id"
    mutated["versionId"] = "live-version"
    mutated["updatedAt"] = "2099-01-01T00:00:00.000Z"
    mutated["createdAt"] = "2099-01-01T00:00:00.000Z"
    for i, node in enumerate(mutated["nodes"]):
        node["id"] = f"live-node-{i}"
        node["position"] = [node["position"][0] + 99, node["position"][1] + 77]
        creds = node.get("credentials")
        if isinstance(creds, dict):
            for block in creds.values():
                if isinstance(block, dict) and "id" in block:
                    block["id"] = f"live-cred-{i}"
    if isinstance(mutated.get("meta"), dict):
        mutated["meta"]["templateCredsSetupCompleted"] = True
        mutated["meta"]["agentRuntimeWiringStatus"] = "WORKFLOW_WIRED"
    assert workflows_materially_equivalent(design_workflow, mutated)
    assert material_fingerprint(design_workflow) == material_fingerprint(mutated)
    assert_workflows_materially_equivalent(design_workflow, mutated)


def test_design_workflow_normalizes(design_workflow: dict) -> None:
    norm = normalize_workflow(design_workflow)
    assert norm["active"] is False
    assert any(n["name"] == "Implementer Gemini Chat Model" for n in norm["nodes"])
    fp = material_fingerprint(design_workflow)
    assert len(fp) == 64
    # Path exists for operators comparing live exports.
    assert design_workflow_path().is_file()
    assert isinstance(Path(design_workflow_path()), Path)
