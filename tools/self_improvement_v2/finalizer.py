"""Finalization from immutable snapshots only — no patch reload/reapply."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.git_worker import (
    assert_source_unchanged,
    branch_name_for,
    create_branch_at_commit,
    create_local_commit,
    remove_worktree,
    resolve_repo_root,
    run_git,
    source_tree_fingerprint,
    worktree_head,
)
from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement_v2.patch_validator import (
    actual_diff_sha256,
    changed_paths_sha256,
    changed_paths_since,
    staged_tree_sha,
)
from tools.self_improvement_v2.path_policy import load_policy, policy_sha256
from tools.self_improvement_v2.review_gate import assert_review_bound
from tools.self_improvement_v2.risk_authority import assert_finalize_risk_bindings
from tools.self_improvement_v2.schema_loader import validate_instance


def finalize(
    *,
    execution_id: str,
    review_id: str,
    state_db: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Finalize using only execution_id / review_id / state_db / repository_root."""
    store = ExperienceStore(state_db)
    existing = store.get_finalization(execution_id)
    if existing is not None:
        if existing.get("review_id") != review_id:
            raise WorkerError(
                ERROR_CODES["SI2-REVIEW-CONFLICT"],
                "conflicting second review",
                state="REVIEW_FAILED",
            )
        return existing

    bundle, worktree_path = store.get_execution(execution_id)
    review = store.get_review(review_id)
    proposal, stored_proposal_hash = store.get_proposal_snapshot(bundle["proposal_id"])

    # Independently re-canonicalize the immutable proposal snapshot and recompute SHA-256.
    # Do not trust proposal_id alone, stored hash alone, review hash alone, or bundle hash alone.
    recomputed_proposal_hash = content_sha256(proposal)
    if (
        recomputed_proposal_hash != stored_proposal_hash
        or recomputed_proposal_hash != bundle.get("proposal_sha256")
        or recomputed_proposal_hash != review.get("proposal_sha256")
        or stored_proposal_hash != bundle.get("proposal_sha256")
        or stored_proposal_hash != review.get("proposal_sha256")
    ):
        raise WorkerError(
            ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"],
            "canonical proposal hash mismatch at finalization",
            state="FAILED_FROZEN",
        )

    # Bind review to frozen bundle (not a mutable proposal file).
    assert_review_bound(review, proposal=proposal, bundle=bundle, root=repository_root)

    # Risk authority recheck — refuses elevated/mismatched risk regardless of review verdict.
    current_policy = load_policy(repository_root)
    current_pol_sha = policy_sha256(repository_root)
    assert_finalize_risk_bindings(
        bundle,
        proposal=proposal,
        current_policy=current_policy,
        current_policy_sha256=current_pol_sha,
    )

    store.append_state_event("execution", execution_id, "REVIEW_PENDING", "REVIEW_BOUND")

    repo = resolve_repo_root(repository_root)
    before_fp = source_tree_fingerprint(repo)
    worktree = Path(worktree_path)
    if not worktree.is_dir():
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            "frozen worktree missing",
            state="CONTENT_BINDING_MISMATCH",
        )

    # Worktree must still be detached at baseline (no premature commit).
    abbrev = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree, check=True).stdout.decode().strip()
    if abbrev != "HEAD":
        raise WorkerError(
            ERROR_CODES["BRANCH_BEFORE_REVIEW"],
            "branch present before finalization commit",
            state="FAILED_FROZEN",
        )
    head = worktree_head(worktree)
    if head != bundle["baseline_sha"]:
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            "worktree HEAD left baseline before commit",
            state="CONTENT_BINDING_MISMATCH",
        )

    # Recompute bindings from frozen worktree — never reload/reapply patches.
    try:
        tree = staged_tree_sha(worktree)
        diff_hash = actual_diff_sha256(worktree, bundle["baseline_sha"])
        paths = changed_paths_since(worktree, bundle["baseline_sha"])
        paths_hash = changed_paths_sha256(paths)
        val_hash = content_sha256(bundle.get("validation_results") or [])
    except WorkerError as exc:
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            f"recompute failed: {exc.message}",
            state="CONTENT_BINDING_MISMATCH",
        ) from exc

    if (
        tree != bundle["worktree_tree_sha"]
        or diff_hash != bundle["actual_diff_sha256"]
        or paths_hash != bundle["changed_paths_sha256"]
        or sorted(paths) != sorted(bundle.get("changed_paths") or [])
        or val_hash != bundle["validation_results_sha256"]
        or tree != review["worktree_tree_sha"]
        or diff_hash != review["actual_diff_sha256"]
        or val_hash != review["validation_results_sha256"]
    ):
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            "binding recomputation mismatch",
            state="CONTENT_BINDING_MISMATCH",
        )

    store.append_state_event("execution", execution_id, "REVIEW_BOUND", "FINALIZATION_REVALIDATED")

    commit = create_local_commit(worktree, proposal["objective"])
    committed_tree = run_git(["rev-parse", "HEAD^{tree}"], cwd=worktree, check=True).stdout.decode().strip()
    if committed_tree != bundle["worktree_tree_sha"]:
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            "committed tree != reviewed tree",
            state="CONTENT_BINDING_MISMATCH",
        )

    branch = branch_name_for(proposal["candidate_id"], execution_id)
    create_branch_at_commit(repo, branch, commit)
    store.append_state_event("execution", execution_id, "FINALIZATION_REVALIDATED", "CANDIDATE_COMMITTED")

    learning = {
        "schema_version": SCHEMA_VERSION,
        "learning_id": f"learn-{execution_id[:16]}",
        "candidate_id": proposal["candidate_id"],
        "proposal_id": proposal["proposal_id"],
        "execution_id": execution_id,
        "proposal_sha256": bundle["proposal_sha256"],
        "execution_result_sha256": bundle["execution_result_sha256"],
        "problem": proposal["objective"],
        "research_summary": "Offline V2 research validation completed",
        "implementation_summary": f"Frozen execution {execution_id} committed",
        "validation_summary": f"Profile {bundle['validation_profile']} bound",
        "review_findings": [],
        "repair_attempts": int(proposal.get("repair_attempt") or 0),
        "final_outcome": "READY_FOR_HUMAN_PROMOTION",
        "reusable_patterns": ["content-bound-finalize"],
        "failure_patterns": [],
        "confidence": 0.8,
        "promotion_status": "READY_FOR_HUMAN_PROMOTION",
    }
    validate_instance("learning_record", learning, root=repository_root)
    store.insert_learning(learning)
    store.append_state_event("execution", execution_id, "CANDIDATE_COMMITTED", "LEARNING_RECORDED")

    result = {
        "schema_version": SCHEMA_VERSION,
        "execution_id": execution_id,
        "review_id": review_id,
        "binding_verified": True,
        "candidate_commit": commit,
        "candidate_branch": branch,
        "committed_tree_sha": committed_tree,
        "committed_diff_sha256": bundle["actual_diff_sha256"],
        "final_state": "READY_FOR_HUMAN_PROMOTION",
        "error_codes": [],
        "learning_record_id": learning["learning_id"],
    }
    validate_instance("finalization_result", result, root=repository_root)
    store.insert_finalization(result)
    store.append_state_event(
        "execution",
        execution_id,
        "LEARNING_RECORDED",
        "READY_FOR_HUMAN_PROMOTION",
    )

    remove_worktree(repo, worktree)
    assert_source_unchanged(repo, before_fp)
    return result


def finalize_or_freeze(**kwargs: Any) -> dict[str, Any]:
    try:
        return finalize(**kwargs)
    except WorkerError as exc:
        freeze_codes = {
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"],
            ERROR_CODES["FAILED_FROZEN"],
        }
        if exc.code in freeze_codes or exc.state in {"CONTENT_BINDING_MISMATCH", "FAILED_FROZEN"}:
            store = ExperienceStore(kwargs["state_db"])
            primary = (
                ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
                if exc.code == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
                else ERROR_CODES["CONTENT_BINDING_MISMATCH"]
            )
            result = {
                "schema_version": SCHEMA_VERSION,
                "execution_id": kwargs["execution_id"],
                "review_id": kwargs["review_id"],
                "binding_verified": False,
                "candidate_commit": None,
                "candidate_branch": None,
                "committed_tree_sha": None,
                "committed_diff_sha256": None,
                "final_state": "FAILED_FROZEN",
                "error_codes": [primary, ERROR_CODES["CONTENT_BINDING_MISMATCH"], ERROR_CODES["FAILED_FROZEN"]]
                if primary == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
                else [ERROR_CODES["CONTENT_BINDING_MISMATCH"], ERROR_CODES["FAILED_FROZEN"]],
                "learning_record_id": None,
            }
            try:
                store.insert_finalization(result)
                store.append_state_event(
                    "execution",
                    kwargs["execution_id"],
                    None,
                    "FAILED_FROZEN",
                    primary,
                )
            except WorkerError:
                pass
            raise WorkerError(
                primary,
                exc.message,
                state="FAILED_FROZEN",
            ) from exc
        raise
