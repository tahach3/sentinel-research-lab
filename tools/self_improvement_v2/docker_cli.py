"""Docker argv construction: exact 64-hex IDs only. Prefix joiners forbidden."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import CONTAINER_ID_RE, EXECUTION_ID_RE, STAGING_GENERATION_RE

DockerRunner = Callable[[list[str]], tuple[int, str, str]]


def require_container_id(value: str) -> str:
    cid = (value or "").strip().lower()
    if cid.startswith("sha256:"):
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            "image digest is not a container id",
            state="FAILED_FROZEN",
        )
    if not CONTAINER_ID_RE.fullmatch(cid):
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            "docker argv requires exact 64-hex container id",
            state="FAILED_FROZEN",
        )
    return cid


def sanitized_docker_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC"):
        val = os.environ.get(key)
        if val:
            env[key] = val
    # Proxy env must not intercept attestor / docker (TOPO-04 / F7).
    return env


def resolve_unique_prefix(full_ids: list[str], prefix: str) -> str:
    """TOPO-03: 0/1/>1 unique prefix resolve. Result is 64-hex; never use prefix in argv."""
    p = prefix.strip().lower()
    if CONTAINER_ID_RE.fullmatch(p):
        if p in {i.lower() for i in full_ids}:
            return p
        raise WorkerError(
            ERROR_CODES["TOPOLOGY_REASSERT_FAILED"],
            "container id not in host-wide listing",
            state="FAILED_FROZEN",
        )
    if len(p) < 12:
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            "docker unique-prefix matching is forbidden for argv",
            state="FAILED_FROZEN",
        )
    matches = [i.lower() for i in full_ids if i.lower().startswith(p)]
    if len(matches) != 1:
        raise WorkerError(
            ERROR_CODES["DOCKER_PREFIX_ID"],
            f"prefix resolve is not unique ({len(matches)}); argv must be 64-hex",
            state="FAILED_FROZEN",
        )
    return matches[0]


def docker_inspect_argv(container_id: str) -> list[str]:
    return ["docker", "inspect", require_container_id(container_id)]


def docker_exec_git_argv(
    container_id: str,
    execution_id: str,
    git_args: list[str],
    isolation_env: dict[str, str],
) -> list[str]:
    cid = require_container_id(container_id)
    if not EXECUTION_ID_RE.fullmatch(execution_id):
        raise WorkerError(
            ERROR_CODES["EXECUTION_ID_GRAMMAR"],
            "SRL_EXECUTION_ID must be 32 hex",
            state="FAILED_FROZEN",
        )
    argv = ["docker", "exec"]
    for key, value in isolation_env.items():
        argv.extend(["--env", f"{key}={value}"])
    repo = f"/tmp/srl-exec/{execution_id}/repo"
    argv.extend([cid, "git", "-C", repo, *git_args])
    return argv


def docker_cp_file_argv(
    container_id: str,
    execution_id: str,
    generation: str,
    name: str,
    dest: Path,
) -> list[str]:
    cid = require_container_id(container_id)
    if not EXECUTION_ID_RE.fullmatch(execution_id):
        raise WorkerError(
            ERROR_CODES["EXECUTION_ID_GRAMMAR"],
            "SRL_EXECUTION_ID must be 32 hex",
            state="FAILED_FROZEN",
        )
    if not STAGING_GENERATION_RE.fullmatch(generation):
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "STAGING_GENERATION must be 8 hex",
            state="FAILED_FROZEN",
        )
    if name in {".", ".."} or "/" in name or "\\" in name or ":" in name or " " in name:
        raise WorkerError(
            ERROR_CODES["NON_REGULAR_ARTIFACT"],
            f"illegal export name: {name}",
            state="FAILED_FROZEN",
        )
    dest_s = str(dest)
    if dest_s.replace("\\", "/").startswith("/tmp/srl-exec"):
        raise WorkerError(
            ERROR_CODES["HOST_TMP_SRL_EXEC"],
            "host must not treat /tmp/srl-exec as a host path",
            state="FAILED_FROZEN",
        )
    src = f"{cid}:/tmp/srl-exec/{execution_id}/export/{generation}/{name}"
    return ["docker", "cp", src, dest_s]


def refuse_directory_cp(argv: list[str]) -> None:
    joined = " ".join(argv)
    if "docker" in argv and "cp" in argv:
        if "/." in joined or joined.rstrip().endswith("/export") or joined.rstrip().endswith("/export/"):
            raise WorkerError(
                ERROR_CODES["POLICY_REJECTED"],
                "directory-wide docker cp is forbidden",
                state="FAILED_FROZEN",
            )
