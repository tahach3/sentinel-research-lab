"""Codex escalate adversarial probes against 6f4f1e2 — FAIL before repair, PASS after.

R0/R5: critical origin probes use an external Python process (no in-tree env assist).
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
    IMPLEMENTER_NODE_NAME,
    AgentRuntimeContractError,
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.pilot_budget import (
    ROLE_BOUND_IDENTITY,
    BudgetError,
    PilotBudgetRegistry,
)
from tools.self_improvement_v2.runtime_bridge import (
    open_budget_operation,
    provider_call_consume_operation,
)
from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.trusted_origin import (
    ENV_REPOSITORY_ROOT,
    ENV_REVIEWED_HEAD,
    PIN_REL,
    TRUSTED_MODULE_NAMES,
    TrustedOriginError,
    assert_trusted_code_origin,
)
from tools.self_improvement_v2.workflow_validator import validate_workflow


def _module_relpath(module_name: str) -> str:
    return str(Path(*module_name.split(".")).with_suffix(".py")).replace("\\", "/")


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        shell=False,
    )


def _build_self_pinned_shadow(tmp_path: Path) -> Path:
    """Arbitrary-name shadow with mutated risk_authority + recomputed pin (committed)."""
    real = worker_package_root()
    shadow = tmp_path / "attacker-alt-checkout"
    shadow.mkdir()
    for root, dirs, files in os.walk(real / "tools" / "self_improvement_v2"):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.endswith(".py"):
                continue
            src = Path(root) / name
            rel = src.relative_to(real)
            dest = shadow / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    (shadow / "tools" / "__init__.py").write_text("", encoding="utf-8")
    pin_dest = shadow / PIN_REL
    pin_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(real / PIN_REL, pin_dest)

    _git(shadow, "init")
    _git(shadow, "config", "user.email", "attacker@local")
    _git(shadow, "config", "user.name", "Attacker")
    _git(shadow, "config", "core.autocrlf", "false")
    _git(shadow, "add", "-A")
    _git(shadow, "commit", "-m", "shadow baseline")

    ra = shadow / "tools/self_improvement_v2/risk_authority.py"
    ra.write_text(ra.read_text(encoding="utf-8") + "\n# shadow-attacker-mutation\n", encoding="utf-8")
    _git(shadow, "add", "-A")
    _git(shadow, "commit", "-m", "shadow mutate classifier")

    # Recompute pin inside shadow process (CWD=shadow); then commit pin (modules unchanged after).
    env = {k: v for k, v in os.environ.items() if k not in (ENV_REPOSITORY_ROOT, ENV_REVIEWED_HEAD)}
    env["PYTHONPATH"] = str(shadow)
    recompute = textwrap.dedent(
        """
        import json
        import subprocess
        from pathlib import Path
        from tools.self_improvement_v2.trusted_origin import (
            PIN_REL,
            TRUSTED_MODULE_NAMES,
            head_content_binding_digest,
            _git_head,
            _module_relpath,
            _sha256_bytes,
        )
        root = Path(".").resolve()
        per = {}
        import hashlib
        h = hashlib.sha256()
        for name in TRUSTED_MODULE_NAMES:
            rel = _module_relpath(name)
            digest = _sha256_bytes((root / rel).read_bytes())
            per[name] = digest
            h.update(rel.encode("utf-8")); h.update(b"\\0")
            h.update(digest.encode("ascii")); h.update(b"\\0")
        combined = h.hexdigest()
        head = _git_head(root)
        pin = {
            "schema_version": "2.0.0",
            "description": "attacker recomputed pin",
            "combined": combined,
            "modules": per,
            "reviewed_git_head": head,
            "head_content_binding": head_content_binding_digest(head, combined),
        }
        (root / PIN_REL).write_text(json.dumps(pin, indent=2) + "\\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-m", "attacker self-pin"], check=True)
        print("PIN_READY")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", recompute],
        cwd=str(shadow),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"shadow pin recompute failed: {proc.stderr}\n{proc.stdout}"
    assert "PIN_READY" in proc.stdout
    return shadow


def test_r5_external_process_no_env_shadow_self_pin_must_reject(tmp_path: Path) -> None:
    """Exact no-environment external-process R5 attack must REJECT (fail-closed).

    Mandatory attack shape: arbitrary-name shadow, CWD=shadow, both
    SRL_REPOSITORY_ROOT and SRL_REVIEWED_HEAD absent, mutated risk_authority +
    recomputed pin. Pre-repair this exits 0; post-repair must be non-zero.
    """
    shadow = _build_self_pinned_shadow(tmp_path)
    env = {k: v for k, v in os.environ.items() if k not in (ENV_REPOSITORY_ROOT, ENV_REVIEWED_HEAD)}
    env["PYTHONPATH"] = str(shadow)
    assert ENV_REPOSITORY_ROOT not in env
    assert ENV_REVIEWED_HEAD not in env

    probe = textwrap.dedent(
        """
        from tools.self_improvement_v2.trusted_origin import assert_trusted_code_origin
        result = assert_trusted_code_origin()
        print("ATTACK_SUCCEEDED", result.get("install_root"))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(shadow),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0, (
        "R5 shadow self-pin without env must reject, but external process accepted origin:\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    assert "ATTACK_SUCCEEDED" not in proc.stdout


def test_r5_real_repo_env_final_head_accepts_omitting_reviewed_head_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env root + final HEAD accept; omitting SRL_REVIEWED_HEAD rejects."""
    root = worker_package_root()
    live = _git(root, "rev-parse", "HEAD").stdout.strip()
    pin = json.loads((root / PIN_REL).read_text(encoding="utf-8"))
    reviewed = pin["reviewed_git_head"]
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(root))
    # Final tip form (pin-only successor allowed when trusted modules match pin head).
    monkeypatch.setenv(ENV_REVIEWED_HEAD, live)
    result = assert_trusted_code_origin()
    assert Path(result["install_root"]).resolve() == root.resolve()
    assert result["reviewed_git_head"] == reviewed

    # Primary bind form: launcher names pin.reviewed_git_head.
    monkeypatch.setenv(ENV_REVIEWED_HEAD, reviewed)
    assert_trusted_code_origin()

    monkeypatch.delenv(ENV_REVIEWED_HEAD, raising=False)
    with pytest.raises(TrustedOriginError) as exc:
        assert_trusted_code_origin()
    assert exc.value.code == ERROR_CODES["TRUSTED_ORIGIN_VIOLATION"]


def test_r5_trusted_origin_module_is_pinned() -> None:
    assert "tools.self_improvement_v2.trusted_origin" in TRUSTED_MODULE_NAMES


def test_f5_boolean_budget_fields_rejected_via_runtime_bridge() -> None:
    """Booleans must not coerce through int/float in open_budget_operation."""
    cases = [
        {"session_id": "bool-max-calls", "max_calls": True},
        {"session_id": "bool-timeout", "timeout_seconds": True},
        {"session_id": "bool-cost", "max_cost_usd": True},
        {"session_id": "bool-in-tokens", "max_input_tokens": True},
        {"session_id": "bool-out-tokens", "max_output_tokens": True},
        {"session_id": "bool-price-in", "price_per_input_token_usd": True},
        {"session_id": "bool-price-out", "price_per_output_token_usd": True},
    ]
    for payload in cases:
        with pytest.raises((BudgetError, WorkerError)) as exc:
            open_budget_operation(PilotBudgetRegistry(), payload)
        assert exc.value.code == ERROR_CODES["PILOT_BUDGET_INVALID"]


def test_f6_max_iterations_boolean_true_rejected(tmp_path: Path) -> None:
    """JSON true must not satisfy maxIterations==1 via int(True)."""
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    for node in mutated["nodes"]:
        if node.get("name") == IMPLEMENTER_NODE_NAME:
            params = node.setdefault("parameters", {})
            options = params.setdefault("options", {})
            options["maxIterations"] = True
            break
    path = tmp_path / "wf-maxiter-true.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    report = validate_workflow(worker_package_root(), path)
    assert report["status"] == "FAIL"
    assert any("maxIterations" in e["message"] for e in report["errors"])
    with pytest.raises(AgentRuntimeContractError):
        assert_workflow_agent_wiring(mutated)


def test_f4_consume_validates_provider_model_credential_binding() -> None:
    """Consume path must validate role-bound provider/model/credential atomically."""
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="f4-consume-bind")
    permit = reg.request_call_permit(session.session_id, role="implementer")
    identity = ROLE_BOUND_IDENTITY["implementer"]
    with pytest.raises(BudgetError) as exc:
        reg.consume_call_permit(
            session.session_id,
            permit_nonce=permit["permit_nonce"],
            role="implementer",
            provider="attacker-provider",
            credential_reference=identity["credential_reference"],
            model=identity["model"],
        )
    assert exc.value.code == ERROR_CODES["PILOT_PERMIT_INVALID"]

    with pytest.raises((BudgetError, WorkerError)):
        provider_call_consume_operation(
            reg,
            {
                "session_id": session.session_id,
                "role": "implementer",
                "permit_nonce": permit["permit_nonce"],
                "provider": "attacker-provider",
                "model": identity["model"],
                "credential_reference": identity["credential_reference"],
            },
        )

    reg2 = PilotBudgetRegistry()
    session2 = reg2.open_session(session_id="f4-consume-ok")
    permit2 = reg2.request_call_permit(session2.session_id, role="implementer")
    consumed = provider_call_consume_operation(
        reg2,
        {
            "session_id": session2.session_id,
            "role": "implementer",
            "permit_nonce": permit2["permit_nonce"],
            "provider": identity["provider"],
            "model": identity["model"],
            "credential_reference": identity["credential_reference"],
        },
    )
    assert consumed["status"] == "PASS"
    assert consumed["consume"]["status"] == "CONSUMED"
