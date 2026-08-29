"""Three-authority export verification. Manifest hash agreement is not sufficient."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import (
    EXECUTION_ID_RE,
    WORKER_EXPORT_ALLOWLIST,
)
from tools.self_improvement_v2.srl_git_exec import GitIsolation, srl_git_exec

DiffRecompute = Callable[[str, str], bytes]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_three_authority(
    *,
    attestation: dict[str, object],
    attempt_dir: Path,
    reviewed_head: str,
    recompute_diff: DiffRecompute,
    isolation: GitIsolation | None = None,
    clone_bundle: Callable[[Path, Path], None] | None = None,
    verify_scratch: Path | None = None,
) -> None:
    names = {p.name for p in attempt_dir.iterdir() if p.name != ".UNUSABLE"}
    extra = names - WORKER_EXPORT_ALLOWLIST
    if extra:
        raise WorkerError(
            ERROR_CODES["EXTRA_ARTIFACT"],
            f"EXTRA_ARTIFACT={sorted(extra)}",
            state="FAILED_FROZEN",
        )
    missing = WORKER_EXPORT_ALLOWLIST - names
    if missing:
        raise WorkerError(
            ERROR_CODES["MISSING_ARTIFACT"],
            f"MISSING_ARTIFACT={sorted(missing)}",
            state="FAILED_FROZEN",
        )
    sealed = attestation["sealed_artifact_hashes"]
    if not isinstance(sealed, dict):
        raise WorkerError(ERROR_CODES["FORGED_EXPORT"], "sealed hashes missing", state="FAILED_FROZEN")
    for name in sorted(WORKER_EXPORT_ALLOWLIST):
        path = attempt_dir / name
        if not path.is_file() or path.is_symlink():
            raise WorkerError(
                ERROR_CODES["NON_REGULAR_ARTIFACT"],
                name,
                state="FAILED_FROZEN",
            )
        if _sha256(path) != sealed[name]:
            raise WorkerError(
                ERROR_CODES["FORGED_EXPORT"],
                f"copied bytes != sealed_artifact_hashes: {name}",
                state="FAILED_FROZEN",
            )
    exec_bytes = (attempt_dir / "execution_id").read_text(encoding="utf-8").strip()
    ledger_eid = str(attestation["execution_id"])
    if exec_bytes != ledger_eid or not EXECUTION_ID_RE.fullmatch(ledger_eid):
        raise WorkerError(
            ERROR_CODES["EXECUTION_ID_GRAMMAR"],
            "execution-id grammar disagreement",
            state="FAILED_FROZEN",
        )
    copied_commit = (attempt_dir / "candidate_commit").read_text(encoding="utf-8").strip()
    copied_tree = (attempt_dir / "candidate_tree").read_text(encoding="utf-8").strip()
    if copied_commit != attestation["candidate_commit"] or copied_tree != attestation["candidate_tree"]:
        raise WorkerError(
            ERROR_CODES["FORGED_EXPORT"],
            "copied candidate identity != FINALIZED_ATTESTATION",
            state="FAILED_FROZEN",
        )
    worker_reviewed = (attempt_dir / "reviewed_head").read_text(encoding="utf-8").strip()
    if worker_reviewed != reviewed_head or reviewed_head != attestation["reviewed_head"]:
        raise WorkerError(
            ERROR_CODES["FORGED_EXPORT"],
            "reviewed_head disagreement",
            state="FAILED_FROZEN",
        )
    actual = (attempt_dir / "actual.diff").read_bytes()
    recomputed = recompute_diff(reviewed_head, str(attestation["candidate_commit"]))
    if recomputed != actual:
        raise WorkerError(
            ERROR_CODES["FORGED_EXPORT"],
            "recomputed actual.diff != copied bytes",
            state="FAILED_FROZEN",
        )
    if hashlib.sha256(actual).hexdigest() != (attempt_dir / "actual.diff.sha256").read_text(
        encoding="utf-8"
    ).strip():
        raise WorkerError(
            ERROR_CODES["FORGED_EXPORT"],
            "actual.diff.sha256 mismatch",
            state="FAILED_FROZEN",
        )
    fin_bytes = (attempt_dir / "finalization_result.json").read_bytes()
    if hashlib.sha256(fin_bytes).hexdigest() != attestation["finalization_result_sha256"]:
        raise WorkerError(
            ERROR_CODES["FORGED_EXPORT"],
            "finalization_result.json != attestation hash",
            state="FAILED_FROZEN",
        )
    if clone_bundle is not None:
        if verify_scratch is None:
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                "verify-scratch required for bundle clone",
                state="FAILED_FROZEN",
            )
        dest = verify_scratch / ledger_eid
        dest.mkdir(parents=True, exist_ok=True)
        clone_bundle(attempt_dir / "candidate.bundle", dest)
        head = srl_git_exec(
            ["rev-parse", "refs/heads/srl-candidate"],
            cwd=dest,
            isolation=isolation,
        ).stdout.decode().strip()
        tree = srl_git_exec(
            ["rev-parse", "refs/heads/srl-candidate^{tree}"],
            cwd=dest,
            isolation=isolation,
        ).stdout.decode().strip()
        if head != attestation["candidate_commit"] or tree != attestation["candidate_tree"]:
            raise WorkerError(
                ERROR_CODES["FORGED_EXPORT"],
                "bundle srl-candidate != attestation",
                state="FAILED_FROZEN",
            )


def atomic_publish(attempt_dir: Path, verified_root: Path) -> Path:
    verified_root.parent.mkdir(parents=True, exist_ok=True)
    tmp = verified_root.with_name(verified_root.name + ".tmp")
    if tmp.exists():
        raise WorkerError(ERROR_CODES["FAILED_FROZEN"], "publish tmp exists", state="FAILED_FROZEN")
    os_replace = __import__("os").replace
    # Copy tree then replace.
    import shutil

    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(attempt_dir, tmp)
    if verified_root.exists():
        raise WorkerError(ERROR_CODES["FAILED_FROZEN"], "verified root exists", state="FAILED_FROZEN")
    os_replace(tmp, verified_root)
    return verified_root
