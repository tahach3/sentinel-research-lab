from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import init_temp_repo, run
from tools.self_improvement_v2.git_worker import DetachedWorktree, run_git
from tools.self_improvement_v2.models import WorkerError


def test_detached_no_branch(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    wt = DetachedWorktree(repo, baseline, "abcd1234ffffeeee")
    path = wt.prepare()
    name = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], path).stdout.strip()
    assert name == "HEAD"
    branches = run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip()
    assert branches == ""
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
