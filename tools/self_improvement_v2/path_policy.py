"""Segment-aware path policy — DENY beats ALLOW at every nesting depth."""

from __future__ import annotations

import json
import os
import re
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.schema_loader import SPEC_REL, worker_package_root

PROTECTED_SEGMENTS = frozenset(
    {
        ".git",
        "credentials",
        "credential",
        "secrets",
        "secret",
        "private_keys",
    }
)

PROTECTED_BASENAME_EXACT = frozenset({".env", "id_rsa", "id_ed25519"})
PROTECTED_BASENAME_GLOBS = (".env.*", "*.pem", "*.key", "*.p12", "*.pfx")

FORBIDDEN_ROOT_PATTERNS = [
    "database/migrations/**",
    "database/init/**",
    "workflows/active/**",
    ".github/workflows/**",
    "specs/round5a/**",
    "specs/round5a_kernel/**",
    "tools/round5a_kernel/**",
    "docs/ROUND_5A_REVISION_8_*",
    "docs/ROUND_5A_EXECUTABLE_KERNEL_RESET.md",
]


@lru_cache(maxsize=4)
def _load_policy_cached(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_policy(root: Path | None = None) -> dict[str, Any]:
    base = root if root is not None else worker_package_root()
    path = (base / SPEC_REL / "policy.json").resolve()
    if not path.is_file():
        path = (worker_package_root() / SPEC_REL / "policy.json").resolve()
    policy = _load_policy_cached(str(path))
    lane = policy.get("autonomous_lane") or {}
    if not lane.get("allowed_paths"):
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "policy missing allowed_paths")
    return policy


def policy_sha256(root: Path | None = None) -> str:
    return content_sha256(load_policy(root))


def normalize_rel_path(path: str) -> str:
    if path is None:
        raise WorkerError(ERROR_CODES["SI2-PATH-TRAVERSAL"], "null path", state="PATCH_REJECTED")
    if "\x00" in path:
        raise WorkerError(ERROR_CODES["SI2-PATH-TRAVERSAL"], "NUL in path", state="PATCH_REJECTED")
    cleaned = path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def is_absolute_path(path: str) -> bool:
    p = path.replace("\\", "/")
    if p.startswith("/") or p.startswith("~"):
        return True
    if p.startswith("//") or p.startswith("\\\\"):
        return True
    if re.match(r"^[A-Za-z]:(/|\\)", path) or re.match(r"^[A-Za-z]:/", p):
        return True
    if p.startswith("unc/") or p.lower().startswith("\\\\"):
        return True
    return False


def has_traversal_or_empty(path: str) -> bool:
    parts = normalize_rel_path(path).split("/")
    if any(part == "" for part in parts):
        return True
    if any(part in (".", "..") for part in parts):
        return True
    return False


def _basename_protected(name: str) -> bool:
    lower = name.lower()
    if lower in {x.lower() for x in PROTECTED_BASENAME_EXACT}:
        return True
    if lower == ".env" or lower.startswith(".env."):
        return True
    for pattern in PROTECTED_BASENAME_GLOBS:
        if fnmatch(name, pattern) or fnmatch(lower, pattern.lower()):
            return True
    return False


def _segment_protected(segment: str) -> bool:
    lower = segment.lower()
    return lower in {s.lower() for s in PROTECTED_SEGMENTS}


def match_patterns(path: str, patterns: list[str]) -> bool:
    norm = normalize_rel_path(path)
    for pattern in patterns:
        pat = normalize_rel_path(pattern)
        if fnmatch(norm, pat) or fnmatch(norm, pat.rstrip("/")):
            return True
        if fnmatch(norm.lower(), pat.lower()):
            return True
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if norm == prefix or norm.startswith(prefix + "/"):
                return True
            if norm.lower() == prefix.lower() or norm.lower().startswith(prefix.lower() + "/"):
                return True
        if pat.endswith("/*"):
            prefix = pat[:-2]
            if norm.startswith(prefix + "/") or norm.lower().startswith(prefix.lower() + "/"):
                return True
    return False


_BIDI_OR_ZEROWIDTH = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]"
)


def _reject_spoofed_protected_name(path: str) -> None:
    """Reject percent-encoded / bidi / zero-width spoofing of protected names.

    Does not URL-decode and then execute; ambiguous representations are rejected.
    """
    if _BIDI_OR_ZEROWIDTH.search(path):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-SPOOFED-PROTECTED-NAME"],
            f"bidi/zero-width path spoofing: {path!r}",
            state="PATCH_REJECTED",
        )
    lowered = path.lower().replace("\\", "/")
    # Percent-encoded .env / .git patterns (including docs/%2e%65%6e%76 and docs/%2Eenv).
    if re.search(r"%2e%65%6e%76", lowered) or re.search(r"%2eenv", lowered):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-SPOOFED-PROTECTED-NAME"],
            f"percent-encoded protected name: {path!r}",
            state="PATCH_REJECTED",
        )
    if re.search(r"%2e%67%69%74", lowered) or re.search(r"%2egit", lowered):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-SPOOFED-PROTECTED-NAME"],
            f"percent-encoded protected name: {path!r}",
            state="PATCH_REJECTED",
        )
    # Other Unicode path-control characters.
    if any(ord(ch) < 32 and ch not in "\t" for ch in path):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-SPOOFED-PROTECTED-NAME"],
            f"control character in path: {path!r}",
            state="PATCH_REJECTED",
        )


def assert_path_allowed(
    path: str,
    policy: dict[str, Any],
    proposal: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> str:
    raw = path
    if '"' in raw or "'" in raw:
        raise WorkerError(
            ERROR_CODES["SI2-PATH-QUOTED-UNSAFE"],
            f"quoted-path ambiguity: {path}",
            state="PATCH_REJECTED",
        )
    _reject_spoofed_protected_name(raw)
    if is_absolute_path(raw) or is_absolute_path(normalize_rel_path(raw) if "\x00" not in raw else raw):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-ABSOLUTE"],
            f"absolute path: {path}",
            state="PATCH_REJECTED",
        )
    if "\\" in path and "/" in normalize_rel_path(path):
        # Windows separators are normalized; reject residual backslash after normalize intent.
        pass
    try:
        norm = normalize_rel_path(raw)
    except WorkerError:
        raise
    if "\\" in norm:
        raise WorkerError(
            ERROR_CODES["SI2-PATH-TRAVERSAL"],
            f"alternate separator remains: {path}",
            state="PATCH_REJECTED",
        )
    if has_traversal_or_empty(norm):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-TRAVERSAL"],
            f"traversal or empty segment: {path}",
            state="PATCH_REJECTED",
        )

    parts = norm.split("/")
    for part in parts[:-1]:
        if _segment_protected(part):
            raise WorkerError(
                ERROR_CODES["SI2-PATH-PROTECTED-SEGMENT"],
                f"protected segment: {path}",
                state="POLICY_REJECTED",
            )
    basename = parts[-1]
    if _segment_protected(basename) and basename.lower() in {".git", "credentials", "credential", "secrets", "secret", "private_keys"}:
        raise WorkerError(
            ERROR_CODES["SI2-PATH-PROTECTED-SEGMENT"],
            f"protected segment basename: {path}",
            state="POLICY_REJECTED",
        )
    if _basename_protected(basename):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-PROTECTED-BASENAME"],
            f"protected basename: {path}",
            state="POLICY_REJECTED",
        )

    # DENY beats ALLOW — forbidden roots and policy forbidden before allow.
    if match_patterns(norm, FORBIDDEN_ROOT_PATTERNS):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-FORBIDDEN-ROOT"],
            f"forbidden root: {path}",
            state="POLICY_REJECTED",
        )

    lane = policy["autonomous_lane"]
    forbidden = list(lane.get("forbidden_paths") or [])
    if proposal is not None:
        forbidden.extend(proposal.get("forbidden_paths") or [])
    if match_patterns(norm, forbidden):
        # Prefer segment/basename codes when applicable; otherwise forbidden root.
        raise WorkerError(
            ERROR_CODES["SI2-PATH-FORBIDDEN-ROOT"],
            f"forbidden path: {path}",
            state="POLICY_REJECTED",
        )

    if repo_root is not None:
        target = (repo_root / norm)
        # Case-bypass: on case-insensitive hosts, resolve and compare.
        try:
            if target.exists():
                if target.is_symlink():
                    raise WorkerError(
                        ERROR_CODES["SI2-PATH-SYMLINK"],
                        f"symlink: {path}",
                        state="PATCH_REJECTED",
                    )
                resolved = target.resolve()
                try:
                    resolved.relative_to(repo_root.resolve())
                except ValueError as exc:
                    raise WorkerError(
                        ERROR_CODES["SI2-PATH-TRAVERSAL"],
                        f"escapes root: {path}",
                        state="PATCH_REJECTED",
                    ) from exc
                # Reconstruct posix relative and re-check protection on real casing.
                rel = resolved.relative_to(repo_root.resolve()).as_posix()
                if os.name == "nt" or (hasattr(os, "path") and getattr(os.path, "normcase", str)("A") == "a"):
                    for part in rel.split("/"):
                        if _segment_protected(part) or _basename_protected(part):
                            raise WorkerError(
                                ERROR_CODES["SI2-PATH-PROTECTED-SEGMENT"]
                                if _segment_protected(part)
                                else ERROR_CODES["SI2-PATH-PROTECTED-BASENAME"],
                                f"case-bypass protected path: {path}",
                                state="POLICY_REJECTED",
                            )
        except WorkerError:
            raise
        except OSError:
            pass

    allowed = list(lane.get("allowed_paths") or [])
    if proposal is not None:
        proposal_allowed = proposal.get("allowed_paths") or allowed
        if not match_patterns(norm, proposal_allowed):
            raise WorkerError(
                ERROR_CODES["SI2-PATH-FORBIDDEN-ROOT"],
                f"outside proposal allowed_paths: {path}",
                state="POLICY_REJECTED",
            )
    if not match_patterns(norm, allowed):
        raise WorkerError(
            ERROR_CODES["SI2-PATH-FORBIDDEN-ROOT"],
            f"outside autonomous allowed_paths: {path}",
            state="POLICY_REJECTED",
        )
    return norm


def classify_and_authorize(proposal: dict[str, Any], policy: dict[str, Any]) -> str:
    """Legacy name — delegates to worker risk authority (content-derived).

    Returns AUTO_AUTHORIZED only when authorize_execution returns AUTHORIZED.
    """
    from tools.self_improvement_v2.risk_authority import (
        DECISION_AUTHORIZED,
        authorize_execution,
        enforce_authorization,
    )

    result = authorize_execution(proposal, policy)
    enforce_authorization(result)
    if result.decision != DECISION_AUTHORIZED:
        raise WorkerError(
            ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
            result.message,
            state="DECISION_REQUIRED",
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
