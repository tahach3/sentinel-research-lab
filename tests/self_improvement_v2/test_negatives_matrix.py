"""Required negative coverage matrix (36 cases)."""

from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.finalizer import finalize
from tools.self_improvement_v2.git_worker import run_git, source_tree_fingerprint
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.path_policy import assert_path_allowed, load_policy
from tools.self_improvement_v2.patch_parser import parse_unified_diff, reject_forbidden_patch_ops
from tools.self_improvement_v2.review_gate import assert_review_bound

POLICY = load_policy()
PROP = {"allowed_paths": ["docs/**", "tests/**"], "forbidden_paths": []}


def test_01_nested_env():
    with pytest.raises(WorkerError):
        assert_path_allowed("docs/.env", POLICY, PROP)


def test_02_nested_git():
    with pytest.raises(WorkerError):
        assert_path_allowed("docs/.git/config", POLICY, PROP)


def test_03_nested_secrets():
    with pytest.raises(WorkerError):
        assert_path_allowed("tests/secrets/x", POLICY, PROP)


def test_04_mixed_case_basename():
    with pytest.raises(WorkerError):
        assert_path_allowed("docs/.Env.Local", POLICY, PROP)


def test_05_windows_separator_traversal():
    with pytest.raises(WorkerError):
        assert_path_allowed("docs/../secrets/a", POLICY, PROP)


def test_06_quoted_git_path_unsafe():
    with pytest.raises(WorkerError):
        assert_path_allowed('docs/"x".md', POLICY, PROP)


def test_07_octal_escape_handled():
    diff = (
        'diff --git "a/docs/x.md" "b/docs/x.md"\n'
        "new file mode 100644\n"
        "--- /dev/null\n"
        '+++ "b/docs/x.md"\n'
        "@@ -0,0 +1 @@\n"
        "+x\n"
    )
    assert parse_unified_diff(diff).new_path == "docs/x.md"


def test_08_rename_bypass():
    diff = (
        "diff --git a/docs/a.md b/docs/b.md\n"
        "rename from docs/a.md\n"
        "rename to docs/b.md\n"
        "--- a/docs/a.md\n"
        "+++ b/docs/b.md\n"
        "@@ -1 +1 @@\n-a\n+b\n"
    )
    with pytest.raises(WorkerError):
        reject_forbidden_patch_ops(parse_unified_diff(diff))


def test_09_copy_bypass():
    diff = (
        "diff --git a/docs/a.md b/docs/b.md\n"
        "copy from docs/a.md\n"
        "copy to docs/b.md\n"
        "--- a/docs/a.md\n"
        "+++ b/docs/b.md\n"
        "@@ -1 +1 @@\n-a\n+b\n"
    )
    with pytest.raises(WorkerError):
        reject_forbidden_patch_ops(parse_unified_diff(diff))


def test_10_symlink():
    diff = (
        "diff --git a/docs/l b/docs/l\n"
        "new file mode 120000\n"
        "--- /dev/null\n"
        "+++ b/docs/l\n"
        "@@ -0,0 +1 @@\n+t\n"
    )
    with pytest.raises(WorkerError):
        reject_forbidden_patch_ops(parse_unified_diff(diff))


def test_11_submodule():
    diff = (
        "diff --git a/docs/s b/docs/s\n"
        "new file mode 160000\n"
        "--- /dev/null\n"
        "+++ b/docs/s\n"
        "@@ -0,0 +1 @@\n+Subproject commit abc\n"
    )
    with pytest.raises(WorkerError):
        reject_forbidden_patch_ops(parse_unified_diff(diff))


def test_12_proposal_replacement(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    altered = dict(proposal)
    altered["objective"] = "mutated"
    with pytest.raises(WorkerError) as ei:
        store.insert_proposal(altered, policy_sha256=bundle["policy_sha256"])
    assert ei.value.code == "SI2-STORE-IMMUTABILITY"


def test_13_execution_replacement(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    altered = dict(bundle)
    altered["actual_diff_sha256"] = "c" * 64
    with pytest.raises(WorkerError) as ei:
        store.insert_execution_bundle(altered, worktree_path="redacted")
    assert ei.value.code == "SI2-STORE-IMMUTABILITY"


def test_14_to_23_binding_and_git(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, proposal)
    bad = dict(review)
    bad["execution_id"] = "0" * 32
    with pytest.raises(WorkerError):
        assert_review_bound(bad, proposal=proposal, bundle=bundle)
    for field in (
        "proposal_sha256",
        "actual_diff_sha256",
        "worktree_tree_sha",
        "validation_results_sha256",
    ):
        stale = dict(review)
        stale[field] = "a" * len(stale[field])
        with pytest.raises(WorkerError):
            assert_review_bound(stale, proposal=proposal, bundle=bundle)
    findings = dict(review)
    findings["architecture_findings"] = ["x"]
    with pytest.raises(WorkerError):
        assert_review_bound(findings, proposal=proposal, bundle=bundle)
    with pytest.raises(WorkerError):
        store.get_review("missing")
    store.insert_review(review)
    wt = Path(store.get_execution(bundle["execution_id"])[1])
    (wt / "docs" / "mut.md").write_text("x\n", encoding="utf-8")
    with pytest.raises(WorkerError):
        finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert run_git(["branch", "--list", "self-improvement-v2/*"], cwd=repo, check=True).stdout.strip() == b""
    with pytest.raises(WorkerError):
        run_git(["push"], cwd=repo)
    with pytest.raises(WorkerError):
        run_git(["merge", "HEAD"], cwd=repo)


def test_24_duplicate_finalization(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, proposal)
    store.insert_review(review)
    a = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    b = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert a["candidate_commit"] == b["candidate_commit"]


def test_33_source_checkout_unchanged(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    before = source_tree_fingerprint(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, proposal)
    store.insert_review(review)
    finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert source_tree_fingerprint(repo) == before


def test_36_v1_pwned_exploit(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, proposal)
    store.insert_review(review)
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
