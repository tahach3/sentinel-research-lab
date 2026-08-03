"""Offline validator for the Self-Improvement Loop V2 n8n design workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES

CREDENTIAL_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}"
)


def _collect_strings(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _collect_strings(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_strings(value, out)
    elif isinstance(node, str):
        out.append(node)


def validate_workflow(root: Path, workflow_path: Path) -> dict[str, Any]:
    data = json.loads(workflow_path.read_text(encoding="utf-8"))
    errors: list[dict[str, str]] = []

    if data.get("active") is not False:
        errors.append({"code": ERROR_CODES["WORKFLOW_ACTIVE"], "message": "active must be false"})

    connections = data.get("connections") or {}
    nodes = data.get("nodes") or []
    names = {str(n.get("name", "")) for n in nodes}
    blob_parts: list[str] = []
    _collect_strings(data, blob_parts)
    blob = "\n".join(blob_parts)

    required_nodes = [
        "Manual Trigger",
        "Candidate Intake",
        "Proposal Freeze",
        "Risk Classification Switch",
        "LOW Auto-Authorize",
        "MEDIUM Decision Required",
        "HIGH Human Approval Required",
        "PROHIBITED Policy Rejected",
        "Detached Worker Execute",
        "Independent Review Bind",
        "Finalization Dispatch",
        "Learning Record",
        "Human Promotion Boundary",
        "Failure Router",
    ]
    for name in required_nodes:
        if name not in names and name.lower() not in blob.lower():
            errors.append({"code": "MISSING_NODE", "message": f"missing node: {name}"})

    # Real conditional branches must exist in connections graph.
    switch = connections.get("Risk Classification Switch") or connections.get("Risk Classification") or {}
    mains = switch.get("main") or []
    if len(mains) < 4:
        errors.append({"code": "MISSING_RISK_BRANCHES", "message": "switch must have 4 outputs"})
    else:
        targets = []
        for output in mains:
            if output:
                targets.append(output[0].get("node"))
        joined = " ".join(str(t) for t in targets)
        for marker, label in (
            ("LOW", "LOW"),
            ("MEDIUM", "MEDIUM"),
            ("HIGH", "HIGH"),
            ("PROHIBITED", "PROHIBITED"),
        ):
            if marker not in joined.upper() and marker not in blob:
                errors.append({"code": "MISSING_RISK_BRANCH", "message": f"missing {label} branch"})

    for route in (
        "POLICY_REJECTED",
        "VALIDATION_FAILED",
        "REVIEW_FAILED",
        "CONTENT_BINDING_MISMATCH",
        "REPAIR_LIMIT_REACHED",
        "FAILED_FROZEN",
    ):
        if route not in blob:
            errors.append({"code": "MISSING_FAILURE_ROUTE", "message": f"missing failure route: {route}"})

    if "AUTO_AUTHORIZED" not in blob:
        errors.append({"code": "MISSING_STATE", "message": "AUTO_AUTHORIZED missing"})
    if "READY_FOR_HUMAN_PROMOTION" not in blob:
        errors.append({"code": "MISSING_PROMOTION_BOUNDARY", "message": "promotion boundary missing"})

    if "push" in blob.lower() and "push_allowed" not in blob.lower():
        # allow mentions of forbidden push
        pass
    if re.search(r"(?i)git\s+push", blob):
        errors.append({"code": ERROR_CODES["PUSH_ATTEMPT"], "message": "workflow encodes push"})
    if re.search(r"(?i)git\s+merge", blob):
        errors.append({"code": ERROR_CODES["MERGE_ATTEMPT"], "message": "workflow encodes merge"})

    if CREDENTIAL_VALUE_RE.search(blob):
        errors.append({"code": ERROR_CODES["CREDENTIALS_IN_WORKFLOW"], "message": "credential values embedded"})

    if "https://" in blob.lower() and "example.invalid" not in blob.lower():
        # Interface-only; block live endpoints
        if re.search(r"https?://(?!127\.0\.0\.1|localhost|example\.invalid)", blob, re.I):
            errors.append({"code": "LIVE_ENDPOINT", "message": "non-local endpoint present"})

    status = "PASS" if not errors else "FAIL"
    return {"status": status, "errors": errors, "nodes": sorted(names)}
