"""Round 5A executable privilege reference model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from tools.round5a_kernel.models import KernelError, PrivilegeResult, normalize_identity

PUBLIC = "PUBLIC"

COLUMN_SUPPORTED_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "REFERENCES"})
TABLE_ONLY_PRIVILEGES = frozenset({"DELETE", "TRUNCATE", "TRIGGER"})

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

    return granted, path, reasons, paths


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
    table_raw_acl: Sequence[Mapping[str, Any]] | None = None,
    table_owner: str | None = None,
    security_definer: bool | None = None,
    security_invoker: bool | None = None,
) -> list[PrivilegeResult]:
    """Evaluate privilege paths for one principal against one object."""
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
        if kind != "SCHEMA":
            schema_ok = bool(schema_usage.get(principal, False)) or principal in superuser_set
            if granted and not schema_ok:
                reasons.append("KR-PRIV-SCHEMA-DENIED")
                path = "SCHEMA_GATED"

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
                        "effective_path": path,
                        "contributing_paths": list(contributing),
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
            path=path if granted else "DIRECT",
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
    # Column-specific grant excludes owner/superuser folded solely via table ownership when
    # those paths are recorded only because principal owns the column object; retain ACL paths
    # plus owner/superuser as column-side contributions when they fired on the column ACL eval.
    column_specific_granted = col_granted
    column_paths = list(col_paths)

    # Table contribution: evaluate separately; do not mutate column path records.
    table_paths: list[str] = []
    if table_privilege_paths is not None:
        table_paths = [str(p) for p in table_privilege_paths]
        table_granted = len(table_paths) > 0 or bool(table_privilege_granted)
    elif table_raw_acl is not None or table_privilege_granted is not None:
        if table_raw_acl is not None or table_owner is not None:
            t_owner = table_owner if table_owner is not None else owner
            t_acl, _ = resolve_effective_acl("TABLE", table_raw_acl, t_owner)
            t_granted, t_path, _t_reasons, t_paths = _evaluate_grant_paths(
                privilege=privilege,
                principal=principal,
                owner=t_owner,
                effective_acl=t_acl,
                memberships=memberships,
                superuser_set=superuser_set,
            )
            table_granted = t_granted
            table_paths = list(t_paths) if t_granted else []
            if t_granted and not table_paths:
                table_paths = [t_path]
        else:
            table_granted = bool(table_privilege_granted)
            if table_granted:
                table_paths = ["DIRECT"]
    else:
        table_granted = False

    # Null/empty attacl contribute no column-specific grant (owner/superuser still may).
    null_attacl = raw_acl is None
    empty_attacl = raw_acl is not None and len(tuple(raw_acl)) == 0
    if null_attacl or empty_attacl:
        # ACL-derived column paths only; owner/superuser remain visible if present.
        acl_only_paths = [p for p in column_paths if p in {"DIRECT", "PUBLIC_DERIVED", "INHERITED", "SET_ROLE_ONLY"}]
        if not acl_only_paths:
            # Keep owner/superuser as column-side only when they fired without ACL entries.
            pass

    composed_granted = bool(table_granted or column_specific_granted)
    if not composed_granted:
        reasons.append("KR-PRIV-NO-GRANT")
    else:
        # Drop NO-GRANT if composition produced a grant.
        col_reasons = [r for r in col_reasons if r != "KR-PRIV-NO-GRANT"]

    contributing_paths: list[str] = []
    for p in table_paths:
        if p not in contributing_paths:
            contributing_paths.append(p)
    for p in column_paths:
        if p not in contributing_paths:
            contributing_paths.append(p)

    primary_path = col_path if column_specific_granted else "DIRECT"
    if table_granted and not column_specific_granted:
        primary_path = "TABLE_COMPOSED_TO_COLUMN"
        reasons.append("KR-PRIV-TABLE-COMPOSED")
    elif table_granted and column_specific_granted:
        reasons.append("KR-PRIV-TABLE-COMPOSED")
        if "TABLE_COMPOSED_TO_COLUMN" not in contributing_paths:
            contributing_paths.append("TABLE_COMPOSED_TO_COLUMN")
        primary_path = col_path
    reasons.extend(col_reasons)

    if default_privilege_owner is not None and default_privilege_owner != owner:
        reasons.append("KR-PRIV-DEFAULT-OWNER-MISMATCH")

    # Schema gating applies after composition.
    schema_ok = bool(schema_usage.get(principal, False)) or principal in superuser_set
    if composed_granted and not schema_ok:
        reasons.append("KR-PRIV-SCHEMA-DENIED")
        primary_path = "SCHEMA_GATED"

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
        # legacy keys retained for existing tests
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
                    "effective_path": primary_path,
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
        path=primary_path if composed_granted else "DIRECT",
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
    table_privileges: Mapping[str, Mapping[str, bool]] | None = None,
    table_raw_acl: Sequence[Mapping[str, Any]] | None = None,
    table_owner: str | None = None,
    security_definer: bool | None = None,
    security_invoker: bool | None = None,
) -> list[PrivilegeResult]:
    """Evaluate all principal/privilege pairs deterministically."""
    out: list[PrivilegeResult] = []
    for principal in sorted(principals):
        for privilege in privileges:
            table_granted = None
            if object_kind.upper() == "COLUMN" and table_privileges is not None:
                table_granted = bool(table_privileges.get(principal, {}).get(privilege, False))
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
                    table_privilege_granted=table_granted,
                    table_raw_acl=table_raw_acl,
                    table_owner=table_owner,
                    security_definer=security_definer,
                    security_invoker=security_invoker,
                )
            )
    return out
