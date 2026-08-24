"""State A reference tests."""

from __future__ import annotations

from tools.round5a_kernel.models import ClassificationRecord
from tools.round5a_kernel.state_a_reference import compute_state_a


def _rec(sid: str, slot: str, rule: str = "RULE-17") -> ClassificationRecord:
    return ClassificationRecord(
        source_identity=sid,
        rule_id=rule,
        order=17,
        outcome_slot=slot,
        failure_state=None,
        actions=tuple(),
        decisive_fields={},
        predicate_trace=tuple(),
    )


def test_state_a_identity_sets_and_invalid_cases() -> None:
    good = compute_state_a(
        source_identities=["s1"],
        classifications=[_rec("s1", "o1")],
        event_refs={"e1": ["s1"]},
        shared_event_members={"e1": ["s1"]},
    )
    assert good.valid is True
    assert good.sets["source_identity_set"] == ("s1",)
    assert good.sets["outcome_slot_set"] == ("o1",)

    assert compute_state_a(source_identities=["s1", "s2"], classifications=[_rec("s1", "o1")]).valid is False
    assert compute_state_a(source_identities=["s1", "s1"], classifications=[_rec("s1", "o1"), _rec("s1", "o2")]).valid is False
    assert compute_state_a(
        source_identities=["s1"],
        classifications=[_rec("s1", "o1"), _rec("s1", "o2")],
    ).valid is False
    assert compute_state_a(source_identities=["s1"], classifications=[]).valid is False
    assert compute_state_a(
        source_identities=["s1"],
        classifications=[_rec("s1", "o1")],
        event_refs={"e": ["unknown"]},
    ).valid is False
    assert compute_state_a(
        source_identities=["s1"],
        classifications=[_rec("s2", "o2")],
    ).valid is False
    # forged / cached digest inputs are irrelevant — State A uses classification records only
    proof = compute_state_a(
        source_identities=["s1"],
        classifications=[_rec("s1", "o1")],
    )
    assert "cached" not in proof.as_dict()
