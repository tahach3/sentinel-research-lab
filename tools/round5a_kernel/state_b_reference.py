"""Independent State B recomputation from raw durable facts.

This module must not import predicate_engine, classification_reference,
oracle_reference, state_a_reference, or bounded_domain.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from tools.round5a_kernel.models import KernelError, StateProof, normalize_identity

FORBIDDEN_INPUT_NAMES = frozenset(
    {
        "expected_rule",
        "expected_outcome",
        "classification",
        "predicate_result",
        "state_a_result",
        "cached_classification",
        "cached_identity_set",
        "cached_count",
        "cached_digest",
        "classifier_result",
        "oracle_result",
    }
)


def _identity(source: Mapping[str, Any]) -> str:
    return normalize_identity({"legacy_reservation_id": source.get("legacy_reservation_id")})


def compute_state_b(
    *,
    legacy_sources: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]] | None = None,
    archives: Sequence[Mapping[str, Any]] | None = None,
    discrepancies: Sequence[Mapping[str, Any]] | None = None,
    fallback_records: Sequence[Mapping[str, Any]] | None = None,
    durable_outcomes: Sequence[Mapping[str, Any]] | None = None,
    source_reference_membership: Mapping[str, Sequence[str]] | None = None,
    hostile_cached_digest: str | None = None,
    hostile_cached_count: int | None = None,
    **forbidden: Any,
) -> StateProof:
    """Recompute identity and ownership sets from durable facts only."""
    if forbidden:
        bad = sorted(set(forbidden) & FORBIDDEN_INPUT_NAMES) or sorted(forbidden)
        raise KernelError("KR-STATE-B-INPUT", f"forbidden State B inputs: {bad}")

    events = list(events or [])
    archives = list(archives or [])
    discrepancies = list(discrepancies or [])
    fallback_records = list(fallback_records or [])
    durable_outcomes = list(durable_outcomes or [])
    source_reference_membership = dict(source_reference_membership or {})

    failures: list[str] = []

    source_ids = [_identity(s) for s in legacy_sources]
    source_identity_set = tuple(sorted(set(source_ids)))
    if any(v > 1 for v in Counter(source_ids).values()):
        failures.append("duplicate_source_identity")

    ownership: dict[str, list[str]] = defaultdict(list)
    for outcome in durable_outcomes:
        sid = str(outcome.get("source_identity") or outcome.get("legacy_reservation_id") or "")
        if not sid and "legacy_reservation_id" in outcome:
            sid = normalize_identity({"legacy_reservation_id": outcome["legacy_reservation_id"]})
        slot = str(outcome.get("outcome_slot") or outcome.get("slot") or "")
        ownership[sid].append(slot)

    for sid in source_identity_set:
        slots = ownership.get(sid, [])
        if len(slots) == 0:
            failures.append("zero_outcome_slots")
        elif len(slots) > 1:
            failures.append("multiple_outcome_slots")

    for sid, slots in ownership.items():
        if sid not in set(source_identity_set):
            failures.append("unknown_outcome_source")

    def collect_refs(rows: Sequence[Mapping[str, Any]], key: str = "source_identity") -> tuple[str, ...]:
        refs: list[str] = []
        for row in rows:
            if key in row:
                refs.append(str(row[key]))
            elif "legacy_reservation_id" in row:
                refs.append(normalize_identity({"legacy_reservation_id": row["legacy_reservation_id"]}))
            elif "source_refs" in row:
                refs.extend(str(x) for x in row["source_refs"])
        return tuple(refs)

    event_refs = collect_refs(events)
    archive_refs = collect_refs(archives)
    discrepancy_refs = collect_refs(discrepancies)
    fallback_refs = collect_refs(fallback_records)

    known = set(source_identity_set)
    for label, refs in (
        ("event", event_refs),
        ("archive", archive_refs),
        ("discrepancy", discrepancy_refs),
        ("fallback", fallback_refs),
    ):
        if set(refs) - known:
            failures.append(f"unknown_{label}_reference")
        if len(refs) != len(set(refs)) and label != "event":
            failures.append(f"duplicate_{label}_reference")

    event_ids_seen: set[str] = set()
    for event in events:
        refs = [str(x) for x in event.get("source_refs", [])]
        if len(refs) != len(set(refs)):
            failures.append("duplicate_event_reference")
        event_id = str(event.get("event_id") or event.get("id") or "")
        event_ids_seen.add(event_id)
        if event_id in source_reference_membership:
            expected = [str(x) for x in source_reference_membership.get(event_id, refs)]
            # Ordered comparison: order-only drift is a failure.
            if refs != expected:
                if set(refs) != set(expected):
                    failures.append("incomplete_shared_event_reference_sets")
                else:
                    failures.append("shared_event_order_mismatch")
        if len(refs) > 1:
            for sid in refs:
                membership = source_reference_membership.get(sid)
                if membership is not None and event_id not in set(membership):
                    failures.append("incomplete_shared_event_reference_sets")

    # Membership keys that are not source identities must name an existing event row.
    for key in source_reference_membership:
        if key not in known and key not in event_ids_seen:
            failures.append("missing_event_reference")

    outcome_slot_set = tuple(sorted({s for slots in ownership.values() for s in slots if s}))
    classified_identity_set = tuple(sorted(ownership.keys()))

    if len(source_identity_set) == len(classified_identity_set) and set(source_identity_set) != set(
        classified_identity_set
    ):
        failures.append("equal_counts_unequal_identities")

    if (
        len(source_identity_set) == len(outcome_slot_set)
        and set(source_identity_set) != set(classified_identity_set)
        and "equal_counts_unequal_identities" not in failures
    ):
        failures.append("equal_counts_unequal_identities")

    # Hostile cached inputs are verified, never trusted.
    if hostile_cached_count is not None and int(hostile_cached_count) != len(
        [sid for sid, slots in ownership.items() if slots]
    ):
        failures.append("forged_cached_count")
    if hostile_cached_digest is not None:
        derived_digest = normalize_identity(
            {
                "sources": ",".join(source_identity_set),
                "outcomes": ",".join(outcome_slot_set),
            }
        )
        if str(hostile_cached_digest) != derived_digest:
            failures.append("forged_cached_digest")

    failures = list(dict.fromkeys(failures))
    if failures:
        evidence = {"failure_state": "failed_frozen"}
    else:
        evidence = {"failure_state": None}

    sets = {
        "source_identity_set": source_identity_set,
        "classified_identity_set": tuple(sorted(set(classified_identity_set) & known)),
        "event_source_reference_set": tuple(sorted(set(event_refs))),
        "archive_source_reference_set": tuple(sorted(set(archive_refs))),
        "discrepancy_source_reference_set": tuple(sorted(set(discrepancy_refs))),
        "fallback_source_reference_set": tuple(sorted(set(fallback_refs))),
        "outcome_slot_set": outcome_slot_set,
    }
    return StateProof(
        valid=not failures,
        failure_codes=tuple(failures),
        sets=sets,
        evidence=evidence,
    )
