"""Structural workflow validator tests — graph edges, not marker text."""

from __future__ import annotations

import copy
import json
from pathlib import Path

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
