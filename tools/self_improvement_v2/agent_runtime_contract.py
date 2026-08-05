"""Phase 1A agent-runtime contract: pinned non-secret bindings (no live AI calls)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement_v2.schema_loader import validate_instance, worker_package_root

PHASE = "1A"
WIRING_STATUS_CONTRACT_ONLY = "CONTRACT_ONLY"
WIRING_STATUS_WORKFLOW_WIRED = "WORKFLOW_WIRED"

IMPLEMENTER_AGENT_ID = "srl-implementer-agent"
REVIEWER_AGENT_ID = "srl-independent-reviewer-agent"

IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE = "SRL Implementer — Google Gemini"
REVIEWER_AGENT_CREDENTIAL_REFERENCE = "SRL Independent Reviewer — Groq"

IMPLEMENTER_PROVIDER = "google_gemini"
REVIEWER_PROVIDER = "groq"

IMPLEMENTER_MODEL = "models/gemini-2.5-flash"
REVIEWER_MODEL = "llama3-8b-8192"

IMPLEMENTER_CHAT_MODEL_NODE_TYPE = "@n8n/n8n-nodes-langchain.lmChatGoogleGemini"
REVIEWER_CHAT_MODEL_NODE_TYPE = "@n8n/n8n-nodes-langchain.lmChatGroq"
AI_AGENT_NODE_TYPE = "@n8n/n8n-nodes-langchain.agent"

IMPLEMENTER_NODE_NAME = "Implementer Agent"
REVIEWER_NODE_NAME = "Independent Reviewer Agent"
CHAT_MODEL_ATTACHMENT = "ai_languageModel"

WORKER_BASE_URL_META_KEY = "localWorkerBaseUrl"
WORKER_HEADER_AUTH_CREDENTIAL_NAME = "srl-v2-worker-header-auth"
DEFAULT_LOCAL_WORKER_BASE_URL = "http://127.0.0.1:8765"

AUTHORIZE_PATH = "/v2/validate-proposal"
EXECUTE_PATH = "/v2/execute"
FINALIZE_PATH = "/v2/finalize"
HEALTH_PATH = "/health"

RISK_AUTHORITY_MODULE = "tools.self_improvement_v2.risk_authority"
REVIEW_GATE_MODULE = "tools.self_improvement_v2.review_gate"

WORKER_DECISIONS = ("AUTHORIZED", "DECISION_REQUIRED", "POLICY_REJECTED")

DESIGN_WORKFLOW_REL = Path("workflows/design/self_improvement_loop_v2.json")

# Assignment-like secret literals only — policy enum names (e.g. api_keys) must not match.
_SECRET_LITERAL_RE = re.compile(
    r"(?i)("
    r"(?:api[_-]?key|secret|password)\s*[:=]\s*['\"]?[^'\"\s,]{8,}"
    r"|bearer\s+[A-Za-z0-9._\-+=/]{8,}"
    r"|SRL_WORKER_TOKEN\s*[:=]\s*\S+"
    r")"
)
_OPERATOR_PLACEHOLDER = "OPERATOR_REQUIRED"


class AgentRuntimeContractError(WorkerError):
    """Agent-runtime contract rejected before any mutation or live call."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(
            code or ERROR_CODES["SI2-AGENT-RUNTIME-CONTRACT"],
            message,
            state="POLICY_REJECTED",
        )


def pinned_agent_runtime_contract() -> dict[str, Any]:
    """Return the canonical Phase 1A contract instance (non-secret)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "wiring_status": WIRING_STATUS_CONTRACT_ONLY,
        "inactive_by_design": True,
        "implementer": {
            "agent_id": IMPLEMENTER_AGENT_ID,
            "credential_reference": IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE,
            "provider": IMPLEMENTER_PROVIDER,
            "chat_model_node_type": IMPLEMENTER_CHAT_MODEL_NODE_TYPE,
            "model": IMPLEMENTER_MODEL,
            "produces": ["improvement_candidate", "implementation_proposal"],
            "must_not": [
                "authorize_risk",
                "mutate_git",
                "finalize",
                "override_worker_decision",
                "share_reviewer_credential",
            ],
        },
        "independent_reviewer": {
            "agent_id": REVIEWER_AGENT_ID,
            "credential_reference": REVIEWER_AGENT_CREDENTIAL_REFERENCE,
            "provider": REVIEWER_PROVIDER,
            "chat_model_node_type": REVIEWER_CHAT_MODEL_NODE_TYPE,
            "model": REVIEWER_MODEL,
            "produces": ["review_result"],
            "must_not": [
                "authorize_risk",
                "mutate_git",
                "finalize",
                "share_implementer_credential",
                "self_review",
            ],
        },
        "n8n_invocation": {
            "ai_agent_node_type": AI_AGENT_NODE_TYPE,
            "implementer_node_name": IMPLEMENTER_NODE_NAME,
            "reviewer_node_name": REVIEWER_NODE_NAME,
            "chat_model_attachment": CHAT_MODEL_ATTACHMENT,
            "credential_binding": "n8n_credential_name_reference_only",
            "export_rules": [
                "active_false",
                "no_secret_values",
                "credential_names_only",
                "model_ids_non_secret",
            ],
        },
        "worker_http": {
            "base_url_meta_key": WORKER_BASE_URL_META_KEY,
            "header_auth_credential_name": WORKER_HEADER_AUTH_CREDENTIAL_NAME,
            "authorize_path": AUTHORIZE_PATH,
            "execute_path": EXECUTE_PATH,
            "finalize_path": FINALIZE_PATH,
            "health_path": HEALTH_PATH,
            "bind_policy": "loopback_only",
        },
        "risk_authority": {
            "module": RISK_AUTHORITY_MODULE,
            "sole_authorizer": True,
            "n8n_may_route_only": True,
            "n8n_must_not": [
                "compute_risk",
                "override_worker_decision",
                "manufacture_AUTO_AUTHORIZED",
                "trust_proposal_risk_level",
            ],
            "worker_decisions": list(WORKER_DECISIONS),
        },
        "review_gate": {
            "module": REVIEW_GATE_MODULE,
            "requires_independent_from_implementer": True,
            "reject_same_agent_ids": True,
            "failure_before_mutation": True,
        },
        "secrets_policy": {
        "forbid_in_repo": [
            "api_keys",
            "worker_token_values",
            "credential_secret_data",
            "bearer_token_literals",
        ],
            "allow_in_repo": [
                "credential_reference_names",
                "model_ids",
                "worker_base_url",
                "header_auth_credential_name",
            ],
        },
        "pilot_limits": {
            "MAXIMUM_PILOT_COST_USD": 5,
            "MAXIMUM_AGENT_CALLS": 6,
            "PILOT_TIMEOUT_MINUTES": 30,
        },
    }


def validate_agent_runtime_contract(
    instance: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Validate a contract instance; defaults to the pinned Phase 1A contract.

    Semantic separation and secret-literal checks run before schema validation so
    mutated instances fail closed with contract codes (failure before mutation).
    """
    payload = pinned_agent_runtime_contract() if instance is None else dict(instance)
    if not isinstance(payload, dict):
        raise AgentRuntimeContractError("agent runtime contract must be an object")
    _assert_no_secret_literals(payload)
    _assert_identity_separation(payload)
    if payload.get("wiring_status") == WIRING_STATUS_CONTRACT_ONLY and payload.get("phase") != PHASE:
        raise AgentRuntimeContractError("CONTRACT_ONLY wiring requires phase 1A")
    validate_instance("agent_runtime_contract", payload, root=root)
    return payload


def assert_identity_separation(contract: dict[str, Any] | None = None) -> None:
    payload = contract if contract is not None else pinned_agent_runtime_contract()
    _assert_identity_separation(payload)


def _assert_identity_separation(payload: dict[str, Any]) -> None:
    implementer = payload.get("implementer") or {}
    reviewer = payload.get("independent_reviewer") or {}
    if implementer.get("agent_id") == reviewer.get("agent_id"):
        raise AgentRuntimeContractError(
            "implementer and reviewer agent_id must differ",
            code=ERROR_CODES["SI2-REVIEW-SELF"],
        )
    if implementer.get("credential_reference") == reviewer.get("credential_reference"):
        raise AgentRuntimeContractError(
            "implementer and reviewer credential references must differ",
            code=ERROR_CODES["SI2-REVIEW-SELF"],
        )
    if implementer.get("provider") == reviewer.get("provider"):
        raise AgentRuntimeContractError(
            "implementer and reviewer providers must differ",
            code=ERROR_CODES["SI2-REVIEW-SELF"],
        )
    if implementer.get("model") == reviewer.get("model"):
        raise AgentRuntimeContractError(
            "implementer and reviewer models must differ",
            code=ERROR_CODES["SI2-REVIEW-SELF"],
        )


def _assert_no_secret_literals(payload: dict[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if _SECRET_LITERAL_RE.search(blob):
        raise AgentRuntimeContractError(
            "secret-like literals forbidden in agent runtime contract",
            code=ERROR_CODES["CREDENTIALS_IN_WORKFLOW"],
        )


def design_workflow_path(root: Path | None = None) -> Path:
    base = root if root is not None else worker_package_root()
    return (base / DESIGN_WORKFLOW_REL).resolve()


def load_design_workflow(root: Path | None = None) -> dict[str, Any]:
    path = design_workflow_path(root)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AgentRuntimeContractError("design workflow must be a JSON object")
    return data


def assert_workflow_meta_bindings(
    workflow: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
    require_pinned_models: bool = True,
) -> dict[str, Any]:
    """Fail before mutation if workflow meta does not match the Phase 1A contract pins."""
    data = workflow if workflow is not None else load_design_workflow(root)
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise AgentRuntimeContractError("workflow meta missing")

    if data.get("active") is not False:
        raise AgentRuntimeContractError(
            "workflow must remain inactive by design",
            code=ERROR_CODES["WORKFLOW_ACTIVE"],
        )
    if meta.get("srlInactiveByDesign") is not True:
        raise AgentRuntimeContractError("meta.srlInactiveByDesign must be true")

    if meta.get("implementerAgentId") != IMPLEMENTER_AGENT_ID:
        raise AgentRuntimeContractError("meta.implementerAgentId mismatch")
    if meta.get("reviewerAgentId") != REVIEWER_AGENT_ID:
        raise AgentRuntimeContractError("meta.reviewerAgentId mismatch")
    if meta.get("implementerAgentId") == meta.get("reviewerAgentId"):
        raise AgentRuntimeContractError(
            "implementerAgentId and reviewerAgentId must differ",
            code=ERROR_CODES["SI2-REVIEW-SELF"],
        )

    impl_cred = meta.get("implementerAgentCredentialReference")
    rev_cred = meta.get("reviewerAgentCredentialReference")
    if impl_cred in (None, "", _OPERATOR_PLACEHOLDER):
        raise AgentRuntimeContractError("implementerAgentCredentialReference not pinned")
    if rev_cred in (None, "", _OPERATOR_PLACEHOLDER):
        raise AgentRuntimeContractError("reviewerAgentCredentialReference not pinned")
    if impl_cred == rev_cred:
        raise AgentRuntimeContractError(
            "credential references must remain distinct",
            code=ERROR_CODES["SI2-REVIEW-SELF"],
        )
    if impl_cred != IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE:
        raise AgentRuntimeContractError("implementerAgentCredentialReference mismatch")
    if rev_cred != REVIEWER_AGENT_CREDENTIAL_REFERENCE:
        raise AgentRuntimeContractError("reviewerAgentCredentialReference mismatch")

    if require_pinned_models:
        if meta.get("implementerModel") != IMPLEMENTER_MODEL:
            raise AgentRuntimeContractError("meta.implementerModel mismatch")
        if meta.get("reviewerModel") != REVIEWER_MODEL:
            raise AgentRuntimeContractError("meta.reviewerModel mismatch")
        if meta.get("implementerModel") == meta.get("reviewerModel"):
            raise AgentRuntimeContractError(
                "implementer and reviewer models must differ",
                code=ERROR_CODES["SI2-REVIEW-SELF"],
            )

    if meta.get("workerHeaderAuthCredentialName") != WORKER_HEADER_AUTH_CREDENTIAL_NAME:
        raise AgentRuntimeContractError("workerHeaderAuthCredentialName mismatch")
    base_url = meta.get(WORKER_BASE_URL_META_KEY)
    if not isinstance(base_url, str) or not base_url.strip():
        raise AgentRuntimeContractError("localWorkerBaseUrl missing")
    if "127.0.0.1" not in base_url and "localhost" not in base_url.lower():
        raise AgentRuntimeContractError("localWorkerBaseUrl must remain loopback")

    _assert_no_secret_literals({"meta": meta})
    return meta


def assert_phase_1a_contract_surface(*, root: Path | None = None) -> dict[str, Any]:
    """Validate pinned contract + design workflow meta bindings (no live provider calls)."""
    contract = validate_agent_runtime_contract(root=root)
    meta = assert_workflow_meta_bindings(root=root, require_pinned_models=True)
    return {"contract": contract, "workflow_meta": meta}
