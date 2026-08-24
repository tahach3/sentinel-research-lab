"""Loopback-only runtime configuration for the Self-Improvement V2 worker bridge."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.topology_identity import ATTESTOR_ORIGIN

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_REQUEST_BYTES = 256 * 1024
REQUEST_TIMEOUT_SECONDS = 120
REPOSITORY_ID = "sentinel-research-lab"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
FORBIDDEN_BIND_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*"})
RUNTIME_MODES = frozenset({"ZONE_P", "P3C1"})

P3C1_STATE_DB = Path("/srl/state/self-improvement-v2.sqlite")
P3C1_TMPDIR = Path("/tmp/srl-exec/runtime-tmp")
P3C1_EXEC_ROOT = Path("/tmp/srl-exec")
ZONE_P_TMPDIR = Path("/tmp/srl-zone-p")

_ENV_TOKEN = "SRL_WORKER_TOKEN"
_ENV_TOKEN_FILE = "SRL_WORKER_TOKEN_FILE"
_ENV_CONSUME_TOKEN_FILE = "SRL_TOPOLOGY_CONSUME_TOKEN_FILE"
_ENV_ATTESTOR_ORIGIN = "SRL_TOPOLOGY_ATTESTOR_ORIGIN"
_ENV_ROOT = "SRL_REPOSITORY_ROOT"
_ENV_DB = "SRL_STATE_DB"
_ENV_HOST = "SRL_WORKER_HOST"
_ENV_PORT = "SRL_WORKER_PORT"
_ENV_RUNTIME_MODE = "SRL_RUNTIME_MODE"

DEFAULT_TOKEN_FILE = "/run/secrets/srl_worker_token"
DEFAULT_CONSUME_TOKEN_FILE = "/run/secrets/srl_topology_consume_token"
DEFAULT_ATTESTOR_ORIGIN = ATTESTOR_ORIGIN

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
    topology_attestor_origin: str = DEFAULT_ATTESTOR_ORIGIN
    topology_consume_credential: str = ""
    runtime_mode: str = ""

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


def _read_secret_file(path_raw: str, name: str) -> str:
    path = Path(path_raw).expanduser()
    if not path.is_file():
        raise RuntimeConfigError(f"{name} is not a readable secret file")
    token = path.read_text(encoding="utf-8").strip()
    if not token or any(ch.isspace() for ch in token):
        raise RuntimeConfigError(f"{name} must contain a single-line secret")
    return token


def _norm_path(value: str | Path) -> Path:
    return Path(os.path.normpath(str(value)))


def _assert_runtime_mode(mode: str, state_db: Path, environ: dict[str, str]) -> str:
    if not mode:
        return ""
    if mode not in RUNTIME_MODES:
        raise RuntimeConfigError("SRL_RUNTIME_MODE must be ZONE_P or P3C1")
    if str(environ.get("PYTHONDONTWRITEBYTECODE") or "") != "1":
        raise RuntimeConfigError("PYTHONDONTWRITEBYTECODE=1 is required")
    tmpdir_raw = str(environ.get("TMPDIR") or "").strip()
    if not tmpdir_raw:
        raise RuntimeConfigError("TMPDIR is required when SRL_RUNTIME_MODE is set")
    db = _norm_path(state_db)
    tmpdir = _norm_path(tmpdir_raw)
    db_text = str(db)
    if mode == "P3C1":
        if db != P3C1_STATE_DB:
            raise RuntimeConfigError("P3C1 SRL_STATE_DB must be /srl/state/self-improvement-v2.sqlite")
        if tmpdir != P3C1_TMPDIR:
            raise RuntimeConfigError("P3C1 TMPDIR must be /tmp/srl-exec/runtime-tmp")
        if "/tmp/srl-zone-p" in db_text:
            raise RuntimeConfigError("P3C1 must not use the Zone P state directory")
        return mode
    if tmpdir != ZONE_P_TMPDIR:
        raise RuntimeConfigError("Zone P TMPDIR must be /tmp/srl-zone-p")
    if _norm_path(db.parent) != ZONE_P_TMPDIR:
        raise RuntimeConfigError("Zone P state DB must live under /tmp/srl-zone-p")
    name = db.name
    if not name.startswith("srl-zone-p-") or not name.endswith(".sqlite"):
        raise RuntimeConfigError("Zone P state DB basename must be srl-zone-p-<id>.sqlite")
    if "/srl/state" in db_text or db_text.startswith("/tmp/srl-exec"):
        raise RuntimeConfigError("Zone P must not use P3C1 writable surfaces")
    return mode


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
    # Blank/whitespace SRL_REPOSITORY_ROOT is absent — never an open R4 gate.
    env_root_raw = env.get(_ENV_ROOT)
    if env_root_raw is not None and not str(env_root_raw).strip():
        env_root_raw = None
    elif env_root_raw is not None:
        env_root_raw = str(env_root_raw).strip()

    root_raw = repository_root if repository_root is not None else env_root_raw
    db_raw = state_db if state_db is not None else env.get(_ENV_DB)
    token_file = str(env.get(_ENV_TOKEN_FILE) or "").strip()
    if token_file:
        token = _read_secret_file(token_file, _ENV_TOKEN_FILE)
    else:
        token_raw = worker_token if worker_token is not None else env.get(_ENV_TOKEN)
        token = _require_non_empty(_ENV_TOKEN, token_raw)
        if any(ch.isspace() for ch in token):
            raise RuntimeConfigError("SRL_WORKER_TOKEN must not contain whitespace")
    consume_file = str(env.get(_ENV_CONSUME_TOKEN_FILE) or "").strip()
    consume_cred = _read_secret_file(consume_file, _ENV_CONSUME_TOKEN_FILE) if consume_file else ""
    attestor_origin = str(env.get(_ENV_ATTESTOR_ORIGIN) or DEFAULT_ATTESTOR_ORIGIN).strip().rstrip("/")
    if attestor_origin != DEFAULT_ATTESTOR_ORIGIN:
        raise RuntimeConfigError("SRL_TOPOLOGY_ATTESTOR_ORIGIN must equal the pinned host-gateway origin")
    host_raw = worker_host if worker_host is not None else env.get(_ENV_HOST, DEFAULT_HOST)
    port_raw = worker_port if worker_port is not None else env.get(_ENV_PORT, str(DEFAULT_PORT))

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
    mode = str(env.get(_ENV_RUNTIME_MODE) or "").strip()
    db_input = Path(_require_non_empty(_ENV_DB, db_raw))
    _assert_runtime_mode(mode, db_input, env)
    db = _assert_state_db(db_input, root)
    host = _assert_loopback_host(_require_non_empty(_ENV_HOST, host_raw))
    port = _assert_port(str(port_raw))

    return RuntimeConfig(
        repository_root=root,
        state_db=db,
        worker_token=token,
        worker_host=host,
        worker_port=port,
        topology_attestor_origin=attestor_origin,
        topology_consume_credential=consume_cred,
        runtime_mode=mode,
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
