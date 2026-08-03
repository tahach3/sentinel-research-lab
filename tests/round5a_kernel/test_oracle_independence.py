"""Independent oracle and differential checks."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from tools.round5a_kernel.bounded_domain import generate_domain_cases
from tools.round5a_kernel.classification_reference import classify_source, load_reconciliation_contract
from tools.round5a_kernel.oracle_reference import classify_oracle

ROOT = Path(__file__).resolve().parents[2]
ORACLE_MOD = ROOT / "tools" / "round5a_kernel" / "oracle_reference.py"
RECON_CASES = ROOT / "specs" / "round5a_kernel" / "oracles" / "reconciliation_cases.json"


def test_oracle_has_no_banned_imports() -> None:
    tree = ast.parse(ORACLE_MOD.read_text(encoding="utf-8"))
    banned = {
        "predicate_engine",
        "classification_reference",
        "state_a_reference",
        "state_b_reference",
        "reconciliation_contract",
    }
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for name in banned:
        assert not any(name in item.split(".") for item in imported)


def test_oracle_uses_decision_table_not_ast() -> None:
    text = ORACLE_MOD.read_text(encoding="utf-8")
    assert "RULE_TABLE" in text
    assert "decision table" in text.lower() or "Decision-table" in text or "decision-table" in text
    assert "PredicateEngine" not in text


def test_reconciliation_oracle_cases_literal() -> None:
    doc = json.loads(RECON_CASES.read_text(encoding="utf-8"))
    rules = {c["expected"]["rule_id"] for c in doc["cases"] if c["expected"].get("rule_id")}
    assert len(rules) == 22
    for case in doc["cases"]:
        if case["expected"].get("error_code"):
            continue
        rec = classify_oracle(case["source"], facts=case.get("oracle_facts"))
        assert rec.rule_id == case["expected"]["rule_id"]


def test_differential_zero_disagreements() -> None:
    rules = load_reconciliation_contract(ROOT)["rules"]
    disagreements = 0
    clf: set[str] = set()
    orc: set[str] = set()
    for case in generate_domain_cases(ROOT):
        rec = classify_source(
            case["source"],
            rules,
            contexts=case.get("classifier_contexts"),
            computed=case.get("classifier_computed"),
        )
        ore = classify_oracle(case["source"], facts=case.get("oracle_facts"))
        clf.add(rec.rule_id)
        orc.add(ore.rule_id)
        if (
            rec.rule_id != ore.rule_id
            or rec.source_identity != ore.source_identity
            or rec.outcome_slot != ore.outcome_slot
            or rec.failure_state != ore.failure_state
        ):
            disagreements += 1
    assert disagreements == 0
    assert len(clf) == 22
    assert len(orc) == 22
