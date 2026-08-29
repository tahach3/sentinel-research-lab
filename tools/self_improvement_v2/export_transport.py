"""Per-file docker cp, fresh host attempts, copy continuity."""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path
from typing import Callable

from tools.self_improvement_v2.docker_cli import docker_cp_file_argv, require_container_id
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import (
    ATTEMPT_ID_RE,
    EXECUTION_ID_RE,
    WORKER_EXPORT_ALLOWLIST,
)
from tools.self_improvement_v2.topology_identity import copy_generation_identity, identities_equal

CopyFn = Callable[[list[str]], None]
InspectLiveFn = Callable[[], dict[str, str]]


def allocate_attempt_id() -> str:
    return secrets.token_hex(4)


def host_attempt_dir(durable_root: Path, execution_id: str, attempt_id: str) -> Path:
    if not EXECUTION_ID_RE.fullmatch(execution_id):
        raise WorkerError(
            ERROR_CODES["EXECUTION_ID_GRAMMAR"],
            "SRL_EXECUTION_ID must be 32 hex",
            state="FAILED_FROZEN",
        )
    if not ATTEMPT_ID_RE.fullmatch(attempt_id):
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "ATTEMPT_ID must be 8 hex",
            state="FAILED_FROZEN",
        )
    return durable_root / "staging" / execution_id / attempt_id


def create_fresh_attempt(durable_root: Path, execution_id: str, attempt_id: str) -> Path:
    dest = host_attempt_dir(durable_root, execution_id, attempt_id)
    if dest.exists():
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "attempt directory reuse is forbidden",
            state="FAILED_FROZEN",
        )
    dest.mkdir(parents=True, exist_ok=False)
    if any(dest.iterdir()):
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "attempt directory must be created empty",
            state="FAILED_FROZEN",
        )
    return dest


def _host_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_generation(
    *,
    durable_root: Path,
    execution_id: str,
    generation: str,
    worker_id: str,
    attested: dict[str, str],
    sealed_hashes: dict[str, str],
    live_inspect: InspectLiveFn,
    copy_fn: CopyFn,
    pre_copy_reassert_done: bool,
) -> Path:
    if not pre_copy_reassert_done:
        raise WorkerError(
            ERROR_CODES["CACHED_TOPOLOGY_AUTHORITY"],
            "PRE_COPY_FULL_REASSERT=MANDATORY",
            state="FAILED_FROZEN",
        )
    live = live_inspect()
    if live.get("live") != "YES":
        raise WorkerError(
            ERROR_CODES["CACHED_TOPOLOGY_AUTHORITY"],
            "copy generation cannot start on a cached PASS",
            state="FAILED_FROZEN",
        )
    gen_id = copy_generation_identity(live)
    attested_id = copy_generation_identity(attested)
    if not identities_equal(gen_id, attested_id):
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "COPY_GENERATION_IDENTITY != FINALIZED_ATTESTATION worker identity",
            state="FAILED_FROZEN",
        )
    cid = require_container_id(worker_id)
    if cid != gen_id["worker_container_id"]:
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            "copy argv id must equal latest full reassert",
            state="FAILED_FROZEN",
        )
    attempt_id = allocate_attempt_id()
    dest = create_fresh_attempt(durable_root, execution_id, attempt_id)
    pre = dict(gen_id)
    try:
        for name in sorted(WORKER_EXPORT_ALLOWLIST):
            try:
                mid = live_inspect()
            except WorkerError as exc:
                raise WorkerError(
                    ERROR_CODES["COPIED_GENERATION_INVALID"],
                    f"COPY_CONTINUITY_MONITOR failed: {exc.message}",
                    state="FAILED_FROZEN",
                ) from exc
            if not identities_equal(copy_generation_identity(mid), pre):
                raise WorkerError(
                    ERROR_CODES["COPIED_GENERATION_INVALID"],
                    "COPY_CONTINUITY_MONITOR failed",
                    state="FAILED_FROZEN",
                )
            argv = docker_cp_file_argv(cid, execution_id, generation, name, dest / name)
            copy_fn(argv)
            target = dest / name
            if not target.is_file() or target.is_symlink():
                raise WorkerError(
                    ERROR_CODES["NON_REGULAR_ARTIFACT"],
                    f"host dest not regular file: {name}",
                    state="FAILED_FROZEN",
                )
            if _host_sha256(target) != sealed_hashes[name]:
                raise WorkerError(
                    ERROR_CODES["COPIED_GENERATION_INVALID"],
                    f"host SHA != seal: {name}",
                    state="FAILED_FROZEN",
                )
        try:
            post = live_inspect()
        except WorkerError as exc:
            raise WorkerError(
                ERROR_CODES["COPIED_GENERATION_INVALID"],
                f"POST_COPY_CONTINUITY_CHECK failed: {exc.message}",
                state="FAILED_FROZEN",
            ) from exc
        if not identities_equal(copy_generation_identity(post), pre):
            raise WorkerError(
                ERROR_CODES["COPIED_GENERATION_INVALID"],
                "POST_COPY_CONTINUITY_CHECK failed",
                state="FAILED_FROZEN",
            )
    except WorkerError:
        (dest / ".UNUSABLE").write_text("COPIED_GENERATION=INVALID\n", encoding="utf-8")
        raise
    return dest
