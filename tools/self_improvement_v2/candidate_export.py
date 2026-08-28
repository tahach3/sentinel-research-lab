"""Host-side candidate export copy-out, SHA verify, ACK, and human promotion.

Imported by the launcher. The worker HTTP bridge must not import this module —
ACK and scratch cleanup are host operations after EXPORT_PENDING.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.topology_attest import DockerTransport, TopologyAttestationError

MANIFEST_SCHEMA = "srl.candidate_export_manifest.v1"
PROMOTION_SCHEMA = "srl.human_promotion_artifact.v1"
STATE_NOT_EXPORTED = "NOT_EXPORTED"
STATE_COPYING = "COPYING"
STATE_COPIED_UNVERIFIED = "COPIED_UNVERIFIED"
STATE_VERIFIED = "VERIFIED"
STATE_ACKNOWLEDGED = "ACKNOWLEDGED"
CONTAINER_EXEC_ROOT = "/tmp/srl-exec"
EXPORT_ARTIFACTS = ("export_state.json", "candidate.bundle", "actual.diff")


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
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(git_tmp),
        "TMP": str(git_tmp),
        "TEMP": str(git_tmp),
        "GIT_OPTIONAL_LOCKS": "0",
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


def _container_scratch(worktree: Path) -> str:
    scratch = _scratch_from_worktree(worktree)
    eid = scratch.name
    if len(eid) != 32 or any(ch not in "0123456789abcdef" for ch in eid):
        raise CandidateExportError("execution scratch name must be 32 lowercase hex")
    return f"{CONTAINER_EXEC_ROOT}/{eid}"


def _docker_cp(docker: DockerTransport, container_id: str, container_src: str, dest: Path) -> None:
    try:
        docker.run(["cp", f"{container_id}:{container_src}", str(dest)])
    except TopologyAttestationError as exc:
        raise CandidateExportError(f"docker cp failed closed: {exc}") from exc
    if not dest.is_file():
        raise CandidateExportError(f"docker cp did not produce {dest.name}")


def _docker_rm_scratch(docker: DockerTransport, container_id: str, container_scratch: str) -> None:
    if not container_scratch.startswith(CONTAINER_EXEC_ROOT + "/") or ".." in container_scratch:
        raise CandidateExportError("container scratch path refused")
    try:
        docker.run(["exec", container_id, "rm", "-rf", "--", container_scratch])
    except TopologyAttestationError as exc:
        raise CandidateExportError(f"docker scratch delete failed closed: {exc}") from exc


def copy_out_and_verify(
    *,
    worktree: Path,
    dest: Path,
    docker: DockerTransport,
    worker_container_id: str,
) -> dict[str, Any]:
    """docker-cp export artifacts, SHA-verify, unpack, re-derive actual.diff."""
    if not isinstance(worker_container_id, str) or len(worker_container_id) != 64:
        raise CandidateExportError("worker_container_id must be a full 64-hex container id")
    container_scratch = _container_scratch(worktree)
    dest = dest.resolve()
    if dest.exists():
        raise CandidateExportError("export destination already exists")
    dest.mkdir(parents=True, exist_ok=False)
    export_prefix = f"{container_scratch}/export"
    for name in EXPORT_ARTIFACTS:
        _docker_cp(docker, worker_container_id, f"{export_prefix}/{name}", dest / name)
    state = _load_json(dest / "export_state.json")
    if state.get("state") != STATE_NOT_EXPORTED:
        raise CandidateExportError("export is not in NOT_EXPORTED")
    bundle_dst = dest / "candidate.bundle"
    diff_dst = dest / "actual.diff"
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
    if not baseline:
        raise CandidateExportError("export_state missing baseline_sha")
    _run_git(
        ["fetch", "--no-tags", str(bundle_dst), f"{ref}:{ref}"],
        cwd=verifier,
        env=env,
    )
    fetched = _run_git(["rev-parse", ref], cwd=verifier, env=env).stdout.decode().strip()
    if fetched != commit:
        raise CandidateExportError("fresh verifier repo commit mismatch")
    alternates = verifier / "objects" / "info" / "alternates"
    if alternates.is_file() and alternates.read_text(encoding="utf-8").strip():
        raise CandidateExportError("verifier repo must not use object alternates")
    derived = _run_git(["diff", "--binary", baseline, commit], cwd=verifier, env=env)
    derived_sha = hashlib.sha256(derived.stdout or b"").hexdigest()
    if derived_sha != expected_diff or derived_sha != _sha256_file(diff_dst):
        raise CandidateExportError("re-derived actual.diff SHA-256 mismatch")
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
        "scratch": container_scratch,
        "worker_container_id": worker_container_id,
    }
    _write_json(dest / "manifest.json", manifest)
    return manifest


def acknowledge_and_cleanup(*, dest: Path, docker: DockerTransport) -> dict[str, Any]:
    dest = dest.resolve()
    manifest_path = dest / "manifest.json"
    manifest = _load_json(manifest_path)
    if manifest.get("state") != STATE_VERIFIED:
        raise CandidateExportError("ACK requires VERIFIED export")
    worker_container_id = str(manifest.get("worker_container_id") or "")
    container_scratch = str(manifest.get("scratch") or "")
    if not worker_container_id or not container_scratch:
        raise CandidateExportError("ACK missing worker container scratch binding")
    manifest["state"] = STATE_ACKNOWLEDGED
    _write_json(manifest_path, manifest)
    _docker_rm_scratch(docker, worker_container_id, container_scratch)
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
