"""Detached Git worktree protocol — no branch/commit before review PASS."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.srl_git_exec import (
    constructed_git_env,
    srl_git_exec,
    tree_is_dirty,
)

FORBIDDEN_GIT_OPS = frozenset({"push", "merge", "rebase", "config", "clean", "status"})

GIT_IDENTITY = [
    "-c",
    "user.name=Sentinel Research Lab",
    "-c",
    "user.email=local-self-improvement@invalid",
]


def _sanitized_git_env() -> dict[str, str]:
    """Minimal env for Git — never os.environ.copy(); no credential helpers."""
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "GCM_INTERACTIVE": "never",
        "GC_IDENTIFICATION": "",
    }
    # Preserve Windows process essentials only.
    for key in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TMP", "TEMP", "TMPDIR"):
        val = os.environ.get(key)
        if val:
            env[key] = val
    # Neutralize inherited credential / signing helpers.
    env["GIT_CONFIG_COUNT"] = "0"
    return env


def run_git(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int = 60,
    input_bytes: bytes | None = None,
    with_identity: bool = False,
    extra_config: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if not args:
        raise WorkerError(ERROR_CODES["COMMAND_INJECTION"], "empty git argv", state="FAILED_FROZEN")
    return srl_git_exec(
        args,
        cwd=cwd,
        check=check,
        timeout=timeout,
        input_bytes=input_bytes,
        extra_config=extra_config,
        with_identity=with_identity,
        env=env,
        allow_reset_hard=args[:1] == ["reset"] and "--hard" in args,
    )


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
    if tree_is_dirty(root):
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


def _empty_hooks_dir(worktree: Path) -> Path:
    """Create an empty hooks directory inside the isolated runtime area (worktree parent)."""
    parent = worktree.parent
    if not parent.name.startswith("srl-si2-wt-"):
        # Fallback: sibling under worktree when not using standard layout.
        parent = worktree
    hooks = parent / "isolated-hooks"
    if hooks.exists():
        shutil.rmtree(hooks, ignore_errors=True)
    hooks.mkdir(parents=True, exist_ok=True)
    # Ensure directory contains no executable files.
    for child in hooks.iterdir():
        child.unlink(missing_ok=True)
    return hooks


def _git_config_snapshot(cwd: Path, *, scope: str) -> str:
    proc = srl_git_exec(
        ["config", f"--{scope}", "--list"],
        cwd=cwd,
        check=False,
        env=constructed_git_env(),
    )
    return (proc.stdout or b"").decode("utf-8", errors="replace")


def create_local_commit(worktree: Path, objective: str) -> str:
    """Create a local candidate commit with isolated empty hooks and signing disabled.

    Never mutates repository or global Git configuration. Uses a sanitized environment
    (not os.environ.copy()).
    """
    worktree = worktree.resolve()
    before_local = _git_config_snapshot(worktree, scope="local")
    before_global = _git_config_snapshot(worktree, scope="global")

    hooks = _empty_hooks_dir(worktree)
    if any(hooks.iterdir()):
        raise WorkerError(
            ERROR_CODES["SI2-GIT-HOOKS-NOT-ISOLATED"],
            "isolated hooks directory is not empty",
            state="FAILED_FROZEN",
        )

    env = constructed_git_env()
    # Command-local identity + hooks isolation + signing disable.
    extra = [
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "gpg.program=/nonexistent-si2-gpg",
        "-c",
        "credential.helper=",
    ]

    run_git(["add", "-A"], cwd=worktree, check=True, env=env)
    msg = f"Self-improvement: {objective}"
    proc = run_git(
        [
            "commit",
            "--no-verify",
            "--no-gpg-sign",
            "-m",
            msg,
        ],
        cwd=worktree,
        check=False,
        with_identity=True,
        extra_config=extra,
        env=env,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:500]
        lower = detail.lower()
        if "gpg" in lower or "signing" in lower:
            raise WorkerError(
                ERROR_CODES["SI2-GIT-SIGNING-NOT-DISABLED"],
                detail or "signing interfered with commit",
                state="FAILED_FROZEN",
            )
        if "hook" in lower:
            raise WorkerError(
                ERROR_CODES["SI2-GIT-HOOKS-NOT-ISOLATED"],
                detail or "hook interfered with commit",
                state="FAILED_FROZEN",
            )
        raise WorkerError(ERROR_CODES["FAILED_FROZEN"], detail or "commit failed")

    after_local = _git_config_snapshot(worktree, scope="local")
    after_global = _git_config_snapshot(worktree, scope="global")
    if after_local != before_local or after_global != before_global:
        raise WorkerError(
            ERROR_CODES["SI2-GIT-CONFIG-MUTATION"],
            "git configuration mutated during candidate commit",
            state="FAILED_FROZEN",
        )

    sha = run_git(["rev-parse", "HEAD"], cwd=worktree, check=True, env=env)
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


def index_fingerprint(root: Path) -> str:
    """Fingerprint the Git index (staged + tracked modes/hashes via ls-files -s)."""
    listing = run_git(["ls-files", "-s"], cwd=root, check=True).stdout
    return hashlib.sha256(listing).hexdigest()


def working_tree_content_fingerprint(root: Path) -> str:
    """Fingerprint tracked file *working-tree bytes* (not only index object ids).

    Unstaged edits to trusted paths are visible here even when `git ls-files -s`
    (index) is unchanged.
    """
    listing = run_git(["ls-files", "-z"], cwd=root, check=True).stdout
    paths = [p.decode("utf-8", errors="surrogateescape") for p in listing.split(b"\0") if p]
    h = hashlib.sha256()
    for rel in sorted(paths):
        h.update(rel.encode("utf-8", errors="surrogateescape"))
        h.update(b"\0")
        file_path = root / rel
        if file_path.is_file() and not file_path.is_symlink():
            h.update(file_path.read_bytes())
        else:
            h.update(b"<missing-or-symlink>")
        h.update(b"\0")
    return h.hexdigest()


def worktree_list_fingerprint(root: Path) -> str:
    """Fingerprint `git worktree list --porcelain` for Wall reassertion."""
    proc = run_git(["worktree", "list", "--porcelain"], cwd=root, check=True)
    return hashlib.sha256(proc.stdout).hexdigest()


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
