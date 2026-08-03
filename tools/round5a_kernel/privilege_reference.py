"""Round 5A executable privilege reference model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from tools.round5a_kernel.models import KernelError, PrivilegeResult, normalize_identity

PUBLIC = "PUBLIC"

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


def _membership_closure(
    start: str,
    memberships: Sequence[Mapping[str, Any]],
    *,
    inherit_only: bool,
) -> set[str]:
    edges: dict[str, set[str]] = {}
    for m in memberships:
        member = str(m["member"])
        granted = str(m["granted_role"])
        if inherit_only and bool(m.get("set_role_only", False)):
            continue
        if (not inherit_only) and (not bool(m.get("set_role_only", False))):
            # set_role_only edges are excluded from inherit closure
            pass
        if inherit_only and bool(m.get("set_role_only", False)):
            continue
        if inherit_only is False:
            # building set-role graph separately
            pass
        edges.setdefault(member, set()).add(granted)

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

    if isinstance(object_identity, str):
        oid = object_identity
        identity_map = {"name": object_identity}
    else:
        identity_map = dict(object_identity)
        oid = normalize_identity(identity_map)

    effective_acl, acl_provenance = resolve_effective_acl(kind, raw_acl, owner)
    grants = _acl_grants(effective_acl, privilege)
    inherit = _inherit_roles(principal, memberships)
    set_role = _set_role_roles(principal, memberships)

    results: list[PrivilegeResult] = []
    reasons: list[str] = []
    granted = False
    path = "DIRECT"

    # PUBLIC is a special principal, never a discovered role.
    if principal == PUBLIC:
        raise KernelError("KR-PRIV-PUBLIC-PRINCIPAL", "PUBLIC is not an evaluable session principal")

    if principal in grants:
        granted = True
        path = "DIRECT"
        reasons.append("KR-PRIV-DIRECT")
    elif PUBLIC in grants:
        granted = True
        path = "PUBLIC_DERIVED"
        reasons.append("KR-PRIV-PUBLIC")
    else:
        inherited_hit = sorted(r for r in inherit if r != principal and r in grants)
        if inherited_hit:
            granted = True
            path = "INHERITED"
            reasons.append("KR-PRIV-INHERITED")
        else:
            set_hit = sorted(r for r in set_role if r in grants)
            if set_hit:
                granted = True
                path = "SET_ROLE_ONLY"
                reasons.append("KR-PRIV-SET-ROLE")

    owner_derived = principal == owner
    if owner_derived:
        # Owner path is always recorded; grants may already be true via ACL default.
        if not granted:
            granted = True
            path = "OWNER_DERIVED"
        reasons.append("KR-PRIV-OWNER")

    superuser_derived = principal in superuser_set
    if superuser_derived:
        if not granted:
            granted = True
            path = "SUPERUSER_DERIVED"
        reasons.append("KR-PRIV-SUPERUSER")

    if not granted:
        reasons.append("KR-PRIV-NO-GRANT")

    if default_privilege_owner is not None and default_privilege_owner != owner:
        reasons.append("KR-PRIV-DEFAULT-OWNER-MISMATCH")

    schema_ok = True
    if kind != "SCHEMA":
        schema_ok = bool(schema_usage.get(principal, False)) or superuser_derived
        if granted and not schema_ok:
            reasons.append("KR-PRIV-SCHEMA-DENIED")
            path = "SCHEMA_GATED"

    column_table = None
    if kind == "COLUMN":
        reasons.append("KR-PRIV-COLUMN-INDEPENDENT")
        column_specific = granted and path in {
            "DIRECT",
            "PUBLIC_DERIVED",
            "INHERITED",
            "SET_ROLE_ONLY",
        }
        table_level = bool(table_privilege_granted)
        column_table = {
            "table_privilege": table_level,
            "column_specific_privilege": bool(column_specific) or (
                granted and path in {"OWNER_DERIVED", "SUPERUSER_DERIVED"}
            ),
            "null_attacl": raw_acl is None,
            "empty_attacl": raw_acl is not None and len(tuple(raw_acl)) == 0,
            "acldefault_c_applied": False,
        }
        # Resulting exercisability requires table-level OR column-specific grant,
        # plus schema gate / owner / superuser paths already folded into granted.
        if not (column_table["table_privilege"] or column_table["column_specific_privilege"] or superuser_derived or owner_derived):
            granted = False
            if "KR-PRIV-NO-GRANT" not in reasons:
                reasons.append("KR-PRIV-NO-GRANT")

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
                reason_codes=tuple(dict.fromkeys(reasons + ["KR-PRIV-DIRECT" if path == "DIRECT" else f"KR-PRIV-{path.replace('_DERIVED','').replace('_ONLY','')}".replace("KR-PRIV-PUBLIC_DERIVED", "KR-PRIV-PUBLIC")])),
                details={
                    "acl_provenance": acl_provenance,
                    "effective_path": path,
                    "security_definer": security_definer,
                    "security_invoker": security_invoker,
                    "column": column_table,
                },
            )
        )

    # Always emit the decisive path result.
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
            "column": column_table,
            "schema_usage": schema_ok,
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
                    security_definer=security_definer,
                    security_invoker=security_invoker,
                )
            )
    return out
