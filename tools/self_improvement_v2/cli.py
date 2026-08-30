"""CLI for validate-proposal / execute / finalize / bind-review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.option_a_controller import run_rev25_production_finalize
from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement_v2.runtime_config import load_runtime_config
from tools.self_improvement_v2.path_policy import load_policy, policy_sha256
from tools.self_improvement_v2.repair_policy import assert_repair_attempt_allowed, assert_repair_not_broadening
from tools.self_improvement_v2.review_gate import assert_no_conflicting_review, assert_review_bound
from tools.self_improvement_v2.risk_authority import authorize_execution, enforce_authorization
from tools.self_improvement_v2.schema_loader import ensure_schema_version, load_json, validate_instance


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def validate_proposal_cmd(root: Path, proposal_path: Path) -> int:
    policy = load_policy(root)
    proposal = ensure_schema_version(load_json(proposal_path))
    validate_instance("proposal", proposal, root=root)
    assert_repair_attempt_allowed(int(proposal.get("repair_attempt") or 0))
    auth = authorize_execution(proposal, policy, policy_sha256=policy_sha256(root))
    enforce_authorization(auth)
    digest = content_sha256(proposal)
    print(
        json.dumps(
            {
                "status": "PASS",
                "proposal_id": proposal["proposal_id"],
                "proposal_sha256": digest,
                "policy_sha256": policy_sha256(root),
                "worker_decision": auth.decision,
                "effective_risk_pre": auth.effective_risk_pre,
            },
            sort_keys=True,
        )
    )
    return 0


def execute_cmd(root: Path, proposal_path: Path, state_db: Path, result_path: Path) -> int:
    proposal = ensure_schema_version(load_json(proposal_path))
    try:
        bundle = execute_proposal(root=root, proposal=proposal, state_db=state_db)
        _write_json(result_path, bundle)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "execution_id": bundle["execution_id"],
                    "final_state": bundle["final_state"],
                },
                sort_keys=True,
            )
        )
        return 0
    except WorkerError as exc:
        final_state = "FAILED_FROZEN" if exc.state == "REPAIR_LIMIT_REACHED" else exc.state
        errors = [exc.code]
        if exc.state == "REPAIR_LIMIT_REACHED":
            errors.append(ERROR_CODES["FAILED_FROZEN"])
            final_state = "FAILED_FROZEN"
        empty = {
            "schema_version": SCHEMA_VERSION,
            "execution_id": "none",
            "proposal_id": proposal.get("proposal_id", "unknown"),
            "proposal_sha256": "0" * 64,
            "policy_sha256": "0" * 64,
            "baseline_sha": proposal.get("baseline_sha") or ("0" * 40),
            "worktree_tree_sha": "0" * 40,
            "actual_diff_sha256": "0" * 64,
            "changed_paths": [],
            "changed_paths_sha256": "0" * 64,
            "validation_profile": proposal.get("validation_profile") or "DOCUMENTATION_ONLY",
            "validation_results": [],
            "validation_results_sha256": "0" * 64,
            "execution_result_sha256": "0" * 64,
            "final_state": final_state,
            "error_codes": errors,
            "declared_risk": proposal.get("risk_level") or "LOW",
            "computed_risk_pre": "LOW",
            "effective_risk_pre": "LOW",
            "computed_risk_post": "LOW",
            "effective_risk_post": "LOW",
            "risk_reason_codes_pre": [],
            "risk_reason_codes_post": [],
            "risk_classifier_version": "2.1.0",
        }
        _write_json(result_path, empty)
        print(json.dumps({"status": "FAIL", "error": exc.code, "final_state": final_state}, sort_keys=True))
        return 1


def bind_review_cmd(root: Path, review_path: Path, state_db: Path) -> int:
    store = ExperienceStore(state_db)
    review = ensure_schema_version(load_json(review_path))
    bundle, _wt = store.get_execution(review["execution_id"])
    proposal = store.get_proposal(bundle["proposal_id"])
    existing = store.list_reviews_for_execution(review["execution_id"])
    assert_no_conflicting_review(existing, review)
    assert_review_bound(review, proposal=proposal, bundle=bundle, root=root)
    store.insert_review(review)
    store.append_state_event("review", review["review_id"], "REVIEW_PENDING", "REVIEW_BOUND")
    print(json.dumps({"status": "PASS", "review_id": review["review_id"]}, sort_keys=True))
    return 0


def finalize_cmd(root: Path, execution_id: str, review_id: str, state_db: Path) -> int:
    try:
        config = load_runtime_config(
            repository_root=str(root),
            state_db=str(state_db),
        )
        result = run_rev25_production_finalize(
            execution_id=execution_id,
            review_id=review_id,
            state_db=config.state_db,
            repository_root=config.repository_root,
            deps=config.rev25_deps,
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "final_state": result["final_state"],
                    "candidate_commit": result["candidate_commit"],
                    "candidate_branch": result["candidate_branch"],
                },
                sort_keys=True,
            )
        )
        return 0
    except WorkerError as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": exc.code,
                    "final_state": exc.state,
                },
                sort_keys=True,
            )
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sentinel Research Lab self-improvement V2 worker")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate-proposal")
    p_val.add_argument("--root", required=True)
    p_val.add_argument("--proposal", required=True)

    p_ex = sub.add_parser("execute")
    p_ex.add_argument("--root", required=True)
    p_ex.add_argument("--proposal", required=True)
    p_ex.add_argument("--state-db", required=True)
    p_ex.add_argument("--result", required=True)

    p_br = sub.add_parser("bind-review")
    p_br.add_argument("--root", required=True)
    p_br.add_argument("--review", required=True)
    p_br.add_argument("--state-db", required=True)

    p_fin = sub.add_parser("finalize")
    p_fin.add_argument("--root", required=True)
    p_fin.add_argument("--execution-id", required=True)
    p_fin.add_argument("--review-id", required=True)
    p_fin.add_argument("--state-db", required=True)
    # Explicitly reject legacy patch-carrying finalize args if someone adds them later.
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-proposal":
            return validate_proposal_cmd(Path(args.root), Path(args.proposal))
        if args.command == "execute":
            return execute_cmd(
                Path(args.root),
                Path(args.proposal),
                Path(args.state_db),
                Path(args.result),
            )
        if args.command == "bind-review":
            return bind_review_cmd(Path(args.root), Path(args.review), Path(args.state_db))
        if args.command == "finalize":
            return finalize_cmd(
                Path(args.root),
                args.execution_id,
                args.review_id,
                Path(args.state_db),
            )
        return 2
    except WorkerError as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": exc.code, "message": str(exc)},
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
