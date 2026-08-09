"""V3 final-delta adversarial probes — permanent regression tests (Codex REPAIR_REQUIRED).

Each probe encodes a defect that must FAIL on pre-repair code and PASS after the fix.
These are not companion-only unit tests written beside the fix; they assert the repaired
contracts directly.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo
from tools.self_improvement_v2.agent_runtime_contract import (
    BIND_REVIEW_PATH,
    IMPLEMENTER_MODEL,
    OPEN_PILOT_BUDGET_NODE_NAME,
    PROVIDER_CALL_PERMIT_PATH,
    AgentRuntimeContractError,
    assert_loopback_worker_url,
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.git_worker import (
    index_fingerprint,
    working_tree_content_fingerprint,
)
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.pilot_budget import (
    MAXIMUM_AGENT_CALLS,
    MAXIMUM_PILOT_COST_USD,
    PILOT_TIMEOUT_SECONDS,
    BudgetError,
    PilotBudgetRegistry,
    open_budget_hard_caps,
    provider_call_params_with_token_ceiling,
)
from tools.self_improvement_v2.runtime_bridge import (
    bind_review_operation,
    execute_operation,
    open_budget_operation,
    wall_assert_operation,
)
from tools.self_improvement_v2.runtime_config import RuntimeConfig
from tools.self_improvement_v2.schema_loader import validate_instance, worker_package_root
from tools.self_improvement_v2.trusted_origin import (
    assert_trusted_code_origin,
    trusted_modules_git_head_digest,
)
from tools.self_improvement_v2.wall_reassert import (
    REQUIRED_WALL_KEYS,
    WallReassertError,
    assert_wall_artifacts_unchanged,
    capture_wall_artifact_snapshot,
)
from tools.self_improvement_v2.workflow_normalizer import (
    MATERIAL_FIELDS_NODE,
    workflows_materially_equivalent,
)
from tools.self_improvement_v2.workflow_validator import validate_workflow
from tools.self_improvement_v2.zone_p_harness import (
    DURABLE_STATE_DB_BASENAME,
    ZonePHarnessError,
    assert_throwaway_zone_p_state_db,
    assert_zone_p_ledger_isolation,
)


def test_f1_budget_open_rejects_inflated_maxima() -> None:
    """Codex probe: caller-supplied maxima above 6 / $5 / 1800s must be rejected."""
    with pytest.raises(BudgetError) as exc:
        open_budget_hard_caps(
            max_calls=999,
            max_cost_usd=999.0,
            timeout_seconds=99999,
            price_per_input_token_usd=1e-6,
            price_per_output_token_usd=1e-6,
        )
    assert exc.value.code == ERROR_CODES["PILOT_BUDGET_INVALID"]

    reg = PilotBudgetRegistry()
    with pytest.raises(BudgetError):
        reg.open_session(session_id="f1-inflated", max_calls=100, max_cost_usd=50.0)

    with pytest.raises(WorkerError):
        open_budget_operation(
            PilotBudgetRegistry(),
            {
                "session_id": "f1-bridge",
                "max_calls": 100,
                "max_cost_usd": 50.0,
                "timeout_seconds": 10_000,
            },
        )


def test_f1_budget_open_rejects_zero_price_zero_worst_case() -> None:
    """Caller zero prices are ignored; server-owned prices are applied (no $0 worst_case)."""
    from tools.self_improvement_v2.pilot_budget import (
        SERVER_OWNED_PRICE_PER_INPUT_TOKEN_USD,
        SERVER_OWNED_PRICE_PER_OUTPUT_TOKEN_USD,
    )

    reg = PilotBudgetRegistry()
    session = reg.open_session(
        session_id="f1-zero-price",
        price_per_input_token_usd=0.0,
        price_per_output_token_usd=0.0,
    )
    assert session.price_per_input_token_usd == SERVER_OWNED_PRICE_PER_INPUT_TOKEN_USD
    assert session.price_per_output_token_usd == SERVER_OWNED_PRICE_PER_OUTPUT_TOKEN_USD
    assert session.worst_case_usd > 0


def test_f2_permit_requires_role_nonce_and_single_use_consume() -> None:
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="f2-nonce")
    permit = reg.request_call_permit(session.session_id, role="implementer")
    assert permit["status"] == "GRANTED"
    assert isinstance(permit.get("permit_nonce"), str) and permit["permit_nonce"]
    assert permit.get("role") == "implementer"
    assert isinstance(permit.get("provider_call_params"), dict)
    assert permit["provider_call_params"].get("max_output_tokens", 0) >= 1

    with pytest.raises(BudgetError) as exc:
        reg.assert_provider_call_authorized(session.session_id, role="implementer")
    assert exc.value.code == ERROR_CODES["PILOT_PERMIT_NOT_CONSUMED"]

    consumed = reg.consume_call_permit(
        session.session_id,
        permit_nonce=permit["permit_nonce"],
        role="implementer",
    )
    assert consumed["status"] == "CONSUMED"
    reg.assert_provider_call_authorized(
        session.session_id,
        role="implementer",
        permit_nonce=permit["permit_nonce"],
    )

    with pytest.raises(BudgetError):
        reg.consume_call_permit(
            session.session_id,
            permit_nonce=permit["permit_nonce"],
            role="implementer",
        )


def test_f2_permit_role_mismatch_rejected() -> None:
    reg = PilotBudgetRegistry()
    session = reg.open_session(session_id="f2-role")
    permit = reg.request_call_permit(session.session_id, role="implementer")
    with pytest.raises(BudgetError):
        reg.consume_call_permit(
            session.session_id,
            permit_nonce=permit["permit_nonce"],
            role="reviewer",
        )


def test_f3_disabled_open_pilot_budget_not_materially_equivalent() -> None:
    """Codex probe: disable Open Pilot Budget must change material fingerprint."""
    assert "disabled" in MATERIAL_FIELDS_NODE
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    for node in mutated["nodes"]:
        if node.get("name") == OPEN_PILOT_BUDGET_NODE_NAME:
            node["disabled"] = True
            break
    else:
        pytest.fail("Open Pilot Budget missing")
    assert not workflows_materially_equivalent(workflow, mutated)


def test_f6_loopback_url_rejects_userinfo_and_host_confusion() -> None:
    """Codex probe: http://127.0.0.1@attacker.example/... must not pass loopback checks."""
    evil = "http://127.0.0.1@attacker.example/v2/provider-call-permit"
    parsed = urlparse(evil)
    assert parsed.hostname == "attacker.example" or parsed.username == "127.0.0.1"
    with pytest.raises(AgentRuntimeContractError):
        assert_loopback_worker_url(evil, PROVIDER_CALL_PERMIT_PATH, "Provider Call Permit")

    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    for node in mutated["nodes"]:
        if node.get("name") == "Provider Call Permit (Implementer)":
            node["parameters"]["url"] = evil
            break
    with pytest.raises(AgentRuntimeContractError):
        assert_workflow_agent_wiring(mutated)


def test_f7_independent_review_bind_invokes_review_gate_not_hardcoded_ok() -> None:
    workflow = load_design_workflow()
    by_name = {n["name"]: n for n in workflow["nodes"]}
    bind = by_name["Independent Review Bind"]
    assert bind.get("type") == "n8n-nodes-base.httpRequest"
    url = str((bind.get("parameters") or {}).get("url") or "")
    assert BIND_REVIEW_PATH in url
    assert "review_ok:true" not in json.dumps(bind)

    wiring = assert_workflow_agent_wiring(workflow)
    assert wiring.get("bind_review") == "Independent Review Bind"


def test_f7_bind_review_operation_rejects_non_pass_verdict(tmp_path: Path) -> None:
    repo = tmp_path / "sentinel-research-lab"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    review = build_pass_review(bundle, proposal)
    review["verdict"] = "ESCALATE"
    review["contract_alignment"] = "FAIL"
    review["architecture_findings"] = ["adversarial fail verdict must not bind"]
    cfg = RuntimeConfig(
        repository_root=repo,
        state_db=db,
        worker_token="test-token-not-a-secret-value",
        worker_host="127.0.0.1",
        worker_port=0,
    )
    with pytest.raises(WorkerError) as exc:
        bind_review_operation(cfg, {"review": review})
    assert exc.value.state in {"REVIEW_FAILED", "REPAIR_LIMIT_REACHED"}


def test_f4_unstaged_trusted_edit_changes_working_tree_fingerprint(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    before_idx = index_fingerprint(repo)
    before_wt = working_tree_content_fingerprint(repo)
    target = repo / "docs" / "README.md"
    target.write_text("# Temp docs\nmutated-wall\n", encoding="utf-8")
    # Index (ls-files -s) may stay identical for unstaged edits; working-tree bytes must change.
    assert index_fingerprint(repo) == before_idx
    assert working_tree_content_fingerprint(repo) != before_wt
    snap = capture_wall_artifact_snapshot(repo)
    assert "working_tree_content_fingerprint" in snap
    assert REQUIRED_WALL_KEYS <= set(snap)
    stale = dict(snap)
    stale["working_tree_content_fingerprint"] = before_wt
    with pytest.raises(WallReassertError):
        assert_wall_artifacts_unchanged(repo, stale)


def test_f4_wall_assert_rejects_partial_caller_keys(tmp_path: Path) -> None:
    """Baseline defect is omitted keys while present fingerprints still match."""
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    full = capture_wall_artifact_snapshot(repo)
    assert REQUIRED_WALL_KEYS <= set(full)
    # All fingerprints match first; omit keys (not wrong values).
    partial = {"index_fingerprint": full["index_fingerprint"]}
    assert partial["index_fingerprint"] == full["index_fingerprint"]
    with pytest.raises(WallReassertError):
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


def test_f4_execute_operation_invokes_wall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "sentinel-research-lab"
    baseline = init_temp_repo(repo)
    db = tmp_path / "s.sqlite"
    proposal = build_proposal(baseline)
    cfg = RuntimeConfig(
        repository_root=repo,
        state_db=db,
        worker_token="test-token-not-a-secret-value",
        worker_host="127.0.0.1",
        worker_port=0,
    )
    calls: list[str] = []
    real_capture = capture_wall_artifact_snapshot

    def wrap_capture(*args, **kwargs):
        calls.append("capture")
        return real_capture(*args, **kwargs)

    monkeypatch.setattr(
        "tools.self_improvement_v2.runtime_bridge.capture_wall_artifact_snapshot",
        wrap_capture,
    )
    result = execute_operation(cfg, proposal, None)
    assert result.get("wall_reassert") == "PASS"
    # Capture before + after execute (worktree list may change; source bytes must not).
    assert calls.count("capture") >= 2


def test_f5_trusted_origin_includes_git_head_digest() -> None:
    result = assert_trusted_code_origin()
    assert "trusted_modules_git_head_digest" in result
    digest = trusted_modules_git_head_digest(worker_package_root())
    assert result["trusted_modules_git_head_digest"] == digest
    assert len(digest) == 64


def test_f9_conflicting_token_aliases_rejected_or_overwritten() -> None:
    with pytest.raises(BudgetError):
        provider_call_params_with_token_ceiling(
            {"max_output_tokens": 100, "max_tokens": 9999, "maxOutputTokens": 50},
            max_output_tokens=100,
        )


def test_f10_duplicate_node_names_rejected(tmp_path: Path) -> None:
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    clone = copy.deepcopy(mutated["nodes"][0])
    clone["id"] = "dup-id-zzz"
    clone["name"] = mutated["nodes"][1]["name"]
    mutated["nodes"].append(clone)
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    report = validate_workflow(worker_package_root(), path)
    assert report["status"] == "FAIL"
    assert any("duplicate" in e["message"].lower() for e in report["errors"])


def test_f10_extra_edge_rejected(tmp_path: Path) -> None:
    workflow = load_design_workflow()
    mutated = copy.deepcopy(workflow)
    mutated["connections"]["Manual Trigger"]["main"][0].append(
        {"node": "Human Promotion Boundary", "type": "main", "index": 0}
    )
    path = tmp_path / "wf-extra.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    report = validate_workflow(worker_package_root(), path)
    assert report["status"] == "FAIL"
    assert any(
        "extra" in e["message"].lower() or "closed-world" in e["message"].lower()
        for e in report["errors"]
    )


def test_f11_implementer_prompt_uses_gemini_3_6_flash() -> None:
    workflow = load_design_workflow()
    by_name = {n["name"]: n for n in workflow["nodes"]}
    text = str((by_name["Implementer Agent"].get("parameters") or {}).get("text") or "")
    assert IMPLEMENTER_MODEL in text
    assert "gemini-2.5-flash" not in text


def test_f8_synthetic_control_requires_probe_id(tmp_path: Path) -> None:
    repo = tmp_path / "sentinel-research-lab"
    baseline = init_temp_repo(repo)
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=tmp_path / "s.sqlite")
    review = build_pass_review(bundle, proposal)
    review["synthetic_control"] = True
    review.pop("probe_id", None)
    with pytest.raises(Exception):
        validate_instance("review_result", review, root=repo)


def test_f8_zone_p_rejects_durable_ledger_contamination(tmp_path: Path) -> None:
    durable = tmp_path / DURABLE_STATE_DB_BASENAME
    durable.write_bytes(b"")
    with pytest.raises(ZonePHarnessError):
        assert_throwaway_zone_p_state_db(durable)
    with pytest.raises(ZonePHarnessError):
        assert_zone_p_ledger_isolation(
            state_db=durable,
            synthetic_control=True,
            probe_id="p1",
        )


def test_control_hard_caps_constants() -> None:
    """Control (not a defect probe): hard-cap constants remain pinned."""
    assert MAXIMUM_AGENT_CALLS == 6
    assert MAXIMUM_PILOT_COST_USD == 5.0
    assert PILOT_TIMEOUT_SECONDS == 1800
