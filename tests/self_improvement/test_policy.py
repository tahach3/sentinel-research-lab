"""Autonomous-lane policy tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.self_improvement.models import WorkerError
from tools.self_improvement.policy import assert_path_allowed, classify_and_authorize, load_policy

ROOT = Path(__file__).resolve().parents[2]


def test_policy_loads_limits_and_profiles() -> None:
    policy = load_policy(ROOT)
    lane = policy["autonomous_lane"]
    assert lane["limits"]["maximum_changed_files"] == 8
    assert lane["limits"]["deletion_allowed"] is False
    assert lane["limits"]["push_allowed"] is False
    assert "LOW" in lane["auto_authorize_risk_levels"]
    assert "SELF_IMPROVEMENT_TESTS" in policy["validation_profiles"]


def test_forbidden_and_migration_paths() -> None:
    policy = load_policy(ROOT)
    with pytest.raises(WorkerError) as exc:
        assert_path_allowed("database/migrations/009_x.sql", policy)
    assert exc.value.code == "MIGRATION_PATH"
    with pytest.raises(WorkerError) as exc2:
        assert_path_allowed("tools/round5a_kernel/models.py", policy)
    assert exc2.value.code == "FORBIDDEN_PATH"


def test_medium_risk_not_auto_authorized() -> None:
    policy = load_policy(ROOT)
    proposal = {
        "risk_level": "MEDIUM",
        "human_approval_required": False,
        "allowed_paths": ["docs/**"],
        "forbidden_paths": [],
        "patches": [
            {
                "path": "docs/x.md",
                "operation": "CREATE",
            }
        ],
    }
    with pytest.raises(WorkerError) as exc:
        classify_and_authorize(proposal, policy)
    assert exc.value.code == "RISK_NOT_AUTO_AUTHORIZED"
    assert exc.value.state == "DECISION_REQUIRED"
