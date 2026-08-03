"""CLI for validate-proposal / execute / finalize."""

from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
import sys
from pathlib import Path
from typing import Any

from tools.self_improvement.experience_store import ExperienceStore
from tools.self_improvement.git_worker import (
    TemporaryWorktree,
    assert_baseline,
    assert_clean_tree,
    assert_source_unchanged,
    create_local_commit,
    resolve_repo_root,
    source_tree_fingerprint,
)
from tools.self_improvement.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement.patch_validator import (
    changed_paths_since,
    enforce_diff_limits,
    git_apply,
    git_apply_check,
    summarize_diff,
    validate_patch_object,
    verify_postimage,
)
from tools.self_improvement.policy import assert_path_allowed, classify_and_authorize, load_policy
from tools.self_improvement.review_gate import assert_review_pass
from tools.self_improvement.schema_loader import (
    ensure_schema_version,
    load_json,
    validate_instance,
)
from tools.self_improvement.validation_runner import run_validation_profile


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def empty_execution_result(proposal_id: str, state: str, errors: list[str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": proposal_id,
        "baseline_verified": False,
        "worktree_path_redacted": "none",
        "changed_paths": [],
        "patch_results": [],
        "validation_results": [],
        "diff_summary": {
            "files_changed": 0,
            "lines_added": 0,
            "lines_removed": 0,
            "patch_bytes": 0,
        },
        "candidate_commit": None,
        "final_state": state,
        "error_codes": errors,
    }


def _candidate_stub(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": proposal.get("candidate_id", "unknown"),
        "repository": "sentinel-research-lab",
        "problem": proposal.get("objective", "n/a"),
        "evidence": proposal.get("evidence_refs") or ["n/a"],
        "expected_benefit": "bounded improvement",
        "success_metrics": proposal.get("acceptance_criteria") or ["validation pass"],
        "risk_indicators": [],
        "source_agent": "fixture-or-caller",
        "created_from_run": "execute",
    }


def validate_proposal_cmd(root: Path, proposal_path: Path) -> int:
    policy = load_policy(root)
    proposal = ensure_schema_version(load_json(proposal_path))
    validate_instance("proposal", proposal, root=root)
    classify_and_authorize(proposal, policy)
    print(json.dumps({"status": "PASS", "proposal_id": proposal["proposal_id"]}, sort_keys=True))
    return 0


def execute_cmd(root: Path, proposal_path: Path, state_db: Path, result_path: Path) -> int:
    policy = load_policy(root)
    proposal = ensure_schema_version(load_json(proposal_path))
    store = ExperienceStore(state_db)
    run_id = secrets.token_hex(8)
    result = empty_execution_result(proposal.get("proposal_id", "unknown"), "CANDIDATE_RECEIVED", [])
    baseline_verified = False

    try:
        validate_instance("proposal", proposal, root=root)
        store.record_candidate(_candidate_stub(proposal), "RESEARCH_VALIDATED")
        store.record_proposal(proposal, "PROPOSAL_VALIDATED")
        store.record_transition("proposal", proposal["proposal_id"], None, "PROPOSAL_VALIDATED")

        classify_and_authorize(proposal, policy)
        store.record_transition(
            "proposal", proposal["proposal_id"], "PROPOSAL_VALIDATED", "AUTO_AUTHORIZED"
        )
        store.record_execution(
            run_id,
            empty_execution_result(proposal["proposal_id"], "AUTO_AUTHORIZED", []),
            "AUTO_AUTHORIZED",
        )

        repair_attempt = int(proposal.get("repair_attempt") or 0)
        if repair_attempt > 1:
            raise WorkerError(
                ERROR_CODES["REPAIR_LIMIT_REACHED"],
                "repair attempt exceeds limit",
                state="REPAIR_LIMIT_REACHED",
            )

        repo = resolve_repo_root(root)
        before_fp = source_tree_fingerprint(repo)
        assert_clean_tree(repo)
        assert_baseline(repo, proposal["baseline_sha"])
        baseline_verified = True

        with TemporaryWorktree(repo, proposal["baseline_sha"], proposal["candidate_id"]) as wt:
            assert wt.path is not None
            result["worktree_path_redacted"] = "<redacted>"
            result["branch_name"] = wt.branch_name
            result["baseline_verified"] = True
            result["final_state"] = "WORKTREE_PREPARED"
            store.record_transition("run", run_id, "AUTO_AUTHORIZED", "WORKTREE_PREPARED")

            patch_results = []
            for patch in proposal["patches"]:
                validate_patch_object(patch, policy=policy, proposal=proposal, repo_root=wt.path)
                git_apply_check(wt.path, patch["unified_diff"])
                patch_results.append(
                    {
                        "path": patch["path"],
                        "operation": patch["operation"],
                        "status": "APPLIED",
                        "error_code": None,
                    }
                )
            result["patch_results"] = patch_results
            result["final_state"] = "PATCH_VALIDATED"

            for patch in proposal["patches"]:
                git_apply(wt.path, patch["unified_diff"])
                verify_postimage(wt.path, patch)

            changed = changed_paths_since(wt.path, proposal["baseline_sha"])
            for path in changed:
                assert_path_allowed(path, policy, proposal)
            summary = summarize_diff(wt.path, proposal["baseline_sha"])
            enforce_diff_limits(summary, policy)
            result["changed_paths"] = changed
            result["diff_summary"] = summary
            result["final_state"] = "PATCH_APPLIED"

            result["final_state"] = "VALIDATING"
            validation = run_validation_profile(
                policy=policy,
                profile_name=proposal["validation_profile"],
                cwd=wt.path,
            )
            result["validation_results"] = validation
            store.record_validation(run_id, {"results": validation}, "PASS")

            # No candidate commit until independent review PASS in finalize.
            result["final_state"] = "INDEPENDENT_REVIEW"
            result["candidate_commit"] = None
            result["repair_attempt"] = repair_attempt
            result["candidate_id"] = proposal["candidate_id"]
            store.record_execution(run_id, result, result["final_state"])
            assert_source_unchanged(repo, before_fp)

        validate_instance("execution_result", result, root=root)
        _write_json(result_path, result)
        print(json.dumps({"status": "PASS", "final_state": result["final_state"]}, sort_keys=True))
        return 0
    except WorkerError as exc:
        if exc.state == "REPAIR_LIMIT_REACHED":
            final_state = "FAILED_FROZEN"
            errors = [ERROR_CODES["REPAIR_LIMIT_REACHED"], ERROR_CODES["FAILED_FROZEN"]]
        else:
            final_state = exc.state
            errors = [exc.code]
        result = empty_execution_result(proposal.get("proposal_id", "unknown"), final_state, errors)
        result["baseline_verified"] = baseline_verified
        try:
            store.record_execution(run_id, result, final_state, exc.code)
            store.record_transition("run", run_id, None, final_state, exc.code)
        except Exception:
            pass
        _write_json(result_path, result)
        print(
            json.dumps(
                {"status": "FAIL", "error": exc.code, "final_state": final_state},
                sort_keys=True,
            )
        )
        return 1


def finalize_cmd(
    root: Path,
    execution_result_path: Path,
    review_result_path: Path,
    state_db: Path,
) -> int:
    policy = load_policy(root)
    store = ExperienceStore(state_db)
    execution = ensure_schema_version(load_json(execution_result_path))
    review = ensure_schema_version(load_json(review_result_path))
    validate_instance("execution_result", execution, root=root)

    if execution.get("candidate_commit"):
        raise WorkerError(
            ERROR_CODES["COMMIT_BEFORE_REVIEW"],
            "candidate commit already present before finalize",
            state="REVIEW_FAILED",
        )
    if execution.get("final_state") != "INDEPENDENT_REVIEW":
        raise WorkerError(
            ERROR_CODES["REVIEW_FAILED"],
            f"execution not ready for review: {execution.get('final_state')}",
            state="REVIEW_FAILED",
        )

    proposal_id = execution["proposal_id"]
    conn = sqlite3.connect(str(state_db))
    row = conn.execute(
        "SELECT payload_json FROM implementation_proposals WHERE proposal_id = ?",
        (proposal_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise WorkerError(
            ERROR_CODES["REVIEW_FAILED"],
            "proposal missing from state db",
            state="REVIEW_FAILED",
        )
    proposal = json.loads(row[0])

    try:
        assert_review_pass(review, proposal=proposal, root=root)
        store.record_review(review, "PASS")

        repo = resolve_repo_root(root)
        before_fp = source_tree_fingerprint(repo)
        assert_clean_tree(repo)
        assert_baseline(repo, proposal["baseline_sha"])

        with TemporaryWorktree(repo, proposal["baseline_sha"], proposal["candidate_id"]) as wt:
            assert wt.path is not None
            for patch in proposal["patches"]:
                validate_patch_object(patch, policy=policy, proposal=proposal, repo_root=wt.path)
                git_apply_check(wt.path, patch["unified_diff"])
                git_apply(wt.path, patch["unified_diff"])
                verify_postimage(wt.path, patch)
            changed = changed_paths_since(wt.path, proposal["baseline_sha"])
            summary = summarize_diff(wt.path, proposal["baseline_sha"])
            enforce_diff_limits(summary, policy)
            run_validation_profile(
                policy=policy,
                profile_name=proposal["validation_profile"],
                cwd=wt.path,
            )
            commit = create_local_commit(wt.path, proposal["objective"])
            execution["candidate_commit"] = commit
            execution["changed_paths"] = changed
            execution["diff_summary"] = summary
            execution["branch_name"] = wt.branch_name
            execution["final_state"] = "CANDIDATE_COMMITTED"
            execution["worktree_path_redacted"] = "<redacted>"
            execution["error_codes"] = []

            learning = {
                "schema_version": SCHEMA_VERSION,
                "candidate_id": proposal["candidate_id"],
                "proposal_id": proposal["proposal_id"],
                "problem": proposal["objective"],
                "research_summary": "Offline fixture/research validation completed",
                "implementation_summary": f"Applied {len(proposal['patches'])} patch(es)",
                "validation_summary": f"Profile {proposal['validation_profile']} passed",
                "review_findings": list(review.get("architecture_findings") or []),
                "repair_attempts": int(proposal.get("repair_attempt") or 0),
                "final_outcome": "READY_FOR_HUMAN_PROMOTION",
                "reusable_patterns": ["bounded-docs-and-tests-patch"],
                "failure_patterns": [],
                "confidence": 0.7,
                "promotion_status": "READY_FOR_HUMAN_PROMOTION",
            }
            validate_instance("learning_record", learning, root=root)
            store.record_learning(learning, "LEARNING_RECORDED")
            execution["final_state"] = "READY_FOR_HUMAN_PROMOTION"
            store.record_execution(secrets.token_hex(8), execution, execution["final_state"])
            store.record_transition(
                "proposal",
                proposal_id,
                "INDEPENDENT_REVIEW",
                "READY_FOR_HUMAN_PROMOTION",
            )
            assert_source_unchanged(repo, before_fp)

        _write_json(execution_result_path, execution)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "final_state": execution["final_state"],
                    "candidate_commit": execution["candidate_commit"],
                },
                sort_keys=True,
            )
        )
        return 0
    except WorkerError as exc:
        if exc.state == "REPAIR_LIMIT_REACHED":
            execution["final_state"] = "FAILED_FROZEN"
            execution["error_codes"] = [
                ERROR_CODES["REPAIR_LIMIT_REACHED"],
                ERROR_CODES["FAILED_FROZEN"],
            ]
        else:
            execution["final_state"] = exc.state
            execution["error_codes"] = [exc.code]
        try:
            store.record_review(review, execution["final_state"], exc.code)
            store.record_execution(
                secrets.token_hex(8),
                execution,
                execution["final_state"],
                exc.code,
            )
        except Exception:
            pass
        _write_json(execution_result_path, execution)
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": exc.code,
                    "final_state": execution["final_state"],
                },
                sort_keys=True,
            )
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sentinel Research Lab self-improvement worker")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate-proposal")
    p_val.add_argument("--root", required=True)
    p_val.add_argument("--proposal", required=True)

    p_ex = sub.add_parser("execute")
    p_ex.add_argument("--root", required=True)
    p_ex.add_argument("--proposal", required=True)
    p_ex.add_argument("--state-db", required=True)
    p_ex.add_argument("--result", required=True)

    p_fin = sub.add_parser("finalize")
    p_fin.add_argument("--root", required=True)
    p_fin.add_argument("--execution-result", required=True)
    p_fin.add_argument("--review-result", required=True)
    p_fin.add_argument("--state-db", required=True)
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
        if args.command == "finalize":
            return finalize_cmd(
                Path(args.root),
                Path(args.execution_result),
                Path(args.review_result),
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
