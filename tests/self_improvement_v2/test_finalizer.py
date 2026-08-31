"""Finalization binding tests — proposal hash recomputation and freeze on mismatch."""

from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo, run
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.finalizer import finalize, finalize_or_freeze
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError


def _ready(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, proposal)
    store.insert_review(review)
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""
    return repo, db, proposal, bundle, review, store


def _drop_immutability_triggers(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'si2_deny_%'"
        ).fetchall()
        for (name,) in rows:
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        conn.commit()
    finally:
        conn.close()


def test_finalize_happy_path(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    result = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert result["final_state"] == "EXPORT_PENDING"
    assert result["candidate_commit"]
    assert result["candidate_branch"] is None
    assert result["committed_tree_sha"] == bundle["worktree_tree_sha"]
    again = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert again["candidate_commit"] == result["candidate_commit"]


def test_altered_worktree_fails(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    wt = Path(store.get_execution(bundle["execution_id"])[1])
    (wt / "docs" / "EXTRA.md").write_text("nope\n", encoding="utf-8")
    with pytest.raises(WorkerError) as ei:
        finalize_or_freeze(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == "CONTENT_BINDING_MISMATCH"
    assert ei.value.state == "FAILED_FROZEN"
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_v1_stale_review_pwned_exploit(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
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
    assert not (repo / "docs" / "PWNED.md").exists()
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_conflicting_second_review(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    result = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    assert result["candidate_commit"]
    other = dict(review)
    other["review_id"] = "rev-other"
    store.insert_review(other)
    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=other["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == "SI2-REVIEW-CONFLICT"


def test_finalizer_signature_no_patch_args():
    sig = inspect.signature(finalize)
    assert "proposal" not in sig.parameters
    assert "patches" not in sig.parameters
    assert set(sig.parameters) >= {"execution_id", "review_id", "state_db", "repository_root"}


def test_sqlite_mutation_proposal_payload_blocks_commit(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    _drop_immutability_triggers(db)
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT payload_json FROM proposal_snapshots WHERE proposal_id = ?",
            (bundle["proposal_id"],),
        ).fetchone()
        payload = json.loads(row[0])
        payload["objective"] = "MUTATED OBJECTIVE"
        conn.execute(
            "UPDATE proposal_snapshots SET payload_json = ? WHERE proposal_id = ?",
            (json.dumps(payload, sort_keys=True), bundle["proposal_id"]),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
    assert ei.value.state == "FAILED_FROZEN"
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_sqlite_mutation_stored_proposal_hash_blocks_commit(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    _drop_immutability_triggers(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE proposal_snapshots SET content_sha256 = ? WHERE proposal_id = ?",
            ("a" * 64, bundle["proposal_id"]),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
    assert ei.value.state == "FAILED_FROZEN"
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_sqlite_mutation_execution_proposal_hash_blocks_commit(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    _drop_immutability_triggers(db)
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT payload_json FROM execution_bundles WHERE execution_id = ?",
            (bundle["execution_id"],),
        ).fetchone()
        payload = json.loads(row[0])
        payload["proposal_sha256"] = "b" * 64
        conn.execute(
            "UPDATE execution_bundles SET payload_json = ?, proposal_sha256 = ? WHERE execution_id = ?",
            (json.dumps(payload, sort_keys=True), "b" * 64, bundle["execution_id"]),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
    assert ei.value.state == "FAILED_FROZEN"
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_sqlite_mutation_review_proposal_hash_blocks_commit(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    _drop_immutability_triggers(db)
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT payload_json FROM review_snapshots WHERE review_id = ?",
            (review["review_id"],),
        ).fetchone()
        payload = json.loads(row[0])
        payload["proposal_sha256"] = "c" * 64
        conn.execute(
            "UPDATE review_snapshots SET payload_json = ? WHERE review_id = ?",
            (json.dumps(payload, sort_keys=True), review["review_id"]),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(WorkerError) as ei:
        finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
        )
    assert ei.value.code == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
    assert ei.value.state == "FAILED_FROZEN"
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_worktree_path_stored_as_runtime_token(tmp_path: Path):
    repo, db, proposal, bundle, review, store = _ready(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT worktree_path FROM execution_bundles WHERE execution_id = ?",
            (bundle["execution_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row[0].startswith("runtime:")
    assert ":" not in row[0][8:] or not Path(row[0]).is_absolute()
    # Resolver still returns a usable worktree directory.
    _bundle, wt = store.get_execution(bundle["execution_id"])
    assert Path(wt).is_dir()
