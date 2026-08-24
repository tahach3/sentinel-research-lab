"""Shared immutable structures for the Round 5A executable kernel."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class PredicateResult(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


class KernelError(Exception):
    """Structured kernel failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


MISSING: object = object()


def normalize_identity(parts: Mapping[str, Any] | list[tuple[str, Any]]) -> str:
    """Deterministic identity encoding without OID usage."""
    if isinstance(parts, Mapping):
        items = sorted((str(k), parts[k]) for k in parts)
    else:
        items = [(str(k), v) for k, v in parts]
    encoded: list[str] = []
    for key, value in items:
        if value is None:
            cell = "null"
        elif isinstance(value, bool):
            cell = "true" if value else "false"
        else:
            cell = str(value)
        encoded.append(f"{key}={cell}")
    return "|".join(encoded)


def canonical_scalar(value: Any) -> str:
    if value is MISSING:
        return "<missing>"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (set, frozenset)):
        return "[" + ",".join(sorted(canonical_scalar(v) for v in value)) + "]"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_scalar(v) for v in value) + "]"
    return str(value)


@dataclass(frozen=True)
class PrivilegeResult:
    object_identity: str
    principal: str
    privilege: str
    path: str
    granted: bool
    exercisable: bool
    reason_codes: tuple[str, ...]
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "object_identity": self.object_identity,
            "principal": self.principal,
            "privilege": self.privilege,
            "path": self.path,
            "granted": self.granted,
            "exercisable": self.exercisable,
            "reason_codes": list(self.reason_codes),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ClassificationRecord:
    source_identity: str
    rule_id: str
    order: int
    outcome_slot: str
    failure_state: str | None
    actions: tuple[Mapping[str, Any], ...]
    decisive_fields: Mapping[str, Any]
    predicate_trace: tuple[Mapping[str, Any], ...]
    fallback: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_identity": self.source_identity,
            "rule_id": self.rule_id,
            "order": self.order,
            "outcome_slot": self.outcome_slot,
            "failure_state": self.failure_state,
            "actions": [dict(a) for a in self.actions],
            "decisive_fields": dict(self.decisive_fields),
            "predicate_trace": [dict(p) for p in self.predicate_trace],
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class StateProof:
    valid: bool
    failure_codes: tuple[str, ...]
    sets: Mapping[str, tuple[str, ...]]
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "failure_codes": list(self.failure_codes),
            "sets": {k: list(v) for k, v in self.sets.items()},
            "evidence": dict(self.evidence),
        }
