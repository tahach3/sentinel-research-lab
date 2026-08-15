"""Bounded-domain case generator (axes only; no classifier/oracle inspection)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.round5a_kernel.models import MISSING, canonical_scalar

COVERAGE_TYPE = "WITNESS_PLUS_AXIS"


def _ck(name: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return name
    return f"{name}:{canonical_scalar(dict(params))}"


# Authored fact→classifier computed bridges (static literals; not predicate inspection).
def _fact_computed() -> dict[str, dict[str, Any]]:
    return {
        "duplicate_idempotency": {
            _ck(
                "PRIMITIVE-DUP-ORDER-WINNER",
                {
                    "group": "pilot_proposal_id,benchmark_case_id,idempotency_key",
                    "winner_mode": "min_legacy_reservation_id_collate_c",
                    "subject_is_non_winner": True,
                },
            ): True,
            "PRIMITIVE-DUP-ORDER-WINNER": True,
        },
        "duplicate_case_attempt": {
            _ck(
                "PRIMITIVE-DUP-ORDER-WINNER",
                {
                    "group": "pilot_proposal_id,benchmark_case_id",
                    "consumption_kind_target": "attempt_consumed",
                    "exclude_rule5_non_winners": True,
                    "winner_mode": "min_legacy_reservation_id_collate_c",
                    "subject_is_non_winner": True,
                },
            ): True,
            "PRIMITIVE-DUP-ORDER-WINNER": True,
        },
        "duplicate_envelope_link": {
            _ck(
                "PRIMITIVE-DUP-ORDER-WINNER",
                {
                    "group": "envelope_id",
                    "winner_mode": "min_source_serialization_collate_c",
                    "subject_is_non_winner": True,
                    "require_different_source": True,
                },
            ): True,
            "PRIMITIVE-DUP-ORDER-WINNER": True,
        },
        "event_natural_key_missing": {
            _ck("PRIMITIVE-EVENT-NATURAL-KEY", {"mode": "required_event_natural_key"}): MISSING,
            "PRIMITIVE-EVENT-NATURAL-KEY": MISSING,
        },
        "ledger_used_as_enforcement": {
            _ck("PRIMITIVE-RECON-SOURCE-DOMAIN", {"flag": "ledger_used_as_enforcement_input"}): True,
            "PRIMITIVE-RECON-SOURCE-DOMAIN": True,
        },
        "ledger_success_mismatch": {
            _ck("PRIMITIVE-RECON-SOURCE-DOMAIN", {"metric": "ledger_success_count"}): 2,
            _ck("PRIMITIVE-EVENT-NATURAL-KEY", {"metric": "success_authority_count"}): 1,
        },
        "token_over_policy": {
            _ck("PRIMITIVE-RECON-SOURCE-DOMAIN", {"metric": "projected_token_sum_events"}): 10,
            _ck("PRIMITIVE-RECON-SOURCE-DOMAIN", {"metric": "policy_max_token_fields"}): 5,
        },
        "cost_conflict": {},
        "negative_or_malformed_counter": {},
        "unacknowledged_discrepancy": {
            _ck("PRIMITIVE-RECON-SOURCE-DOMAIN", {"lookup": "accounting_discrepancies_open"}): True,
            _ck("PRIMITIVE-RECON-SOURCE-DOMAIN", {"lookup": "accounting_discrepancy_acknowledged"}): MISSING,
        },
        "orphaned_ledger": {
            _ck(
                "PRIMITIVE-RECON-LEDGER-ORPHANS",
                {"binding": "no_reservation_or_auth_or_event_match"},
            ): True,
            "PRIMITIVE-RECON-LEDGER-ORPHANS": True,
        },
        "orphaned_envelope": {
            _ck(
                "PRIMITIVE-RECON-ENVELOPE-ORPHANS",
                {"binding": "no_matching_capacity_event_natural_key"},
            ): True,
            "PRIMITIVE-RECON-ENVELOPE-ORPHANS": True,
        },
    }


FACT_CONTEXTS: dict[str, dict[str, Any]] = {
    "ledger_used_as_enforcement": {"shared_data_model": {"ledger_request_count_reporting": 1}},
    "ledger_success_mismatch": {"shared_data_model": {"ledger_success_count": 1}},
    "token_over_policy": {
        "shared_data_model": {"projected_token_sum_events": 10, "policy_max_token_fields": 5}
    },
    "cost_conflict": {
        "shared_data_model": {
            "projected_cost_usd": 1,
            "estimated_cost_usd": 0,
            "ledger_cost_usd": 0,
        }
    },
    "negative_or_malformed_counter": {"shared_data_model": {"counter_value": -1}},
    "unacknowledged_discrepancy": {"shared_data_model": {"discrepancy_fingerprint": "fp"}},
    "orphaned_ledger": {"ledger_orphan": {"ledger_id": "L1"}},
    "orphaned_envelope": {"envelope_orphan": {"envelope_id": "E1"}},
}


def load_bounded_domain(root: Path | None = None) -> dict[str, Any]:
    base = root or Path.cwd()
    path = base / "specs" / "round5a_kernel" / "oracles" / "bounded_domain.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _computed_for_flags(flags: list[str]) -> dict[str, Any]:
    table = _fact_computed()
    out: dict[str, Any] = {}
    for flag in flags:
        out.update(table.get(flag, {}))
    return out


def _contexts_for_flags(flags: list[str], base: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = dict(base or {})
    for flag in flags:
        extra = FACT_CONTEXTS.get(flag)
        if not extra:
            continue
        for scope, payload in extra.items():
            merged = dict(ctx.get(scope) or {})
            merged.update(payload)
            ctx[scope] = merged
    return ctx


def _infer_axis_values(raw: dict[str, Any]) -> dict[str, Any]:
    """Infer declared-axis coverage tags from authored case content."""
    explicit = dict(raw.get("axis_values") or {})
    source = dict(raw.get("source") or {})
    facts = dict(raw.get("oracle_facts") or {})
    out = dict(explicit)

    if "related_row_cardinality" not in out:
        if facts.get("duplicate_case_attempt") or facts.get("duplicate_idempotency") or facts.get(
            "duplicate_envelope_link"
        ):
            out["related_row_cardinality"] = "duplicate"
        elif source.get("pilot_proposal_id") is None and "pilot_proposal_id" in source:
            out["related_row_cardinality"] = "zero"
        elif "pilot_proposal_id" in source:
            out["related_row_cardinality"] = "one"

    if "identity_validity" not in out:
        if raw.get("identity_validity"):
            out["identity_validity"] = raw["identity_validity"]
        elif "legacy_reservation_id" not in source:
            out["identity_validity"] = "missing_component"
        elif str(raw.get("case_id", "")).endswith("collision") or raw.get("normalization_collision"):
            out["identity_validity"] = "normalization_collision_candidate"
        else:
            out["identity_validity"] = "valid"

    if "status" not in out:
        if "status" in source:
            out["status"] = source.get("status")
        else:
            out["status"] = "MISSING"
    if "envelope_id" not in out and "envelope_id" in source:
        out["envelope_id"] = source.get("envelope_id")
    return out


def generate_domain_cases_from_doc(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a bounded-domain document into concrete cases."""
    cases: list[dict[str, Any]] = []
    for raw in list(doc.get("seeded_cases") or []) + list(doc.get("sweep_cases") or []):
        flags = list(raw.get("classifier_computed_flags") or [])
        facts = dict(raw.get("oracle_facts") or {})
        for k, v in facts.items():
            if v and k not in flags:
                flags.append(k)
        axis_values = _infer_axis_values(raw)
        cases.append(
            {
                "case_id": raw["case_id"],
                "source": dict(raw["source"]),
                "oracle_facts": facts,
                "classifier_contexts": _contexts_for_flags(
                    flags, dict(raw.get("classifier_contexts") or {})
                ),
                "classifier_computed": _computed_for_flags(flags),
                "axis_values": axis_values,
                "expected_classifier_rule": raw.get("expected_classifier_rule"),
                "expected_oracle_rule": raw.get("expected_oracle_rule"),
            }
        )
    return cases


def generate_domain_cases(root: Path | None = None) -> list[dict[str, Any]]:
    """Expand bounded_domain.json into concrete cases without inspecting classifiers."""
    return generate_domain_cases_from_doc(load_bounded_domain(root))


def _flatten_declared_axes(axes: dict[str, Any]) -> dict[str, list[Any]]:
    flat: dict[str, list[Any]] = {}
    for name, values in axes.items():
        if name == "boolean_flags" and isinstance(values, dict):
            for flag, flag_values in values.items():
                flat[f"boolean_flags.{flag}"] = list(flag_values)
        else:
            flat[name] = list(values)
    return flat


def coverage_report(
    doc: dict[str, Any] | None = None,
    cases: list[dict[str, Any]] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Report declared vs covered axes/values. Coverage is WITNESS_PLUS_AXIS, not Cartesian."""
    document = doc if doc is not None else load_bounded_domain(root)
    generated = cases if cases is not None else generate_domain_cases_from_doc(document)
    declared = _flatten_declared_axes(dict(document.get("axes") or {}))
    covered: dict[str, set[str]] = {axis: set() for axis in declared}

    for case in generated:
        axis_values = dict(case.get("axis_values") or {})
        source = dict(case.get("source") or {})
        facts = dict(case.get("oracle_facts") or {})

        for axis, value in axis_values.items():
            key = axis if axis in covered else None
            if key is None:
                continue
            covered[key].add(canonical_scalar(value))

        # boolean flag coverage
        for flag, flag_values in (document.get("axes", {}).get("boolean_flags") or {}).items():
            axis_key = f"boolean_flags.{flag}"
            if axis_key not in covered:
                continue
            present = bool(facts.get(flag)) or flag in (case.get("classifier_computed_flags") or [])
            covered[axis_key].add(canonical_scalar(present))
            # ensure false is recorded when flag absent on ordinary cases
            if not present:
                covered[axis_key].add(canonical_scalar(False))

        if "status" in declared and "status" in source:
            covered["status"].add(canonical_scalar(source.get("status")))
        if "envelope_id" in declared and "envelope_id" in source:
            covered["envelope_id"].add(canonical_scalar(source.get("envelope_id")))
        for axis in ("pilot_proposal_id", "authorization_id", "benchmark_case_id"):
            if axis in declared and axis in source:
                covered[axis].add(canonical_scalar(source.get(axis)))

    missing_axes: list[str] = []
    missing_values: list[dict[str, Any]] = []
    covered_axes: list[str] = []
    covered_values: dict[str, list[str]] = {}

    for axis, values in declared.items():
        seen = covered.get(axis, set())
        covered_values[axis] = sorted(seen)
        declared_canon = {canonical_scalar(v) for v in values}
        if not seen:
            missing_axes.append(axis)
        else:
            covered_axes.append(axis)
        for value in values:
            if canonical_scalar(value) not in seen:
                missing_values.append({"axis": axis, "value": value})

    return {
        "coverage_type": COVERAGE_TYPE,
        "declared_axes": sorted(declared.keys()),
        "declared_values": {k: list(v) for k, v in declared.items()},
        "covered_axes": sorted(covered_axes),
        "covered_values": covered_values,
        "missing_axes": sorted(missing_axes),
        "missing_values": missing_values,
        "domain_cases": len(generated),
    }


def domain_limitations(root: Path | None = None) -> list[str]:
    return list(load_bounded_domain(root).get("limitations") or [])
