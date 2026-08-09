"""Phase 1B agent-runtime contract: pinned non-secret bindings + inactive workflow wiring checks."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement_v2.schema_loader import validate_instance, worker_package_root

PHASE = "1B"
PHASE_CONTRACT_ONLY = "1A"
WIRING_STATUS_CONTRACT_ONLY = "CONTRACT_ONLY"
WIRING_STATUS_WORKFLOW_WIRED = "WORKFLOW_WIRED"

IMPLEMENTER_AGENT_ID = "srl-implementer-agent"
REVIEWER_AGENT_ID = "srl-independent-reviewer-agent"

IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE = "SRL Implementer — Google Gemini"
REVIEWER_AGENT_CREDENTIAL_REFERENCE = "SRL Independent Reviewer — Groq"

IMPLEMENTER_PROVIDER = "google_gemini"
REVIEWER_PROVIDER = "groq"

IMPLEMENTER_MODEL = "models/gemini-3.6-flash"
REVIEWER_MODEL = "llama3-8b-8192"

IMPLEMENTER_CHAT_MODEL_NODE_TYPE = "@n8n/n8n-nodes-langchain.lmChatGoogleGemini"
REVIEWER_CHAT_MODEL_NODE_TYPE = "@n8n/n8n-nodes-langchain.lmChatGroq"
AI_AGENT_NODE_TYPE = "@n8n/n8n-nodes-langchain.agent"
HTTP_REQUEST_NODE_TYPE = "n8n-nodes-base.httpRequest"

IMPLEMENTER_NODE_NAME = "Implementer Agent"
REVIEWER_NODE_NAME = "Independent Reviewer Agent"
IMPLEMENTER_CHAT_MODEL_NODE_NAME = "Implementer Gemini Chat Model"
REVIEWER_CHAT_MODEL_NODE_NAME = "Independent Reviewer Groq Chat Model"
WORKER_AUTHORIZE_NODE_NAME = "Worker Authorize"
OPEN_PILOT_BUDGET_NODE_NAME = "Open Pilot Budget"
PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME = "Provider Call Permit (Implementer)"
PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME = "Provider Call Permit (Reviewer)"
PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME = "Provider Call Consume (Implementer)"
PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME = "Provider Call Consume (Reviewer)"
ANNOTATE_BUDGET_DENIED_NODE_NAME = "Annotate Budget Denied"
REQUIRED_AGENT_MAX_ITERATIONS = 1

CHAT_MODEL_ATTACHMENT = "ai_languageModel"

IMPLEMENTER_CREDENTIAL_TYPE = "googlePalmApi"
REVIEWER_CREDENTIAL_TYPE = "groqApi"
WORKER_HEADER_AUTH_CREDENTIAL_TYPE = "httpHeaderAuth"

WORKER_BASE_URL_META_KEY = "localWorkerBaseUrl"
WORKER_HEADER_AUTH_CREDENTIAL_NAME = "srl-v2-worker-header-auth"
DEFAULT_LOCAL_WORKER_BASE_URL = "http://127.0.0.1:8765"

AUTHORIZE_PATH = "/v2/validate-proposal"
EXECUTE_PATH = "/v2/execute"
FINALIZE_PATH = "/v2/finalize"
HEALTH_PATH = "/health"
BUDGET_OPEN_PATH = "/v2/budget/open"
PROVIDER_CALL_PERMIT_PATH = "/v2/provider-call-permit"
PROVIDER_CALL_CONSUME_PATH = "/v2/provider-call-consume"
BIND_REVIEW_PATH = "/v2/bind-review"
INDEPENDENT_REVIEW_BIND_NODE_NAME = "Independent Review Bind"

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

# Credential-name inequality alone does NOT prove runtime identity independence.
RUNTIME_IDENTITY_INDEPENDENCE_CLAIM = False


class AgentRuntimeContractError(WorkerError):
    """Agent-runtime contract rejected before any mutation or live call."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(
            code or ERROR_CODES["SI2-AGENT-RUNTIME-CONTRACT"],
            message,
            state="POLICY_REJECTED",
        )


def pinned_agent_runtime_contract() -> dict[str, Any]:
    """Return the canonical Phase 1B contract instance (non-secret)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "wiring_status": WIRING_STATUS_WORKFLOW_WIRED,
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
        # Executable enforcers (not schema fields): pilot_budget.PilotBudgetRegistry
        # for calls/cost/wall-clock; repair_policy.assert_repair_attempt_allowed for repairs.
    }


def validate_agent_runtime_contract(
    instance: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Validate a contract instance; defaults to the pinned Phase 1B contract.

    Semantic separation and secret-literal checks run before schema validation so
    mutated instances fail closed with contract codes (failure before mutation).
    """
    payload = pinned_agent_runtime_contract() if instance is None else dict(instance)
    if not isinstance(payload, dict):
        raise AgentRuntimeContractError("agent runtime contract must be an object")
    _assert_no_secret_literals(payload)
    _assert_identity_separation(payload)
    _assert_phase_wiring_coupling(payload)
    validate_instance("agent_runtime_contract", payload, root=root)
    return payload


def assert_identity_separation(contract: dict[str, Any] | None = None) -> None:
    payload = contract if contract is not None else pinned_agent_runtime_contract()
    _assert_identity_separation(payload)


def credential_references_equivalent(left: str, right: str) -> bool:
    """Exact credential-reference equality only (no case/whitespace/Unicode folding).

    Distinct names are necessary but not sufficient for runtime identity independence.
    """
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    return left == right


def reject_nonexact_credential_reference(candidate: str, pinned: str) -> None:
    """Fail closed when candidate is not the exact pinned credential reference."""
    if not isinstance(candidate, str):
        raise AgentRuntimeContractError("credential reference must be a string")
    if credential_references_equivalent(candidate, pinned):
        return
    raise AgentRuntimeContractError("credential reference mismatch (exact pin required)")


def _assert_phase_wiring_coupling(payload: dict[str, Any]) -> None:
    phase = payload.get("phase")
    wiring = payload.get("wiring_status")
    if wiring == WIRING_STATUS_CONTRACT_ONLY and phase != PHASE_CONTRACT_ONLY:
        raise AgentRuntimeContractError("CONTRACT_ONLY wiring requires phase 1A")
    if wiring == WIRING_STATUS_WORKFLOW_WIRED and phase != PHASE:
        raise AgentRuntimeContractError("WORKFLOW_WIRED wiring requires phase 1B")
    if phase == PHASE and wiring != WIRING_STATUS_WORKFLOW_WIRED:
        raise AgentRuntimeContractError("phase 1B requires WORKFLOW_WIRED wiring status")


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
    # Strict provider/role/model binding to pinned constants when present.
    if implementer.get("provider") not in (None, IMPLEMENTER_PROVIDER):
        raise AgentRuntimeContractError("implementer provider binding mismatch")
    if reviewer.get("provider") not in (None, REVIEWER_PROVIDER):
        raise AgentRuntimeContractError("reviewer provider binding mismatch")
    if implementer.get("model") not in (None, IMPLEMENTER_MODEL):
        raise AgentRuntimeContractError("implementer model binding mismatch")
    if reviewer.get("model") not in (None, REVIEWER_MODEL):
        raise AgentRuntimeContractError("reviewer model binding mismatch")


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
    """Fail before mutation if workflow meta does not match the Phase 1B contract pins."""
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

    if meta.get("agentRuntimePhase") != PHASE:
        raise AgentRuntimeContractError("meta.agentRuntimePhase must be 1B")
    if meta.get("agentRuntimeWiringStatus") != WIRING_STATUS_WORKFLOW_WIRED:
        raise AgentRuntimeContractError("meta.agentRuntimeWiringStatus must be WORKFLOW_WIRED")

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
    reject_nonexact_credential_reference(str(impl_cred), IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE)
    reject_nonexact_credential_reference(str(rev_cred), REVIEWER_AGENT_CREDENTIAL_REFERENCE)

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
    # Base URL is origin only (no path); reject userinfo / non-loopback.
    from urllib.parse import urlparse

    parsed = urlparse(base_url.strip())
    if parsed.scheme != "http":
        raise AgentRuntimeContractError("localWorkerBaseUrl scheme must be http")
    if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
        raise AgentRuntimeContractError("localWorkerBaseUrl must not include userinfo")
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost"}:
        raise AgentRuntimeContractError("localWorkerBaseUrl must remain loopback")
    if parsed.path not in ("", "/"):
        raise AgentRuntimeContractError("localWorkerBaseUrl must not include a path")

    _assert_no_secret_literals({"meta": meta})
    return meta


def _nodes_by_name(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for node in workflow.get("nodes") or []:
        if isinstance(node, dict) and isinstance(node.get("name"), str):
            out[node["name"]] = node
    return out


def _credential_name(node: dict[str, Any], cred_type: str) -> str | None:
    creds = node.get("credentials")
    if not isinstance(creds, dict):
        return None
    block = creds.get(cred_type)
    if not isinstance(block, dict):
        return None
    name = block.get("name")
    return name if isinstance(name, str) else None


def _has_ai_language_model_edge(
    connections: dict[str, Any], source: str, dest: str
) -> bool:
    block = connections.get(source) or {}
    outputs = block.get(CHAT_MODEL_ATTACHMENT) or []
    for group in outputs:
        if not group:
            continue
        for link in group:
            if isinstance(link, dict) and link.get("node") == dest:
                if link.get("type") == CHAT_MODEL_ATTACHMENT:
                    return True
    return False


def _has_main_edge(connections: dict[str, Any], source: str, dest: str) -> bool:
    block = connections.get(source) or {}
    mains = block.get("main") or []
    for group in mains:
        if not group:
            continue
        for link in group:
            if isinstance(link, dict) and link.get("node") == dest and link.get("type") == "main":
                return True
    return False


def assert_loopback_worker_url(url: str, path: str, label: str) -> None:
    """Exact scheme/host/port/path loopback check — rejects userinfo / host confusion."""
    from urllib.parse import urlparse

    if not isinstance(url, str) or not url.strip():
        raise AgentRuntimeContractError(f"{label} URL missing")
    parsed = urlparse(url.strip())
    if parsed.scheme != "http":
        raise AgentRuntimeContractError(f"{label} URL scheme must be http")
    if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
        raise AgentRuntimeContractError(f"{label} URL must not include userinfo")
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost"}:
        raise AgentRuntimeContractError(f"{label} URL host must be 127.0.0.1 or localhost")
    if parsed.path != path:
        raise AgentRuntimeContractError(f"{label} URL path must be exactly {path}")
    if parsed.query or parsed.fragment:
        raise AgentRuntimeContractError(f"{label} URL must not include query/fragment")
    # Port optional; when present must be numeric (urlparse already validates).
    if parsed.port is not None and not (1 <= int(parsed.port) <= 65535):
        raise AgentRuntimeContractError(f"{label} URL port out of range")


def _assert_http_post_loopback_path(node: dict[str, Any], path: str, label: str) -> None:
    params = node.get("parameters") or {}
    url = str(params.get("url") or "")
    method = str(params.get("method") or "GET").upper()
    if method != "POST":
        raise AgentRuntimeContractError(f"{label} must POST")
    assert_loopback_worker_url(url, path, label)


def _assert_agent_max_iterations(node: dict[str, Any], label: str) -> None:
    """Agents must be single-iteration — consume cannot gate mid-loop retries."""
    params = node.get("parameters") or {}
    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    raw = options.get("maxIterations", params.get("maxIterations"))
    if raw is None:
        raise AgentRuntimeContractError(f"{label} must set maxIterations={REQUIRED_AGENT_MAX_ITERATIONS}")
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise AgentRuntimeContractError(f"{label} maxIterations must be an integer (boolean rejected)")
    if raw != REQUIRED_AGENT_MAX_ITERATIONS:
        raise AgentRuntimeContractError(
            f"{label} maxIterations must be {REQUIRED_AGENT_MAX_ITERATIONS} (got {raw})"
        )
    if node.get("retryOnFail") is True:
        raise AgentRuntimeContractError(f"{label} retryOnFail must be false when agent is present")


def assert_workflow_agent_wiring(
    workflow: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Assert Phase 1B inactive AI/HTTP wiring (credential names + models only; no live calls)."""
    data = workflow if workflow is not None else load_design_workflow(root)
    by_name = _nodes_by_name(data)
    connections = data.get("connections") or {}
    if not isinstance(connections, dict):
        raise AgentRuntimeContractError("workflow connections missing")

    implementer = by_name.get(IMPLEMENTER_NODE_NAME)
    reviewer = by_name.get(REVIEWER_NODE_NAME)
    impl_model = by_name.get(IMPLEMENTER_CHAT_MODEL_NODE_NAME)
    rev_model = by_name.get(REVIEWER_CHAT_MODEL_NODE_NAME)
    authorize = by_name.get(WORKER_AUTHORIZE_NODE_NAME)
    open_budget = by_name.get(OPEN_PILOT_BUDGET_NODE_NAME)
    permit_impl = by_name.get(PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME)
    permit_rev = by_name.get(PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME)
    consume_impl = by_name.get(PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME)
    consume_rev = by_name.get(PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME)
    budget_denied = by_name.get(ANNOTATE_BUDGET_DENIED_NODE_NAME)
    bind_review = by_name.get(INDEPENDENT_REVIEW_BIND_NODE_NAME)

    for label, node in (
        (IMPLEMENTER_NODE_NAME, implementer),
        (REVIEWER_NODE_NAME, reviewer),
        (IMPLEMENTER_CHAT_MODEL_NODE_NAME, impl_model),
        (REVIEWER_CHAT_MODEL_NODE_NAME, rev_model),
        (WORKER_AUTHORIZE_NODE_NAME, authorize),
        (OPEN_PILOT_BUDGET_NODE_NAME, open_budget),
        (PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME, permit_impl),
        (PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME, permit_rev),
        (PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME, consume_impl),
        (PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME, consume_rev),
        (ANNOTATE_BUDGET_DENIED_NODE_NAME, budget_denied),
        (INDEPENDENT_REVIEW_BIND_NODE_NAME, bind_review),
    ):
        if node is None:
            raise AgentRuntimeContractError(f"missing wired node: {label}")

    if implementer.get("type") != AI_AGENT_NODE_TYPE:
        raise AgentRuntimeContractError("Implementer Agent node type mismatch")
    if reviewer.get("type") != AI_AGENT_NODE_TYPE:
        raise AgentRuntimeContractError("Independent Reviewer Agent node type mismatch")
    _assert_agent_max_iterations(implementer, IMPLEMENTER_NODE_NAME)
    _assert_agent_max_iterations(reviewer, REVIEWER_NODE_NAME)
    if impl_model.get("type") != IMPLEMENTER_CHAT_MODEL_NODE_TYPE:
        raise AgentRuntimeContractError("Implementer chat model node type mismatch")
    if rev_model.get("type") != REVIEWER_CHAT_MODEL_NODE_TYPE:
        raise AgentRuntimeContractError("Reviewer chat model node type mismatch")
    if authorize.get("type") != HTTP_REQUEST_NODE_TYPE:
        raise AgentRuntimeContractError("Worker Authorize must be HTTP Request for Phase 1B")
    if bind_review.get("type") != HTTP_REQUEST_NODE_TYPE:
        raise AgentRuntimeContractError(
            "Independent Review Bind must be HTTP Request to worker bind-review (review_gate)"
        )
    for label, node in (
        (OPEN_PILOT_BUDGET_NODE_NAME, open_budget),
        (PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME, permit_impl),
        (PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME, permit_rev),
        (PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME, consume_impl),
        (PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME, consume_rev),
    ):
        if node.get("type") != HTTP_REQUEST_NODE_TYPE:
            raise AgentRuntimeContractError(f"{label} must be HTTP Request")

    impl_model_name = (impl_model.get("parameters") or {}).get("modelName") or (
        impl_model.get("parameters") or {}
    ).get("model")
    rev_model_name = (rev_model.get("parameters") or {}).get("model") or (
        rev_model.get("parameters") or {}
    ).get("modelName")
    if impl_model_name != IMPLEMENTER_MODEL:
        raise AgentRuntimeContractError("Implementer chat model pin mismatch")
    if rev_model_name != REVIEWER_MODEL:
        raise AgentRuntimeContractError("Reviewer chat model pin mismatch")

    impl_cred = _credential_name(impl_model, IMPLEMENTER_CREDENTIAL_TYPE)
    rev_cred = _credential_name(rev_model, REVIEWER_CREDENTIAL_TYPE)
    reject_nonexact_credential_reference(
        str(impl_cred or ""), IMPLEMENTER_AGENT_CREDENTIAL_REFERENCE
    )
    reject_nonexact_credential_reference(
        str(rev_cred or ""), REVIEWER_AGENT_CREDENTIAL_REFERENCE
    )
    if impl_cred == rev_cred:
        raise AgentRuntimeContractError(
            "chat model credential references must differ",
            code=ERROR_CODES["SI2-REVIEW-SELF"],
        )

    worker_cred = _credential_name(authorize, WORKER_HEADER_AUTH_CREDENTIAL_TYPE)
    if worker_cred != WORKER_HEADER_AUTH_CREDENTIAL_NAME:
        raise AgentRuntimeContractError("Worker Authorize header auth credential name mismatch")
    for label, node in (
        (OPEN_PILOT_BUDGET_NODE_NAME, open_budget),
        (PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME, permit_impl),
        (PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME, permit_rev),
        (PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME, consume_impl),
        (PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME, consume_rev),
        (INDEPENDENT_REVIEW_BIND_NODE_NAME, bind_review),
    ):
        cred = _credential_name(node, WORKER_HEADER_AUTH_CREDENTIAL_TYPE)
        if cred != WORKER_HEADER_AUTH_CREDENTIAL_NAME:
            raise AgentRuntimeContractError(f"{label} header auth credential name mismatch")

    auth_params = authorize.get("parameters") or {}
    method = str(auth_params.get("method") or "GET").upper()
    if method != "POST":
        raise AgentRuntimeContractError("Worker Authorize must POST")
    assert_loopback_worker_url(str(auth_params.get("url") or ""), AUTHORIZE_PATH, WORKER_AUTHORIZE_NODE_NAME)

    _assert_http_post_loopback_path(open_budget, BUDGET_OPEN_PATH, OPEN_PILOT_BUDGET_NODE_NAME)
    _assert_http_post_loopback_path(
        permit_impl, PROVIDER_CALL_PERMIT_PATH, PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME
    )
    _assert_http_post_loopback_path(
        permit_rev, PROVIDER_CALL_PERMIT_PATH, PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME
    )
    _assert_http_post_loopback_path(
        consume_impl, PROVIDER_CALL_CONSUME_PATH, PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME
    )
    _assert_http_post_loopback_path(
        consume_rev, PROVIDER_CALL_CONSUME_PATH, PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME
    )
    _assert_http_post_loopback_path(
        bind_review, BIND_REVIEW_PATH, INDEPENDENT_REVIEW_BIND_NODE_NAME
    )
    # Hardcoded review_ok must never appear — Groq/review_gate verdict must matter.
    if "review_ok:true" in json.dumps(bind_review):
        raise AgentRuntimeContractError(
            "Independent Review Bind must not hardcode review_ok:true; use worker review_gate"
        )

    # Chat model options must bind provider_call_params / token ceilings (permit not advisory).
    for label, node, permit_name in (
        (IMPLEMENTER_CHAT_MODEL_NODE_NAME, impl_model, PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME),
        (REVIEWER_CHAT_MODEL_NODE_NAME, rev_model, PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME),
    ):
        options = (node.get("parameters") or {}).get("options")
        if not isinstance(options, dict) or not options:
            raise AgentRuntimeContractError(f"{label} options must bind provider_call_params")
        blob = json.dumps(options)
        if "max_output_tokens" not in blob and "maxOutputTokens" not in blob and "maxTokens" not in blob:
            raise AgentRuntimeContractError(f"{label} options must include token ceiling binding")
        if permit_name not in blob and "provider_call_params" not in blob:
            raise AgentRuntimeContractError(
                f"{label} options must reference permit provider_call_params"
            )

    if not _has_ai_language_model_edge(
        connections, IMPLEMENTER_CHAT_MODEL_NODE_NAME, IMPLEMENTER_NODE_NAME
    ):
        raise AgentRuntimeContractError("Implementer chat model must attach via ai_languageModel")
    if not _has_ai_language_model_edge(
        connections, REVIEWER_CHAT_MODEL_NODE_NAME, REVIEWER_NODE_NAME
    ):
        raise AgentRuntimeContractError("Reviewer chat model must attach via ai_languageModel")

    # Provider-controlled path: open → permit → consume → agent (maxIterations=1).
    if not _has_main_edge(connections, "Candidate Schema Validation", OPEN_PILOT_BUDGET_NODE_NAME):
        raise AgentRuntimeContractError("Open Pilot Budget must follow Candidate Schema Validation")
    if not _has_main_edge(
        connections, OPEN_PILOT_BUDGET_NODE_NAME, PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME
    ):
        raise AgentRuntimeContractError(
            "Provider Call Permit (Implementer) must follow Open Pilot Budget"
        )
    if not _has_main_edge(
        connections,
        PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME,
        PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME,
    ):
        raise AgentRuntimeContractError(
            "Provider Call Consume (Implementer) must follow Provider Call Permit (Implementer)"
        )
    if not _has_main_edge(
        connections, PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME, IMPLEMENTER_NODE_NAME
    ):
        raise AgentRuntimeContractError(
            "Implementer Agent must follow Provider Call Consume (Implementer)"
        )
    if _has_main_edge(connections, PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME, IMPLEMENTER_NODE_NAME):
        raise AgentRuntimeContractError(
            "Implementer Agent must not bypass provider-call-consume"
        )
    if _has_main_edge(connections, "Candidate Schema Validation", IMPLEMENTER_NODE_NAME):
        raise AgentRuntimeContractError(
            "Implementer Agent must not bypass budget/permit gates"
        )
    if not _has_main_edge(connections, IMPLEMENTER_NODE_NAME, "Proposal Schema Validation"):
        raise AgentRuntimeContractError("Implementer Agent must feed Proposal Schema Validation")
    if not _has_main_edge(
        connections, "Execution Result Validation", PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME
    ):
        raise AgentRuntimeContractError(
            "Provider Call Permit (Reviewer) must follow Execution Result Validation"
        )
    if not _has_main_edge(
        connections,
        PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME,
        PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME,
    ):
        raise AgentRuntimeContractError(
            "Provider Call Consume (Reviewer) must follow Provider Call Permit (Reviewer)"
        )
    if not _has_main_edge(
        connections, PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME, REVIEWER_NODE_NAME
    ):
        raise AgentRuntimeContractError(
            "Independent Reviewer Agent must follow Provider Call Consume (Reviewer)"
        )
    if _has_main_edge(connections, PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME, REVIEWER_NODE_NAME):
        raise AgentRuntimeContractError(
            "Independent Reviewer Agent must not bypass provider-call-consume"
        )
    if _has_main_edge(connections, "Execution Result Validation", REVIEWER_NODE_NAME):
        raise AgentRuntimeContractError(
            "Independent Reviewer Agent must not bypass provider-call-permit"
        )
    if not _has_main_edge(connections, REVIEWER_NODE_NAME, "Independent Review Bind"):
        raise AgentRuntimeContractError(
            "Independent Reviewer Agent must feed Independent Review Bind"
        )
    if not _has_main_edge(connections, OPEN_PILOT_BUDGET_NODE_NAME, ANNOTATE_BUDGET_DENIED_NODE_NAME):
        raise AgentRuntimeContractError("budget open deny must route to Annotate Budget Denied")
    if not _has_main_edge(
        connections, PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME, ANNOTATE_BUDGET_DENIED_NODE_NAME
    ):
        raise AgentRuntimeContractError("implementer permit deny must route to Annotate Budget Denied")
    if not _has_main_edge(
        connections, PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME, ANNOTATE_BUDGET_DENIED_NODE_NAME
    ):
        raise AgentRuntimeContractError("reviewer permit deny must route to Annotate Budget Denied")
    if not _has_main_edge(
        connections, PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME, ANNOTATE_BUDGET_DENIED_NODE_NAME
    ):
        raise AgentRuntimeContractError("implementer consume deny must route to Annotate Budget Denied")
    if not _has_main_edge(
        connections, PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME, ANNOTATE_BUDGET_DENIED_NODE_NAME
    ):
        raise AgentRuntimeContractError("reviewer consume deny must route to Annotate Budget Denied")
    if not _has_main_edge(connections, ANNOTATE_BUDGET_DENIED_NODE_NAME, "Failure Router"):
        raise AgentRuntimeContractError("Annotate Budget Denied must route to Failure Router")
    denied_code = str((budget_denied.get("parameters") or {}).get("jsCode") or "")
    if "POLICY_REJECTED" not in denied_code:
        raise AgentRuntimeContractError("budget deny annotation must set POLICY_REJECTED")

    # Secret-like values must not appear in workflow nodes/meta/fixtures surface.
    _assert_no_secret_literals({"workflow": {"meta": data.get("meta"), "nodes": data.get("nodes")}})
    return {
        "implementer_node": IMPLEMENTER_NODE_NAME,
        "reviewer_node": REVIEWER_NODE_NAME,
        "worker_authorize": WORKER_AUTHORIZE_NODE_NAME,
        "budget_open": OPEN_PILOT_BUDGET_NODE_NAME,
        "provider_call_permit_implementer": PROVIDER_CALL_PERMIT_IMPLEMENTER_NODE_NAME,
        "provider_call_permit_reviewer": PROVIDER_CALL_PERMIT_REVIEWER_NODE_NAME,
        "provider_call_consume_implementer": PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME,
        "provider_call_consume_reviewer": PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME,
        "bind_review": INDEPENDENT_REVIEW_BIND_NODE_NAME,
        "runtime_identity_independence_proven": RUNTIME_IDENTITY_INDEPENDENCE_CLAIM,
    }


def assert_phase_1b_contract_surface(*, root: Path | None = None) -> dict[str, Any]:
    """Validate pinned Phase 1B contract + inactive workflow AI/HTTP wiring (offline)."""
    contract = validate_agent_runtime_contract(root=root)
    meta = assert_workflow_meta_bindings(root=root, require_pinned_models=True)
    wiring = assert_workflow_agent_wiring(root=root)
    return {"contract": contract, "workflow_meta": meta, "workflow_wiring": wiring}


def assert_phase_1a_contract_surface(*, root: Path | None = None) -> dict[str, Any]:
    """Compatibility alias — Phase 1B supersedes the Phase 1A contract-only surface."""
    return assert_phase_1b_contract_surface(root=root)


def lookalike_credential_reference_cases(pinned: str) -> list[str]:
    """Case, whitespace, and Unicode-adjacent variants that must not match the pin."""
    en_dash = pinned.replace("\u2014", "\u2013")
    hyphen = pinned.replace("\u2014", "-")
    nfd = unicodedata.normalize("NFD", pinned)
    return [
        pinned.upper(),
        pinned.lower(),
        f" {pinned}",
        f"{pinned} ",
        f"  {pinned}  ",
        en_dash,
        hyphen,
        nfd if nfd != pinned else pinned + "\u200b",
    ]
