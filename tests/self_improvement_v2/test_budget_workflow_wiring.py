"""Prove inactive workflow wires budget open + permits before provider agents.

Also re-proves executable 1..6 grants vs 7th refuse so the gate cannot be docs-only.
"""

from __future__ import annotations

import copy
import json

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    ANNOTATE_BUDGET_DENIED_NODE_NAME,
    BUDGET_OPEN_PATH,
    IMPLEMENTER_NODE_NAME,
    OPEN_PILOT_BUDGET_NODE_NAME,
    PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME,
    PROVIDER_CALL_CONSUME_PATH,
    PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME,
    PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME,
    PROVIDER_CALL_PERMIT_PATH,
    PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME,
    REVIEWER_NODE_NAME,
    AgentRuntimeContractError,
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.pilot_budget import (
    MAXIMUM_AGENT_CALLS,
    BudgetError,
    PilotBudgetRegistry,
)


def test_workflow_wires_budget_open_and_permits_before_agents() -> None:
    wiring = assert_workflow_agent_wiring()
    assert wiring["budget_open"] == OPEN_PILOT_BUDGET_NODE_NAME
    assert wiring["provider_call_permit_implementer"] == PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME
    assert wiring["provider_call_permit_reviewer"] == PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME
    assert wiring["provider_call_consume_implementer"] == PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME
    assert wiring["provider_call_consume_reviewer"] == PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME

    workflow = load_design_workflow()
    assert workflow.get("active") is False
    by_name = {n["name"]: n for n in workflow["nodes"]}
    assert BUDGET_OPEN_PATH in by_name[OPEN_PILOT_BUDGET_NODE_NAME]["parameters"]["url"]
    assert PROVIDER_CALL_PERMIT_PATH in by_name[PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME]["parameters"]["url"]
    assert PROVIDER_CALL_PERMIT_PATH in by_name[PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME]["parameters"]["url"]
    assert PROVIDER_CALL_CONSUME_PATH in by_name[PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME]["parameters"]["url"]
    assert PROVIDER_CALL_CONSUME_PATH in by_name[PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME]["parameters"]["url"]

    connections = workflow["connections"]
    assert (
        connections["Candidate Schema Validation"]["main"][0][0]["node"]
        == OPEN_PILOT_BUDGET_NODE_NAME
    )
    assert (
        connections[OPEN_PILOT_BUDGET_NODE_NAME]["main"][0][0]["node"]
        == PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME
    )
    assert (
        connections[PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME]["main"][0][0]["node"]
        == PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME
    )
    assert (
        connections[PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME]["main"][0][0]["node"]
        == "Provider Call Authorize (Implementer)"
    )
    assert (
        connections["Provider Call Authorize (Implementer)"]["main"][0][0]["node"]
        == IMPLEMENTER_NODE_NAME
    )
    assert (
        connections["Execution Result Validation"]["main"][0][0]["node"]
        == PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME
    )
    assert (
        connections[PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME]["main"][0][0]["node"]
        == PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME
    )
    assert (
        connections[PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME]["main"][0][0]["node"]
        == "Provider Call Authorize (Reviewer)"
    )
    assert (
        connections["Provider Call Authorize (Reviewer)"]["main"][0][0]["node"]
        == REVIEWER_NODE_NAME
    )
    # Deny outputs are terminal via Annotate Budget Denied → Failure Router.
    for source in (
        OPEN_PILOT_BUDGET_NODE_NAME,
        PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME,
        PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME,
        "Provider Call Authorize (Implementer)",
        PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME,
        PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME,
        "Provider Call Authorize (Reviewer)",
    ):
        assert connections[source]["main"][1][0]["node"] == ANNOTATE_BUDGET_DENIED_NODE_NAME
    assert (
        connections[ANNOTATE_BUDGET_DENIED_NODE_NAME]["main"][0][0]["node"] == "Failure Router"
    )


def test_agents_cannot_bypass_permit_edges() -> None:
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    # Bypass: Candidate Schema Validation → Implementer Agent directly.
    mutated["connections"]["Candidate Schema Validation"]["main"][0][0]["node"] = IMPLEMENTER_NODE_NAME
    with pytest.raises(AgentRuntimeContractError, match="budget/permit|Open Pilot Budget must follow"):
        assert_workflow_agent_wiring(mutated)

    mutated = copy.deepcopy(workflow)
    mutated["connections"]["Execution Result Validation"]["main"][0][0]["node"] = REVIEWER_NODE_NAME
    with pytest.raises(
        AgentRuntimeContractError,
        match="bypass provider-call-permit|Provider Call Permit \\(Reviewer\\) must follow",
    ):
        assert_workflow_agent_wiring(mutated)


def test_missing_budget_open_node_rejected() -> None:
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    mutated["nodes"] = [n for n in mutated["nodes"] if n.get("name") != OPEN_PILOT_BUDGET_NODE_NAME]
    with pytest.raises(AgentRuntimeContractError, match="missing wired node"):
        assert_workflow_agent_wiring(mutated)


def test_permit_path_1_to_6_granted_7th_refused_cannot_reach_provider() -> None:
    """Executable gate behind the workflow permit nodes: 7th call never grants."""
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="workflow-budget-wiring-1")
    granted = []
    for i in range(MAXIMUM_AGENT_CALLS):
        permit = reg.request_call_permit(
            session.session_id, role="implementer", max_output_tokens=2000
        )
        assert permit["status"] == "GRANTED"
        granted.append(permit["permit_number"])
        # Workflow only routes to provider agents on grant — simulate that gate.
        assert permit["permit_number"] <= MAXIMUM_AGENT_CALLS
    assert granted == list(range(1, MAXIMUM_AGENT_CALLS + 1))
    with pytest.raises(BudgetError) as exc:
        reg.request_call_permit(session.session_id, role="implementer", max_output_tokens=2000)
    assert exc.value.code == ERROR_CODES["PILOT_CALL_LIMIT"]
    # No 7th grant exists; provider path must not proceed.
    assert session.calls_granted == MAXIMUM_AGENT_CALLS


def test_workflow_export_has_no_secret_literals_in_budget_nodes() -> None:
    workflow = load_design_workflow()
    blob = json.dumps(workflow)
    assert "api_key=" not in blob.lower()
    assert "bearer " not in blob.lower()
    assert "SRL_WORKER_TOKEN=" not in blob
