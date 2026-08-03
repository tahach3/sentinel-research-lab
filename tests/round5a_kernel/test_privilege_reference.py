"""Exhaustive privilege reference tests."""

from __future__ import annotations

from tools.round5a_kernel.privilege_reference import (
    evaluate_privilege,
    resolve_effective_acl,
)


def _schemas(role: str = "research_app", ok: bool = True) -> dict[str, bool]:
    return {role: ok, "postgres": True, "extra_discovered_role": True}


def test_function_null_proacl_public_execute() -> None:
    acl, prov = resolve_effective_acl("FUNCTION", None, "postgres")
    assert prov == "acldefault_f_owner"
    assert any(e["grantee"] == "PUBLIC" and "EXECUTE" in e["privileges"] for e in acl)
    results = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity={"schema": "research", "name": "fn", "args": "int"},
        privilege="EXECUTE",
        principal="research_app",
        owner="postgres",
        raw_acl=None,
        schema_usage=_schemas(),
    )
    top = results[0]
    assert top.granted is True
    assert top.exercisable is True
    assert "KR-PRIV-PUBLIC" in top.reason_codes
    assert top.path == "PUBLIC_DERIVED"


def test_function_explicit_public_revoke() -> None:
    results = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity="research.fn(int)",
        privilege="EXECUTE",
        principal="research_app",
        owner="postgres",
        raw_acl=[{"grantee": "PUBLIC", "privileges": ["EXECUTE"], "revoked": True}],
        schema_usage=_schemas(),
    )
    assert results[0].granted is False
    assert "KR-PRIV-NO-GRANT" in results[0].reason_codes


def test_function_direct_inherited_set_role_owner_superuser() -> None:
    memberships = [
        {"member": "research_app", "granted_role": "research_governance", "set_role_only": False},
        {"member": "research_app", "granted_role": "elevated", "set_role_only": True},
    ]
    direct = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity="research.fn(int)",
        privilege="EXECUTE",
        principal="research_app",
        owner="postgres",
        raw_acl=[{"grantee": "research_app", "privileges": ["EXECUTE"]}],
        memberships=memberships,
        schema_usage=_schemas(),
    )[0]
    assert direct.path == "DIRECT" and "KR-PRIV-DIRECT" in direct.reason_codes

    inherited = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity="research.fn(int)",
        privilege="EXECUTE",
        principal="research_app",
        owner="postgres",
        raw_acl=[{"grantee": "research_governance", "privileges": ["EXECUTE"]}],
        memberships=memberships,
        schema_usage=_schemas(),
    )[0]
    assert inherited.path == "INHERITED" and "KR-PRIV-INHERITED" in inherited.reason_codes

    set_role = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity="research.fn(int)",
        privilege="EXECUTE",
        principal="research_app",
        owner="postgres",
        raw_acl=[{"grantee": "elevated", "privileges": ["EXECUTE"]}],
        memberships=memberships,
        schema_usage=_schemas(),
    )[0]
    assert set_role.path == "SET_ROLE_ONLY" and "KR-PRIV-SET-ROLE" in set_role.reason_codes

    owner = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity="research.fn(int)",
        privilege="EXECUTE",
        principal="postgres",
        owner="postgres",
        raw_acl=[],
        schema_usage=_schemas("postgres"),
    )[0]
    assert "KR-PRIV-OWNER" in owner.reason_codes

    su = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity="research.fn(int)",
        privilege="EXECUTE",
        principal="research_app",
        owner="other",
        raw_acl=[],
        schema_usage=_schemas(ok=False),
        superusers=["research_app"],
    )[0]
    assert "KR-PRIV-SUPERUSER" in su.reason_codes
    assert su.exercisable is True


def test_function_schema_denied_and_empty_acl_and_overloads_and_security() -> None:
    denied = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity="research.fn(int)",
        privilege="EXECUTE",
        principal="research_app",
        owner="postgres",
        raw_acl=None,
        schema_usage={"research_app": False},
    )[0]
    assert denied.granted is True
    assert denied.exercisable is False
    assert "KR-PRIV-SCHEMA-DENIED" in denied.reason_codes

    empty = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity="research.fn(int)",
        privilege="EXECUTE",
        principal="research_app",
        owner="other",
        raw_acl=[],
        schema_usage=_schemas(),
    )[0]
    assert empty.granted is False

    a = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity={"name": "fn", "args": "int"},
        privilege="EXECUTE",
        principal="research_app",
        owner="postgres",
        raw_acl=[{"grantee": "research_app", "privileges": ["EXECUTE"]}],
        schema_usage=_schemas(),
        security_definer=True,
    )[0]
    b = evaluate_privilege(
        object_kind="FUNCTION",
        object_identity={"name": "fn", "args": "text"},
        privilege="EXECUTE",
        principal="research_app",
        owner="postgres",
        raw_acl=[],
        schema_usage=_schemas(),
        security_invoker=True,
    )[0]
    assert a.object_identity != b.object_identity
    assert a.details["security_definer"] is True
    assert b.details["security_invoker"] is True


def test_table_and_sequence_matrix() -> None:
    for kind, privs in (
        ("TABLE", ["SELECT", "INSERT", "UPDATE", "DELETE"]),
        ("SEQUENCE", ["SELECT", "USAGE", "UPDATE"]),
    ):
        null_acl = evaluate_privilege(
            object_kind=kind,
            object_identity=f"research.obj_{kind.lower()}",
            privilege=privs[0],
            principal="postgres",
            owner="postgres",
            raw_acl=None,
            schema_usage=_schemas("postgres"),
        )[0]
        assert null_acl.granted is True
        assert "KR-PRIV-OWNER" in null_acl.reason_codes

        empty = evaluate_privilege(
            object_kind=kind,
            object_identity=f"research.obj_{kind.lower()}",
            privilege=privs[0],
            principal="research_app",
            owner="postgres",
            raw_acl=[],
            schema_usage=_schemas(),
        )[0]
        assert empty.granted is False

        public = evaluate_privilege(
            object_kind=kind,
            object_identity=f"research.obj_{kind.lower()}",
            privilege=privs[0],
            principal="extra_discovered_role",
            owner="postgres",
            raw_acl=[{"grantee": "PUBLIC", "privileges": [privs[0]]}],
            schema_usage=_schemas("extra_discovered_role"),
        )[0]
        assert public.path == "PUBLIC_DERIVED"


def test_column_null_attacl_independence() -> None:
    acl, prov = resolve_effective_acl("COLUMN", None, "postgres")
    assert acl == tuple()
    assert prov == "null_attacl_no_column_specific_acl"

    # table UPDATE, null column ACL → column specific false, table true
    r = evaluate_privilege(
        object_kind="COLUMN",
        object_identity={"table": "t", "column": "c"},
        privilege="UPDATE",
        principal="research_app",
        owner="postgres",
        raw_acl=None,
        schema_usage=_schemas(),
        table_privilege_granted=True,
    )[0]
    assert r.details["column"]["null_attacl"] is True
    assert r.details["column"]["acldefault_c_applied"] is False
    assert r.details["column"]["table_privilege"] is True
    assert r.granted is True
    assert r.exercisable is True
    assert r.path == "TABLE_COMPOSED_TO_COLUMN"
    assert "KR-PRIV-COLUMN-INDEPENDENT" in r.reason_codes
    assert "KR-PRIV-TABLE-COMPOSED" in r.reason_codes

    # column UPDATE without table UPDATE
    col_only = evaluate_privilege(
        object_kind="COLUMN",
        object_identity={"table": "t", "column": "c"},
        privilege="UPDATE",
        principal="research_app",
        owner="postgres",
        raw_acl=[{"grantee": "research_app", "privileges": ["UPDATE"]}],
        schema_usage=_schemas(),
        table_privilege_granted=False,
    )[0]
    assert col_only.details["column"]["column_specific_privilege"] is True
    assert col_only.granted is True
    assert col_only.exercisable is True

    empty = evaluate_privilege(
        object_kind="COLUMN",
        object_identity={"table": "t", "column": "c"},
        privilege="UPDATE",
        principal="research_app",
        owner="postgres",
        raw_acl=[],
        schema_usage=_schemas(),
        table_privilege_granted=True,
    )[0]
    assert empty.details["column"]["empty_attacl"] is True
    assert empty.granted is True
    assert empty.exercisable is True
    assert empty.object_identity  # retained identity even when ACL empty


def test_default_privilege_owner_mismatch() -> None:
    r = evaluate_privilege(
        object_kind="TABLE",
        object_identity="research.t",
        privilege="SELECT",
        principal="research_app",
        owner="actual_owner",
        raw_acl=[{"grantee": "research_app", "privileges": ["SELECT"]}],
        schema_usage=_schemas(),
        default_privilege_owner="migration_creator",
    )[0]
    assert "KR-PRIV-DEFAULT-OWNER-MISMATCH" in r.reason_codes
