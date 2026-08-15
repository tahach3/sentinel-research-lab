"""Shared fixtures for Self-Improvement V2 tests."""

from __future__ import annotations

import subprocess

import pytest

from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.trusted_origin import ENV_REPOSITORY_ROOT, ENV_REVIEWED_HEAD


@pytest.fixture(autouse=True)
def _srl_trusted_origin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Launcher anchors for in-process tests (external R5 probes clear these explicitly)."""
    root = worker_package_root()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(root))
    monkeypatch.setenv(ENV_REVIEWED_HEAD, head)
