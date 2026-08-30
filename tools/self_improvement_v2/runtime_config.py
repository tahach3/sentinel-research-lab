"""Loopback-only runtime configuration for the Self-Improvement V2 worker bridge."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_controller import Rev25RuntimeDeps

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_REQUEST_BYTES = 256 * 1024
REQUEST_TIMEOUT_SECONDS = 120
REPOSITORY_ID = "sentinel-research-lab"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
FORBIDDEN_BIND_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*"})

_ENV_TOKEN = "SRL_WORKER_TOKEN"
_ENV_ROOT = "SRL_REPOSITORY_ROOT"
_ENV_DB = "SRL_STATE_DB"
_ENV_HOST = "SRL_WORKER_HOST"
_ENV_PORT = "SRL_WORKER_PORT"
_ENV_WORKER_CID = "SRL_WORKER_CONTAINER_ID"
_ENV_N8N_CID = "SRL_N8N_CONTAINER_ID"
_ENV_IMAGE = "SRL_WORKER_IMAGE_DIGEST"

_FORBIDDEN_ROOT_NAMES = frozenset({"equitify-machine", "ai-development-os"})
_ABS_PATH_RE = re.compile(r"(?i)[A-Za-z]:[\\/]|/(?:Users|home|var|tmp|private)/")
_CREDENTIAL_LIKE_RE = re.compile(
    r"(?i)(authorization|bearer\s+[A-Za-z0-9._\-+=/]{8,}|api[_-]?key|secret|password|token\s*[:=]\s*\S+)"
)


class RuntimeConfigError(WorkerError):
    """Configuration rejected before the bridge accepts traffic."""

    def __init__(self, message: str) -> None:
        super().__init__(ERROR_CODES["POLICY_REJECTED"], message, state="POLICY_REJECTED")


@dataclass(frozen=True)
class RuntimeConfig:
    repository_root: Path
    state_db: Path
    worker_token: str
    worker_host: str
    worker_port: int
    max_request_bytes: int = MAX_REQUEST_BYTES
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS
    rev25_deps: Any = None

    @property
    def repository_id(self) -> str:
        return REPOSITORY_ID


def _require_non_empty(name: str, value: str | None) -> str:
    if value is None or not str(value).strip():
        raise RuntimeConfigError(f"{name} is required")
    return str(value).strip()


def _assert_loopback_host(host: str) -> str:
    normalized = host.strip().lower()
    if normalized in FORBIDDEN_BIND_HOSTS or normalized.endswith("%"):
        raise RuntimeConfigError("worker host must remain loopback-only")
    if normalized not in LOOPBACK_HOSTS:
        raise RuntimeConfigError("worker host must be 127.0.0.1 or localhost")
    # Canonical bind address — never "::1" dual-stack public expansion.
    return "127.0.0.1"


def _assert_port(raw: str) -> int:
    try:
        port = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigError("SRL_WORKER_PORT must be an integer") from exc
    # Port 0 is allowed only for ephemeral local test binds; production uses 1–65535.
    if port < 0 or port > 65535:
        raise RuntimeConfigError("SRL_WORKER_PORT out of range")
    return port


def _assert_repository_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise RuntimeConfigError("SRL_REPOSITORY_ROOT must be an existing directory")
    if resolved.name in _FORBIDDEN_ROOT_NAMES:
        raise RuntimeConfigError("repository root is outside Research Lab boundaries")
    if resolved.name != REPOSITORY_ID:
        raise RuntimeConfigError("repository root must resolve to sentinel-research-lab")
    marker = resolved / "specs" / "self_improvement" / "v2" / "policy.json"
    if not marker.is_file():
        raise RuntimeConfigError("repository root missing Self-Improvement V2 policy")
    git_dir = resolved / ".git"
    if not git_dir.exists():
        raise RuntimeConfigError("repository root must be a git checkout")
    return resolved


def _assert_state_db(state_db: Path, repository_root: Path) -> Path:
    resolved = state_db.expanduser().resolve()
    if resolved.exists() and resolved.is_dir():
        raise RuntimeConfigError("SRL_STATE_DB must be a file path")
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        pass
    else:
        # Inside the repository tree — only allow if clearly outside tracked content
        # by requiring the parent path to be outside the repo OR under an explicit
        # non-tracked runtime directory name. Prefer hard outside-repo placement.
        raise RuntimeConfigError("state database must be outside tracked repository files")
    parent = resolved.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir():
        raise RuntimeConfigError("state database parent could not be created")
    return resolved


def _require_operator_value(name: str, value: str | None) -> str:
    if value is None or not str(value).strip():
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            f"{name} is required",
            state="FAILED_FROZEN",
        )
    return str(value).strip()


def _parse_docker_inspect_stdout(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "docker inspect returned non-JSON",
            state="FAILED_FROZEN",
        ) from exc
    if isinstance(payload, list):
        if not payload:
            raise WorkerError(
                ERROR_CODES["FAILED_FROZEN"],
                "docker inspect returned an empty list",
                state="FAILED_FROZEN",
            )
        payload = payload[0]
    if not isinstance(payload, dict):
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "docker inspect returned a non-object",
            state="FAILED_FROZEN",
        )
    return payload


def _build_rev25_runtime_deps(
    *,
    environ: dict[str, str],
    docker_runner: Any,
) -> Rev25RuntimeDeps:
    from tools.self_improvement_v2.docker_cli import (
        docker_inspect_argv,
        docker_ps_all_ids_argv,
        require_container_id,
        run_docker_argv,
    )
    from tools.self_improvement_v2.topology_identity import normalize_image_digest

    runner = docker_runner if docker_runner is not None else run_docker_argv
    worker_id = require_container_id(
        _require_operator_value(_ENV_WORKER_CID, environ.get(_ENV_WORKER_CID))
    )
    n8n_id = require_container_id(
        _require_operator_value(_ENV_N8N_CID, environ.get(_ENV_N8N_CID))
    )
    digest = normalize_image_digest(
        _require_operator_value(_ENV_IMAGE, environ.get(_ENV_IMAGE))
    )

    def inspect_one(cid: str) -> dict[str, Any]:
        argv = docker_inspect_argv(cid)
        code, out, err = runner(argv)
        if code != 0:
            raise WorkerError(
                ERROR_CODES["FAILED_FROZEN"],
                (err or "docker inspect failed").strip(),
                state="FAILED_FROZEN",
            )
        return _parse_docker_inspect_stdout(out)

    def list_all_ids() -> list[str]:
        argv = docker_ps_all_ids_argv()
        code, out, err = runner(argv)
        if code != 0:
            raise WorkerError(
                ERROR_CODES["FAILED_FROZEN"],
                (err or "docker ps failed").strip(),
                state="FAILED_FROZEN",
            )
        return [line.strip().lower() for line in out.splitlines() if line.strip()]

    return Rev25RuntimeDeps(
        inspect_worker=inspect_one,
        inspect_n8n=inspect_one,
        list_all_ids=list_all_ids,
        worker_id=worker_id,
        n8n_id=n8n_id,
        expected_image_digest=digest,
    )


def load_runtime_config(
    *,
    repository_root: str | None = None,
    state_db: str | None = None,
    worker_token: str | None = None,
    worker_host: str | None = None,
    worker_port: str | int | None = None,
    environ: dict[str, str] | None = None,
    docker_runner: Any = None,
) -> RuntimeConfig:
    env = environ if environ is not None else os.environ
    # Blank/whitespace SRL_REPOSITORY_ROOT is absent — never an open R4 gate.
    env_root_raw = env.get(_ENV_ROOT)
    if env_root_raw is not None and not str(env_root_raw).strip():
        env_root_raw = None
    elif env_root_raw is not None:
        env_root_raw = str(env_root_raw).strip()

    root_raw = repository_root if repository_root is not None else env_root_raw
    db_raw = state_db if state_db is not None else env.get(_ENV_DB)
    token_raw = worker_token if worker_token is not None else env.get(_ENV_TOKEN)
    host_raw = worker_host if worker_host is not None else env.get(_ENV_HOST, DEFAULT_HOST)
    port_raw = worker_port if worker_port is not None else env.get(_ENV_PORT, str(DEFAULT_PORT))

    token = _require_non_empty(_ENV_TOKEN, token_raw)
    if any(ch.isspace() for ch in token):
        raise RuntimeConfigError("SRL_WORKER_TOKEN must not contain whitespace")

    # R4: refuse divergent roots at the config loader — not only in main().
    # Every caller (CLI, library, tests) hits this path; "main-only" guards decay.
    # Trusted install root must be present (blank ≡ missing) whenever a CLI/kwarg
    # root is supplied; otherwise the equality gate would open by accident.
    if repository_root is not None:
        trusted_raw = _require_non_empty(_ENV_ROOT, env_root_raw)
        cli_root = Path(repository_root).expanduser().resolve()
        trusted = Path(trusted_raw).expanduser().resolve()
        if cli_root != trusted:
            raise RuntimeConfigError(
                "repository_root must equal SRL_REPOSITORY_ROOT (trusted install root)"
            )

    root = _assert_repository_root(Path(_require_non_empty(_ENV_ROOT, root_raw)))
    if env_root_raw is not None:
        trusted = Path(env_root_raw).expanduser().resolve()
        if root != trusted:
            raise RuntimeConfigError(
                "repository_root must equal SRL_REPOSITORY_ROOT (trusted install root)"
            )
    db = _assert_state_db(Path(_require_non_empty(_ENV_DB, db_raw)), root)
    host = _assert_loopback_host(_require_non_empty(_ENV_HOST, host_raw))
    port = _assert_port(str(port_raw))

    return RuntimeConfig(
        repository_root=root,
        state_db=db,
        worker_token=token,
        worker_host=host,
        worker_port=port,
        rev25_deps=_build_rev25_runtime_deps(environ=dict(env), docker_runner=docker_runner),
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Self-Improvement V2 loopback worker bridge")
    parser.add_argument("--repository-root", default=None, help="Overrides SRL_REPOSITORY_ROOT")
    parser.add_argument("--state-db", default=None, help="Overrides SRL_STATE_DB")
    parser.add_argument("--host", default=None, help="Overrides SRL_WORKER_HOST")
    parser.add_argument("--port", default=None, help="Overrides SRL_WORKER_PORT")
    # Token is environment-only — never accept as a CLI flag (avoids shell history leaks).
    return parser


def redact_log_text(text: str) -> str:
    """Redact tokens, auth headers, absolute paths, and credential-like values."""
    redacted = _CREDENTIAL_LIKE_RE.sub("[REDACTED]", text)
    redacted = _ABS_PATH_RE.sub("[REDACTED_PATH]", redacted)
    return redacted


def is_forbidden_request_field(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    forbidden = {
        "repository_root",
        "repo_root",
        "root",
        "state_db",
        "state_database",
        "db_path",
        "database_path",
        "command",
        "commands",
        "shell",
        "env",
        "environment",
        "environ",
        "cwd",
        "workdir",
        "worktree",
        "git_command",
        "token",
        "worker_token",
        "authorization",
    }
    return normalized in forbidden
