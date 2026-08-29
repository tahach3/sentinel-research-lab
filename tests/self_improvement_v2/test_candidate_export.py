"""E4–E5 candidate export: copy-out, host SHA, verifier, ACK, then cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo, run
from tools.self_improvement_v2.candidate_export import (
    CandidateExportError,
    acknowledge_and_cleanup,
    copy_out_and_verify,
    write_human_promotion_artifact,
)
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.finalizer import finalize
from tools.self_improvement_v2.git_worker import source_tree_fingerprint


def _finalize(tmp_path: Path):
    repo = tmp_path / "r"
    baseline = init_temp_repo(repo)
    before = source_tree_fingerprint(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, proposal)
    store.insert_review(review)
    result = finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
    )
    _bundle, worktree = store.get_execution(bundle["execution_id"])
    return repo, before, Path(worktree), result


def test_export_copy_verify_ack_cleanup_and_human_promotion(tmp_path: Path) -> None:
    repo, before, worktree, result = _finalize(tmp_path)
    scratch = worktree.resolve().parent.parent
    export_dir = scratch / "export"
    assert (export_dir / "candidate.bundle").is_file()
    assert (export_dir / "actual.diff").is_file()
    assert result["final_state"] == "EXPORT_PENDING"
    dest = tmp_path / "host-export"
    manifest = copy_out_and_verify(worktree=worktree, dest=dest)
    assert manifest["state"] == "VERIFIED"
    assert manifest["push"] is False
    assert manifest["merge"] is False
    assert (dest / "verifier.git").is_dir()
    with pytest.raises(CandidateExportError):
        write_human_promotion_artifact(dest=dest)
    acked = acknowledge_and_cleanup(dest=dest)
    assert acked["state"] == "ACKNOWLEDGED"
    assert not scratch.exists()
    artifact = write_human_promotion_artifact(dest=dest)
    assert artifact["final_state"] == "READY_FOR_HUMAN_PROMOTION"
    assert artifact["push"] is False
    assert artifact["merge"] is False
    assert source_tree_fingerprint(repo) == before
    assert run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip() == ""


def test_ack_refused_before_verify(tmp_path: Path) -> None:
    dest = tmp_path / "empty-export"
    dest.mkdir()
    (dest / "manifest.json").write_text('{"state":"COPIED_UNVERIFIED"}\n', encoding="utf-8")
    with pytest.raises(CandidateExportError):
        acknowledge_and_cleanup(dest=dest)


def test_ack_cleanup_ids_must_match_verified_manifest(tmp_path: Path) -> None:
    """ACK cleanup identity is manifest-bound; mismatched caller ids fail closed."""
    _repo, _before, worktree, _result = _finalize(tmp_path)
    dest = tmp_path / "host-export-ack-bind"
    manifest = copy_out_and_verify(worktree=worktree, dest=dest)
    assert manifest["state"] == "VERIFIED"
    exec_id = str(manifest["execution_id"])
    with pytest.raises(CandidateExportError, match="execution_id must match"):
        acknowledge_and_cleanup(dest=dest, execution_id="0" * 32)
    assert _load_manifest_state(dest) == "VERIFIED"
    with pytest.raises(CandidateExportError, match="worker_container_id must match"):
        acknowledge_and_cleanup(
            dest=dest,
            execution_id=exec_id,
            worker_container_id="a" * 64,
        )
    assert _load_manifest_state(dest) == "VERIFIED"
    wrong_scratch = tmp_path / "wrong-scratch"
    wrong_scratch.mkdir()
    with pytest.raises(CandidateExportError, match="local_scratch must match"):
        acknowledge_and_cleanup(dest=dest, local_scratch=wrong_scratch)
    assert _load_manifest_state(dest) == "VERIFIED"
    # Matching caller ids (or omitting them) still ACK from verified manifest.
    acked = acknowledge_and_cleanup(dest=dest, execution_id=exec_id)
    assert acked["state"] == "ACKNOWLEDGED"


def _load_manifest_state(dest: Path) -> str:
    import json

    return str(json.loads((dest / "manifest.json").read_text(encoding="utf-8"))["state"])
