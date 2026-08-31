"""Revision 2.5 focused tests — topology, git isolation, attestation, export, cleanup."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import init_temp_repo, run
from tools.self_improvement_v2.cleanup_lifecycle import (
    apply_cleanup,
    reconstruct_execution_root,
    refuse_manifest_deletion_path,
    write_ack,
)
from tools.self_improvement_v2.docker_cli import (
    docker_cp_file_argv,
    refuse_directory_cp,
    require_container_id,
    resolve_unique_prefix,
    sanitized_docker_env,
)
from tools.self_improvement_v2.export_seal import bind_observed_identity, seal_generation
from tools.self_improvement_v2.export_transport import copy_generation, create_fresh_attempt
from tools.self_improvement_v2.export_verify import verify_three_authority
from tools.self_improvement_v2.finalized_attestation import write_finalized_attestation
from tools.self_improvement_v2.git_worker import run_git
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.option_a_constants import SCHEMA_FINALIZED_ATTESTATION, WORKER_EXPORT_ALLOWLIST
from tools.self_improvement_v2.option_a_controller import run_rev25_export
from tools.self_improvement_v2.runtime_authority import refuse_mode_as_authority
from tools.self_improvement_v2.srl_git_exec import classify_git_args, constructed_git_env, srl_git_exec
from tools.self_improvement_v2.topology_attest import live_reassert
from tools.self_improvement_v2.topology_consume import consume_live_reassert, require_independent_live

WID = "a" * 64
NID = "b" * 64
DIGEST = "sha256:" + "c" * 64
EID = "d" * 32
GEN = "e" * 8
HEAD = "f" * 40
TREE = "1" * 40
CAND = "2" * 40
CTREE = "3" * 40


def _inspect(cid: str, started: str = "t0", image: str = DIGEST, netns: str = "net-1", state: str = "running") -> dict:
    return {
        "Id": cid,
        "State": {"Status": state, "StartedAt": started},
        "Image": image,
        "NetworkSettings": {"SandboxKey": netns},
        "HostConfig": {"NetworkMode": f"container:{NID}"},
    }


class LiveBox:
    def __init__(self, started: str = "t0", image: str = DIGEST, netns: str = "net-1", state: str = "running") -> None:
        self.started = started
        self.image = image
        self.netns = netns
        self.state = state
        self.calls = 0

    def worker(self, cid: str) -> dict:
        self.calls += 1
        return _inspect(cid, self.started, self.image, self.netns, self.state)

    def n8n(self, cid: str) -> dict:
        return _inspect(cid, "n8n-t0", DIGEST, self.netns, "running")

    def listing(self) -> list[str]:
        return [WID, NID]


_SEALED_CP = re.compile(
    r"^([a-f0-9]{64}):(/tmp/srl-exec/[a-f0-9]{32}/export/[a-f0-9]{8}/[^/\\:]+)$"
)


class RecordingDocker:
    """Instrumentable Docker adapter: inspect/ps, per-file cp, mkdir/git exec."""

    def __init__(self) -> None:
        self.ops: list[list[str]] = []
        self.fs: dict[str, bytes] = {}
        self._repos: dict[str, Path] = {}
        self.directory_cp = 0
        self.local_copy_fallback = 0
        self.local_authority_c_fallback = 0
        self.local_git_observation = 0

    def runner(self, argv: list[str]) -> tuple[int, str, str]:
        self.ops.append(list(argv))
        if not argv or argv[0] != "docker":
            return 1, "", "not docker"
        if len(argv) == 3 and argv[1] == "inspect":
            return 0, json.dumps([_inspect(argv[2])]), ""
        if argv[1:] == ["ps", "--all", "--quiet", "--no-trunc"]:
            return 0, f"{WID}\n{NID}\n", ""
        if len(argv) == 4 and argv[1] == "cp":
            return self._cp(argv[2], argv[3])
        if len(argv) >= 4 and argv[1] == "exec":
            return self._exec(argv)
        return 1, "", "unexpected docker argv"

    def _cp(self, src: str, dest: str) -> tuple[int, str, str]:
        if src.rstrip().endswith("/") or dest.rstrip().endswith("/") or "/." in src or "/." in dest:
            self.directory_cp += 1
            return 1, "", "directory-wide docker cp is forbidden"
        outbound = _SEALED_CP.fullmatch(src)
        inbound = _SEALED_CP.fullmatch(dest)
        if outbound and inbound is None:
            host = Path(dest)
            host.parent.mkdir(parents=True, exist_ok=True)
            data = self.fs.get(src)
            if data is None:
                self.local_copy_fallback += 1
                return 1, "", "missing worker file"
            host.write_bytes(data)
            return 0, "", ""
        if inbound and outbound is None:
            self.fs[dest] = Path(src).read_bytes()
            return 0, "", ""
        self.local_copy_fallback += 1
        return 1, "", "unclassified docker cp"

    def _exec(self, argv: list[str]) -> tuple[int, str, str]:
        index = 2
        while index + 1 < len(argv) and argv[index] == "--env":
            index += 2
        if index >= len(argv):
            return 1, "", "unclassified docker exec"
        cid = argv[index]
        cmd = argv[index + 1 :]
        if cmd[:2] == ["mkdir", "-p"] and len(cmd) == 3:
            return 0, "", ""
        if cmd[:1] == ["cat"] and len(cmd) == 2:
            key = f"{cid}:{cmd[1]}"
            data = self.fs.get(key)
            if data is None:
                return 1, "", "missing worker file"
            return 0, data.decode("utf-8"), ""
        if cmd and cmd[0] == "git":
            return self._git(cid, cmd)
        return 1, "", "unclassified docker exec"

    def _git(self, cid: str, cmd: list[str]) -> tuple[int, str, str]:
        import subprocess
        import tempfile

        if cmd[:3] == ["git", "clone", "--branch"]:
            rest = cmd[3:]
            if rest and rest[0] == "srl-candidate":
                rest = rest[1:]
            if rest and rest[0] == "--":
                rest = rest[1:]
            if len(rest) != 2:
                return 1, "", "unclassified git clone"
            bundle, repo = rest
            data = self.fs.get(f"{cid}:{bundle}")
            if data is None:
                return 1, "", "missing worker bundle"
            tmp = Path(tempfile.mkdtemp(prefix="srl-r5-obs-"))
            bundle_file = tmp / "candidate.bundle"
            bundle_file.write_bytes(data)
            dest = tmp / "repo"
            proc = subprocess.run(
                ["git", "clone", "--branch", "srl-candidate", str(bundle_file), str(dest)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                self._repos[repo] = dest
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        if len(cmd) >= 4 and cmd[1] == "-C":
            host = self._repos.get(cmd[2])
            if host is None:
                return 1, "", "EXECUTION_REPO_ROOT not reconstructed"
            proc = subprocess.run(
                ["git", "-C", str(host), *cmd[3:]],
                capture_output=True,
                text=True,
                check=False,
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        return 1, "", "unclassified docker git"

    def copy_fn(self, argv: list[str]) -> None:
        code, _out, err = self.runner(argv)
        if code != 0:
            raise WorkerError("FAILED_FROZEN", err or "docker cp failed", state="FAILED_FROZEN")

    def exec_docker(self, argv: list[str]) -> tuple[int, str, str]:
        return self.runner(argv)

    def has_inspect_or_ps(self) -> bool:
        return any(argv[1] in {"inspect", "ps"} for argv in self.ops if len(argv) > 1)

    def has_exec(self) -> bool:
        return any(argv[1] == "exec" for argv in self.ops if len(argv) > 1)

    def has_per_file_cp(self) -> bool:
        return any(argv[1] == "cp" for argv in self.ops if len(argv) > 1)

    def inspect_only(self) -> bool:
        return self.has_inspect_or_ps() and not self.has_exec() and not self.has_per_file_cp()


def _hashes_for(payloads: dict[str, bytes]) -> dict[str, str]:
    return {k: hashlib.sha256(v).hexdigest() for k, v in payloads.items()}


def _write_allowlist(directory: Path, commit: str = CAND, tree: str = CTREE, eid: str = EID) -> dict[str, bytes]:
    fin = json.dumps({"candidate_commit": commit, "candidate_tree": tree}, sort_keys=True).encode()
    payloads: dict[str, bytes] = {name: f"{name}\n".encode() for name in WORKER_EXPORT_ALLOWLIST}
    payloads["candidate_commit"] = f"{commit}\n".encode()
    payloads["candidate_tree"] = f"{tree}\n".encode()
    payloads["execution_id"] = f"{eid}\n".encode()
    payloads["reviewed_head"] = f"{HEAD}\n".encode()
    payloads["authorized_baseline"] = f"{HEAD}\n".encode()
    payloads["finalization_result.json"] = fin
    payloads["actual.diff"] = b"diff --git a/x b/x\n"
    payloads["actual.diff.sha256"] = f"{hashlib.sha256(payloads['actual.diff']).hexdigest()}\n".encode()
    payloads["finalization_result.sha256"] = f"{hashlib.sha256(fin).hexdigest()}\n".encode()
    payloads["candidate.bundle.sha256"] = (
        f"{hashlib.sha256(payloads['candidate.bundle']).hexdigest()}\n".encode()
    )
    for name, data in payloads.items():
        (directory / name).write_bytes(data)
    return payloads


def test_same_id_new_started_at_refuses() -> None:
    box = LiveBox(started="t0")
    first = live_reassert(
        inspect_worker=box.worker,
        inspect_n8n=box.n8n,
        list_all_ids=box.listing,
        worker_id=WID,
        n8n_id=NID,
        sequence=1,
    )
    box.started = "t1"
    with pytest.raises(WorkerError) as ei:
        live_reassert(
            inspect_worker=box.worker,
            inspect_n8n=box.n8n,
            list_all_ids=box.listing,
            worker_id=WID,
            n8n_id=NID,
            previous=first,
            sequence=2,
        )
    assert ei.value.code == "TOPOLOGY_REASSERT_FAILED"
    assert ei.value.state == "FAILED_FROZEN"


def test_cached_topology_reuse_forbidden() -> None:
    prior = {"live": "YES", "from_cache": True}
    with pytest.raises(WorkerError) as ei:
        consume_live_reassert(prior)
    assert ei.value.code == "CACHED_TOPOLOGY_AUTHORITY"
    live = {"live": "YES", "satisfy_later_gate": True}
    box = LiveBox()
    with pytest.raises(WorkerError) as ei2:
        require_independent_live(
            inspect_worker=box.worker,
            inspect_n8n=box.n8n,
            list_all_ids=box.listing,
            worker_id=WID,
            n8n_id=NID,
            sequence=1,
            prior_pass=live,
        )
    assert ei2.value.code == "CACHED_TOPOLOGY_AUTHORITY"


def test_wrong_worker_image_pin() -> None:
    box = LiveBox()
    with pytest.raises(WorkerError) as ei:
        live_reassert(
            inspect_worker=box.worker,
            inspect_n8n=box.n8n,
            list_all_ids=box.listing,
            worker_id=WID,
            n8n_id=NID,
            expected_image_digest="sha256:" + "9" * 64,
            sequence=1,
        )
    assert ei.value.code == "TOPOLOGY_REASSERT_FAILED"


def test_docker_prefix_joiner_forbidden_in_argv() -> None:
    with pytest.raises(WorkerError) as ei:
        require_container_id(WID[:12])
    assert ei.value.code == "DOCKER_PREFIX_ID"
    resolved = resolve_unique_prefix([WID, NID], WID)
    assert resolved == WID
    with pytest.raises(WorkerError):
        resolve_unique_prefix([WID, NID], "aa")


def test_restart_during_export_invalidates_generation(tmp_path: Path) -> None:
    gen = tmp_path / "gen"
    gen.mkdir()
    payloads = _write_allowlist(gen)
    hashes = _hashes_for(payloads)
    box = LiveBox()
    calls = {"n": 0}

    def inspect_live() -> dict:
        calls["n"] += 1
        prev = {
            "worker_container_id": WID,
            "worker_started_at": "t0",
            "worker_image_digest": DIGEST,
            "worker_netns_identity": "net-1",
        }
        if calls["n"] >= 3:
            box.started = "restarted"
        return live_reassert(
            inspect_worker=box.worker,
            inspect_n8n=box.n8n,
            list_all_ids=box.listing,
            worker_id=WID,
            n8n_id=NID,
            previous=prev if calls["n"] >= 3 else None,
            sequence=calls["n"],
        )

    def copy_fn(argv: list[str]) -> None:
        Path(argv[-1]).write_bytes(payloads[Path(argv[-1]).name])

    attested = {
        "worker_container_id": WID,
        "worker_started_at": "t0",
        "worker_image_digest": DIGEST,
        "worker_netns_identity": "net-1",
    }
    with pytest.raises(WorkerError) as ei:
        copy_generation(
            durable_root=tmp_path / "durable",
            execution_id=EID,
            generation=GEN,
            worker_id=WID,
            attested=attested,
            sealed_hashes=hashes,
            live_inspect=inspect_live,
            copy_fn=copy_fn,
            pre_copy_reassert_done=True,
        )
    assert ei.value.code == "COPIED_GENERATION_INVALID"


def test_omit_pre_copy_reassert_refuses(tmp_path: Path) -> None:
    with pytest.raises(WorkerError) as ei:
        copy_generation(
            durable_root=tmp_path / "durable",
            execution_id=EID,
            generation=GEN,
            worker_id=WID,
            attested={"worker_container_id": WID, "worker_started_at": "t0", "worker_image_digest": DIGEST, "worker_netns_identity": "net-1"},
            sealed_hashes={},
            live_inspect=lambda: {"live": "YES"},
            copy_fn=lambda argv: None,
            pre_copy_reassert_done=False,
        )
    assert ei.value.code == "CACHED_TOPOLOGY_AUTHORITY"


def test_partial_attestation_and_overwrite(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger"
    hashes = {name: "a" * 64 for name in WORKER_EXPORT_ALLOWLIST}
    fields = {
        "schema_version": SCHEMA_FINALIZED_ATTESTATION,
        "execution_id": EID,
        "reviewed_head": HEAD,
        "authorized_baseline": HEAD,
        "candidate_commit": CAND,
        "candidate_tree": CTREE,
        "srl_candidate_ref": "refs/heads/srl-candidate",
        "finalization_result_sha256": "4" * 64,
        "sealed_inventory_sha256": "5" * 64,
        "sealed_artifact_hashes": hashes,
        "candidate_bundle_sha256": hashes["candidate.bundle"],
        "staging_generation": GEN,
        "worker_container_id": WID,
        "worker_started_at": "t0",
        "worker_image_digest": DIGEST,
        "worker_netns_identity": "net-1",
        "n8n_container_id": NID,
        "topology_attestation_identity": "6" * 64,
        "topology_attestation_sequence": 1,
        "launcher_observation_sequence": 2,
        "observed_unix_ts": 1,
    }
    partial = dict(fields)
    partial["candidate_commit"] = "PENDING"
    with pytest.raises(WorkerError) as ei:
        write_finalized_attestation(ledger, partial)
    assert ei.value.code == "ATTESTATION_INCOMPLETE"
    assert not (ledger / "finalized_attestation.json").exists()
    write_finalized_attestation(ledger, fields)
    with pytest.raises(WorkerError) as ei2:
        write_finalized_attestation(ledger, fields)
    assert ei2.value.code == "ATTESTATION_EXISTS"


def test_observe_t_seal_tprime_refuses_before_write() -> None:
    with pytest.raises(WorkerError) as ei:
        bind_observed_identity(
            observed_commit=CAND,
            observed_tree=CTREE,
            sealed_commit_bytes="9" * 40,
            sealed_tree_bytes=CTREE,
            finalization_commit=CAND,
            finalization_tree=CTREE,
            bundle_heads=["refs/heads/srl-candidate"],
            sealed_bundle_sha256="a" * 64,
        )
    assert ei.value.code == "SEAL_BIND_MISMATCH"


def test_symlink_and_extra_artifact_refused(tmp_path: Path) -> None:
    gen = tmp_path / "gen"
    gen.mkdir()
    _write_allowlist(gen)
    (gen / "secret").write_text("nope", encoding="utf-8")
    with pytest.raises(WorkerError) as ei:
        seal_generation(gen)
    assert ei.value.code == "EXTRA_ARTIFACT"
    (gen / "secret").unlink()
    (gen / "actual.diff").unlink()
    (gen / "actual.diff").mkdir()
    with pytest.raises(WorkerError) as ei2:
        seal_generation(gen)
    assert ei2.value.code == "NON_REGULAR_ARTIFACT"


def test_partial_copy_retry_uses_fresh_attempt(tmp_path: Path) -> None:
    first = create_fresh_attempt(tmp_path / "d", EID, "aa" * 4)
    (first / "actual.diff").write_bytes(b"partial")
    with pytest.raises(WorkerError):
        create_fresh_attempt(tmp_path / "d", EID, "aa" * 4)
    second = create_fresh_attempt(tmp_path / "d", EID, "bb" * 4)
    assert list(second.iterdir()) == []
    assert (first / "actual.diff").exists()


def test_ambient_proxy_not_used_for_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:9")
    env = sanitized_docker_env()
    assert "HTTP_PROXY" not in env
    assert "HTTPS_PROXY" not in env
    assert "ALL_PROXY" not in env


def test_directory_wide_docker_cp_refused() -> None:
    with pytest.raises(WorkerError):
        refuse_directory_cp(["docker", "cp", f"{WID}:/tmp/srl-exec/{EID}/export/.", str(Path("out"))])


def test_seal_mutation_detected(tmp_path: Path) -> None:
    gen = tmp_path / "gen"
    gen.mkdir()
    _write_allowlist(gen)
    seen = {"n": 0}

    def reader(path: Path) -> bytes:
        seen["n"] += 1
        data = path.read_bytes()
        if seen["n"] > len(WORKER_EXPORT_ALLOWLIST):
            return data + b"mutated"
        return data

    with pytest.raises(WorkerError) as ei:
        seal_generation(gen, open_nofollow=reader)
    assert ei.value.state == "FAILED_FROZEN"


def test_host_tmp_srl_exec_forbidden(tmp_path: Path) -> None:
    with pytest.raises(WorkerError) as ei:
        docker_cp_file_argv(WID, EID, GEN, "actual.diff", Path("/tmp/srl-exec/nope"))
    assert ei.value.code == "HOST_TMP_SRL_EXEC"


def test_status_and_push_forbidden(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    init_temp_repo(repo)
    with pytest.raises(WorkerError) as ei:
        run_git(["status"], cwd=repo)
    assert ei.value.code == "REVIEWED_SOURCE_WRITE"
    with pytest.raises(WorkerError) as ei2:
        run_git(["push"], cwd=repo)
    assert ei2.value.code == "PUSH_ATTEMPT"
    assert classify_git_args(["merge", "HEAD"]) == "FORBIDDEN"


def test_git_alternates_templates_hooks_and_autocrlf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "r"
    init_temp_repo(repo)
    monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", str(tmp_path / "alts"))
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(tmp_path / "tmpl"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "evil.gitconfig"))
    env = constructed_git_env()
    assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" not in env
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    proc = srl_git_exec(["rev-parse", "HEAD"], cwd=repo)
    assert len(proc.stdout.decode().strip()) == 40


def test_execution_id_grammar_disagreement(tmp_path: Path) -> None:
    attempt = tmp_path / "a"
    attempt.mkdir()
    payloads = _write_allowlist(attempt, eid="0" * 32)
    hashes = _hashes_for(payloads)
    att = {
        "execution_id": EID,
        "candidate_commit": CAND,
        "candidate_tree": CTREE,
        "reviewed_head": HEAD,
        "finalization_result_sha256": hashes["finalization_result.json"],
        "sealed_artifact_hashes": hashes,
    }
    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head=HEAD,
            recompute_diff=lambda *_: payloads["actual.diff"],
            clone_bundle=lambda *_: None,
            verify_scratch=tmp_path / "scratch",
        )
    assert ei.value.code == "EXECUTION_ID_GRAMMAR"


def test_forged_export_t_vs_tprime(tmp_path: Path) -> None:
    attempt = tmp_path / "a"
    attempt.mkdir()
    payloads = _write_allowlist(attempt)
    hashes = _hashes_for(payloads)
    att = {
        "execution_id": EID,
        "candidate_commit": "9" * 40,
        "candidate_tree": CTREE,
        "reviewed_head": HEAD,
        "finalization_result_sha256": hashes["finalization_result.json"],
        "sealed_artifact_hashes": hashes,
    }
    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head=HEAD,
            recompute_diff=lambda *_: payloads["actual.diff"],
            clone_bundle=lambda *_: None,
            verify_scratch=tmp_path / "scratch",
        )
    assert ei.value.code == "FORGED_EXPORT"


def test_self_consistent_forged_diff_still_fails(tmp_path: Path) -> None:
    attempt = tmp_path / "a"
    attempt.mkdir()
    payloads = _write_allowlist(attempt)
    hashes = _hashes_for(payloads)
    att = {
        "execution_id": EID,
        "candidate_commit": CAND,
        "candidate_tree": CTREE,
        "reviewed_head": HEAD,
        "finalization_result_sha256": hashes["finalization_result.json"],
        "sealed_artifact_hashes": hashes,
    }
    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head=HEAD,
            recompute_diff=lambda *_: b"forged-but-self-hashed",
            clone_bundle=lambda *_: None,
            verify_scratch=tmp_path / "scratch",
        )
    assert ei.value.code == "FORGED_EXPORT"


def test_unsafe_cleanup_target() -> None:
    with pytest.raises(WorkerError) as ei:
        refuse_manifest_deletion_path("/tmp/evil", EID)
    assert ei.value.code == "UNSAFE_CLEANUP_TARGET"
    assert reconstruct_execution_root(EID) == f"/tmp/srl-exec/{EID}"


def test_ack_is_not_deleted(tmp_path: Path) -> None:
    write_ack(tmp_path, EID)
    deleted = {"n": 0}

    def delete(_path: str) -> bool:
        deleted["n"] += 1
        return False

    state = apply_cleanup(execution_id=EID, ledger_state="ACKNOWLEDGED", delete_fn=delete)
    assert state == "CLEANUP_PARTIAL"
    assert deleted["n"] == 1


def test_runtime_mode_is_not_authority() -> None:
    with pytest.raises(WorkerError) as ei:
        refuse_mode_as_authority("P3C1", live_authorized=False, p3c1_authorized=False)
    assert ei.value.code == "RUNTIME_MODE_NOT_AUTHORITY"


def test_bundle_clone_after_scratch_destroyed(tmp_path: Path) -> None:
    src = tmp_path / "src"
    init_temp_repo(src)
    run(["git", "checkout", "-b", "srl-candidate"], src)
    (src / "docs" / "CAND.md").write_text("cand\n", encoding="utf-8")
    run(["git", "add", "-A"], src)
    run(["git", "commit", "-m", "cand"], src)
    bundle = tmp_path / "candidate.bundle"
    run(["git", "bundle", "create", str(bundle), "HEAD", "srl-candidate"], src)
    import shutil
    import stat

    def _rmtree(path: Path) -> None:
        def _onerror(func, name, _exc):
            os.chmod(name, stat.S_IWRITE)
            func(name)

        shutil.rmtree(path, onerror=_onerror)

    _rmtree(src)
    dest = tmp_path / "promotion"
    run(["git", "clone", "--branch", "srl-candidate", str(bundle), str(dest)], tmp_path)
    head = run(["git", "rev-parse", "refs/heads/srl-candidate"], dest).stdout.strip()
    assert len(head) == 40


def test_controller_happy_path(tmp_path: Path) -> None:
    from tests.self_improvement_v2.test_option_a_rev25_repair1 import (
        _real_srl_candidate_bundle,
        _write_allowlist_with_bundle,
    )

    bundle, commit, tree = _real_srl_candidate_bundle(tmp_path)
    gen = tmp_path / "gen"
    gen.mkdir()
    payloads = _write_allowlist_with_bundle(gen, bundle, commit, tree)
    box = LiveBox()

    def copy_fn(argv: list[str]) -> None:
        name = Path(argv[-1]).name
        Path(argv[-1]).write_bytes(payloads[name])

    def clone(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--branch", "srl-candidate", str(src), str(dest)], tmp_path)

    result = run_rev25_export(
        execution_id=EID,
        reviewed_head=HEAD,
        authorized_baseline=HEAD,
        staging_generation=GEN,
        worker_id=WID,
        n8n_id=NID,
        expected_image_digest=DIGEST,
        inspect_worker=box.worker,
        inspect_n8n=box.n8n,
        list_all_ids=box.listing,
        observe_git=lambda: (commit, tree, commit),
        bundle_heads=lambda: [(commit, "refs/heads/srl-candidate")],
        worker_generation_dir=gen,
        ledger_root=tmp_path / "ledger",
        durable_root=tmp_path / "durable",
        copy_fn=copy_fn,
        recompute_diff=lambda *_: payloads["actual.diff"],
        clone_bundle=clone,
        verify_scratch=tmp_path / "scratch",
        now_ts=1,
    )
    assert result["state"] == "FINALIZED"
    assert (tmp_path / "ledger" / "finalized_attestation.json").is_file()
    assert (tmp_path / "durable" / "verified" / EID / "actual.diff").is_file()
    assert box.calls >= 3


def test_no_unguarded_git_in_rev25_modules() -> None:
    from tests.self_improvement_v2.test_option_a_rev25_repair1 import (
        test_unguarded_git_detection_is_closed_world,
    )

    test_unguarded_git_detection_is_closed_world()
