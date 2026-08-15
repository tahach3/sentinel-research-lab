"""Null-semantics oracle tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.round5a_kernel.models import KernelError, PredicateResult
from tools.round5a_kernel.predicate_engine import PredicateEngine

ROOT = Path(__file__).resolve().parents[2]
ORACLE = ROOT / "specs" / "round5a_kernel" / "oracles" / "null_semantics_cases.json"


def _cases():
    return json.loads(ORACLE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_null_semantics_oracle_case(case: dict) -> None:
    eng = PredicateEngine(case.get("contexts") or {})
    expected = case["expected"]
    if expected == "ERROR":
        with pytest.raises(KernelError) as ei:
            eng.evaluate(case["node"])
        if case.get("error_code"):
            assert ei.value.code == case["error_code"]
        return
    result = eng.evaluate(case["node"])
    assert result is PredicateResult[expected]


def test_null_is_value_equality_not_eager() -> None:
    eng = PredicateEngine({"source_record": {"a": None, "b": None}})
    assert (
        eng.evaluate(
            {
                "node": "compare",
                "op": "eq",
                "left": {
                    "operand_kind": "field_ref",
                    "field_ref": {
                        "scope": "source_record",
                        "path": ["a"],
                        "data_type": "string",
                        "nullable": True,
                    },
                },
                "right": {
                    "operand_kind": "field_ref",
                    "field_ref": {
                        "scope": "source_record",
                        "path": ["b"],
                        "data_type": "string",
                        "nullable": True,
                    },
                },
                "null_semantics": "NULL_IS_VALUE",
            }
        )
        is PredicateResult.TRUE
    )


def test_any_invalid_not_hidden_by_true() -> None:
    eng = PredicateEngine({"source_record": {"a": None}})
    # INVALID branch + TRUE branch → INVALID (KR-ND-008)
    node = {
        "node": "any",
        "predicates": [
            {
                "node": "compare",
                "op": "eq",
                "left": {
                    "operand_kind": "field_ref",
                    "field_ref": {
                        "scope": "source_record",
                        "path": ["missing"],
                        "data_type": "string",
                        "nullable": True,
                    },
                },
                "right": {
                    "operand_kind": "typed_literal",
                    "typed_literal": {"data_type": "string", "value": "x"},
                },
                "null_semantics": "NULL_IS_VALUE",
            },
            {
                "node": "compare",
                "op": "eq",
                "left": {
                    "operand_kind": "typed_literal",
                    "typed_literal": {"data_type": "string", "value": "a"},
                },
                "right": {
                    "operand_kind": "typed_literal",
                    "typed_literal": {"data_type": "string", "value": "a"},
                },
                "null_semantics": "NULL_IS_VALUE",
            },
        ],
    }
    assert eng.evaluate(node) is PredicateResult.INVALID
