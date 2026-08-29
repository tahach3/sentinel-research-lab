"""Option A+ / Codex e85c42ee adversarial probes — exact FAIL→PASS shapes.

Attack setups are copied from the review report; they must not import candidate
helpers beyond the public worker surfaces under test.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.pilot_budget import ROLE_BOUND_IDENTITY, PilotBudgetRegistry
from tools.self_improvement_v2.runtime_bridge import (
    provider_call_consume_operation,
    provider_call_permit_operation,
)
from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.trusted_origin import (
    ENV_REPOSITORY_ROOT,
    ENV_REVIEWED_HEAD,
    PIN_REL,
    TRUSTED_MODULE_NAMES,
    gated_assert_trusted_code_origin,
)
from tools.self_improvement_v2.workflow_validator import validate_workflow


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _clone_reviewed(tmp_path: Path) -> Path:
    real = worker_package_root()
    dest = tmp_path / "reviewed-clone"
    subprocess.run(
        ["git", "clone", "--quiet", str(real), str(dest)],
        check=True,
        capture_output=True,
    )
    return dest


def test_a1_dirty_runtime_bridge_rejects_before_sentinel(tmp_path: Path) -> None:
    """Valid anchors + dirty runtime_bridge.py must reject before sentinel executes."""
    clone = _clone_reviewed(tmp_path)
    head = _git(clone, "rev-parse", "HEAD").stdout.strip()
    target = clone / "tools/self_improvement_v2/runtime_bridge.py"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nprint('SENTINEL_RUNTIME_BRIDGE')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env[ENV_REPOSITORY_ROOT] = str(clone)
    env[ENV_REVIEWED_HEAD] = head
    env["PYTHONPATH"] = str(clone)
    probe = textwrap.dedent(
        """
        from tools.self_improvement_v2.trusted_origin import gated_assert_trusted_code_origin
        gated_assert_trusted_code_origin()
        print('ATTACK_ACCEPTED')
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(clone),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "SENTINEL_RUNTIME_BRIDGE" not in proc.stdout
    assert "ATTACK_ACCEPTED" not in proc.stdout


def test_a2_dirty_git_worker_rejects_before_sentinel(tmp_path: Path) -> None:
    clone = _clone_reviewed(tmp_path)
    head = _git(clone, "rev-parse", "HEAD").stdout.strip()
    target = clone / "tools/self_improvement_v2/git_worker.py"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nprint('SENTINEL_GIT_WORKER')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env[ENV_REPOSITORY_ROOT] = str(clone)
    env[ENV_REVIEWED_HEAD] = head
    env["PYTHONPATH"] = str(clone)
    probe = textwrap.dedent(
        """
        from tools.self_improvement_v2.trusted_origin import gated_assert_trusted_code_origin
        gated_assert_trusted_code_origin()
        print('ATTACK_ACCEPTED')
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(clone),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "SENTINEL_GIT_WORKER" not in proc.stdout
    assert "ATTACK_ACCEPTED" not in proc.stdout


def test_dirty_workflow_validator_rejects_before_sentinel(tmp_path: Path) -> None:
    """Pinned workflow_validator must dirty-refuse (Codex ABSENT→PRESENT)."""
    clone = _clone_reviewed(tmp_path)
    head = _git(clone, "rev-parse", "HEAD").stdout.strip()
    target = clone / "tools/self_improvement_v2/workflow_validator.py"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nprint('SENTINEL_WORKFLOW_VALIDATOR')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env[ENV_REPOSITORY_ROOT] = str(clone)
    env[ENV_REVIEWED_HEAD] = head
    env["PYTHONPATH"] = str(clone)
    probe = textwrap.dedent(
        """
        from tools.self_improvement_v2.trusted_origin import gated_assert_trusted_code_origin
        gated_assert_trusted_code_origin()
        print('ATTACK_ACCEPTED')
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(clone),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "SENTINEL_WORKFLOW_VALIDATOR" not in proc.stdout
    assert "ATTACK_ACCEPTED" not in proc.stdout


def test_a3_preloaded_forged_verifier_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = worker_package_root()
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(root))
    monkeypatch.setenv(ENV_REVIEWED_HEAD, head)

    class Forge:
        def assert_trusted_code_origin(self, *a, **k):
            print("ACCEPTED_BY_PRELOADED_VERIFIER")
            return {"install_root": "forge"}

    forge = type(sys)("tools.self_improvement_v2.trusted_origin")
    forge.assert_trusted_code_origin = Forge().assert_trusted_code_origin
    forge.__file__ = str(tmp_path / "forged_trusted_origin.py")
    (tmp_path / "forged_trusted_origin.py").write_text("# forge\n", encoding="utf-8")
    sys.modules["tools.self_improvement_v2.trusted_origin"] = forge
    # gated loader must displace forge and use on-disk pin-matching module
    result = gated_assert_trusted_code_origin()
    assert Path(result["install_root"]).resolve() == root.resolve()
    assert "tools.self_improvement_v2.runtime_bridge" in TRUSTED_MODULE_NAMES


def test_b1_disabled_worker_authorize_rejected(tmp_path: Path) -> None:
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    for node in mutated["nodes"]:
        if node.get("name") == "Worker Authorize":
            node["disabled"] = True
            break
    path = tmp_path / "wf-disabled-authorize.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    report = validate_workflow(worker_package_root(), path)
    assert report["status"] == "FAIL"
    assert any("Worker Authorize" in e["message"] and "disabled" in e["message"] for e in report["errors"])
    with pytest.raises(Exception):
        assert_workflow_agent_wiring(mutated)


def test_b2_disabled_review_bind_rejected(tmp_path: Path) -> None:
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    for node in mutated["nodes"]:
        if node.get("name") == "Independent Review Bind":
            node["disabled"] = True
            break
    path = tmp_path / "wf-disabled-bind.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    report = validate_workflow(worker_package_root(), path)
    assert report["status"] == "FAIL"
    with pytest.raises(Exception):
        assert_workflow_agent_wiring(mutated)


def test_b3_hardcoded_decision_router_output_rejected(tmp_path: Path) -> None:
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    for node in mutated["nodes"]:
        if node.get("name") == "Worker Decision Router":
            node.setdefault("parameters", {})["output"] = "={{'AUTHORIZED'}}"
            break
    path = tmp_path / "wf-hardcoded-router.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    report = validate_workflow(worker_package_root(), path)
    assert report["status"] == "FAIL"
    with pytest.raises(Exception):
        assert_workflow_agent_wiring(mutated)


def test_c1_permit_bool_tokens_rejected_before_grant() -> None:
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="c1-bool")
    before = session.calls_granted
    with pytest.raises(Exception):
        provider_call_permit_operation(
            reg,
            {"session_id": session.session_id, "role": "implementer", "max_input_tokens": True},
        )
    assert reg._sessions[session.session_id].calls_granted == before


def test_c2_omit_consume_identity_preserves_nonce() -> None:
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="c2-omit")
    permit = reg.request_call_permit(session.session_id, role="implementer")
    identity = ROLE_BOUND_IDENTITY["implementer"]
    with pytest.raises(Exception):
        provider_call_consume_operation(
            reg,
            {
                "session_id": session.session_id,
                "role": "implementer",
                "permit_nonce": permit["permit_nonce"],
            },
        )
    ok = provider_call_consume_operation(
        reg,
        {
            "session_id": session.session_id,
            "role": "implementer",
            "permit_nonce": permit["permit_nonce"],
            "provider": identity["provider"],
            "model": identity["model"],
            "credential_reference": identity["credential_reference"],
        },
    )
    assert ok["consume"]["status"] == "CONSUMED"
    assert ok["invocation_evidence"]
