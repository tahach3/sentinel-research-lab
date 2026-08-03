"""Static independence checks for State B."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_B = ROOT / "tools" / "round5a_kernel" / "state_b_reference.py"


def test_state_b_does_not_import_classifier_predicate_or_state_a() -> None:
    tree = ast.parse(STATE_B.read_text(encoding="utf-8"))
    banned = {"predicate_engine", "classification_reference", "state_a_reference"}
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
