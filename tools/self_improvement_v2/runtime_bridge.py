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
from tools.self_improvement_v2.path_policy import classify_and_authorize, load_policy, policy_sha256
from tools.self_improvement_v2.repair_policy import assert_repair_attempt_allowed
from tools.self_improvement_v2.review_gate import assert_no_conflicting_review, assert_review_bound
from tools.self_improvement_v2.runtime_config import (
    RuntimeConfig,
    build_arg_parser,
    is_forbidden_request_field,
    load_runtime_config,
    redact_log_text,
)
from tools.self_improvement_v2.schema_loader import ensure_schema_version, validate_instance

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
    ],
}

_EXECUTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_VALIDATE_FIELDS = frozenset({"proposal"})
_EXECUTE_FIELDS = frozenset({"proposal", "candidate"})
_FINALIZE_FIELDS = frozenset({"execution_id", "review_id", "review"})


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
    policy = load_policy(config.repository_root)
    proposal = ensure_schema_version(proposal)
    validate_instance("proposal", proposal, root=config.repository_root)
    assert_repair_attempt_allowed(int(proposal.get("repair_attempt") or 0))
    classify_and_authorize(proposal, policy)
    return {
        "status": "PASS",
        "proposal_id": proposal["proposal_id"],
        "proposal_sha256": content_sha256(proposal),
        "policy_sha256": policy_sha256(config.repository_root),
    }


def execute_operation(config: RuntimeConfig, proposal: dict[str, Any], candidate: dict[str, Any] | None) -> dict[str, Any]:
    proposal = ensure_schema_version(proposal)
    validate_instance("proposal", proposal, root=config.repository_root)
    if proposal.get("risk_level") != "LOW":
        raise WorkerError(
            ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
            "execute allows LOW risk only",
            state="DECISION_REQUIRED",
        )
    bundle = execute_proposal(
        root=config.repository_root,
        proposal=proposal,
        state_db=config.state_db,
        candidate=candidate,
    )
    # Never expose absolute worktree paths over HTTP.
    safe = {k: v for k, v in bundle.items() if k != "worktree_path"}
    safe["worktree_path_redacted"] = "<redacted>"
    return {"status": "PASS", "execution": safe}


def finalize_operation(
    config: RuntimeConfig,
    *,
    execution_id: str,
    review_id: str,
    review: dict[str, Any] | None,
) -> dict[str, Any]:
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
    return {"status": "PASS", "finalization": result}


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


class WorkerBridge:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

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

            if method == "POST" and path in {"/v2/validate-proposal", "/v2/execute", "/v2/finalize"}:
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
    def __init__(self, config: RuntimeConfig) -> None:
        if config.worker_host != "127.0.0.1":
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "refusing non-loopback bind")
        self.config = config
        self.bridge = WorkerBridge(config)
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
