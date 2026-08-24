"""Round 5A executable privilege reference model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from tools.round5a_kernel.models import KernelError, PrivilegeResult, normalize_identity

PUBLIC = "PUBLIC"

COLUMN_SUPPORTED_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "REFERENCES"})
TABLE_ONLY_PRIVILEGES = frozenset({"DELETE", "TRUNCATE", "TRIGGER"})

# Caller-supplied path labels are never authoritative input.
REJECTED_PATH_INPUTS = frozenset(
    {
        "table_privilege_paths",
        "column_privilege_paths",
        "expected_paths",
        "derived_paths",
    }
)

ACLDEFAULT: dict[str, list[dict[str, Any]]] = {
    "f": [
        {"grantee": PUBLIC, "privileges": ["EXECUTE"], "grant_option": False},
        {"grantee": "OWNER", "privileges": ["EXECUTE"], "grant_option": True},
    ],
    "r": [
        {
            "grantee": "OWNER",
            "privileges": [
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "TRUNCATE",
                "REFERENCES",
                "TRIGGER",
            ],
            "grant_option": True,
        }
    ],
    "s": [
        {
            "grantee": "OWNER",
            "privileges": ["SELECT", "UPDATE", "USAGE"],
            "grant_option": True,
        }
    ],
    "n": [
        {
            "grantee": "OWNER",
            "privileges": ["USAGE", "CREATE"],
            "grant_option": True,
        }
    ],
}

KIND_DEFAULT_KEY = {
    "FUNCTION": "f",
    "TABLE": "r",
    "SEQUENCE": "s",
    "SCHEMA": "n",
}

GRANT_PATH_ORDER = (
    "DIRECT",
    "PUBLIC_DERIVED",
    "INHERITED",
    "SET_ROLE_ONLY",
    "OWNER_DERIVED",
    "SUPERUSER_DERIVED",
)


def _reject_fabricated_path_inputs(**candidates: Any) -> None:
    for name, value in candidates.items():
        if name not in REJECTED_PATH_INPUTS:
            continue
        if value is not None:
            raise KernelError(
                "KR-PRIV-PATH-FABRICATED",
                f"reject authoritative path input {name}",
            )


def _frozen_acl(entries: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, Any], ...] | None:
    if entries is None:
        return None
    out: list[dict[str, Any]] = []
    for e in entries:
        out.append(
            {
                "grantee": str(e["grantee"]),
                "privileges": tuple(str(p) for p in e.get("privileges", ())),
                "grant_option": bool(e.get("grant_option", False)),
                "revoked": bool(e.get("revoked", False)),
            }
        )
    return tuple(out)


def resolve_effective_acl(
    object_kind: str,
    raw_acl: Sequence[Mapping[str, Any]] | None,
    owner: str,
) -> tuple[tuple[dict[str, Any], ...], str]:
    """Apply COALESCE semantics; columns never use acldefault('c')."""
    kind = object_kind.upper()
    if kind == "COLUMN":
        if raw_acl is None:
            return tuple(), "null_attacl_no_column_specific_acl"
        return _frozen_acl(raw_acl) or tuple(), "explicit_column_acl"

    if raw_acl is None:
        key = KIND_DEFAULT_KEY[kind]
        defaults = deepcopy(ACLDEFAULT[key])
        for entry in defaults:
            if entry["grantee"] == "OWNER":
                entry["grantee"] = owner
        return _frozen_acl(defaults) or tuple(), f"acldefault_{key}_owner"
    return _frozen_acl(raw_acl) or tuple(), "explicit_acl"


def _inherit_roles(start: str, memberships: Sequence[Mapping[str, Any]]) -> set[str]:
    edges: dict[str, set[str]] = {}
    for m in memberships:
        if bool(m.get("set_role_only", False)):
            continue
        edges.setdefault(str(m["member"]), set()).add(str(m["granted_role"]))
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in edges.get(cur, ()):
            if nxt not in seen:
                stack.append(nxt)
    return seen


def _set_role_roles(start: str, memberships: Sequence[Mapping[str, Any]]) -> set[str]:
    edges: dict[str, set[str]] = {}
    for m in memberships:
        if not bool(m.get("set_role_only", False)):
            continue
        edges.setdefault(str(m["member"]), set()).add(str(m["granted_role"]))
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in edges.get(cur, ()):
            if nxt not in seen:
                stack.append(nxt)
    return seen - {start}


def _acl_grants(
    effective_acl: Sequence[Mapping[str, Any]],
    privilege: str,
) -> dict[str, bool]:
    """Return grantee -> grant_option for privilege, honoring revoke entries."""
    grants: dict[str, bool] = {}
    for entry in effective_acl:
        privs = set(entry.get("privileges", ()))
        if privilege not in privs:
            continue
        grantee = str(entry["grantee"])
        if bool(entry.get("revoked", False)):
            grants.pop(grantee, None)
            continue
        grants[grantee] = bool(entry.get("grant_option", False))
    return grants


def _normalize_paths(paths: Sequence[str]) -> list[str]:
    """Deterministic unique grant-path order without inventing labels."""
    present = {p for p in paths if p in GRANT_PATH_ORDER}
    return [p for p in GRANT_PATH_ORDER if p in present]


def _evaluate_grant_paths(
    *,
    privilege: str,
    principal: str,
    owner: str,
    effective_acl: Sequence[Mapping[str, Any]],
    memberships: Sequence[Mapping[str, Any]],
    superuser_set: set[str],
) -> tuple[bool, str, list[str], list[str]]:
    """Evaluate ACL/owner/superuser grant paths without schema gating.

    Returns (granted, primary_path, reason_codes, contributing_paths).
    """
    grants = _acl_grants(effective_acl, privilege)
    inherit = _inherit_roles(principal, memberships)
    set_role = _set_role_roles(principal, memberships)

    reasons: list[str] = []
    paths: list[str] = []
    granted = False
    path = "DIRECT"

    if principal in grants:
        granted = True
        path = "DIRECT"
        reasons.append("KR-PRIV-DIRECT")
        paths.append("DIRECT")
    elif PUBLIC in grants:
        granted = True
        path = "PUBLIC_DERIVED"
        reasons.append("KR-PRIV-PUBLIC")
        paths.append("PUBLIC_DERIVED")
    else:
        inherited_hit = sorted(r for r in inherit if r != principal and r in grants)
        if inherited_hit:
            granted = True
            path = "INHERITED"
            reasons.append("KR-PRIV-INHERITED")
            paths.append("INHERITED")
        else:
            set_hit = sorted(r for r in set_role if r in grants)
            if set_hit:
                granted = True
                path = "SET_ROLE_ONLY"
                reasons.append("KR-PRIV-SET-ROLE")
                paths.append("SET_ROLE_ONLY")

    owner_derived = principal == owner
    if owner_derived:
        if not granted:
            granted = True
            path = "OWNER_DERIVED"
        reasons.append("KR-PRIV-OWNER")
        if "OWNER_DERIVED" not in paths:
            paths.append("OWNER_DERIVED")

    superuser_derived = principal in superuser_set
    if superuser_derived:
        if not granted:
            granted = True
            path = "SUPERUSER_DERIVED"
        reasons.append("KR-PRIV-SUPERUSER")
        if "SUPERUSER_DERIVED" not in paths:
            paths.append("SUPERUSER_DERIVED")

    if not granted:
        reasons.append("KR-PRIV-NO-GRANT")

    return granted, path, reasons, _normalize_paths(paths)


def evaluate_privilege(
    *,
    object_kind: str,
    object_identity: Mapping[str, Any] | str,
    privilege: str,
    principal: str,
    owner: str,
    raw_acl: Sequence[Mapping[str, Any]] | None,
    memberships: Sequence[Mapping[str, Any]] | None = None,
    schema_usage: Mapping[str, bool] | None = None,
    superusers: Iterable[str] | None = None,
    default_privilege_owner: str | None = None,
    table_privilege_granted: bool | None = None,
    table_privilege_paths: Sequence[str] | None = None,
    column_privilege_paths: Sequence[str] | None = None,
    expected_paths: Sequence[str] | None = None,
    derived_paths: Sequence[str] | None = None,
    table_raw_acl: Sequence[Mapping[str, Any]] | None = None,
    table_owner: str | None = None,
    security_definer: bool | None = None,
    security_invoker: bool | None = None,
) -> list[PrivilegeResult]:
    """Evaluate privilege paths for one principal against one object.

    Path provenance is derived only from raw privilege facts. Caller-provided
    path labels are rejected.
    """
    _reject_fabricated_path_inputs(
        table_privilege_paths=table_privilege_paths,
        column_privilege_paths=column_privilege_paths,
        expected_paths=expected_paths,
        derived_paths=derived_paths,
    )

    memberships = list(memberships or ())
    schema_usage = dict(schema_usage or {})
    superuser_set = set(superusers or ())
    kind = object_kind.upper()
    if kind not in {"SCHEMA", "FUNCTION", "TABLE", "COLUMN", "SEQUENCE"}:
        raise KernelError("KR-PRIV-KIND", f"unsupported object kind {object_kind}")

    if principal == PUBLIC:
        raise KernelError("KR-PRIV-PUBLIC-PRINCIPAL", "PUBLIC is not an evaluable session principal")

    if isinstance(object_identity, str):
        oid = object_identity
        identity_map = {"name": object_identity}
    else:
        identity_map = dict(object_identity)
        oid = normalize_identity(identity_map)

    if kind == "COLUMN" and privilege.upper() in TABLE_ONLY_PRIVILEGES:
        raise KernelError(
            "KR-PRIV-COLUMN-UNSUPPORTED",
            f"{privilege} is table-level only and cannot be evaluated as a column privilege",
        )

    effective_acl, acl_provenance = resolve_effective_acl(kind, raw_acl, owner)
    results: list[PrivilegeResult] = []

    if kind != "COLUMN":
        granted, path, reasons, contributing = _evaluate_grant_paths(
            privilege=privilege,
            principal=principal,
            owner=owner,
            effective_acl=effective_acl,
            memberships=memberships,
            superuser_set=superuser_set,
        )
        if default_privilege_owner is not None and default_privilege_owner != owner:
            reasons.append("KR-PRIV-DEFAULT-OWNER-MISMATCH")

        schema_ok = True
        result_path = path if granted else "DIRECT"
        if kind != "SCHEMA":
            schema_ok = bool(schema_usage.get(principal, False)) or principal in superuser_set
            if granted and not schema_ok:
                reasons.append("KR-PRIV-SCHEMA-DENIED")
                result_path = "SCHEMA_GATED"

        exercisable = bool(granted and schema_ok)
        if exercisable:
            results.append(
                PrivilegeResult(
                    object_identity=oid,
                    principal=principal,
                    privilege=privilege,
                    path="EXERCISABLE",
                    granted=True,
                    exercisable=True,
                    reason_codes=tuple(dict.fromkeys(reasons)),
                    details={
                        "acl_provenance": acl_provenance,
                        "effective_path": result_path,
                        "contributing_paths": list(contributing),
                        "table_paths": list(contributing),
                        "column_paths": [],
                        "security_definer": security_definer,
                        "security_invoker": security_invoker,
                        "column": None,
                    },
                )
            )

        path_result = PrivilegeResult(
            object_identity=oid,
            principal=principal,
            privilege=privilege,
            path=result_path,
            granted=granted,
            exercisable=exercisable,
            reason_codes=tuple(dict.fromkeys(reasons)),
            details={
                "acl_provenance": acl_provenance,
                "effective_acl": [dict(e) for e in effective_acl],
                "security_definer": security_definer,
                "security_invoker": security_invoker,
                "column": None,
                "schema_usage": schema_ok,
                "contributing_paths": list(contributing),
                "table_paths": list(contributing),
                "column_paths": [],
            },
        )
        results.insert(0, path_result)
        return results

    # --- COLUMN composition (KR-ND-007) ---
    reasons: list[str] = ["KR-PRIV-COLUMN-INDEPENDENT"]
    col_granted, col_path, col_reasons, col_paths = _evaluate_grant_paths(
        privilege=privilege,
        principal=principal,
        owner=owner,
        effective_acl=effective_acl,
        memberships=memberships,
        superuser_set=superuser_set,
    )
    column_specific_granted = col_granted
    column_paths = list(col_paths)

    # Table contribution derived only from raw table ACL / ownership / memberships.
    table_paths: list[str] = []
    table_granted = False
    evaluate_table = table_raw_acl is not None or table_privilege_granted is True
    if table_privilege_granted is False:
        evaluate_table = False
    if evaluate_table:
        t_owner = table_owner if table_owner is not None else owner
        t_acl, _ = resolve_effective_acl("TABLE", table_raw_acl, t_owner)
        t_granted, _t_path, _t_reasons, t_paths = _evaluate_grant_paths(
            privilege=privilege,
            principal=principal,
            owner=t_owner,
            effective_acl=t_acl,
            memberships=memberships,
            superuser_set=superuser_set,
        )
        table_granted = t_granted
        table_paths = list(t_paths) if t_granted else []

    null_attacl = raw_acl is None
    empty_attacl = raw_acl is not None and len(tuple(raw_acl)) == 0

    composed_granted = bool(table_granted or column_specific_granted)
    if not composed_granted:
        reasons.append("KR-PRIV-NO-GRANT")
    else:
        col_reasons = [r for r in col_reasons if r != "KR-PRIV-NO-GRANT"]

    # Keep origins separate; contributing_paths is ordered union (not a silent merge of labels).
    contributing_paths: list[str] = []
    for p in table_paths:
        if p not in contributing_paths:
            contributing_paths.append(p)
    for p in column_paths:
        if p not in contributing_paths:
            contributing_paths.append(p)
    contributing_paths = _normalize_paths(contributing_paths)

    primary_path = col_path if column_specific_granted else "DIRECT"
    if table_granted and not column_specific_granted:
        primary_path = "TABLE_COMPOSED_TO_COLUMN"
        reasons.append("KR-PRIV-TABLE-COMPOSED")
    elif table_granted and column_specific_granted:
        reasons.append("KR-PRIV-TABLE-COMPOSED")
        primary_path = col_path
    reasons.extend(col_reasons)

    if default_privilege_owner is not None and default_privilege_owner != owner:
        reasons.append("KR-PRIV-DEFAULT-OWNER-MISMATCH")

    # Schema gating applies after grant provenance; does not erase underlying paths.
    schema_ok = bool(schema_usage.get(principal, False)) or principal in superuser_set
    result_path = primary_path if composed_granted else "DIRECT"
    if composed_granted and not schema_ok:
        reasons.append("KR-PRIV-SCHEMA-DENIED")
        result_path = "SCHEMA_GATED"

    exercisable = bool(composed_granted and schema_ok)

    composition = {
        "table_privilege_contribution": table_granted,
        "column_specific_contribution": column_specific_granted,
        "schema_usage_contribution": schema_ok,
        "composed_column_granted": composed_granted,
        "composed_column_exercisable": exercisable,
        "contributing_paths": list(contributing_paths),
        "table_granted": table_granted,
        "column_specific_granted": column_specific_granted,
        "composed_granted": composed_granted,
        "schema_usage": schema_ok,
        "exercisable": exercisable,
        "table_paths": list(table_paths),
        "column_paths": list(column_paths),
        "null_attacl": null_attacl,
        "empty_attacl": empty_attacl,
        "acldefault_c_applied": False,
        "table_privilege": table_granted,
        "column_specific_privilege": column_specific_granted,
    }

    if exercisable:
        results.append(
            PrivilegeResult(
                object_identity=oid,
                principal=principal,
                privilege=privilege,
                path="EXERCISABLE",
                granted=True,
                exercisable=True,
                reason_codes=tuple(dict.fromkeys(reasons)),
                details={
                    "acl_provenance": acl_provenance,
                    "effective_path": result_path,
                    "security_definer": security_definer,
                    "security_invoker": security_invoker,
                    "column": composition,
                },
            )
        )

    path_result = PrivilegeResult(
        object_identity=oid,
        principal=principal,
        privilege=privilege,
        path=result_path,
        granted=composed_granted,
        exercisable=exercisable,
        reason_codes=tuple(dict.fromkeys(reasons)),
        details={
            "acl_provenance": acl_provenance,
            "effective_acl": [dict(e) for e in effective_acl],
            "security_definer": security_definer,
            "security_invoker": security_invoker,
            "column": composition,
            "schema_usage": schema_ok,
            "table_granted": table_granted,
            "column_specific_granted": column_specific_granted,
            "composed_granted": composed_granted,
            "table_paths": list(table_paths),
            "column_paths": list(column_paths),
            "contributing_paths": list(contributing_paths),
        },
    )
    results.insert(0, path_result)
    return results


def evaluate_object_matrix(
    *,
    object_kind: str,
    object_identity: Mapping[str, Any] | str,
    privileges: Sequence[str],
    principals: Sequence[str],
    owner: str,
    raw_acl: Sequence[Mapping[str, Any]] | None,
    memberships: Sequence[Mapping[str, Any]] | None = None,
    schema_usage: Mapping[str, bool] | None = None,
    superusers: Iterable[str] | None = None,
    default_privilege_owner: str | None = None,
    table_raw_acl: Sequence[Mapping[str, Any]] | None = None,
    table_owner: str | None = None,
    security_definer: bool | None = None,
    security_invoker: bool | None = None,
) -> list[PrivilegeResult]:
    """Evaluate all principal/privilege pairs deterministically from raw facts."""
    out: list[PrivilegeResult] = []
    for principal in sorted(principals):
        for privilege in privileges:
            out.extend(
                evaluate_privilege(
                    object_kind=object_kind,
                    object_identity=object_identity,
                    privilege=privilege,
                    principal=principal,
                    owner=owner,
                    raw_acl=raw_acl,
                    memberships=memberships,
                    schema_usage=schema_usage,
                    superusers=superusers,
                    default_privilege_owner=default_privilege_owner,
                    table_raw_acl=table_raw_acl,
                    table_owner=table_owner,
                    table_privilege_granted=True if (
                        object_kind.upper() == "COLUMN" and table_raw_acl is not None
                    ) else None,
                    security_definer=security_definer,
                    security_invoker=security_invoker,
                )
            )
    return out
