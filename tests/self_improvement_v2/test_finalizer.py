import inspect
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo, run
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.finalizer import finalize, finalize_or_freeze
from tools.self_improvement_v2.models import WorkerError


def _ready(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, proposal)
    store.insert_review(review)
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""
    return repo, db, proposal, bundle, review, store


def test_finalize_happy_path(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    result = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert result["final_state"] == "READY_FOR_HUMAN_PROMOTION"
    assert result["candidate_commit"]
    assert result["candidate_branch"].startswith("self-improvement-v2/")
    assert result["committed_tree_sha"] == bundle["worktree_tree_sha"]
    again = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert again["candidate_commit"] == result["candidate_commit"]


def test_altered_worktree_fails(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    wt = Path(store.get_execution(bundle["execution_id"])[1])
    (wt / "docs" / "EXTRA.md").write_text("nope\n", encoding="utf-8")
    with pytest.raises(WorkerError) as ei:
        finalize_or_freeze(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == "CONTENT_BINDING_MISMATCH"
    assert ei.value.state == "FAILED_FROZEN"
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_v1_stale_review_pwned_exploit(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    wt = Path(store.get_execution(bundle["execution_id"])[1])
    (wt / "docs" / "PWNED.md").write_text("PWNED\n", encoding="utf-8")
    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == "CONTENT_BINDING_MISMATCH"
    assert not (repo / "docs" / "PWNED.md").exists()
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_conflicting_second_review(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    result = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert result["candidate_commit"]
    other = dict(review)
    other["review_id"] = "rev-other"
    store.insert_review(other)
    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=other["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == "SI2-REVIEW-CONFLICT"


def test_finalizer_signature_no_patch_args():
    sig = inspect.signature(finalize)
    assert "proposal" not in sig.parameters
    assert "patches" not in sig.parameters
    assert set(sig.parameters) >= {"execution_id", "review_id", "state_db", "repository_root"}
