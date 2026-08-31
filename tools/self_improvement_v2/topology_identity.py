"""Live worker/n8n identity. Cached topology is never authority."""

from __future__ import annotations

from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import CONTAINER_ID_RE, HEX64_RE


def require_running_state(state: str) -> None:
    if (state or "").strip() != "running":
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            f"worker State must be running, got {state!r}",
            state="FAILED_FROZEN",
        )


def normalize_image_digest(value: str) -> str:
    digest = (value or "").strip()
    if digest.startswith("sha256:"):
        hexpart = digest[7:]
    else:
        hexpart = digest
    if not HEX64_RE.fullmatch(hexpart):
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "worker image digest D must be sha256 64-hex",
            state="FAILED_FROZEN",
        )
    return f"sha256:{hexpart}"


def parse_inspect_identity(inspect: dict[str, Any], *, n8n_inspect: dict[str, Any] | None = None) -> dict[str, str]:
    cid = str(inspect.get("Id") or "").strip().lower()
    if cid.startswith("sha256:"):
        cid = cid[7:]
    if not CONTAINER_ID_RE.fullmatch(cid):
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            "inspect Id is not exact 64-hex",
            state="FAILED_FROZEN",
        )
    state_obj = inspect.get("State") or {}
    status = str(state_obj.get("Status") or "")
    require_running_state(status)
    started = str(state_obj.get("StartedAt") or "")
    if not started:
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "StartedAt missing",
            state="FAILED_FROZEN",
        )
    image = normalize_image_digest(str(inspect.get("Image") or inspect.get("ImageDigest") or ""))
    netns = str(inspect.get("worker_netns_identity") or inspect.get("NetworkNamespace") or "")
    if not netns:
        net = inspect.get("NetworkSettings") or {}
        netns = str(net.get("SandboxKey") or net.get("SandboxID") or "")
    if not netns:
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "network namespace identity missing",
            state="FAILED_FROZEN",
        )
    host = inspect.get("HostConfig") or {}
    network_mode = str(host.get("NetworkMode") or "")
    n8n_id = ""
    n8n_netns = ""
    if n8n_inspect:
        n8n_id = str(n8n_inspect.get("Id") or "").strip().lower()
        if n8n_id.startswith("sha256:"):
            n8n_id = n8n_id[7:]
        if not CONTAINER_ID_RE.fullmatch(n8n_id):
            raise WorkerError(
                ERROR_CODES["DOCKER_PREFIX_ID"],
                "n8n Id is not exact 64-hex",
                state="FAILED_FROZEN",
            )
        n8n_state = n8n_inspect.get("State") or {}
        require_running_state(str(n8n_state.get("Status") or ""))
        n8n_net = n8n_inspect.get("NetworkSettings") or {}
        n8n_netns = str(
            n8n_inspect.get("worker_netns_identity")
            or n8n_inspect.get("NetworkNamespace")
            or n8n_net.get("SandboxKey")
            or n8n_net.get("SandboxID")
            or ""
        )
        if not n8n_netns:
            raise WorkerError(
                ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
                "n8n network namespace identity missing",
                state="FAILED_FROZEN",
            )
        if n8n_netns != netns:
            raise WorkerError(
                ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
                "worker and n8n must share a network namespace",
                state="FAILED_FROZEN",
            )
        allowed_modes = {f"container:{n8n_id}", "service:n8n"}
        if network_mode.strip().lower() not in allowed_modes:
            raise WorkerError(
                ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
                f"worker NetworkMode must share n8n namespace, got {network_mode!r}",
                state="FAILED_FROZEN",
            )
    return {
        "worker_container_id": cid,
        "worker_started_at": started,
        "worker_image_digest": image,
        "worker_netns_identity": netns,
        "n8n_container_id": n8n_id,
        "network_mode": network_mode,
        "state": status,
    }


def identities_equal(a: dict[str, str], b: dict[str, str], *, fields: tuple[str, ...] | None = None) -> bool:
    keys = fields or (
        "worker_container_id",
        "worker_started_at",
        "worker_image_digest",
        "worker_netns_identity",
    )
    return all(a.get(k) == b.get(k) for k in keys)


def refuse_restart(previous: dict[str, str], live: dict[str, str]) -> None:
    if (
        previous.get("worker_container_id") == live.get("worker_container_id")
        and previous.get("worker_started_at") != live.get("worker_started_at")
    ):
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "same container Id + changed StartedAt = REFUSE",
            state="FAILED_FROZEN",
        )


def copy_generation_identity(live: dict[str, str]) -> dict[str, str]:
    return {
        "worker_container_id": live["worker_container_id"],
        "worker_started_at": live["worker_started_at"],
        "worker_image_digest": live["worker_image_digest"],
        "worker_netns_identity": live["worker_netns_identity"],
    }
