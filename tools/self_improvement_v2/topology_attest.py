"""Mandatory live INV-TOPO reassert. A prior PASS never satisfies a later gate."""

from __future__ import annotations

from typing import Any, Callable

from tools.self_improvement_v2.canonical import canonical_bytes, sha256_hex
from tools.self_improvement_v2.docker_cli import require_container_id, resolve_unique_prefix
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import CONTAINER_ID_RE
from tools.self_improvement_v2.topology_identity import parse_inspect_identity, refuse_restart

InspectFn = Callable[[str], dict[str, Any]]
ListFn = Callable[[], list[str]]


def closed_set_from_listing(
    all_ids: list[str],
    *,
    worker_id: str,
    n8n_id: str,
) -> frozenset[str]:
    w = require_container_id(worker_id)
    n = require_container_id(n8n_id)
    listing = [i.strip().lower() for i in all_ids if i and i.strip()]
    for item in listing:
        if not CONTAINER_ID_RE.fullmatch(item):
            raise WorkerError(
                ERROR_CODES["DOCKER_PREFIX_ID"],
                "host-wide listing contains a non-64-hex / prefix joiner",
                state="FAILED_FROZEN",
            )
    actual = frozenset(listing)
    expected = frozenset({w, n})
    if actual != expected:
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "host-wide closed-set must equal exactly {worker, n8n}",
            state="FAILED_FROZEN",
        )
    return expected


def live_reassert(
    *,
    inspect_worker: InspectFn,
    inspect_n8n: InspectFn,
    list_all_ids: ListFn,
    worker_id: str,
    n8n_id: str,
    expected_image_digest: str | None = None,
    previous: dict[str, str] | None = None,
    sequence: int,
) -> dict[str, Any]:
    """Independent live inspect. `previous` is compared, never reused as authority."""
    wid = require_container_id(worker_id)
    nid = require_container_id(n8n_id)
    listing = list_all_ids()
    # Prefix tokens must resolve uniquely then be discarded; argv uses 64-hex only.
    resolved_w = resolve_unique_prefix(listing, wid)
    resolved_n = resolve_unique_prefix(listing, nid)
    if resolved_w != wid or resolved_n != nid:
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            "live reassert requires exact 64-hex ids, not prefixes",
            state="FAILED_FROZEN",
        )
    worker_inspect = inspect_worker(wid)
    n8n_inspect = inspect_n8n(nid)
    identity = parse_inspect_identity(worker_inspect, n8n_inspect=n8n_inspect)
    if expected_image_digest and identity["worker_image_digest"] != expected_image_digest:
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "wrong worker image pin",
            state="FAILED_FROZEN",
        )
    if previous is not None:
        refuse_restart(previous, identity)
        for key in (
            "worker_container_id",
            "worker_started_at",
            "worker_image_digest",
            "worker_netns_identity",
            "n8n_container_id",
        ):
            if previous.get(key) and previous.get(key) != identity.get(key):
                raise WorkerError(
                    ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
                    f"live identity changed: {key}",
                    state="FAILED_FROZEN",
                )
    closed = closed_set_from_listing(listing, worker_id=wid, n8n_id=nid)
    if previous and previous.get("closed_set"):
        if previous["closed_set"] != ",".join(sorted(closed)):
            raise WorkerError(
                ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
                "closed-set changed",
                state="FAILED_FROZEN",
            )
    identity["closed_set"] = ",".join(sorted(closed))
    body = {
        "worker_container_id": identity["worker_container_id"],
        "worker_started_at": identity["worker_started_at"],
        "worker_image_digest": identity["worker_image_digest"],
        "worker_netns_identity": identity["worker_netns_identity"],
        "n8n_container_id": identity["n8n_container_id"],
        "closed_set": identity["closed_set"],
        "network_mode": identity.get("network_mode", ""),
        "sequence": sequence,
    }
    identity["topology_attestation_sha256"] = sha256_hex(canonical_bytes(body))
    identity["topology_attestation_sequence"] = str(sequence)
    identity["live"] = "YES"
    return identity


def topology_attestation_sha256(identity: dict[str, Any]) -> str:
    raw = identity.get("topology_attestation_sha256")
    if not isinstance(raw, str) or len(raw) != 64:
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "topology attestation hash missing",
            state="FAILED_FROZEN",
        )
    return raw
