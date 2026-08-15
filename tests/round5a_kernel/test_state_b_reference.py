"""State B independence and mapping tests."""

from __future__ import annotations

import json
from pathlib import Path

from tools.round5a_kernel.models import KernelError, normalize_identity
from tools.round5a_kernel.state_b_reference import compute_state_b

ROOT = Path(__file__).resolve().parents[2]
ORACLE = ROOT / "specs" / "round5a_kernel" / "oracles" / "state_b_cases.json"


def _sid(x: str) -> str:
    return normalize_identity({"legacy_reservation_id": x})


def test_state_b_literal_oracle_pack() -> None:
    doc = json.loads(ORACLE.read_text(encoding="utf-8"))
    for case in doc["cases"]:
        proof = compute_state_b(
            legacy_sources=case.get("legacy_sources") or [],
            durable_outcomes=case.get("durable_outcomes") or [],
            events=case.get("events") or [],
            archives=case.get("archives") or [],
            discrepancies=case.get("discrepancies") or [],
            fallback_records=case.get("fallback_records") or [],
            source_reference_membership=case.get("source_reference_membership") or {},
            hostile_cached_digest=case.get("hostile_cached_digest"),
            hostile_cached_count=case.get("hostile_cached_count"),
        )
        exp = case["expected"]
        assert proof.valid is bool(exp["valid"]), case["case_id"]
        assert proof.evidence.get("failure_state") == exp.get("failure_state"), case["case_id"]
        for code in exp.get("failure_codes") or []:
            assert code in proof.failure_codes, (case["case_id"], code, proof.failure_codes)


def test_exactly_one_slot_enforcement() -> None:
    s = "00000000-0000-4000-8000-000000000001"
    sid = _sid(s)
    ok = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s}],
        durable_outcomes=[{"source_identity": sid, "outcome_slot": "slot-a"}],
    )
    assert ok.valid is True

    zero = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s}],
        durable_outcomes=[],
    )
    assert zero.valid is False
    assert zero.evidence["failure_state"] == "failed_frozen"
    assert "zero_outcome_slots" in zero.failure_codes


def test_forged_digest_detected() -> None:
    s = "00000000-0000-4000-8000-000000000001"
    sid = _sid(s)
    proof = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s}],
        durable_outcomes=[{"source_identity": sid, "outcome_slot": "a"}],
        hostile_cached_digest="FORGED",
    )
    assert proof.valid is False
    assert "forged_cached_digest" in proof.failure_codes


def test_forbidden_kwargs_rejected() -> None:
    try:
        compute_state_b(
            legacy_sources=[{"legacy_reservation_id": "s1"}],
            durable_outcomes=[],
            expected_rule="RULE-17",  # type: ignore[call-arg]
        )
        assert False, "expected KernelError"
    except KernelError as exc:
        assert exc.code == "KR-STATE-B-INPUT"
