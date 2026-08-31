"""Revision 2.5 complete finalization-result contract. Hash only after one write."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement_v2.option_a_constants import COMMIT_SHA_RE, HEX64_RE, SRL_CANDIDATE_REF
from tools.self_improvement_v2.schema_loader import validate_instance

REV25_FINALIZATION_SCHEMA: Final = SCHEMA_VERSION
REV25_FINALIZATION_REQUIRED: Final = (
    "schema_version",
    "execution_id",
    "review_id",
    "binding_verified",
    "reviewed_head",
    "authorized_baseline",
    "candidate_commit",
    "candidate_tree",
    "candidate_branch",
    "committed_tree_sha",
    "committed_diff_sha256",
    "final_state",
    "error_codes",
    "learning_record_id",
)


def _frozen(message: str) -> WorkerError:
    return WorkerError(ERROR_CODES["FAILED_FROZEN"], message, state="FAILED_FROZEN")


def validate_rev25_finalization_result(instance: dict[str, Any]) -> None:
    if not isinstance(instance, dict):
        raise _frozen("finalization_result must be an object")
    if instance.get("schema_version") != REV25_FINALIZATION_SCHEMA:
        raise _frozen("unknown/invalid finalization_result schema version")
    missing = [name for name in REV25_FINALIZATION_REQUIRED if name not in instance]
    if missing:
        raise _frozen(f"finalization_result missing required fields: {missing}")
    if instance.get("reviewed_head") != instance.get("authorized_baseline"):
        raise _frozen("authorized_baseline must equal reviewed_head")
    for key in ("reviewed_head", "authorized_baseline", "candidate_commit", "candidate_tree", "committed_tree_sha"):
        value = str(instance.get(key) or "")
        if not COMMIT_SHA_RE.fullmatch(value):
            raise _frozen(f"finalization_result {key} is not a commit/tree identity")
    if instance.get("candidate_tree") != instance.get("committed_tree_sha"):
        raise _frozen("candidate_tree must equal committed_tree_sha")
    if instance.get("candidate_branch") != SRL_CANDIDATE_REF:
        raise _frozen("candidate_branch must be refs/heads/srl-candidate")
    diff_sha = str(instance.get("committed_diff_sha256") or "")
    if not HEX64_RE.fullmatch(diff_sha):
        raise _frozen("committed_diff_sha256 must be 64 hex")
    if instance.get("binding_verified") is not True:
        raise _frozen("binding_verified must be true before FINALIZED")
    if not str(instance.get("execution_id") or "").strip():
        raise _frozen("execution_id missing")
    if not str(instance.get("review_id") or "").strip():
        raise _frozen("review_id missing")
    if not str(instance.get("final_state") or "").strip():
        raise _frozen("final_state missing")
    if not isinstance(instance.get("error_codes"), list):
        raise _frozen("error_codes must be a list")
    if not str(instance.get("learning_record_id") or "").strip():
        raise _frozen("learning_record_id missing")
    try:
        validate_instance("finalization_result", instance)
    except WorkerError as exc:
        raise _frozen(exc.message) from exc


def serialize_finalization_result(instance: dict[str, Any]) -> bytes:
    validate_rev25_finalization_result(instance)
    return json.dumps(instance, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def finalization_result_sha256(instance: dict[str, Any]) -> str:
    return hashlib.sha256(serialize_finalization_result(instance)).hexdigest()
