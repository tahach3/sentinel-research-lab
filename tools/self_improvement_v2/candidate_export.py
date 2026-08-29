"""Host-side candidate export copy-out, SHA verify, ACK, and human promotion.

Imported by the launcher. The worker HTTP bridge must not import this module —
ACK and scratch cleanup are host operations after EXPORT_PENDING.

Production transport is docker -H <E> cp from the worker container export dir.
Direct host filesystem reads of /tmp/srl-exec are refused unless an explicit
local_export_dir is supplied for same-namespace unit tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.topology_attest import (
    docker_argv,
    sanitized_docker_env,
    validate_docker_endpoint,
)

MANIFEST_SCHEMA = "srl.candidate_export_manifest.v1"
PROMOTION_SCHEMA = "srl.human_promotion_artifact.v1"
STATE_NOT_EXPORTED = "NOT_EXPORTED"
STATE_COPYING = "COPYING"
STATE_COPIED_UNVERIFIED = "COPIED_UNVERIFIED"
STATE_VERIFIED = "VERIFIED"
STATE_ACKNOWLEDGED = "ACKNOWLEDGED"

_EXEC_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{64}$")


class CandidateExportError(WorkerError):
    def __init__(self, message: str) -> None:
        super().__init__(ERROR_CODES["FAILED_FROZEN"], message, state="FAILED_FROZEN")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sanitized_git_env(git_tmp: Path) -> dict[str, str]:
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "GCM_INTERACTIVE": "never",
        "GIT_CONFIG_COUNT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(git_tmp),
        "TMP": str(git_tmp),
        "TEMP": str(git_tmp),
    }
    for key in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC"):
        val = os.environ.get(key)
        if val:
            env[key] = val
    return env


def _run_git(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        check=False,
        shell=False,
        env=env,
        timeout=60,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:400]
        raise CandidateExportError(detail or f"git {' '.join(args)} failed")
    return proc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateExportError(f"unable to read {path.name}") from exc
    if not isinstance(payload, dict):
        raise CandidateExportError(f"{path.name} must be an object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _scratch_from_worktree(worktree: Path) -> Path:
    resolved = worktree.resolve()
    if resolved.parent.name != "worktrees":
        raise CandidateExportError("worktree is not under /worktrees/main")
    return resolved.parent.parent


def _docker_cp_export(
    *,
    docker_endpoint: str,
    worker_container_id: str,
    execution_id: str,
    dest: Path,
    runner: Callable[[list[str], dict[str, str]], Any] | None = None,
) -> None:
    if _CONTAINER_ID_RE.fullmatch(worker_container_id) is None:
        raise CandidateExportError("worker_container_id must be 64-lowercase-hex")
    if _EXEC_ID_RE.fullmatch(execution_id) is None:
        raise CandidateExportError("execution_id must be 32-lowercase-hex")
    ep = validate_docker_endpoint(docker_endpoint)
    container_src = f"{worker_container_id}:/tmp/srl-exec/{execution_id}/export/."
    argv = docker_argv(ep, ["cp", container_src, str(dest) + "/"])
    env = sanitized_docker_env()
    if runner is not None:
        result = runner(argv, env)
        code = getattr(result, "returncode", 0 if isinstance(result, str) else 1)
        if code != 0:
            raise CandidateExportError("docker cp export failed")
        return
    proc = subprocess.run(argv, capture_output=True, check=False, env=env, timeout=120)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")[:400]
        raise CandidateExportError(detail or "docker cp export failed")


def _verify_copied_export(*, dest: Path, state: dict[str, Any]) -> dict[str, Any]:
    bundle_dst = dest / "candidate.bundle"
    diff_dst = dest / "actual.diff"
    if not bundle_dst.is_file() or not diff_dst.is_file():
        raise CandidateExportError("export artifacts missing after copy-out")
    expected_bundle = str(state.get("candidate_bundle_sha256") or "")
    expected_diff = str(state.get("actual_diff_sha256") or "")
    if _sha256_file(bundle_dst) != expected_bundle or _sha256_file(diff_dst) != expected_diff:
        raise CandidateExportError("copied export SHA-256 mismatch")
    verifier = dest / "verifier.git"
    git_tmp = dest / "git-tmp"
    git_tmp.mkdir(parents=True, exist_ok=True)
    env = _sanitized_git_env(git_tmp)
    _run_git(["init", "--bare", str(verifier)], cwd=dest, env=env)
    ref = str(state.get("export_ref") or "")
    commit = str(state.get("candidate_commit") or "")
    baseline = str(state.get("baseline_sha") or "")
    if not baseline or len(baseline) != 40:
        raise CandidateExportError("export_state missing baseline_sha")
    _run_git(
        ["fetch", "--no-tags", str(bundle_dst), f"{ref}:{ref}"],
        cwd=verifier,
        env=env,
    )
    fetched = _run_git(["rev-parse", ref], cwd=verifier, env=env).stdout.decode().strip()
    if fetched != commit:
        raise CandidateExportError("fresh verifier repo commit mismatch")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, commit],
        cwd=str(verifier),
        capture_output=True,
        check=False,
        env=env,
        timeout=30,
    )
    if ancestry.returncode != 0:
        raise CandidateExportError("candidate commit is not a descendant of baseline")
    work = dest / "verifier-work"
    if work.exists():
        shutil.rmtree(work)
    _run_git(["clone", str(verifier), str(work)], cwd=dest, env=env)
    _run_git(["checkout", "--force", commit], cwd=work, env=env)
    derived = _run_git(
        ["diff", "--binary", baseline, commit],
        cwd=work,
        env=env,
    ).stdout
    if hashlib.sha256(derived).hexdigest() != expected_diff:
        raise CandidateExportError("re-derived actual.diff SHA-256 mismatch")
    if derived != diff_dst.read_bytes():
        raise CandidateExportError("actual.diff bytes do not match re-derived diff")
    alternates = verifier / "objects" / "info" / "alternates"
    if alternates.is_file() and alternates.read_text(encoding="utf-8").strip():
        raise CandidateExportError("verifier repo must not use object alternates")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "execution_id": state["execution_id"],
        "candidate_commit": commit,
        "baseline_sha": baseline,
        "export_ref": ref,
        "candidate_bundle_sha256": expected_bundle,
        "actual_diff_sha256": expected_diff,
        "state": STATE_VERIFIED,
        "push": False,
        "merge": False,
        "worker_container_id": state.get("worker_container_id"),
        "execution_scratch_id": state.get("execution_id"),
    }
    _write_json(dest / "manifest.json", manifest)
    return manifest


def copy_out_and_verify(
    *,
    dest: Path,
    docker_endpoint: str | None = None,
    worker_container_id: str | None = None,
    execution_id: str | None = None,
    local_export_dir: Path | None = None,
    worktree: Path | None = None,
    docker_runner: Callable[[list[str], dict[str, str]], Any] | None = None,
) -> dict[str, Any]:
    """Copy candidate.bundle + actual.diff via docker cp (or test-local dir), then verify.

    Production requires docker_endpoint + worker_container_id + execution_id.
    Unit tests may pass local_export_dir (or legacy worktree) in the same namespace.
    """
    dest = dest.resolve()
    if dest.exists():
        raise CandidateExportError("export destination already exists")
    dest.mkdir(parents=True, exist_ok=False)

    if local_export_dir is None and worktree is not None:
        local_export_dir = _scratch_from_worktree(worktree) / "export"

    if docker_endpoint and worker_container_id and execution_id:
        _docker_cp_export(
            docker_endpoint=docker_endpoint,
            worker_container_id=worker_container_id,
            execution_id=execution_id,
            dest=dest,
            runner=docker_runner,
        )
        state_path = dest / "export_state.json"
        if not state_path.is_file():
            raise CandidateExportError("export_state.json missing after docker cp")
        state = _load_json(state_path)
        if state.get("state") != STATE_NOT_EXPORTED:
            raise CandidateExportError("export is not in NOT_EXPORTED")
        if state.get("execution_id") != execution_id:
            raise CandidateExportError("export_state execution_id mismatch")
        state["state"] = STATE_COPIED_UNVERIFIED
        state["worker_container_id"] = worker_container_id
        _write_json(state_path, state)
        return _verify_copied_export(dest=dest, state=state)

    if local_export_dir is None:
        raise CandidateExportError(
            "production export requires docker_endpoint, worker_container_id, and execution_id"
        )

    export_dir = local_export_dir.resolve()
    scratch = export_dir.parent
    state_path = export_dir / "export_state.json"
    state = _load_json(state_path)
    if state.get("state") != STATE_NOT_EXPORTED:
        raise CandidateExportError("export is not in NOT_EXPORTED")
    bundle_src = export_dir / "candidate.bundle"
    diff_src = export_dir / "actual.diff"
    if not bundle_src.is_file() or not diff_src.is_file():
        raise CandidateExportError("export artifacts missing")
    state["state"] = STATE_COPYING
    _write_json(state_path, state)
    shutil.copyfile(bundle_src, dest / "candidate.bundle")
    shutil.copyfile(diff_src, dest / "actual.diff")
    shutil.copyfile(state_path, dest / "export_state.json")
    state["state"] = STATE_COPIED_UNVERIFIED
    _write_json(dest / "export_state.json", state)
    _write_json(state_path, state)
    manifest = _verify_copied_export(dest=dest, state=state)
    manifest["scratch"] = str(scratch)
    _write_json(dest / "manifest.json", manifest)
    return manifest


def acknowledge_and_cleanup(
    *,
    dest: Path,
    docker_endpoint: str | None = None,
    worker_container_id: str | None = None,
    execution_id: str | None = None,
    docker_runner: Callable[[list[str], dict[str, str]], Any] | None = None,
    local_scratch: Path | None = None,
) -> dict[str, Any]:
    dest = dest.resolve()
    manifest_path = dest / "manifest.json"
    manifest = _load_json(manifest_path)
    if manifest.get("state") != STATE_VERIFIED:
        raise CandidateExportError("ACK requires VERIFIED export")
    # Cleanup identity is taken from the verified manifest only. Callers may
    # supply matching ids for defense-in-depth; mismatched ids are refused.
    manifest_exec = str(manifest.get("execution_id") or "")
    manifest_worker = manifest.get("worker_container_id")
    if execution_id is not None and execution_id != manifest_exec:
        raise CandidateExportError("ACK execution_id must match verified manifest")
    if worker_container_id is not None and worker_container_id != manifest_worker:
        raise CandidateExportError("ACK worker_container_id must match verified manifest")
    execution_id = manifest_exec
    if docker_endpoint:
        if not isinstance(manifest_worker, str) or not manifest_worker:
            raise CandidateExportError("ACK docker cleanup requires manifest worker_container_id")
        worker_container_id = manifest_worker

    # Resolve and bind cleanup target before durable ACK. Mismatched caller
    # scratch must fail closed without flipping VERIFIED → ACKNOWLEDGED.
    scratch: Path | None = None
    if docker_endpoint:
        scratch = None
    elif local_scratch is not None:
        expected = Path(str(manifest.get("scratch") or "")).resolve()
        if expected != local_scratch.resolve():
            raise CandidateExportError("ACK local_scratch must match verified manifest scratch")
        scratch = local_scratch
    else:
        scratch_raw = manifest.get("scratch")
        if isinstance(scratch_raw, str) and scratch_raw:
            scratch = Path(scratch_raw)

    manifest["state"] = STATE_ACKNOWLEDGED
    # Durable ACK first (temp → fsync → replace → dir fsync), then scratch delete.
    tmp = dest / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with tmp.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, manifest_path)
    dir_fd = os.open(str(dest), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

    if docker_endpoint and worker_container_id and execution_id:
        if _EXEC_ID_RE.fullmatch(execution_id) is None:
            raise CandidateExportError("execution_id must be 32-lowercase-hex")
        if _CONTAINER_ID_RE.fullmatch(worker_container_id) is None:
            raise CandidateExportError("worker_container_id must be 64-lowercase-hex")
        ep = validate_docker_endpoint(docker_endpoint)
        argv = docker_argv(
            ep,
            [
                "exec",
                worker_container_id,
                "rm",
                "-rf",
                f"/tmp/srl-exec/{execution_id}",
            ],
        )
        env = sanitized_docker_env()
        if docker_runner is not None:
            result = docker_runner(argv, env)
            code = getattr(result, "returncode", 0 if isinstance(result, str) else 1)
            if code != 0:
                raise CandidateExportError("docker exec scratch cleanup failed")
        else:
            proc = subprocess.run(argv, capture_output=True, check=False, env=env, timeout=120)
            if proc.returncode != 0:
                raise CandidateExportError("docker exec scratch cleanup failed")
        return manifest

    if scratch is not None and scratch.exists():
        shutil.rmtree(scratch, ignore_errors=False)
    return manifest


def write_human_promotion_artifact(*, dest: Path) -> dict[str, Any]:
    dest = dest.resolve()
    manifest = _load_json(dest / "manifest.json")
    if manifest.get("state") != STATE_ACKNOWLEDGED:
        raise CandidateExportError("human promotion requires ACKNOWLEDGED export")
    artifact = {
        "schema": PROMOTION_SCHEMA,
        "execution_id": manifest["execution_id"],
        "candidate_commit": manifest["candidate_commit"],
        "export_ref": manifest["export_ref"],
        "final_state": "READY_FOR_HUMAN_PROMOTION",
        "push": False,
        "merge": False,
    }
    _write_json(dest / "human_promotion.json", artifact)
    return artifact
