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


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_privilege_composition_oracle_case(case: dict) -> None:
    inp = case["input"]
    exp = case["expected"]
    if exp.get("error_code"):
        with pytest.raises(KernelError) as ei:
            evaluate_privilege(
                object_kind="COLUMN",
                object_identity={"table": "t", "column": "c"},
                privilege=inp["privilege"],
                principal=inp["principal"],
                owner=inp["owner"],
                raw_acl=inp.get("column_acl"),
                memberships=inp.get("memberships") or [],
                schema_usage=inp.get("schema_usage") or {},
                superusers=inp.get("superusers") or [],
                table_privilege_granted=inp.get("table_privilege_granted"),
                table_privilege_paths=inp.get("table_privilege_paths"),
            )
        assert ei.value.code == exp["error_code"]
        return

    top = evaluate_privilege(
        object_kind="COLUMN",
        object_identity={"table": "t", "column": "c"},
        privilege=inp["privilege"],
        principal=inp["principal"],
        owner=inp["owner"],
        raw_acl=inp.get("column_acl"),
        memberships=inp.get("memberships") or [],
        schema_usage=inp.get("schema_usage") or {},
        superusers=inp.get("superusers") or [],
        table_privilege_granted=inp.get("table_privilege_granted"),
        table_privilege_paths=inp.get("table_privilege_paths"),
    )[0]
    col = top.details["column"]
    assert col["table_privilege_contribution"] is exp["table_contribution"]
    assert col["column_specific_contribution"] is exp["column_contribution"]
    assert top.granted is exp["composed_grant"]
    assert top.exercisable is exp["exercisable"]


def test_original_defect_table_update_reaches_column() -> None:
    r = evaluate_privilege(
        object_kind="COLUMN",
        object_identity={"table": "t", "column": "c"},
        privilege="UPDATE",
        principal="research_app",
        owner="postgres",
        raw_acl=None,
        schema_usage={"research_app": True},
        table_privilege_granted=True,
    )[0]
    assert r.granted is True
    assert r.exercisable is True
    assert r.path == "TABLE_COMPOSED_TO_COLUMN"
    assert "KR-PRIV-TABLE-COMPOSED" in r.reason_codes
