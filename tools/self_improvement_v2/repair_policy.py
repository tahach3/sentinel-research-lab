"""Repair proposal anti-broadening rules for Self-Improvement Loop V2."""

from __future__ import annotations

from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.path_policy import match_patterns, normalize_rel_path


PROFILE_STRICTNESS = {
    "DOCUMENTATION_ONLY": 0,
    "WORKFLOW_DESIGN_STATIC": 1,
    "PYTHON_TOOLING": 2,
    "SELF_IMPROVEMENT_TESTS": 3,
}


def assert_repair_not_broadening(parent: dict[str, Any], repair: dict[str, Any]) -> None:
    if int(repair.get("repair_attempt") or 0) != 1:
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair_attempt must be 1 for repair proposals",
            state="POLICY_REJECTED",
        )
    if repair.get("parent_proposal_id") != parent.get("proposal_id"):
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair must reference parent_proposal_id",
            state="POLICY_REJECTED",
        )
    if repair.get("repository_id") != parent.get("repository_id"):
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair changed repository",
            state="POLICY_REJECTED",
        )
    if repair.get("baseline_sha") != parent.get("baseline_sha"):
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair changed baseline",
            state="POLICY_REJECTED",
        )
    if repair.get("risk_level") != "LOW":
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair must remain LOW risk",
            state="POLICY_REJECTED",
        )
    if repair.get("risk_level") != parent.get("risk_level") and parent.get("risk_level") == "LOW":
        # raising risk already rejected above if not LOW
        pass
    risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "PROHIBITED": 3}
    if risk_order.get(str(repair.get("risk_level")), 99) > risk_order.get(str(parent.get("risk_level")), 0):
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair raised risk",
            state="POLICY_REJECTED",
        )

    parent_allowed = [normalize_rel_path(p) for p in parent.get("allowed_paths") or []]
    repair_allowed = [normalize_rel_path(p) for p in repair.get("allowed_paths") or []]
    for path in repair_allowed:
        if not match_patterns(path if not path.endswith("/**") else path, parent_allowed):
            # each repair allowed pattern must be covered by parent allow list
            if not any(
                path == pa
                or (pa.endswith("/**") and (path == pa[:-3] or path.startswith(pa[:-3] + "/") or path.startswith(pa[:-3])))
                or path.startswith(pa.rstrip("*").rstrip("/"))
                for pa in parent_allowed
            ):
                raise WorkerError(
                    ERROR_CODES["REPAIR_BROADENING"],
                    "repair broadened allowed paths",
                    state="POLICY_REJECTED",
                )

    parent_forbidden = set(normalize_rel_path(p) for p in parent.get("forbidden_paths") or [])
    repair_forbidden = set(normalize_rel_path(p) for p in repair.get("forbidden_paths") or [])
    if not parent_forbidden.issubset(repair_forbidden):
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair dropped forbidden paths",
            state="POLICY_REJECTED",
        )

    parent_files = int(parent.get("maximum_changed_files") or 8)
    repair_files = int(repair.get("maximum_changed_files") or parent_files)
    if repair_files > parent_files:
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair increased file limit",
            state="POLICY_REJECTED",
        )
    parent_lines = int(parent.get("maximum_total_added_and_removed_lines") or 500)
    repair_lines = int(repair.get("maximum_total_added_and_removed_lines") or parent_lines)
    if repair_lines > parent_lines:
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair increased diff limit",
            state="POLICY_REJECTED",
        )

    parent_profile = str(parent.get("validation_profile"))
    repair_profile = str(repair.get("validation_profile"))
    if PROFILE_STRICTNESS.get(repair_profile, -1) < PROFILE_STRICTNESS.get(parent_profile, 0):
        raise WorkerError(
            ERROR_CODES["REPAIR_BROADENING"],
            "repair weakened validation profile",
            state="POLICY_REJECTED",
        )

    blob = str(repair).lower()
    for banned in (
        "credential",
        "network_allowed",
        "database/migrations",
        "deploy",
        "workflows/active",
    ):
        if banned in blob and banned not in str(parent).lower():
            # soft check — structural path policy still primary
            pass


def assert_repair_attempt_allowed(repair_attempt: int) -> None:
    if repair_attempt > 1:
        raise WorkerError(
            ERROR_CODES["REPAIR_LIMIT_REACHED"],
            "second repair attempt prohibited",
            state="REPAIR_LIMIT_REACHED",
        )
    if repair_attempt > 1:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "repair limit reached",
            state="FAILED_FROZEN",
        )
