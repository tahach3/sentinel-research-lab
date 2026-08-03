"""Independent oracle and differential checks."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from tools.round5a_kernel.bounded_domain import generate_domain_cases
from tools.round5a_kernel.classification_reference import classify_source, load_reconciliation_contract
from tools.round5a_kernel.models import ClassificationRecord
from tools.round5a_kernel import classification_reference as cr
from tools.round5a_kernel import oracle_reference as ore
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
        ore_rec = classify_oracle(case["source"], facts=case.get("oracle_facts"))
        clf.add(rec.rule_id)
        orc.add(ore_rec.rule_id)
        if (
            rec.rule_id != ore_rec.rule_id
            or rec.source_identity != ore_rec.source_identity
            or rec.outcome_slot != ore_rec.outcome_slot
            or rec.failure_state != ore_rec.failure_state
        ):
            disagreements += 1
    assert disagreements == 0
    assert len(clf) == 22
    assert len(orc) == 22


def test_classifier_corruption_with_independent_oracle_diverges() -> None:
    rules = load_reconciliation_contract(ROOT)["rules"]
    cases = {c["case_id"]: c for c in generate_domain_cases(ROOT)}
    seed17 = cases["seed_rule-17"]
    real = cr.classify_source

    def always22(source, rules_arg, **kwargs):
        rec = real(source, rules_arg, **kwargs)
        return ClassificationRecord(
            source_identity=rec.source_identity,
            rule_id="RULE-22",
            order=22,
            outcome_slot=rec.outcome_slot,
            failure_state="failed_frozen",
            actions=rec.actions,
            decisive_fields=rec.decisive_fields,
            predicate_trace=rec.predicate_trace,
            fallback=True,
        )

    cr.classify_source = always22
    try:
        rec = cr.classify_source(seed17["source"], rules)
        ore_rec = ore.classify_oracle(seed17["source"], facts={})
        assert rec.rule_id != ore_rec.rule_id
    finally:
        cr.classify_source = real


def test_coupled_oracle_triggers_independence_failure() -> None:
    rules = load_reconciliation_contract(ROOT)["rules"]
    cases = {c["case_id"]: c for c in generate_domain_cases(ROOT)}
    seed17 = cases["seed_rule-17"]
    real_oracle = ore.classify_oracle
    real_classify = cr.classify_source
    independent = real_oracle(seed17["source"], facts={})

    def coupled(source, facts=None):
        return cr.classify_source(source, rules)

    def corrupt(source, rules_arg, **kwargs):
        rec = real_classify(source, rules_arg, **kwargs)
        return ClassificationRecord(
            source_identity=rec.source_identity,
            rule_id="RULE-22",
            order=22,
            outcome_slot=rec.outcome_slot,
            failure_state="failed_frozen",
            actions=rec.actions,
            decisive_fields=rec.decisive_fields,
            predicate_trace=rec.predicate_trace,
            fallback=True,
        )

    ore.classify_oracle = coupled
    cr.classify_source = corrupt
    try:
        coupled_rec = ore.classify_oracle(seed17["source"], facts={})
        assert coupled_rec.rule_id == "RULE-22"
        assert independent.rule_id != "RULE-22"
    finally:
        ore.classify_oracle = real_oracle
        cr.classify_source = real_classify


def test_closure_only_check_cannot_satisfy_coupling_mutation() -> None:
    rules = load_reconciliation_contract(ROOT)["rules"]

    def oracle_calls_classifier(source, facts=None):
        return cr.classify_source(source, rules)

    freevars = oracle_calls_classifier.__code__.co_freevars
    # A local closure reference alone is not proof of runtime independence failure.
    assert "cr" in freevars or "classify_source" in oracle_calls_classifier.__code__.co_names
    # Require runtime coupling detection path instead.
    real_oracle = ore.classify_oracle
    independent = real_oracle(
        {
            "legacy_reservation_id": "00000000-0000-4000-8000-aaaaaaaaaa17",
            "pilot_proposal_id": "pp-17",
            "authorization_id": "auth-17",
            "benchmark_case_id": "case-17",
            "idempotency_key": "idem-17",
            "envelope_id": "env-17",
            "status": "reserved",
        },
        facts={},
    )
    assert independent.rule_id == "RULE-17"
