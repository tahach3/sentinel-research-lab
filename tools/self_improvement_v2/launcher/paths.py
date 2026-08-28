"""Canonical out-of-repo launcher install locations."""

from __future__ import annotations

import os
from pathlib import Path

LAUNCHER_DIR_NAME = "SentinelResearchLab"
LAUNCHER_PS1_NAME = "launch-worker.ps1"
LAUNCHER_SH_NAME = "launch-worker.sh"
ATTESTATION_NAME = "launcher-attestation.json"
VERIFIER_REL = Path("tools/self_improvement_v2/trusted_origin.py")
CONTAINER_SECRET_PREFIX = "/run/secrets"
HOST_SECRETS_DIRNAME = "secrets"


def default_launcher_dir() -> Path:
    """Return the out-of-repo launcher directory (never inside a git checkout)."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / LAUNCHER_DIR_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / LAUNCHER_DIR_NAME
    return Path.home() / ".local" / "share" / LAUNCHER_DIR_NAME


def default_host_secret_dir() -> Path:
    """Windows-safe host secret dir under the launcher install dir — never /run/secrets."""
    return default_launcher_dir() / HOST_SECRETS_DIRNAME


def is_container_secret_path(path: str | Path) -> bool:
    text = str(path).replace("\\", "/")
    if text.startswith("//"):
        text = "/" + text.lstrip("/")
    lowered = text.lower()
    return lowered == CONTAINER_SECRET_PREFIX or lowered.startswith(CONTAINER_SECRET_PREFIX + "/")


def assert_host_secret_path(path: str | Path) -> Path:
    if is_container_secret_path(path):
        raise ValueError("host secret path must not be a container /run/secrets path")
    resolved = Path(path).expanduser()
    if is_container_secret_path(resolved):
        raise ValueError("host secret path must not be a container /run/secrets path")
    return resolved


def assert_outside_repository(install_dir: Path, repository_root: Path) -> None:
    install = install_dir.resolve()
    repo = repository_root.resolve()
    try:
        install.relative_to(repo)
    except ValueError:
        return
    raise ValueError(
        f"launcher install dir must be outside the repository under review: {install} is under {repo}"
    )
