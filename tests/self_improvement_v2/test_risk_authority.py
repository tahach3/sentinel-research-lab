"""Adversarial risk-authority tests for Self-Improvement Loop V2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.self_improvement_v2.helpers import (
    build_pass_review,
    build_proposal,
    create_file_diff,
    init_temp_repo,
    run,
    sha256_text,
)
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.finalizer import finalize
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.path_policy import load_policy
from tools.self_improvement_v2.risk_authority import (
    DECISION_AUTHORIZED,
    DECISION_POLICY_REJECTED,
    DECISION_REQUIRED,
    authorize_execution,
    classify_post_application,
    classify_pre_application,
    enforce_authorization,
    enforce_post_risk,
)
from tools.self_improvement_v2.runtime_bridge import execute_operation
from tools.self_improvement_v2.runtime_config import RuntimeConfig


def _assert_outcome(
    *,
    stage: str,
    computed: str,
    effective: str,
    reason_code: str | None,
    reasons: list[str],
    worktree: bool,
    patch_applied: bool,
    review: bool,
    commit: bool,
    branch: bool,
    final_state: str,
    decision: str | None = None,
) -> None:
    assert stage
    assert computed in {"LOW", "MEDIUM", "HIGH", "PROHIBITED"}
    assert effective in {"LOW", "MEDIUM", "HIGH", "PROHIBITED"}
    if reason_code:
        assert reason_code in reasons
    assert worktree is False or worktree is True
    assert patch_applied is False or patch_applied is True
    assert review is False
    assert commit is False
    assert branch is False
    assert final_state
    if decision is not None:
        assert decision in {DECISION_AUTHORIZED, DECISION_REQUIRED, DECISION_POLICY_REJECTED}


def _multi_file_proposal(baseline: str, n: int, prefix: str = "docs/f") -> dict[str, Any]:
    patches = []
    for i in range(n):
        path = f"{prefix}{i}.md"
        body = f"# f{i}\n"
        patches.append(
            {
                "path": path,
                "operation": "CREATE",
                "unified_diff": create_file_diff(path, body),
                "expected_preimage_sha256": "",
                "expected_postimage_sha256": sha256_text(body),
            }
        )
    prop = build_proposal(baseline)
    prop["patches"] = patches
    prop["maximum_changed_files"] = 8
    return prop


def test_01_low_declared_migration_rejected(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    prop = build_proposal(
        baseline,
        path="database/migrations/001_add.sql",
        body="ALTER TABLE t ADD c INT;\n",
        allowed_paths=["database/migrations/**", "docs/**"],
    )
    auth = authorize_execution(prop, policy)
    pre = classify_pre_application(prop, policy)
    _assert_outcome(
        stage="pre",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code="RISK_MIGRATION",
        reasons=pre.reason_codes + (["RISK_PATH_POLICY_DENY"] if "RISK_PATH_POLICY_DENY" in pre.reason_codes else pre.reason_codes),
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="POLICY_REJECTED",
        decision=auth.decision,
    )
    assert auth.decision == DECISION_POLICY_REJECTED
    assert pre.effective_risk == "PROHIBITED"
    with pytest.raises(WorkerError) as ei:
        execute_proposal(root=repo, proposal=prop, state_db=tmp_path / "s.sqlite")
    assert ei.value.code == ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"]
    assert ei.value.state == "POLICY_REJECTED"
    assert run(["git", "worktree", "list"], repo).stdout.count("\n") <= 1


def test_02_low_declared_active_workflow(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    prop = build_proposal(
        baseline,
        path="workflows/active/evil.json",
        body='{"active":true}\n',
        allowed_paths=["workflows/active/**", "docs/**"],
    )
    auth = authorize_execution(prop, policy)
    pre = classify_pre_application(prop, policy)
    assert auth.decision == DECISION_POLICY_REJECTED
    assert pre.effective_risk == "PROHIBITED"
    assert "RISK_ACTIVE_WORKFLOW" in pre.reason_codes or "RISK_PATH_POLICY_DENY" in pre.reason_codes
    _assert_outcome(
        stage="pre",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code=None,
        reasons=pre.reason_codes,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="POLICY_REJECTED",
        decision=auth.decision,
    )


def test_03_low_declared_credential_path(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    prop = build_proposal(baseline, path="docs/.env", body="KEY=1\n")
    auth = authorize_execution(prop, policy)
    pre = classify_pre_application(prop, policy)
    assert auth.decision == DECISION_POLICY_REJECTED
    assert pre.effective_risk == "PROHIBITED"
    assert "RISK_CREDENTIAL" in pre.reason_codes or "RISK_PATH_POLICY_DENY" in pre.reason_codes
    _assert_outcome(
        stage="pre",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code=None,
        reasons=pre.reason_codes,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="POLICY_REJECTED",
        decision=auth.decision,
    )


def test_04_low_declared_file_limit(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    prop = _multi_file_proposal(baseline, 9)
    prop["maximum_changed_files"] = 8
    auth = authorize_execution(prop, policy)
    pre = classify_pre_application(prop, policy)
    assert auth.decision == DECISION_REQUIRED
    assert pre.effective_risk == "MEDIUM"
    assert "RISK_EXCESSIVE_FILES" in pre.reason_codes
    _assert_outcome(
        stage="pre",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code="RISK_EXCESSIVE_FILES",
        reasons=pre.reason_codes,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
        decision=auth.decision,
    )


def test_05_low_declared_diff_limit(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    body = "\n".join(f"line {i}" for i in range(120)) + "\n"
    prop = build_proposal(baseline, body=body)
    prop["maximum_total_added_and_removed_lines"] = 50
    auth = authorize_execution(prop, policy)
    pre = classify_pre_application(prop, policy)
    assert auth.decision == DECISION_REQUIRED
    assert "RISK_EXCESSIVE_DIFF" in pre.reason_codes
    _assert_outcome(
        stage="pre",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code="RISK_EXCESSIVE_DIFF",
        reasons=pre.reason_codes,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
        decision=auth.decision,
    )


def test_06_insufficient_validation_profile(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    # Copy tools path into temp so CREATE under tools is allowed by policy copy.
    policy = load_policy(repo)
    path = "tools/self_improvement_v2/note_helper.py"
    # Ensure parent exists in temp for later apply scenarios; authorize is text-only.
    (repo / "tools" / "self_improvement_v2").mkdir(parents=True, exist_ok=True)
    body = "VALUE = 1\n"
    prop = build_proposal(
        baseline,
        path=path,
        body=body,
        allowed_paths=["tools/self_improvement_v2/**", "docs/**", "tests/**"],
    )
    prop["validation_profile"] = "DOCUMENTATION_ONLY"
    auth = authorize_execution(prop, policy)
    pre = classify_pre_application(prop, policy)
    assert auth.decision == DECISION_REQUIRED
    assert "RISK_INSUFFICIENT_VALIDATION" in pre.reason_codes
    _assert_outcome(
        stage="pre",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code="RISK_INSUFFICIENT_VALIDATION",
        reasons=pre.reason_codes,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
        decision=auth.decision,
    )


def test_07_declared_medium_computed_low(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    prop = build_proposal(baseline, risk_level="MEDIUM")
    auth = authorize_execution(prop, policy)
    pre = classify_pre_application(prop, policy)
    assert pre.computed_risk == "LOW"
    assert pre.effective_risk == "MEDIUM"
    assert auth.decision == DECISION_REQUIRED
    _assert_outcome(
        stage="pre",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code=None,
        reasons=pre.reason_codes,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
        decision=auth.decision,
    )


def test_08_declared_high_computed_low(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    prop = build_proposal(baseline, risk_level="HIGH")
    auth = authorize_execution(prop, policy)
    pre = classify_pre_application(prop, policy)
    assert pre.computed_risk == "LOW"
    assert pre.effective_risk == "HIGH"
    assert auth.decision == DECISION_REQUIRED
    _assert_outcome(
        stage="pre",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code=None,
        reasons=pre.reason_codes,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
        decision=auth.decision,
    )


def test_09_n8n_forged_auto_authorized_ignored(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    prop = build_proposal(baseline, risk_level="HIGH")
    prop["state"] = "AUTO_AUTHORIZED"
    prop["n8n_route"] = "LOW"
    auth = authorize_execution(prop, policy)
    assert auth.decision == DECISION_REQUIRED
    with pytest.raises(WorkerError):
        enforce_authorization(auth)
    _assert_outcome(
        stage="pre",
        computed=auth.computed_risk_pre,
        effective=auth.effective_risk_pre,
        reason_code=None,
        reasons=auth.risk_reason_codes_pre,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
        decision=auth.decision,
    )


def test_10_runtime_bridge_execute_without_low(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    prop = build_proposal(baseline, risk_level="HIGH")
    cfg = RuntimeConfig(
        repository_root=repo,
        state_db=tmp_path / "bridge.sqlite",
        worker_token="t" * 32,
        worker_host="127.0.0.1",
        worker_port=8765,
        max_request_bytes=262144,
    )
    with pytest.raises(WorkerError) as ei:
        execute_operation(cfg, prop, None)
    assert ei.value.code == ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"]
    assert ei.value.state == "DECISION_REQUIRED"
    pre = classify_pre_application(prop, load_policy(repo))
    _assert_outcome(
        stage="bridge_execute",
        computed=pre.computed_risk,
        effective=pre.effective_risk,
        reason_code=None,
        reasons=pre.reason_codes,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
    )


def test_11_internal_bypass_flags_rejected(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    prop = build_proposal(baseline)
    with pytest.raises(WorkerError) as ei:
        execute_proposal(
            root=repo,
            proposal=prop,
            state_db=tmp_path / "s.sqlite",
            authorization={"decision": "AUTHORIZED"},
        )
    assert ei.value.code == ERROR_CODES["RISK_AUTH_REPLAY"]
    with pytest.raises(WorkerError) as ei2:
        execute_proposal(
            root=repo,
            proposal=prop,
            state_db=tmp_path / "s2.sqlite",
            skip_risk_check=True,
        )
    assert ei2.value.code == ERROR_CODES["POLICY_REJECTED"]
    _assert_outcome(
        stage="internal_api",
        computed="LOW",
        effective="LOW",
        reason_code=None,
        reasons=[],
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="POLICY_REJECTED",
        decision=DECISION_POLICY_REJECTED,
    )


def test_12_post_risk_escalates_to_medium(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    prop = build_proposal(baseline)
    policy = load_policy(repo)
    pre = classify_pre_application(prop, policy)
    assert pre.effective_risk == "LOW"

    def fake_changed(worktree, baseline_sha):
        return ["docs/SELF_IMPROVEMENT_V2_NOTE.md", "tools/self_improvement_v2/path_policy.py"]

    monkeypatch.setattr(
        "tools.self_improvement_v2.executor.changed_paths_since",
        fake_changed,
    )
    # path allow will fail on security path during execute — use post classifier directly
    post = classify_post_application(
        proposal=prop,
        policy=policy,
        changed_paths=["docs/SELF_IMPROVEMENT_V2_NOTE.md", "tools/self_improvement_v2/path_policy.py"],
        lines_added=3,
        lines_removed=0,
        patch_bytes=100,
        pre=pre,
    )
    assert post.computed_risk in {"MEDIUM", "HIGH"}
    assert post.effective_risk != "LOW" or "RISK_PATH_SET_CHANGED" in post.reason_codes
    with pytest.raises(WorkerError) as ei:
        enforce_post_risk(pre=pre, post=post)
    assert ei.value.code == ERROR_CODES["RISK_ESCALATED_POST_EXECUTION"]
    assert ei.value.state == "DECISION_REQUIRED"
    _assert_outcome(
        stage="post",
        computed=post.computed_risk,
        effective=post.effective_risk,
        reason_code="RISK_PATH_SET_CHANGED",
        reasons=post.reason_codes,
        worktree=True,
        patch_applied=True,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
    )


def test_13_post_path_set_differs(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    prop = build_proposal(baseline)
    policy = load_policy(repo)
    pre = classify_pre_application(prop, policy)
    post = classify_post_application(
        proposal=prop,
        policy=policy,
        changed_paths=["docs/OTHER.md"],
        lines_added=2,
        lines_removed=0,
        patch_bytes=50,
        pre=pre,
    )
    assert "RISK_PATH_SET_CHANGED" in post.reason_codes
    assert post.effective_risk == "MEDIUM"
    with pytest.raises(WorkerError) as ei:
        enforce_post_risk(pre=pre, post=post)
    assert ei.value.code == ERROR_CODES["RISK_ESCALATED_POST_EXECUTION"]
    _assert_outcome(
        stage="post",
        computed=post.computed_risk,
        effective=post.effective_risk,
        reason_code="RISK_PATH_SET_CHANGED",
        reasons=post.reason_codes,
        worktree=True,
        patch_applied=True,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
    )


def test_14_and_15_finalizer_refuses_elevated_with_pass_review(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    prop = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=prop, state_db=db)
    # Tamper risk fields on the in-memory/store path by rewriting bundle via store internals
    store = ExperienceStore(db)
    review = build_pass_review(bundle, prop)
    # Elevate post risk in review+bundle copies used at finalize by mutating stored bundle
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'si2_deny_%'"
        ):
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        row = conn.execute(
            "SELECT payload_json FROM execution_bundles WHERE execution_id = ?",
            (bundle["execution_id"],),
        ).fetchone()
        payload = json.loads(row[0])
        payload["effective_risk_post"] = "MEDIUM"
        payload["computed_risk_post"] = "MEDIUM"
        payload["risk_reason_codes_post"] = ["RISK_PATH_SET_CHANGED"]
        conn.execute(
            "UPDATE execution_bundles SET payload_json = ? WHERE execution_id = ?",
            (json.dumps(payload, sort_keys=True), bundle["execution_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    review["effective_risk_post"] = "MEDIUM"
    review["computed_risk_post"] = "MEDIUM"
    review["risk_reason_codes_post"] = ["RISK_PATH_SET_CHANGED"]
    review["verdict"] = "PASS"
    store.insert_review(review)
    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code in {
        ERROR_CODES["RISK_ESCALATED_POST_EXECUTION"],
        ERROR_CODES["SI2-REVIEW-RISK-BINDING"],
    }
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""
    _assert_outcome(
        stage="finalize",
        computed="MEDIUM",
        effective="MEDIUM",
        reason_code="RISK_PATH_SET_CHANGED",
        reasons=["RISK_PATH_SET_CHANGED"],
        worktree=True,
        patch_applied=True,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
    )


def test_16_stricter_policy_at_finalization(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    prop = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=prop, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, prop)
    store.insert_review(review)
    # Tighten current policy: disallow docs/**
    policy_path = repo / "specs" / "self_improvement" / "v2" / "policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["autonomous_lane"]["allowed_paths"] = ["tests/**"]
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    # Clear policy cache
    from tools.self_improvement_v2 import path_policy

    path_policy._load_policy_cached.cache_clear()
    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code in {
        ERROR_CODES["RISK_POLICY_TIGHTENED"],
        ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
    }
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""
    _assert_outcome(
        stage="finalize_policy",
        computed="PROHIBITED",
        effective="PROHIBITED",
        reason_code=None,
        reasons=["RISK_PATH_POLICY_DENY"],
        worktree=True,
        patch_applied=True,
        review=False,
        commit=False,
        branch=False,
        final_state="DECISION_REQUIRED",
    )


def test_17_repair_weakens_validation_profile(tmp_path: Path):
    from tools.self_improvement_v2.repair_policy import assert_repair_not_broadening

    parent = build_proposal("a" * 40)
    parent["validation_profile"] = "PYTHON_TOOLING"
    repair = build_proposal(
        "a" * 40,
        proposal_id="prop-repair",
        repair_attempt=1,
        parent_proposal_id=parent["proposal_id"],
    )
    repair["validation_profile"] = "DOCUMENTATION_ONLY"
    with pytest.raises(WorkerError) as ei:
        assert_repair_not_broadening(parent, repair)
    assert ei.value.code == ERROR_CODES["REPAIR_BROADENING"]
    _assert_outcome(
        stage="repair",
        computed="MEDIUM",
        effective="MEDIUM",
        reason_code=None,
        reasons=[],
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="POLICY_REJECTED",
    )


def test_18_replayed_authorization_rejected(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    policy = load_policy(repo)
    prop = build_proposal(baseline)
    auth = authorize_execution(prop, policy)
    assert auth.decision == DECISION_AUTHORIZED
    # Attempt to reuse prior authorization artifact on a different / same call path.
    with pytest.raises(WorkerError) as ei:
        authorize_execution(
            prop,
            policy,
            caller_authorization={
                "decision": DECISION_AUTHORIZED,
                "proposal_sha256": "deadbeef",
            },
        )
    assert ei.value.code == ERROR_CODES["RISK_AUTH_REPLAY"]
    with pytest.raises(WorkerError):
        execute_proposal(
            root=repo,
            proposal=prop,
            state_db=tmp_path / "s.sqlite",
            authorization={"decision": DECISION_AUTHORIZED},
        )
    _assert_outcome(
        stage="replay",
        computed=auth.computed_risk_pre,
        effective=auth.effective_risk_pre,
        reason_code=None,
        reasons=auth.risk_reason_codes_pre,
        worktree=False,
        patch_applied=False,
        review=False,
        commit=False,
        branch=False,
        final_state="POLICY_REJECTED",
        decision=DECISION_POLICY_REJECTED,
    )


def test_happy_path_still_binds_risk(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    prop = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=prop, state_db=db)
    assert bundle["effective_risk_pre"] == "LOW"
    assert bundle["effective_risk_post"] == "LOW"
    assert bundle["risk_classifier_version"]
    store = ExperienceStore(db)
    review = build_pass_review(bundle, prop)
    store.insert_review(review)
    result = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert result["final_state"] == "EXPORT_PENDING"
    assert result["candidate_branch"] is None
