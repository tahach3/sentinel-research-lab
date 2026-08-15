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

COMPARE_OPS = {"eq", "ne", "lt", "lte", "gt", "gte"}
ORDERED_OPS = {"lt", "lte", "gt", "gte"}


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


def _types_compatible(left: Any, right: Any) -> bool:
    if type(left) is type(right):
        return True
    # Allow int subclasses only when both are non-bool numbers of same abstract class.
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return True
    return False


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
            if name in self.computed:
                return self.computed[name]
            return MISSING
        raise KernelError("KR-PRED-OPERAND", f"unhandled operand {kind}")

    def _require_null_mode(self, node: Mapping[str, Any]) -> str:
        mode = node.get("null_semantics")
        if mode not in NULL_MODES:
            raise KernelError("KR-PRED-NULL", f"missing or invalid null_semantics on {node.get('node')}")
        return mode

    def _compare(self, op: str, left: Any, right: Any, mode: str) -> PredicateResult:
        if left is MISSING or right is MISSING:
            return PredicateResult.INVALID

        left_null = left is None
        right_null = right is None

        if left_null or right_null:
            if mode == "NULL_IS_UNKNOWN":
                return PredicateResult.UNKNOWN
            if mode == "NULL_FAILS_PREDICATE":
                return PredicateResult.FALSE
            # NULL_IS_VALUE
            if op in ORDERED_OPS:
                return PredicateResult.INVALID
            if op == "eq":
                return PredicateResult.TRUE if (left_null and right_null) else PredicateResult.FALSE
            if op == "ne":
                return PredicateResult.FALSE if (left_null and right_null) else PredicateResult.TRUE
            raise KernelError("KR-PRED-OP", f"unknown compare op {op}")

        if not _types_compatible(left, right):
            return PredicateResult.INVALID

        if op not in COMPARE_OPS:
            raise KernelError("KR-PRED-OP", f"unknown compare op {op}")

        # Evaluate only the selected operator — never build an eager dict.
        try:
            if op == "eq":
                ok = left == right
            elif op == "ne":
                ok = left != right
            elif op == "lt":
                ok = left < right
            elif op == "lte":
                ok = left <= right
            elif op == "gt":
                ok = left > right
            else:  # gte
                ok = left >= right
        except TypeError:
            return PredicateResult.INVALID
        return PredicateResult.TRUE if ok is True else PredicateResult.FALSE

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
            # KR-ND-008: INVALID first — invalid branch cannot be hidden.
            if any(r is PredicateResult.INVALID for r in results):
                return PredicateResult.INVALID
            if any(r is PredicateResult.TRUE for r in results):
                return PredicateResult.TRUE
            if any(r is PredicateResult.UNKNOWN for r in results):
                return PredicateResult.UNKNOWN
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
            # Presence only — no Python truthiness. Missing → FALSE; null → FALSE; any present value → TRUE.
            if value is MISSING:
                return PredicateResult.FALSE
            if value is None:
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
            op = node.get("op")
            if op not in COMPARE_OPS:
                raise KernelError("KR-PRED-OP", f"unknown compare op {op}")
            return self._compare(op, left, right, mode)

        if n in ("in", "not_in"):
            mode = self._require_null_mode(node)
            value = self.eval_operand(node["operand"])
            if value is MISSING:
                return PredicateResult.INVALID
            if value is None:
                if mode == "NULL_IS_UNKNOWN":
                    return PredicateResult.UNKNOWN
                if mode == "NULL_FAILS_PREDICATE":
                    return PredicateResult.FALSE
                # NULL_IS_VALUE: null membership compares as a value
            values = [self.eval_operand(v) for v in node.get("values", [])]
            if any(v is MISSING for v in values):
                return PredicateResult.INVALID
            present = any(value is v or value == v for v in values)
            # Avoid truthiness: explicit membership only.
            ok = present if n == "in" else not present
            return PredicateResult.TRUE if ok else PredicateResult.FALSE

        if n in ("set_equals", "set_contains"):
            mode = self._require_null_mode(node)
            left = self.eval_operand(node["left"])
            right = self.eval_operand(node["right"])
            if left is MISSING or right is MISSING:
                return PredicateResult.INVALID
            if left is None or right is None:
                if mode == "NULL_IS_UNKNOWN":
                    return PredicateResult.UNKNOWN
                if mode == "NULL_FAILS_PREDICATE":
                    return PredicateResult.FALSE
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
