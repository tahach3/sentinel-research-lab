"""Consume live INV-TOPO results only. Cached topology cannot satisfy a gate."""

from __future__ import annotations

from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.topology_attest import live_reassert


def consume_live_reassert(result: dict[str, Any], *, prior_pass: dict[str, Any] | None = None) -> dict[str, Any]:
    if result.get("from_cache") is True or result.get("live") != "YES":
        raise WorkerError(
            ERROR_CODES["CACHED_TOPOLOGY_AUTHORITY"],
            "CACHED_TOPOLOGY_AUTHORITY=FORBIDDEN",
            state="FAILED_FROZEN",
        )
    if prior_pass is not None and result is prior_pass:
        raise WorkerError(
            ERROR_CODES["CACHED_TOPOLOGY_AUTHORITY"],
            "a prior PASS MUST NOT satisfy a later gate",
            state="FAILED_FROZEN",
        )
    return result


def require_independent_live(
    *,
    inspect_worker,
    inspect_n8n,
    list_all_ids,
    worker_id: str,
    n8n_id: str,
    sequence: int,
    previous: dict[str, str] | None = None,
    expected_image_digest: str | None = None,
    prior_pass: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if prior_pass is not None and prior_pass.get("satisfy_later_gate"):
        raise WorkerError(
            ERROR_CODES["CACHED_TOPOLOGY_AUTHORITY"],
            "a prior PASS MUST NOT satisfy a later gate",
            state="FAILED_FROZEN",
        )
    live = live_reassert(
        inspect_worker=inspect_worker,
        inspect_n8n=inspect_n8n,
        list_all_ids=list_all_ids,
        worker_id=worker_id,
        n8n_id=n8n_id,
        expected_image_digest=expected_image_digest,
        previous=previous,
        sequence=sequence,
    )
    return consume_live_reassert(live, prior_pass=prior_pass)
