"""Independent decision-table reconciliation oracle (KR-ND-009).

This module is a second reference implementation authored from KR-ND decisions.
It intentionally uses a flat ordered decision table — not an AST predicate
interpreter and not the reconciliation contract document.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from tools.round5a_kernel.models import ClassificationRecord, KernelError, normalize_identity

# Allowed shared imports only: models (identity + ClassificationRecord + errors).
# Prohibited: predicate_engine, classification_reference, state_a/b, contract loaders.

ALLOWED_STATUSES = frozenset({"reserved", "finalized", "released"})

# Flat decision table: rule_id -> (order, slot_type, failure_state, fallback, reason)
RULE_TABLE: tuple[tuple[str, int, str, str | None, bool, str], ...] = (
    ("RULE-01", 1, "source_owned", None, False, "KR-ORACLE-INVALID-STATUS"),
    ("RULE-02", 2, "source_owned", None, False, "KR-ORACLE-MISSING-PROPOSAL"),
    ("RULE-03", 3, "source_owned", None, False, "KR-ORACLE-MISSING-AUTHORIZATION"),
    ("RULE-04", 4, "source_owned", None, False, "KR-ORACLE-MISSING-CASE"),
    ("RULE-05", 5, "source_owned", None, False, "KR-ORACLE-DUP-IDEMPOTENCY"),
    ("RULE-06", 6, "source_owned", None, False, "KR-ORACLE-DUP-CASE-ATTEMPT"),
    ("RULE-07", 7, "source_owned", None, False, "KR-ORACLE-DUP-ENVELOPE"),
    ("RULE-08", 8, "source_owned", None, False, "KR-ORACLE-EVENT-CONFLICT"),
    ("RULE-09", 9, "source_owned", None, False, "KR-ORACLE-LEDGER-REQUEST-CONFLICT"),
    ("RULE-10", 10, "source_owned", None, False, "KR-ORACLE-LEDGER-SUCCESS-CONFLICT"),
    ("RULE-11", 11, "source_owned", None, False, "KR-ORACLE-TOKEN-CONFLICT"),
    ("RULE-12", 12, "source_owned", None, False, "KR-ORACLE-COST-CONFLICT"),
    ("RULE-13", 13, "source_owned", None, False, "KR-ORACLE-MALFORMED-COUNTER"),
    ("RULE-14", 14, "source_owned", None, False, "KR-ORACLE-UNACK-DISCREPANCY"),
    ("RULE-15", 15, "ledger_orphan", None, False, "KR-ORACLE-LEDGER-ORPHAN"),
    ("RULE-16", 16, "envelope_orphan", None, False, "KR-ORACLE-ENVELOPE-ORPHAN"),
    ("RULE-17", 17, "shared_event", None, False, "KR-ORACLE-RESERVED-WITH-ENVELOPE"),
    ("RULE-18", 18, "shared_event", None, False, "KR-ORACLE-RESERVED-WITHOUT-ENVELOPE"),
    ("RULE-19", 19, "shared_event", None, False, "KR-ORACLE-FINALIZED-WITH-ENVELOPE"),
    ("RULE-20", 20, "shared_event", None, False, "KR-ORACLE-FINALIZED-WITHOUT-ENVELOPE"),
    ("RULE-21", 21, "source_owned", None, False, "KR-ORACLE-RELEASED"),
    ("RULE-22", 22, "fallback", "failed_frozen", True, "KR-ORACLE-FALLBACK"),
)

_RULE_BY_ID = {r[0]: r for r in RULE_TABLE}


@dataclass(frozen=True)
class OracleFacts:
    """Typed decision-table inputs — not AST computed_value_ref keys."""

    duplicate_idempotency: bool = False
    duplicate_case_attempt: bool = False
    duplicate_envelope_link: bool = False
    event_natural_key_missing: bool = False
    ledger_used_as_enforcement: bool = False
    ledger_success_mismatch: bool = False
    token_over_policy: bool = False
    cost_conflict: bool = False
    negative_or_malformed_counter: bool = False
    unacknowledged_discrepancy: bool = False
    orphaned_ledger: bool = False
    orphaned_envelope: bool = False


def facts_from_mapping(raw: Mapping[str, Any] | None) -> OracleFacts:
    raw = dict(raw or {})
    return OracleFacts(
        duplicate_idempotency=bool(raw.get("duplicate_idempotency", False)),
        duplicate_case_attempt=bool(raw.get("duplicate_case_attempt", False)),
        duplicate_envelope_link=bool(raw.get("duplicate_envelope_link", False)),
        event_natural_key_missing=bool(raw.get("event_natural_key_missing", False)),
        ledger_used_as_enforcement=bool(raw.get("ledger_used_as_enforcement", False)),
        ledger_success_mismatch=bool(raw.get("ledger_success_mismatch", False)),
        token_over_policy=bool(raw.get("token_over_policy", False)),
        cost_conflict=bool(raw.get("cost_conflict", False)),
        negative_or_malformed_counter=bool(raw.get("negative_or_malformed_counter", False)),
        unacknowledged_discrepancy=bool(raw.get("unacknowledged_discrepancy", False)),
        orphaned_ledger=bool(raw.get("orphaned_ledger", False)),
        orphaned_envelope=bool(raw.get("orphaned_envelope", False)),
    )


def _has(source: Mapping[str, Any], key: str) -> bool:
    return key in source


def _identity(source: Mapping[str, Any], rule_id: str) -> str:
    if "legacy_reservation_id" not in source and rule_id not in {"RULE-15", "RULE-16"}:
        raise KernelError("KR-ORACLE-IDENTITY", "legacy_reservation_id required")
    if rule_id == "RULE-15":
        return normalize_identity({"ledger_id": source.get("ledger_id")})
    if rule_id == "RULE-16":
        return normalize_identity({"envelope_id": source.get("envelope_id")})
    return normalize_identity({"legacy_reservation_id": source["legacy_reservation_id"]})


def _slot(slot_type: str, source: Mapping[str, Any], rule_id: str) -> str:
    # Mirror classifier slot_identity shape without importing the classifier.
    parts: list[tuple[str, Any]] = [("slot_type", slot_type), ("slot_name", slot_type)]
    if rule_id == "RULE-15":
        parts.append(("ledger_id", source.get("ledger_id", source.get("legacy_reservation_id"))))
    elif rule_id == "RULE-16":
        parts.append(("envelope_id", source.get("envelope_id", source.get("legacy_reservation_id"))))
    else:
        parts.append(("legacy_reservation_id", source.get("legacy_reservation_id")))
    return normalize_identity(parts)


def _match_rule(source: Mapping[str, Any], facts: OracleFacts) -> str:
    """Ordered decision-table matching — visibly different from AST evaluation."""
    status_present = _has(source, "status")
    status = source.get("status") if status_present else None
    envelope_present = _has(source, "envelope_id")
    envelope = source.get("envelope_id") if envelope_present else None

    # RULE-01: present-null status OR unknown/invalid status value
    if status_present and (status is None or status not in ALLOWED_STATUSES):
        return "RULE-01"

    # RULE-02..04 missing related identifiers (present-null)
    if _has(source, "pilot_proposal_id") and source.get("pilot_proposal_id") is None:
        return "RULE-02"
    if _has(source, "authorization_id") and source.get("authorization_id") is None:
        return "RULE-03"
    if _has(source, "benchmark_case_id") and source.get("benchmark_case_id") is None:
        return "RULE-04"

    # Conflict / duplicate fact flags (decision-table axes)
    if facts.duplicate_idempotency:
        return "RULE-05"
    if facts.duplicate_case_attempt:
        return "RULE-06"
    if facts.duplicate_envelope_link:
        return "RULE-07"
    if facts.event_natural_key_missing and status == "reserved":
        return "RULE-08"
    if facts.ledger_used_as_enforcement:
        return "RULE-09"
    if facts.ledger_success_mismatch:
        return "RULE-10"
    if facts.token_over_policy:
        return "RULE-11"
    if facts.cost_conflict:
        return "RULE-12"
    if facts.negative_or_malformed_counter:
        return "RULE-13"
    if facts.unacknowledged_discrepancy:
        return "RULE-14"
    if facts.orphaned_ledger:
        return "RULE-15"
    if facts.orphaned_envelope:
        return "RULE-16"

    # Ordinary status/envelope branches
    if status == "reserved" and envelope is not None:
        return "RULE-17"
    if status == "reserved" and envelope is None:
        return "RULE-18"
    if status == "finalized" and envelope is not None:
        return "RULE-19"
    if status == "finalized" and envelope is None:
        return "RULE-20"
    if status == "released":
        return "RULE-21"

    # Missing status → fallback (RULE-22). Present-null already handled by RULE-01.
    if not status_present:
        return "RULE-22"

    return "RULE-22"


def classify_oracle(
    source: Mapping[str, Any],
    *,
    facts: Mapping[str, Any] | OracleFacts | None = None,
) -> ClassificationRecord:
    """Classify one source via the independent decision table."""
    ofacts = facts if isinstance(facts, OracleFacts) else facts_from_mapping(facts)
    rule_id = _match_rule(source, ofacts)
    meta = _RULE_BY_ID[rule_id]
    _, order, slot_type, failure_state, fallback, reason = meta
    sid = _identity(source, rule_id)
    slot = _slot(slot_type, source, rule_id)
    decisive: dict[str, Any] = {}
    for key in ("status", "envelope_id", "pilot_proposal_id", "authorization_id", "benchmark_case_id"):
        if key in source:
            decisive[key] = source[key]
    return ClassificationRecord(
        source_identity=sid,
        rule_id=rule_id,
        order=order,
        outcome_slot=slot,
        failure_state=failure_state,
        actions=({"reason": reason},),
        decisive_fields=decisive,
        predicate_trace=({"rule_id": rule_id, "representation": "decision_table"},),
        fallback=fallback,
    )


def classify_oracle_many(
    sources: list[Mapping[str, Any]],
    *,
    facts_by_index: Mapping[int, Mapping[str, Any]] | None = None,
) -> list[ClassificationRecord]:
    facts_by_index = dict(facts_by_index or {})
    return [
        classify_oracle(src, facts=facts_by_index.get(i))
        for i, src in enumerate(sources)
    ]
