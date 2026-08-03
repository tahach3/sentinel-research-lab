"""Detached Git worktree protocol — no branch/commit before review PASS."""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

FORBIDDEN_GIT_OPS = frozenset({"push", "merge", "rebase", "config", "clean"})

GIT_IDENTITY = [
    "-c",
    "user.name=Sentinel Research Lab",
    "-c",
    "user.email=local-self-improvement@invalid",
]


def run_git(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int = 60,
    input_bytes: bytes | None = None,
    with_identity: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    if not args:
        raise WorkerError(ERROR_CODES["COMMAND_INJECTION"], "empty git argv", state="FAILED_FROZEN")
    op = args[0]
    if op in FORBIDDEN_GIT_OPS:
        code = (
            ERROR_CODES["PUSH_ATTEMPT"]
            if op == "push"
            else (ERROR_CODES["MERGE_ATTEMPT"] if op == "merge" else ERROR_CODES["POLICY_REJECTED"])
        )
        raise WorkerError(code, f"forbidden git operation: {op}", state="POLICY_REJECTED")
    prefix = ["git", *GIT_IDENTITY] if with_identity else ["git"]
    proc = subprocess.run(
        [*prefix, *args],
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


def branch_name_for(candidate_id: str, execution_id: str) -> str:
    safe_candidate = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in candidate_id)
    short = execution_id[:8]
    return f"self-improvement-v2/{safe_candidate}/{short}"


class DetachedWorktree:
    """Detached temporary worktree — no branch created until finalization."""

    def __init__(self, source_root: Path, baseline_sha: str, execution_id: str) -> None:
        self.source_root = source_root.resolve()
        self.baseline_sha = baseline_sha
        self.execution_id = execution_id
        self.path: Path | None = None
        self._parent: Path | None = None
        self._kept = False

    def prepare(self) -> Path:
        # mkdtemp (not TemporaryDirectory) so keep-for-finalize cannot auto-delete.
        self._parent = Path(tempfile.mkdtemp(prefix="srl-si2-wt-"))
        self.path = self._parent / "worktree"
        run_git(
            ["worktree", "add", "--detach", str(self.path), self.baseline_sha],
            cwd=self.source_root,
            check=True,
        )
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=self.path, check=True)
        name = branch.stdout.decode("utf-8").strip()
        if name != "HEAD":
            raise WorkerError(
                ERROR_CODES["BRANCH_BEFORE_REVIEW"],
                f"worktree not detached: {name}",
                state="FAILED_FROZEN",
            )
        return self.path

    def abandon_tmpdir_ownership(self) -> Path:
        """Return path and transfer ownership to the experience store / finalizer."""
        assert self.path is not None and self._parent is not None
        path = self.path
        meta = self._parent / "si2_meta.json"
        meta.write_text(
            json.dumps(
                {
                    "worktree": str(path),
                    "source_root": str(self.source_root),
                    "baseline_sha": self.baseline_sha,
                    "execution_id": self.execution_id,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self._kept = True
        return path

    def cleanup(self) -> None:
        if self._kept:
            # Ownership transferred; do not delete here.
            self.path = None
            self._parent = None
            return
        if self.path is not None:
            remove_worktree(self.source_root, self.path)
        self.path = None
        self._parent = None


def remove_worktree(source_root: Path, worktree: Path) -> None:
    run_git(["worktree", "remove", "--force", str(worktree)], cwd=source_root, check=False)
    if worktree.exists():
        shutil.rmtree(worktree, ignore_errors=True)
    run_git(["worktree", "prune"], cwd=source_root, check=False)
    parent = worktree.parent
    meta = parent / "si2_meta.json"
    if meta.exists():
        meta.unlink(missing_ok=True)
    if parent.exists() and parent.name.startswith("srl-si2-wt-"):
        shutil.rmtree(parent, ignore_errors=True)


def create_local_commit(worktree: Path, objective: str) -> str:
    run_git(["add", "-A"], cwd=worktree, check=True)
    msg = f"Self-improvement: {objective}"
    proc = run_git(
        ["commit", "-m", msg],
        cwd=worktree,
        check=False,
        with_identity=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:500]
        raise WorkerError(ERROR_CODES["FAILED_FROZEN"], detail or "commit failed")
    sha = run_git(["rev-parse", "HEAD"], cwd=worktree, check=True)
    return sha.stdout.decode("utf-8").strip()


def create_branch_at_commit(source_root: Path, branch_name: str, commit: str) -> None:
    # Create branch ref only after commit exists.
    proc = run_git(["branch", branch_name, commit], cwd=source_root, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:500]
        # Idempotent: if branch already points to same commit, OK
        show = run_git(["rev-parse", branch_name], cwd=source_root, check=False)
        if show.returncode == 0 and show.stdout.decode().strip() == commit:
            return
        raise WorkerError(ERROR_CODES["FAILED_FROZEN"], detail or "branch create failed")


def worktree_head(worktree: Path) -> str:
    return run_git(["rev-parse", "HEAD"], cwd=worktree, check=True).stdout.decode().strip()


def assert_detached_and_baseline(worktree: Path, baseline_sha: str) -> None:
    name = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree, check=True).stdout.decode().strip()
    if name != "HEAD":
        raise WorkerError(
            ERROR_CODES["BRANCH_BEFORE_REVIEW"],
            "branch present before review pass",
            state="FAILED_FROZEN",
        )
    head = worktree_head(worktree)
    if head != baseline_sha:
        # After staging, HEAD should still be baseline until commit.
        # If already committed, head changes — finalizer handles post-commit separately.
        pass
    # Ensure no commits ahead of baseline before finalize commit step:
    count = run_git(
        ["rev-list", "--count", f"{baseline_sha}..HEAD"],
        cwd=worktree,
        check=True,
    ).stdout.decode().strip()
    if count not in ("0", ""):
        raise WorkerError(
            ERROR_CODES["COMMIT_BEFORE_REVIEW"],
            "commit present before review pass",
            state="FAILED_FROZEN",
        )


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


def list_local_branches(root: Path) -> list[str]:
    proc = run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=root, check=True)
    return [line.decode() if isinstance(line, bytes) else line for line in proc.stdout.splitlines()]
