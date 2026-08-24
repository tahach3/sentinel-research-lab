"""Unified-diff patch safety checks for the autonomous lane."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from tools.self_improvement.models import ERROR_CODES, WorkerError
from tools.self_improvement.policy import (
    assert_path_allowed,
    has_traversal,
    is_absolute_path,
    limits,
    normalize_rel_path,
)

BINARY_MARKERS = ("GIT binary patch", "Binary files ", "\0")
DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)
MINUS_RE = re.compile(r"^--- (?:a/)?(.+)$", re.MULTILINE)
PLUS_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$", re.MULTILINE)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return sha256_bytes(path.read_bytes())


def _reject(code: str, message: str) -> None:
    raise WorkerError(code, message, state="PATCH_REJECTED")


def extract_paths_from_diff(unified_diff: str) -> list[str]:
    paths: list[str] = []
    for match in DIFF_GIT_RE.finditer(unified_diff):
        paths.extend([match.group(1), match.group(2)])
    for match in MINUS_RE.finditer(unified_diff):
        value = match.group(1).strip()
        if value not in ("/dev/null",):
            paths.append(value)
    for match in PLUS_RE.finditer(unified_diff):
        value = match.group(1).strip()
        if value not in ("/dev/null",):
            paths.append(value)
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        norm = normalize_rel_path(p)
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def validate_patch_object(
    patch: dict[str, Any],
    *,
    policy: dict[str, Any],
    proposal: dict[str, Any],
    repo_root: Path,
) -> None:
    path = normalize_rel_path(str(patch.get("path", "")))
    operation = patch.get("operation")
    diff = patch.get("unified_diff") or ""
    pre = patch.get("expected_preimage_sha256") or ""
    post = patch.get("expected_postimage_sha256") or ""

    if operation == "DELETE":
        _reject(ERROR_CODES["DELETION_PROHIBITED"], f"deletion not allowed: {path}")
    if not isinstance(diff, str) or not diff.strip():
        _reject(ERROR_CODES["PATCH_REJECTED"], f"empty diff: {path}")
    if any(marker in diff for marker in BINARY_MARKERS if marker != "\0") or "\0" in diff:
        _reject(ERROR_CODES["BINARY_PATCH"], f"binary patch: {path}")
    if "submodule" in diff.lower() and "160000" in diff:
        _reject(ERROR_CODES["SUBMODULE_CHANGE"], f"submodule change: {path}")

    assert_path_allowed(path, policy, proposal)
    for diff_path in extract_paths_from_diff(diff):
        if diff_path in ("/dev/null", "dev/null"):
            continue
        if is_absolute_path(diff_path) or has_traversal(diff_path):
            code = ERROR_CODES["ABSOLUTE_PATH"] if is_absolute_path(diff_path) else ERROR_CODES["PATH_TRAVERSAL"]
            _reject(code, f"unsafe diff path: {diff_path}")
        assert_path_allowed(diff_path, policy, proposal)
        if normalize_rel_path(diff_path) != path and operation != "MODIFY":
            # Allow standard a/b same-path diffs; reject multi-file surprises.
            if normalize_rel_path(diff_path) != path:
                if path not in normalize_rel_path(diff_path) and normalize_rel_path(diff_path) not in path:
                    _reject(ERROR_CODES["PATCH_REJECTED"], f"diff path mismatch: {diff_path} vs {path}")

    lim = limits(policy)
    if len(diff.encode("utf-8")) > int(lim["maximum_patch_size_bytes"]):
        _reject(ERROR_CODES["EXCESSIVE_PATCH_SIZE"], f"patch too large: {path}")

    target = (repo_root / path).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError:
        _reject(ERROR_CODES["PATH_TRAVERSAL"], f"escapes root: {path}")

    if target.exists() and target.is_symlink():
        _reject(ERROR_CODES["SYMLINK_PROHIBITED"], f"symlink target: {path}")

    actual_pre = file_sha256(target) if target.exists() else ""
    if operation == "CREATE":
        if target.exists():
            _reject(ERROR_CODES["PREIMAGE_MISMATCH"], f"create target exists: {path}")
        if pre not in ("", actual_pre):
            _reject(ERROR_CODES["PREIMAGE_MISMATCH"], f"create preimage must be empty: {path}")
    elif operation == "MODIFY":
        if not target.exists():
            _reject(ERROR_CODES["PREIMAGE_MISMATCH"], f"modify target missing: {path}")
        if actual_pre != pre:
            _reject(ERROR_CODES["PREIMAGE_MISMATCH"], f"preimage mismatch: {path}")
    else:
        _reject(ERROR_CODES["PATCH_REJECTED"], f"unsupported operation: {operation}")

    if not re.fullmatch(r"[a-f0-9]{64}", post or ""):
        _reject(ERROR_CODES["POSTIMAGE_MISMATCH"], f"invalid postimage: {path}")


def git_apply_check(repo_root: Path, unified_diff: str) -> None:
    proc = subprocess.run(
        ["git", "apply", "--check", "--whitespace=nowarn", "-"],
        cwd=str(repo_root),
        input=unified_diff.encode("utf-8"),
        capture_output=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:500]
        _reject(ERROR_CODES["GIT_APPLY_CHECK_FAILED"], detail or "git apply --check failed")


def git_apply(repo_root: Path, unified_diff: str) -> None:
    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        cwd=str(repo_root),
        input=unified_diff.encode("utf-8"),
        capture_output=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:500]
        _reject(ERROR_CODES["PATCH_REJECTED"], detail or "git apply failed")


def verify_postimage(repo_root: Path, patch: dict[str, Any]) -> None:
    path = normalize_rel_path(str(patch["path"]))
    target = (repo_root / path).resolve()
    if not target.is_file():
        _reject(ERROR_CODES["POSTIMAGE_MISMATCH"], f"missing after apply: {path}")
    if target.is_symlink():
        _reject(ERROR_CODES["SYMLINK_PROHIBITED"], f"symlink after apply: {path}")
    actual = file_sha256(target)
    expected = patch.get("expected_postimage_sha256") or ""
    if actual != expected:
        _reject(ERROR_CODES["POSTIMAGE_MISMATCH"], f"postimage mismatch: {path}")


def _stage_all(repo_root: Path) -> None:
    proc = subprocess.run(
        ["git", "add", "-A"],
        cwd=str(repo_root),
        capture_output=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        _reject(ERROR_CODES["PATCH_REJECTED"], "unable to stage changes for diff audit")


def summarize_diff(repo_root: Path, baseline_sha: str) -> dict[str, int]:
    _stage_all(repo_root)
    proc = subprocess.run(
        ["git", "diff", "--cached", "--numstat", baseline_sha],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        _reject(ERROR_CODES["PATCH_REJECTED"], "unable to summarize diff")
    files = 0
    added = 0
    removed = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, r, _name = parts[0], parts[1], parts[2]
        if a == "-" or r == "-":
            _reject(ERROR_CODES["BINARY_PATCH"], f"binary change detected: {_name}")
        files += 1
        added += int(a)
        removed += int(r)
    patch = subprocess.run(
        ["git", "diff", "--cached", baseline_sha],
        cwd=str(repo_root),
        capture_output=True,
        timeout=30,
        check=False,
        shell=False,
    )
    return {
        "files_changed": files,
        "lines_added": added,
        "lines_removed": removed,
        "patch_bytes": len(patch.stdout or b""),
    }


def enforce_diff_limits(summary: dict[str, int], policy: dict[str, Any]) -> None:
    lim = limits(policy)
    if summary["files_changed"] > int(lim["maximum_changed_files"]):
        _reject(ERROR_CODES["TOO_MANY_FILES"], "too many changed files")
    total_lines = summary["lines_added"] + summary["lines_removed"]
    if total_lines > int(lim["maximum_total_added_and_removed_lines"]):
        _reject(ERROR_CODES["EXCESSIVE_DIFF"], "excessive diff size")
    if summary["patch_bytes"] > int(lim["maximum_patch_size_bytes"]):
        _reject(ERROR_CODES["EXCESSIVE_PATCH_SIZE"], "patch bytes exceed limit")


def changed_paths_since(repo_root: Path, baseline_sha: str) -> list[str]:
    _stage_all(repo_root)
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", baseline_sha],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        _reject(ERROR_CODES["PATCH_REJECTED"], "unable to list changed paths")
    return [normalize_rel_path(line) for line in proc.stdout.splitlines() if line.strip()]
