"""Patch validation against path policy, pre/post images, and diff limits."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.canonical import content_sha256, sha256_hex
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.patch_parser import (
    parse_unified_diff,
    paths_from_parsed,
    reject_forbidden_patch_ops,
)
from tools.self_improvement_v2.path_policy import (
    assert_path_allowed,
    limits,
    normalize_rel_path,
)


def file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return sha256_hex(path.read_bytes())


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

    if operation not in ("CREATE", "MODIFY"):
        raise WorkerError(
            ERROR_CODES["PATCH_REJECTED"],
            f"unsupported operation: {operation}",
            state="PATCH_REJECTED",
        )

    parsed = parse_unified_diff(diff)
    reject_forbidden_patch_ops(parsed)

    assert_path_allowed(path, policy, proposal, repo_root=repo_root)
    for diff_path in paths_from_parsed(parsed):
        assert_path_allowed(diff_path, policy, proposal, repo_root=repo_root)
        if normalize_rel_path(diff_path) != path:
            raise WorkerError(
                ERROR_CODES["PATCH_REJECTED"],
                f"diff path mismatch: {diff_path} vs {path}",
                state="PATCH_REJECTED",
            )

    lim = limits(policy)
    if len(diff.encode("utf-8")) > int(lim["maximum_patch_size_bytes"]):
        raise WorkerError(
            ERROR_CODES["EXCESSIVE_PATCH_SIZE"],
            f"patch too large: {path}",
            state="PATCH_REJECTED",
        )

    target = (repo_root / path).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise WorkerError(
            ERROR_CODES["SI2-PATH-TRAVERSAL"],
            f"escapes root: {path}",
            state="PATCH_REJECTED",
        ) from exc

    if target.exists() and target.is_symlink():
        raise WorkerError(
            ERROR_CODES["SI2-PATH-SYMLINK"],
            f"symlink target: {path}",
            state="PATCH_REJECTED",
        )

    actual_pre = file_sha256(target) if target.exists() else ""
    if operation == "CREATE":
        if target.exists():
            raise WorkerError(
                ERROR_CODES["PREIMAGE_MISMATCH"],
                f"create target exists: {path}",
                state="PATCH_REJECTED",
            )
        if pre not in ("", actual_pre):
            raise WorkerError(
                ERROR_CODES["PREIMAGE_MISMATCH"],
                f"create preimage must be empty: {path}",
                state="PATCH_REJECTED",
            )
    elif operation == "MODIFY":
        if not target.exists():
            raise WorkerError(
                ERROR_CODES["PREIMAGE_MISMATCH"],
                f"modify target missing: {path}",
                state="PATCH_REJECTED",
            )
        if actual_pre != pre:
            raise WorkerError(
                ERROR_CODES["PREIMAGE_MISMATCH"],
                f"preimage mismatch: {path}",
                state="PATCH_REJECTED",
            )

    if not post or len(post) != 64:
        raise WorkerError(
            ERROR_CODES["POSTIMAGE_MISMATCH"],
            f"invalid postimage: {path}",
            state="PATCH_REJECTED",
        )


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
        raise WorkerError(
            ERROR_CODES["GIT_APPLY_CHECK_FAILED"],
            detail or "git apply --check failed",
            state="PATCH_REJECTED",
        )


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
        raise WorkerError(
            ERROR_CODES["PATCH_REJECTED"],
            detail or "git apply failed",
            state="PATCH_REJECTED",
        )


def verify_postimage(repo_root: Path, patch: dict[str, Any]) -> None:
    path = normalize_rel_path(str(patch["path"]))
    target = (repo_root / path).resolve()
    if not target.is_file():
        raise WorkerError(
            ERROR_CODES["POSTIMAGE_MISMATCH"],
            f"missing after apply: {path}",
            state="PATCH_REJECTED",
        )
    if target.is_symlink():
        raise WorkerError(
            ERROR_CODES["SI2-PATH-SYMLINK"],
            f"symlink after apply: {path}",
            state="PATCH_REJECTED",
        )
    actual = file_sha256(target)
    expected = patch.get("expected_postimage_sha256") or ""
    if actual != expected:
        raise WorkerError(
            ERROR_CODES["POSTIMAGE_MISMATCH"],
            f"postimage mismatch: {path}",
            state="PATCH_REJECTED",
        )


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
        raise WorkerError(ERROR_CODES["PATCH_REJECTED"], "unable to stage changes", state="PATCH_REJECTED")


def staged_tree_sha(repo_root: Path) -> str:
    _stage_all(repo_root)
    proc = subprocess.run(
        ["git", "write-tree"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        raise WorkerError(ERROR_CODES["PATCH_REJECTED"], "write-tree failed", state="PATCH_REJECTED")
    return proc.stdout.strip()


def actual_diff_bytes(repo_root: Path, baseline_sha: str) -> bytes:
    _stage_all(repo_root)
    proc = subprocess.run(
        ["git", "diff", "--binary", "--cached", baseline_sha],
        cwd=str(repo_root),
        capture_output=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        raise WorkerError(ERROR_CODES["PATCH_REJECTED"], "unable to compute diff", state="PATCH_REJECTED")
    return proc.stdout or b""


def actual_diff_sha256(repo_root: Path, baseline_sha: str) -> str:
    return sha256_hex(actual_diff_bytes(repo_root, baseline_sha))


def changed_paths_since(repo_root: Path, baseline_sha: str) -> list[str]:
    _stage_all(repo_root)
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z", baseline_sha],
        cwd=str(repo_root),
        capture_output=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        # fallback without -z
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
            raise WorkerError(ERROR_CODES["PATCH_REJECTED"], "unable to list changed paths", state="PATCH_REJECTED")
        return [normalize_rel_path(line) for line in proc.stdout.splitlines() if line.strip()]
    raw = proc.stdout or b""
    parts = [p.decode("utf-8", errors="replace") for p in raw.split(b"\0") if p]
    return [normalize_rel_path(p) for p in parts]


def changed_paths_sha256(paths: list[str]) -> str:
    return content_sha256(sorted(paths))


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
        raise WorkerError(ERROR_CODES["PATCH_REJECTED"], "unable to summarize diff", state="PATCH_REJECTED")
    files = 0
    added = 0
    removed = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, r, name = parts[0], parts[1], parts[2]
        if a == "-" or r == "-":
            raise WorkerError(ERROR_CODES["BINARY_PATCH"], f"binary change: {name}", state="PATCH_REJECTED")
        files += 1
        added += int(a)
        removed += int(r)
    patch = actual_diff_bytes(repo_root, baseline_sha)
    return {
        "files_changed": files,
        "lines_added": added,
        "lines_removed": removed,
        "patch_bytes": len(patch),
    }


def enforce_diff_limits(summary: dict[str, int], policy: dict[str, Any], proposal: dict[str, Any] | None = None) -> None:
    lim = limits(policy)
    max_files = int(lim["maximum_changed_files"])
    max_lines = int(lim["maximum_total_added_and_removed_lines"])
    if proposal is not None:
        if proposal.get("maximum_changed_files") is not None:
            max_files = min(max_files, int(proposal["maximum_changed_files"]))
        if proposal.get("maximum_total_added_and_removed_lines") is not None:
            max_lines = min(max_lines, int(proposal["maximum_total_added_and_removed_lines"]))
    if summary["files_changed"] > max_files:
        raise WorkerError(ERROR_CODES["TOO_MANY_FILES"], "too many changed files", state="PATCH_REJECTED")
    total_lines = summary["lines_added"] + summary["lines_removed"]
    if total_lines > max_lines:
        raise WorkerError(ERROR_CODES["EXCESSIVE_DIFF"], "excessive diff size", state="PATCH_REJECTED")
    if summary["patch_bytes"] > int(lim["maximum_patch_size_bytes"]):
        raise WorkerError(ERROR_CODES["EXCESSIVE_PATCH_SIZE"], "patch bytes exceed limit", state="PATCH_REJECTED")
