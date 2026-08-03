"""Autonomous-lane policy loading and enforcement."""

from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Any

from tools.self_improvement.models import ERROR_CODES, WorkerError
from tools.self_improvement.schema_loader import worker_package_root

POLICY_REL = Path("specs/self_improvement/v1/policy.json")


@lru_cache(maxsize=4)
def _load_policy_cached(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_policy(root: Path | None = None) -> dict[str, Any]:
    base = root if root is not None else worker_package_root()
    path = (base / POLICY_REL).resolve()
    if not path.is_file():
        path = (worker_package_root() / POLICY_REL).resolve()
    policy = _load_policy_cached(str(path))
    lane = policy.get("autonomous_lane") or {}
    if not lane.get("allowed_paths"):
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "policy missing allowed_paths")
    profiles = policy.get("validation_profiles") or {}
    for name, profile in profiles.items():
        commands = profile.get("commands")
        if not isinstance(commands, list) or not commands:
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], f"profile {name} has no commands")
        for cmd in commands:
            if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
                raise WorkerError(
                    ERROR_CODES["POLICY_REJECTED"],
                    f"profile {name} commands must be argv string arrays",
                )
    return policy


def normalize_rel_path(path: str) -> str:
    cleaned = path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def is_absolute_path(path: str) -> bool:
    p = path.replace("\\", "/")
    if p.startswith("/") or p.startswith("~"):
        return True
    if re.match(r"^[A-Za-z]:/", p):
        return True
    return False


def has_traversal(path: str) -> bool:
    parts = normalize_rel_path(path).split("/")
    return any(part == ".." for part in parts)


def match_patterns(path: str, patterns: list[str]) -> bool:
    norm = normalize_rel_path(path)
    for pattern in patterns:
        pat = normalize_rel_path(pattern)
        if fnmatch(norm, pat) or fnmatch(norm, pat.rstrip("/")):
            return True
        # Directory prefix match for patterns ending with /**
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if norm == prefix or norm.startswith(prefix + "/"):
                return True
        if pat.endswith("/*"):
            prefix = pat[:-2]
            if norm.startswith(prefix + "/"):
                return True
    return False


def path_is_migration(path: str) -> bool:
    norm = normalize_rel_path(path)
    return (
        norm.startswith("database/migrations/")
        or norm.startswith("database/init/")
        or match_patterns(norm, ["database/migrations/**", "database/init/**"])
    )


def assert_path_allowed(path: str, policy: dict[str, Any], proposal: dict[str, Any] | None = None) -> None:
    norm = normalize_rel_path(path)
    if is_absolute_path(norm) or is_absolute_path(path):
        raise WorkerError(ERROR_CODES["ABSOLUTE_PATH"], f"absolute path: {path}", state="PATCH_REJECTED")
    if has_traversal(norm):
        raise WorkerError(ERROR_CODES["PATH_TRAVERSAL"], f"traversal: {path}", state="PATCH_REJECTED")
    if norm.startswith(".git/") or norm == ".git":
        raise WorkerError(ERROR_CODES["FORBIDDEN_PATH"], f"git path: {path}", state="PATCH_REJECTED")
    if path_is_migration(norm):
        raise WorkerError(ERROR_CODES["MIGRATION_PATH"], f"migration path: {path}", state="POLICY_REJECTED")

    lane = policy["autonomous_lane"]
    forbidden = list(lane.get("forbidden_paths") or [])
    if proposal is not None:
        forbidden.extend(proposal.get("forbidden_paths") or [])
    if match_patterns(norm, forbidden):
        raise WorkerError(ERROR_CODES["FORBIDDEN_PATH"], f"forbidden path: {path}", state="POLICY_REJECTED")

    allowed = list(lane.get("allowed_paths") or [])
    if proposal is not None:
        # Proposal allowed_paths may only narrow the lane.
        proposal_allowed = proposal.get("allowed_paths") or allowed
        if not match_patterns(norm, proposal_allowed):
            raise WorkerError(
                ERROR_CODES["FORBIDDEN_PATH"],
                f"outside proposal allowed_paths: {path}",
                state="POLICY_REJECTED",
            )
    if not match_patterns(norm, allowed):
        raise WorkerError(
            ERROR_CODES["FORBIDDEN_PATH"],
            f"outside autonomous allowed_paths: {path}",
            state="POLICY_REJECTED",
        )


def classify_and_authorize(proposal: dict[str, Any], policy: dict[str, Any]) -> str:
    risk = proposal.get("risk_level")
    lane = policy["autonomous_lane"]
    if risk not in lane.get("risk_levels", []):
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], f"unknown risk: {risk}", state="POLICY_REJECTED")

    for patch in proposal.get("patches") or []:
        op = patch.get("operation")
        path = patch.get("path", "")
        if op == "DELETE":
            raise WorkerError(
                ERROR_CODES["DELETION_PROHIBITED"],
                "deletion prohibited in autonomous lane",
                state="POLICY_REJECTED",
            )
        assert_path_allowed(path, policy, proposal)

    if proposal.get("human_approval_required") is True:
        raise WorkerError(
            ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
            "human approval required",
            state="DECISION_REQUIRED",
        )
    if risk not in lane.get("auto_authorize_risk_levels", []):
        state = "POLICY_REJECTED" if risk == "PROHIBITED" else "DECISION_REQUIRED"
        raise WorkerError(
            ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
            f"risk {risk} not auto-authorized",
            state=state,
        )
    return "AUTO_AUTHORIZED"


def get_validation_profile(policy: dict[str, Any], name: str) -> dict[str, Any]:
    profiles = policy.get("validation_profiles") or {}
    if name not in profiles:
        raise WorkerError(
            ERROR_CODES["PROHIBITED_VALIDATION_PROFILE"],
            f"unknown validation profile: {name}",
            state="POLICY_REJECTED",
        )
    return profiles[name]


def limits(policy: dict[str, Any]) -> dict[str, Any]:
    return dict(policy["autonomous_lane"]["limits"])
