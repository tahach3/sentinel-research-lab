"""Sole guarded Git runner (Revision 2.4 §10 / 2.5). No parallel _run_git."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

ROLE_READ_ONLY = "READ_ONLY"
ROLE_CONTROLLED = "CONTROLLED_LOCAL_MUTATION"
ROLE_FORBIDDEN = "FORBIDDEN"

REPO_ROLE_DISPOSABLE = "DISPOSABLE_EXECUTION_REPO"
REPO_ROLE_RO_REVIEWED = "RO_REVIEWED_ROOT"
REPO_ROLE_DURABLE = "DURABLE_EVIDENCE_REPO"
REPO_ROLE_UNKNOWN = "UNKNOWN"

READ_ONLY_OPS = frozenset(
    {
        "rev-parse",
        "cat-file",
        "show",
        "diff",
        "log",
        "ls-files",
        "ls-tree",
        "rev-list",
        "for-each-ref",
        "symbolic-ref",
        "bundle",
        "hash-object",
        "config",
        "write-tree",
    }
)

CONTROLLED_OPS = frozenset(
    {
        "clone",
        "checkout",
        "add",
        "commit",
        "reset",
        "update-index",
        "update-ref",
        "worktree",
        "apply",
        "bundle",
        "hash-object",
        "branch",
        "write-tree",
    }
)

FORBIDDEN_OPS = frozenset(
    {
        "push",
        "fetch",
        "pull",
        "merge",
        "rebase",
        "cherry-pick",
        "remote",
        "submodule",
        "clean",
        "status",
        "filter-branch",
        "lfs",
        "credential",
        "init",
    }
)

ALLOWED_MINUS_C = frozenset(
    {
        "core.autocrlf",
        "core.eol",
        "core.safecrlf",
        "core.hooksPath",
        "safe.directory",
        "commit.gpgsign",
        "gpg.program",
        "credential.helper",
        "user.name",
        "user.email",
        "core.ignorecase",
    }
)

_PRESERVE_ENV = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC")


@dataclass(frozen=True)
class GitIsolation:
    home: Path
    hooks: Path
    template: Path
    global_config: Path


_ISOLATION: GitIsolation | None = None


def isolation_dirs(base: Path | None = None) -> GitIsolation:
    global _ISOLATION
    if base is None and _ISOLATION is not None:
        return _ISOLATION
    root = Path(base) if base is not None else Path(tempfile.mkdtemp(prefix="srl-git-iso-"))
    home = root / "home"
    hooks = root / "hooks"
    template = root / "template"
    home.mkdir(parents=True, exist_ok=True)
    hooks.mkdir(parents=True, exist_ok=True)
    template.mkdir(parents=True, exist_ok=True)
    for child in hooks.iterdir():
        if child.is_file():
            child.unlink()
    global_config = home / ".gitconfig"
    if not global_config.exists():
        global_config.write_text("", encoding="utf-8")
    layout = GitIsolation(home=home, hooks=hooks, template=template, global_config=global_config)
    if base is None:
        _ISOLATION = layout
    return layout


def constructed_git_env(isolation: GitIsolation | None = None) -> dict[str, str]:
    iso = isolation or isolation_dirs()
    env: dict[str, str] = {}
    for key in _PRESERVE_ENV:
        val = os.environ.get(key)
        if val:
            env[key] = val
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_ATTR_NOSYSTEM"] = "1"
    env["GIT_TEMPLATE_DIR"] = str(iso.template)
    env["HOME"] = str(iso.home)
    env["XDG_CONFIG_HOME"] = str(iso.home)
    env["GIT_CONFIG_GLOBAL"] = str(iso.global_config)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_CONFIG_COUNT"] = "0"
    inherited_git = [key for key in os.environ if key.startswith("GIT_")]
    unknown = [
        key
        for key in inherited_git
        if key
        not in {
            "GIT_CONFIG_NOSYSTEM",
            "GIT_OPTIONAL_LOCKS",
            "GIT_ATTR_NOSYSTEM",
            "GIT_TEMPLATE_DIR",
            "GIT_CONFIG_GLOBAL",
            "GIT_TERMINAL_PROMPT",
            "GIT_ASKPASS",
            "GIT_CONFIG_COUNT",
        }
    ]
    # Fail closed: inherited GIT_* must never pass through. constructed env omits them.
    _ = unknown
    return env


def classify_git_args(args: list[str]) -> str:
    if not args:
        raise WorkerError(ERROR_CODES["COMMAND_INJECTION"], "empty git argv", state="FAILED_FROZEN")
    op = args[0]
    if op in FORBIDDEN_OPS:
        return ROLE_FORBIDDEN
    if op == "config":
        rest = set(args[1:])
        if rest & {"--add", "--unset", "--unset-all", "--replace-all", "--remove-section"}:
            return ROLE_FORBIDDEN
        if "--list" in args or "--get" in args or "--get-regexp" in args:
            return ROLE_READ_ONLY
        return ROLE_FORBIDDEN
    if op == "bundle":
        if len(args) < 2:
            return ROLE_FORBIDDEN
        if args[1] in {"verify", "list-heads"}:
            return ROLE_READ_ONLY
        if args[1] == "create":
            return ROLE_CONTROLLED
        return ROLE_FORBIDDEN
    if op == "hash-object":
        return ROLE_CONTROLLED if "-w" in args else ROLE_READ_ONLY
    if op == "update-ref":
        if SRL_CANDIDATE_REF_IN(args):
            return ROLE_CONTROLLED
        return ROLE_FORBIDDEN
    if op == "write-tree":
        return ROLE_CONTROLLED
    if op in CONTROLLED_OPS:
        return ROLE_CONTROLLED
    if op in READ_ONLY_OPS:
        return ROLE_READ_ONLY
    return ROLE_FORBIDDEN


def SRL_CANDIDATE_REF_IN(args: list[str]) -> bool:
    return any(part == "refs/heads/srl-candidate" for part in args)


def _forbidden_code(op: str) -> str:
    if op == "push":
        return ERROR_CODES["PUSH_ATTEMPT"]
    if op == "merge":
        return ERROR_CODES["MERGE_ATTEMPT"]
    if op == "status":
        return ERROR_CODES["REVIEWED_SOURCE_WRITE"]
    return ERROR_CODES["FORBIDDEN_GIT_OP"]


def _validate_minus_c(extra_config: list[str] | None) -> None:
    if not extra_config:
        return
    i = 0
    while i < len(extra_config):
        if extra_config[i] != "-c":
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                "extra_config must be -c key=value pairs",
                state="POLICY_REJECTED",
            )
        if i + 1 >= len(extra_config):
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "dangling -c", state="POLICY_REJECTED")
        pair = extra_config[i + 1]
        key = pair.split("=", 1)[0]
        if key == "safe.directory" and pair.endswith("=*"):
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                "safe.directory=* is forbidden",
                state="POLICY_REJECTED",
            )
        if key not in ALLOWED_MINUS_C:
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                f"git -c key not allowlisted: {key}",
                state="POLICY_REJECTED",
            )
        i += 2


def srl_git_exec(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int = 60,
    input_bytes: bytes | None = None,
    extra_config: list[str] | None = None,
    with_identity: bool = False,
    isolation: GitIsolation | None = None,
    env: dict[str, str] | None = None,
    allow_reset_hard: bool = False,
    repository_role: str = REPO_ROLE_UNKNOWN,
) -> subprocess.CompletedProcess[bytes]:
    role = classify_git_args(args)
    op = args[0]
    if role == ROLE_FORBIDDEN:
        raise WorkerError(
            _forbidden_code(op),
            f"forbidden git operation: {op}",
            state="POLICY_REJECTED",
        )
    if op == "reset" and "--hard" in args:
        # Permission is never derived from argv. All three must hold.
        if (
            role != ROLE_CONTROLLED
            or repository_role != REPO_ROLE_DISPOSABLE
            or not allow_reset_hard
        ):
            raise WorkerError(
                ERROR_CODES["FORBIDDEN_GIT_OP"],
                "reset --hard requires CONTROLLED_LOCAL_MUTATION + "
                "DISPOSABLE_EXECUTION_REPO + explicit policy",
                state="POLICY_REJECTED",
            )
    if op == "clone":
        joined = " ".join(args)
        if "--shared" in args or "--reference" in args or "--reference-if-able" in args:
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                "clone --shared/--reference is forbidden",
                state="POLICY_REJECTED",
            )
        if "--local" in args:
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                "clone --local is forbidden",
                state="POLICY_REJECTED",
            )
        _ = joined
    _validate_minus_c(extra_config)
    iso = isolation or isolation_dirs()
    use_env = env if env is not None else constructed_git_env(iso)
    prefix = ["git"]
    prefix.extend(
        [
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.eol=lf",
            "-c",
            "core.safecrlf=false",
            "-c",
            f"core.hooksPath={iso.hooks}",
            "-c",
            f"safe.directory={Path(cwd).resolve()}",
        ]
    )
    if with_identity:
        prefix.extend(
            [
                "-c",
                "user.name=Sentinel Research Lab",
                "-c",
                "user.email=local-self-improvement@invalid",
            ]
        )
    if extra_config:
        prefix.extend(extra_config)
    argv = [*prefix, *args]
    if op == "clone" and "--template" not in args:
        # Insert after 'clone'
        argv = [*prefix, "clone", f"--template={iso.template}", "--no-hardlinks", "--no-local", *args[1:]]
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        input=input_bytes,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
        env=use_env,
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:500]
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], detail or f"git {op} failed")
    return proc


def tree_is_dirty(root: Path, *, isolation: GitIsolation | None = None) -> bool:
    """Dirty detection without `git status` (forbidden globally)."""
    diff = srl_git_exec(
        ["diff", "--quiet", "--no-ext-diff", "--exit-code", "HEAD"],
        cwd=root,
        check=False,
        isolation=isolation,
    )
    if diff.returncode == 1:
        return True
    if diff.returncode not in (0, 1):
        detail = (diff.stderr or diff.stdout).decode("utf-8", errors="replace")[:300]
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], detail or "git diff failed")
    untracked = srl_git_exec(
        ["ls-files", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        isolation=isolation,
    )
    return bool(untracked.stdout.strip())
