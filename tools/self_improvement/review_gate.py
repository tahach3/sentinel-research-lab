"""Independent review gate — worker must not self-issue PASS."""

from __future__ import annotations

from typing import Any

from tools.self_improvement.models import ERROR_CODES, WorkerError
from tools.self_improvement.schema_loader import validate_instance


def assert_review_pass(
    review: dict[str, Any],
    *,
    proposal: dict[str, Any],
    root: Any = None,
) -> None:
    validate_instance("review_result", review, root=root)

    if review.get("proposal_id") != proposal.get("proposal_id"):
        raise WorkerError(
            ERROR_CODES["REVIEW_FAILED"],
            "review proposal_id mismatch",
            state="REVIEW_FAILED",
        )

    implementer = proposal.get("implementer_id") or "implementer-agent"
    reviewer = review.get("reviewer_id")
    if not reviewer:
        raise WorkerError(
            ERROR_CODES["MISSING_INDEPENDENT_REVIEW"],
            "missing reviewer_id",
            state="REVIEW_FAILED",
        )
    if review.get("independent_from_implementer") is not True:
        raise WorkerError(
            ERROR_CODES["SELF_REVIEW"],
            "review is not independent",
            state="REVIEW_FAILED",
        )
    if reviewer == implementer:
        raise WorkerError(
            ERROR_CODES["SELF_REVIEW"],
            "reviewer_id matches implementer_id",
            state="REVIEW_FAILED",
        )
    declared = review.get("implementer_id")
    if declared and declared == reviewer:
        raise WorkerError(
            ERROR_CODES["SELF_REVIEW"],
            "review declares same implementer/reviewer",
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
            ERROR_CODES["REVIEW_NOT_PASS"],
            "FINITE_REPAIR requested",
            state="REVIEW_FAILED",
        )

    if review.get("verdict") != "PASS":
        raise WorkerError(
            ERROR_CODES["REVIEW_NOT_PASS"],
            f"verdict is {review.get('verdict')}",
            state="REVIEW_FAILED",
        )
    for field in ("contract_alignment", "allowed_path_compliance", "acceptance_results"):
        if review.get(field) != "PASS":
            raise WorkerError(
                ERROR_CODES["REVIEW_NOT_PASS"],
                f"{field} is not PASS",
                state="REVIEW_FAILED",
            )
    if review.get("security_findings"):
        raise WorkerError(
            ERROR_CODES["REVIEW_NOT_PASS"],
            "security_findings must be empty for PASS",
            state="REVIEW_FAILED",
        )


def repair_limit_exceeded(repair_attempt: int) -> None:
    if repair_attempt >= 1:
        raise WorkerError(
            ERROR_CODES["REPAIR_LIMIT_REACHED"],
            "maximum autonomous repair attempts exceeded",
            state="REPAIR_LIMIT_REACHED",
        )
