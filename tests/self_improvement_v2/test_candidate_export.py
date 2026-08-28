"""E4–E5 candidate export: docker-cp copy-out, re-derived diff, ACK, then cleanup."""

from __future__ import annotations

import ast
import hashlib
import shutil
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo, run
from tools.self_improvement_v2.candidate_export import (
    CONTAINER_EXEC_ROOT,
    CandidateExportError,
    _sanitized_git_env,
    acknowledge_and_cleanup,
    copy_out_and_verify,
    write_human_promotion_artifact,
)
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.finalizer import finalize
from tools.self_improvement_v2.git_worker import remove_worktree, source_tree_fingerprint
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.topology_attest import DockerTransport, TopologyAttestationError


WORKER_ID = "b" * 64
ENDPOINT = "unix:///var/run/docker.sock"


class FakeExportDocker:
    def __init__(self) -> None:
        self.endpoint = ENDPOINT
        self.fail_cp = False
        self.fail_rm = False
        self.seen_argv: list[list[str]] = []
        self.seen_env: list[dict[str, str]] = []

    def runner(self, argv: list[str], env: dict[str, str]) -> str:
        self.seen_argv.append(list(argv))
        self.seen_env.append(dict(env))
        assert argv[:3] == ["docker", "-H", self.endpoint]
        args = argv[3:]
        if args[0] == "cp":
            if self.fail_cp:
                raise TopologyAttestationError("docker cp failed")
            src, dst = args[1], args[2]
            _cid, cpath = src.split(":", 1)
            host_src = Path(cpath)
            shutil.copyfile(host_src, dst)
            return ""
        if args[0] == "exec" and args[2] == "rm":
            if self.fail_rm:
                raise TopologyAttestationError("docker rm failed")
            target = Path(args[-1])
            if target.exists():
                shutil.rmtree(target)
            return ""
        raise TopologyAttestationError(f"unexpected docker argv {args}")


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
    fake = FakeExportDocker()
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    manifest = copy_out_and_verify(
        worktree=worktree,
        dest=dest,
        docker=docker,
        worker_container_id=WORKER_ID,
    )
    assert manifest["state"] == "VERIFIED"
    assert manifest["push"] is False
    assert manifest["merge"] is False
    assert manifest["scratch"] == f"{CONTAINER_EXEC_ROOT}/{scratch.name}"
    assert (dest / "verifier.git").is_dir()
    assert any(a[3] == "cp" for a in fake.seen_argv)
    assert scratch.exists()
    with pytest.raises(CandidateExportError):
        write_human_promotion_artifact(dest=dest)
    acked = acknowledge_and_cleanup(dest=dest, docker=docker)
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
    fake = FakeExportDocker()
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    with pytest.raises(CandidateExportError):
        acknowledge_and_cleanup(dest=dest, docker=docker)
    assert dest.exists()


def test_delete_before_ack_is_refused_scratch_remains(tmp_path: Path) -> None:
    _repo, _before, worktree, _result = _finalize(tmp_path)
    scratch = worktree.resolve().parent.parent
    assert scratch.exists()
    with pytest.raises(WorkerError, match="EXPORT_PENDING"):
        remove_worktree(_repo, worktree)
    assert scratch.exists()
    dest = tmp_path / "host-export"
    fake = FakeExportDocker()
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    copy_out_and_verify(
        worktree=worktree, dest=dest, docker=docker, worker_container_id=WORKER_ID
    )
    assert scratch.exists()
    with pytest.raises(WorkerError, match="EXPORT_PENDING"):
        remove_worktree(_repo, worktree)
    assert scratch.exists()
    acknowledge_and_cleanup(dest=dest, docker=docker)
    assert not scratch.exists()


def test_docker_cp_failure_fails_closed_no_shutil_fallback(tmp_path: Path) -> None:
    _repo, _before, worktree, _result = _finalize(tmp_path)
    scratch = worktree.resolve().parent.parent
    dest = tmp_path / "host-export"
    fake = FakeExportDocker()
    fake.fail_cp = True
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    with pytest.raises(CandidateExportError, match="docker cp"):
        copy_out_and_verify(
            worktree=worktree, dest=dest, docker=docker, worker_container_id=WORKER_ID
        )
    assert scratch.exists()
    assert not (dest / "candidate.bundle").exists()


def test_rederived_diff_mismatch_fails_closed_no_ack(tmp_path: Path) -> None:
    _repo, _before, worktree, _result = _finalize(tmp_path)
    scratch = worktree.resolve().parent.parent
    export_dir = scratch / "export"
    tampered = b"not-the-git-diff\n"
    (export_dir / "actual.diff").write_bytes(tampered)
    state_path = export_dir / "export_state.json"
    import json

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["actual_diff_sha256"] = hashlib.sha256(tampered).hexdigest()
    state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    dest = tmp_path / "host-export"
    fake = FakeExportDocker()
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    with pytest.raises(CandidateExportError, match="re-derived"):
        copy_out_and_verify(
            worktree=worktree, dest=dest, docker=docker, worker_container_id=WORKER_ID
        )
    assert scratch.exists()
    assert not (dest / "manifest.json").exists() or (
        dest / "manifest.json"
    ).read_text(encoding="utf-8").find("ACKNOWLEDGED") == -1


def test_copy_out_does_not_use_shutil_copyfile() -> None:
    tree = ast.parse(Path("tools/self_improvement_v2/candidate_export.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "copyfile":
            raise AssertionError("candidate_export must not shutil.copyfile host-guessed paths")


def test_sanitized_git_env_sets_optional_locks(tmp_path: Path) -> None:
    env = _sanitized_git_env(tmp_path)
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    git_dir = tmp_path / "repo"
    git_dir.mkdir()
    from tools.self_improvement_v2.candidate_export import _run_git

    _run_git(["init"], cwd=git_dir, env=env)
    status = _run_git(["status"], cwd=git_dir, env=env)
    assert status.returncode == 0
    assert b"git" in (status.stdout + status.stderr) or (git_dir / ".git").exists()
