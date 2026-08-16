"""R1: closed-world must cover every connection key; agent attachment set pinned."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    IMPLEMENTER_CHAT_MODEL_NODE_NAME,
    IMPLEMENTER_NODE_NAME,
    REVIEWER_NODE_NAME,
    AgentRuntimeContractError,
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.workflow_validator import validate_workflow

REPO = Path(__file__).resolve().parents[2]


def _mutated(workflow: dict | None = None) -> dict:
    return copy.deepcopy(workflow if workflow is not None else load_design_workflow(root=REPO))


def _write_probe(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _fail_both(tmp_path: Path, wf: dict, *, structural_substr: str, contract_re: str) -> None:
    report = validate_workflow(REPO, _write_probe(tmp_path, wf))
    assert report["status"] == "FAIL"
    messages = " ".join(e["message"] for e in report["errors"])
    assert structural_substr.lower() in messages.lower(), messages
    with pytest.raises(AgentRuntimeContractError, match=contract_re):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_r1_positive_control_legitimate_ai_language_model_still_passes() -> None:
    """Exactly one legitimate ai_languageModel per agent must still PASS."""
    wf = load_design_workflow(root=REPO)
    report = validate_workflow(REPO, REPO / "workflows/design/self_improvement_loop_v2.json")
    assert report["status"] == "PASS"
    # Primary signal: no raise — over-strict attachment pin would break the design workflow.
    wiring = assert_workflow_agent_wiring(workflow=wf, root=REPO)
    assert isinstance(wiring, dict)


def test_r1_p1d_second_ai_language_model_defeats_cost_bound_rejected(tmp_path: Path) -> None:
    """P1d: second unpinned model + huge maxOutputTokens must be REJECTED by both."""
    wf = _mutated()
    rogue_name = "Rogue Ultra Chat Model"
    wf["nodes"].append(
        {
            "parameters": {
                "modelName": "models/gemini-1.0-ultra",
                "options": {"maxOutputTokens": 999999},
            },
            "id": "rogue-ultra-chat-model",
            "name": rogue_name,
            "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
            "typeVersion": 1,
            "position": [0, 0],
        }
    )
    wf["connections"][rogue_name] = {
        "ai_languageModel": [
            [
                {
                    "node": IMPLEMENTER_NODE_NAME,
                    "type": "ai_languageModel",
                    "index": 0,
                }
            ]
        ]
    }
    _fail_both(
        tmp_path,
        wf,
        structural_substr="ai_languageModel",
        contract_re="ai_languageModel|attachment|chat model",
    )


def test_r1_p1b_ai_tool_http_loopback_non_pinned_port_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    tool_name = "Rogue Loopback Tool"
    wf["nodes"].append(
        {
            "parameters": {"url": "http://127.0.0.1:9999/anything"},
            "id": "rogue-loopback-tool",
            "name": tool_name,
            "type": "n8n-nodes-base.httpRequestTool",
            "typeVersion": 1,
            "position": [0, 0],
        }
    )
    wf["connections"][tool_name] = {
        "ai_tool": [
            [{"node": IMPLEMENTER_NODE_NAME, "type": "ai_tool", "index": 0}]
        ]
    }
    _fail_both(tmp_path, wf, structural_substr="ai_tool", contract_re="ai_tool|attachment")


def test_r1_p1c_ai_tool_code_exec_on_reviewer_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    tool_name = "Rogue Code Tool"
    wf["nodes"].append(
        {
            "parameters": {"jsCode": "require('child_process').execSync('id')"},
            "id": "rogue-code-tool",
            "name": tool_name,
            "type": "@n8n/n8n-nodes-langchain.toolCode",
            "typeVersion": 1,
            "position": [0, 0],
        }
    )
    wf["connections"][tool_name] = {
        "ai_tool": [
            [{"node": REVIEWER_NODE_NAME, "type": "ai_tool", "index": 0}]
        ]
    }
    _fail_both(tmp_path, wf, structural_substr="ai_tool", contract_re="ai_tool|attachment")


def test_r1_p1e_ai_memory_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    mem_name = "Rogue Memory"
    wf["nodes"].append(
        {
            "parameters": {},
            "id": "rogue-memory",
            "name": mem_name,
            "type": "@n8n/n8n-nodes-langchain.memoryBufferWindow",
            "typeVersion": 1,
            "position": [0, 0],
        }
    )
    wf["connections"][mem_name] = {
        "ai_memory": [
            [{"node": IMPLEMENTER_NODE_NAME, "type": "ai_memory", "index": 0}]
        ]
    }
    _fail_both(tmp_path, wf, structural_substr="ai_memory", contract_re="ai_memory|attachment")


def test_r1_duplicate_legitimate_ai_language_model_edge_rejected(tmp_path: Path) -> None:
    wf = _mutated()
    edge = {
        "node": IMPLEMENTER_NODE_NAME,
        "type": "ai_languageModel",
        "index": 0,
    }
    wf["connections"][IMPLEMENTER_CHAT_MODEL_NODE_NAME]["ai_languageModel"][0].append(edge)
    _fail_both(
        tmp_path,
        wf,
        structural_substr="duplicate",
        contract_re="exactly once|duplicate|ai_languageModel",
    )
