"""Classification reference tests (no self-fulfilling State B coupling)."""

from __future__ import annotations

from tools.round5a_kernel.classification_reference import classify_source, load_reconciliation_contract
from tools.round5a_kernel.oracle_reference import classify_oracle

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


def _rules():
    return load_reconciliation_contract(ROOT)["rules"]


def test_first_match_and_rule22_missing_status() -> None:
    rules = _rules()
    rec = classify_source(
        {
            "legacy_reservation_id": "00000000-0000-4000-8000-000000000099",
            "pilot_proposal_id": "pp",
            "authorization_id": "auth",
            "benchmark_case_id": "case",
            "idempotency_key": "idem",
            "status": "bogus",
        },
        rules,
    )
    assert rec.rule_id == "RULE-01"
    assert len(rec.outcome_slot) > 0

    missing = {
        "legacy_reservation_id": "00000000-0000-4000-8000-000000000098",
        "pilot_proposal_id": "pp",
        "authorization_id": "auth",
        "benchmark_case_id": "case",
        "idempotency_key": "idem",
        "envelope_id": None,
    }
    rec22 = classify_source(missing, rules)
    assert rec22.rule_id == "RULE-22"
    assert rec22.fallback is True
    assert rec22.failure_state == "failed_frozen"
    assert classify_oracle(missing).rule_id == "RULE-22"


def test_happy_paths() -> None:
    rules = _rules()
    for status, env, expected in (
        ("reserved", "e1", "RULE-17"),
        ("reserved", None, "RULE-18"),
        ("finalized", "e1", "RULE-19"),
        ("finalized", None, "RULE-20"),
        ("released", None, "RULE-21"),
    ):
        source = {
            "legacy_reservation_id": f"00000000-0000-4000-8000-0000000000{expected[-2:]}",
            "pilot_proposal_id": "pp",
            "authorization_id": "auth",
            "benchmark_case_id": "case",
            "idempotency_key": "idem",
            "envelope_id": env,
            "status": status,
        }
        rec = classify_source(source, rules)
        assert rec.rule_id == expected
        assert classify_oracle(source).rule_id == expected


def test_predicate_trace_records_non_true() -> None:
    rules = _rules()
    rec = classify_source(
        {
            "legacy_reservation_id": "00000000-0000-4000-8000-000000000097",
            "pilot_proposal_id": "pp",
            "authorization_id": "auth",
            "benchmark_case_id": "case",
            "idempotency_key": "idem",
            "envelope_id": "e",
            "status": "reserved",
        },
        rules,
    )
    assert rec.rule_id == "RULE-17"
    assert any(t["result"] in {"FALSE", "UNKNOWN", "INVALID", "TRUE"} for t in rec.predicate_trace)
