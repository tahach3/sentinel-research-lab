"""Material workflow normalizer for live↔design comparison (A14).

Explicit MATERIAL_FIELDS / IGNORED_FIELDS allowlists. Unknown keys fail closed.
Instance-generated IDs, layout coordinates, and timestamps are ignored; model IDs,
credential-reference names, worker endpoints, and edges are material.
"""

from __future__ import annotations

import copy
from typing import Any

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

# Top-level workflow object
MATERIAL_FIELDS_TOP = frozenset({"active", "name", "nodes", "connections", "meta", "settings"})
IGNORED_FIELDS_TOP = frozenset(
    {
        "id",
        "versionId",
        "updatedAt",
        "createdAt",
        "pinData",
        "staticData",
        "tags",
        "hash",
        "description",
        "shared",
        "metaVersion",
    }
)

# Per-node object
MATERIAL_FIELDS_NODE = frozenset(
    {
        "name",
        "type",
        "typeVersion",
        "parameters",
        "credentials",
        "onError",
        "continueOnFail",
        "alwaysOutputData",
        "retryOnFail",
        "maxTries",
        "waitBetweenTries",
    }
)
IGNORED_FIELDS_NODE = frozenset(
    {
        "id",
        "position",
        "disabled",
        "notes",
        "notesInFlow",
        "color",
        "webhookId",
        "extendsCredential",
    }
)

# Credential binding: name is material; instance id is ignored
MATERIAL_FIELDS_CREDENTIAL = frozenset({"name"})
IGNORED_FIELDS_CREDENTIAL = frozenset({"id"})

# Meta keys that affect runtime trust / pins
MATERIAL_FIELDS_META = frozenset(
    {
        "srlInactiveByDesign",
        "implementerAgentId",
        "reviewerAgentId",
        "localWorkerBaseUrl",
        "workerHeaderAuthCredentialName",
        "implementerAgentCredentialReference",
        "reviewerAgentCredentialReference",
        "implementerModel",
        "reviewerModel",
        "implementerChatModelNodeType",
        "reviewerChatModelNodeType",
        "aiAgentNodeType",
        "agentRuntimePhase",
        "schemas",
        "srlRound",
    }
)
IGNORED_FIELDS_META = frozenset(
    {
        "templateCredsSetupCompleted",
        "agentRuntimeWiringStatus",  # design-only WORKFLOW_WIRED marker
        "instanceId",
    }
)

# Parameter keys that are layout / n8n chrome (sticky notes etc.)
IGNORED_FIELDS_PARAMETERS = frozenset(
    {
        "height",
        "width",
        "color",
    }
)

# Connection link fields
MATERIAL_FIELDS_LINK = frozenset({"node", "type", "index"})
IGNORED_FIELDS_LINK = frozenset()

# Public aliases required by the A14 contract wording
MATERIAL_FIELDS = {
    "top": MATERIAL_FIELDS_TOP,
    "node": MATERIAL_FIELDS_NODE,
    "credential": MATERIAL_FIELDS_CREDENTIAL,
    "meta": MATERIAL_FIELDS_META,
    "parameters_ignored_subset": IGNORED_FIELDS_PARAMETERS,
    "link": MATERIAL_FIELDS_LINK,
}
IGNORED_FIELDS = {
    "top": IGNORED_FIELDS_TOP,
    "node": IGNORED_FIELDS_NODE,
    "credential": IGNORED_FIELDS_CREDENTIAL,
    "meta": IGNORED_FIELDS_META,
    "parameters": IGNORED_FIELDS_PARAMETERS,
    "link": IGNORED_FIELDS_LINK,
}


class WorkflowNormalizerError(WorkerError):
    def __init__(self, message: str) -> None:
        super().__init__(ERROR_CODES["WORKFLOW_NORMALIZER"], message, state="POLICY_REJECTED")


def _partition_keys(
    obj: dict[str, Any],
    *,
    material: frozenset[str],
    ignored: frozenset[str],
    context: str,
) -> list[str]:
    unknown = sorted(k for k in obj if k not in material and k not in ignored)
    if unknown:
        raise WorkflowNormalizerError(f"unknown field(s) at {context}: {', '.join(unknown)}")
    return sorted(k for k in obj if k in material)


def _normalize_credentials(creds: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(creds, dict):
        raise WorkflowNormalizerError(f"{context}: credentials must be an object")
    out: dict[str, Any] = {}
    for cred_type, block in sorted(creds.items()):
        if not isinstance(block, dict):
            raise WorkflowNormalizerError(f"{context}.credentials.{cred_type}: must be object")
        keys = _partition_keys(
            block,
            material=MATERIAL_FIELDS_CREDENTIAL,
            ignored=IGNORED_FIELDS_CREDENTIAL,
            context=f"{context}.credentials.{cred_type}",
        )
        out[cred_type] = {k: block[k] for k in keys}
    return out


def _normalize_parameters(params: Any, *, context: str) -> Any:
    if not isinstance(params, dict):
        return params
    # Nested objects: recursively drop ignored layout keys; unknown nested keys stay
    # (parameter schemas vary by node type — material by default).
    out: dict[str, Any] = {}
    for key, value in sorted(params.items()):
        if key in IGNORED_FIELDS_PARAMETERS:
            continue
        if isinstance(value, dict):
            out[key] = _normalize_parameters(value, context=f"{context}.{key}")
        elif isinstance(value, list):
            out[key] = [
                _normalize_parameters(item, context=f"{context}.{key}[]")
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            out[key] = value
    return out


def _normalize_node(node: dict[str, Any], *, index: int) -> dict[str, Any]:
    ctx = "nodes[%d]" % index
    if not isinstance(node, dict):
        raise WorkflowNormalizerError(f"{ctx} must be an object")
    keys = _partition_keys(
        node,
        material=MATERIAL_FIELDS_NODE,
        ignored=IGNORED_FIELDS_NODE,
        context=ctx,
    )
    out: dict[str, Any] = {}
    for key in keys:
        if key == "parameters":
            out[key] = _normalize_parameters(node.get(key) or {}, context=f"{ctx}.parameters")
        elif key == "credentials":
            out[key] = _normalize_credentials(node.get(key) or {}, context=ctx)
        else:
            out[key] = copy.deepcopy(node[key])
    return out


def _normalize_link(link: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(link, dict):
        raise WorkflowNormalizerError(f"{context}: link must be an object")
    keys = _partition_keys(
        link,
        material=MATERIAL_FIELDS_LINK,
        ignored=IGNORED_FIELDS_LINK,
        context=context,
    )
    return {k: link[k] for k in keys}


def _normalize_connections(connections: Any) -> dict[str, Any]:
    if not isinstance(connections, dict):
        raise WorkflowNormalizerError("connections must be an object")
    out: dict[str, Any] = {}
    for source in sorted(connections):
        block = connections[source]
        if not isinstance(block, dict):
            raise WorkflowNormalizerError(f"connections.{source}: must be object")
        # Connection channel names (main, ai_languageModel, ...) are material structure.
        norm_block: dict[str, Any] = {}
        for channel, groups in sorted(block.items()):
            if not isinstance(groups, list):
                raise WorkflowNormalizerError(f"connections.{source}.{channel}: must be array")
            norm_groups = []
            for gi, group in enumerate(groups):
                if group is None:
                    norm_groups.append([])
                    continue
                if not isinstance(group, list):
                    raise WorkflowNormalizerError(
                        f"connections.{source}.{channel}[{gi}]: must be array"
                    )
                norm_groups.append(
                    [
                        _normalize_link(
                            link,
                            context="connections.%s.%s[%d][%d]" % (source, channel, gi, li),
                        )
                        for li, link in enumerate(group)
                    ]
                )
            norm_block[channel] = norm_groups
        out[source] = norm_block
    return out


def _normalize_meta(meta: Any) -> dict[str, Any]:
    if not isinstance(meta, dict):
        raise WorkflowNormalizerError("meta must be an object")
    keys = _partition_keys(
        meta,
        material=MATERIAL_FIELDS_META,
        ignored=IGNORED_FIELDS_META,
        context="meta",
    )
    return {k: copy.deepcopy(meta[k]) for k in keys}


def normalize_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return the material form of a workflow. Unknown fields raise."""
    if not isinstance(workflow, dict):
        raise WorkflowNormalizerError("workflow must be an object")
    keys = _partition_keys(
        workflow,
        material=MATERIAL_FIELDS_TOP,
        ignored=IGNORED_FIELDS_TOP,
        context="<workflow>",
    )
    out: dict[str, Any] = {}
    for key in keys:
        if key == "nodes":
            nodes = workflow.get("nodes") or []
            if not isinstance(nodes, list):
                raise WorkflowNormalizerError("nodes must be an array")
            # Sort by name for stable comparison (ids ignored).
            normalized_nodes = [_normalize_node(n, index=i) for i, n in enumerate(nodes)]
            out["nodes"] = sorted(normalized_nodes, key=lambda n: str(n.get("name") or ""))
        elif key == "connections":
            out["connections"] = _normalize_connections(workflow.get("connections") or {})
        elif key == "meta":
            out["meta"] = _normalize_meta(workflow.get("meta") or {})
        else:
            out[key] = copy.deepcopy(workflow[key])
    return out


def workflows_materially_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return normalize_workflow(left) == normalize_workflow(right)


def assert_workflows_materially_equivalent(left: dict[str, Any], right: dict[str, Any]) -> None:
    if not workflows_materially_equivalent(left, right):
        raise WorkflowNormalizerError("workflows are not materially equivalent")


def material_fingerprint(workflow: dict[str, Any]) -> str:
    return content_sha256(normalize_workflow(workflow))
