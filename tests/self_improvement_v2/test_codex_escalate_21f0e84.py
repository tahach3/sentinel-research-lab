"""Codex escalate adversarial probes against 21f0e84 — must FAIL before repair, PASS after.

R0-style: each probe asserts the repaired contract. Pre-fix code is red; post-fix is green.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
from pathlib import Path

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    IMPLEMENTER_NODE_NAME,
    PROVIDER_CALL_CONSUME_PATH,
    AgentRuntimeContractError,
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.pilot_budget import (
    BudgetError,
    PilotBudgetRegistry,
)
from tools.self_improvement_v2.runtime_bridge import open_budget_operation
from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.trusted_origin import (
    PIN_REL,
    TRUSTED_MODULE_NAMES,
    TrustedOriginError,
    assert_trusted_code_origin,
    trusted_modules_tree_digest,
)
from tools.self_improvement_v2.wall_reassert import (
    REQUIRED_WALL_KEYS,
    capture_wall_artifact_snapshot,
)
from tools.self_improvement_v2.workflow_validator import validate_workflow


def _module_relpath(module_name: str) -> str:
    return str(Path(*module_name.split(".")).with_suffix(".py")).replace("\\", "/")


def test_r1_zero_max_calls_rejected_not_clamped() -> None:
    """Explicit max_calls=0 must error — not silently become the default via `or`."""
    with pytest.raises((BudgetError, WorkerError)) as exc:
        open_budget_operation(
            PilotBudgetRegistry(),
            {"session_id": "r1-zero-calls", "max_calls": 0},
        )
    assert exc.value.code == ERROR_CODES["PILOT_BUDGET_INVALID"]


def test_r1_nan_prices_and_max_cost_rejected() -> None:
    with pytest.raises((BudgetError, WorkerError)):
        open_budget_operation(
            PilotBudgetRegistry(),
            {
                "session_id": "r1-nan-price",
                "price_per_input_token_usd": float("nan"),
                "price_per_output_token_usd": 1e-6,
            },
        )
    with pytest.raises((BudgetError, WorkerError)):
        open_budget_operation(
            PilotBudgetRegistry(),
            {
                "session_id": "r1-nan-cost",
                "max_cost_usd": float("nan"),
            },
        )
    with pytest.raises((BudgetError, WorkerError)):
        open_budget_operation(
            PilotBudgetRegistry(),
            {
                "session_id": "r1-inf-cost",
                "max_cost_usd": float("inf"),
            },
        )


def test_r1_caller_low_prices_ignored_server_owned_only() -> None:
    """Caller must not set price authority — server constants win."""
    from tools.self_improvement_v2.pilot_budget import (
        SERVER_OWNED_PRICE_PER_INPUT_TOKEN_USD,
        SERVER_OWNED_PRICE_PER_OUTPUT_TOKEN_USD,
    )

    result = open_budget_operation(
        PilotBudgetRegistry(),
        {
            "session_id": "r1-caller-prices",
            "price_per_input_token_usd": 1e-18,
            "price_per_output_token_usd": 1e-18,
            "max_input_tokens": 100,
            "max_output_tokens": 50,
        },
    )
    assert result["status"] == "PASS"
    # Worst-case must be computed from server-owned prices, not attacker 1e-18 rates.
    expected_worst = (
        100 * SERVER_OWNED_PRICE_PER_INPUT_TOKEN_USD
        + 50 * SERVER_OWNED_PRICE_PER_OUTPUT_TOKEN_USD
    ) * result["max_calls"]
    assert math.isclose(result["worst_case_usd"], expected_worst, rel_tol=0, abs_tol=1e-15)
    assert result["worst_case_usd"] > 1e-12


def test_r2_consumed_permit_second_assert_one_shot() -> None:
    """After consume, authorization is one-shot — second assert must fail."""
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="r2-oneshot")
    permit = reg.request_call_permit(session.session_id, role="implementer")
    reg.consume_call_permit(
        session.session_id,
        permit_nonce=permit["permit_nonce"],
        role="implementer",
    )
    reg.assert_provider_call_authorized(
        session.session_id,
        role="implementer",
        permit_nonce=permit["permit_nonce"],
    )
    with pytest.raises(BudgetError) as exc:
        reg.assert_provider_call_authorized(
            session.session_id,
            role="implementer",
            permit_nonce=permit["permit_nonce"],
        )
    assert exc.value.code in {
        ERROR_CODES["PILOT_PERMIT_CONSUMED"],
        ERROR_CODES["PILOT_PERMIT_NOT_CONSUMED"],
        ERROR_CODES["PILOT_PERMIT_INVALID"],
    }


def test_r2_provider_credential_mismatch_rejected() -> None:
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="r2-provider-swap")
    with pytest.raises(BudgetError):
        reg.request_call_permit(
            session.session_id,
            role="implementer",
            call_params={
                "provider": "attacker_provider",
                "credential_reference": "attacker-cred",
                "model": "attacker-model",
            },
        )


def test_r2_max_iterations_seven_fails_validation(tmp_path: Path) -> None:
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    for node in mutated["nodes"]:
        if node.get("name") == IMPLEMENTER_NODE_NAME:
            params = node.setdefault("parameters", {})
            options = params.setdefault("options", {})
            options["maxIterations"] = 7
            break
    path = tmp_path / "wf-maxiter.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    report = validate_workflow(worker_package_root(), path)
    assert report["status"] == "FAIL"
    assert any("maxIterations" in e["message"] for e in report["errors"])
    with pytest.raises(AgentRuntimeContractError):
        assert_workflow_agent_wiring(mutated)


def test_r5_shadow_checkout_recomputed_pin_must_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Arbitrary-name shadow with modified risk_authority + recomputed pin must fail."""
    real = worker_package_root()
    shadow = tmp_path / "attacker-alt-checkout"
    shadow.mkdir()
    # Minimal git checkout mirroring trusted package layout (no srl-si2-wt- marker).
    for name in TRUSTED_MODULE_NAMES:
        rel = _module_relpath(name)
        src = real / rel
        dest = shadow / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    pin_src = real / PIN_REL
    pin_dest = shadow / PIN_REL
    pin_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pin_src, pin_dest)
    # Also copy __init__.py files for package importability if needed.
    for rel in (
        "tools/__init__.py",
        "tools/self_improvement_v2/__init__.py",
    ):
        src = real / rel
        if src.is_file():
            dest = shadow / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    from tests.self_improvement_v2.helpers import run as git_run

    git_run(["git", "init"], shadow)
    git_run(["git", "config", "user.email", "attacker@local"], shadow)
    git_run(["git", "config", "user.name", "Attacker"], shadow)
    git_run(["git", "add", "-A"], shadow)
    git_run(["git", "commit", "-m", "shadow baseline"], shadow)

    # Mutate classifier authority bytes in the shadow checkout.
    ra = shadow / "tools/self_improvement_v2/risk_authority.py"
    ra.write_text(
        ra.read_text(encoding="utf-8") + "\n# shadow-attacker-mutation\n",
        encoding="utf-8",
    )
    # Recompute pin from shadow working tree (self-pinning attack).
    from tools.self_improvement_v2.git_worker import run_git
    from tools.self_improvement_v2.trusted_origin import head_content_binding_digest

    combined, per = trusted_modules_tree_digest(shadow)
    head = run_git(["rev-parse", "HEAD"], cwd=shadow, check=True).stdout.decode("utf-8").strip()
    pin = {
        "schema_version": "2.0.0",
        "description": "attacker recomputed pin",
        "combined": combined,
        "modules": per,
        "reviewed_git_head": head,
        "head_content_binding": head_content_binding_digest(head, combined),
    }
    pin_dest.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")

    # Real reviewed HEAD stays pinned via env (outside candidate-controlled contents).
    real_head = run_git(["rev-parse", "HEAD"], cwd=real, check=True).stdout.decode("utf-8").strip()
    monkeypatch.setenv("SRL_REVIEWED_HEAD", real_head)
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(real))

    with pytest.raises(TrustedOriginError) as exc:
        assert_trusted_code_origin(install_root=shadow)
    assert exc.value.code == ERROR_CODES["TRUSTED_ORIGIN_VIOLATION"]


def test_r5_primary_assert_invokes_worktree_reject(tmp_path: Path) -> None:
    """reject_worktree_as_import_root is part of the primary assertion path."""
    fake = tmp_path / "not-the-install" / "tools" / "self_improvement_v2"
    fake.mkdir(parents=True)
    # Ensure primary assert rejects alternate roots even without srl-si2-wt- marker.
    with pytest.raises(TrustedOriginError):
        assert_trusted_code_origin(install_root=tmp_path / "not-the-install")


def test_f4_wall_assert_rejects_partial_caller_keys_omitted_only(tmp_path: Path) -> None:
    """Baseline defect is omitted keys while present fingerprints still match."""
    from tests.self_improvement_v2.helpers import init_temp_repo
    from tools.self_improvement_v2.runtime_bridge import wall_assert_operation
    from tools.self_improvement_v2.runtime_config import RuntimeConfig
    from tools.self_improvement_v2.wall_reassert import assert_wall_artifacts_unchanged

    repo = tmp_path / "repo"
    init_temp_repo(repo)
    full = capture_wall_artifact_snapshot(repo)
    assert REQUIRED_WALL_KEYS <= set(full)
    # All captured fingerprints match; omit keys (not wrong values).
    partial = {"index_fingerprint": full["index_fingerprint"]}
    assert partial["index_fingerprint"] == full["index_fingerprint"]
    with pytest.raises(Exception):
        assert_wall_artifacts_unchanged(repo, partial)

    cfg = RuntimeConfig(
        repository_root=repo,
        state_db=tmp_path / "wall.sqlite",
        worker_token="test-token-not-a-secret-value",
        worker_host="127.0.0.1",
        worker_port=0,
    )
    with pytest.raises(WorkerError):
        wall_assert_operation(cfg, {"before": partial})


def test_control_hard_caps_constants() -> None:
    """Control (not a defect probe): hard-cap constants remain pinned."""
    from tools.self_improvement_v2.pilot_budget import (
        MAXIMUM_AGENT_CALLS,
        MAXIMUM_PILOT_COST_USD,
        PILOT_TIMEOUT_SECONDS,
    )

    assert MAXIMUM_AGENT_CALLS == 6
    assert MAXIMUM_PILOT_COST_USD == 5.0
    assert PILOT_TIMEOUT_SECONDS == 1800


def test_r2_workflow_requires_consume_path() -> None:
    workflow = load_design_workflow()
    blob = json.dumps(workflow)
    assert PROVIDER_CALL_CONSUME_PATH in blob
    wiring = assert_workflow_agent_wiring(workflow)
    assert "provider_call_consume" in json.dumps(wiring).lower() or any(
        "consume" in str(v).lower() for v in wiring.values()
    )
