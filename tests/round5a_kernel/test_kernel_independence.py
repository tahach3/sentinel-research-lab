"""Static and runtime independence checks."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from tools.round5a_kernel.state_b_reference import FORBIDDEN_INPUT_NAMES, compute_state_b

ROOT = Path(__file__).resolve().parents[2]
STATE_B = ROOT / "tools" / "round5a_kernel" / "state_b_reference.py"
ORACLE = ROOT / "tools" / "round5a_kernel" / "oracle_reference.py"


def test_state_b_does_not_import_banned_modules() -> None:
    tree = ast.parse(STATE_B.read_text(encoding="utf-8"))
    banned = {
        "predicate_engine",
        "classification_reference",
        "state_a_reference",
        "oracle_reference",
        "bounded_domain",
    }
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        if isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            for alias in node.names:
                imported.add(alias.name)
    for name in banned:
        assert not any(name in item.split(".") for item in imported), imported


def test_state_b_shared_code_limited_to_models() -> None:
    tree = ast.parse(STATE_B.read_text(encoding="utf-8"))
    allowed_from = {"tools.round5a_kernel.models"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("tools.round5a_kernel"):
                assert node.module in allowed_from


def test_state_b_signature_rejects_forbidden_inputs() -> None:
    params = inspect.signature(compute_state_b).parameters
    for name in FORBIDDEN_INPUT_NAMES:
        assert name not in params
    sid = "legacy_reservation_id=s1"
    base = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": "s1"}],
        durable_outcomes=[{"source_identity": sid, "outcome_slot": "a"}],
    )
    import tools.round5a_kernel.classification_reference as cr
    import tools.round5a_kernel.oracle_reference as ore
    import tools.round5a_kernel.state_a_reference as sa

    oc, oo, oa = cr.classify_source, ore.classify_oracle, sa.compute_state_a
    cr.classify_source = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("clf"))  # type: ignore[assignment]
    ore.classify_oracle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("orc"))  # type: ignore[assignment]
    sa.compute_state_a = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sa"))  # type: ignore[assignment]
    try:
        patched = compute_state_b(
            legacy_sources=[{"legacy_reservation_id": "s1"}],
            durable_outcomes=[{"source_identity": sid, "outcome_slot": "a"}],
        )
        assert patched.as_dict() == base.as_dict()
    finally:
        cr.classify_source, ore.classify_oracle, sa.compute_state_a = oc, oo, oa

    changed = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": "s1"}],
        durable_outcomes=[],
    )
    assert changed.valid is False


def test_oracle_module_independence_from_classifier() -> None:
    tree = ast.parse(ORACLE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "classification_reference" not in node.module
            assert "predicate_engine" not in node.module
