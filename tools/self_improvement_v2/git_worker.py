"""Detached Git worktree protocol — no branch/commit before review PASS."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

DEFAULT_EXEC_ROOT = Path("/tmp/srl-exec")
EXECUTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
FORBIDDEN_CLONE_FLAGS = ("--shared", "--reference", "--reference-if-able")

FORBIDDEN_GIT_OPS = frozenset({"push", "merge", "rebase", "config", "clean"})

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
    env["PYTHONDONTWRITEBYTECODE"] = "1"
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
    op = args[0]
    if op in FORBIDDEN_GIT_OPS:
        code = (
            ERROR_CODES["PUSH_ATTEMPT"]
            if op == "push"
            else (ERROR_CODES["MERGE_ATTEMPT"] if op == "merge" else ERROR_CODES["POLICY_REJECTED"])
        )
        raise WorkerError(code, f"forbidden git operation: {op}", state="POLICY_REJECTED")
    prefix = ["git"]
    if with_identity:
        prefix.extend(GIT_IDENTITY)
    if extra_config:
        prefix.extend(extra_config)
    proc = subprocess.run(
        [*prefix, *args],
        cwd=str(cwd),
        input=input_bytes,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
        env=env,
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


def default_exec_root() -> Path:
    raw = str(os.environ.get("SRL_EXEC_ROOT") or "").strip()
    return Path(raw) if raw else DEFAULT_EXEC_ROOT


def new_execution_id() -> str:
    return secrets.token_hex(16)


def assert_execution_id(execution_id: str) -> str:
    if not isinstance(execution_id, str) or EXECUTION_ID_RE.fullmatch(execution_id) is None:
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "execution_id must be 32 lowercase hex",
            state="POLICY_REJECTED",
        )
    return execution_id


def short_run_id() -> str:
    return secrets.token_hex(4)


def branch_name_for(candidate_id: str, execution_id: str) -> str:
    safe_candidate = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in candidate_id)
    short = execution_id[:8]
    return f"self-improvement-v2/{safe_candidate}/{short}"


def _git_dir(repo: Path) -> Path:
    proc = run_git(["rev-parse", "--git-dir"], cwd=repo, check=True, env=_sanitized_git_env())
    raw = proc.stdout.decode("utf-8").strip()
    path = Path(raw)
    return path if path.is_absolute() else (repo / path).resolve()


def assert_no_alternates(repo: Path) -> None:
    git_dir = _git_dir(repo)
    alternates = git_dir / "objects" / "info" / "alternates"
    if alternates.is_file() and alternates.read_text(encoding="utf-8").strip():
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "clone must not share object alternates with the reviewed source",
            state="FAILED_FROZEN",
        )


def _object_file_inodes(repo: Path) -> set[tuple[int, int]]:
    git_dir = _git_dir(repo)
    objects = git_dir / "objects"
    found: set[tuple[int, int]] = set()
    if not objects.is_dir():
        return found
    for path in objects.rglob("*"):
        if path.is_file() and not path.is_symlink():
            stat = path.stat()
            found.add((stat.st_dev, stat.st_ino))
    return found


def _assert_clone_argv(args: list[str]) -> None:
    if not args or args[0] != "clone":
        raise WorkerError(ERROR_CODES["COMMAND_INJECTION"], "execution clone argv is not git clone")
    joined = args
    for flag in FORBIDDEN_CLONE_FLAGS:
        if flag in joined:
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                f"git clone must not use {flag}",
                state="FAILED_FROZEN",
            )
    if "--no-local" not in joined or "--no-hardlinks" not in joined:
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "git clone must be --no-local --no-hardlinks",
            state="FAILED_FROZEN",
        )


def _clone_env(*, git_tmp: Path) -> dict[str, str]:
    env = _sanitized_git_env()
    env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    env.pop("GIT_OBJECT_DIRECTORY", None)
    env["TMPDIR"] = str(git_tmp)
    env["TMP"] = str(git_tmp)
    env["TEMP"] = str(git_tmp)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


class DetachedWorktree:
    """Independent disposable clone + detached worktree. Never writes the reviewed source."""

    def __init__(
        self,
        source_root: Path,
        baseline_sha: str,
        execution_id: str,
        *,
        exec_root: Path | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.baseline_sha = baseline_sha
        self.execution_id = assert_execution_id(execution_id)
        self.exec_root = Path(exec_root).resolve() if exec_root is not None else default_exec_root().resolve()
        self.scratch = self.exec_root / self.execution_id
        self.clone_path: Path | None = None
        self.path: Path | None = None
        self._kept = False

    def prepare(self) -> Path:
        if self.scratch.exists():
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                "execution scratch already exists",
                state="FAILED_FROZEN",
            )
        self.exec_root.mkdir(parents=True, exist_ok=True)
        self.scratch.mkdir(parents=False, exist_ok=False)
        worktrees = self.scratch / "worktrees"
        git_tmp = worktrees / "git-tmp"
        hooks = worktrees / "isolated-hooks"
        export = self.scratch / "export"
        git_tmp.mkdir(parents=True, exist_ok=True)
        hooks.mkdir(parents=True, exist_ok=True)
        export.mkdir(parents=True, exist_ok=True)
        self.clone_path = self.scratch / "repo"
        env = _clone_env(git_tmp=git_tmp)
        clone_args = [
            "clone",
            "--no-local",
            "--no-hardlinks",
            "--",
            str(self.source_root),
            str(self.clone_path),
        ]
        _assert_clone_argv(clone_args)
        run_git(clone_args, cwd=self.scratch, check=True, env=env)
        assert_no_alternates(self.clone_path)
        source_inodes = _object_file_inodes(self.source_root)
        clone_inodes = _object_file_inodes(self.clone_path)
        if source_inodes and clone_inodes and source_inodes.intersection(clone_inodes):
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                "clone object store shares inodes with reviewed source",
                state="FAILED_FROZEN",
            )
        self.path = worktrees / "main"
        run_git(
            ["worktree", "add", "--detach", str(self.path), self.baseline_sha],
            cwd=self.clone_path,
            check=True,
            env=env,
        )
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=self.path, check=True, env=env)
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
        assert self.path is not None and self.clone_path is not None
        path = self.path
        meta = self.scratch / "si2_meta.json"
        meta.write_text(
            json.dumps(
                {
                    "worktree": str(path),
                    "clone_path": str(self.clone_path),
                    "source_root": str(self.source_root),
                    "baseline_sha": self.baseline_sha,
                    "execution_id": self.execution_id,
                    "scratch": str(self.scratch),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self._kept = True
        return path

    def cleanup(self) -> None:
        if self._kept:
            self.path = None
            self.clone_path = None
            return
        if self.scratch.exists():
            shutil.rmtree(self.scratch, ignore_errors=True)
        self.path = None
        self.clone_path = None


def execution_scratch_from_worktree(worktree: Path) -> Path:
    resolved = worktree.resolve()
    # /tmp/srl-exec/<id>/worktrees/main → scratch is parent.parent
    if resolved.parent.name != "worktrees":
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "worktree is not under /worktrees/main",
            state="FAILED_FROZEN",
        )
    return resolved.parent.parent


def remove_worktree(source_root: Path, worktree: Path) -> None:
    """Remove disposable execution scratch. Never runs git worktree on reviewed source."""
    del source_root  # reviewed source is not a git write target
    scratch = execution_scratch_from_worktree(worktree)
    meta = scratch / "si2_meta.json"
    clone: Path | None = None
    if meta.is_file():
        try:
            payload = json.loads(meta.read_text(encoding="utf-8"))
            raw = payload.get("clone_path")
            if isinstance(raw, str) and raw:
                clone = Path(raw)
        except json.JSONDecodeError:
            clone = None
    if clone is None:
        clone = scratch / "repo"
    if clone.is_dir():
        run_git(
            ["worktree", "remove", "--force", str(worktree)],
            cwd=clone,
            check=False,
            env=_sanitized_git_env(),
        )
        run_git(["worktree", "prune"], cwd=clone, check=False, env=_sanitized_git_env())
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)


def _empty_hooks_dir(worktree: Path) -> Path:
    """Empty hooks directory sibling to the detached worktree (worktrees/isolated-hooks)."""
    parent = worktree.parent
    hooks = parent / "isolated-hooks"
    if hooks.exists():
        shutil.rmtree(hooks, ignore_errors=True)
    hooks.mkdir(parents=True, exist_ok=True)
    for child in hooks.iterdir():
        child.unlink(missing_ok=True)
    return hooks


def _git_config_snapshot(cwd: Path, *, scope: str) -> str:
    proc = subprocess.run(
        ["git", "config", f"--{scope}", "--list"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        env=_sanitized_git_env(),
    )
    return proc.stdout or ""


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

    env = _sanitized_git_env()
    git_tmp = worktree.parent / "git-tmp"
    git_tmp.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(git_tmp)
    env["TMP"] = str(git_tmp)
    env["TEMP"] = str(git_tmp)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
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


EXPORT_REF_PREFIX = "refs/srl/export/"


def export_ref_for(execution_id: str) -> str:
    return f"{EXPORT_REF_PREFIX}{assert_execution_id(execution_id)}"


def package_candidate_export(
    *,
    clone_root: Path,
    worktree: Path,
    execution_id: str,
    baseline_sha: str,
    commit: str,
) -> dict[str, str]:
    """Write refs/srl/export/<id>, candidate.bundle, and actual.diff in disposable scratch."""
    execution_id = assert_execution_id(execution_id)
    scratch = execution_scratch_from_worktree(worktree)
    export_dir = scratch / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    git_tmp = scratch / "worktrees" / "git-tmp"
    git_tmp.mkdir(parents=True, exist_ok=True)
    env = _clone_env(git_tmp=git_tmp)
    ref = export_ref_for(execution_id)
    run_git(["update-ref", ref, commit], cwd=clone_root, check=True, env=env)
    stored = run_git(["rev-parse", ref], cwd=clone_root, check=True, env=env).stdout.decode().strip()
    if stored != commit:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "export ref does not point at the candidate commit",
            state="FAILED_FROZEN",
        )
    bundle_path = export_dir / "candidate.bundle"
    diff_path = export_dir / "actual.diff"
    run_git(["bundle", "create", str(bundle_path), ref], cwd=clone_root, check=True, env=env)
    verify = run_git(["bundle", "verify", str(bundle_path)], cwd=clone_root, check=False, env=env)
    if verify.returncode != 0:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "candidate.bundle failed git bundle verify",
            state="FAILED_FROZEN",
        )
    diff_proc = run_git(
        ["diff", "--binary", baseline_sha, commit],
        cwd=clone_root,
        check=True,
        env=env,
    )
    diff_path.write_bytes(diff_proc.stdout or b"")
    bundle_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    diff_sha = hashlib.sha256(diff_path.read_bytes()).hexdigest()
    state = {
        "schema": "srl.candidate_export_state.v1",
        "execution_id": execution_id,
        "export_ref": ref,
        "candidate_commit": commit,
        "candidate_bundle_sha256": bundle_sha,
        "actual_diff_sha256": diff_sha,
        "state": "NOT_EXPORTED",
    }
    (export_dir / "export_state.json").write_text(
        json.dumps(state, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return state


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
