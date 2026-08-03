"""Bounded-domain generator tests."""

from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

from tools.round5a_kernel.bounded_domain import (
    coverage_report,
    domain_limitations,
    generate_domain_cases,
    generate_domain_cases_from_doc,
    load_bounded_domain,
)

ROOT = Path(__file__).resolve().parents[2]
BD_MOD = ROOT / "tools" / "round5a_kernel" / "bounded_domain.py"


def test_bounded_domain_axes_and_limitations() -> None:
    doc = load_bounded_domain(ROOT)
    assert "status" in doc["axes"]
    assert "related_row_cardinality" in doc["axes"]
    assert "identity_validity" in doc["axes"]
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


def test_every_declared_axis_and_value_covered() -> None:
    report = coverage_report(root=ROOT)
    assert report["coverage_type"] == "WITNESS_PLUS_AXIS"
    assert report["missing_axes"] == []
    assert report["missing_values"] == []
    assert "related_row_cardinality" in report["declared_axes"]
    assert "identity_validity" in report["declared_axes"]
    assert set(report["covered_values"]["related_row_cardinality"]) >= {
        "zero",
        "one",
        "duplicate",
    }
    assert set(report["covered_values"]["identity_validity"]) >= {
        "valid",
        "missing_component",
        "normalization_collision_candidate",
    }


def test_removing_required_axis_value_fails_coverage() -> None:
    doc = load_bounded_domain(ROOT)
    mutated = deepcopy(doc)
    mutated["seeded_cases"] = [
        c
        for c in mutated["seeded_cases"]
        if (c.get("axis_values") or {}).get("related_row_cardinality") != "duplicate"
        and not (c.get("oracle_facts") or {}).get("duplicate_case_attempt")
        and not (c.get("oracle_facts") or {}).get("duplicate_idempotency")
        and not (c.get("oracle_facts") or {}).get("duplicate_envelope_link")
    ]
    cases = generate_domain_cases_from_doc(mutated)
    report = coverage_report(doc=doc, cases=cases)
    assert report["missing_values"]
    assert any(
        m["axis"] == "related_row_cardinality" and m["value"] == "duplicate"
        for m in report["missing_values"]
    )


def test_unused_declared_axis_fails() -> None:
    doc = load_bounded_domain(ROOT)
    mutated = deepcopy(doc)
    mutated["axes"] = dict(mutated["axes"])
    mutated["axes"]["unused_axis_for_test"] = ["only"]
    cases = generate_domain_cases_from_doc(mutated)
    report = coverage_report(doc=mutated, cases=cases)
    assert "unused_axis_for_test" in report["missing_axes"] or any(
        m["axis"] == "unused_axis_for_test" for m in report["missing_values"]
    )


def test_related_row_and_identity_cases_have_expected_rules() -> None:
    cases = {c["case_id"]: c for c in generate_domain_cases(ROOT)}
    for cid in (
        "axis_related_row_zero",
        "axis_related_row_one",
        "axis_related_row_duplicate",
        "axis_identity_valid",
        "axis_identity_missing_component",
        "axis_identity_normalization_collision_candidate",
    ):
        assert cid in cases
        assert cases[cid].get("expected_classifier_rule")
        assert cases[cid].get("expected_oracle_rule")
