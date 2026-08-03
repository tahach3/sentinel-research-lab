"""Git isolation and negative safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.self_improvement.helpers import init_temp_repo, write_json, build_pilot_proposal
from tools.self_improvement.cli import execute_cmd, main
from tools.self_improvement.git_worker import TemporaryWorktree, run_git
from tools.self_improvement.models import WorkerError


def test_temporary_worktree_isolated(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    with TemporaryWorktree(repo, baseline, "cand-1") as wt:
        assert wt.path is not None
        assert wt.path.exists()
        assert (wt.path / "docs" / "README.md").is_file()
        branch = wt.branch_name
        assert branch.startswith("self-improvement/")
    assert not (tmp_path / "gone").exists()


def test_baseline_mismatch_and_dirty_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    proposal = build_pilot_proposal(repo, "a" * 40)
    prop_path = tmp_path / "proposal.json"
    write_json(prop_path, proposal)
    result_path = tmp_path / "result.json"
    db = tmp_path / "state.sqlite"
    code = execute_cmd(repo, prop_path, db, result_path)
    assert code == 1
    data = result_path.read_text(encoding="utf-8")
    assert "BASELINE_MISMATCH" in data

    # dirty tree
    proposal2 = build_pilot_proposal(repo, baseline)
    write_json(prop_path, proposal2)
    (repo / "docs" / "dirty.md").write_text("dirty\n", encoding="utf-8")
    code2 = execute_cmd(repo, prop_path, db, result_path)
    assert code2 == 1
    assert "DIRTY_SOURCE_TREE" in result_path.read_text(encoding="utf-8")


def test_direct_push_attempt_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    with pytest.raises(WorkerError) as exc:
        run_git(["push", "origin", "HEAD"], cwd=repo, check=True)
    assert exc.value.code == "PUSH_ATTEMPT"


def test_tracked_source_unchanged_guard(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    proposal = build_pilot_proposal(repo, baseline)
    prop_path = tmp_path / "proposal.json"
    write_json(prop_path, proposal)
    result_path = tmp_path / "result.json"
    db = tmp_path / "state.sqlite"
    before = (repo / "docs" / "README.md").read_text(encoding="utf-8")
    code = execute_cmd(repo, prop_path, db, result_path)
    assert code == 0
    after = (repo / "docs" / "README.md").read_text(encoding="utf-8")
    assert before == after
    assert not (repo / "docs" / "SELF_IMPROVEMENT_NOTE.md").exists()
