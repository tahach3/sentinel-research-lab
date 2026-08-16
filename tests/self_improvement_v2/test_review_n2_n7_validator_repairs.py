"""Adversarial probes for Codex/Claude review findings N2–N7 (validator layer)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME,
    PROVIDER_CALL_AUTHORIZE_REVIEWER_NODE_NAME,
    PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME,
    AgentRuntimeContractError,
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.workflow_validator import validate_workflow

REPO = Path(__file__).resolve().parents[2]
WF = REPO / "workflows/design/self_improvement_loop_v2.json"


def _mutated(workflow: dict | None = None) -> dict:
    return copy.deepcopy(workflow if workflow is not None else load_design_workflow(root=REPO))


def _write_probe(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_n3_duplicate_authorize_to_agent_edge_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    edge = {"node": "Implementer Agent", "type": "main", "index": 0}
    wf["connections"][PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME]["main"][0].append(edge)
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    messages = " ".join(e["message"] for e in report["errors"])
    assert "duplicate" in messages.lower() or "extra" in messages.lower()
    with pytest.raises(AgentRuntimeContractError, match="duplicate|more than once|Authorize"):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_n4_execute_once_on_authorize_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    for node in wf["nodes"]:
        if node.get("name") == PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME:
            node["executeOnce"] = True
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    assert any("executeOnce" in e["message"] for e in report["errors"])
    with pytest.raises(AgentRuntimeContractError, match="executeOnce"):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_n4b_execute_once_on_consume_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    for node in wf["nodes"]:
        if node.get("name") == PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME:
            node["executeOnce"] = True
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    with pytest.raises(AgentRuntimeContractError, match="executeOnce"):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_n2_authorize_node_rogue_loopback_port_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    for node in wf["nodes"]:
        if node.get("name") == PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME:
            node["parameters"]["url"] = "http://127.0.0.1:59999/v2/provider-call-authorize"
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    assert any(
        "origin" in e["message"].lower() or "8765" in e["message"] or "base" in e["message"].lower()
        for e in report["errors"]
    )
    with pytest.raises(AgentRuntimeContractError, match="origin|localWorkerBaseUrl|port|path"):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_n2_worker_authorize_port_must_match_meta(tmp_path: Path) -> None:
    wf = _mutated()
    for node in wf["nodes"]:
        if node.get("name") == "Worker Authorize":
            node["parameters"]["url"] = "http://127.0.0.1:1234/v2/authorize"
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    with pytest.raises(AgentRuntimeContractError, match="origin|localWorkerBaseUrl|port|path"):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_n5_authorize_disabled_rejected_by_both_validators(tmp_path: Path) -> None:
    wf = _mutated()
    for node in wf["nodes"]:
        if node.get("name") == PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME:
            node["disabled"] = True
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    with pytest.raises(AgentRuntimeContractError, match="must not be disabled"):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_n6_authorize_retry_on_fail_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    for node in wf["nodes"]:
        if node.get("name") == PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME:
            node["retryOnFail"] = True
            node["maxTries"] = 5
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    assert any("retryOnFail" in e["message"] for e in report["errors"])
    with pytest.raises(AgentRuntimeContractError, match="retryOnFail"):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_n7_authorize_on_error_continue_regular_rejected_by_both(tmp_path: Path) -> None:
    wf = _mutated()
    for node in wf["nodes"]:
        if node.get("name") == PROVIDER_CALL_AUTHORIZE_REVIEWER_NODE_NAME:
            node["onError"] = "continueRegularOutput"
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    with pytest.raises(AgentRuntimeContractError, match="onError|continueErrorOutput"):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_control_clean_workflow_still_passes() -> None:
    report = validate_workflow(REPO, WF)
    assert report["status"] == "PASS"
    assert_workflow_agent_wiring(root=REPO)
