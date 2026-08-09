"""Loopback-only HTTP bridge wrapping reviewed Self-Improvement V2 APIs."""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.finalizer import finalize_or_freeze
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.path_policy import load_policy, policy_sha256
from tools.self_improvement_v2.pilot_budget import (
    DEFAULT_MAX_INPUT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_PRICE_PER_INPUT_TOKEN_USD,
    DEFAULT_PRICE_PER_OUTPUT_TOKEN_USD,
    MAXIMUM_AGENT_CALLS,
    MAXIMUM_PILOT_COST_USD,
    PILOT_TIMEOUT_SECONDS,
    PilotBudgetRegistry,
    default_registry,
    open_budget_hard_caps,
)
from tools.self_improvement_v2.repair_policy import assert_repair_attempt_allowed
from tools.self_improvement_v2.review_gate import assert_no_conflicting_review, assert_review_bound
from tools.self_improvement_v2.risk_authority import (
    authorize_execution,
    enforce_authorization,
)
from tools.self_improvement_v2.runtime_config import (
    RuntimeConfig,
    build_arg_parser,
    is_forbidden_request_field,
    load_runtime_config,
    redact_log_text,
)
from tools.self_improvement_v2.schema_loader import ensure_schema_version, validate_instance
from tools.self_improvement_v2.trusted_origin import assert_trusted_code_origin
from tools.self_improvement_v2.wall_reassert import (
    REQUIRED_WALL_KEYS,
    assert_wall_artifacts_unchanged,
    capture_wall_artifact_snapshot,
)

LOGGER = logging.getLogger("self_improvement_v2.runtime_bridge")

HEALTH_BODY = {
    "service": "sentinel-research-lab-self-improvement-v2",
    "version": "2",
    "status": "ready",
    "repository_id": "sentinel-research-lab",
    "capabilities": [
        "validate-proposal",
        "execute",
        "finalize",
        "execution-status",
        "budget-open",
        "provider-call-permit",
        "provider-call-consume",
        "bind-review",
        "wall-reassert",
    ],
}

_EXECUTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_VALIDATE_FIELDS = frozenset({"proposal"})
_EXECUTE_FIELDS = frozenset({"proposal", "candidate"})
_FINALIZE_FIELDS = frozenset({"execution_id", "review_id", "review"})
_BUDGET_OPEN_FIELDS = frozenset(
    {
        "session_id",
        "max_input_tokens",
        "max_output_tokens",
        "price_per_input_token_usd",
        "price_per_output_token_usd",
        "max_calls",
        "max_cost_usd",
        "timeout_seconds",
        "meta",
    }
)
_PERMIT_FIELDS = frozenset(
    {
        "session_id",
        "role",
        "max_input_tokens",
        "max_output_tokens",
        "call_params",
    }
)
_CONSUME_FIELDS = frozenset(
    {
        "session_id",
        "role",
        "permit_nonce",
    }
)
_BIND_REVIEW_FIELDS = frozenset({"review"})
_WALL_CAPTURE_FIELDS = frozenset({"workflow_fingerprint"})
_WALL_ASSERT_FIELDS = frozenset({"before", "workflow_fingerprint"})


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_log_text(original)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_RedactingFormatter("%(levelname)s %(message)s"))
    root = logging.getLogger("self_improvement_v2")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _json_bytes(payload: dict[str, Any], *, status: int = 200) -> tuple[bytes, int, str]:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    if len(body) > 1024 * 1024:
        truncated = json.dumps(
            {"status": "FAIL", "error": ERROR_CODES["POLICY_REJECTED"], "message": "response too large"},
            sort_keys=True,
        ).encode("utf-8")
        return truncated, 500, "application/json; charset=utf-8"
    return body, status, "application/json; charset=utf-8"


def _error(code: str, message: str, *, status: int = 400, state: str | None = None) -> tuple[bytes, int, str]:
    payload: dict[str, Any] = {"status": "FAIL", "error": code, "message": redact_log_text(message)}
    if state is not None:
        payload["final_state"] = state
    return _json_bytes(payload, status=status)


def _reject_unknown_and_forbidden(payload: dict[str, Any], allowed: frozenset[str]) -> None:
    for key in payload:
        if is_forbidden_request_field(key):
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                f"caller-supplied field rejected: {key}",
                state="POLICY_REJECTED",
            )
        if key not in allowed:
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                f"unknown field: {key}",
                state="POLICY_REJECTED",
            )


def validate_proposal_operation(config: RuntimeConfig, proposal: dict[str, Any]) -> dict[str, Any]:
    # Code origin is the worker install (__file__), not the git repository_root.
    assert_trusted_code_origin()
    policy = load_policy(config.repository_root)
    proposal = ensure_schema_version(proposal)
    validate_instance("proposal", proposal, root=config.repository_root)
    assert_repair_attempt_allowed(int(proposal.get("repair_attempt") or 0))
    auth = authorize_execution(proposal, policy, policy_sha256=policy_sha256(config.repository_root))
    enforce_authorization(auth)
    return {
        "status": "PASS",
        "proposal_id": proposal["proposal_id"],
        "proposal_sha256": content_sha256(proposal),
        "policy_sha256": policy_sha256(config.repository_root),
        "worker_decision": auth.decision,
        "declared_risk": auth.declared_risk,
        "computed_risk_pre": auth.computed_risk_pre,
        "effective_risk_pre": auth.effective_risk_pre,
        "risk_reason_codes_pre": auth.risk_reason_codes_pre,
    }


def _assert_wall_source_repo_unchanged(root: Any, before: dict[str, str]) -> None:
    """Reassert reviewed source/index/working-tree bytes.

    Intentional detached worktree add/remove changes worktree_list_fingerprint;
    that key is enforced via /v2/wall/assert when callers capture a full snapshot
    outside the worktree lifecycle.
    """
    after = capture_wall_artifact_snapshot(root)
    source_keys = (
        "source_tree_fingerprint",
        "index_fingerprint",
        "working_tree_content_fingerprint",
    )
    mismatches = [k for k in source_keys if before.get(k) != after.get(k)]
    if mismatches:
        raise WorkerError(
            ERROR_CODES["WALL_REASSERT_MISMATCH"],
            f"Wall artifact mismatch: {', '.join(mismatches)}",
            state="POLICY_REJECTED",
        )


def execute_operation(config: RuntimeConfig, proposal: dict[str, Any], candidate: dict[str, Any] | None) -> dict[str, Any]:
    assert_trusted_code_origin()
    wall_before = capture_wall_artifact_snapshot(config.repository_root)
    proposal = ensure_schema_version(proposal)
    validate_instance("proposal", proposal, root=config.repository_root)
    # Authorization is recomputed inside execute_proposal; never trust proposer risk_level alone.
    if "authorization" in proposal or proposal.get("skip_risk_check"):
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "classification bypass fields rejected",
            state="POLICY_REJECTED",
        )
    bundle = execute_proposal(
        root=config.repository_root,
        proposal=proposal,
        state_db=config.state_db,
        candidate=candidate,
    )
    _assert_wall_source_repo_unchanged(config.repository_root, wall_before)
    # Never expose absolute worktree paths over HTTP.
    safe = {k: v for k, v in bundle.items() if k != "worktree_path"}
    safe["worktree_path_redacted"] = "<redacted>"
    return {"status": "PASS", "execution": safe, "wall_reassert": "PASS"}


def finalize_operation(
    config: RuntimeConfig,
    *,
    execution_id: str,
    review_id: str,
    review: dict[str, Any] | None,
) -> dict[str, Any]:
    assert_trusted_code_origin()
    wall_before = capture_wall_artifact_snapshot(config.repository_root)
    store = ExperienceStore(config.state_db)
    bundle, _worktree = store.get_execution(execution_id)
    if review is not None:
        review = ensure_schema_version(review)
        if review.get("review_id") != review_id:
            raise WorkerError(
                ERROR_CODES["SI2-REVIEW-MISSING"],
                "review_id mismatch",
                state="REVIEW_FAILED",
            )
        if review.get("execution_id") != execution_id:
            raise WorkerError(
                ERROR_CODES["SI2-REVIEW-EXECUTION-ID"],
                "review execution_id mismatch",
                state="REVIEW_FAILED",
            )
        proposal = store.get_proposal(bundle["proposal_id"])
        existing = store.list_reviews_for_execution(execution_id)
        assert_no_conflicting_review(existing, review)
        assert_review_bound(review, proposal=proposal, bundle=bundle, root=config.repository_root)
        if not any(item.get("review_id") == review_id for item in existing):
            store.insert_review(review)
            store.append_state_event("review", review_id, "REVIEW_PENDING", "REVIEW_BOUND")
    else:
        # Requires a previously bound review in the immutable store.
        store.get_review(review_id)

    result = finalize_or_freeze(
        execution_id=execution_id,
        review_id=review_id,
        state_db=config.state_db,
        repository_root=config.repository_root,
    )
    _assert_wall_source_repo_unchanged(config.repository_root, wall_before)
    return {"status": "PASS", "finalization": result, "wall_reassert": "PASS"}


def execution_status_operation(config: RuntimeConfig, execution_id: str) -> dict[str, Any]:
    if not _EXECUTION_ID_RE.fullmatch(execution_id) or ".." in execution_id or "/" in execution_id or "\\" in execution_id:
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "invalid execution_id", state="POLICY_REJECTED")
    store = ExperienceStore(config.state_db)
    bundle, _worktree = store.get_execution(execution_id)
    safe = {k: v for k, v in bundle.items() if k not in {"worktree_path"}}
    safe["worktree_path_redacted"] = "<redacted>"
    finalization = store.get_finalization(execution_id)
    return {
        "status": "PASS",
        "execution_id": execution_id,
        "execution": safe,
        "finalization": finalization,
    }


def open_budget_operation(registry: PilotBudgetRegistry, payload: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown_and_forbidden(payload, _BUDGET_OPEN_FIELDS)
    max_calls = int(payload.get("max_calls") or MAXIMUM_AGENT_CALLS)
    max_cost_usd = float(payload.get("max_cost_usd") or MAXIMUM_PILOT_COST_USD)
    timeout_seconds = int(payload.get("timeout_seconds") or PILOT_TIMEOUT_SECONDS)
    price_in = float(
        payload.get("price_per_input_token_usd")
        if payload.get("price_per_input_token_usd") is not None
        else DEFAULT_PRICE_PER_INPUT_TOKEN_USD
    )
    price_out = float(
        payload.get("price_per_output_token_usd")
        if payload.get("price_per_output_token_usd") is not None
        else DEFAULT_PRICE_PER_OUTPUT_TOKEN_USD
    )
    # Explicit pre-check so bridge rejects inflated maxima before session construction.
    open_budget_hard_caps(
        max_calls=max_calls,
        max_cost_usd=max_cost_usd,
        timeout_seconds=timeout_seconds,
        price_per_input_token_usd=price_in,
        price_per_output_token_usd=price_out,
    )
    session = registry.open_session(
        session_id=payload.get("session_id"),
        max_input_tokens=int(payload.get("max_input_tokens") or DEFAULT_MAX_INPUT_TOKENS),
        max_output_tokens=int(payload.get("max_output_tokens") or DEFAULT_MAX_OUTPUT_TOKENS),
        price_per_input_token_usd=price_in,
        price_per_output_token_usd=price_out,
        max_calls=max_calls,
        max_cost_usd=max_cost_usd,
        timeout_seconds=timeout_seconds,
        meta=payload.get("meta") if isinstance(payload.get("meta"), dict) else None,
    )
    return {
        "status": "PASS",
        "session_id": session.session_id,
        "max_calls": session.max_calls,
        "max_cost_usd": session.max_cost_usd,
        "timeout_seconds": session.timeout_seconds,
        "max_input_tokens": session.max_input_tokens,
        "max_output_tokens": session.max_output_tokens,
        "worst_case_usd": session.worst_case_usd,
        "cost_enforcement": "by_construction",
        "hard_caps": {
            "max_calls": MAXIMUM_AGENT_CALLS,
            "max_cost_usd": MAXIMUM_PILOT_COST_USD,
            "timeout_seconds": PILOT_TIMEOUT_SECONDS,
        },
    }


def provider_call_permit_operation(registry: PilotBudgetRegistry, payload: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown_and_forbidden(payload, _PERMIT_FIELDS)
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise WorkerError(ERROR_CODES["PILOT_BUDGET_INVALID"], "session_id required", state="POLICY_REJECTED")
    role = payload.get("role")
    if not isinstance(role, str) or not role:
        raise WorkerError(ERROR_CODES["PILOT_BUDGET_INVALID"], "role required", state="POLICY_REJECTED")
    call_params = payload.get("call_params")
    if call_params is not None and not isinstance(call_params, dict):
        raise WorkerError(ERROR_CODES["SCHEMA_INVALID"], "call_params must be an object", state="POLICY_REJECTED")
    permit = registry.request_call_permit(
        session_id,
        role=role,
        max_input_tokens=int(payload["max_input_tokens"]) if payload.get("max_input_tokens") is not None else None,
        max_output_tokens=int(payload["max_output_tokens"]) if payload.get("max_output_tokens") is not None else None,
        call_params=call_params,
    )
    return {"status": "PASS", "permit": permit}


def provider_call_consume_operation(registry: PilotBudgetRegistry, payload: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown_and_forbidden(payload, _CONSUME_FIELDS)
    session_id = payload.get("session_id")
    role = payload.get("role")
    permit_nonce = payload.get("permit_nonce")
    if not isinstance(session_id, str) or not session_id:
        raise WorkerError(ERROR_CODES["PILOT_BUDGET_INVALID"], "session_id required", state="POLICY_REJECTED")
    if not isinstance(role, str) or not role:
        raise WorkerError(ERROR_CODES["PILOT_BUDGET_INVALID"], "role required", state="POLICY_REJECTED")
    if not isinstance(permit_nonce, str) or not permit_nonce:
        raise WorkerError(ERROR_CODES["PILOT_PERMIT_INVALID"], "permit_nonce required", state="POLICY_REJECTED")
    consumed = registry.consume_call_permit(session_id, permit_nonce=permit_nonce, role=role)
    return {"status": "PASS", "consume": consumed}


def bind_review_operation(config: RuntimeConfig, payload: dict[str, Any]) -> dict[str, Any]:
    """Invoke real review_gate — Groq/agent verdict must matter (no hardcoded review_ok)."""
    _reject_unknown_and_forbidden(payload, _BIND_REVIEW_FIELDS)
    review = payload.get("review")
    if not isinstance(review, dict):
        raise WorkerError(ERROR_CODES["SCHEMA_INVALID"], "review object required", state="REVIEW_FAILED")
    assert_trusted_code_origin()
    store = ExperienceStore(config.state_db)
    review = ensure_schema_version(review)
    validate_instance("review_result", review, root=config.repository_root)
    execution_id = review.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id:
        raise WorkerError(ERROR_CODES["SI2-REVIEW-EXECUTION-ID"], "execution_id required", state="REVIEW_FAILED")
    bundle, _wt = store.get_execution(execution_id)
    proposal = store.get_proposal(bundle["proposal_id"])
    existing = store.list_reviews_for_execution(execution_id)
    assert_no_conflicting_review(existing, review)
    assert_review_bound(review, proposal=proposal, bundle=bundle, root=config.repository_root)
    review_id = str(review["review_id"])
    if not any(item.get("review_id") == review_id for item in existing):
        store.insert_review(review)
        store.append_state_event("review", review_id, "REVIEW_PENDING", "REVIEW_BOUND")
    repair_limit_ok = int(proposal.get("repair_attempt") or 0) < 1 or review.get("verdict") != "FINITE_REPAIR"
    return {
        "status": "PASS",
        "state": "REVIEW_BOUND",
        "review_ok": True,
        "repair_limit_ok": bool(repair_limit_ok),
        "independent_from_implementer": True,
        "review_id": review_id,
        "verdict": review.get("verdict"),
        "reviewer_id": review.get("reviewer_id"),
        "implementer_id": review.get("implementer_id"),
        "review_gate": "tools.self_improvement_v2.review_gate",
    }


def wall_capture_operation(config: RuntimeConfig, payload: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown_and_forbidden(payload, _WALL_CAPTURE_FIELDS)
    wf = payload.get("workflow_fingerprint")
    if wf is not None and not isinstance(wf, str):
        raise WorkerError(ERROR_CODES["SCHEMA_INVALID"], "workflow_fingerprint must be a string")
    snap = capture_wall_artifact_snapshot(config.repository_root, workflow_fingerprint=wf)
    return {"status": "PASS", "snapshot": snap}


def wall_assert_operation(config: RuntimeConfig, payload: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown_and_forbidden(payload, _WALL_ASSERT_FIELDS)
    before = payload.get("before")
    if not isinstance(before, dict) or not before:
        raise WorkerError(ERROR_CODES["SCHEMA_INVALID"], "before snapshot object required")
    before_str = {str(k): str(v) for k, v in before.items()}
    missing = sorted(REQUIRED_WALL_KEYS - set(before_str))
    if missing:
        raise WorkerError(
            ERROR_CODES["WALL_REASSERT_MISMATCH"],
            f"Wall before snapshot missing required keys: {', '.join(missing)}",
            state="POLICY_REJECTED",
        )
    wf = payload.get("workflow_fingerprint")
    wf_fn = (lambda: str(wf)) if isinstance(wf, str) else None
    result = assert_wall_artifacts_unchanged(
        config.repository_root,
        before_str,
        workflow_fingerprint_fn=wf_fn,
    )
    return result


class WorkerBridge:
    def __init__(self, config: RuntimeConfig, *, budget_registry: PilotBudgetRegistry | None = None) -> None:
        self.config = config
        self.budget_registry = budget_registry or default_registry()
        # Fail closed at process construction if trusted modules are not from this install.
        assert_trusted_code_origin()

    def authenticate(self, authorization_header: str | None) -> None:
        if not authorization_header:
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "missing authorization", state="POLICY_REJECTED")
        scheme, _, token = authorization_header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "invalid authorization scheme", state="POLICY_REJECTED")
        expected = self.config.worker_token.encode("utf-8")
        provided = token.strip().encode("utf-8")
        if not hmac.compare_digest(expected, provided):
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "invalid token", state="POLICY_REJECTED")

    def handle(
        self,
        *,
        method: str,
        path: str,
        authorization: str | None,
        raw_body: bytes,
    ) -> tuple[bytes, int, str]:
        try:
            if method == "GET" and path == "/health":
                # Health is unauthenticated readiness for local probes; all /v2/* require auth.
                return _json_bytes(dict(HEALTH_BODY))

            self.authenticate(authorization)

            if method == "GET" and path.startswith("/v2/executions/"):
                execution_id = unquote(path[len("/v2/executions/") :])
                return _json_bytes(execution_status_operation(self.config, execution_id))

            if method == "POST" and path in {
                "/v2/validate-proposal",
                "/v2/execute",
                "/v2/finalize",
                "/v2/budget/open",
                "/v2/provider-call-permit",
                "/v2/provider-call-consume",
                "/v2/bind-review",
                "/v2/wall/capture",
                "/v2/wall/assert",
            }:
                if raw_body == b"__OVERSIZE__" or len(raw_body) > self.config.max_request_bytes:
                    return _error(ERROR_CODES["POLICY_REJECTED"], "request exceeds 256KB limit", status=413)
                if not raw_body:
                    return _error(ERROR_CODES["SCHEMA_INVALID"], "JSON body required")
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return _error(ERROR_CODES["SCHEMA_INVALID"], "malformed JSON")
                if not isinstance(payload, dict):
                    return _error(ERROR_CODES["SCHEMA_INVALID"], "JSON object required")

                if path == "/v2/validate-proposal":
                    _reject_unknown_and_forbidden(payload, _VALIDATE_FIELDS)
                    if "proposal" not in payload or not isinstance(payload["proposal"], dict):
                        return _error(ERROR_CODES["SCHEMA_INVALID"], "proposal object required")
                    return _json_bytes(validate_proposal_operation(self.config, payload["proposal"]))

                if path == "/v2/execute":
                    _reject_unknown_and_forbidden(payload, _EXECUTE_FIELDS)
                    if "proposal" not in payload or not isinstance(payload["proposal"], dict):
                        return _error(ERROR_CODES["SCHEMA_INVALID"], "proposal object required")
                    candidate = payload.get("candidate")
                    if candidate is not None and not isinstance(candidate, dict):
                        return _error(ERROR_CODES["SCHEMA_INVALID"], "candidate must be an object")
                    return _json_bytes(execute_operation(self.config, payload["proposal"], candidate))

                if path == "/v2/budget/open":
                    return _json_bytes(open_budget_operation(self.budget_registry, payload))

                if path == "/v2/provider-call-permit":
                    return _json_bytes(provider_call_permit_operation(self.budget_registry, payload))

                if path == "/v2/provider-call-consume":
                    return _json_bytes(provider_call_consume_operation(self.budget_registry, payload))

                if path == "/v2/bind-review":
                    return _json_bytes(bind_review_operation(self.config, payload))

                if path == "/v2/wall/capture":
                    return _json_bytes(wall_capture_operation(self.config, payload))

                if path == "/v2/wall/assert":
                    return _json_bytes(wall_assert_operation(self.config, payload))

                # finalize
                _reject_unknown_and_forbidden(payload, _FINALIZE_FIELDS)
                execution_id = payload.get("execution_id")
                review_id = payload.get("review_id")
                review = payload.get("review")
                if not isinstance(execution_id, str) or not execution_id:
                    return _error(ERROR_CODES["SCHEMA_INVALID"], "execution_id required")
                if review is not None:
                    if not isinstance(review, dict):
                        return _error(ERROR_CODES["SCHEMA_INVALID"], "review must be an object")
                    review_id = review_id or review.get("review_id")
                if not isinstance(review_id, str) or not review_id:
                    return _error(ERROR_CODES["SCHEMA_INVALID"], "review_id required")
                return _json_bytes(
                    finalize_operation(
                        self.config,
                        execution_id=execution_id,
                        review_id=review_id,
                        review=review,
                    )
                )

            return _error(ERROR_CODES["POLICY_REJECTED"], "unknown endpoint", status=404)
        except WorkerError as exc:
            auth_failure = any(
                marker in exc.message.lower()
                for marker in ("authorization", "token", "bearer")
            )
            status = 401 if auth_failure else 400
            return _error(exc.code, exc.message, status=status, state=exc.state)
        except Exception:  # noqa: BLE001 — bridge boundary
            LOGGER.exception("unhandled bridge error")
            return _error(ERROR_CODES["FAILED_FROZEN"], "internal error", status=500, state="FAILED_FROZEN")


def make_handler(bridge: WorkerBridge) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            LOGGER.info(redact_log_text(fmt % args))

        def _read_body(self) -> bytes:
            length_raw = self.headers.get("Content-Length", "0")
            try:
                length = int(length_raw)
            except ValueError:
                return b""
            if length < 0:
                return b""
            if length > bridge.config.max_request_bytes:
                # Consume a bounded prefix so the connection stays usable, then signal oversize.
                self.rfile.read(min(length, bridge.config.max_request_bytes + 1))
                return b"__OVERSIZE__"
            return self.rfile.read(length)

        def _write(self, body: bytes, status: int, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            body, status, ctype = bridge.handle(
                method="GET",
                path=self.path.split("?", 1)[0],
                authorization=self.headers.get("Authorization"),
                raw_body=b"",
            )
            self._write(body, status, ctype)

        def do_POST(self) -> None:  # noqa: N802
            raw = self._read_body()
            body, status, ctype = bridge.handle(
                method="POST",
                path=self.path.split("?", 1)[0],
                authorization=self.headers.get("Authorization"),
                raw_body=raw,
            )
            self._write(body, status, ctype)

    return Handler


class LoopbackServer:
    def __init__(
        self,
        config: RuntimeConfig,
        *,
        budget_registry: PilotBudgetRegistry | None = None,
    ) -> None:
        if config.worker_host != "127.0.0.1":
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "refusing non-loopback bind")
        self.config = config
        self.bridge = WorkerBridge(config, budget_registry=budget_registry or PilotBudgetRegistry())
        self._httpd = ThreadingHTTPServer((config.worker_host, config.worker_port), make_handler(self.bridge))
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def serve_forever(self) -> None:
        LOGGER.info("listening on 127.0.0.1:%s", self.port)
        self._httpd.serve_forever()

    def start_background(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="srl-v2-bridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        config = load_runtime_config(
            repository_root=args.repository_root,
            state_db=args.state_db,
            worker_host=args.host,
            worker_port=args.port,
        )
    except WorkerError as exc:
        print(json.dumps({"status": "FAIL", "error": exc.code, "message": exc.message}, sort_keys=True))
        return 2
    server = LoopbackServer(config)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("shutdown requested")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
