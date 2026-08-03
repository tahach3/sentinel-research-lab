"""Bounded-domain case generator (axes only; no classifier/oracle inspection)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.round5a_kernel.models import MISSING, canonical_scalar


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


def generate_domain_cases(root: Path | None = None) -> list[dict[str, Any]]:
    """Expand bounded_domain.json into concrete cases without inspecting classifiers."""
    doc = load_bounded_domain(root)
    cases: list[dict[str, Any]] = []
    for raw in list(doc.get("seeded_cases") or []) + list(doc.get("sweep_cases") or []):
        flags = list(raw.get("classifier_computed_flags") or [])
        facts = dict(raw.get("oracle_facts") or {})
        for k, v in facts.items():
            if v and k not in flags:
                flags.append(k)
        cases.append(
            {
                "case_id": raw["case_id"],
                "source": dict(raw["source"]),
                "oracle_facts": facts,
                "classifier_contexts": _contexts_for_flags(
                    flags, dict(raw.get("classifier_contexts") or {})
                ),
                "classifier_computed": _computed_for_flags(flags),
            }
        )
    return cases


def domain_limitations(root: Path | None = None) -> list[str]:
    return list(load_bounded_domain(root).get("limitations") or [])
