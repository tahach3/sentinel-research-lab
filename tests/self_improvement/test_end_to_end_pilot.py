"""Deterministic offline pilot and remaining negative safety tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tests.self_improvement.helpers import (
    REAL_ROOT,
    build_pilot_proposal,
    create_file_diff,
    init_temp_repo,
    load_fixture,
    sha256_text,
    write_json,
)
from tools.self_improvement.cli import execute_cmd, finalize_cmd, main
from tools.self_improvement.models import WorkerError
from tools.self_improvement.patch_validator import enforce_diff_limits
from tools.self_improvement.policy import load_policy
from tools.self_improvement.review_gate import assert_review_pass


def test_end_to_end_offline_pilot(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    proposal = build_pilot_proposal(repo, baseline)
    prop_path = tmp_path / "proposal.json"
    write_json(prop_path, proposal)
    db = tmp_path / "runtime.sqlite"
    result_path = tmp_path / "execution_result.json"

    # Also persist candidate fixture into store via execute stub path
    code = execute_cmd(repo, prop_path, db, result_path)
    assert code == 0
    execution = json.loads(result_path.read_text(encoding="utf-8"))
    assert execution["final_state"] == "INDEPENDENT_REVIEW"
    assert execution["candidate_commit"] is None
    assert execution["baseline_verified"] is True
    assert "docs/SELF_IMPROVEMENT_NOTE.md" in execution["changed_paths"]
    assert not (repo / "docs" / "SELF_IMPROVEMENT_NOTE.md").exists()

    review = load_fixture("review_pass.json")
    review_path = tmp_path / "review.json"
    write_json(review_path, review)

    code2 = finalize_cmd(repo, result_path, review_path, db)
    assert code2 == 0
    final = json.loads(result_path.read_text(encoding="utf-8"))
    assert final["final_state"] == "READY_FOR_HUMAN_PROMOTION"
    assert final["candidate_commit"]
    assert len(final["candidate_commit"]) == 40

    # Candidate commit exists on temp repo branch tip reachable via rev-parse
    import subprocess

    show = subprocess.run(
        ["git", "cat-file", "-t", final["candidate_commit"]],
        cwd=str(repo),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    assert show.returncode == 0
    assert show.stdout.strip() == "commit"

    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM learning_records").fetchone()[0]
    conn.close()
    assert count == 1

    # Source repository HEAD unchanged (still baseline)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        shell=False,
        check=True,
    ).stdout.strip()
    assert head == baseline
    assert not (repo / "docs" / "SELF_IMPROVEMENT_NOTE.md").exists()


def test_too_many_files_and_excessive_diff() -> None:
    policy = load_policy(REAL_ROOT)
    with pytest.raises(WorkerError) as exc:
        enforce_diff_limits(
            {"files_changed": 9, "lines_added": 1, "lines_removed": 0, "patch_bytes": 10},
            policy,
        )
    assert exc.value.code == "TOO_MANY_FILES"
    with pytest.raises(WorkerError) as exc2:
        enforce_diff_limits(
            {"files_changed": 1, "lines_added": 400, "lines_removed": 200, "patch_bytes": 10},
            policy,
        )
    assert exc2.value.code == "EXCESSIVE_DIFF"


def test_migration_path_requested(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    proposal = build_pilot_proposal(repo, baseline)
    content = "SELECT 1;\n"
    proposal["patches"] = [
        {
            "path": "database/migrations/009_bad.sql",
            "operation": "CREATE",
            "unified_diff": create_file_diff("database/migrations/009_bad.sql", content),
            "expected_preimage_sha256": "",
            "expected_postimage_sha256": sha256_text(content),
        }
    ]
    proposal["allowed_paths"] = ["database/migrations/**"]
    prop_path = tmp_path / "proposal.json"
    write_json(prop_path, proposal)
    code = execute_cmd(repo, prop_path, tmp_path / "db.sqlite", tmp_path / "r.json")
    assert code == 1
    text = (tmp_path / "r.json").read_text(encoding="utf-8")
    assert "MIGRATION_PATH" in text or "POLICY_REJECTED" in text or "FORBIDDEN_PATH" in text


def test_candidate_commit_before_review_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    proposal = build_pilot_proposal(repo, baseline)
    prop_path = tmp_path / "proposal.json"
    write_json(prop_path, proposal)
    db = tmp_path / "db.sqlite"
    result_path = tmp_path / "r.json"
    assert execute_cmd(repo, prop_path, db, result_path) == 0
    execution = json.loads(result_path.read_text(encoding="utf-8"))
    execution["candidate_commit"] = "a" * 40
    write_json(result_path, execution)
    review_path = tmp_path / "review.json"
    write_json(review_path, load_fixture("review_pass.json"))
    with pytest.raises(WorkerError) as exc:
        # finalize_cmd raises before try when commit present
        finalize_cmd(repo, result_path, review_path, db)
    assert exc.value.code == "COMMIT_BEFORE_REVIEW"


def test_execute_repair_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    proposal = build_pilot_proposal(repo, baseline)
    proposal["repair_attempt"] = 2
    prop_path = tmp_path / "proposal.json"
    write_json(prop_path, proposal)
    result_path = tmp_path / "r.json"
    code = execute_cmd(repo, prop_path, tmp_path / "db.sqlite", result_path)
    assert code == 1
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["final_state"] == "FAILED_FROZEN"
    assert "REPAIR_LIMIT_REACHED" in data["error_codes"]


def test_cli_validate_proposal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    proposal = build_pilot_proposal(repo, baseline)
    prop_path = tmp_path / "proposal.json"
    write_json(prop_path, proposal)
    assert main(["validate-proposal", "--root", str(REAL_ROOT), "--proposal", str(prop_path)]) == 0


def test_postimage_mismatch_on_apply(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    baseline = init_temp_repo(repo)
    proposal = build_pilot_proposal(repo, baseline)
    proposal["patches"][0]["expected_postimage_sha256"] = "ab" * 32
    prop_path = tmp_path / "proposal.json"
    write_json(prop_path, proposal)
    result_path = tmp_path / "r.json"
    code = execute_cmd(repo, prop_path, tmp_path / "db.sqlite", result_path)
    assert code == 1
    assert "POSTIMAGE_MISMATCH" in result_path.read_text(encoding="utf-8")
