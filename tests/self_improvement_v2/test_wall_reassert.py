"""Wall artifact fingerprint helpers including worktree-list reassertion."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import init_temp_repo, run
from tools.self_improvement_v2.git_worker import (
    index_fingerprint,
    source_tree_fingerprint,
    worktree_list_fingerprint,
)
from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.wall_reassert import (
    WallReassertError,
    assert_wall_artifacts_unchanged,
    capture_wall_artifact_snapshot,
)


def test_wall_snapshot_stable_on_clean_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    before = capture_wall_artifact_snapshot(repo)
    assert len(before["source_tree_fingerprint"]) == 64
    assert len(before["index_fingerprint"]) == 64
    assert len(before["worktree_list_fingerprint"]) == 64
    assert before["index_fingerprint"] == index_fingerprint(repo)
    assert before["source_tree_fingerprint"] == source_tree_fingerprint(repo)
    result = assert_wall_artifacts_unchanged(repo, before)
    assert result["status"] == "PASS"


def test_worktree_list_fingerprint_detects_added_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    before = worktree_list_fingerprint(repo)
    wt = tmp_path / "extra-wt"
    run(["git", "worktree", "add", "--detach", str(wt), baseline], repo)
    after = worktree_list_fingerprint(repo)
    assert after != before
    snap_before = capture_wall_artifact_snapshot(repo)
    # Capture after already includes the extra worktree — mutate again via prune path:
    # remove worktree and expect mismatch against snap that included it.
    run(["git", "worktree", "remove", "--force", str(wt)], repo, check=False)
    with pytest.raises(WallReassertError) as exc:
        assert_wall_artifacts_unchanged(repo, snap_before)
    assert exc.value.code == ERROR_CODES["WALL_REASSERT_MISMATCH"]
    assert "worktree_list_fingerprint" in exc.value.message


def test_index_fingerprint_detects_staged_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    before = capture_wall_artifact_snapshot(repo)
    (repo / "docs" / "WALL.md").write_text("# wall\n", encoding="utf-8")
    run(["git", "add", "docs/WALL.md"], repo)
    with pytest.raises(WallReassertError) as exc:
        assert_wall_artifacts_unchanged(repo, before)
    assert "index_fingerprint" in exc.value.message or "source_tree_fingerprint" in exc.value.message
