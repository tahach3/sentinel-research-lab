"""Launcher-owned FINALIZED_ATTESTATION: exactly one complete write."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.canonical import canonical_bytes, sha256_hex
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import (
    COMMIT_SHA_RE,
    CONTAINER_ID_RE,
    EXECUTION_ID_RE,
    HEX64_RE,
    SCHEMA_FINALIZED_ATTESTATION,
    SRL_CANDIDATE_REF,
    STAGING_GENERATION_RE,
)

REQUIRED_FIELDS = (
    "schema_version",
    "execution_id",
    "reviewed_head",
    "authorized_baseline",
    "candidate_commit",
    "candidate_tree",
    "srl_candidate_ref",
    "finalization_result_sha256",
    "sealed_inventory_sha256",
    "sealed_artifact_hashes",
    "staging_generation",
    "worker_container_id",
    "worker_started_at",
    "worker_image_digest",
    "worker_netns_identity",
    "n8n_container_id",
    "topology_attestation_identity",
    "topology_attestation_sequence",
    "launcher_observation_sequence",
    "observed_unix_ts",
)


def attestation_path(ledger_root: Path) -> Path:
    return ledger_root / "finalized_attestation.json"


def _require_hex40(name: str, value: str) -> str:
    if not COMMIT_SHA_RE.fullmatch(value or ""):
        raise WorkerError(
            ERROR_CODES["ATTESTATION_INCOMPLETE"],
            f"{name} must be 40 hex",
            state="FAILED_FROZEN",
        )
    return value


def _require_hex64(name: str, value: str) -> str:
    if not HEX64_RE.fullmatch(value or ""):
        raise WorkerError(
            ERROR_CODES["ATTESTATION_INCOMPLETE"],
            f"{name} must be 64 hex",
            state="FAILED_FROZEN",
        )
    return value


def build_attestation_body(fields: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in REQUIRED_FIELDS if k not in fields]
    if missing:
        raise WorkerError(
            ERROR_CODES["ATTESTATION_INCOMPLETE"],
            f"incomplete attestation: {missing}",
            state="FAILED_FROZEN",
        )
    for key in REQUIRED_FIELDS:
        val = fields[key]
        if val is None or val == "" or val == "PENDING":
            raise WorkerError(
                ERROR_CODES["ATTESTATION_INCOMPLETE"],
                f"attestation field empty/PENDING: {key}",
                state="FAILED_FROZEN",
            )
    if fields["schema_version"] != SCHEMA_FINALIZED_ATTESTATION:
        raise WorkerError(
            ERROR_CODES["ATTESTATION_INCOMPLETE"],
            "schema_version must be srl.finalized_attestation.v2_5",
            state="FAILED_FROZEN",
        )
    if not EXECUTION_ID_RE.fullmatch(str(fields["execution_id"])):
        raise WorkerError(
            ERROR_CODES["EXECUTION_ID_GRAMMAR"],
            "execution_id must be 32 hex",
            state="FAILED_FROZEN",
        )
    _require_hex40("reviewed_head", str(fields["reviewed_head"]))
    _require_hex40("authorized_baseline", str(fields["authorized_baseline"]))
    _require_hex40("candidate_commit", str(fields["candidate_commit"]))
    _require_hex40("candidate_tree", str(fields["candidate_tree"]))
    if fields["srl_candidate_ref"] != SRL_CANDIDATE_REF:
        raise WorkerError(
            ERROR_CODES["ATTESTATION_INCOMPLETE"],
            "srl_candidate_ref mismatch",
            state="FAILED_FROZEN",
        )
    _require_hex64("finalization_result_sha256", str(fields["finalization_result_sha256"]))
    _require_hex64("sealed_inventory_sha256", str(fields["sealed_inventory_sha256"]))
    hashes = fields["sealed_artifact_hashes"]
    if not isinstance(hashes, dict) or not hashes:
        raise WorkerError(
            ERROR_CODES["ATTESTATION_INCOMPLETE"],
            "sealed_artifact_hashes missing",
            state="FAILED_FROZEN",
        )
    if not STAGING_GENERATION_RE.fullmatch(str(fields["staging_generation"])):
        raise WorkerError(
            ERROR_CODES["ATTESTATION_INCOMPLETE"],
            "staging_generation must be 8 hex",
            state="FAILED_FROZEN",
        )
    if not CONTAINER_ID_RE.fullmatch(str(fields["worker_container_id"])):
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            "worker_container_id must be 64 hex",
            state="FAILED_FROZEN",
        )
    if not CONTAINER_ID_RE.fullmatch(str(fields["n8n_container_id"])):
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            "n8n_container_id must be 64 hex",
            state="FAILED_FROZEN",
        )
    _require_hex64("topology_attestation_identity", str(fields["topology_attestation_identity"]))
    body = {k: fields[k] for k in REQUIRED_FIELDS}
    return body


def attestation_sha256(body: dict[str, Any]) -> str:
    return sha256_hex(canonical_bytes(body))


def write_finalized_attestation(ledger_root: Path, fields: dict[str, Any]) -> dict[str, Any]:
    path = attestation_path(ledger_root)
    if path.exists():
        raise WorkerError(
            ERROR_CODES["ATTESTATION_EXISTS"],
            "FINALIZED_ATTESTATION already exists; overwrite forbidden",
            state="FAILED_FROZEN",
        )
    body = build_attestation_body(fields)
    digest = attestation_sha256(body)
    record = dict(body)
    record["attestation_sha256"] = digest
    ledger_root.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)
    path.chmod(path.stat().st_mode & ~0o222)
    return record


def load_finalized_attestation(ledger_root: Path) -> dict[str, Any]:
    path = attestation_path(ledger_root)
    if not path.is_file():
        raise WorkerError(
            ERROR_CODES["ATTESTATION_INCOMPLETE"],
            "FINALIZED_ATTESTATION missing",
            state="FAILED_FROZEN",
        )
    return json.loads(path.read_text(encoding="utf-8"))
