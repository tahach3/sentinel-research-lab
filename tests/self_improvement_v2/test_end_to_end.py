from pathlib import Path

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo, run
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.finalizer import finalize
from tools.self_improvement_v2.git_worker import source_tree_fingerprint


def test_offline_v2_pilot(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    before = source_tree_fingerprint(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    assert bundle["final_state"] == "REVIEW_PENDING"
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""
    store = ExperienceStore(db)
    _bundle, wt = store.get_execution(bundle["execution_id"])
    assert Path(wt).is_dir()
    assert run(["git", "rev-parse", "--abbrev-ref", "HEAD"], Path(wt)).stdout.strip() == "HEAD"
    review = build_pass_review(bundle, proposal)
    store.insert_review(review)
    result = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert result["final_state"] == "EXPORT_PENDING"
    assert result["candidate_commit"]
    assert result["candidate_branch"] is None
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""
    assert Path(wt).is_dir()
    clone = Path(wt).resolve().parent.parent / "repo"
    export_ref = f"refs/srl/export/{bundle['execution_id']}"
    tip = run(["git", "rev-parse", export_ref], clone).stdout.strip()
    assert tip == result["candidate_commit"]
    assert store.count_learning_records() == 1
    assert source_tree_fingerprint(repo) == before
    head = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    assert head == baseline
