"""Loopback-only runtime configuration for the Self-Improvement V2 worker bridge."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

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


def load_runtime_config(
    *,
    repository_root: str | None = None,
    state_db: str | None = None,
    worker_token: str | None = None,
    worker_host: str | None = None,
    worker_port: str | int | None = None,
    environ: dict[str, str] | None = None,
) -> RuntimeConfig:
    env = environ if environ is not None else os.environ
    root_raw = repository_root if repository_root is not None else env.get(_ENV_ROOT)
    db_raw = state_db if state_db is not None else env.get(_ENV_DB)
    token_raw = worker_token if worker_token is not None else env.get(_ENV_TOKEN)
    host_raw = worker_host if worker_host is not None else env.get(_ENV_HOST, DEFAULT_HOST)
    port_raw = worker_port if worker_port is not None else env.get(_ENV_PORT, str(DEFAULT_PORT))

    token = _require_non_empty(_ENV_TOKEN, token_raw)
    if any(ch.isspace() for ch in token):
        raise RuntimeConfigError("SRL_WORKER_TOKEN must not contain whitespace")

    root = _assert_repository_root(Path(_require_non_empty(_ENV_ROOT, root_raw)))
    db = _assert_state_db(Path(_require_non_empty(_ENV_DB, db_raw)), root)
    host = _assert_loopback_host(_require_non_empty(_ENV_HOST, host_raw))
    port = _assert_port(str(port_raw))

    return RuntimeConfig(
        repository_root=root,
        state_db=db,
        worker_token=token,
        worker_host=host,
        worker_port=port,
    )


def assert_cli_repository_root_matches_launcher(
    cli_repository_root: str | None,
    *,
    environ: dict[str, str] | None = None,
) -> None:
    """Refuse --repository-root that diverges from launcher SRL_REPOSITORY_ROOT (R4)."""
    if cli_repository_root is None or not str(cli_repository_root).strip():
        return
    env = environ if environ is not None else os.environ
    env_root = env.get(_ENV_ROOT)
    if not env_root or not str(env_root).strip():
        return
    cli = Path(cli_repository_root).expanduser().resolve()
    trusted = Path(str(env_root).strip()).expanduser().resolve()
    if cli != trusted:
        raise RuntimeConfigError(
            "repository_root must equal SRL_REPOSITORY_ROOT (trusted install root)"
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
