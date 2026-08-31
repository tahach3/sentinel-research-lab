"""Repair #5: isolated Git observation, Authority C, complete finalize, full topology."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import init_temp_repo, run
from tests.self_improvement_v2.test_option_a_rev25 import (
    DIGEST,
    EID,
    GEN,
    LiveBox,
    NID,
    RecordingDocker,
    WID,
    _inspect,
)
from tests.self_improvement_v2.test_option_a_rev25_repair1 import (
    _real_srl_candidate_bundle,
    _write_allowlist_with_bundle,
)
from tests.self_improvement_v2.test_option_a_rev25_repair2 import _ready_execution
from tools.self_improvement_v2.docker_cli import (
    docker_exec_cat_argv,
    docker_exec_git_argv,
    run_docker_argv,
)
from tools.self_improvement_v2.export_verify import reconstruct_authority_c, verify_three_authority
from tools.self_improvement_v2.finalization_result import (
    REV25_FINALIZATION_REQUIRED,
    serialize_finalization_result,
    validate_rev25_finalization_result,
)
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.option_a_constants import SRL_CANDIDATE_REF
from tools.self_improvement_v2.option_a_controller import (
    Rev25RuntimeDeps,
    _observe_git_via_worker_exec,
    _write_generation_allowlist,
    run_rev25_production_finalize,
)
from tools.self_improvement_v2.topology_attest import closed_set_from_listing, live_reassert

REPO = Path(__file__).resolve().parents[2]
CONTROLLER = REPO / "tools" / "self_improvement_v2" / "option_a_controller.py"
VERIFY = REPO / "tools" / "self_improvement_v2" / "export_verify.py"
ATTEST = REPO / "tools" / "self_improvement_v2" / "topology_attest.py"
DOCKER_CLI = REPO / "tools" / "self_improvement_v2" / "docker_cli.py"

EXEC_SENTINEL_COMMIT = "c0ffee00" + "11" * 16
EXEC_SENTINEL_TREE = "deadbeef" + "22" * 16
LOCAL_LOOKING_COMMIT = "aa" * 20
LOCAL_LOOKING_TREE = "bb" * 20
ISOLATION = {"GIT_OPTIONAL_LOCKS": "0"}


class GitSentinelDocker:
    """Governed exec: git observation returns sentinels; export-file cat returns launcher bytes."""

    def __init__(self) -> None:
        self.ops: list[list[str]] = []
        self.local_git_observation = 0

    def exec_docker(self, argv: list[str]) -> tuple[int, str, str]:
        self.ops.append(list(argv))
        joined = " ".join(argv)
        if argv[:2] != ["docker", "exec"]:
            return 1, "", "not exec"
        if "mkdir" in argv:
            return 0, "", ""
        if "cat" in argv:
            return 0, f"{LOCAL_LOOKING_COMMIT}\n", ""
        if "git" in argv:
            if "clone" in argv:
                return 0, "", ""
            if "HEAD^{tree}" in joined or "HEAD^{tree}" in argv:
                return 0, f"{EXEC_SENTINEL_TREE}\n", ""
            if "rev-parse" in argv:
                return 0, f"{EXEC_SENTINEL_COMMIT}\n", ""
            if "show" in argv or SRL_CANDIDATE_REF in argv:
                return 0, f"{EXEC_SENTINEL_COMMIT}\n", ""
        return 1, "", "unclassified"

    def copy_fn(self, argv: list[str]) -> None:
        return None


def _raise_if_local_git(*_a, **_k):
    raise WorkerError("FAILED_FROZEN", "LOCAL_GIT_OBSERVATION", state="FAILED_FROZEN")


def test_sentinels_do_not_resolve_in_local_object_store(tmp_path: Path) -> None:
    repo = tmp_path / "local"
    init_temp_repo(repo)
    for sha in (EXEC_SENTINEL_COMMIT, EXEC_SENTINEL_TREE):
        proc = run(["git", "cat-file", "-t", sha], repo, check=False)
        assert proc.returncode != 0
        assert sha not in run(["git", "rev-parse", "HEAD"], repo).stdout


def test_observe_git_uses_docker_exec_git_sentinels_not_export_files() -> None:
    docker = GitSentinelDocker()
    commit, tree, ref = _observe_git_via_worker_exec(
        worker_id=WID,
        execution_id=EID,
        staging_generation=GEN,
        exec_docker=docker.exec_docker,
    )
    assert commit == EXEC_SENTINEL_COMMIT
    assert tree == EXEC_SENTINEL_TREE
    assert ref == EXEC_SENTINEL_COMMIT
    git_ops = [argv for argv in docker.ops if "git" in argv]
    assert git_ops, docker.ops
    assert any("rev-parse" in argv and "HEAD" in argv for argv in git_ops)
    assert any("HEAD^{tree}" in " ".join(argv) for argv in git_ops)
    assert any(SRL_CANDIDATE_REF in argv for argv in git_ops)
    assert not any("cat" in argv and "candidate_commit" in " ".join(argv) for argv in docker.ops)


def test_observe_git_does_not_read_export_identity_files() -> None:
    src = ast.get_source_segment(
        CONTROLLER.read_text(encoding="utf-8"),
        next(
            n
            for n in ast.parse(CONTROLLER.read_text(encoding="utf-8")).body
            if isinstance(n, ast.FunctionDef) and n.name == "_observe_git_via_worker_exec"
        ),
    ) or ""
    assert "candidate_commit" not in src
    assert "candidate_tree" not in src
    assert "docker_exec_cat_argv" not in src


def test_observe_git_missing_capability_fails_frozen() -> None:
    def refuse(argv: list[str]) -> tuple[int, str, str]:
        return 1, "", "git unavailable"

    with pytest.raises(WorkerError) as ei:
        _observe_git_via_worker_exec(
            worker_id=WID,
            execution_id=EID,
            staging_generation=GEN,
            exec_docker=refuse,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_local_git_observation_hook_is_not_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.self_improvement_v2.option_a_controller.run_git",
        _raise_if_local_git,
    )
    monkeypatch.setattr(
        "tools.self_improvement_v2.srl_git_exec.srl_git_exec",
        _raise_if_local_git,
    )
    docker = GitSentinelDocker()
    commit, _tree, _ref = _observe_git_via_worker_exec(
        worker_id=WID,
        execution_id=EID,
        staging_generation=GEN,
        exec_docker=docker.exec_docker,
    )
    assert commit == EXEC_SENTINEL_COMMIT


def test_docker_exec_classifier_permits_isolated_git_not_arbitrary() -> None:
    repo = f"/tmp/srl-exec/{EID}/repo"
    head = docker_exec_git_argv(WID, EID, ["rev-parse", "--verify", "HEAD"], ISOLATION)
    assert head[0:2] == ["docker", "exec"]
    assert "--env" in head
    assert "GIT_OPTIONAL_LOCKS=0" in head
    assert head[-5:] == [WID, "git", "-C", repo, "rev-parse"] or (
        "git" in head and "-C" in head and repo in head
    )
    with pytest.raises(WorkerError) as ei:
        run_docker_argv(["docker", "exec", WID, "bash", "-lc", "git rev-parse HEAD"])
    assert ei.value.state == "FAILED_FROZEN"
    with pytest.raises(WorkerError) as ei2:
        run_docker_argv(docker_exec_cat_argv(WID, EID, GEN, "candidate_commit"))
    assert ei2.value.state == "FAILED_FROZEN"


def test_closed_set_refuses_extra_joiner() -> None:
    extra = "c" * 64
    with pytest.raises(WorkerError) as ei:
        closed_set_from_listing([WID, NID, extra], worker_id=WID, n8n_id=NID)
    assert ei.value.state == "FAILED_FROZEN"


def test_closed_set_refuses_prefix_id_joiner() -> None:
    with pytest.raises(WorkerError) as ei:
        closed_set_from_listing([WID, NID, WID[:12]], worker_id=WID, n8n_id=NID)
    assert ei.value.state == "FAILED_FROZEN"


def test_correct_worker_wrong_n8n_refuses() -> None:
    box = LiveBox()
    wrong = "d" * 64

    def listing() -> list[str]:
        return [WID, wrong]

    with pytest.raises(WorkerError) as ei:
        live_reassert(
            inspect_worker=box.worker,
            inspect_n8n=lambda cid: _inspect(cid, "n8n-t0", DIGEST, "other-net"),
            list_all_ids=listing,
            worker_id=WID,
            n8n_id=wrong,
            expected_image_digest=DIGEST,
            sequence=1,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_wrong_network_mode_refuses() -> None:
    box = LiveBox()

    def worker(cid: str) -> dict:
        payload = box.worker(cid)
        payload = dict(payload)
        payload["HostConfig"] = {"NetworkMode": "bridge"}
        return payload

    with pytest.raises(WorkerError) as ei:
        live_reassert(
            inspect_worker=worker,
            inspect_n8n=box.n8n,
            list_all_ids=box.listing,
            worker_id=WID,
            n8n_id=NID,
            expected_image_digest=DIGEST,
            sequence=1,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_exited_conflicting_container_refuses() -> None:
    extra = "e" * 64
    box = LiveBox()

    def listing() -> list[str]:
        return [WID, NID, extra]

    with pytest.raises(WorkerError) as ei:
        live_reassert(
            inspect_worker=box.worker,
            inspect_n8n=box.n8n,
            list_all_ids=listing,
            worker_id=WID,
            n8n_id=NID,
            expected_image_digest=DIGEST,
            sequence=1,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_same_worker_id_changed_netns_refuses() -> None:
    box = LiveBox(netns="net-1")
    first = live_reassert(
        inspect_worker=box.worker,
        inspect_n8n=box.n8n,
        list_all_ids=box.listing,
        worker_id=WID,
        n8n_id=NID,
        expected_image_digest=DIGEST,
        sequence=1,
    )
    box.netns = "net-2"
    with pytest.raises(WorkerError) as ei:
        live_reassert(
            inspect_worker=box.worker,
            inspect_n8n=box.n8n,
            list_all_ids=box.listing,
            worker_id=WID,
            n8n_id=NID,
            expected_image_digest=DIGEST,
            previous=first,
            sequence=2,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_stopped_n8n_refuses() -> None:
    box = LiveBox()

    def n8n(cid: str) -> dict:
        return _inspect(cid, "n8n-t0", DIGEST, box.netns, "exited")

    with pytest.raises(WorkerError) as ei:
        live_reassert(
            inspect_worker=box.worker,
            inspect_n8n=n8n,
            list_all_ids=box.listing,
            worker_id=WID,
            n8n_id=NID,
            expected_image_digest=DIGEST,
            sequence=1,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_finalization_result_missing_each_required_field_refuses() -> None:
    complete = {
        "schema_version": "2.0.0",
        "execution_id": EID,
        "review_id": "rev-1",
        "binding_verified": True,
        "reviewed_head": "f" * 40,
        "authorized_baseline": "f" * 40,
        "candidate_commit": "2" * 40,
        "candidate_tree": "3" * 40,
        "candidate_branch": SRL_CANDIDATE_REF,
        "committed_tree_sha": "3" * 40,
        "committed_diff_sha256": "4" * 64,
        "final_state": "READY_FOR_HUMAN_PROMOTION",
        "error_codes": [],
        "learning_record_id": "learn-1",
    }
    validate_rev25_finalization_result(complete)
    for field in REV25_FINALIZATION_REQUIRED:
        partial = dict(complete)
        partial.pop(field)
        with pytest.raises(WorkerError) as ei:
            validate_rev25_finalization_result(partial)
        assert ei.value.state == "FAILED_FROZEN"


def test_finalization_result_unknown_schema_and_partial_refuse() -> None:
    with pytest.raises(WorkerError) as ei:
        validate_rev25_finalization_result({"schema_version": "not-a-schema", "execution_id": EID})
    assert ei.value.state == "FAILED_FROZEN"
    with pytest.raises(WorkerError) as ei2:
        validate_rev25_finalization_result({"candidate_commit": "2" * 40, "candidate_tree": "3" * 40})
    assert ei2.value.state == "FAILED_FROZEN"


def test_finalization_result_deterministic_hash_and_mutation_detected() -> None:
    complete = {
        "schema_version": "2.0.0",
        "execution_id": EID,
        "review_id": "rev-1",
        "binding_verified": True,
        "reviewed_head": "f" * 40,
        "authorized_baseline": "f" * 40,
        "candidate_commit": "2" * 40,
        "candidate_tree": "3" * 40,
        "candidate_branch": SRL_CANDIDATE_REF,
        "committed_tree_sha": "3" * 40,
        "committed_diff_sha256": "4" * 64,
        "final_state": "READY_FOR_HUMAN_PROMOTION",
        "error_codes": [],
        "learning_record_id": "learn-1",
    }
    a = serialize_finalization_result(complete)
    b = serialize_finalization_result(dict(reversed(list(complete.items()))))
    assert a == b
    digest = hashlib.sha256(a).hexdigest()
    mutated = bytearray(a)
    mutated[-2] ^= 0x01
    assert hashlib.sha256(bytes(mutated)).hexdigest() != digest


def test_write_generation_allowlist_emits_complete_finalization_result(tmp_path: Path) -> None:
    gen = tmp_path / "gen"
    complete = {
        "schema_version": "2.0.0",
        "execution_id": EID,
        "review_id": "rev-1",
        "binding_verified": True,
        "reviewed_head": "f" * 40,
        "authorized_baseline": "f" * 40,
        "candidate_commit": "2" * 40,
        "candidate_tree": "3" * 40,
        "candidate_branch": SRL_CANDIDATE_REF,
        "committed_tree_sha": "3" * 40,
        "committed_diff_sha256": "4" * 64,
        "final_state": "READY_FOR_HUMAN_PROMOTION",
        "error_codes": [],
        "learning_record_id": "learn-1",
    }
    _write_generation_allowlist(
        gen,
        execution_id=EID,
        reviewed_head="f" * 40,
        candidate_commit="2" * 40,
        candidate_tree="3" * 40,
        actual_diff=b"diff",
        bundle_bytes=b"bundle",
        finalization_result=complete,
    )
    raw = (gen / "finalization_result.json").read_bytes()
    loaded = json.loads(raw.decode("utf-8"))
    validate_rev25_finalization_result(loaded)
    assert hashlib.sha256(raw).hexdigest() == hashlib.sha256(
        serialize_finalization_result(complete)
    ).hexdigest()
    sidecar = (gen / "finalization_result.sha256").read_text(encoding="utf-8").strip()
    assert sidecar == hashlib.sha256(raw).hexdigest()


def test_production_finalize_does_not_enrich_result_after_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = CONTROLLER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    finalize = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_rev25_production_finalize"
    )
    body = ast.get_source_segment(src, finalize) or ""
    write_idx = body.find("_write_generation_allowlist")
    result_idx = body.find("validate_instance(\"finalization_result\"")
    assert write_idx != -1
    assert result_idx != -1
    assert result_idx < write_idx


def _authority_bundle(tmp_path: Path) -> tuple[Path, str, str, bytes]:
    bundle, commit, tree = _real_srl_candidate_bundle(tmp_path)
    gen = tmp_path / "export-gen"
    gen.mkdir()
    payloads = _write_allowlist_with_bundle(gen, bundle, commit, tree)
    return gen / "candidate.bundle", commit, tree, payloads["actual.diff"]


def test_authority_c_wrong_bundle_refuses(tmp_path: Path) -> None:
    good_bundle, commit, tree, actual = _authority_bundle(tmp_path / "good")
    other_src = tmp_path / "other"
    init_temp_repo(other_src)
    run(["git", "checkout", "-b", "srl-candidate"], other_src)
    (other_src / "docs" / "WRONG.md").write_text("wrong\n", encoding="utf-8")
    run(["git", "add", "-A"], other_src)
    run(["git", "commit", "-m", "wrong"], other_src)
    wrong_bundle = tmp_path / "wrong.bundle"
    run(["git", "bundle", "create", str(wrong_bundle), "HEAD", "srl-candidate"], other_src)
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    from tests.self_improvement_v2.test_option_a_rev25_repair1 import _write_allowlist_with_bundle

    payloads = _write_allowlist_with_bundle(attempt, good_bundle, commit, tree)
    hashes = {name: hashlib.sha256((attempt / name).read_bytes()).hexdigest() for name in payloads}
    (attempt / "candidate.bundle").write_bytes(wrong_bundle.read_bytes())
    hashes["candidate.bundle"] = hashlib.sha256(wrong_bundle.read_bytes()).hexdigest()
    (attempt / "candidate.bundle.sha256").write_text(hashes["candidate.bundle"] + "\n", encoding="utf-8")
    att = {
        "execution_id": EID,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "reviewed_head": "f" * 40,
        "authorized_baseline": "f" * 40,
        "finalization_result_sha256": hashes["finalization_result.json"],
        "sealed_artifact_hashes": hashes,
        "candidate_bundle_sha256": hashes["candidate.bundle"],
    }
    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head="f" * 40,
            recompute_diff=lambda *_: actual,
            clone_bundle=reconstruct_authority_c,
            verify_scratch=tmp_path / "scratch",
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_authority_c_refuses_reviewed_source_and_precopy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "reviewed"
    init_temp_repo(repo)
    dest = tmp_path / "c"
    dest.mkdir()
    with pytest.raises(WorkerError) as ei:
        reconstruct_authority_c(repo, dest / "from-source")
    assert ei.value.state == "FAILED_FROZEN"
    pre = tmp_path / "pre-copy" / "candidate.bundle"
    pre.parent.mkdir()
    pre.write_bytes(b"not-from-attempt")
    with pytest.raises(WorkerError) as ei2:
        reconstruct_authority_c(pre, dest / "from-precopy")
    assert ei2.value.state == "FAILED_FROZEN"


def test_authority_c_wrong_tree_metadata_refuses(tmp_path: Path) -> None:
    bundle, commit, tree, actual = _authority_bundle(tmp_path)
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    payloads = _write_allowlist_with_bundle(attempt, bundle, commit, tree)
    hashes = {name: hashlib.sha256((attempt / name).read_bytes()).hexdigest() for name in payloads}
    att = {
        "execution_id": EID,
        "candidate_commit": commit,
        "candidate_tree": "9" * 40,
        "reviewed_head": "f" * 40,
        "authorized_baseline": "f" * 40,
        "finalization_result_sha256": hashes["finalization_result.json"],
        "sealed_artifact_hashes": hashes,
        "candidate_bundle_sha256": hashes["candidate.bundle"],
    }
    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head="f" * 40,
            recompute_diff=lambda *_: actual,
            clone_bundle=reconstruct_authority_c,
            verify_scratch=tmp_path / "scratch",
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_production_observe_source_is_docker_exec_git() -> None:
    src = CONTROLLER.read_text(encoding="utf-8")
    assert "docker_exec_git_argv" in src
    assert "bundle list-heads" in src or "list-heads" in src
    verify = VERIFY.read_text(encoding="utf-8")
    assert "refs/heads/srl-candidate" in verify
    attest = ATTEST.read_text(encoding="utf-8")
    assert "closed-set" in attest.lower() or "closed_set" in attest


def test_production_finalize_wires_complete_transport_without_local_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, _proposal, bundle, review, _store, _baseline = _ready_execution(
        tmp_path, monkeypatch=monkeypatch
    )
    docker = RecordingDocker()
    deps = Rev25RuntimeDeps(
        inspect_worker=lambda cid: json.loads(docker.runner(["docker", "inspect", cid])[1])[0],
        inspect_n8n=lambda cid: json.loads(docker.runner(["docker", "inspect", cid])[1])[0],
        list_all_ids=lambda: [WID, NID],
        worker_id=WID,
        n8n_id=NID,
        expected_image_digest=DIGEST,
        copy_fn=docker.copy_fn,
        clone_bundle=reconstruct_authority_c,
        exec_docker=docker.exec_docker,
    )
    result = run_rev25_production_finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
        deps=deps,
    )
    assert result["candidate_commit"]
    git_ops = [argv for argv in docker.ops if argv[1:2] == ["exec"] and "git" in argv]
    assert git_ops, docker.ops
    assert docker.local_copy_fallback == 0
    assert docker.local_authority_c_fallback == 0
    validate_rev25_finalization_result(result)
