"""State A proof model — may consume classification records."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

from tools.round5a_kernel.models import ClassificationRecord, StateProof


def compute_state_a(
    *,
    source_identities: Sequence[str],
    classifications: Sequence[ClassificationRecord],
    event_refs: Mapping[str, Sequence[str]] | None = None,
    archive_refs: Mapping[str, Sequence[str]] | None = None,
    discrepancy_refs: Mapping[str, Sequence[str]] | None = None,
    fallback_refs: Mapping[str, Sequence[str]] | None = None,
    shared_event_members: Mapping[str, Sequence[str]] | None = None,
) -> StateProof:
    """Exact identity-set proof over classification outputs."""
    event_refs = dict(event_refs or {})
    archive_refs = dict(archive_refs or {})
    discrepancy_refs = dict(discrepancy_refs or {})
    fallback_refs = dict(fallback_refs or {})
    shared_event_members = dict(shared_event_members or {})

    source_identity_set = tuple(sorted(set(source_identities)))
    classified_identity_set = tuple(sorted({c.source_identity for c in classifications}))
    outcome_slot_set = tuple(sorted({c.outcome_slot for c in classifications}))

    event_source_reference_set = tuple(sorted({s for refs in event_refs.values() for s in refs}))
    archive_source_reference_set = tuple(sorted({s for refs in archive_refs.values() for s in refs}))
    discrepancy_source_reference_set = tuple(
        sorted({s for refs in discrepancy_refs.values() for s in refs})
    )
    fallback_source_reference_set = tuple(
        sorted({s for refs in fallback_refs.values() for s in refs})
    )

    failures: list[str] = []

    source_counts = Counter(source_identities)
    for sid, count in source_counts.items():
        if count > 1:
            failures.append("duplicate_source_identity")

    class_counts = Counter(c.source_identity for c in classifications)
    for sid in source_identity_set:
        if sid not in class_counts:
            failures.append("missing_classification")
        elif class_counts[sid] == 0:
            failures.append("zero_outcome_slots")
        elif class_counts[sid] > 1:
            failures.append("multiple_outcome_slots")

    for c in classifications:
        if not c.outcome_slot:
            failures.append("zero_outcome_slots")

    known = set(source_identity_set)
    for label, refs in (
        ("event", event_source_reference_set),
        ("archive", archive_source_reference_set),
        ("discrepancy", discrepancy_source_reference_set),
        ("fallback", fallback_source_reference_set),
    ):
        unknown = set(refs) - known
        if unknown:
            failures.append(f"unknown_{label}_reference")
        if len(refs) != len(set(refs)):
            failures.append(f"duplicate_{label}_reference")

    for event_id, members in shared_event_members.items():
        member_set = set(members)
        if len(members) != len(member_set):
            failures.append("duplicate_event_reference")
        expected = set(event_refs.get(event_id, ()))
        if member_set != expected:
            failures.append("incomplete_shared_event_reference_sets")

    if len(source_identity_set) == len(classified_identity_set) and set(source_identity_set) != set(
        classified_identity_set
    ):
        failures.append("equal_counts_unequal_identities")

    failures = list(dict.fromkeys(failures))
    sets = {
        "source_identity_set": source_identity_set,
        "classified_identity_set": classified_identity_set,
        "event_source_reference_set": event_source_reference_set,
        "archive_source_reference_set": archive_source_reference_set,
        "discrepancy_source_reference_set": discrepancy_source_reference_set,
        "fallback_source_reference_set": fallback_source_reference_set,
        "outcome_slot_set": outcome_slot_set,
    }
    return StateProof(valid=not failures, failure_codes=tuple(failures), sets=sets)


def state_a_from_records(
    sources: Sequence[Mapping[str, Any]],
    classifications: Sequence[ClassificationRecord],
    **kwargs: Any,
) -> StateProof:
    identities = []
    for src, cls in zip(sources, classifications):
        identities.append(cls.source_identity)
    # also include any source without classification by using provided identities
    if len(identities) < len(sources):
        pass
    return compute_state_a(source_identities=identities, classifications=classifications, **kwargs)
