"""Worker-namespace seal: allowlist, regular files, nlink==1, O_NOFOLLOW hashes."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Callable, Iterable

from tools.self_improvement_v2.canonical import canonical_bytes, sha256_hex
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import (
    HOST_LAUNCHER_ONLY_NAMES,
    WORKER_EXPORT_ALLOWLIST,
)

OpenNoFollow = Callable[[str], bytes]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def default_open_nofollow(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    elif hasattr(os, "O_NOFOLLOW"):  # pragma: no cover
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise WorkerError(
                ERROR_CODES["NON_REGULAR_ARTIFACT"],
                f"not a regular file: {path.name}",
                state="FAILED_FROZEN",
            )
        if st.st_nlink != 1:
            raise WorkerError(
                ERROR_CODES["NON_REGULAR_ARTIFACT"],
                f"nlink!=1: {path.name}",
                state="FAILED_FROZEN",
            )
        return os.read(fd, st.st_size)
    finally:
        os.close(fd)


def seal_generation(
    generation_dir: Path,
    *,
    open_nofollow: Callable[[Path], bytes] | None = None,
) -> dict[str, str]:
    if not generation_dir.is_dir():
        raise WorkerError(
            ERROR_CODES["MISSING_ARTIFACT"],
            "generation directory missing",
            state="FAILED_FROZEN",
        )
    names = {p.name for p in generation_dir.iterdir()}
    extra = names - WORKER_EXPORT_ALLOWLIST
    if extra & HOST_LAUNCHER_ONLY_NAMES or extra:
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
    reader = open_nofollow or default_open_nofollow
    hashes: dict[str, str] = {}
    for name in sorted(WORKER_EXPORT_ALLOWLIST):
        path = generation_dir / name
        if path.is_symlink() or path.is_dir():
            raise WorkerError(
                ERROR_CODES["NON_REGULAR_ARTIFACT"],
                f"NON_REGULAR_ARTIFACT={name}",
                state="FAILED_FROZEN",
            )
        data = reader(path)
        hashes[name] = _sha256_bytes(data)
    rehash: dict[str, str] = {}
    for name in sorted(WORKER_EXPORT_ALLOWLIST):
        rehash[name] = _sha256_bytes(reader(generation_dir / name))
    if rehash != hashes:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "seal re-hash mismatch",
            state="FAILED_FROZEN",
        )
    return hashes


def sealed_inventory_sha256(hashes: dict[str, str]) -> str:
    return sha256_hex(canonical_bytes(hashes))


def bind_observed_identity(
    *,
    observed_commit: str,
    observed_tree: str,
    sealed_commit_bytes: str,
    sealed_tree_bytes: str,
    finalization_commit: str,
    finalization_tree: str,
    bundle_heads: Iterable[str],
) -> None:
    if sealed_commit_bytes.strip() != observed_commit:
        raise WorkerError(
            ERROR_CODES["SEAL_BIND_MISMATCH"],
            "observe T + seal T' before attestation write",
            state="FAILED_FROZEN",
        )
    if sealed_tree_bytes.strip() != observed_tree:
        raise WorkerError(
            ERROR_CODES["SEAL_BIND_MISMATCH"],
            "sealed candidate_tree != observed",
            state="FAILED_FROZEN",
        )
    if finalization_commit != observed_commit or finalization_tree != observed_tree:
        raise WorkerError(
            ERROR_CODES["SEAL_BIND_MISMATCH"],
            "finalization_result identity != observed",
            state="FAILED_FROZEN",
        )
    heads = list(bundle_heads)
    if "refs/heads/srl-candidate" not in heads and not any(
        h.startswith("refs/heads/srl-candidate") for h in heads
    ):
        raise WorkerError(
            ERROR_CODES["SEAL_BIND_MISMATCH"],
            "bundle missing refs/heads/srl-candidate",
            state="FAILED_FROZEN",
        )
