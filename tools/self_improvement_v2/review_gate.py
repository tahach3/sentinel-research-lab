"""Content-bound independent review gate for Self-Improvement Loop V2."""

from __future__ import annotations

from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.schema_loader import validate_instance


def assert_review_bound(
    review: dict[str, Any],
    *,
    proposal: dict[str, Any],
    bundle: dict[str, Any],
    root: Any = None,
) -> None:
    validate_instance("review_result", review, root=root)

    if review.get("proposal_id") != proposal.get("proposal_id") or review.get("proposal_id") != bundle.get(
        "proposal_id"
    ):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-PROPOSAL-HASH"],
            "review proposal_id mismatch",
            state="REVIEW_FAILED",
        )

    if review.get("proposal_sha256") != bundle.get("proposal_sha256"):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-PROPOSAL-HASH"],
            "review proposal_sha256 mismatch",
            state="REVIEW_FAILED",
        )

    if review.get("execution_id") != bundle.get("execution_id"):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-EXECUTION-ID"],
            "review execution_id mismatch",
            state="REVIEW_FAILED",
        )

    if review.get("execution_result_sha256") != bundle.get("execution_result_sha256"):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-EXECUTION-HASH"],
            "review execution_result_sha256 mismatch",
            state="REVIEW_FAILED",
        )

    if review.get("actual_diff_sha256") != bundle.get("actual_diff_sha256"):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-DIFF-HASH"],
            "review actual_diff_sha256 mismatch",
            state="REVIEW_FAILED",
        )

    if review.get("worktree_tree_sha") != bundle.get("worktree_tree_sha"):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-TREE-HASH"],
            "review worktree_tree_sha mismatch",
            state="REVIEW_FAILED",
        )

    if review.get("validation_results_sha256") != bundle.get("validation_results_sha256"):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-VALIDATION-HASH"],
            "review validation_results_sha256 mismatch",
            state="REVIEW_FAILED",
        )

    risk_keys = (
        "declared_risk",
        "computed_risk_pre",
        "effective_risk_pre",
        "computed_risk_post",
        "effective_risk_post",
        "risk_reason_codes_pre",
        "risk_reason_codes_post",
        "policy_sha256",
        "risk_classifier_version",
    )
    for key in risk_keys:
        if review.get(key) != bundle.get(key):
            raise WorkerError(
                ERROR_CODES["SI2-REVIEW-RISK-BINDING"],
                f"review risk binding mismatch: {key}",
                state="REVIEW_FAILED",
            )

    implementer = proposal.get("implementer_id") or review.get("implementer_id")
    reviewer = review.get("reviewer_id")
    if not reviewer:
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-MISSING"],
            "missing reviewer_id",
            state="REVIEW_FAILED",
        )
    if review.get("independent_from_implementer") is not True:
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-SELF"],
            "review is not independent",
            state="REVIEW_FAILED",
        )
    if reviewer == implementer:
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-SELF"],
            "reviewer_id matches implementer_id",
            state="REVIEW_FAILED",
        )

    if review.get("verdict") == "FINITE_REPAIR":
        attempt = int(proposal.get("repair_attempt") or 0)
        if attempt >= 1:
            raise WorkerError(
                ERROR_CODES["REPAIR_LIMIT_REACHED"],
                "repair limit reached",
                state="REPAIR_LIMIT_REACHED",
            )
        raise WorkerError(
            ERROR_CODES["REVIEW_FAILED"],
            "FINITE_REPAIR requested",
            state="REVIEW_FAILED",
        )

    if review.get("verdict") != "PASS":
        raise WorkerError(
            ERROR_CODES["REVIEW_FAILED"],
            f"verdict is {review.get('verdict')}",
            state="REVIEW_FAILED",
        )
    for field in ("contract_alignment", "allowed_path_compliance", "acceptance_results"):
        if review.get(field) != "PASS":
            raise WorkerError(
                ERROR_CODES["REVIEW_FAILED"],
                f"{field} is not PASS",
                state="REVIEW_FAILED",
            )
    if review.get("security_findings"):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-FINDINGS"],
            "security_findings must be empty for PASS",
            state="REVIEW_FAILED",
        )
    if review.get("architecture_findings"):
        raise WorkerError(
            ERROR_CODES["SI2-REVIEW-FINDINGS"],
            "architecture_findings must be empty for PASS",
            state="REVIEW_FAILED",
        )


def assert_no_conflicting_review(
    existing_reviews: list[dict[str, Any]],
    new_review: dict[str, Any],
) -> None:
    for old in existing_reviews:
        if old.get("review_id") == new_review.get("review_id"):
            continue
        # Another review for same execution with different binding/verdict
        if old.get("execution_id") == new_review.get("execution_id"):
            if old.get("verdict") == "PASS" and new_review.get("verdict") == "PASS":
                if old.get("review_id") != new_review.get("review_id"):
                    # Allow identical content only
                    keys = (
                        "proposal_sha256",
                        "execution_result_sha256",
                        "actual_diff_sha256",
                        "worktree_tree_sha",
                        "validation_results_sha256",
                    )
                    if any(old.get(k) != new_review.get(k) for k in keys):
                        raise WorkerError(
                            ERROR_CODES["SI2-REVIEW-CONFLICT"],
                            "duplicate conflicting review",
                            state="REVIEW_FAILED",
                        )
