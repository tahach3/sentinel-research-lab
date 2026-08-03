# SRL Phase 1 — Canonical Evidence Specification

**Bundle:** `srl-phase1-catalog-sql-recreated-20260801`  
**Authoritative SQL:** `SRL_Phase1_catalog_snapshot.sql`  
**Decision Record alignment:** `docs/ROUND_5A_REVISION_8_NORMATIVE_DECISION_RECORD.md` §1 EV-* markers (read-only reference; not modified)

This document defines exactly one canonical serialization for Phase 1 catalog evidence digests and row materialization after SQL execution.

---

## 1. Canonical serialization (single algorithm)

| Rule | Value |
| --- | --- |
| Encoding | UTF-8 |
| Line endings in source dumps | LF |
| Field separator | U+001F (UNIT SEPARATOR) |
| Record separator | U+001E (RECORD SEPARATOR) |
| Null | `\N` (backslash + N; two characters) |
| Boolean | `t` / `f` |
| Column order | Fixed selected-column order per evidence set (below) |
| Row order | Deterministic natural-key order with PostgreSQL `COLLATE "C"` |
| Final framing | Exactly one trailing record separator after the last record |
| Locale | No locale-sensitive formatting; no thousands separators; no localized booleans |
| OID policy | Unstable OIDs excluded from digest input and from `row_key` |
| Digest output | Lowercase hexadecimal SHA-256 (64 chars). If live `digest(bytea,text)` is unavailable, record `md5` fallback separately and still emit the known empty SHA-256 constant self-test value for empty input: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Digest construction

1. Select columns for the evidence set in the listed order (exclude unstable xref columns).
2. Sort rows by natural row key / canonical ordering (`COLLATE "C"`).
3. For each row, emit fields joined by U+001F; encode null as `\N`; booleans as `t`/`f`.
4. Join rows with U+001E; append one final U+001E.
5. SHA-256 over the UTF-8 bytes of that framed payload (lowercase hex).
6. Empty set: SHA-256 of the algorithm label + U+001F with no rows, or empty payload per set note — Phase 1 drift digests use natural-key concatenation algorithm `natural_keys_roles_functions_tables_v1` as emitted by G00/G99.

### Row key escaping

Within `row_key` segments, escape `\` as `\\` and `|` as `\|` so `|` remains the sole structural separator.

---

## 2. Evidence sets

Decision-record markers appear in parentheses where aligned.

### EV-PG-VERSION (EV-PG-VERSION)

| Field | Value |
| --- | --- |
| Identifier | `EV-PG-VERSION` |
| Selected columns | `server_version_string`, `server_version`, `server_version_num`, `database_name`, `current_user_name` |
| Natural row key | `session\|<database>\|<current_user>` |
| Ordering | single row |
| Unstable xref excluded | `backend_pid_unstable_xref` |
| Rev7 notes | none |

### EV-DRIFT-START / EV-DRIFT-END (EV-DRIFT-START, EV-DRIFT-END)

| Field | Value |
| --- | --- |
| Identifiers | `EV-DRIFT-START`, `EV-DRIFT-END` |
| Selected columns | `drift_algorithm`, `drift_digest_md5_fallback`, `drift_payload_bytes`, `sha256_empty_selftest_status` (start only) |
| Natural row key | `drift\|start` / `drift\|end` |
| Ordering | single row each |
| Unstable xref excluded | all OIDs (none in digest input) |
| Rev7 notes | End digest must equal start; mismatch ⇒ catalog drift/mutation during capture |

### EV-CRYPTO-LOCATION (EV-CRYPTO-LOCATION)

| Field | Value |
| --- | --- |
| Identifier | `EV-CRYPTO-LOCATION` |
| Selected columns | `extension_name`, `extension_schema`, `proc_schema`, `proc_name`, `identity_args`, `proc_owner` |
| Natural row key | `crypto\|extension\|…` or `crypto\|proc\|…` |
| Ordering | `row_key COLLATE "C"` |
| Unstable xref excluded | yes |
| Rev7 notes | Location evidence only; do not relocate extensions in Phase 1 |

### EV-ROLE-001 / EV-ROLE-ATTR-001 (EV-ROLES)

| Field | Value |
| --- | --- |
| Identifiers | `EV-ROLE-001`, `EV-ROLE-ATTR-001` |
| Selected columns (001) | `role_name`, `can_login`, `inherit_attr`, `is_superuser`, `can_create_role`, `can_create_db`, `can_replicate`, `bypass_rls`, `has_connect`, `research_usage`, `research_create` |
| Natural row key | `role\|<role_name>` / `roleattr\|<role_name>` |
| Ordering | `role_name COLLATE "C"` |
| Unstable xref excluded | `role_oid_unstable_xref` |
| Rev7 notes | Confirm presence/absence of `research_governance` / `research_test` vs Rev7 preflight assumptions |

### EV-ROLE-MEM-001 (EV-MEMBERSHIPS)

| Field | Value |
| --- | --- |
| Identifier | `EV-ROLE-MEM-001` |
| Selected columns | `member_name`, `granted_name`, `is_direct`, `depth`, `membership_path`, `member_inherit_attr`, `path_grants_inherited_authority`, `requires_explicit_set_role`, `admin_option` |
| Natural row key | `membership\|<member>\|<granted>\|<depth>\|<path>` |
| Ordering | member, granted, depth, path (`COLLATE "C"`) |
| Unstable xref excluded | yes |
| Rev7 notes | Inherited WRITE assumed N when no inherit path |

### EV-SCHEMA-001 / EV-SCHEMA-PRIVS (EV-SCHEMAS, EV-SCHEMA-PRIVS)

| Field | Value |
| --- | --- |
| Identifiers | `EV-SCHEMA-001`, `EV-SCHEMA-PRIVS` |
| Selected columns (001) | `schema_name`, `owner_name`, `raw_acl_text`, `expanded_defaulted_acl_text`, `grantor_name`, `grantee_name`, `is_public`, `privilege_type`, `is_grantable`, `grantee_is_owner` |
| Natural row key | `schema\|…` / `schemapriv\|…` |
| Ordering | schema, grantee/role, privilege (`COLLATE "C"`) |
| Unstable xref excluded | `schema_oid_unstable_xref` |
| PUBLIC | grantee OID `0` serialized as `PUBLIC` |
| Rev7 notes | CREATE denied expectations for runtime roles are evaluated from these rows |

### EV-EXTENSION-001 (EV-EXTENSIONS)

| Field | Value |
| --- | --- |
| Identifier | `EV-EXTENSION-001` |
| Selected columns | `extension_name`, `extension_version`, `extension_schema`, `owner_name` |
| Natural row key | `extension\|<name>\|<schema>` |
| Ordering | name, schema (`COLLATE "C"`) |
| Unstable xref excluded | `extension_oid_unstable_xref` |

### EV-FUNCTION-001 (EV-FUNCTIONS)

| Field | Value |
| --- | --- |
| Identifier | `EV-FUNCTION-001` |
| Selected columns | `schema_name`, `function_name`, `identity_args`, `result_type`, `owner_name`, `language_name`, `security_mode`, `volatility`, `parallel_classification`, `raw_proacl_text`, `proacl_is_null_defaults_apply`, `research_function_count`, `distinct_function_names`, `helper_name_matches` |
| Natural row key | `function\|research\|<name>\|<identity_args>` |
| Ordering | name, identity_args (`COLLATE "C"`) |
| Unstable xref excluded | `function_oid_unstable_xref` |
| ACL semantics | null `proacl` ⇒ defaults via `acldefault('f', proowner)` including PUBLIC EXECUTE |

### EV-HELPER-FUNCTIONS (EV-HELPER-FUNCTIONS)

| Field | Value |
| --- | --- |
| Identifier | `EV-HELPER-FUNCTIONS` |
| Selected columns | `schema_name`, `function_name`, `identity_args`, `owner_name`, `raw_proacl_text` |
| Natural row key | `helper\|<schema>\|<name>\|<identity_args>` |
| Ordering | schema, name, args (`COLLATE "C"`) |

### EV-SCHEMA-VERSION (EV-SCHEMA-VERSION)

| Field | Value |
| --- | --- |
| Identifier | `EV-SCHEMA-VERSION` |
| Selected columns | `schema_version_table_present`, `table_name`, `ordinal`, `column_name`, `data_type` |
| Natural row key | `schema_version\|research\|catalog\|…` |
| Ordering | ordinal |
| Notes | Max version **value** is not invented here; run-specific select only after unique column resolution (else `BLOCKED_MISSING_CATALOG_DETAIL`) |

### EV-FUNCTION-ACL-001 / EV-FUNCTION-ACL-002 (EV-FUNCTION-ACLS, EV-FUNCTION-PUBLIC)

| Field | Value |
| --- | --- |
| Identifiers | `EV-FUNCTION-ACL-001`, `EV-FUNCTION-ACL-002` |
| Selected columns (001) | `schema_name`, `function_name`, `identity_args`, `owner_name`, `raw_proacl_text`, `grantor_name`, `grantee_name`, `is_public`, `privilege_type`, `is_grantable`, `grantee_is_owner` |
| Natural row key | `function\|research\|<name>\|<args>\|<grantee>\|<privilege>` |
| Ordering | name, args, grantee, privilege (`COLLATE "C"`) |
| Unstable xref excluded | function OID |
| PUBLIC | OID `0` ⇒ `PUBLIC`; focused PUBLIC EXECUTE set in `EV-FUNCTION-ACL-002` |
| Rev7 notes | PUBLIC EXECUTE presence confirms/contradicts Rev7 blanket-grant assumptions |

### EV-FUNCTION-EXEC-001 (EV-FUNCTION-EFFECTIVE)

| Field | Value |
| --- | --- |
| Identifier | `EV-FUNCTION-EXEC-001` |
| Selected columns | `schema_name`, `function_name`, `identity_args`, `role_name`, `direct_execute`, `public_execute`, `inherited_execute`, `set_role_only_execute`, `owner_derived`, `superuser_derived`, `schema_usage`, `final_exercisable_execute`, `catalog_has_execute` |
| Natural row key | `function\|research\|<name>\|<args>\|<role>\|EXECUTE` |
| Ordering | name, args, role (`COLLATE "C"`) |
| Path columns | kept separate; not collapsed to one unexplained boolean |
| Rev7 notes | Direct `research_app` EXECUTE vs PUBLIC EXECUTE evaluated from path columns |

### EV-TABLE-001 (EV-TABLES)

| Field | Value |
| --- | --- |
| Identifier | `EV-TABLE-001` |
| Selected columns | `schema_name`, `table_name`, `owner_name`, `persistence`, `rls_enabled`, `rls_forced`, `raw_relacl_text`, `relacl_is_null_defaults_apply` |
| Natural row key | `table\|research\|<table>` |
| Ordering | `table_name COLLATE "C"` |
| Unstable xref excluded | `table_oid_unstable_xref` |

### EV-TABLE-ACL-001 (EV-TABLE-ACLS)

| Field | Value |
| --- | --- |
| Identifier | `EV-TABLE-ACL-001` |
| Selected columns | `schema_name`, `table_name`, `owner_name`, `raw_relacl_text`, `grantor_name`, `grantee_name`, `is_public`, `privilege_type`, `is_grantable`, `grantee_is_owner` |
| Natural row key | `table\|research\|<table>\|<grantee>\|<privilege>` |
| Ordering | table, grantee, privilege (`COLLATE "C"`) |
| ACL semantics | `COALESCE(relacl, acldefault('r', relowner))`; owner implicit vs granted distinguished via `grantee_is_owner` + grant rows |

### EV-TABLE-WRITE-001 / EV-TABLE-WRITE-002 (EV-TABLE-WRITES)

| Field | Value |
| --- | --- |
| Identifiers | `EV-TABLE-WRITE-001`, `EV-TABLE-WRITE-002` |
| Selected columns (001) | `schema_name`, `table_name`, `role_name`, `privilege_type`, `direct_grant`, `public_grant`, `inherited_grant`, `set_role_only_grant`, `owner_derived`, `superuser_derived`, `schema_usage`, `final_exercisable`, `catalog_has_privilege` |
| Natural row key | `table\|research\|<table>\|<role>\|<privilege>` |
| Ordering | table, role, privilege (`COLLATE "C"`) |
| Rev7 assertion (002) | `research_app DELETE = Y on every table` → per-table `CONFIRMS` / `CONTRADICTS` / `BLOCKED_MISSING_CATALOG_DETAIL` |

### EV-COLUMN-ACL-001 / EV-COLUMN-EFF-001 (EV-COLUMNS, EV-COLUMN-ACLS, EV-COLUMN-EFFECTIVE)

| Field | Value |
| --- | --- |
| Identifiers | `EV-COLUMN-ACL-001`, `EV-COLUMN-EFF-001` |
| Selected columns (ACL) | `schema_name`, `table_name`, `ordinal`, `column_name`, `raw_attacl_text`, `explicit_column_acl_absent`, `grantee_name`, `is_public`, `privilege_type`, `is_grantable` |
| Natural row key | `column\|research\|<table>\|<ordinal>\|<column>\|<role>\|<privilege>` |
| Ordering | table, ordinal, column, role, privilege (`COLLATE "C"`) |
| ACL semantics | **Do not** apply `acldefault` to `attacl`; null ⇒ no column-specific ACL |
| Rev7 notes | Full-column UPDATE assumptions confirmed/contradicted via effective column/table path columns |

### EV-VIEW-001 (EV-VIEWS)

| Field | Value |
| --- | --- |
| Identifier | `EV-VIEW-001` |
| Selected columns | `schema_name`, `view_name`, `view_kind`, `owner_name`, `definition_md5`, `definition_length`, `raw_relacl_text`, `defaulted_acl_text` |
| Natural row key | `view\|research\|<name>\|<kind>` |
| Ordering | kind, name (`COLLATE "C"`) |
| Notes | Definition body replaced by deterministic MD5 for digest stability/size |

### EV-SEQUENCE-001 (EV-SEQUENCES)

| Field | Value |
| --- | --- |
| Identifier | `EV-SEQUENCE-001` |
| Selected columns | `schema_name`, `sequence_name`, `owner_name`, `raw_relacl_text`, `defaulted_acl_text`, `grantor_name`, `grantee_name`, `is_public`, `privilege_type`, `is_grantable` |
| Natural row key | `sequence\|research\|<name>\|<grantee>\|<privilege>` |
| Ordering | name, grantee, privilege (`COLLATE "C"`) |
| ACL semantics | `COALESCE(relacl, acldefault('s', relowner))` |

### EV-TRIGGER-001 (EV-TRIGGERS)

| Field | Value |
| --- | --- |
| Identifier | `EV-TRIGGER-001` |
| Selected columns | `schema_name`, `table_name`, `trigger_name`, `enabled_state`, `trigger_def`, `function_schema`, `function_name`, `function_identity_args`, `is_internal` |
| Natural row key | `trigger\|research\|<table>\|<trigger>` |
| Ordering | table, trigger (`COLLATE "C"`) |

### EV-RLS-001 (EV-RLS)

| Field | Value |
| --- | --- |
| Identifier | `EV-RLS-001` |
| Selected columns | `schema_name`, `table_name`, `policy_name`, `policy_command`, `permissive_or_restrictive`, `policy_roles`, `using_expression`, `with_check_expression` |
| Natural row key | `rls\|research\|<table>\|<policy>` |
| Ordering | table, policy (`COLLATE "C"`) |

### EV-CONSTRAINT-001 / EV-INDEX-001 (EV-CONSTRAINTS, EV-INDEXES)

| Field | Value |
| --- | --- |
| Identifiers | `EV-CONSTRAINT-001`, `EV-INDEX-001` |
| Selected columns (constraints) | `schema_name`, `table_name`, `constraint_name`, `constraint_type`, `constraint_def`, `is_validated`, `is_deferrable`, `is_deferred`, `is_local` |
| Selected columns (indexes) | `schema_name`, `table_name`, `index_name`, `is_unique`, `is_primary`, `is_valid`, `is_ready`, `is_live`, `index_def`, `index_predicate` |
| Natural row keys | `constraint\|…`, `index\|…` |
| Ordering | table, name (`COLLATE "C"`) |

### EV-DEFACL-001 / EV-DEFACL-002 (EV-DEFAULT-PRIVS)

| Field | Value |
| --- | --- |
| Identifiers | `EV-DEFACL-001`, `EV-DEFACL-002` |
| Selected columns (001) | `target_owner_name`, `schema_name`, `object_type`, `grantor_name`, `grantee_name`, `is_public`, `privilege_type`, `is_grantable`, `raw_defacl_text` |
| Natural row key | `default_acl\|<owner>\|<schema>\|<object_type>\|<grantee>\|<privilege>` |
| Provenance (002) | per table: `matching_owner_default_privilege` / `no_matching_owner_default_privilege` / `ambiguous_provenance` |
| Rev7 notes | Default-privilege owner mismatches surface as provenance_class ≠ matching |

### EV-APP-DISCOVERY-001 (feeds EV-SAFETY-BASELINE, EV-RESERVATION-STATE, EV-CUTOVER-STATE)

| Field | Value |
| --- | --- |
| Identifier | `EV-APP-DISCOVERY-001` |
| Selected columns | `discovery_kind`, `discovery_class`, `table_name`, `ordinal`, `column_name`, `data_type`, `secret_risk_name_match`, `matched_pattern` |
| Natural row key | `appdisc\|…` |
| Ordering | `row_key COLLATE "C"` |
| Secret safety | Names/metadata only; never secret values |
| Secret-risk name patterns | `secret`, `token`, `api_key`, `password`, `private_key`, `cipher`, `encrypted`, `plaintext` |

### G20 templates (EV-SAFETY-BASELINE / EV-RESERVATION-STATE / EV-CUTOVER-STATE)

| Field | Value |
| --- | --- |
| Identifiers | `EV-SAFETY-BASELINE-TEMPLATE`, `EV-RESERVATION-STATE-TEMPLATE`, `EV-CUTOVER-STATE-TEMPLATE` |
| Status until resolution | `BLOCKED_UNTIL_G19_UNIQUE_RESOLUTION` |
| Non-unique token | `BLOCKED_MISSING_CATALOG_DETAIL` |
| Rule | Do not fill placeholders with guesses; run-specific copy only from unique G19 results |

---

## 3. ACL / privilege path semantics (normative for this bundle)

| Object | Rule |
| --- | --- |
| Functions | `COALESCE(proacl, acldefault('f', proowner))` + `aclexplode`; null ≠ no privilege |
| Tables | `COALESCE(relacl, acldefault('r', relowner))` + `aclexplode`; distinguish owner vs granted |
| Sequences | `COALESCE(relacl, acldefault('s', relowner))` + `aclexplode` |
| Columns | no `acldefault` on `attacl`; null = no column-specific ACL |
| PUBLIC | ACL grantee OID `0` ⇒ `PUBLIC` (never rely on `pg_get_userbyid(0)`) |
| Paths | direct; PUBLIC; inherited (INHERIT); SET ROLE-only; owner-derived; superuser-derived; schema-USAGE gating; final exercisable — separate columns |
| Identities | Natural keys only in `row_key` and digest input; OIDs are unstable xrefs |

---

## 4. Mapping to Decision Record markers (31)

| DR marker | Bundle evidence_set |
| --- | --- |
| EV-PG-VERSION | EV-PG-VERSION |
| EV-SCHEMA-VERSION | EV-SCHEMA-VERSION |
| EV-ROLES | EV-ROLE-001, EV-ROLE-ATTR-001 |
| EV-MEMBERSHIPS | EV-ROLE-MEM-001 |
| EV-SCHEMAS | EV-SCHEMA-001 |
| EV-SCHEMA-PRIVS | EV-SCHEMA-PRIVS |
| EV-EXTENSIONS | EV-EXTENSION-001 |
| EV-FUNCTIONS | EV-FUNCTION-001 |
| EV-FUNCTION-ACLS | EV-FUNCTION-ACL-001 |
| EV-FUNCTION-PUBLIC | EV-FUNCTION-ACL-002 |
| EV-FUNCTION-EFFECTIVE | EV-FUNCTION-EXEC-001 |
| EV-TABLES | EV-TABLE-001 |
| EV-TABLE-ACLS | EV-TABLE-ACL-001 |
| EV-TABLE-WRITES | EV-TABLE-WRITE-001, EV-TABLE-WRITE-002 |
| EV-COLUMNS | EV-COLUMN-ACL-001 (identity columns) |
| EV-COLUMN-ACLS | EV-COLUMN-ACL-001 |
| EV-COLUMN-EFFECTIVE | EV-COLUMN-EFF-001 |
| EV-VIEWS | EV-VIEW-001 |
| EV-SEQUENCES | EV-SEQUENCE-001 |
| EV-TRIGGERS | EV-TRIGGER-001 |
| EV-RLS | EV-RLS-001 |
| EV-CONSTRAINTS | EV-CONSTRAINT-001 |
| EV-INDEXES | EV-INDEX-001 |
| EV-DEFAULT-PRIVS | EV-DEFACL-001, EV-DEFACL-002 |
| EV-SAFETY-BASELINE | EV-APP-DISCOVERY-001 + G20 template |
| EV-RESERVATION-STATE | EV-APP-DISCOVERY-001 + G20 template |
| EV-CUTOVER-STATE | EV-APP-DISCOVERY-001 + G20 template |
| EV-HELPER-FUNCTIONS | EV-HELPER-FUNCTIONS |
| EV-CRYPTO-LOCATION | EV-CRYPTO-LOCATION |
| EV-DRIFT-START | EV-DRIFT-START |
| EV-DRIFT-END | EV-DRIFT-END |
