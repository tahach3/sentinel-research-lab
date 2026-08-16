"""Structural workflow validator tests — graph edges, not marker text."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.workflow_validator import validate_workflow


def _load() -> tuple[Path, Path, dict]:
    root = worker_package_root()
    path = root / "workflows/design/self_improvement_loop_v2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return root, path, data


def _validate_data(root: Path, data: dict, tmp_path: Path) -> dict:
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return validate_workflow(root, path)


def _codes(report: dict) -> set[str]:
    return {e["code"] for e in report["errors"]}


def test_workflow_inactive_with_real_failure_graph():
    root, path, data = _load()
    report = validate_workflow(root, path)
    assert report["status"] == "PASS", report["errors"]
    assert data.get("active") is False
    assert "Failure Router" in report["nodes"]
    assert "Worker Decision Router" in report["nodes"]
    assert report["graph"]["failure_router_outputs"]["3"] == "Terminal CONTENT_BINDING_MISMATCH"
    assert report["graph"]["worker_decision_outputs"]["0"] == "Worker AUTHORIZED Continue"


def test_mutation_remove_worker_failure_edge(tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated["connections"]["Detached Worker Execute"]["main"] = [
        mutated["connections"]["Detached Worker Execute"]["main"][0]
    ]
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"] in _codes(report)


def test_mutation_remove_review_failure_edge(tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated["connections"]["Independent Review Bind"]["main"] = [
        mutated["connections"]["Independent Review Bind"]["main"][0]
    ]
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"] in _codes(report)


def test_mutation_route_decision_required_to_worker(tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated["connections"]["Worker Decision Router"]["main"][1] = [
        {"node": "Worker AUTHORIZED Continue", "type": "main", "index": 0}
    ]
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    codes = _codes(report)
    assert (
        ERROR_CODES["SI2-WF-AUTOAUTH-NONLOW"] in codes
        or ERROR_CODES["SI2-WF-INVALID-RISK-ROUTE"] in codes
    )


def test_mutation_route_policy_rejected_to_worker(tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated["connections"]["Worker Decision Router"]["main"][2] = [
        {"node": "Detached Worker Execute", "type": "main", "index": 0}
    ]
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert (
        ERROR_CODES["SI2-WF-INVALID-RISK-ROUTE"] in _codes(report)
        or ERROR_CODES["SI2-WF-AUTOAUTH-NONLOW"] in _codes(report)
    )


def test_mutation_remove_content_binding_route(tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated["connections"]["Failure Router"]["main"][3] = []
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert ERROR_CODES["SI2-WF-DISCONNECTED-FAILURE-STATE"] in _codes(report)


def test_mutation_marker_only_failure_router(tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    for node in mutated["nodes"]:
        if node.get("name") == "Failure Router":
            node["type"] = "n8n-nodes-base.code"
            node["parameters"] = {
                "jsCode": (
                    "// failure routes: POLICY_REJECTED VALIDATION_FAILED REVIEW_FAILED "
                    "CONTENT_BINDING_MISMATCH REPAIR_LIMIT_REACHED FAILED_FROZEN "
                    "PATCH_REJECTED BASELINE_MISMATCH IMMUTABILITY_VIOLATION\nreturn items;"
                )
            }
            node.pop("onError", None)
            break
    mutated["connections"]["Failure Router"] = {"main": [[]]}
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    codes = _codes(report)
    assert ERROR_CODES["SI2-WF-MARKER-NOT-ROUTE"] in codes


def test_malformed_worker_port_is_structured_fail(tmp_path: Path):
    """Non-numeric / out-of-range ports must not raise raw ValueError (NP-5)."""
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated.setdefault("meta", {})["localWorkerBaseUrl"] = "http://127.0.0.1:8765x"
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"] in _codes(report)
    assert all("ValueError" not in str(e) for e in report["errors"])

    mutated2 = copy.deepcopy(data)
    for node in mutated2["nodes"]:
        if node.get("name") == "Open Pilot Budget":
            node.setdefault("parameters", {})["url"] = "http://127.0.0.1:99999/v2/budget/open"
            break
    report2 = _validate_data(root, mutated2, tmp_path)
    assert report2["status"] == "FAIL"
    assert ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"] in _codes(report2)


def test_parse_strict_structured_credential_key_rejected(tmp_path: Path):
    """{"apiKey": "sk-…"} must FAIL — keys are not discarded (Codex NP-2)."""
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    for node in mutated["nodes"]:
        if node.get("name") == "Candidate Intake":
            node.setdefault("parameters", {})["apiKey"] = "sk-probe-12345678901234567890"
            break
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert ERROR_CODES["CREDENTIALS_IN_WORKFLOW"] in _codes(report)


def test_parse_strict_credential_inline_string_still_rejected(tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    for node in mutated["nodes"]:
        if node.get("name") == "Candidate Intake":
            node.setdefault("parameters", {})["jsCode"] = 'const x = "apiKey=\'sk-abcdefghijklmnop\'";'
            break
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert ERROR_CODES["CREDENTIALS_IN_WORKFLOW"] in _codes(report)


def test_parse_strict_malformed_channel_body_object_rejected(tmp_path: Path):
    """Non-list channel body must REJECT, not disappear (Codex NP-4)."""
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated.setdefault("connections", {}).setdefault("Implementer Agent", {})["ai_tool"] = {
        "rogue": True
    }
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert any("malformed connection channel body" in e["message"] for e in report["errors"])


@pytest.mark.parametrize(
    "body",
    ["not-a-list", 42, None, True],
)
def test_parse_strict_malformed_channel_body_types_rejected(body: object, tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated.setdefault("connections", {}).setdefault("Implementer Agent", {})["ai_memory"] = body
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert any("malformed connection channel body" in e["message"] for e in report["errors"])


def test_parse_strict_malformed_link_and_outputs_rejected(tmp_path: Path):
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    # outputs slot is a dict instead of a list of links
    mutated["connections"]["Manual Trigger"]["main"] = [{"node": "Candidate Intake"}]
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert any("malformed connection outputs" in e["message"] for e in report["errors"])

    mutated2 = copy.deepcopy(data)
    mutated2["connections"]["Manual Trigger"]["main"] = [["not-a-link-object"]]
    report2 = _validate_data(root, mutated2, tmp_path)
    assert report2["status"] == "FAIL"
    assert any("malformed connection link" in e["message"] for e in report2["errors"])


def test_parse_strict_extra_unconnected_code_node_rejected(tmp_path: Path):
    """Rogue unconnected executable node must FAIL node-set closure (Codex NP-3)."""
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated["nodes"].append(
        {
            "id": "rogue-code-node",
            "name": "Rogue Code",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [0, 0],
            "parameters": {"jsCode": "return items;"},
        }
    )
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert any("extra closed-world node rejected: Rogue Code" in e["message"] for e in report["errors"])


def test_parse_strict_unknown_channel_name_still_rejected(tmp_path: Path):
    """Well-formed invent channel remains deny-by-default (prior repair still holds)."""
    root, _path, data = _load()
    mutated = copy.deepcopy(data)
    mutated.setdefault("connections", {}).setdefault("Implementer Gemini Chat Model", {})[
        "ai_widget"
    ] = [[{"node": "Implementer Agent", "type": "ai_widget", "index": 0}]]
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "FAIL"
    assert any("unknown connection channel rejected: ai_widget" in e["message"] for e in report["errors"])


def test_parse_strict_design_workflow_still_passes():
    root, path, _data = _load()
    report = validate_workflow(root, path)
    assert report["status"] == "PASS", report["errors"]


def test_positive_control_design_passes_both_validators():
    """Blocking M7-style control: unchanged design must PASS workflow_validator + wiring."""
    from tools.self_improvement_v2.agent_runtime_contract import (
        assert_workflow_agent_wiring,
        load_design_workflow,
    )

    root, path, _data = _load()
    report = validate_workflow(root, path)
    assert report["status"] == "PASS", report["errors"]
    assert report["errors"] == []
    wiring = assert_workflow_agent_wiring(workflow=load_design_workflow(root=root), root=root)
    assert isinstance(wiring, dict)


def test_positive_control_legitimate_unusual_shapes_still_pass(tmp_path: Path):
    """Over-strict regression control: legitimate-but-unusual shapes must still PASS."""
    root, _path, data = _load()

    # optional keys absent + node with no parameters object (sticky note)
    mutated = copy.deepcopy(data)
    for node in mutated["nodes"]:
        if node.get("name") == "V2 Design Notes":
            node.pop("parameters", None)
            node.pop("disabled", None)
            node.pop("credentials", None)
            node.pop("notes", None)
            break
    report = _validate_data(root, mutated, tmp_path)
    assert report["status"] == "PASS", report["errors"]

    # null where schema allows (notes=null on sticky) + empty parameters object
    mutated2 = copy.deepcopy(data)
    for node in mutated2["nodes"]:
        if node.get("name") == "V2 Design Notes":
            node["notes"] = None
            node["parameters"] = {}
            break
    report2 = _validate_data(root, mutated2, tmp_path)
    assert report2["status"] == "PASS", report2["errors"]

    # channel present but empty ([]), and empty arrays in output slots
    mutated3 = copy.deepcopy(data)
    mutated3.setdefault("connections", {}).setdefault("V2 Design Notes", {})["main"] = []
    # trailing empty output slot on an existing main channel
    mains = mutated3["connections"]["Open Pilot Budget"]["main"]
    assert isinstance(mains, list)
    mains.append([])
    report3 = _validate_data(root, mutated3, tmp_path)
    assert report3["status"] == "PASS", report3["errors"]
