"""Cleanup reconstructs worker paths from ledger identity. ACK ≠ deleted."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import EXECUTION_ID_RE, EXECUTION_ROOT_PREFIX

STATES = (
    "EXPORT_VERIFIED",
    "ACKNOWLEDGED",
    "CLEANUP_PENDING",
    "CLEANED",
    "CLEANUP_PARTIAL",
    "FAILED_FROZEN",
)


def reconstruct_execution_root(execution_id: str) -> str:
    if not EXECUTION_ID_RE.fullmatch(execution_id):
        raise WorkerError(
            ERROR_CODES["EXECUTION_ID_GRAMMAR"],
            "cleanup execution_id must be 32 hex",
            state="FAILED_FROZEN",
        )
    return f"{EXECUTION_ROOT_PREFIX}/{execution_id}"


def refuse_manifest_deletion_path(manifest_path: str | None, execution_id: str) -> str:
    reconstructed = reconstruct_execution_root(execution_id)
    if manifest_path and manifest_path.replace("\\", "/") != reconstructed:
        raise WorkerError(
            ERROR_CODES["UNSAFE_CLEANUP_TARGET"],
            "manifest deletion path is not authority",
            state="FAILED_FROZEN",
        )
    return reconstructed


def write_ack(ledger_root: Path, execution_id: str) -> Path:
    if not EXECUTION_ID_RE.fullmatch(execution_id):
        raise WorkerError(
            ERROR_CODES["EXECUTION_ID_GRAMMAR"],
            "ACK execution_id must be 32 hex",
            state="FAILED_FROZEN",
        )
    path = ledger_root / "ACK.json"
    path.write_text(
        '{"schema":"srl.ack.v1","execution_id":"%s","acknowledged":true}\n' % execution_id,
        encoding="utf-8",
    )
    return path


def apply_cleanup(
    *,
    execution_id: str,
    ledger_state: str,
    delete_fn: Callable[[str], bool],
    manifest_path: str | None = None,
) -> str:
    target = refuse_manifest_deletion_path(manifest_path, execution_id)
    if ledger_state == "ACKNOWLEDGED":
        # ACK is not deletion.
        next_state = "CLEANUP_PENDING"
    elif ledger_state in {"EXPORT_VERIFIED", "CLEANUP_PENDING", "CLEANUP_PARTIAL"}:
        next_state = "CLEANUP_PENDING"
    else:
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            f"cleanup not permitted from {ledger_state}",
            state="FAILED_FROZEN",
        )
    deleted = delete_fn(target)
    if deleted:
        return "CLEANED"
    return "CLEANUP_PARTIAL"
