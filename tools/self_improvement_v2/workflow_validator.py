"""Structural offline validator for the Self-Improvement Loop V2 n8n design workflow.

Certifies routing from node IDs/types, connections, output indexes, and error behavior —
never from comments, jsCode marker strings, display names alone, or whole-file blob searches.
"""

from __future__ import annotations

import json
import re
from collections import Counter, deque
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tools.self_improvement_v2.models import ERROR_CODES


def _safe_url_origin(url: str) -> str | None:
    """Return ``scheme://host:port`` lowercased, or None when URL/port is unusable."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if not parsed.scheme or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        return None
    return f"{parsed.scheme}://{parsed.hostname}:{port}".lower()


def _safe_url_host_port_path(url: str) -> tuple[str | None, int | None, str]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None, None, ""
    host = (parsed.hostname or "").lower() or None
    try:
        port = parsed.port
    except ValueError:
        return host, None, parsed.path or ""
    return host, port, parsed.path or ""


CREDENTIAL_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}"
)
# Dict keys that must not hold credential material (structured injection).
# Anchored exact names only — substrings like tokenLimit / keyboardMode / authorizationMode
# are intentionally outside this set (false-positive control).
SENSITIVE_KEY_RE = re.compile(
    r"(?i)^(api[_-]?key|secret|password|token|authorization|access[_-]?token|bearer)$"
)

# Reviewed workflow contract: every connection link is exactly {node, type, index}.
ALLOWED_CONNECTION_LINK_KEYS: frozenset[str] = frozenset({"node", "type", "index"})
# Destination input slot for all reviewed edges (main + ai_languageModel) is 0.
REVIEWED_CONNECTION_INPUT_INDEX: int = 0

REQUIRED_NODE_SPECS: dict[str, str] = {
    "Manual Trigger": "n8n-nodes-base.manualTrigger",
    "Candidate Intake": "n8n-nodes-base.code",
    "Candidate Schema Validation": "n8n-nodes-base.if",
    "Open Pilot Budget": "n8n-nodes-base.httpRequest",
    "Provider Call Permit (Implementer)": "n8n-nodes-base.httpRequest",
    "Provider Call Consume (Implementer)": "n8n-nodes-base.httpRequest",
    "Proposal Schema Validation": "n8n-nodes-base.if",
    "Proposal Freeze": "n8n-nodes-base.code",
    "Topology Attest (Implementer)": "n8n-nodes-base.httpRequest",
    "Topology Attest (Reviewer)": "n8n-nodes-base.httpRequest",
    "Topology Attest (Worker Authorize)": "n8n-nodes-base.httpRequest",
    "Topology Attest (Execute)": "n8n-nodes-base.httpRequest",
    "Implementer Agent": "@n8n/n8n-nodes-langchain.agent",
    "Worker Authorize": "n8n-nodes-base.httpRequest",
    "Worker Decision Router": "n8n-nodes-base.switch",
    "Worker AUTHORIZED Continue": "n8n-nodes-base.code",
    "Annotate Authorize Failure": "n8n-nodes-base.code",
    "Detached Worker Execute": "n8n-nodes-base.code",
    "Execution Result Validation": "n8n-nodes-base.if",
    "Provider Call Permit (Reviewer)": "n8n-nodes-base.httpRequest",
    "Provider Call Consume (Reviewer)": "n8n-nodes-base.httpRequest",
    "Provider Call Authorize (Implementer)": "n8n-nodes-base.httpRequest",
    "Provider Call Authorize (Reviewer)": "n8n-nodes-base.httpRequest",
    "Independent Reviewer Agent": "@n8n/n8n-nodes-langchain.agent",
    "Independent Review Bind": "n8n-nodes-base.httpRequest",
    "Review Result Validation": "n8n-nodes-base.if",
    "Finalization": "n8n-nodes-base.code",
    "Learning Persistence": "n8n-nodes-base.code",
    "Human Promotion Boundary": "n8n-nodes-base.code",
    "Failure Router": "n8n-nodes-base.switch",
    "Invalid Candidate": "n8n-nodes-base.code",
    "Invalid Proposal": "n8n-nodes-base.code",
    "Annotate Budget Denied": "n8n-nodes-base.code",
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

# Closed node world: required nodes plus pinned attachments and the design sticky note.
# Extra executable nodes (even unconnected) are rejected — same class as edge closure.
ALLOWED_NODE_SPECS: dict[str, str] = {
    **REQUIRED_NODE_SPECS,
    "Implementer Gemini Chat Model": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
    "Independent Reviewer Groq Chat Model": "@n8n/n8n-nodes-langchain.lmChatGroq",
    "V2 Design Notes": "n8n-nodes-base.stickyNote",
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
    ("Open Pilot Budget", 1, "Annotate Budget Denied"),
    ("Provider Call Permit (Implementer)", 1, "Annotate Budget Denied"),
    ("Provider Call Consume (Implementer)", 1, "Annotate Budget Denied"),
    ("Topology Attest (Implementer)", 1, "Annotate Budget Denied"),
    ("Provider Call Permit (Reviewer)", 1, "Annotate Budget Denied"),
    ("Provider Call Consume (Reviewer)", 1, "Annotate Budget Denied"),
    ("Topology Attest (Reviewer)", 1, "Annotate Budget Denied"),
    ("Provider Call Authorize (Implementer)", 1, "Annotate Budget Denied"),
    ("Provider Call Authorize (Reviewer)", 1, "Annotate Budget Denied"),
    ("Annotate Budget Denied", 0, "Failure Router"),
    ("Proposal Schema Validation", 1, "Invalid Proposal"),
    ("Invalid Proposal", 0, "Failure Router"),
    ("Topology Attest (Worker Authorize)", 1, "Annotate Budget Denied"),
    ("Worker Authorize", 1, "Annotate Authorize Failure"),
    ("Annotate Authorize Failure", 0, "Failure Router"),
    ("Worker Decision Router", 1, "Terminal DECISION_REQUIRED"),
    ("Worker Decision Router", 2, "Terminal POLICY_REJECTED"),
    ("Topology Attest (Execute)", 1, "Annotate Budget Denied"),
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
    "Open Pilot Budget",
    "Provider Call Permit (Implementer)",
    "Provider Call Consume (Implementer)",
    "Topology Attest (Implementer)",
    "Provider Call Permit (Reviewer)",
    "Provider Call Consume (Reviewer)",
    "Topology Attest (Reviewer)",
    "Provider Call Authorize (Implementer)",
    "Provider Call Authorize (Reviewer)",
    "Topology Attest (Worker Authorize)",
    "Worker Authorize",
    "Topology Attest (Execute)",
    "Detached Worker Execute",
    "Independent Review Bind",
    "Finalization",
)

AGENT_NODES_REQUIRING_MAX_ITERATIONS = (
    "Implementer Agent",
    "Independent Reviewer Agent",
)
REQUIRED_AGENT_MAX_ITERATIONS = 1

# Nodes that must never be disabled (n8n passes first main input through when disabled).
MUST_ENABLE_AUTHORITY_NODES = (
    "Open Pilot Budget",
    "Provider Call Permit (Implementer)",
    "Provider Call Consume (Implementer)",
    "Topology Attest (Implementer)",
    "Provider Call Permit (Reviewer)",
    "Provider Call Consume (Reviewer)",
    "Topology Attest (Reviewer)",
    "Provider Call Authorize (Implementer)",
    "Provider Call Authorize (Reviewer)",
    "Topology Attest (Worker Authorize)",
    "Topology Attest (Execute)",
    "Proposal Schema Validation",
    "Worker Authorize",
    "Worker Decision Router",
    "Independent Review Bind",
    "Review Result Validation",
    "Finalization",
    "Candidate Schema Validation",
    "Execution Result Validation",
    "Failure Router",
)

# HTTP authority nodes whose retryOnFail / executeOnce must stay false.
NO_RETRY_EXECUTE_ONCE_NODES = MUST_ENABLE_AUTHORITY_NODES + (
    "Implementer Agent",
    "Independent Reviewer Agent",
)

# Worker HTTP nodes whose URL origin must equal meta.localWorkerBaseUrl.
WORKER_HTTP_NODES_WITH_PATH: tuple[tuple[str, str], ...] = (
    ("Open Pilot Budget", "/v2/budget/open"),
    ("Provider Call Permit (Implementer)", "/v2/provider-call-permit"),
    ("Provider Call Consume (Implementer)", "/v2/provider-call-consume"),
    ("Provider Call Authorize (Implementer)", "/v2/provider-call-authorize"),
    ("Provider Call Permit (Reviewer)", "/v2/provider-call-permit"),
    ("Provider Call Consume (Reviewer)", "/v2/provider-call-consume"),
    ("Provider Call Authorize (Reviewer)", "/v2/provider-call-authorize"),
    ("Worker Authorize", "/v2/validate-proposal"),
    ("Independent Review Bind", "/v2/bind-review"),
)

TOPOLOGY_ATTEST_NODES_WITH_PATH: tuple[tuple[str, str], ...] = (
    ("Topology Attest (Implementer)", "/v2/topology-attest"),
    ("Topology Attest (Reviewer)", "/v2/topology-attest"),
    ("Topology Attest (Worker Authorize)", "/v2/topology-attest"),
    ("Topology Attest (Execute)", "/v2/topology-attest"),
)

TOPOLOGY_ATTESTOR_ORIGIN = "http://host.docker.internal:8764"
TOPOLOGY_ATTEST_CREDENTIAL_NAME = "srl-v2-topology-attest-header-auth"
TOPOLOGY_TOKEN_EXPR = {
    "Topology Attest (Implementer)": "$('Topology Attest (Implementer)').item.json.topology_binding_token",
    "Topology Attest (Reviewer)": "$('Topology Attest (Reviewer)').item.json.topology_binding_token",
    "Topology Attest (Worker Authorize)": "$('Topology Attest (Worker Authorize)').item.json.topology_binding_token",
}

WORKER_DECISION_OUTPUT_EXPR = "={{$json.worker_decision}}"
WORKER_DECISION_RULE_VALUES = ("AUTHORIZED", "DECISION_REQUIRED", "POLICY_REJECTED")


def _err(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _nodes_by_name(nodes: list[Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Index nodes by name, or report uninterpretable members (never AttributeError)."""
    out: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            problems.append(
                f"nodes member must be object at $.nodes[{i}], got {type(node).__name__}"
            )
            continue
        name = str(node.get("name") or "")
        if name:
            if name in out:
                # Duplicate names are rejected by validate_workflow; keep first for diagnostics.
                continue
            out[name] = node
    return out, problems


def _enumerate_channel_edges(
    connections: dict[str, Any],
) -> tuple[list[tuple[str, str, int, str, int]], list[str]]:
    """Enumerate every connection-channel edge, or report uninterpretable shapes.

    Parse-strictly-or-reject: any channel body / output slot / link the walker
    cannot fully interpret becomes a problem string, never a silent skip.

    Edge identity is ``(channel, source, output_index, dest, input_index)`` —
    destination ``link.index`` participates, not only source output slot.
    Reviewed contract: link members exactly ``{node, type, index}``; input index
    is ``REVIEWED_CONNECTION_INPUT_INDEX`` (0) for every allowed channel.
    """
    edges: list[tuple[str, str, int, str, int]] = []
    problems: list[str] = []
    for source, block in connections.items():
        if not isinstance(source, str) or not source:
            problems.append(
                f"connection source must be non-empty string, got {type(source).__name__}"
            )
            continue
        if not isinstance(block, dict):
            problems.append(
                f"connection block for {source!r} must be object, got {type(block).__name__}"
            )
            continue
        for channel, groups in block.items():
            if not isinstance(channel, str) or not channel:
                problems.append(
                    f"connection channel name under {source!r} must be non-empty string, "
                    f"got {type(channel).__name__}"
                )
                continue
            if not isinstance(groups, list):
                problems.append(
                    f"malformed connection channel body: {source!r}.{channel} "
                    f"must be list, got {type(groups).__name__}"
                )
                continue
            for idx, outputs in enumerate(groups):
                if outputs is None or outputs == []:
                    continue
                if not isinstance(outputs, list):
                    problems.append(
                        f"malformed connection outputs: {source!r}.{channel}[{idx}] "
                        f"must be list, got {type(outputs).__name__}"
                    )
                    continue
                for link_i, link in enumerate(outputs):
                    if not isinstance(link, dict):
                        problems.append(
                            f"malformed connection link: {source!r}.{channel}[{idx}][{link_i}] "
                            f"must be object, got {type(link).__name__}"
                        )
                        continue
                    unknown = sorted(set(link.keys()) - ALLOWED_CONNECTION_LINK_KEYS)
                    if unknown:
                        problems.append(
                            f"unknown connection link member: {source!r}.{channel}[{idx}][{link_i}] "
                            f"keys {unknown} (allowed {sorted(ALLOWED_CONNECTION_LINK_KEYS)})"
                        )
                        continue
                    node = link.get("node")
                    if not isinstance(node, str) or not node:
                        problems.append(
                            f"malformed connection link: {source!r}.{channel}[{idx}][{link_i}] "
                            f"missing non-empty string node"
                        )
                        continue
                    link_type = link.get("type")
                    if not isinstance(link_type, str) or not link_type:
                        problems.append(
                            f"malformed connection link: {source!r}.{channel}[{idx}][{link_i}] "
                            f"type must be non-empty string, got {type(link_type).__name__}"
                        )
                        continue
                    if link_type != channel:
                        problems.append(
                            f"malformed connection link: {source!r}.{channel}[{idx}][{link_i}] "
                            f"type {link_type!r} does not match channel {channel!r}"
                        )
                        continue
                    link_index = link.get("index")
                    # bool is a subclass of int — reject explicitly.
                    if isinstance(link_index, bool) or not isinstance(link_index, int):
                        problems.append(
                            f"malformed connection link: {source!r}.{channel}[{idx}][{link_i}] "
                            f"index must be int, got {type(link_index).__name__}"
                        )
                        continue
                    if link_index != REVIEWED_CONNECTION_INPUT_INDEX:
                        problems.append(
                            f"malformed connection link: {source!r}.{channel}[{idx}][{link_i}] "
                            f"index {link_index} is not a reviewed destination input slot "
                            f"(required {REVIEWED_CONNECTION_INPUT_INDEX})"
                        )
                        continue
                    edges.append((channel, source, idx, node, link_index))
    return edges, problems


def _all_channel_edges(
    connections: dict[str, Any],
) -> list[tuple[str, str, int, str, int]]:
    """Enumerate edges only (shape problems discarded). Prefer ``_enumerate_channel_edges``."""
    edges, _problems = _enumerate_channel_edges(connections)
    return edges


def _all_main_edges(connections: dict[str, Any]) -> list[tuple[str, int, str]]:
    """Main-channel edges only — used by success-path / required-edge helpers."""
    return [
        (src, idx, dest)
        for channel, src, idx, dest, _input_idx in _all_channel_edges(connections)
        if channel == "main"
    ]


def _edge_multiset(connections: dict[str, Any]) -> Counter[tuple[str, str, int, str, int]]:
    """Count all-channel edges as a multiset so duplicated links are visible."""
    return Counter(_all_channel_edges(connections))


# Allowed non-main attachments (exactly once each). Agents may not gain ai_tool / ai_memory.
ALLOWED_CONNECTION_CHANNELS: frozenset[str] = frozenset({"main", "ai_languageModel"})
# (channel, source, source_output_index, dest, dest_input_index)
ALLOWED_AI_LANGUAGE_MODEL_EDGES: tuple[tuple[str, str, int, str, int], ...] = (
    ("ai_languageModel", "Implementer Gemini Chat Model", 0, "Implementer Agent", 0),
    ("ai_languageModel", "Independent Reviewer Groq Chat Model", 0, "Independent Reviewer Agent", 0),
)
AGENT_ATTACHMENT_FORBIDDEN_CHANNELS: frozenset[str] = frozenset({"ai_tool", "ai_memory"})
AGENT_NODE_NAMES: frozenset[str] = frozenset({"Implementer Agent", "Independent Reviewer Agent"})


def _outgoing(
    connections: dict[str, Any], source: str
) -> list[tuple[int, str]]:
    """Return list of (output_index, destination_name) for structural edges."""
    block = connections.get(source) or {}
    if not isinstance(block, dict):
        return []
    mains = block.get("main")
    if mains is None:
        return []
    if not isinstance(mains, list):
        # Malformed shape is reported by _enumerate_channel_edges; do not invent edges.
        return []
    edges: list[tuple[int, str]] = []
    for idx, outputs in enumerate(mains):
        if not outputs:
            continue
        if not isinstance(outputs, list):
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


def _scan_embedded_secrets(node: Any, *, path: str = "$") -> list[str]:
    """Find embedded credential material; reject uninterpretable JSON types.

    Credential-bearing structured keys are rejected by **key identity** (any string
    value length, including short placeholders). Pattern matching on values remains
    a secondary signal for free-form strings.
    """
    findings: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_s = str(key)
            child = f"{path}.{key_s}"
            if SENSITIVE_KEY_RE.match(key_s):
                if isinstance(value, str):
                    findings.append(
                        f"credential-bearing key {key_s!r} present at {child} "
                        f"(rejected by key identity)"
                    )
                elif value is None or isinstance(value, (bool, int, float)):
                    findings.append(
                        f"credential-bearing key {key_s!r} present at {child} "
                        f"(rejected by key identity; value type {type(value).__name__})"
                    )
                elif isinstance(value, (dict, list)):
                    findings.append(
                        f"credential-bearing key {key_s!r} present at {child} "
                        f"(rejected by key identity; nested value)"
                    )
                    findings.extend(_scan_embedded_secrets(value, path=child))
                else:
                    findings.append(
                        f"credential-bearing key {key_s!r} present at {child} "
                        f"(uninterpretable value type {type(value).__name__})"
                    )
                continue
            if isinstance(value, str):
                if CREDENTIAL_VALUE_RE.search(value):
                    findings.append(f"credential pattern in string at {child}")
            elif isinstance(value, (dict, list)):
                findings.extend(_scan_embedded_secrets(value, path=child))
            elif value is None or isinstance(value, (bool, int, float)):
                continue
            else:
                findings.append(
                    f"uninterpretable JSON type {type(value).__name__} at {child}"
                )
    elif isinstance(node, list):
        for i, value in enumerate(node):
            findings.extend(_scan_embedded_secrets(value, path=f"{path}[{i}]"))
    elif isinstance(node, str):
        if CREDENTIAL_VALUE_RE.search(node):
            findings.append(f"credential pattern in string at {path}")
    elif node is None or isinstance(node, (bool, int, float)):
        return findings
    else:
        findings.append(f"uninterpretable JSON type {type(node).__name__} at {path}")
    return findings


def validate_workflow(root: Path, workflow_path: Path) -> dict[str, Any]:
    del root  # reserved for future path-relative checks
    data = json.loads(workflow_path.read_text(encoding="utf-8"))
    errors: list[dict[str, str]] = []

    if not isinstance(data, dict):
        errors.append(
            _err(
                ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                f"workflow root must be object, got {type(data).__name__}",
            )
        )
        return {"status": "FAIL", "errors": errors, "nodes": []}

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

    by_name, node_shape_problems = _nodes_by_name(nodes)
    for problem in node_shape_problems:
        errors.append(_err(ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], problem))
    if node_shape_problems:
        return {"status": "FAIL", "errors": errors, "nodes": sorted(by_name)}

    names = [str(n.get("name") or "") for n in nodes]
    if any(not n for n in names):
        errors.append(_err(ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], "node names must be non-empty"))
    if len(names) != len(set(names)):
        errors.append(_err(ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], "duplicate node names rejected (closed-world)"))

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

    # Node-set closure (matches edge closure): every declared node must be allow-listed.
    for name, node in sorted(by_name.items()):
        expected_type = ALLOWED_NODE_SPECS.get(name)
        if expected_type is None:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"extra closed-world node rejected: {name} "
                    f"(type={node.get('type')!r}); deny-by-default",
                )
            )
            continue
        if name in REQUIRED_NODE_SPECS:
            continue  # type already checked above
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

    # Agent maxIterations must be exactly 1 (consume cannot gate mid-loop retries).
    for agent_name in AGENT_NODES_REQUIRING_MAX_ITERATIONS:
        agent = by_name.get(agent_name)
        if agent is None:
            continue
        params = agent.get("parameters") or {}
        options = params.get("options") if isinstance(params.get("options"), dict) else {}
        raw = options.get("maxIterations", params.get("maxIterations"))
        if raw is None:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{agent_name} missing maxIterations (must be {REQUIRED_AGENT_MAX_ITERATIONS})",
                )
            )
            continue
        if not isinstance(raw, int) or isinstance(raw, bool):
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{agent_name} maxIterations must be an integer (boolean rejected)",
                )
            )
            continue
        if raw != REQUIRED_AGENT_MAX_ITERATIONS:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{agent_name} maxIterations must be {REQUIRED_AGENT_MAX_ITERATIONS} (got {raw})",
                )
            )

    # Disabled authority / control nodes must be rejected (n8n passthrough hazard).
    for name in MUST_ENABLE_AUTHORITY_NODES:
        node = by_name.get(name)
        if node is None:
            continue
        if "disabled" in node:
            disabled = node.get("disabled")
            if not isinstance(disabled, bool):
                errors.append(
                    _err(
                        ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                        f"{name} disabled must be boolean when present",
                    )
                )
            elif disabled is True:
                errors.append(
                    _err(
                        ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                        f"{name} must not be disabled (authority/control node)",
                    )
                )

    # executeOnce / retryOnFail on authority or agent nodes enable multi-dispatch / burn.
    for name in NO_RETRY_EXECUTE_ONCE_NODES:
        node = by_name.get(name)
        if node is None:
            continue
        if node.get("executeOnce") is True:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{name} executeOnce must be false (single authorize must not cover N dispatches)",
                )
            )
        if node.get("retryOnFail") is True:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{name} retryOnFail must be false",
                )
            )

    # Worker HTTP node URL origins must equal absolute pin AND meta.localWorkerBaseUrl.
    # Absolute pin closes the "attacker sets both meta and nodes" self-consistency hole.
    from tools.self_improvement_v2.agent_runtime_contract import DEFAULT_LOCAL_WORKER_BASE_URL

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    base_url = str(meta.get("localWorkerBaseUrl") or "").strip().rstrip("/")
    absolute = urlparse(DEFAULT_LOCAL_WORKER_BASE_URL)
    absolute_origin = f"{absolute.scheme}://{absolute.hostname}:{absolute.port}".lower()
    base_origin = _safe_url_origin(base_url) or ""
    if not base_origin:
        errors.append(
            _err(
                ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                "meta.localWorkerBaseUrl missing or invalid (required to pin worker HTTP origins)",
            )
        )
    elif base_origin != absolute_origin:
        errors.append(
            _err(
                ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                f"meta.localWorkerBaseUrl must equal absolute pin {DEFAULT_LOCAL_WORKER_BASE_URL} "
                f"(not a self-chosen rogue origin)",
            )
        )
    if base_origin == absolute_origin:
        for name, expected_path in WORKER_HTTP_NODES_WITH_PATH:
            node = by_name.get(name)
            if node is None:
                continue
            url = str((node.get("parameters") or {}).get("url") or "").strip()
            host, port, path = _safe_url_host_port_path(url)
            if host != "127.0.0.1" or port != 8765 or not url.lower().startswith("http://"):
                errors.append(
                    _err(
                        ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                        f"{name} URL origin must equal absolute pin {DEFAULT_LOCAL_WORKER_BASE_URL}",
                    )
                )
            elif path != expected_path:
                errors.append(
                    _err(
                        ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                        f"{name} URL path must be exactly {expected_path}",
                    )
                )

    attest_base = str(meta.get("topologyAttestorBaseUrl") or "").strip().rstrip("/")
    if attest_base != TOPOLOGY_ATTESTOR_ORIGIN:
        errors.append(
            _err(
                ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                f"meta.topologyAttestorBaseUrl must equal {TOPOLOGY_ATTESTOR_ORIGIN}",
            )
        )
    for name, expected_path in TOPOLOGY_ATTEST_NODES_WITH_PATH:
        node = by_name.get(name)
        if node is None:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"missing topology attest node: {name}",
                )
            )
            continue
        url = str((node.get("parameters") or {}).get("url") or "").strip()
        host, port, path = _safe_url_host_port_path(url)
        if host != "host.docker.internal" or port != 8764 or not url.lower().startswith("http://"):
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{name} URL origin must equal {TOPOLOGY_ATTESTOR_ORIGIN}",
                )
            )
        elif path != expected_path:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{name} URL path must be exactly {expected_path}",
                )
            )
        creds = node.get("credentials") if isinstance(node.get("credentials"), dict) else {}
        header = creds.get("httpHeaderAuth") if isinstance(creds.get("httpHeaderAuth"), dict) else {}
        cred_name = str(header.get("name") or "")
        if cred_name != TOPOLOGY_ATTEST_CREDENTIAL_NAME:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{name} must use {TOPOLOGY_ATTEST_CREDENTIAL_NAME}",
                )
            )
        body = str((node.get("parameters") or {}).get("jsonBody") or "")
        purpose_by_name = {
            "Topology Attest (Implementer)": "provider_implementer",
            "Topology Attest (Reviewer)": "provider_reviewer",
            "Topology Attest (Worker Authorize)": "worker_authorize",
            "Topology Attest (Execute)": "execute_probe",
        }
        expected_purpose = purpose_by_name[name]
        if expected_purpose not in body:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{name} jsonBody must include purpose {expected_purpose}",
                )
            )

    for consumer, expr in (
        ("Provider Call Authorize (Implementer)", TOPOLOGY_TOKEN_EXPR["Topology Attest (Implementer)"]),
        ("Provider Call Authorize (Reviewer)", TOPOLOGY_TOKEN_EXPR["Topology Attest (Reviewer)"]),
        ("Worker Authorize", TOPOLOGY_TOKEN_EXPR["Topology Attest (Worker Authorize)"]),
    ):
        node = by_name.get(consumer)
        if node is None:
            continue
        body = str((node.get("parameters") or {}).get("jsonBody") or "")
        if "topology_binding_token" not in body or expr not in body:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"{consumer} jsonBody must include matching topology_binding_token expression",
                )
            )

    # Worker Decision Router selector + ordered rules (not destinations alone).
    decision_node = by_name.get("Worker Decision Router")
    if decision_node is not None:
        params = decision_node.get("parameters") or {}
        output_expr = params.get("output")
        if output_expr != WORKER_DECISION_OUTPUT_EXPR:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-INVALID-RISK-ROUTE"],
                    "Worker Decision Router output selector must be ={{$json.worker_decision}}",
                )
            )
        rules_obj = params.get("rules") if isinstance(params.get("rules"), dict) else {}
        rules = rules_obj.get("rules") if isinstance(rules_obj.get("rules"), list) else []
        values = tuple(str(r.get("value") or "") for r in rules if isinstance(r, dict))
        if values != WORKER_DECISION_RULE_VALUES:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-INVALID-RISK-ROUTE"],
                    "Worker Decision Router rules must be AUTHORIZED, DECISION_REQUIRED, POLICY_REJECTED in order",
                )
            )

    # Failure Router must keep expression-mode failure_state selector.
    failure_router = by_name.get("Failure Router")
    if failure_router is not None:
        params = failure_router.get("parameters") or {}
        if params.get("output") != "={{$json.failure_state}}":
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MARKER-NOT-ROUTE"],
                    "Failure Router output selector must be ={{$json.failure_state}}",
                )
            )

    # Success-path edges for operational nodes (budget/permit/consume gates before providers).
    success_edges = [
        ("Manual Trigger", 0, "Candidate Intake"),
        ("Candidate Intake", 0, "Candidate Schema Validation"),
        ("Candidate Schema Validation", 0, "Open Pilot Budget"),
        ("Open Pilot Budget", 0, "Provider Call Permit (Implementer)"),
        ("Provider Call Permit (Implementer)", 0, "Provider Call Consume (Implementer)"),
        ("Provider Call Consume (Implementer)", 0, "Topology Attest (Implementer)"),
        ("Topology Attest (Implementer)", 0, "Provider Call Authorize (Implementer)"),
        ("Provider Call Authorize (Implementer)", 0, "Implementer Agent"),
        ("Implementer Agent", 0, "Proposal Schema Validation"),
        ("Proposal Schema Validation", 0, "Proposal Freeze"),
        ("Proposal Freeze", 0, "Topology Attest (Worker Authorize)"),
        ("Topology Attest (Worker Authorize)", 0, "Worker Authorize"),
        ("Worker Authorize", 0, "Worker Decision Router"),
        ("Worker Decision Router", 0, "Worker AUTHORIZED Continue"),
        ("Worker AUTHORIZED Continue", 0, "Topology Attest (Execute)"),
        ("Topology Attest (Execute)", 0, "Detached Worker Execute"),
        ("Detached Worker Execute", 0, "Execution Result Validation"),
        ("Execution Result Validation", 0, "Provider Call Permit (Reviewer)"),
        ("Provider Call Permit (Reviewer)", 0, "Provider Call Consume (Reviewer)"),
        ("Provider Call Consume (Reviewer)", 0, "Topology Attest (Reviewer)"),
        ("Topology Attest (Reviewer)", 0, "Provider Call Authorize (Reviewer)"),
        ("Provider Call Authorize (Reviewer)", 0, "Independent Reviewer Agent"),
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

    # Closed-world graph: every connection channel (not just main). Multiset.
    # Parse-strictly-or-reject first: uninterpretable channel shapes are findings.
    actual_edges, shape_problems = _enumerate_channel_edges(connections)
    for problem in shape_problems:
        errors.append(_err(ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], problem))
    allowed_main_keys = set(REQUIRED_EDGES) | set(success_edges)
    for out_idx, dest in WORKER_DECISION_TARGETS.items():
        allowed_main_keys.add(("Worker Decision Router", out_idx, dest))
    for out_idx, dest in FAILURE_ROUTER_TARGETS.items():
        allowed_main_keys.add(("Failure Router", out_idx, dest))
    allowed_all: Counter[tuple[str, str, int, str, int]] = Counter(
        {
            ("main", src, idx, dest, REVIEWED_CONNECTION_INPUT_INDEX): 1
            for src, idx, dest in allowed_main_keys
        }
    )
    for edge in ALLOWED_AI_LANGUAGE_MODEL_EDGES:
        allowed_all[edge] = 1
    actual_all = Counter(actual_edges)
    for edge, count in actual_all.items():
        channel, source, out_idx, dest, _input_idx = edge
        if channel not in ALLOWED_CONNECTION_CHANNELS:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"unknown connection channel rejected: {channel} "
                    f"({source}[{out_idx}] → {dest}); deny-by-default",
                )
            )
            continue
        allowed = allowed_all.get(edge, 0)
        if allowed == 0:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"extra closed-world edge rejected: {channel}:{source}[{out_idx}] → {dest}",
                )
            )
        elif count > allowed:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"duplicate closed-world edge rejected: {channel}:{source}[{out_idx}] → {dest} "
                    f"(count={count}, allowed={allowed})",
                )
            )

    # Agent attachment set: exactly one ai_languageModel inbound; zero ai_tool/ai_memory.
    inbound: dict[str, Counter[str]] = {name: Counter() for name in AGENT_NODE_NAMES}
    for channel, _source, _idx, dest, _input_idx in actual_edges:
        if dest in inbound:
            inbound[dest][channel] += 1
    for agent in sorted(AGENT_NODE_NAMES):
        lm_count = inbound[agent].get("ai_languageModel", 0)
        if lm_count != 1:
            errors.append(
                _err(
                    ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                    f"agent attachment pin: {agent} must have exactly one ai_languageModel "
                    f"(count={lm_count})",
                )
            )
        for forbidden in sorted(AGENT_ATTACHMENT_FORBIDDEN_CHANNELS):
            if inbound[agent].get(forbidden, 0) > 0:
                errors.append(
                    _err(
                        ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"],
                        f"agent attachment pin: {agent} must not have {forbidden} "
                        f"(count={inbound[agent][forbidden]})",
                    )
                )

    # Credential / live endpoint / push-merge checks — walk nodes strictly.
    secret_hits = _scan_embedded_secrets(nodes, path="$.nodes")
    if secret_hits:
        errors.append(
            _err(
                ERROR_CODES["CREDENTIALS_IN_WORKFLOW"],
                "credential values embedded: " + "; ".join(secret_hits[:5]),
            )
        )
    # Endpoint / push / merge still need a string corpus; collect only after type walk.
    strings: list[str] = []

    def _collect_strings(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                _collect_strings(value)
        elif isinstance(node, list):
            for value in node:
                _collect_strings(value)
        elif isinstance(node, str):
            strings.append(node)

    _collect_strings(nodes)
    blob = "\n".join(strings)
    if re.search(r"(?i)git\s+push", blob):
        errors.append(_err(ERROR_CODES["PUSH_ATTEMPT"], "workflow encodes push"))
    if re.search(r"(?i)git\s+merge", blob):
        errors.append(_err(ERROR_CODES["MERGE_ATTEMPT"], "workflow encodes merge"))
    # The attestor pin is the only non-loopback URL the reviewed graph may carry.
    blob_for_live = blob.replace(TOPOLOGY_ATTESTOR_ORIGIN, "")
    if re.search(r"https?://(?!127\.0\.0\.1|localhost|example\.invalid)", blob_for_live, re.I):
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
