"""Zone P harness — synthetic NC reaches reviewer boundary, not path validator."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import REAL_ROOT, build_pass_review, init_temp_repo
from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.path_policy import assert_path_allowed, load_policy
from tools.self_improvement_v2.schema_loader import _load_schema_cached, validate_instance
from tools.self_improvement_v2.zone_p_harness import (
    DURABLE_STATE_DB_BASENAME,
    TARGET_PATH,
    ZonePHarnessError,
    allocate_zone_p_state_db,
    assert_throwaway_zone_p_state_db,
    build_synthetic_nc_package,
    inject_at_reviewer_boundary,
    tag_review_result,
)


@pytest.fixture(autouse=True)
def _clear_schema_cache() -> None:
    _load_schema_cached.cache_clear()


def test_throwaway_db_rejects_durable_basename(tmp_path: Path) -> None:
    bad = tmp_path / DURABLE_STATE_DB_BASENAME
    with pytest.raises(ZonePHarnessError) as exc:
        assert_throwaway_zone_p_state_db(bad)
    assert exc.value.code == ERROR_CODES["ZONE_P_HARNESS"]


def test_allocate_zone_p_state_db_under_temp() -> None:
    path = allocate_zone_p_state_db(probe_id="nc1")
    assert path.name.startswith("srl-zone-p-")
    assert_throwaway_zone_p_state_db(path)


def test_synthetic_nc_reaches_reviewer_boundary_not_path_validator(tmp_path: Path) -> None:
    repo = tmp_path / "sentinel-research-lab"
    baseline = init_temp_repo(repo)
    # Ensure docs/** allowlist target is creatable (file absent → CREATE).
    assert not (repo / TARGET_PATH).exists()

    package = build_synthetic_nc_package(
        probe_id="nc-repair-1",
        defect="repair_limit_contradiction",
        baseline_sha=baseline,
        root=repo,
    )
    assert package["path_validation"] == "PASSED"
    assert package["patch_validation"] == "PASSED"
    assert package["synthetic_control"] is True
    assert package["probe_id"] == "nc-repair-1"
    assert package["execution_bundle"]["actual_diff_sha256"]
    assert "MAXIMUM_REPAIR_ATTEMPTS=1" in package["review_package"]["synthetic_diff"]
    assert "MAXIMUM_REPAIR_ATTEMPTS=0" in package["review_package"]["objective"]

    # Path policy still accepts the target — defect is semantic only.
    policy = load_policy(repo)
    assert_path_allowed(TARGET_PATH, policy, package["proposal"], repo_root=repo)

    injection = inject_at_reviewer_boundary(package)
    assert injection["boundary"] == "independent_reviewer_agent"
    assert injection["rejected_by_path_validator"] is False
    assert injection["path_validation"] == "PASSED"
    assert injection["reviewer_invoked_required"] is True
    assert injection["synthetic_control"] is True
    assert injection["review_package"]["defect_kind"] == "repair_limit_contradiction"


def test_synthetic_nc_against_real_docs_modify() -> None:
    """When the target file exists, harness builds a MODIFY package that still validates."""
    baseline = os.popen(f'git -C "{REAL_ROOT}" rev-parse HEAD').read().strip()
    package = build_synthetic_nc_package(
        probe_id="nc-real-docs",
        defect="temp_state_db_contradiction",
        baseline_sha=baseline,
        root=REAL_ROOT,
    )
    assert package["proposal"]["patches"][0]["operation"] == "MODIFY"
    injection = inject_at_reviewer_boundary(package)
    assert injection["rejected_by_path_validator"] is False


def test_tag_review_result_schema(tmp_path: Path) -> None:
    repo = tmp_path / "sentinel-research-lab"
    baseline = init_temp_repo(repo)
    package = build_synthetic_nc_package(
        probe_id="tag-1",
        defect="repair_limit_contradiction",
        baseline_sha=baseline,
        root=repo,
    )
    review = build_pass_review(package["execution_bundle"], package["proposal"], review_id="rev-zone-p-1")
    # PASS review with findings empty — tagging must still schema-validate.
    tagged = tag_review_result(review, probe_id="tag-1", synthetic_control=True)
    assert tagged["synthetic_control"] is True
    assert tagged["probe_id"] == "tag-1"
    validate_instance("review_result", tagged, root=repo)
    validate_instance("execution_bundle", package["execution_bundle"], root=repo)


def test_inject_requires_path_pass() -> None:
    with pytest.raises(ZonePHarnessError):
        inject_at_reviewer_boundary(
            {
                "synthetic_control": True,
                "probe_id": "x",
                "path_validation": "FAILED",
                "patch_validation": "PASSED",
                "review_package": {},
            }
        )
