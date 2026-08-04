"""Executable risk authority for Self-Improvement Loop V2.

Only the worker derives and enforces risk. Proposer risk_level may raise but
never lower computed risk. Pre-authorization classifies patch text without
applying patches or creating worktrees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.patch_parser import parse_unified_diff, paths_from_parsed
from tools.self_improvement_v2.path_policy import (
    FORBIDDEN_ROOT_PATTERNS,
    assert_path_allowed,
    limits,
    match_patterns,
    normalize_rel_path,
)
from tools.self_improvement_v2.repair_policy import PROFILE_STRICTNESS

RISK_CLASSIFIER_VERSION = "2.1.0"

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "PROHIBITED": 3}

DECISION_AUTHORIZED = "AUTHORIZED"
DECISION_REQUIRED = "DECISION_REQUIRED"
DECISION_POLICY_REJECTED = "POLICY_REJECTED"

# Paths that elevate to HIGH (security-sensitive worker modules).
SECURITY_SENSITIVE_GLOBS = [
    "tools/self_improvement_v2/path_policy.py",
    "tools/self_improvement_v2/risk_authority.py",
    "tools/self_improvement_v2/git_worker.py",
    "tools/self_improvement_v2/finalizer.py",
    "tools/self_improvement_v2/runtime_bridge.py",
    "tools/self_improvement_v2/review_gate.py",
    "tools/self_improvement_v2/experience_store.py",
]

DEPENDENCY_GLOBS = [
    "requirements.txt",
    "requirements*.txt",
    "pyproject.toml",
    "Pipfile",
    "Pipfile.lock",
    "package.json",
    "package-lock.json",
    "poetry.lock",
]

MIGRATION_GLOBS = [
    "database/migrations/**",
    "database/init/**",
    "database/**",
]

ACTIVE_WORKFLOW_GLOBS = [
    "workflows/active/**",
    ".github/workflows/**",
]

CREDENTIAL_GLOBS = [
    "credentials/**",
    "secrets/**",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
]

NETWORK_CONTENT_MARKERS = (
    "import requests",
    "import httpx",
    "import urllib",
    "from urllib",
    "import socket",
    "aiohttp",
    "http.client",
    "subprocess with network",
)


@dataclass
class RiskAssessment:
    declared_risk: str
    computed_risk: str
    effective_risk: str
    reason_codes: list[str] = field(default_factory=list)
    file_count: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    patch_bytes: int = 0
    paths: list[str] = field(default_factory=list)
    classifier_version: str = RISK_CLASSIFIER_VERSION


@dataclass
class AuthorizationResult:
    decision: str
    declared_risk: str
    computed_risk_pre: str
    effective_risk_pre: str
    risk_reason_codes_pre: list[str]
    risk_classifier_version: str
    policy_sha256: str | None = None
    error_code: str | None = None
    message: str = ""


def risk_rank(level: str) -> int:
    return RISK_ORDER.get(str(level), 99)


def stricter(*levels: str) -> str:
    best = "LOW"
    for level in levels:
        if risk_rank(level) > risk_rank(best):
            best = str(level)
    return best


def _count_diff_lines(unified_diff: str) -> tuple[int, int]:
    added = 0
    removed = 0
    for line in unified_diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _required_profile_floor(paths: list[str]) -> int:
    """Minimum PROFILE_STRICTNESS required for the path set."""
    floor = 0
    for path in paths:
        norm = normalize_rel_path(path)
        if match_patterns(norm, ["tools/**", "tests/**", "specs/**"]):
            floor = max(floor, PROFILE_STRICTNESS["PYTHON_TOOLING"])
        if match_patterns(norm, ["workflows/**"]):
            floor = max(floor, PROFILE_STRICTNESS["WORKFLOW_DESIGN_STATIC"])
        if match_patterns(norm, ["docs/**"]) and floor == 0:
            floor = max(floor, PROFILE_STRICTNESS["DOCUMENTATION_ONLY"])
    return floor


def _path_risk(path: str, reasons: list[str]) -> str:
    norm = normalize_rel_path(path)
    level = "LOW"
    if match_patterns(norm, MIGRATION_GLOBS) or match_patterns(norm, FORBIDDEN_ROOT_PATTERNS):
        if match_patterns(norm, MIGRATION_GLOBS) or "database/" in norm:
            reasons.append("RISK_MIGRATION")
            level = stricter(level, "PROHIBITED")
        if match_patterns(norm, ACTIVE_WORKFLOW_GLOBS):
            reasons.append("RISK_ACTIVE_WORKFLOW")
            level = stricter(level, "PROHIBITED")
    if match_patterns(norm, ACTIVE_WORKFLOW_GLOBS):
        if "RISK_ACTIVE_WORKFLOW" not in reasons:
            reasons.append("RISK_ACTIVE_WORKFLOW")
        level = stricter(level, "PROHIBITED")
    if match_patterns(norm, CREDENTIAL_GLOBS) or any(
        seg in normalize_rel_path(path).lower().split("/")
        for seg in ("credentials", "credential", "secrets", "secret", "private_keys")
    ):
        reasons.append("RISK_CREDENTIAL")
        level = stricter(level, "PROHIBITED")
    basename = norm.split("/")[-1].lower()
    if basename == ".env" or basename.startswith(".env."):
        if "RISK_CREDENTIAL" not in reasons:
            reasons.append("RISK_CREDENTIAL")
        level = stricter(level, "PROHIBITED")
    if match_patterns(norm, DEPENDENCY_GLOBS):
        reasons.append("RISK_DEPENDENCY")
        level = stricter(level, "HIGH")
    if match_patterns(norm, SECURITY_SENSITIVE_GLOBS):
        reasons.append("RISK_SECURITY_SENSITIVE")
        level = stricter(level, "HIGH")
    if match_patterns(norm, ["workflows/design/**"]):
        # Design workflows are allowed but not auto-LOW when mixed with other scopes.
        pass
    return level


def extract_proposal_features(proposal: dict[str, Any]) -> dict[str, Any]:
    """Parse proposal patch text into structural features (no apply)."""
    paths: list[str] = []
    ops: list[str] = []
    added = 0
    removed = 0
    patch_bytes = 0
    content_blob_parts: list[str] = []
    for patch in proposal.get("patches") or []:
        diff = str(patch.get("unified_diff") or "")
        patch_bytes += len(diff.encode("utf-8"))
        content_blob_parts.append(diff.lower())
        parsed = parse_unified_diff(diff)
        for p in paths_from_parsed(parsed):
            norm = normalize_rel_path(p)
            if norm not in paths:
                paths.append(norm)
        meta_path = normalize_rel_path(str(patch.get("path") or ""))
        if meta_path and meta_path not in paths:
            # Still record metadata path, but classification trusts parsed paths.
            pass
        op = str(patch.get("operation") or "")
        if parsed.is_delete or op == "DELETE":
            ops.append("DELETE")
        elif parsed.is_rename or op == "RENAME":
            ops.append("RENAME")
        elif parsed.is_copy or op == "COPY":
            ops.append("COPY")
        elif parsed.is_create or op == "CREATE":
            ops.append("CREATE")
        else:
            ops.append("MODIFY")
        a, r = _count_diff_lines(diff)
        added += a
        removed += r
    return {
        "paths": paths,
        "operations": ops,
        "file_count": len(paths),
        "lines_added": added,
        "lines_removed": removed,
        "patch_bytes": patch_bytes,
        "content_blob": "\n".join(content_blob_parts),
        "validation_profile": str(proposal.get("validation_profile") or ""),
    }


def compute_risk_from_features(
    features: dict[str, Any],
    *,
    policy: dict[str, Any],
    proposal: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    level = "LOW"
    paths = list(features.get("paths") or [])
    for path in paths:
        level = stricter(level, _path_risk(path, reasons))

    for op in features.get("operations") or []:
        if op == "DELETE":
            reasons.append("RISK_DELETION")
            level = stricter(level, "PROHIBITED")
        if op in ("RENAME", "COPY"):
            reasons.append("RISK_RENAME_OR_COPY")
            level = stricter(level, "PROHIBITED")

    lim = limits(policy)
    max_files = int(lim["maximum_changed_files"])
    max_lines = int(lim["maximum_total_added_and_removed_lines"])
    max_bytes = int(lim["maximum_patch_size_bytes"])
    if proposal is not None:
        if proposal.get("maximum_changed_files") is not None:
            max_files = min(max_files, int(proposal["maximum_changed_files"]))
        if proposal.get("maximum_total_added_and_removed_lines") is not None:
            max_lines = min(max_lines, int(proposal["maximum_total_added_and_removed_lines"]))

    file_count = int(features.get("file_count") or 0)
    total_lines = int(features.get("lines_added") or 0) + int(features.get("lines_removed") or 0)
    patch_bytes = int(features.get("patch_bytes") or 0)
    if file_count > max_files:
        reasons.append("RISK_EXCESSIVE_FILES")
        level = stricter(level, "MEDIUM")
    if total_lines > max_lines:
        reasons.append("RISK_EXCESSIVE_DIFF")
        level = stricter(level, "MEDIUM")
    if patch_bytes > max_bytes:
        reasons.append("RISK_EXCESSIVE_PATCH_BYTES")
        level = stricter(level, "MEDIUM")

    profile = str(features.get("validation_profile") or "")
    profile_rank = PROFILE_STRICTNESS.get(profile, -1)
    if profile_rank < 0:
        reasons.append("RISK_UNKNOWN_VALIDATION_PROFILE")
        level = stricter(level, "PROHIBITED")
    else:
        floor = _required_profile_floor(paths)
        if profile_rank < floor:
            reasons.append("RISK_INSUFFICIENT_VALIDATION")
            level = stricter(level, "MEDIUM")

    blob = str(features.get("content_blob") or "")
    for marker in NETWORK_CONTENT_MARKERS:
        if marker in blob:
            reasons.append("RISK_NETWORK_CAPABLE")
            level = stricter(level, "HIGH")
            break

    # Deduplicate reason codes while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for code in reasons:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return level, ordered


def classify_pre_application(
    proposal: dict[str, Any],
    policy: dict[str, Any],
) -> RiskAssessment:
    declared = str(proposal.get("risk_level") or "")
    if declared not in RISK_ORDER:
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            f"unknown declared risk: {declared}",
            state="POLICY_REJECTED",
        )
    features = extract_proposal_features(proposal)
    # Path allow/deny contributes to computed risk; do not trust proposal summaries.
    for path in features["paths"]:
        try:
            assert_path_allowed(path, policy, proposal)
        except WorkerError as exc:
            # Forbidden/protected paths elevate; keep original code in reasons.
            if "RISK_PATH_POLICY" not in features.get("_path_errors", []):
                pass
            computed_extra = "PROHIBITED"
            if exc.code in {
                ERROR_CODES["SI2-PATH-FORBIDDEN-ROOT"],
                ERROR_CODES["SI2-PATH-PROTECTED-SEGMENT"],
                ERROR_CODES["SI2-PATH-PROTECTED-BASENAME"],
            }:
                # Specific path risks already covered; still mark prohibited.
                features.setdefault("_forced_reasons", []).append("RISK_PATH_POLICY_DENY")
                features["_forced_level"] = stricter(features.get("_forced_level") or "LOW", computed_extra)
            else:
                # Structural path errors remain hard rejects at authorize time.
                features.setdefault("_hard_errors", []).append(exc)

    computed, reasons = compute_risk_from_features(features, policy=policy, proposal=proposal)
    if features.get("_forced_level"):
        computed = stricter(computed, str(features["_forced_level"]))
        for code in features.get("_forced_reasons") or []:
            if code not in reasons:
                reasons.append(code)
    effective = stricter(declared, computed)
    return RiskAssessment(
        declared_risk=declared,
        computed_risk=computed,
        effective_risk=effective,
        reason_codes=reasons,
        file_count=int(features["file_count"]),
        lines_added=int(features["lines_added"]),
        lines_removed=int(features["lines_removed"]),
        patch_bytes=int(features["patch_bytes"]),
        paths=list(features["paths"]),
    )


def classify_post_application(
    *,
    proposal: dict[str, Any],
    policy: dict[str, Any],
    changed_paths: list[str],
    lines_added: int,
    lines_removed: int,
    patch_bytes: int,
    pre: RiskAssessment,
) -> RiskAssessment:
    features = {
        "paths": [normalize_rel_path(p) for p in changed_paths],
        "operations": [],
        "file_count": len(changed_paths),
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "patch_bytes": patch_bytes,
        "content_blob": "",
        "validation_profile": str(proposal.get("validation_profile") or ""),
    }
    computed, reasons = compute_risk_from_features(features, policy=policy, proposal=proposal)

    proposed = sorted(normalize_rel_path(p) for p in pre.paths)
    actual = sorted(normalize_rel_path(p) for p in changed_paths)
    if proposed != actual:
        reasons.append("RISK_PATH_SET_CHANGED")
        computed = stricter(computed, "MEDIUM")

    # Post can only maintain or increase relative to pre effective.
    effective = stricter(pre.effective_risk, computed)
    return RiskAssessment(
        declared_risk=pre.declared_risk,
        computed_risk=computed,
        effective_risk=effective,
        reason_codes=reasons,
        file_count=len(changed_paths),
        lines_added=lines_added,
        lines_removed=lines_removed,
        patch_bytes=patch_bytes,
        paths=list(actual),
    )


def authorize_execution(
    proposal: dict[str, Any],
    policy: dict[str, Any],
    *,
    policy_sha256: str | None = None,
    caller_authorization: Any = None,
) -> AuthorizationResult:
    """Sole worker authorization gate. Never trusts caller-supplied authorization."""
    if caller_authorization is not None:
        raise WorkerError(
            ERROR_CODES["RISK_AUTH_REPLAY"],
            "caller-supplied authorization rejected; worker must recompute",
            state="POLICY_REJECTED",
        )

    # Reject hard structural path errors discovered during feature extraction.
    features = extract_proposal_features(proposal)
    for path in features["paths"]:
        try:
            assert_path_allowed(path, policy, proposal)
        except WorkerError as exc:
            if exc.code in {
                ERROR_CODES["SI2-PATH-TRAVERSAL"],
                ERROR_CODES["SI2-PATH-ABSOLUTE"],
                ERROR_CODES["SI2-PATH-QUOTED-UNSAFE"],
                ERROR_CODES["SI2-PATH-SPOOFED-PROTECTED-NAME"],
                ERROR_CODES["SI2-PATH-SYMLINK"],
            }:
                raise

    pre = classify_pre_application(proposal, policy)
    if pre.effective_risk == "PROHIBITED":
        return AuthorizationResult(
            decision=DECISION_POLICY_REJECTED,
            declared_risk=pre.declared_risk,
            computed_risk_pre=pre.computed_risk,
            effective_risk_pre=pre.effective_risk,
            risk_reason_codes_pre=pre.reason_codes,
            risk_classifier_version=RISK_CLASSIFIER_VERSION,
            policy_sha256=policy_sha256,
            error_code=ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
            message="effective risk PROHIBITED",
        )
    if pre.effective_risk != "LOW":
        return AuthorizationResult(
            decision=DECISION_REQUIRED,
            declared_risk=pre.declared_risk,
            computed_risk_pre=pre.computed_risk,
            effective_risk_pre=pre.effective_risk,
            risk_reason_codes_pre=pre.reason_codes,
            risk_classifier_version=RISK_CLASSIFIER_VERSION,
            policy_sha256=policy_sha256,
            error_code=ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
            message=f"effective risk {pre.effective_risk} not auto-authorized",
        )
    return AuthorizationResult(
        decision=DECISION_AUTHORIZED,
        declared_risk=pre.declared_risk,
        computed_risk_pre=pre.computed_risk,
        effective_risk_pre=pre.effective_risk,
        risk_reason_codes_pre=pre.reason_codes,
        risk_classifier_version=RISK_CLASSIFIER_VERSION,
        policy_sha256=policy_sha256,
    )


def enforce_authorization(result: AuthorizationResult) -> AuthorizationResult:
    """Raise WorkerError unless AUTHORIZED."""
    if result.decision == DECISION_AUTHORIZED:
        return result
    state = "POLICY_REJECTED" if result.decision == DECISION_POLICY_REJECTED else "DECISION_REQUIRED"
    raise WorkerError(
        result.error_code or ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
        result.message or f"authorization decision: {result.decision}",
        state=state,
    )


def enforce_post_risk(
    *,
    pre: RiskAssessment,
    post: RiskAssessment,
) -> None:
    if post.effective_risk != "LOW" or post.effective_risk != pre.effective_risk:
        raise WorkerError(
            ERROR_CODES["RISK_ESCALATED_POST_EXECUTION"],
            (
                f"post risk {post.effective_risk} (computed={post.computed_risk}) "
                f"vs pre {pre.effective_risk}; reasons={post.reason_codes}"
            ),
            state="DECISION_REQUIRED",
        )


def assert_finalize_risk_bindings(
    bundle: dict[str, Any],
    *,
    proposal: dict[str, Any],
    current_policy: dict[str, Any],
    current_policy_sha256: str,
) -> None:
    required = (
        "declared_risk",
        "computed_risk_pre",
        "effective_risk_pre",
        "computed_risk_post",
        "effective_risk_post",
        "risk_reason_codes_pre",
        "risk_reason_codes_post",
        "policy_sha256",
        "risk_classifier_version",
    )
    for key in required:
        if key not in bundle or bundle.get(key) in (None, ""):
            raise WorkerError(
                ERROR_CODES["RISK_EVIDENCE_MISSING"],
                f"missing risk binding field: {key}",
                state="DECISION_REQUIRED",
            )
    pinned_policy_sha256 = str(bundle.get("policy_sha256") or "")
    if not pinned_policy_sha256:
        raise WorkerError(
            ERROR_CODES["RISK_POLICY_BINDING"],
            "pinned policy_sha256 missing from execution bundle",
            state="DECISION_REQUIRED",
        )
    if bundle.get("effective_risk_pre") != "LOW" or bundle.get("effective_risk_post") != "LOW":
        raise WorkerError(
            ERROR_CODES["RISK_ESCALATED_POST_EXECUTION"],
            "finalizer refuses elevated risk regardless of review",
            state="DECISION_REQUIRED",
        )
    if bundle.get("effective_risk_pre") != bundle.get("effective_risk_post"):
        raise WorkerError(
            ERROR_CODES["RISK_ESCALATED_POST_EXECUTION"],
            "pre/post effective risk mismatch at finalization",
            state="DECISION_REQUIRED",
        )

    # Always evaluate current policy. A later policy may tighten or halt; never loosen.
    current_auth = authorize_execution(
        proposal, current_policy, policy_sha256=current_policy_sha256
    )
    if current_policy_sha256 == pinned_policy_sha256:
        if current_auth.decision != DECISION_AUTHORIZED or current_auth.effective_risk_pre != "LOW":
            raise WorkerError(
                ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
                "pinned policy no longer authorizes proposal",
                state="DECISION_REQUIRED",
            )
        return

    # Policy content changed since pin — current may only tighten/halt.
    if risk_rank(current_auth.effective_risk_pre) > risk_rank(str(bundle["effective_risk_pre"])):
        raise WorkerError(
            ERROR_CODES["RISK_POLICY_TIGHTENED"],
            "current policy is stricter than pinned authorization",
            state="DECISION_REQUIRED",
        )
    if current_auth.decision != DECISION_AUTHORIZED:
        raise WorkerError(
            ERROR_CODES["RISK_POLICY_TIGHTENED"],
            "current policy rejects previously authorized proposal",
            state="DECISION_REQUIRED",
        )


def risk_fields_for_bundle(
    *,
    auth: AuthorizationResult,
    post: RiskAssessment,
    policy_sha256: str,
) -> dict[str, Any]:
    return {
        "declared_risk": auth.declared_risk,
        "computed_risk_pre": auth.computed_risk_pre,
        "effective_risk_pre": auth.effective_risk_pre,
        "computed_risk_post": post.computed_risk,
        "effective_risk_post": post.effective_risk,
        "risk_reason_codes_pre": list(auth.risk_reason_codes_pre),
        "risk_reason_codes_post": list(post.reason_codes),
        "policy_sha256": policy_sha256,
        "risk_classifier_version": RISK_CLASSIFIER_VERSION,
    }
