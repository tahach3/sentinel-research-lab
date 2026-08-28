"""Git worker isolation — detached worktrees and neutralized commit hooks/signing."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import init_temp_repo, run
from tools.self_improvement_v2.git_worker import DetachedWorktree, create_local_commit, run_git
from tools.self_improvement_v2.models import WorkerError


def test_detached_no_branch(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    before_worktrees = run(["git", "worktree", "list", "--porcelain"], repo).stdout
    wt = DetachedWorktree(repo, baseline, "abcd1234ffffeeeeabcd1234ffffeeee")
    try:
        path = wt.prepare()
        name = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], path).stdout.strip()
        assert name == "HEAD"
        branches = run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip()
        assert branches == ""
        after_worktrees = run(["git", "worktree", "list", "--porcelain"], repo).stdout
        assert after_worktrees == before_worktrees
        assert path == wt.scratch / "worktrees" / "main"
        assert (wt.scratch / "repo" / ".git").exists()
        assert not (wt.scratch / "repo" / ".git" / "objects" / "info" / "alternates").exists()
    finally:
        wt.cleanup()


def test_push_merge_rejected(tmp_path: Path):
    repo = tmp_path / "r"
    init_temp_repo(repo)
    with pytest.raises(WorkerError) as ei:
        run_git(["push"], cwd=repo, check=True)
    assert ei.value.code == "PUSH_ATTEMPT"
    with pytest.raises(WorkerError) as ei2:
        run_git(["merge", "HEAD"], cwd=repo, check=True)
    assert ei2.value.code == "MERGE_ATTEMPT"


def _install_malicious_hook(hooks_dir: Path, name: str, marker: Path) -> None:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    script = hooks_dir / name
    # Cross-platform: use a small Python marker writer invoked via sh/cmd-compatible shebang where possible.
    # Git on Windows often runs hooks via sh from Git for Windows.
    body = (
        "#!/bin/sh\n"
        f"echo hooked > \"{marker.as_posix()}\"\n"
        "exit 1\n"
    )
    script.write_text(body, encoding="utf-8", newline="\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_create_local_commit_neutralizes_hooks_and_signing(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    wt = DetachedWorktree(repo, baseline, "deadbeefcafef00ddeadbeefcafef00d")
    worktree = wt.prepare()

    marker = tmp_path / "hook-fired.txt"
    # Install malicious hooks in the shared repo hooks path (normally inherited).
    repo_hooks = repo / ".git" / "hooks"
    for hook_name in ("pre-commit", "commit-msg", "post-commit"):
        _install_malicious_hook(repo_hooks, hook_name, marker)

    # Also poison the worktree's git dir hooks if distinct.
    git_dir = run(["git", "rev-parse", "--git-dir"], worktree).stdout.strip()
    wt_hooks = Path(git_dir) / "hooks"
    if not wt_hooks.is_absolute():
        wt_hooks = (worktree / wt_hooks).resolve()
    for hook_name in ("pre-commit", "commit-msg", "post-commit"):
        _install_malicious_hook(wt_hooks, hook_name, marker)

    # Adversarial local/global-like config on the worktree repo.
    run(["git", "config", "commit.gpgsign", "true"], worktree)
    run(["git", "config", "user.signingkey", "ABADKEY"], worktree)
    run(["git", "config", "credential.helper", "store"], worktree)

    before_local = run(["git", "config", "--local", "--list"], worktree).stdout
    before_global = subprocess.run(
        ["git", "config", "--global", "--list"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    ).stdout

    (worktree / "docs" / "HOOK_SAFE.md").write_text("# safe\n", encoding="utf-8")
    sha = create_local_commit(worktree, "hook isolation probe")
    assert len(sha) == 40
    assert not marker.exists(), "malicious hook must not execute"

    after_local = run(["git", "config", "--local", "--list"], worktree).stdout
    after_global = subprocess.run(
        ["git", "config", "--global", "--list"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    ).stdout
    assert after_local == before_local
    assert after_global == before_global
    # Config values remain as set (we do not mutate), but commit still succeeded unsigned.
    assert "commit.gpgsign=true" in after_local
    assert "credential.helper=store" in after_local

    # Isolated hooks dir must exist and be empty.
    hooks = worktree.parent / "isolated-hooks"
    assert hooks.is_dir()
    assert list(hooks.iterdir()) == []

    wt.cleanup()


def test_sanitized_git_env_sets_optional_locks_and_git_ops_work(tmp_path: Path):
    from tools.self_improvement_v2.git_worker import _sanitized_git_env, run_git

    env = _sanitized_git_env()
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    proc = run_git(["rev-parse", "HEAD"], cwd=repo, env=env)
    assert proc.stdout.decode().strip() == baseline


def test_create_local_commit_does_not_use_environ_copy():
    import ast
    from tools.self_improvement_v2 import git_worker

    tree = ast.parse(Path(git_worker.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "copy":
                val = node.func.value
                if (
                    isinstance(val, ast.Attribute)
                    and val.attr == "environ"
                    and isinstance(val.value, ast.Name)
                    and val.value.id == "os"
                ):
                    raise AssertionError("os.environ.copy() must not be used")
