"""Predicate engine tests."""

from __future__ import annotations

import pytest

from tools.round5a_kernel.models import KernelError, PredicateResult
from tools.round5a_kernel.predicate_engine import PredicateEngine


def test_true_false_unknown_invalid_and_missing_vs_null() -> None:
    eng = PredicateEngine({"source_record": {"status": None, "name": "x"}})
    assert (
        eng.evaluate(
            {
                "node": "is_null",
                "operand": {
                    "operand_kind": "field_ref",
                    "field_ref": {
                        "scope": "source_record",
                        "path": ["status"],
                        "data_type": "string",
                        "nullable": True,
                    },
                },
                "null_semantics": "NULL_IS_VALUE",
            }
        )
        is PredicateResult.TRUE
    )
    missing = PredicateEngine({"source_record": {"name": "x"}})
    assert (
        missing.evaluate(
            {
                "node": "missing",
                "target": {
                    "operand_kind": "field_ref",
                    "field_ref": {
                        "scope": "source_record",
                        "path": ["status"],
                        "data_type": "string",
                        "nullable": True,
                    },
                },
                "null_semantics": "NULL_IS_VALUE",
            }
        )
        is PredicateResult.TRUE
    )
    assert (
        missing.evaluate(
            {
                "node": "is_null",
                "operand": {
                    "operand_kind": "field_ref",
                    "field_ref": {
                        "scope": "source_record",
                        "path": ["status"],
                        "data_type": "string",
                        "nullable": True,
                    },
                },
                "null_semantics": "NULL_IS_VALUE",
            }
        )
        is PredicateResult.FALSE
    )


def test_null_modes_and_unknown_node_rejection() -> None:
    eng = PredicateEngine({"source_record": {"status": None}})
    node = {
        "node": "compare",
        "op": "eq",
        "left": {
            "operand_kind": "field_ref",
            "field_ref": {
                "scope": "source_record",
                "path": ["status"],
                "data_type": "string",
                "nullable": True,
            },
        },
        "right": {
            "operand_kind": "typed_literal",
            "typed_literal": {"data_type": "string", "value": "reserved"},
        },
        "null_semantics": "NULL_IS_UNKNOWN",
    }
    assert eng.evaluate(node) is PredicateResult.UNKNOWN
    node["null_semantics"] = "NULL_FAILS_PREDICATE"
    assert eng.evaluate(node) is PredicateResult.FALSE
    with pytest.raises(KernelError):
        eng.evaluate({"node": "eval"})
    with pytest.raises(KernelError):
        eng.evaluate(
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
            }
        )
