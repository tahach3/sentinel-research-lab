"""Host-side candidate export copy-out, SHA verify, ACK, and human promotion.

Imported by the launcher. The worker HTTP bridge must not import this module —
ACK and scratch cleanup are host operations after EXPORT_PENDING.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

MANIFEST_SCHEMA = "srl.candidate_export_manifest.v1"
PROMOTION_SCHEMA = "srl.human_promotion_artifact.v1"
STATE_NOT_EXPORTED = "NOT_EXPORTED"
STATE_COPYING = "COPYING"
STATE_COPIED_UNVERIFIED = "COPIED_UNVERIFIED"
STATE_VERIFIED = "VERIFIED"
STATE_ACKNOWLEDGED = "ACKNOWLEDGED"


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


def copy_out_and_verify(*, worktree: Path, dest: Path) -> dict[str, Any]:
    """Copy candidate.bundle + actual.diff, verify SHAs, unpack into a fresh verifier repo."""
    scratch = _scratch_from_worktree(worktree)
    export_dir = scratch / "export"
    state_path = export_dir / "export_state.json"
    state = _load_json(state_path)
    if state.get("state") != STATE_NOT_EXPORTED:
        raise CandidateExportError("export is not in NOT_EXPORTED")
    bundle_src = export_dir / "candidate.bundle"
    diff_src = export_dir / "actual.diff"
    if not bundle_src.is_file() or not diff_src.is_file():
        raise CandidateExportError("export artifacts missing")
    dest = dest.resolve()
    if dest.exists():
        raise CandidateExportError("export destination already exists")
    dest.mkdir(parents=True, exist_ok=False)
    state["state"] = STATE_COPYING
    _write_json(state_path, state)
    bundle_dst = dest / "candidate.bundle"
    diff_dst = dest / "actual.diff"
    shutil.copyfile(bundle_src, bundle_dst)
    shutil.copyfile(diff_src, diff_dst)
    state["state"] = STATE_COPIED_UNVERIFIED
    _write_json(state_path, state)
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
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "execution_id": state["execution_id"],
        "candidate_commit": commit,
        "export_ref": ref,
        "candidate_bundle_sha256": expected_bundle,
        "actual_diff_sha256": expected_diff,
        "state": STATE_VERIFIED,
        "push": False,
        "merge": False,
        "scratch": str(scratch),
    }
    _write_json(dest / "manifest.json", manifest)
    state["state"] = STATE_VERIFIED
    _write_json(state_path, state)
    return manifest


def acknowledge_and_cleanup(*, dest: Path) -> dict[str, Any]:
    dest = dest.resolve()
    manifest_path = dest / "manifest.json"
    manifest = _load_json(manifest_path)
    if manifest.get("state") != STATE_VERIFIED:
        raise CandidateExportError("ACK requires VERIFIED export")
    manifest["state"] = STATE_ACKNOWLEDGED
    _write_json(manifest_path, manifest)
    scratch_raw = manifest.get("scratch")
    if isinstance(scratch_raw, str) and scratch_raw:
        scratch = Path(scratch_raw)
        if scratch.exists():
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
