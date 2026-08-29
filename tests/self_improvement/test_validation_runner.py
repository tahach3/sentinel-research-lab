"""Validation profile confinement tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.self_improvement.helpers import init_temp_repo
from tools.self_improvement.models import WorkerError
from tools.self_improvement.policy import load_policy
from tools.self_improvement.validation_runner import run_validation_profile

ROOT = Path(__file__).resolve().parents[2]


def test_prohibited_validation_profile(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    with pytest.raises(WorkerError) as exc:
        run_validation_profile(policy=policy, profile_name="NOT_A_PROFILE", cwd=repo)
    assert exc.value.code == "PROHIBITED_VALIDATION_PROFILE"


def test_arbitrary_command_injection_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    with pytest.raises(WorkerError) as exc:
        run_validation_profile(
            policy=policy,
            profile_name="DOCUMENTATION_ONLY; rm -rf /",
            cwd=repo,
        )
    assert exc.value.code == "COMMAND_INJECTION"


def test_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    # Force tiny timeout and a hanging handler by patching subprocess.run
    import tools.self_improvement.validation_runner as vr
    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=0.01)

    monkeypatch.setattr(vr.subprocess, "run", fake_run)
    with pytest.raises(WorkerError) as exc:
        run_validation_profile(policy=policy, profile_name="DOCUMENTATION_ONLY", cwd=repo)
    assert exc.value.code == "VALIDATION_TIMEOUT"


def test_failed_acceptance_test(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    # Remove docs so DOCUMENTATION_ONLY fails
    import shutil

    shutil.rmtree(repo / "docs")
    policy = load_policy(ROOT)
    with pytest.raises(WorkerError) as exc:
        run_validation_profile(policy=policy, profile_name="DOCUMENTATION_ONLY", cwd=repo)
    assert exc.value.code == "ACCEPTANCE_FAILED"
