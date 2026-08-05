"""Structural offline validator for the Self-Improvement Loop V2 n8n design workflow.

Certifies routing from node IDs/types, connections, output indexes, and error behavior —
never from comments, jsCode marker strings, display names alone, or whole-file blob searches.
"""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES

CREDENTIAL_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}"
)

REQUIRED_NODE_SPECS: dict[str, str] = {
    "Manual Trigger": "n8n-nodes-base.manualTrigger",
    "Candidate Intake": "n8n-nodes-base.code",
    "Candidate Schema Validation": "n8n-nodes-base.if",
    "Proposal Schema Validation": "n8n-nodes-base.if",
    "Proposal Freeze": "n8n-nodes-base.code",
    "Implementer Agent": "@n8n/n8n-nodes-langchain.agent",
    "Worker Authorize": "n8n-nodes-base.httpRequest",
    "Worker Decision Router": "n8n-nodes-base.switch",
    "Worker AUTHORIZED Continue": "n8n-nodes-base.code",
    "Annotate Authorize Failure": "n8n-nodes-base.code",
    "Detached Worker Execute": "n8n-nodes-base.code",
    "Execution Result Validation": "n8n-nodes-base.if",
    "Independent Reviewer Agent": "@n8n/n8n-nodes-langchain.agent",
    "Independent Review Bind": "n8n-nodes-base.code",
    "Review Result Validation": "n8n-nodes-base.if",
    "Finalization": "n8n-nodes-base.code",
    "Learning Persistence": "n8n-nodes-base.code",
    "Human Promotion Boundary": "n8n-nodes-base.code",
    "Failure Router": "n8n-nodes-base.switch",
    "Invalid Candidate": "n8n-nodes-base.code",
    "Invalid Proposal": "n8n-nodes-base.code",
    "Annotate Worker Failure": "n8n-nodes-base.code",
    "Annotate Validation Failure": "n8n-nodes-base.code",
    "Annotate Review Failure": "n8n-nodes-base.code",
    "Annotate Repair Limit Failure": "n8n-nodes-base.code",
    "Annotate Finalization Failure": "n8n-nodes-base.code",
    "Terminal DECISION_REQUIRED": "n8n-nodes-base.code",
    "Terminal POLICY_REJECTED": "n8n-nodes-base.code",
    "Terminal VALIDATION_FAILED": "n8n-nodes-base.code",
    "Terminal REVIEW_FAILED": "n8n-nodes-base.code",
    "Terminal CONTENT_BINDING_MISMATCH": "n8n-nodes-base.code",
    "Terminal REPAIR_LIMIT_REACHED": "n8n-nodes-base.code",
    "Terminal FAILED_FROZEN": "n8n-nodes-base.code",
    "Terminal PATCH_REJECTED": "n8n-nodes-base.code",
    "Terminal BASELINE_MISMATCH": "n8n-nodes-base.code",
    "Terminal IMMUTABILITY_VIOLATION": "n8n-nodes-base.code",
}

# Worker Decision Router switch output index → required destination (direct).
WORKER_DECISION_TARGETS = {
    0: "Worker AUTHORIZED Continue",
    1: "Terminal DECISION_REQUIRED",
    2: "Terminal POLICY_REJECTED",
}

# Failure Router switch output index → required terminal.
FAILURE_ROUTER_TARGETS = {
    0: "Terminal POLICY_REJECTED",
    1: "Terminal VALIDATION_FAILED",
    2: "Terminal REVIEW_FAILED",
    3: "Terminal CONTENT_BINDING_MISMATCH",
    4: "Terminal REPAIR_LIMIT_REACHED",
    5: "Terminal FAILED_FROZEN",
    6: "Terminal PATCH_REJECTED",
    7: "Terminal BASELINE_MISMATCH",
    8: "Terminal IMMUTABILITY_VIOLATION",
    9: "Terminal DECISION_REQUIRED",
}

# (source, output_index, destination) required failure/risk edges.
REQUIRED_EDGES: list[tuple[str, int, str]] = [
    ("Candidate Schema Validation", 1, "Invalid Candidate"),
    ("Invalid Candidate", 0, "Failure Router"),
    ("Proposal Schema Validation", 1, "Invalid Proposal"),
    ("Invalid Proposal", 0, "Failure Router"),
    ("Worker Authorize", 1, "Annotate Authorize Failure"),
    ("Annotate Authorize Failure", 0, "Failure Router"),
    ("Worker Decision Router", 1, "Terminal DECISION_REQUIRED"),
    ("Worker Decision Router", 2, "Terminal POLICY_REJECTED"),
    ("Detached Worker Execute", 1, "Annotate Worker Failure"),
    ("Annotate Worker Failure", 0, "Failure Router"),
    ("Execution Result Validation", 1, "Annotate Validation Failure"),
    ("Annotate Validation Failure", 0, "Failure Router"),
    ("Independent Review Bind", 1, "Annotate Review Failure"),
    ("Annotate Review Failure", 0, "Failure Router"),
    ("Review Result Validation", 1, "Annotate Repair Limit Failure"),
    ("Annotate Repair Limit Failure", 0, "Failure Router"),
    ("Finalization", 1, "Annotate Finalization Failure"),
    ("Annotate Finalization Failure", 0, "Failure Router"),
    ("Terminal CONTENT_BINDING_MISMATCH", 0, "Terminal FAILED_FROZEN"),
]

ERROR_OUTPUT_NODES = (
    "Worker Authorize",
    "Detached Worker Execute",
    "Independent Review Bind",
    "Finalization",
)


def _err(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _nodes_by_name(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for node in nodes:
        name = str(node.get("name") or "")
        if name:
            out[name] = node
    return out


def _outgoing(
    connections: dict[str, Any], source: str
) -> list[tuple[int, str]]:
    """Return list of (output_index, destination_name) for structural edges."""
    block = connections.get(source) or {}
    mains = block.get("main") or []
    edges: list[tuple[int, str]] = []
    for idx, outputs in enumerate(mains):
        if not outputs:
            continue
        for link in outputs:
            if not isinstance(link, dict):
                continue
            dest = link.get("node")
            if isinstance(dest, str) and dest:
                edges.append((idx, dest))
    return edges


def _has_edge(connections: dict[str, Any], source: str, output_index: int, dest: str) -> bool:
    return any(idx == output_index and d == dest for idx, d in _outgoing(connections, source))


def _reachable_from(
    connections: dict[str, Any],
    start: str,
    *,
    only_output: int | None = None,
) -> set[str]:
    """BFS over structural main connections. Optionally restrict the first hop output index."""
    seen: set[str] = set()
    q: deque[str] = deque()
    if only_output is None:
        q.append(start)
        seen.add(start)
    else:
        for idx, dest in _outgoing(connections, start):
            if idx == only_output and dest not in seen:
                seen.add(dest)
                q.append(dest)
    while q:
        cur = q.popleft()
        for _idx, dest in _outgoing(connections, cur):
            if dest not in seen:
                seen.add(dest)
                q.append(dest)
    return seen


def _collect_credential_strings(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _collect_credential_strings(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_credential_strings(value, out)
    elif isinstance(node, str):
        out.append(node)


def validate_workflow(root: Path, workflow_path: Path) -> dict[str, Any]:
    del root  # reserved for future path-relative checks
    data = json.loads(workflow_path.read_text(encoding="utf-8"))
    errors: list[dict[str, str]] = []

    if data.get("active") is not False:
        errors.append(_err(ERROR_CODES["WORKFLOW_ACTIVE"], "active must be false"))

    connections = data.get("connections") or {}
    if not isinstance(connections, dict):
        errors.append(_err(ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], "connections must be object"))
        return {"status": "FAIL", "errors": errors, "nodes": []}

    nodes = data.get("nodes") or []
    if not isinstance(nodes, list):
        errors.append(_err(ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], "nodes must be list"))
        return {"status": "FAIL", "errors": errors, "nodes": []}

    by_name = _nodes_by_name(nodes)
    ids = [str(n.get("id") or "") for n in nodes]
    if len(ids) != len(set(ids)) or any(not i for i in ids):
        errors.append(_err(ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], "node IDs must be unique and non-empty"))

    # Forbidden: n8n must not classify from proposal risk_level.
    for banned in (
        "Risk Classification",
        "LOW Auto-Authorize",
        "MEDIUM Decision Required",
        "HIGH Human Approval Required",
        "PROHIBITED Policy Rejected",
    ):
        if banned in by_name:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-INVALID-RISK-ROUTE"],
                    f"executable risk node forbidden in n8n design: {banned}",
                )
            )

    for name, expected_type in REQUIRED_NODE_SPECS.items():
        node = by_name.get(name)
        if node is None:
            errors.append(_err(ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], f"missing node: {name}"))
            continue
        actual_type = str(node.get("type") or "")
        if actual_type != expected_type:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MARKER-NOT-ROUTE"],
                    f"node {name} type {actual_type} != {expected_type}",
                )
            )

    # Worker decision router — structural only.
    decision_node = by_name.get("Worker Decision Router")
    if decision_node is not None:
        for out_idx, dest in WORKER_DECISION_TARGETS.items():
            if not _has_edge(connections, "Worker Decision Router", out_idx, dest):
                errors.append(
                    _err(
                        ERROR_CODES["SI2-WF-INVALID-RISK-ROUTE"],
                        f"Worker Decision Router output {out_idx} must connect to {dest}",
                    )
                )

        # Non-AUTHORIZED outputs must not reach worker execute.
        for out_idx, label in ((1, "DECISION_REQUIRED"), (2, "POLICY_REJECTED")):
            reach = _reachable_from(connections, "Worker Decision Router", only_output=out_idx)
            if "Detached Worker Execute" in reach or "Worker AUTHORIZED Continue" in reach:
                errors.append(
                    _err(
                        ERROR_CODES["SI2-WF-AUTOAUTH-NONLOW"],
                        f"{label} reaches worker execution path",
                    )
                )

        auth_reach = _reachable_from(connections, "Worker Decision Router", only_output=0)
        if "Detached Worker Execute" not in auth_reach:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-INVALID-RISK-ROUTE"],
                    "AUTHORIZED does not reach Detached Worker Execute",
                )
            )

    # Failure Router must be a real multi-output switch with terminal edges.
    failure_router = by_name.get("Failure Router")
    if failure_router is not None:
        fr_type = str(failure_router.get("type") or "")
        fr_edges = _outgoing(connections, "Failure Router")
        if fr_type != "n8n-nodes-base.switch":
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MARKER-NOT-ROUTE"],
                    "Failure Router must be n8n-nodes-base.switch",
                )
            )
        if not fr_edges:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MARKER-NOT-ROUTE"],
                    "Failure Router has no structural outgoing edges",
                )
            )
        for out_idx, dest in FAILURE_ROUTER_TARGETS.items():
            if not _has_edge(connections, "Failure Router", out_idx, dest):
                code = ERROR_CODES["SI2-WF-DISCONNECTED-FAILURE-STATE"]
                errors.append(
                    _err(code, f"Failure Router output {out_idx} must connect to {dest}")
                )

    for source, out_idx, dest in REQUIRED_EDGES:
        if source not in by_name or dest not in by_name:
            if source in by_name and dest not in by_name:
                errors.append(
                    _err(
                        ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                        f"missing failure edge {source}[{out_idx}] → {dest}",
                    )
                )
            continue
        if not _has_edge(connections, source, out_idx, dest):
            code = ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"]
            if "CONTENT_BINDING" in dest or "CONTENT_BINDING" in source:
                code = ERROR_CODES["SI2-WF-DISCONNECTED-FAILURE-STATE"]
            errors.append(
                _err(code, f"missing failure edge {source}[{out_idx}] → {dest}")
            )

    # Error behavior: operational nodes must declare continueErrorOutput when they expose output 1.
    for name in ERROR_OUTPUT_NODES:
        node = by_name.get(name)
        if node is None:
            continue
        if node.get("onError") != "continueErrorOutput":
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{name} must set onError=continueErrorOutput",
                )
            )
        if not any(idx == 1 for idx, _ in _outgoing(connections, name)):
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{name} missing structural error output edge",
                )
            )

    # Success-path edges for operational nodes.
    success_edges = [
        ("Candidate Schema Validation", 0, "Implementer Agent"),
        ("Implementer Agent", 0, "Proposal Schema Validation"),
        ("Proposal Schema Validation", 0, "Proposal Freeze"),
        ("Proposal Freeze", 0, "Worker Authorize"),
        ("Worker Authorize", 0, "Worker Decision Router"),
        ("Worker AUTHORIZED Continue", 0, "Detached Worker Execute"),
        ("Detached Worker Execute", 0, "Execution Result Validation"),
        ("Execution Result Validation", 0, "Independent Reviewer Agent"),
        ("Independent Reviewer Agent", 0, "Independent Review Bind"),
        ("Independent Review Bind", 0, "Review Result Validation"),
        ("Review Result Validation", 0, "Finalization"),
        ("Finalization", 0, "Learning Persistence"),
        ("Learning Persistence", 0, "Human Promotion Boundary"),
    ]
    for source, out_idx, dest in success_edges:
        if source in by_name and dest in by_name and not _has_edge(connections, source, out_idx, dest):
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"missing success edge {source}[{out_idx}] → {dest}",
                )
            )

    # Credential / live endpoint / push-merge checks use node parameter strings only
    # (not whole-file routing certification).
    strings: list[str] = []
    _collect_credential_strings(nodes, strings)
    blob = "\n".join(strings)
    if CREDENTIAL_VALUE_RE.search(blob):
        errors.append(_err(ERROR_CODES["CREDENTIALS_IN_WORKFLOW"], "credential values embedded"))
    if re.search(r"(?i)git\s+push", blob):
        errors.append(_err(ERROR_CODES["PUSH_ATTEMPT"], "workflow encodes push"))
    if re.search(r"(?i)git\s+merge", blob):
        errors.append(_err(ERROR_CODES["MERGE_ATTEMPT"], "workflow encodes merge"))
    if re.search(r"https?://(?!127\.0\.0\.1|localhost|example\.invalid)", blob, re.I):
        errors.append(_err("LIVE_ENDPOINT", "non-local endpoint present"))

    status = "PASS" if not errors else "FAIL"
    return {
        "status": status,
        "errors": errors,
        "nodes": sorted(by_name),
        "graph": {
            "worker_decision_outputs": {
                str(i): WORKER_DECISION_TARGETS[i] for i in WORKER_DECISION_TARGETS
            },
            "failure_router_outputs": {
                str(i): FAILURE_ROUTER_TARGETS[i] for i in FAILURE_ROUTER_TARGETS
            },
        },
    }
