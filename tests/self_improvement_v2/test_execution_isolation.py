"""E1–E3 execution isolation: independent clone, hex32 IDs, mode surfaces."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import build_proposal, init_temp_repo, run
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.git_worker import (
    DEFAULT_EXEC_ROOT,
    DetachedWorktree,
    EXECUTION_ID_RE,
    new_execution_id,
)
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.runtime_config import load_runtime_config
from tools.self_improvement_v2.validation_runner import sanitized_environ
from tools.self_improvement_v2.zone_p_harness import ZONE_P_TMPDIR, allocate_zone_p_state_db


def test_new_execution_id_is_hex32() -> None:
    value = new_execution_id()
    assert EXECUTION_ID_RE.fullmatch(value)


def test_detached_worktree_refuses_non_hex32(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    with pytest.raises(WorkerError):
        DetachedWorktree(repo, baseline, "abcd1234ffffeeee")


def test_execute_uses_independent_clone_under_srl_exec(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    before_wt = run(["git", "worktree", "list", "--porcelain"], repo).stdout
    before_head = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    db = tmp_path / "s.sqlite"
    bundle = execute_proposal(root=repo, proposal=build_proposal(baseline), state_db=db)
    assert EXECUTION_ID_RE.fullmatch(bundle["execution_id"])
    store = ExperienceStore(db)
    _bundle, worktree = store.get_execution(bundle["execution_id"])
    wt = Path(worktree).resolve()
    expected = (DEFAULT_EXEC_ROOT / bundle["execution_id"] / "worktrees" / "main").resolve()
    assert wt == expected
    assert wt.is_dir()
    clone = DEFAULT_EXEC_ROOT / bundle["execution_id"] / "repo"
    assert clone.is_dir()
    assert not (clone / ".git" / "objects" / "info" / "alternates").exists()
    after_wt = run(["git", "worktree", "list", "--porcelain"], repo).stdout
    assert after_wt == before_wt
    assert run(["git", "rev-parse", "HEAD"], repo).stdout.strip() == before_head
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_sqlite_journal_mode_delete(tmp_path: Path) -> None:
    db = tmp_path / "journal.sqlite"
    ExperienceStore(db)
    conn = sqlite3.connect(str(db))
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert str(mode).upper() == "DELETE"


def test_validation_env_disables_bytecode() -> None:
    env = sanitized_environ(pythonpath="/tmp")
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_p3c1_mode_refuses_wrong_surfaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "sentinel-research-lab"
    init_temp_repo(repo)
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    monkeypatch.setenv("SRL_RUNTIME_MODE", "P3C1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("TMPDIR", "/tmp")
    with pytest.raises(Exception, match="P3C1"):
        load_runtime_config(
            repository_root=str(repo),
            state_db=str(tmp_path / "db.sqlite"),
            worker_token="test-worker-token-not-for-production",
            worker_host="127.0.0.1",
            worker_port=8765,
        )


def test_zone_p_mode_refuses_p3c1_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "sentinel-research-lab"
    init_temp_repo(repo)
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    monkeypatch.setenv("SRL_RUNTIME_MODE", "ZONE_P")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("TMPDIR", str(ZONE_P_TMPDIR))
    with pytest.raises(Exception, match="Zone P"):
        load_runtime_config(
            repository_root=str(repo),
            state_db="/srl/state/self-improvement-v2.sqlite",
            worker_token="test-worker-token-not-for-production",
            worker_host="127.0.0.1",
            worker_port=8765,
        )


def test_allocate_zone_p_db_under_zone_p_tmpdir() -> None:
    path = allocate_zone_p_state_db(probe_id="iso1")
    assert path.parent == ZONE_P_TMPDIR
    assert os.environ.get("TMPDIR") != "/tmp/srl-exec"
