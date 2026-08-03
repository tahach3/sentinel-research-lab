"""Shared models and stable error codes for the self-improvement worker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0.0"

SUCCESS_STATES = (
    "CANDIDATE_RECEIVED",
    "RESEARCH_VALIDATED",
    "PROPOSAL_VALIDATED",
    "RISK_CLASSIFIED",
    "AUTO_AUTHORIZED",
    "WORKTREE_PREPARED",
    "PATCH_VALIDATED",
    "PATCH_APPLIED",
    "VALIDATING",
    "INDEPENDENT_REVIEW",
    "CANDIDATE_COMMITTED",
    "LEARNING_RECORDED",
    "READY_FOR_HUMAN_PROMOTION",
)

FAILURE_STATES = (
    "DECISION_REQUIRED",
    "BASELINE_MISMATCH",
    "POLICY_REJECTED",
    "PATCH_REJECTED",
    "VALIDATION_FAILED",
    "REVIEW_FAILED",
    "REPAIR_LIMIT_REACHED",
    "FAILED_FROZEN",
)

ERROR_CODES = {
    "BASELINE_MISMATCH": "BASELINE_MISMATCH",
    "DIRTY_SOURCE_TREE": "DIRTY_SOURCE_TREE",
    "FORBIDDEN_PATH": "FORBIDDEN_PATH",
    "PATH_TRAVERSAL": "PATH_TRAVERSAL",
    "ABSOLUTE_PATH": "ABSOLUTE_PATH",
    "BINARY_PATCH": "BINARY_PATCH",
    "DELETION_PROHIBITED": "DELETION_PROHIBITED",
    "PREIMAGE_MISMATCH": "PREIMAGE_MISMATCH",
    "POSTIMAGE_MISMATCH": "POSTIMAGE_MISMATCH",
    "TOO_MANY_FILES": "TOO_MANY_FILES",
    "EXCESSIVE_DIFF": "EXCESSIVE_DIFF",
    "EXCESSIVE_PATCH_SIZE": "EXCESSIVE_PATCH_SIZE",
    "PROHIBITED_VALIDATION_PROFILE": "PROHIBITED_VALIDATION_PROFILE",
    "COMMAND_INJECTION": "COMMAND_INJECTION",
    "VALIDATION_TIMEOUT": "VALIDATION_TIMEOUT",
    "ACCEPTANCE_FAILED": "ACCEPTANCE_FAILED",
    "SELF_REVIEW": "SELF_REVIEW",
    "MISSING_INDEPENDENT_REVIEW": "MISSING_INDEPENDENT_REVIEW",
    "REVIEW_NOT_PASS": "REVIEW_NOT_PASS",
    "REPAIR_LIMIT_REACHED": "REPAIR_LIMIT_REACHED",
    "COMMIT_BEFORE_REVIEW": "COMMIT_BEFORE_REVIEW",
    "SOURCE_REPO_CHANGED": "SOURCE_REPO_CHANGED",
    "CREDENTIALS_IN_WORKFLOW": "CREDENTIALS_IN_WORKFLOW",
    "WORKFLOW_ACTIVE": "WORKFLOW_ACTIVE",
    "PUSH_ATTEMPT": "PUSH_ATTEMPT",
    "MERGE_ATTEMPT": "MERGE_ATTEMPT",
    "MIGRATION_PATH": "MIGRATION_PATH",
    "POLICY_REJECTED": "POLICY_REJECTED",
    "PATCH_REJECTED": "PATCH_REJECTED",
    "VALIDATION_FAILED": "VALIDATION_FAILED",
    "REVIEW_FAILED": "REVIEW_FAILED",
    "FAILED_FROZEN": "FAILED_FROZEN",
    "SYMLINK_PROHIBITED": "SYMLINK_PROHIBITED",
    "SUBMODULE_CHANGE": "SUBMODULE_CHANGE",
    "GIT_APPLY_CHECK_FAILED": "GIT_APPLY_CHECK_FAILED",
    "SCHEMA_INVALID": "SCHEMA_INVALID",
    "RISK_NOT_AUTO_AUTHORIZED": "RISK_NOT_AUTO_AUTHORIZED",
}


@dataclass
class WorkerError(Exception):
    code: str
    message: str
    state: str = "FAILED_FROZEN"

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass
class ExecutionContext:
    proposal: dict[str, Any]
    root: Any
    state_db: Any
    run_id: str
    repair_attempt: int = 0
    error_codes: list[str] = field(default_factory=list)
    final_state: str = "CANDIDATE_RECEIVED"
    changed_paths: list[str] = field(default_factory=list)
    patch_results: list[dict[str, Any]] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    diff_summary: dict[str, int] = field(
        default_factory=lambda: {
            "files_changed": 0,
            "lines_added": 0,
            "lines_removed": 0,
            "patch_bytes": 0,
        }
    )
    candidate_commit: str | None = None
    branch_name: str | None = None
    worktree_prepared: bool = False
    baseline_verified: bool = False
