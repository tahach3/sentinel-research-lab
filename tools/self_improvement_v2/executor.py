"""Execute frozen proposals into detached worktrees and immutable bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.git_worker import (
    DetachedWorktree,
    assert_baseline,
    assert_clean_tree,
    assert_source_unchanged,
    new_execution_id,
    resolve_repo_root,
    source_tree_fingerprint,
)
from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement_v2.patch_validator import (
    actual_diff_sha256,
    changed_paths_sha256,
    changed_paths_since,
    enforce_diff_limits,
    git_apply,
    git_apply_check,
    staged_tree_sha,
    summarize_diff,
    validate_patch_object,
    verify_postimage,
)
from tools.self_improvement_v2.path_policy import (
    assert_path_allowed,
    load_policy,
    policy_sha256,
)
from tools.self_improvement_v2.repair_policy import assert_repair_attempt_allowed, assert_repair_not_broadening
from tools.self_improvement_v2.risk_authority import (
    authorize_execution,
    classify_post_application,
    classify_pre_application,
    enforce_authorization,
    enforce_post_risk,
    risk_fields_for_bundle,
)
from tools.self_improvement_v2.schema_loader import ensure_schema_version, validate_instance
from tools.self_improvement_v2.validation_runner import run_validation_profile


def freeze_proposal(
    store: ExperienceStore,
    proposal: dict[str, Any],
    *,
    policy: dict[str, Any],
    root: Path,
) -> str:
    proposal = ensure_schema_version(proposal)
    validate_instance("proposal", proposal, root=root)
    repair_attempt = int(proposal.get("repair_attempt") or 0)
    assert_repair_attempt_allowed(repair_attempt)
    if repair_attempt == 1:
        parent_id = proposal.get("parent_proposal_id")
        if not parent_id:
            raise WorkerError(
                ERROR_CODES["REPAIR_BROADENING"],
                "repair missing parent_proposal_id",
                state="POLICY_REJECTED",
            )
        parent = store.get_proposal(parent_id)
        assert_repair_not_broadening(parent, proposal)
    elif proposal.get("parent_proposal_id") not in (None,):
        # parent_proposal_id may be null for original
        pass

    p_sha = policy_sha256(root)
    digest = store.insert_proposal(proposal, policy_sha256=p_sha)
    store.append_state_event(
        "proposal",
        proposal["proposal_id"],
        "PROPOSAL_VALIDATED",
        "PROPOSAL_FROZEN",
    )
    return digest


def execute_proposal(
    *,
    root: Path,
    proposal: dict[str, Any],
    state_db: Path,
    candidate: dict[str, Any] | None = None,
    authorization: Any = None,
    skip_risk_check: Any = None,
) -> dict[str, Any]:
    """Execute a proposal. Risk authority is mandatory and non-bypassable."""
    if skip_risk_check is not None:
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "skip_risk_check is not permitted",
            state="POLICY_REJECTED",
        )

    policy = load_policy(root)
    store = ExperienceStore(state_db)
    proposal = ensure_schema_version(proposal)
    validate_instance("proposal", proposal, root=root)

    if candidate is None:
        candidate = {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": proposal["candidate_id"],
            "repository_id": proposal["repository_id"],
            "problem": proposal["objective"],
            "evidence": proposal.get("evidence_refs") or ["n/a"],
            "expected_benefit": "bounded improvement",
            "success_metrics": proposal.get("acceptance_criteria") or ["validation pass"],
            "risk_indicators": [],
            "source_agent": proposal.get("implementer_id") or "fixture-or-caller",
            "created_from_run": "execute",
        }
    candidate = ensure_schema_version(candidate)
    validate_instance("candidate", candidate, root=root)
    store.insert_candidate(candidate)
    store.append_state_event("candidate", candidate["candidate_id"], None, "RESEARCH_VALIDATED")

    proposal_digest = freeze_proposal(store, proposal, policy=policy, root=root)
    # Always recompute — never accept caller-supplied hash as authority.
    proposal_digest = content_sha256(proposal)
    pol_sha = policy_sha256(root)

    # Pre-authorization from patch text + policy BEFORE any worktree / apply / staging.
    auth = authorize_execution(
        proposal,
        policy,
        policy_sha256=pol_sha,
        caller_authorization=authorization,
    )
    enforce_authorization(auth)
    pre = classify_pre_application(proposal, policy)
    store.append_state_event("proposal", proposal["proposal_id"], "PROPOSAL_FROZEN", "RISK_CLASSIFIED")
    store.append_state_event("proposal", proposal["proposal_id"], "RISK_CLASSIFIED", "AUTO_AUTHORIZED")

    execution_id = new_execution_id()
    repo = resolve_repo_root(root)
    before_fp = source_tree_fingerprint(repo)
    assert_clean_tree(repo)
    assert_baseline(repo, proposal["baseline_sha"])

    wt = DetachedWorktree(repo, proposal["baseline_sha"], execution_id)
    worktree = wt.prepare()
    store.append_state_event("execution", execution_id, "AUTO_AUTHORIZED", "DETACHED_WORKTREE_PREPARED")

    try:
        for patch in proposal["patches"]:
            validate_patch_object(patch, policy=policy, proposal=proposal, repo_root=worktree)
            git_apply_check(worktree, patch["unified_diff"])
        for patch in proposal["patches"]:
            git_apply(worktree, patch["unified_diff"])
            verify_postimage(worktree, patch)

        changed = changed_paths_since(worktree, proposal["baseline_sha"])
        for path in changed:
            assert_path_allowed(path, policy, proposal, repo_root=worktree)
        summary = summarize_diff(worktree, proposal["baseline_sha"])
        enforce_diff_limits(summary, policy, proposal)

        post = classify_post_application(
            proposal=proposal,
            policy=policy,
            changed_paths=changed,
            lines_added=int(summary["lines_added"]),
            lines_removed=int(summary["lines_removed"]),
            patch_bytes=int(summary["patch_bytes"]),
            pre=pre,
        )
        enforce_post_risk(pre=pre, post=post)

        store.append_state_event("execution", execution_id, "DETACHED_WORKTREE_PREPARED", "PATCH_APPLIED")

        store.append_state_event("execution", execution_id, "PATCH_APPLIED", "VALIDATING")
        validation = run_validation_profile(
            policy=policy,
            profile_name=proposal["validation_profile"],
            cwd=worktree,
        )

        tree = staged_tree_sha(worktree)
        diff_hash = actual_diff_sha256(worktree, proposal["baseline_sha"])
        paths_hash = changed_paths_sha256(changed)
        val_hash = content_sha256(validation)
        profile_hash = content_sha256(policy["validation_profiles"][proposal["validation_profile"]])

        risk_fields = risk_fields_for_bundle(auth=auth, post=post, policy_sha256=pol_sha)
        bundle_body = {
            "schema_version": SCHEMA_VERSION,
            "execution_id": execution_id,
            "proposal_id": proposal["proposal_id"],
            "proposal_sha256": proposal_digest,
            "policy_sha256": pol_sha,
            "baseline_sha": proposal["baseline_sha"],
            "worktree_tree_sha": tree,
            "actual_diff_sha256": diff_hash,
            "changed_paths": changed,
            "changed_paths_sha256": paths_hash,
            "validation_profile": proposal["validation_profile"],
            "validation_profile_sha256": profile_hash,
            "validation_results": validation,
            "validation_results_sha256": val_hash,
            "execution_result_sha256": "",  # filled after body without this field cycle
            "worktree_path_redacted": "<redacted>",
            "candidate_id": proposal["candidate_id"],
            "repair_attempt": int(proposal.get("repair_attempt") or 0),
            "final_state": "REVIEW_PENDING",
            "error_codes": [],
            **risk_fields,
        }
        # execution_result_sha256 is hash of bundle without that field set to empty — use core fields
        core_for_hash = {k: v for k, v in bundle_body.items() if k != "execution_result_sha256"}
        bundle_body["execution_result_sha256"] = content_sha256(core_for_hash)

        validate_instance("execution_bundle", bundle_body, root=root)
        kept = wt.abandon_tmpdir_ownership()
        store.insert_execution_bundle(bundle_body, worktree_path=str(kept))
        store.append_state_event(
            "execution",
            execution_id,
            "VALIDATING",
            "EXECUTION_BUNDLE_FROZEN",
        )
        store.append_state_event(
            "execution",
            execution_id,
            "EXECUTION_BUNDLE_FROZEN",
            "REVIEW_PENDING",
        )
        assert_source_unchanged(repo, before_fp)
        return bundle_body
    except Exception:
        wt.cleanup()
        raise
