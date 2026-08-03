"""Classification reference and bounded-domain tests."""

from __future__ import annotations

import json
from pathlib import Path

from tools.round5a_kernel.classification_reference import classify_source, load_reconciliation_contract
from tools.round5a_kernel.models import MISSING, normalize_identity
from tools.round5a_kernel.state_b_reference import compute_state_b


ROOT = Path(__file__).resolve().parents[2]


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


def test_happy_paths() -> None:
    rules = _rules()
    for status, env, expected in (
        ("reserved", "e1", "RULE-17"),
        ("reserved", None, "RULE-18"),
        ("finalized", "e1", "RULE-19"),
        ("finalized", None, "RULE-20"),
        ("released", None, "RULE-21"),
    ):
        rec = classify_source(
            {
                "legacy_reservation_id": f"00000000-0000-4000-8000-0000000000{expected[-2:]}",
                "pilot_proposal_id": "pp",
                "authorization_id": "auth",
                "benchmark_case_id": "case",
                "idempotency_key": "idem",
                "envelope_id": env,
                "status": status,
            },
            rules,
        )
        assert rec.rule_id == expected


def test_bounded_domain_zero_disagreements() -> None:
    rules = _rules()
    disagreements = 0
    cases = 0
    for i, status in enumerate(["reserved", "finalized", "released", "nope", None]):
        for env in ("env", None):
            cases += 1
            source = {
                "legacy_reservation_id": f"00000000-0000-4000-8000-abcd000000{i}{0 if env else 1}",
                "pilot_proposal_id": "pp",
                "authorization_id": "auth",
                "benchmark_case_id": "case",
                "idempotency_key": "idem",
                "envelope_id": env,
                "status": status,
            }
            rec = classify_source(source, rules)
            sid = rec.source_identity
            state_b = compute_state_b(
                legacy_sources=[source],
                durable_outcomes=[{"source_identity": sid, "outcome_slot": rec.outcome_slot}],
                events=[{"event_id": "e", "source_refs": [sid]}]
                if rec.rule_id in {"RULE-17", "RULE-18", "RULE-19", "RULE-20"}
                else [],
                archives=[{"source_identity": sid}] if rec.rule_id == "RULE-21" else [],
                discrepancies=[{"source_identity": sid}] if int(rec.order) <= 16 else [],
                fallback_records=[{"source_identity": sid}] if rec.fallback else [],
                source_reference_membership={"e": [sid]}
                if rec.rule_id in {"RULE-17", "RULE-18", "RULE-19", "RULE-20"}
                else {},
            )
            if sid not in state_b.sets["source_identity_set"]:
                disagreements += 1
            if state_b.valid and sid not in state_b.sets["classified_identity_set"]:
                disagreements += 1
    # missing status
    cases += 1
    missing = {
        "legacy_reservation_id": "00000000-0000-4000-8000-ffff00000001",
        "pilot_proposal_id": "pp",
        "authorization_id": "auth",
        "benchmark_case_id": "case",
        "idempotency_key": "idem",
    }
    rec = classify_source(missing, rules)
    sid = rec.source_identity
    state_b = compute_state_b(
        legacy_sources=[missing],
        durable_outcomes=[{"source_identity": sid, "outcome_slot": rec.outcome_slot}],
        fallback_records=[{"source_identity": sid}],
    )
    if sid not in state_b.sets["source_identity_set"]:
        disagreements += 1
    assert cases > 0
    assert disagreements == 0
