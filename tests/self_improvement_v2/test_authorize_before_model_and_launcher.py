"""Authorize-before-model ordering + out-of-repo launcher R0 probes."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    IMPLEMENTER_NODE_NAME,
    PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME,
    PROVIDER_CALL_AUTHORIZE_REVIEWER_NODE_NAME,
    PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME,
    PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME,
    REVIEWER_NODE_NAME,
    AgentRuntimeContractError,
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.launcher.install_launcher import (
    compute_verifier_digest,
    install_launcher,
)
from tools.self_improvement_v2.launcher.paths import VERIFIER_REL, assert_outside_repository
from tools.self_improvement_v2.workflow_validator import validate_workflow


REPO = Path(__file__).resolve().parents[2]


def test_d1_authorize_immediately_before_agents() -> None:
    """Permit → Consume → Authorize → Agent on both roles (not post-hoc)."""
    wiring = assert_workflow_agent_wiring(root=REPO)
    assert wiring
    wf = load_design_workflow(root=REPO)
    c = wf["connections"]
    assert (
        c[PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME]["main"][0][0]["node"]
        == PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME
    )
    assert (
        c[PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME]["main"][0][0]["node"]
        == IMPLEMENTER_NODE_NAME
    )
    assert c[IMPLEMENTER_NODE_NAME]["main"][0][0]["node"] == "Proposal Schema Validation"
    assert (
        c[PROVIDER_CALL_CONSUME_REVIEWER_NODE_NAME]["main"][0][0]["node"]
        == PROVIDER_CALL_AUTHORIZE_REVIEWER_NODE_NAME
    )
    assert (
        c[PROVIDER_CALL_AUTHORIZE_REVIEWER_NODE_NAME]["main"][0][0]["node"]
        == REVIEWER_NODE_NAME
    )
    assert c[REVIEWER_NODE_NAME]["main"][0][0]["node"] == "Independent Review Bind"
    report = validate_workflow(REPO, REPO / "workflows/design/self_improvement_loop_v2.json")
    assert report["status"] == "PASS"


def test_d1_posthoc_authorize_after_agent_rejected() -> None:
    """Regression: Agent → Authorize must fail both validators."""
    wf = load_design_workflow(root=REPO)
    mutated = copy.deepcopy(wf)
    mutated["connections"][PROVIDER_CALL_CONSUME_IMPLEMENTER_NODE_NAME]["main"][0] = [
        {"node": IMPLEMENTER_NODE_NAME, "type": "main", "index": 0}
    ]
    mutated["connections"][IMPLEMENTER_NODE_NAME]["main"][0] = [
        {"node": PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME, "type": "main", "index": 0}
    ]
    mutated["connections"][PROVIDER_CALL_AUTHORIZE_IMPLEMENTER_NODE_NAME]["main"][0] = [
        {"node": "Proposal Schema Validation", "type": "main", "index": 0}
    ]
    with pytest.raises(
        AgentRuntimeContractError,
        match="must not run after Implementer Agent|must not bypass provider-call-authorize|must follow Provider Call Consume",
    ):
        assert_workflow_agent_wiring(workflow=mutated, root=REPO)

    # Same mutation must fail structural validator (closed-world / missing success edges).
    probe = REPO / "tmp_posthoc_authorize_probe.json"
    try:
        probe.write_text(json.dumps(mutated), encoding="utf-8")
        report = validate_workflow(REPO, probe)
        assert report["status"] == "FAIL"
        messages = " ".join(e["message"] for e in report["errors"])
        assert "Provider Call Authorize (Implementer)" in messages or "missing success edge" in messages
    finally:
        if probe.exists():
            probe.unlink()


def test_d2_launcher_install_refuses_inside_repo(tmp_path: Path) -> None:
    inside = REPO / "tmp_launcher_inside_must_fail"
    inside.mkdir(exist_ok=True)
    try:
        with pytest.raises(ValueError, match="outside the repository"):
            install_launcher(
                repository_root=REPO,
                reviewed_head="a" * 40,
                install_dir=inside,
            )
    finally:
        inside.rmdir()


def test_d2_launcher_digest_mismatch_refuses(tmp_path: Path) -> None:
    head = "b" * 40
    digest = compute_verifier_digest(REPO)
    result = install_launcher(
        repository_root=REPO,
        reviewed_head=head,
        install_dir=tmp_path / "SentinelResearchLab",
        expected_digest=digest,
    )
    assert_outside_repository(Path(result["install_dir"]), REPO)
    sh = Path(result["launch_worker_sh"])
    # Mutate expected digest in the installed script to force refuse without touching repo bytes.
    text = sh.read_text(encoding="utf-8")
    bad = "c" * 64
    sh.write_text(text.replace(digest, bad), encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(sh)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={**os.environ, "SRL_WORKER_TOKEN": "test-token-not-used"},
    )
    assert proc.returncode == 3
    assert "digest mismatch" in (proc.stderr + proc.stdout)


def test_d2_launcher_matching_digest_sets_anchors(tmp_path: Path) -> None:
    # Use a stub exec: rewrite launcher to print env and exit 0 before runtime_bridge.
    head = "a" * 40
    digest = compute_verifier_digest(REPO)
    result = install_launcher(
        repository_root=REPO,
        reviewed_head=head,
        install_dir=tmp_path / "SentinelResearchLab",
        expected_digest=digest,
    )
    sh = Path(result["launch_worker_sh"])
    text = sh.read_text(encoding="utf-8")
    text = text.replace(
        'exec python3 -m tools.self_improvement_v2.runtime_bridge "$@"',
        'printf "ROOT=%s\\nHEAD=%s\\n" "$SRL_REPOSITORY_ROOT" "$SRL_REVIEWED_HEAD"; exit 0',
    )
    sh.write_text(text, encoding="utf-8")
    proc = subprocess.run(["bash", str(sh)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert f"ROOT={REPO.resolve()}" in proc.stdout
    assert f"HEAD={head}" in proc.stdout


def test_d2_expected_digest_lives_outside_checkout(tmp_path: Path) -> None:
    digest = compute_verifier_digest(REPO)
    result = install_launcher(
        repository_root=REPO,
        reviewed_head="d" * 40,
        install_dir=tmp_path / "SentinelResearchLab",
        expected_digest=digest,
    )
    att = json.loads(Path(result["attestation"]).read_text(encoding="utf-8"))
    assert att["expected_verifier_digest"] == digest
    assert Path(result["attestation"]).resolve().is_relative_to(tmp_path.resolve())
    # Pin file inside repo is not the launcher attestation.
    pin = json.loads((REPO / "specs/self_improvement/v2/trusted_origin_pin.json").read_text())
    assert "reviewed_git_head" not in pin
    assert att["expected_verifier_digest"] != pin.get("combined_digest", "")
