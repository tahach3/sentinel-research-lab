"""First-match reconciliation classification reference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.round5a_kernel.models import ClassificationRecord, KernelError, PredicateResult, normalize_identity
from tools.round5a_kernel.predicate_engine import PredicateEngine


def load_reconciliation_contract(root: Path | None = None) -> dict[str, Any]:
    base = root or Path.cwd()
    path = base / "specs" / "round5a_kernel" / "reconciliation_contract.json"
    return json.loads(path.read_text(encoding="utf-8"))


def collect_computed_refs(rules: Sequence[Mapping[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    refs: list[tuple[str, dict[str, Any]]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("operand_kind") == "computed_value_ref":
                cref = obj["computed_value_ref"]
                refs.append((str(cref["name"]), dict(cref.get("parameters") or {})))
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    for rule in rules:
        walk(rule.get("predicate"))
    return refs


def computed_key(name: str, params: Mapping[str, Any] | None = None) -> str:
    from tools.round5a_kernel.models import canonical_scalar

    if not params:
        return name
    return f"{name}:{canonical_scalar(dict(params))}"


def default_computed_values(rules: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Defaults keep happy-path sources from matching conflict/missing rules."""
    from tools.round5a_kernel.models import MISSING

    values: dict[str, Any] = {}
    for name, params in collect_computed_refs(rules):
        key = computed_key(name, params)
        if params.get("subject_is_non_winner"):
            values[key] = MISSING
            values[name] = MISSING
        elif "lookup" in params and params.get("lookup") in {
            "pilot_proposal_id",
            "authorization_id",
            "benchmark_case_id",
        }:
            values[key] = {"found": True}
            values[name] = {"found": True}
        elif params.get("lookup") == "accounting_discrepancies_open":
            values[key] = MISSING
            values[name] = MISSING
        elif params.get("lookup") == "accounting_discrepancy_acknowledged":
            values[key] = {"ack": True}
            values[name] = {"ack": True}
        elif params.get("mode") == "required_event_natural_key":
            values[key] = {"event_key": "present"}
            values[name] = {"event_key": "present"}
        elif params.get("mode") in {"event_field_tuple", "source_field_tuple"}:
            values[key] = ["aligned"]
            values[name] = ["aligned"]
        elif "binding" in params:
            values[key] = MISSING
            values[name] = MISSING
        elif "flag" in params or "metric" in params:
            values[key] = False if "flag" in params else 0
            values[name] = values[key]
        else:
            values[key] = {"present": True}
            values.setdefault(name, {"present": True})
    return values


def source_identity_of(source: Mapping[str, Any], rule: Mapping[str, Any]) -> str:
    identity = rule["source_identity"]
    parts: list[tuple[str, Any]] = []
    for field in identity["identity_fields"]:
        path = list(field["path"])
        cur: Any = source
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                cur = None
                break
            cur = cur[p]
        parts.append((path[-1], cur))
    return normalize_identity(parts)


def outcome_slot_of(source: Mapping[str, Any], rule: Mapping[str, Any]) -> str:
    ctor = rule["outcome_constructor"]
    slot_type = ctor.get("slot_type", rule["name"])
    identity = ctor.get("slot_identity") or {}
    parts: list[tuple[str, Any]] = [("slot_type", slot_type)]
    for field in identity.get("identity_fields", []):
        name = field["path"][-1]
        if name == "slot_name":
            parts.append((name, slot_type))
        elif name in source:
            parts.append((name, source.get(name)))
        else:
            parts.append((name, source.get("legacy_reservation_id")))
    return normalize_identity(parts)


def classify_source(
    source: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
    *,
    contexts: Mapping[str, Any] | None = None,
    computed: Mapping[str, Any] | None = None,
) -> ClassificationRecord:
    """Evaluate rules in order; first TRUE wins. UNKNOWN/INVALID never match."""
    ordered = sorted(rules, key=lambda r: int(r["order"]))
    ctx = {"source_record": dict(source)}
    if contexts:
        ctx.update(contexts)
    merged_computed = default_computed_values(ordered)
    if computed:
        merged_computed.update(computed)
    engine = PredicateEngine(ctx, computed=merged_computed)
    trace: list[dict[str, Any]] = []

    for rule in ordered:
        result = engine.evaluate(rule["predicate"])
        trace.append({"rule_id": rule["rule_id"], "result": result.value})
        if result is not PredicateResult.TRUE:
            continue
        sid = source_identity_of(source, rule)
        slot = outcome_slot_of(source, rule)
        actions = tuple(dict(a) for a in rule.get("actions", []))
        decisive = {}
        for df in rule.get("decisive_fields", []):
            path = list(df["path"])
            scope = df["scope"]
            record = ctx.get(scope, {})
            cur: Any = record if isinstance(record, dict) else {}
            for p in path:
                if not isinstance(cur, dict) or p not in cur:
                    cur = None
                    break
                cur = cur[p]
            decisive[".".join(path)] = cur
        return ClassificationRecord(
            source_identity=sid,
            rule_id=rule["rule_id"],
            order=int(rule["order"]),
            outcome_slot=slot,
            failure_state=rule.get("failure_state"),
            actions=actions,
            decisive_fields=decisive,
            predicate_trace=tuple(trace),
            fallback=bool(rule.get("fallback", False)),
        )

    raise KernelError("KR-CLASS-UNMATCHED", "no rule matched including fallback")


def classify_many(
    sources: Sequence[Mapping[str, Any]],
    rules: Sequence[Mapping[str, Any]],
    *,
    context_builder=None,
) -> list[ClassificationRecord]:
    out: list[ClassificationRecord] = []
    for source in sources:
        contexts = context_builder(source) if context_builder else None
        out.append(classify_source(source, rules, contexts=contexts))
    return out
