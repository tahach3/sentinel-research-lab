"""Deterministic predicate interpreter for Round 5A reconciliation kernel."""

from __future__ import annotations

from typing import Any, Mapping

from tools.round5a_kernel.models import MISSING, KernelError, PredicateResult, canonical_scalar

ALLOWED_NODES = {
    "all",
    "any",
    "not",
    "compare",
    "is_null",
    "is_not_null",
    "in",
    "not_in",
    "set_equals",
    "set_contains",
    "exists",
    "missing",
}

ALLOWED_OPERANDS = {
    "field_ref",
    "typed_literal",
    "normalized_identity_ref",
    "computed_value_ref",
}

NULL_MODES = {"NULL_IS_VALUE", "NULL_IS_UNKNOWN", "NULL_FAILS_PREDICATE"}


def resolve_field(contexts: Mapping[str, Any], scope: str, path: list[str]) -> Any:
    record = contexts.get(scope, MISSING)
    if record is MISSING or record is None:
        return MISSING
    cur: Any = record
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return MISSING
        cur = cur[part]
    return cur


class PredicateEngine:
    """Interpret only approved predicate nodes with explicit null modes."""

    def __init__(
        self,
        contexts: Mapping[str, Any],
        computed: Mapping[str, Any] | None = None,
    ) -> None:
        self.contexts = dict(contexts)
        self.computed = dict(computed or {})

    def eval_operand(self, operand: Mapping[str, Any]) -> Any:
        kind = operand.get("operand_kind")
        if kind not in ALLOWED_OPERANDS:
            raise KernelError("KR-PRED-OPERAND", f"unsupported operand_kind {kind}")
        if kind == "typed_literal":
            lit = operand["typed_literal"]
            return lit["value"]
        if kind == "field_ref":
            fr = operand["field_ref"]
            return resolve_field(self.contexts, fr["scope"], list(fr["path"]))
        if kind == "normalized_identity_ref":
            ref = operand["normalized_identity_ref"]
            return ref.get("value")
        if kind == "computed_value_ref":
            cref = operand["computed_value_ref"]
            name = cref["name"]
            params = cref.get("parameters") or {}
            key = name if not params else f"{name}:{canonical_scalar(params)}"
            if key in self.computed:
                return self.computed[key]
            # allow direct name lookup
            if name in self.computed:
                return self.computed[name]
            return MISSING
        raise KernelError("KR-PRED-OPERAND", f"unhandled operand {kind}")

    def _require_null_mode(self, node: Mapping[str, Any]) -> str:
        mode = node.get("null_semantics")
        if mode not in NULL_MODES:
            raise KernelError("KR-PRED-NULL", f"missing or invalid null_semantics on {node.get('node')}")
        return mode

    def _apply_null_mode(self, mode: str, *values: Any) -> PredicateResult | None:
        if any(v is MISSING for v in values):
            return PredicateResult.INVALID
        if any(v is None for v in values):
            if mode == "NULL_IS_VALUE":
                return None
            if mode == "NULL_IS_UNKNOWN":
                return PredicateResult.UNKNOWN
            if mode == "NULL_FAILS_PREDICATE":
                return PredicateResult.FALSE
        return None

    def _normalize_set(self, value: Any) -> set[str] | PredicateResult:
        if value is MISSING:
            return PredicateResult.INVALID
        if value is None:
            return PredicateResult.UNKNOWN
        if isinstance(value, (set, frozenset, list, tuple)):
            return {canonical_scalar(v) for v in value}
        raise KernelError("KR-PRED-SET", "set operand must be a collection")

    def evaluate(self, node: Mapping[str, Any]) -> PredicateResult:
        if "node" not in node:
            raise KernelError("KR-PRED-NODE", "predicate node missing")
        n = node["node"]
        if n not in ALLOWED_NODES:
            raise KernelError("KR-PRED-NODE", f"unknown node {n}")

        if n == "all":
            results = [self.evaluate(p) for p in node.get("predicates", [])]
            if any(r is PredicateResult.INVALID for r in results):
                return PredicateResult.INVALID
            if any(r is PredicateResult.FALSE for r in results):
                return PredicateResult.FALSE
            if any(r is PredicateResult.UNKNOWN for r in results):
                return PredicateResult.UNKNOWN
            return PredicateResult.TRUE

        if n == "any":
            results = [self.evaluate(p) for p in node.get("predicates", [])]
            if any(r is PredicateResult.TRUE for r in results):
                return PredicateResult.TRUE
            if any(r is PredicateResult.INVALID for r in results) and not any(
                r is PredicateResult.FALSE for r in results
            ):
                # all INVALID/UNKNOWN without FALSE/TRUE
                if all(r is PredicateResult.INVALID for r in results):
                    return PredicateResult.INVALID
            if any(r is PredicateResult.UNKNOWN for r in results):
                return PredicateResult.UNKNOWN
            if any(r is PredicateResult.INVALID for r in results):
                return PredicateResult.INVALID
            return PredicateResult.FALSE

        if n == "not":
            inner = self.evaluate(node["predicate"])
            if inner is PredicateResult.TRUE:
                return PredicateResult.FALSE
            if inner is PredicateResult.FALSE:
                return PredicateResult.TRUE
            return inner

        if n == "is_null":
            self._require_null_mode(node)
            value = self.eval_operand(node["operand"])
            if value is MISSING:
                return PredicateResult.FALSE
            return PredicateResult.TRUE if value is None else PredicateResult.FALSE

        if n == "is_not_null":
            self._require_null_mode(node)
            value = self.eval_operand(node["operand"])
            if value is MISSING:
                return PredicateResult.FALSE
            return PredicateResult.TRUE if value is not None else PredicateResult.FALSE

        if n == "exists":
            self._require_null_mode(node)
            value = self.eval_operand(node["target"])
            if value is MISSING:
                return PredicateResult.FALSE
            if value is None or value is False:
                return PredicateResult.FALSE
            return PredicateResult.TRUE

        if n == "missing":
            self._require_null_mode(node)
            value = self.eval_operand(node["target"])
            return PredicateResult.TRUE if value is MISSING else PredicateResult.FALSE

        if n == "compare":
            mode = self._require_null_mode(node)
            left = self.eval_operand(node["left"])
            right = self.eval_operand(node["right"])
            early = self._apply_null_mode(mode, left, right)
            if early is not None:
                return early
            op = node["op"]
            try:
                ok = {
                    "eq": left == right,
                    "ne": left != right,
                    "lt": left < right,
                    "lte": left <= right,
                    "gt": left > right,
                    "gte": left >= right,
                }[op]
            except TypeError as exc:
                raise KernelError("KR-PRED-TYPE", f"incompatible compare types: {exc}") from exc
            return PredicateResult.TRUE if ok else PredicateResult.FALSE

        if n in ("in", "not_in"):
            mode = self._require_null_mode(node)
            value = self.eval_operand(node["operand"])
            early = self._apply_null_mode(mode, value)
            if early is not None:
                return early
            values = [self.eval_operand(v) for v in node.get("values", [])]
            if any(v is MISSING for v in values):
                return PredicateResult.INVALID
            present = value in values
            ok = present if n == "in" else not present
            return PredicateResult.TRUE if ok else PredicateResult.FALSE

        if n in ("set_equals", "set_contains"):
            mode = self._require_null_mode(node)
            left = self.eval_operand(node["left"])
            right = self.eval_operand(node["right"])
            early = self._apply_null_mode(mode, left, right)
            if early is not None:
                return early
            left_set = self._normalize_set(left)
            right_set = self._normalize_set(right)
            if isinstance(left_set, PredicateResult):
                return left_set
            if isinstance(right_set, PredicateResult):
                return right_set
            if n == "set_equals":
                ok = left_set == right_set
            else:
                ok = right_set.issubset(left_set)
            return PredicateResult.TRUE if ok else PredicateResult.FALSE

        raise KernelError("KR-PRED-NODE", f"unhandled node {n}")
