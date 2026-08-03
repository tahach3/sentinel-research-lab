"""Bounded-domain generator tests."""

from __future__ import annotations

import ast
from pathlib import Path

from tools.round5a_kernel.bounded_domain import domain_limitations, generate_domain_cases, load_bounded_domain

ROOT = Path(__file__).resolve().parents[2]
BD_MOD = ROOT / "tools" / "round5a_kernel" / "bounded_domain.py"


def test_bounded_domain_axes_and_limitations() -> None:
    doc = load_bounded_domain(ROOT)
    assert "status" in doc["axes"]
    assert domain_limitations(ROOT)
    cases = generate_domain_cases(ROOT)
    assert len(cases) >= 22
    assert any(c["case_id"] == "seed_rule-22" for c in cases)


def test_domain_generator_does_not_import_classifier_or_oracle() -> None:
    tree = ast.parse(BD_MOD.read_text(encoding="utf-8"))
    banned = {"classification_reference", "oracle_reference", "predicate_engine"}
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        if isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
        for mod in mods:
            assert not any(b in mod.split(".") for b in banned)
