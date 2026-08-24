"""Git isolation helpers: temp worktrees, local branches, no push/merge."""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tools.self_improvement.models import ERROR_CODES, WorkerError

FORBIDDEN_GIT_OPS = frozenset({"push", "merge", "rebase", "config", "clean"})


def run_git(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int = 60,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if not args:
        raise WorkerError(ERROR_CODES["COMMAND_INJECTION"], "empty git argv", state="FAILED_FROZEN")
    op = args[0]
    if op in FORBIDDEN_GIT_OPS:
        code = ERROR_CODES["PUSH_ATTEMPT"] if op == "push" else (
            ERROR_CODES["MERGE_ATTEMPT"] if op == "merge" else ERROR_CODES["POLICY_REJECTED"]
        )
        raise WorkerError(code, f"forbidden git operation: {op}", state="POLICY_REJECTED")
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        input=input_bytes,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:500]
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], detail or f"git {' '.join(args)} failed")
    return proc


def resolve_repo_root(root: Path) -> Path:
    root = root.resolve()
    proc = run_git(["rev-parse", "--show-toplevel"], cwd=root, check=True)
    top = Path(proc.stdout.decode("utf-8").strip()).resolve()
    if top != root:
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "root is not git toplevel",
            state="POLICY_REJECTED",
        )
    return top


def assert_clean_tree(root: Path) -> None:
    proc = run_git(["status", "--porcelain=v1"], cwd=root, check=True)
    if proc.stdout.strip():
        raise WorkerError(
            ERROR_CODES["DIRTY_SOURCE_TREE"],
            "source worktree is dirty",
            state="BASELINE_MISMATCH",
        )


def assert_baseline(root: Path, baseline_sha: str) -> str:
    proc = run_git(["rev-parse", "HEAD"], cwd=root, check=True)
    head = proc.stdout.decode("utf-8").strip()
    if head != baseline_sha:
        raise WorkerError(
            ERROR_CODES["BASELINE_MISMATCH"],
            f"HEAD {head} != baseline {baseline_sha}",
            state="BASELINE_MISMATCH",
        )
    verify = run_git(["rev-parse", "--verify", baseline_sha], cwd=root, check=False)
    if verify.returncode != 0:
        raise WorkerError(
            ERROR_CODES["BASELINE_MISMATCH"],
            f"baseline missing: {baseline_sha}",
            state="BASELINE_MISMATCH",
        )
    return head


def short_run_id() -> str:
    return secrets.token_hex(4)


def branch_name_for(candidate_id: str, run_id: str) -> str:
    safe_candidate = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in candidate_id)
    return f"self-improvement/{safe_candidate}/{run_id}"


class TemporaryWorktree:
    def __init__(self, source_root: Path, baseline_sha: str, candidate_id: str) -> None:
        self.source_root = source_root.resolve()
        self.baseline_sha = baseline_sha
        self.candidate_id = candidate_id
        self.run_id = short_run_id()
        self.branch_name = branch_name_for(candidate_id, self.run_id)
        self.path: Path | None = None
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> "TemporaryWorktree":
        self._tmpdir = tempfile.TemporaryDirectory(prefix="srl-si-wt-")
        self.path = Path(self._tmpdir.name) / "worktree"
        run_git(
            ["worktree", "add", "-b", self.branch_name, str(self.path), self.baseline_sha],
            cwd=self.source_root,
            check=True,
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self.path is not None:
            run_git(
                ["worktree", "remove", "--force", str(self.path)],
                cwd=self.source_root,
                check=False,
            )
            if self.path.exists():
                shutil.rmtree(self.path, ignore_errors=True)
        run_git(["worktree", "prune"], cwd=self.source_root, check=False)
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None
        self.path = None


def create_local_commit(worktree: Path, objective: str) -> str:
    run_git(["add", "-A"], cwd=worktree, check=True)
    msg = f"Self-improvement: {objective}"
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "SRL Self-Improvement")
    env.setdefault("GIT_AUTHOR_EMAIL", "self-improvement@local")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    proc = subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=str(worktree),
        capture_output=True,
        timeout=60,
        check=False,
        shell=False,
        env=env,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:500]
        raise WorkerError(ERROR_CODES["FAILED_FROZEN"], detail or "commit failed")
    sha = run_git(["rev-parse", "HEAD"], cwd=worktree, check=True)
    return sha.stdout.decode("utf-8").strip()


def source_tree_fingerprint(root: Path) -> str:
    head = run_git(["rev-parse", "HEAD"], cwd=root, check=True).stdout
    listing = run_git(["ls-files", "-s"], cwd=root, check=True).stdout
    h = hashlib.sha256()
    h.update(head)
    h.update(listing)
    return h.hexdigest()


def assert_source_unchanged(root: Path, before: str) -> None:
    after = source_tree_fingerprint(root)
    if after != before:
        raise WorkerError(
            ERROR_CODES["SOURCE_REPO_CHANGED"],
            "tracked source repository changed during execution",
            state="FAILED_FROZEN",
        )
