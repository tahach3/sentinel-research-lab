"""Docker argv construction: exact 64-hex IDs only. Prefix joiners forbidden."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Callable

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import (
    CONTAINER_ID_RE,
    EXECUTION_ID_RE,
    STAGING_GENERATION_RE,
    WORKER_EXPORT_ALLOWLIST,
)

DockerRunner = Callable[[list[str]], tuple[int, str, str]]

_SEALED_REMOTE = re.compile(
    r"^([a-f0-9]{64}):(/tmp/srl-exec/[a-f0-9]{32}/export/[a-f0-9]{8}/([^/\\:]+))$"
)
_SEALED_EXPORT_DIR = re.compile(r"^/tmp/srl-exec/[a-f0-9]{32}/export/[a-f0-9]{8}$")
_SEALED_FILE_PATH = re.compile(
    r"^/tmp/srl-exec/[a-f0-9]{32}/export/[a-f0-9]{8}/([^/\\:]+)$"
)
_SEALED_REPO = re.compile(r"^/tmp/srl-exec/[a-f0-9]{32}/repo$")
_SEALED_BUNDLE = re.compile(
    r"^/tmp/srl-exec/[a-f0-9]{32}/export/[a-f0-9]{8}/candidate\.bundle$"
)
_ALLOWED_GIT_ISOLATION = {"GIT_OPTIONAL_LOCKS": "0"}
_ALLOWED_GIT_OBSERVE = {
    ("rev-parse", "--verify", "HEAD"),
    ("rev-parse", "--verify", "HEAD^{tree}"),
    ("show", "-s", "--format=%H", "refs/heads/srl-candidate"),
}


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


def docker_ps_all_ids_argv() -> list[str]:
    return ["docker", "ps", "--all", "--quiet", "--no-trunc"]


def _frozen(message: str) -> WorkerError:
    return WorkerError(
        ERROR_CODES["FAILED_FROZEN"],
        message,
        state="FAILED_FROZEN",
    )


def _assert_allowlisted_name(name: str) -> str:
    if name in {".", ".."} or "/" in name or "\\" in name or ":" in name or " " in name:
        raise WorkerError(
            ERROR_CODES["NON_REGULAR_ARTIFACT"],
            f"illegal export name: {name}",
            state="FAILED_FROZEN",
        )
    if name not in WORKER_EXPORT_ALLOWLIST:
        raise WorkerError(
            ERROR_CODES["NON_REGULAR_ARTIFACT"],
            f"illegal export name: {name}",
            state="FAILED_FROZEN",
        )
    return name


def _assert_execution_id(execution_id: str) -> str:
    if not EXECUTION_ID_RE.fullmatch(execution_id):
        raise WorkerError(
            ERROR_CODES["EXECUTION_ID_GRAMMAR"],
            "SRL_EXECUTION_ID must be 32 hex",
            state="FAILED_FROZEN",
        )
    return execution_id


def _assert_generation(generation: str) -> str:
    if not STAGING_GENERATION_RE.fullmatch(generation):
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "STAGING_GENERATION must be 8 hex",
            state="FAILED_FROZEN",
        )
    return generation


def _assert_host_path_not_worker_exec(path: str) -> str:
    if path.replace("\\", "/").startswith("/tmp/srl-exec"):
        raise WorkerError(
            ERROR_CODES["HOST_TMP_SRL_EXEC"],
            "host must not treat /tmp/srl-exec as a host path",
            state="FAILED_FROZEN",
        )
    return path


def _sealed_remote(container_id: str, execution_id: str, generation: str, name: str) -> str:
    cid = require_container_id(container_id)
    eid = _assert_execution_id(execution_id)
    gen = _assert_generation(generation)
    artifact = _assert_allowlisted_name(name)
    return f"{cid}:/tmp/srl-exec/{eid}/export/{gen}/{artifact}"


def _sealed_export_dir(execution_id: str, generation: str) -> str:
    eid = _assert_execution_id(execution_id)
    gen = _assert_generation(generation)
    return f"/tmp/srl-exec/{eid}/export/{gen}"


def docker_exec_mkdir_argv(container_id: str, execution_id: str, generation: str) -> list[str]:
    cid = require_container_id(container_id)
    path = _sealed_export_dir(execution_id, generation)
    return ["docker", "exec", cid, "mkdir", "-p", path]


def docker_exec_cat_argv(
    container_id: str,
    execution_id: str,
    generation: str,
    name: str,
) -> list[str]:
    cid = require_container_id(container_id)
    artifact = _assert_allowlisted_name(name)
    path = f"{_sealed_export_dir(execution_id, generation)}/{artifact}"
    return ["docker", "exec", cid, "cat", path]


def docker_cp_into_worker_argv(
    container_id: str,
    execution_id: str,
    generation: str,
    name: str,
    src: Path,
) -> list[str]:
    src_s = _assert_host_path_not_worker_exec(str(src))
    dest = _sealed_remote(container_id, execution_id, generation, name)
    return ["docker", "cp", src_s, dest]


def _classify_docker_cp(argv: list[str]) -> tuple[str, str] | None:
    if len(argv) != 4 or argv[0] != "docker" or argv[1] != "cp":
        return None
    src, dest = argv[2], argv[3]
    refuse_directory_cp(argv)
    outbound = _SEALED_REMOTE.fullmatch(src)
    inbound = _SEALED_REMOTE.fullmatch(dest)
    if outbound is not None and inbound is None:
        if outbound.group(3) not in WORKER_EXPORT_ALLOWLIST:
            return None
        _assert_host_path_not_worker_exec(dest)
        return src, dest
    if inbound is not None and outbound is None:
        if inbound.group(3) not in WORKER_EXPORT_ALLOWLIST:
            return None
        _assert_host_path_not_worker_exec(src)
        return src, dest
    return None


def _split_docker_exec(argv: list[str]) -> tuple[dict[str, str], str, list[str]] | None:
    if len(argv) < 4 or argv[0] != "docker" or argv[1] != "exec":
        return None
    index = 2
    envs: dict[str, str] = {}
    while index + 1 < len(argv) and argv[index] == "--env":
        raw = argv[index + 1]
        if "=" not in raw:
            return None
        key, value = raw.split("=", 1)
        envs[key] = value
        index += 2
    if index >= len(argv):
        return None
    try:
        cid = require_container_id(argv[index])
    except WorkerError:
        return None
    return envs, cid, argv[index + 1 :]


def _classify_docker_exec(argv: list[str]) -> tuple[str, str, list[str]] | None:
    split = _split_docker_exec(argv)
    if split is None:
        return None
    envs, cid, cmd = split
    if cmd[:2] == ["mkdir", "-p"] and len(cmd) == 3:
        if envs:
            return None
        path = cmd[2]
        if _SEALED_EXPORT_DIR.fullmatch(path) or _SEALED_REPO.fullmatch(path):
            return "mkdir", cid, cmd
        return None
    if not cmd or cmd[0] != "git":
        return None
    if envs != _ALLOWED_GIT_ISOLATION:
        return None
    if cmd[:3] == ["git", "clone", "--branch"] and len(cmd) in {6, 7}:
        rest = cmd[3:]
        if rest[0] != "srl-candidate":
            return None
        if rest[1] == "--":
            rest = rest[2:]
        else:
            rest = rest[1:]
        if len(rest) != 2:
            return None
        bundle, repo = rest
        if _SEALED_BUNDLE.fullmatch(bundle) and _SEALED_REPO.fullmatch(repo):
            return "git-clone", cid, cmd
        return None
    if len(cmd) >= 4 and cmd[1] == "-C" and _SEALED_REPO.fullmatch(cmd[2]):
        git_args = tuple(cmd[3:])
        if git_args in _ALLOWED_GIT_OBSERVE:
            return "git-observe", cid, cmd
    return None


def _run_literal_docker(argv: list[str]) -> tuple[int, str, str]:
    """Sole docker process launcher. Argv[0] must be the literal docker executable."""
    if not argv or argv[0] != "docker":
        raise _frozen("docker runner requires docker argv")
    if len(argv) == 3 and argv[1] == "inspect":
        proc = subprocess.run(
            ["docker", "inspect", argv[2]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sanitized_docker_env(),
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    if argv[1:] == ["ps", "--all", "--quiet", "--no-trunc"]:
        proc = subprocess.run(
            ["docker", "ps", "--all", "--quiet", "--no-trunc"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sanitized_docker_env(),
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    if len(argv) == 4 and argv[1] == "cp":
        classified = _classify_docker_cp(argv)
        if classified is None:
            raise _frozen("unclassified docker argv")
        src, dest = classified
        proc = subprocess.run(
            ["docker", "cp", src, dest],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sanitized_docker_env(),
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    if len(argv) >= 4 and argv[1] == "exec":
        classified = _classify_docker_exec(argv)
        if classified is None:
            raise _frozen("unclassified docker argv")
        kind, cid, cmd = classified
        rebuilt = ["docker", "exec"]
        if kind.startswith("git"):
            rebuilt.extend(["--env", "GIT_OPTIONAL_LOCKS=0"])
        rebuilt.append(cid)
        rebuilt.extend(cmd)
        proc = subprocess.run(
            ["docker", *rebuilt[1:]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sanitized_docker_env(),
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    raise _frozen("unclassified docker argv")


def run_docker_argv(argv: list[str]) -> tuple[int, str, str]:
    return _run_literal_docker(argv)


def docker_exec_git_argv(
    container_id: str,
    execution_id: str,
    git_args: list[str],
    isolation_env: dict[str, str],
) -> list[str]:
    cid = require_container_id(container_id)
    eid = _assert_execution_id(execution_id)
    if isolation_env != _ALLOWED_GIT_ISOLATION:
        raise _frozen("docker exec git isolation must be GIT_OPTIONAL_LOCKS=0 only")
    if tuple(git_args) not in _ALLOWED_GIT_OBSERVE:
        raise _frozen("unclassified docker git observation argv")
    argv = ["docker", "exec", "--env", "GIT_OPTIONAL_LOCKS=0", cid, "git", "-C", f"/tmp/srl-exec/{eid}/repo", *git_args]
    if _classify_docker_exec(argv) is None:
        raise _frozen("unclassified docker git observation argv")
    return argv


def docker_exec_clone_bundle_argv(
    container_id: str,
    execution_id: str,
    generation: str,
) -> list[str]:
    cid = require_container_id(container_id)
    eid = _assert_execution_id(execution_id)
    gen = _assert_generation(generation)
    bundle = f"/tmp/srl-exec/{eid}/export/{gen}/candidate.bundle"
    repo = f"/tmp/srl-exec/{eid}/repo"
    argv = [
        "docker",
        "exec",
        "--env",
        "GIT_OPTIONAL_LOCKS=0",
        cid,
        "git",
        "clone",
        "--branch",
        "srl-candidate",
        "--",
        bundle,
        repo,
    ]
    if _classify_docker_exec(argv) is None:
        raise _frozen("unclassified docker git clone argv")
    return argv


def docker_exec_mkdir_repo_argv(container_id: str, execution_id: str) -> list[str]:
    cid = require_container_id(container_id)
    eid = _assert_execution_id(execution_id)
    return ["docker", "exec", cid, "mkdir", "-p", f"/tmp/srl-exec/{eid}/repo"]


def docker_cp_file_argv(
    container_id: str,
    execution_id: str,
    generation: str,
    name: str,
    dest: Path,
) -> list[str]:
    dest_s = _assert_host_path_not_worker_exec(str(dest))
    src = _sealed_remote(container_id, execution_id, generation, name)
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
