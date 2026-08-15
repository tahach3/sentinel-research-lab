"""Shared fixtures for Self-Improvement V2 tests."""

from __future__ import annotations

import json

import pytest

from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.trusted_origin import ENV_REPOSITORY_ROOT, ENV_REVIEWED_HEAD, PIN_REL


@pytest.fixture(autouse=True)
def _srl_trusted_origin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Launcher anchors for in-process tests (external R5 probes clear these explicitly)."""
    root = worker_package_root()
    pin = json.loads((root / PIN_REL).read_text(encoding="utf-8"))
    reviewed = pin.get("reviewed_git_head")
    if not isinstance(reviewed, str) or len(reviewed) < 40:
        raise RuntimeError("trusted_origin_pin.json missing reviewed_git_head for test env")
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(root))
    monkeypatch.setenv(ENV_REVIEWED_HEAD, reviewed)
