"""State B independence and mapping tests."""

from __future__ import annotations

from tools.round5a_kernel.models import normalize_identity
from tools.round5a_kernel.state_b_reference import compute_state_b


def _sid(x: str) -> str:
    return normalize_identity({"legacy_reservation_id": x})


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

    two = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s}],
        durable_outcomes=[
            {"source_identity": sid, "outcome_slot": "a"},
            {"source_identity": sid, "outcome_slot": "b"},
        ],
    )
    assert two.valid is False
    assert two.evidence["failure_state"] == "failed_frozen"


def test_duplicates_shared_events_and_membership_changes() -> None:
    s1 = "00000000-0000-4000-8000-000000000001"
    s2 = "00000000-0000-4000-8000-000000000002"
    sid1, sid2 = _sid(s1), _sid(s2)

    dup = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}, {"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": sid1, "outcome_slot": "a"}],
    )
    assert dup.valid is False
    assert "duplicate_source_identity" in dup.failure_codes

    shared_ok = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}, {"legacy_reservation_id": s2}],
        durable_outcomes=[
            {"source_identity": sid1, "outcome_slot": "a"},
            {"source_identity": sid2, "outcome_slot": "b"},
        ],
        events=[{"event_id": "e1", "source_refs": [sid1, sid2]}],
        source_reference_membership={"e1": [sid1, sid2]},
    )
    assert shared_ok.valid is True

    incomplete = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}, {"legacy_reservation_id": s2}],
        durable_outcomes=[
            {"source_identity": sid1, "outcome_slot": "a"},
            {"source_identity": sid2, "outcome_slot": "b"},
        ],
        events=[{"event_id": "e1", "source_refs": [sid1, sid2]}],
        source_reference_membership={"e1": [sid1]},
    )
    assert incomplete.valid is False
    assert incomplete.evidence["failure_state"] == "failed_frozen"

    unknown_event = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": sid1, "outcome_slot": "a"}],
        events=[{"event_id": "e1", "source_refs": ["unknown"]}],
    )
    assert unknown_event.valid is False

    unknown_archive = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": sid1, "outcome_slot": "a"}],
        archives=[{"source_identity": "nope"}],
    )
    assert unknown_archive.valid is False


def test_equal_counts_unequal_identities_and_mutations() -> None:
    s1 = "00000000-0000-4000-8000-000000000001"
    sid1 = _sid(s1)
    unequal = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": "other", "outcome_slot": "a"}],
    )
    assert unequal.valid is False
    assert unequal.evidence["failure_state"] == "failed_frozen"

    # State B ignores forged State A digests / cached classifications by accepting
    # only raw durable facts — no classifier fields are consulted.
    base = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": sid1, "outcome_slot": "a"}],
        events=[{"event_id": "e1", "source_refs": [sid1]}],
        source_reference_membership={"e1": [sid1]},
    )
    assert base.valid is True

    removed_event = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": sid1, "outcome_slot": "a"}],
        events=[],
    )
    assert removed_event.valid is True  # absence of events is allowed if outcomes exist

    changed_membership = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": sid1, "outcome_slot": "a"}],
        events=[{"event_id": "e1", "source_refs": [sid1]}],
        source_reference_membership={"e1": []},
    )
    assert changed_membership.valid is False
    assert changed_membership.evidence["failure_state"] == "failed_frozen"

    discrepancy_only = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": sid1, "outcome_slot": "disc"}],
        discrepancies=[{"source_identity": sid1}],
    )
    assert discrepancy_only.valid is True

    fallback_only = compute_state_b(
        legacy_sources=[{"legacy_reservation_id": s1}],
        durable_outcomes=[{"source_identity": sid1, "outcome_slot": "fb"}],
        fallback_records=[{"source_identity": sid1}],
    )
    assert fallback_only.valid is True
