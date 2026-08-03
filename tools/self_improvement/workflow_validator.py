"""Offline validator for the self-improvement n8n design workflow."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from tools.self_improvement.models import ERROR_CODES, WorkerError

REQUIRED_STAGE_MARKERS = [
    "candidate intake",
    "candidate schema validation",
    "research-agent dispatch",
    "implementation-proposal validation",
    "risk classification",
    "LOW-risk auto-authorization",
    "local-worker dispatch",
    "execution-result validation",
    "independent-review-agent dispatch",
    "review-result validation",
    "finalization dispatch",
    "learning-record persistence",
    "human notification",
]

CREDENTIAL_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}"
)
PRODUCTION_URL_RE = re.compile(r"https?://(?!127\.0\.0\.1|localhost)[a-z0-9.-]+", re.I)
PAID_API_RE = re.compile(r"(?i)(openai|anthropic|openrouter|groq\.com|generativelanguage)")


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

    if data.get("active") is True:
        errors.append({"code": ERROR_CODES["WORKFLOW_ACTIVE"], "message": "workflow active must be false"})
    if data.get("active") is not False:
        errors.append({"code": ERROR_CODES["WORKFLOW_ACTIVE"], "message": "active field missing or not false"})

    nodes = data.get("nodes") or []
    names = [str(n.get("name", "")) for n in nodes]
    blob_parts: list[str] = []
    _collect_strings(data, blob_parts)
    blob = "\n".join(blob_parts)

    for marker in REQUIRED_STAGE_MARKERS:
        if marker.lower() not in blob.lower():
            errors.append({"code": "MISSING_STAGE", "message": f"missing stage: {marker}"})

    if "READY_FOR_HUMAN_PROMOTION" not in blob and "human promotion" not in blob.lower():
        errors.append({"code": "MISSING_PROMOTION_BOUNDARY", "message": "human promotion boundary missing"})

    for state in (
        "CANDIDATE_RECEIVED",
        "PROPOSAL_VALIDATED",
        "AUTO_AUTHORIZED",
        "INDEPENDENT_REVIEW",
        "FAILED_FROZEN",
    ):
        if state not in blob:
            errors.append({"code": "MISSING_STATE", "message": f"missing state marker: {state}"})

    if "implementer" not in blob.lower() or "reviewer" not in blob.lower():
        errors.append({"code": "MISSING_AGENT_IDS", "message": "implementer/reviewer identifiers missing"})

    if "improvement_candidate.schema.json" not in blob and "implementation_proposal.schema.json" not in blob:
        errors.append({"code": "MISSING_SCHEMA_REF", "message": "proposal/result schema references missing"})

    if "failure" not in blob.lower() and "FAILED_FROZEN" not in blob:
        errors.append({"code": "MISSING_FAILURE_ROUTE", "message": "failure routes missing"})

    # Worker interface contract
    for key in ("proposal", "operation", "correlation_id", "execution_result"):
        if key not in blob:
            errors.append({"code": "MISSING_INTERFACE", "message": f"worker interface missing: {key}"})

    if CREDENTIAL_VALUE_RE.search(blob):
        errors.append({"code": ERROR_CODES["CREDENTIALS_IN_WORKFLOW"], "message": "credential values embedded"})

    # Placeholder credential references are OK; raw values are not.
    for node in nodes:
        creds = node.get("credentials")
        if isinstance(creds, dict):
            encoded = json.dumps(creds)
            if CREDENTIAL_VALUE_RE.search(encoded):
                errors.append(
                    {
                        "code": ERROR_CODES["CREDENTIALS_IN_WORKFLOW"],
                        "message": f"credential values in node {node.get('name')}",
                    }
                )

    if PRODUCTION_URL_RE.search(blob):
        errors.append({"code": "PRODUCTION_URL", "message": "production URL detected"})
    if PAID_API_RE.search(blob):
        errors.append({"code": "PAID_API", "message": "paid API execution reference detected"})

    # Must include inactive design meta.
    meta = data.get("meta") or {}
    if meta.get("srlInactiveByDesign") is not True:
        errors.append({"code": "MISSING_INACTIVE_META", "message": "srlInactiveByDesign meta required"})

    status = "PASS" if not errors else "FAIL"
    return {
        "status": status,
        "workflow": str(workflow_path.as_posix().split("/")[-1]),
        "node_count": len(nodes),
        "node_names": names,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate self-improvement design workflow")
    parser.add_argument("--root", required=True)
    parser.add_argument("--workflow", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root)
    workflow = Path(args.workflow)
    if not workflow.is_file():
        workflow = root / args.workflow
    try:
        report = validate_workflow(root, workflow)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "FAIL", "errors": [{"code": "JSON_SYNTAX", "message": str(exc)}]}))
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
