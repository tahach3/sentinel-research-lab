"""Privilege composition oracle tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.round5a_kernel.models import KernelError
from tools.round5a_kernel.privilege_reference import evaluate_privilege

ROOT = Path(__file__).resolve().parents[2]
ORACLE = ROOT / "specs" / "round5a_kernel" / "oracles" / "privilege_composition_cases.json"


def _cases():
    return json.loads(ORACLE.read_text(encoding="utf-8"))["cases"]


def _kwargs(inp: dict) -> dict:
    kwargs = {
        "object_kind": "COLUMN",
        "object_identity": {"table": "t", "column": "c"},
        "privilege": inp["privilege"],
        "principal": inp["principal"],
        "owner": inp["owner"],
        "raw_acl": inp.get("column_acl"),
        "memberships": inp.get("memberships") or [],
        "schema_usage": inp.get("schema_usage") or {},
        "superusers": inp.get("superusers") or [],
    }
    if "table_privilege_granted" in inp:
        kwargs["table_privilege_granted"] = inp.get("table_privilege_granted")
    if "table_raw_acl" in inp:
        kwargs["table_raw_acl"] = inp.get("table_raw_acl")
    return kwargs


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_privilege_composition_oracle_case(case: dict) -> None:
    inp = case["input"]
    exp = case["expected"]
    for banned in (
        "table_privilege_paths",
        "column_privilege_paths",
        "expected_paths",
        "derived_paths",
    ):
        assert banned not in inp or inp.get(banned) is None
    if exp.get("error_code"):
        with pytest.raises(KernelError) as ei:
            evaluate_privilege(**_kwargs(inp))
        assert ei.value.code == exp["error_code"]
        return

    top = evaluate_privilege(**_kwargs(inp))[0]
    col = top.details["column"]
    assert col["table_privilege_contribution"] is exp["table_privilege_contribution"]
    assert col["column_specific_contribution"] is exp["column_specific_contribution"]
    assert top.granted is exp["composed_column_granted"]
    assert top.exercisable is exp["exercisable"]
    assert col["schema_usage"] is exp["schema_usage"]
    assert list(col["table_paths"]) == list(exp["table_paths"])
    assert list(col["column_paths"]) == list(exp["column_paths"])
    assert list(col["contributing_paths"]) == list(exp["contributing_paths"])
    for code in exp.get("reason_codes") or []:
        assert code in top.reason_codes


def test_original_defect_table_update_reaches_column() -> None:
    r = evaluate_privilege(
        object_kind="COLUMN",
        object_identity={"table": "t", "column": "c"},
        privilege="UPDATE",
        principal="research_app",
        owner="postgres",
        raw_acl=None,
        schema_usage={"research_app": True},
        table_raw_acl=[{"grantee": "research_app", "privileges": ["UPDATE"]}],
    )[0]
    assert r.granted is True
    assert r.exercisable is True
    assert r.path == "TABLE_COMPOSED_TO_COLUMN"
    assert r.details["column"]["table_paths"] == ["DIRECT"]
    assert r.details["column"]["column_paths"] == []
    assert "KR-PRIV-TABLE-COMPOSED" in r.reason_codes
