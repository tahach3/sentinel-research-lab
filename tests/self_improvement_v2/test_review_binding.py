from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.review_gate import assert_review_bound


def _exec(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    return repo, db, proposal, bundle


def test_review_binds_all_hashes(tmp_path: Path):
    _repo, _db, proposal, bundle = _exec(tmp_path)
    review = build_pass_review(bundle, proposal)
    assert_review_bound(review, proposal=proposal, bundle=bundle)


@pytest.mark.parametrize(
    "field,code",
    [
        ("proposal_sha256", "SI2-REVIEW-PROPOSAL-HASH"),
        ("execution_id", "SI2-REVIEW-EXECUTION-ID"),
        ("execution_result_sha256", "SI2-REVIEW-EXECUTION-HASH"),
        ("actual_diff_sha256", "SI2-REVIEW-DIFF-HASH"),
        ("worktree_tree_sha", "SI2-REVIEW-TREE-HASH"),
        ("validation_results_sha256", "SI2-REVIEW-VALIDATION-HASH"),
    ],
)
def test_stale_hash_fields(tmp_path: Path, field, code):
    _repo, _db, proposal, bundle = _exec(tmp_path)
    review = build_pass_review(bundle, proposal)
    if field.endswith("sha256") or field == "worktree_tree_sha":
        review[field] = "a" * len(review[field])
    else:
        review[field] = "other-exec"
    with pytest.raises(WorkerError) as ei:
        assert_review_bound(review, proposal=proposal, bundle=bundle)
    assert ei.value.code == code


def test_wrong_execution_review(tmp_path: Path):
    _repo, _db, proposal, bundle = _exec(tmp_path)
    review = build_pass_review(bundle, proposal)
    review["execution_id"] = "deadbeef" * 4
    with pytest.raises(WorkerError) as ei:
        assert_review_bound(review, proposal=proposal, bundle=bundle)
    assert ei.value.code == "SI2-REVIEW-EXECUTION-ID"


def test_pass_with_architecture_findings(tmp_path: Path):
    _repo, _db, proposal, bundle = _exec(tmp_path)
    review = build_pass_review(bundle, proposal)
    review["architecture_findings"] = ["layering issue"]
    with pytest.raises(WorkerError) as ei:
        assert_review_bound(review, proposal=proposal, bundle=bundle)
    # Draft 2020-12 conditional schema rejects PASS with non-empty findings.
    assert ei.value.code in {"SI2-REVIEW-FINDINGS", "SCHEMA_INVALID"}


def test_self_review(tmp_path: Path):
    _repo, _db, proposal, bundle = _exec(tmp_path)
    review = build_pass_review(bundle, proposal)
    review["reviewer_id"] = review["implementer_id"]
    with pytest.raises(WorkerError) as ei:
        assert_review_bound(review, proposal=proposal, bundle=bundle)
    assert ei.value.code == "SI2-REVIEW-SELF"
