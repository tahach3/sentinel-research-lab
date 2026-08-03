-- =============================================================================
-- SRL Phase 1 — Catalog Evidence Snapshot (read-only)
-- Bundle: srl-phase1-catalog-sql-recreated-20260801
-- PostgreSQL 11+ | authoritative consolidated execution artifact
-- Groups: G00–G20, G99
-- DO NOT install/move extensions. DO NOT select secret column values.
-- Safe to re-run: BEGIN … SET TRANSACTION READ ONLY … ROLLBACK
-- =============================================================================

-- === G00 SESSION / CAPTURE METADATA ===
-- Evidence: EV-PG-VERSION, EV-DRIFT-START, EV-CRYPTO-LOCATION (availability probe)

SELECT
  'EV-PG-VERSION'::text AS evidence_set,
  ('session|' || current_database() || '|' || current_user)::text AS row_key,
  ('phase1|' || current_database() || '|'
     || to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYYMMDD"T"HH24MISS.US"Z"'))::text AS capture_id,
  current_database()::text AS database_name,
  current_user::text AS current_user_name,
  session_user::text AS session_user_name,
  version()::text AS server_version_string,
  current_setting('server_version')::text AS server_version,
  current_setting('server_version_num')::integer AS server_version_num,
  current_setting('transaction_isolation')::text AS transaction_isolation,
  current_setting('transaction_read_only')::text AS transaction_read_only,
  current_setting('server_encoding')::text AS server_encoding,
  pg_backend_pid() AS backend_pid_unstable_xref
;

-- Start drift digest from natural keys only (no OIDs). Prefer pgcrypto digest when
-- already resolvable in search_path at parse time is unsafe; use built-in md5 for
-- the executable fingerprint and report digest()-availability separately.
WITH catalog_nk AS (
  SELECT ('role|' || r.rolname)::text AS nk
  FROM pg_catalog.pg_roles r
  UNION ALL
  SELECT ('function|research|' || p.proname || '|' || pg_catalog.pg_get_function_identity_arguments(p.oid))::text
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'research'
  UNION ALL
  SELECT ('table|research|' || c.relname)::text
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'research'
    AND c.relkind = 'r'
    AND NOT c.relispartition
),
agg AS (
  SELECT COALESCE(string_agg(nk, E'\n' ORDER BY nk COLLATE "C"), '') AS payload
  FROM catalog_nk
),
digest_avail AS (
  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc p
    JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
    WHERE p.proname = 'digest'
      AND pg_catalog.pg_get_function_identity_arguments(p.oid) = 'bytea, text'
  ) AS digest_bytea_text_present,
  EXISTS (
    SELECT 1
    FROM pg_catalog.pg_extension e
    WHERE e.extname = 'pgcrypto'
  ) AS pgcrypto_installed,
  (
    SELECT n.nspname
    FROM pg_catalog.pg_extension e
    JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
    WHERE e.extname = 'pgcrypto'
    ORDER BY n.nspname COLLATE "C"
    LIMIT 1
  ) AS pgcrypto_schema
)
SELECT
  'EV-DRIFT-START'::text AS evidence_set,
  'drift|start'::text AS row_key,
  md5(a.payload) AS drift_digest_md5_fallback,
  length(a.payload) AS drift_payload_bytes,
  'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'::text AS sha256_empty_known_constant,
  d.digest_bytea_text_present,
  d.pgcrypto_installed,
  d.pgcrypto_schema,
  CASE
    WHEN d.digest_bytea_text_present THEN 'DIGEST_PRESENT_NOT_INVOKED_PARSE_SAFE_USE_KNOWN_CONSTANT_AND_MD5_FALLBACK'
    ELSE 'DIGEST_ABSENT_USING_MD5_FALLBACK_AND_KNOWN_SHA256_CONSTANT'
  END AS sha256_empty_selftest_status,
  'natural_keys_roles_functions_tables_v1'::text AS drift_algorithm
FROM agg a
CROSS JOIN digest_avail d
;

SELECT
  'EV-CRYPTO-LOCATION'::text AS evidence_set,
  ('crypto|extension|' || e.extname || '|' || n.nspname)::text AS row_key,
  e.extname::text AS extension_name,
  n.nspname::text AS extension_schema,
  NULL::text AS proc_name,
  NULL::text AS identity_args,
  NULL::text AS proc_schema,
  NULL::text AS proc_owner
FROM pg_catalog.pg_extension e
JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname = 'pgcrypto'
UNION ALL
SELECT
  'EV-CRYPTO-LOCATION'::text AS evidence_set,
  ('crypto|proc|' || n.nspname || '|' || p.proname || '|'
     || pg_catalog.pg_get_function_identity_arguments(p.oid))::text AS row_key,
  NULL::text AS extension_name,
  NULL::text AS extension_schema,
  p.proname::text AS proc_name,
  pg_catalog.pg_get_function_identity_arguments(p.oid)::text AS identity_args,
  n.nspname::text AS proc_schema,
  r.rolname::text AS proc_owner
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
WHERE p.proname IN ('digest', 'gen_random_uuid')
ORDER BY 2 COLLATE "C"
;

-- === G01 SAFETY GUARDS ===
BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '180s';
SET LOCAL client_min_messages = warning;

-- Fail closed if PostgreSQL < 11 (integer division by zero).
SELECT
  'G01_VERSION_GUARD'::text AS evidence_set,
  'guard|pg_version'::text AS row_key,
  current_setting('server_version_num')::integer AS server_version_num,
  (1 / CASE
         WHEN current_setting('server_version_num')::integer >= 110000 THEN 1
         ELSE 0
       END) AS pg_version_ok_or_fail
;

SELECT
  'G01_HASH_SELFTEST'::text AS evidence_set,
  'guard|hash_selftest'::text AS row_key,
  md5('') AS md5_empty_builtin,
  'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'::text AS sha256_empty_known_constant,
  EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc p
    WHERE p.proname = 'digest'
      AND pg_catalog.pg_get_function_identity_arguments(p.oid) = 'bytea, text'
  ) AS digest_bytea_text_present,
  current_setting('transaction_read_only')::text AS transaction_read_only,
  current_setting('statement_timeout')::text AS statement_timeout,
  current_setting('lock_timeout')::text AS lock_timeout,
  current_setting('idle_in_transaction_session_timeout')::text AS idle_in_transaction_session_timeout
;

-- === G02 ROLE ATTRIBUTES ===
-- Evidence: EV-ROLE-001, EV-ROLE-ATTR-001, EV-ROLES

SELECT
  'EV-ROLE-001'::text AS evidence_set,
  ('role|' || r.rolname)::text AS row_key,
  r.rolname::text AS role_name,
  r.rolcanlogin AS can_login,
  r.rolinherit AS inherit_attr,
  r.rolsuper AS is_superuser,
  r.rolcreaterole AS can_create_role,
  r.rolcreatedb AS can_create_db,
  r.rolreplication AS can_replicate,
  r.rolbypassrls AS bypass_rls,
  COALESCE(has_database_privilege(r.oid, current_database(), 'CONNECT'), false) AS has_connect,
  COALESCE(has_schema_privilege(r.oid, 'research', 'USAGE'), false) AS research_usage,
  COALESCE(has_schema_privilege(r.oid, 'research', 'CREATE'), false) AS research_create,
  r.oid AS role_oid_unstable_xref
FROM pg_catalog.pg_roles r
ORDER BY r.rolname COLLATE "C"
;

SELECT
  'EV-ROLE-ATTR-001'::text AS evidence_set,
  ('roleattr|' || r.rolname)::text AS row_key,
  r.rolname::text AS role_name,
  r.rolcanlogin AS can_login,
  r.rolinherit AS inherit_attr,
  r.rolsuper AS is_superuser,
  r.rolcreaterole AS can_create_role,
  r.rolcreatedb AS can_create_db,
  r.rolreplication AS can_replicate,
  r.rolbypassrls AS bypass_rls,
  r.rolconnlimit AS connection_limit,
  r.rolvaliduntil AS valid_until
FROM pg_catalog.pg_roles r
ORDER BY r.rolname COLLATE "C"
;

-- === G03 ROLE MEMBERSHIPS ===
-- Evidence: EV-ROLE-MEM-001, EV-MEMBERSHIPS

WITH RECURSIVE
direct AS (
  SELECT
    mr.rolname::text AS member_name,
    gr.rolname::text AS granted_name,
    m.member AS member_oid,
    m.roleid AS granted_oid,
    m.admin_option AS admin_option,
    ARRAY[m.member, m.roleid]::oid[] AS path_oids,
    ARRAY[mr.rolname::text, gr.rolname::text] AS path_names,
    1 AS depth,
    true AS is_direct
  FROM pg_catalog.pg_auth_members m
  JOIN pg_catalog.pg_roles mr ON mr.oid = m.member
  JOIN pg_catalog.pg_roles gr ON gr.oid = m.roleid
),
walk AS (
  SELECT * FROM direct
  UNION ALL
  SELECT
    w.member_name,
    gr.rolname::text AS granted_name,
    w.member_oid,
    m.roleid AS granted_oid,
    m.admin_option,
    (w.path_oids || m.roleid)::oid[] AS path_oids,
    (w.path_names || gr.rolname::text) AS path_names,
    w.depth + 1,
    false AS is_direct
  FROM walk w
  JOIN pg_catalog.pg_auth_members m ON m.member = w.granted_oid
  JOIN pg_catalog.pg_roles gr ON gr.oid = m.roleid
  WHERE NOT (m.roleid = ANY (w.path_oids))
    AND w.depth < 64
),
annot AS (
  SELECT
    w.*,
    mr.rolinherit AS member_inherit_attr,
    -- Automatic inherit path: member has INHERIT; every intermediate granted role
    -- on the path (excluding the terminal privilege holder) also has INHERIT.
    (
      mr.rolinherit
      AND NOT EXISTS (
        SELECT 1
        FROM unnest(w.path_names[1:greatest(array_length(w.path_names, 1) - 1, 1)]) WITH ORDINALITY AS u(name, ord)
        JOIN pg_catalog.pg_roles xr ON xr.rolname = u.name
        WHERE u.ord >= 2
          AND NOT xr.rolinherit
      )
    ) AS path_grants_inherited_authority,
    (
      (NOT mr.rolinherit)
      OR EXISTS (
        SELECT 1
        FROM unnest(w.path_names[1:greatest(array_length(w.path_names, 1) - 1, 1)]) WITH ORDINALITY AS u(name, ord)
        JOIN pg_catalog.pg_roles xr ON xr.rolname = u.name
        WHERE u.ord >= 2
          AND NOT xr.rolinherit
      )
    ) AS requires_explicit_set_role
  FROM walk w
  JOIN pg_catalog.pg_roles mr ON mr.oid = w.member_oid
)
SELECT
  'EV-ROLE-MEM-001'::text AS evidence_set,
  ('membership|' || a.member_name || '|' || a.granted_name || '|' || a.depth::text || '|'
     || array_to_string(a.path_names, '>'))::text AS row_key,
  a.member_name,
  a.granted_name,
  a.is_direct,
  a.depth,
  array_to_string(a.path_names, '>') AS membership_path,
  a.member_inherit_attr,
  a.path_grants_inherited_authority,
  a.requires_explicit_set_role,
  a.admin_option
FROM annot a
ORDER BY
  a.member_name COLLATE "C",
  a.granted_name COLLATE "C",
  a.depth,
  array_to_string(a.path_names, '>') COLLATE "C"
;

-- === G04 SCHEMAS ===
-- Evidence: EV-SCHEMA-001, EV-SCHEMAS, EV-SCHEMA-PRIVS

WITH schemas AS (
  SELECT
    n.oid AS schema_oid,
    n.nspname::text AS schema_name,
    r.rolname::text AS owner_name,
    n.nspowner AS owner_oid,
    n.nspacl AS raw_nspacl,
    COALESCE(n.nspacl, acldefault('n', n.nspowner)) AS effective_acl
  FROM pg_catalog.pg_namespace n
  JOIN pg_catalog.pg_roles r ON r.oid = n.nspowner
  WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
     OR n.nspname IN ('pg_catalog', 'information_schema')
     OR n.nspname IN ('research', 'research_crypto', 'research_test', 'public')
),
expanded AS (
  SELECT
    s.*,
    acl.grantor AS grantor_oid,
    acl.grantee AS grantee_oid,
    acl.privilege_type::text AS privilege_type,
    acl.is_grantable AS is_grantable,
    CASE WHEN acl.grantee = 0 THEN true ELSE false END AS is_public,
    CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
         ELSE COALESCE(gr.rolname::text, ('unknown_oid_' || acl.grantee::text))
    END AS grantee_name,
    CASE WHEN acl.grantor = 0 THEN 'PUBLIC'
         ELSE COALESCE(gor.rolname::text, ('unknown_oid_' || acl.grantor::text))
    END AS grantor_name
  FROM schemas s
  CROSS JOIN LATERAL aclexplode(s.effective_acl) AS acl
  LEFT JOIN pg_catalog.pg_roles gr ON gr.oid = acl.grantee AND acl.grantee <> 0
  LEFT JOIN pg_catalog.pg_roles gor ON gor.oid = acl.grantor AND acl.grantor <> 0
)
SELECT
  'EV-SCHEMA-001'::text AS evidence_set,
  ('schema|' || e.schema_name || '|' || e.grantee_name || '|' || e.privilege_type)::text AS row_key,
  e.schema_name,
  e.owner_name,
  e.raw_nspacl::text AS raw_acl_text,
  e.effective_acl::text AS expanded_defaulted_acl_text,
  e.grantor_name,
  e.grantee_name,
  e.is_public,
  e.privilege_type,
  e.is_grantable,
  (e.owner_oid = e.grantee_oid) AS grantee_is_owner,
  e.schema_oid AS schema_oid_unstable_xref
FROM expanded e
ORDER BY
  e.schema_name COLLATE "C",
  e.grantee_name COLLATE "C",
  e.privilege_type COLLATE "C",
  e.grantor_name COLLATE "C"
;

-- Effective USAGE/CREATE for every role × non-system schema of interest
SELECT
  'EV-SCHEMA-PRIVS'::text AS evidence_set,
  ('schemapriv|' || n.nspname || '|' || r.rolname || '|USAGE')::text AS row_key,
  n.nspname::text AS schema_name,
  r.rolname::text AS role_name,
  'USAGE'::text AS privilege_type,
  has_schema_privilege(r.oid, n.oid, 'USAGE') AS catalog_has_privilege,
  COALESCE(has_schema_privilege(r.oid, n.oid, 'CREATE'), false) AS catalog_has_create
FROM pg_catalog.pg_namespace n
CROSS JOIN pg_catalog.pg_roles r
WHERE n.nspname IN ('research', 'research_crypto', 'research_test', 'public')
   OR n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
ORDER BY n.nspname COLLATE "C", r.rolname COLLATE "C"
;

-- === G05 EXTENSIONS ===
-- Evidence: EV-EXTENSION-001, EV-EXTENSIONS

SELECT
  'EV-EXTENSION-001'::text AS evidence_set,
  ('extension|' || e.extname || '|' || n.nspname)::text AS row_key,
  e.extname::text AS extension_name,
  e.extversion::text AS extension_version,
  n.nspname::text AS extension_schema,
  COALESCE(r.rolname::text, '\N') AS owner_name,
  e.oid AS extension_oid_unstable_xref
FROM pg_catalog.pg_extension e
JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
LEFT JOIN pg_catalog.pg_roles r ON r.oid = (
  SELECT c.relowner
  FROM pg_catalog.pg_depend d
  JOIN pg_catalog.pg_class c ON c.oid = d.objid
  WHERE d.refobjid = e.oid
  ORDER BY c.relname COLLATE "C"
  LIMIT 1
)
ORDER BY e.extname COLLATE "C", n.nspname COLLATE "C"
;

-- === G06 FUNCTIONS (schema research) ===
-- Evidence: EV-FUNCTION-001, EV-FUNCTIONS, EV-HELPER-FUNCTIONS

WITH funcs AS (
  SELECT
    p.oid AS function_oid,
    n.nspname::text AS schema_name,
    p.proname::text AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid)::text AS identity_args,
    pg_catalog.pg_get_function_result(p.oid)::text AS result_type,
    r.rolname::text AS owner_name,
    l.lanname::text AS language_name,
    p.prosecdef AS is_security_definer,
    CASE p.provolatile
      WHEN 'i' THEN 'immutable'
      WHEN 's' THEN 'stable'
      WHEN 'v' THEN 'volatile'
      ELSE p.provolatile::text
    END AS volatility,
    CASE p.proparallel
      WHEN 's' THEN 'safe'
      WHEN 'r' THEN 'restricted'
      WHEN 'u' THEN 'unsafe'
      ELSE p.proparallel::text
    END AS parallel_classification,
    p.proacl AS raw_proacl,
    p.proowner AS owner_oid
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
  JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
  JOIN pg_catalog.pg_language l ON l.oid = p.prolang
  WHERE n.nspname = 'research'
),
pop AS (
  SELECT
    count(*)::bigint AS research_function_count,
    count(DISTINCT function_name)::bigint AS distinct_function_names,
    count(*) FILTER (
      WHERE function_name LIKE '\_r3%' ESCAPE '\'
         OR function_name LIKE '\_r4%' ESCAPE '\'
         OR function_name LIKE '\_r5a%' ESCAPE '\'
         OR function_name IN ('cleanup_test_fixture', 'record_pilot_usage_for_tests')
    )::bigint AS helper_name_matches
  FROM funcs
)
SELECT
  'EV-FUNCTION-001'::text AS evidence_set,
  ('function|' || f.schema_name || '|' || replace(replace(f.function_name, E'\\', E'\\\\'), '|', E'\\|')
     || '|' || replace(replace(f.identity_args, E'\\', E'\\\\'), '|', E'\\|'))::text AS row_key,
  f.function_oid AS function_oid_unstable_xref,
  f.schema_name,
  f.function_name,
  f.identity_args,
  f.result_type,
  f.owner_name,
  f.language_name,
  CASE WHEN f.is_security_definer THEN 'DEFINER' ELSE 'INVOKER' END AS security_mode,
  f.volatility,
  f.parallel_classification,
  f.raw_proacl::text AS raw_proacl_text,
  (f.raw_proacl IS NULL) AS proacl_is_null_defaults_apply,
  p.research_function_count,
  p.distinct_function_names,
  p.helper_name_matches
FROM funcs f
CROSS JOIN pop p
ORDER BY f.schema_name COLLATE "C", f.function_name COLLATE "C", f.identity_args COLLATE "C"
;

SELECT
  'EV-HELPER-FUNCTIONS'::text AS evidence_set,
  ('helper|' || n.nspname || '|' || p.proname || '|'
     || pg_catalog.pg_get_function_identity_arguments(p.oid))::text AS row_key,
  n.nspname::text AS schema_name,
  p.proname::text AS function_name,
  pg_catalog.pg_get_function_identity_arguments(p.oid)::text AS identity_args,
  r.rolname::text AS owner_name,
  p.proacl::text AS raw_proacl_text
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
WHERE p.proname LIKE '\_r3%' ESCAPE '\'
   OR p.proname LIKE '\_r4%' ESCAPE '\'
   OR p.proname LIKE '\_r5a%' ESCAPE '\'
   OR p.proname IN ('cleanup_test_fixture', 'record_pilot_usage_for_tests')
ORDER BY n.nspname COLLATE "C", p.proname COLLATE "C",
         pg_catalog.pg_get_function_identity_arguments(p.oid) COLLATE "C"
;

-- schema_version presence/columns only (no table data select; avoids hard parse dependency).
-- Max version value is run-specific after unique column resolution (see G20 protocol).
SELECT
  'EV-SCHEMA-VERSION'::text AS evidence_set,
  ('schema_version|research|catalog|' || COALESCE(a.attname::text, 'table'))::text AS row_key,
  true AS schema_version_table_present,
  c.relname::text AS table_name,
  a.attnum AS ordinal,
  a.attname::text AS column_name,
  pg_catalog.format_type(a.atttypid, a.atttypmod)::text AS data_type,
  'MAX_VERSION_VALUE_REQUIRES_RUN_SPECIFIC_SELECT_AFTER_UNIQUE_COLUMN_RESOLUTION'::text AS value_protocol,
  'BLOCKED_MISSING_CATALOG_DETAIL'::text AS if_column_not_unique
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attribute a
  ON a.attrelid = c.oid
 AND a.attnum > 0
 AND NOT a.attisdropped
WHERE n.nspname = 'research'
  AND c.relname = 'schema_version'
  AND c.relkind = 'r'
ORDER BY a.attnum NULLS FIRST
;

-- === G07 FUNCTION ACL EXPANSION ===
-- Evidence: EV-FUNCTION-ACL-001, EV-FUNCTION-ACL-002, EV-FUNCTION-ACLS, EV-FUNCTION-PUBLIC

WITH funcs AS (
  SELECT
    p.oid AS function_oid,
    n.nspname::text AS schema_name,
    p.proname::text AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid)::text AS identity_args,
    p.proowner AS owner_oid,
    r.rolname::text AS owner_name,
    p.proacl AS raw_proacl,
    COALESCE(p.proacl, acldefault('f', p.proowner)) AS effective_acl
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
  JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
  WHERE n.nspname = 'research'
),
expanded AS (
  SELECT
    f.*,
    acl.grantor AS grantor_oid,
    acl.grantee AS grantee_oid,
    acl.privilege_type::text AS privilege_type,
    acl.is_grantable AS is_grantable,
    CASE WHEN acl.grantee = 0 THEN true ELSE false END AS is_public,
    CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
         ELSE COALESCE(gr.rolname::text, ('unknown_oid_' || acl.grantee::text))
    END AS grantee_name,
    CASE WHEN acl.grantor = 0 THEN 'PUBLIC'
         ELSE COALESCE(gor.rolname::text, ('unknown_oid_' || acl.grantor::text))
    END AS grantor_name,
    (acl.grantee = f.owner_oid) AS grantee_is_owner
  FROM funcs f
  CROSS JOIN LATERAL aclexplode(f.effective_acl) AS acl
  LEFT JOIN pg_catalog.pg_roles gr ON gr.oid = acl.grantee AND acl.grantee <> 0
  LEFT JOIN pg_catalog.pg_roles gor ON gor.oid = acl.grantor AND acl.grantor <> 0
)
SELECT
  'EV-FUNCTION-ACL-001'::text AS evidence_set,
  ('function|' || e.schema_name || '|' || replace(replace(e.function_name, E'\\', E'\\\\'), '|', E'\\|')
     || '|' || replace(replace(e.identity_args, E'\\', E'\\\\'), '|', E'\\|')
     || '|' || e.grantee_name || '|' || e.privilege_type)::text AS row_key,
  e.schema_name,
  e.function_name,
  e.identity_args,
  e.owner_name,
  e.raw_proacl::text AS raw_proacl_text,
  e.grantor_name,
  e.grantee_name,
  e.is_public,
  e.privilege_type,
  e.is_grantable,
  e.grantee_is_owner,
  e.function_oid AS function_oid_unstable_xref
FROM expanded e
ORDER BY
  e.schema_name COLLATE "C",
  e.function_name COLLATE "C",
  e.identity_args COLLATE "C",
  e.grantee_name COLLATE "C",
  e.privilege_type COLLATE "C",
  e.grantor_name COLLATE "C"
;

SELECT
  'EV-FUNCTION-ACL-002'::text AS evidence_set,
  ('function_public_execute|' || e.schema_name || '|' || e.function_name || '|' || e.identity_args)::text AS row_key,
  e.schema_name,
  e.function_name,
  e.identity_args,
  e.owner_name,
  e.privilege_type,
  e.is_grantable,
  true AS public_has_execute
FROM (
  SELECT
    n.nspname::text AS schema_name,
    p.proname::text AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid)::text AS identity_args,
    r.rolname::text AS owner_name,
    acl.privilege_type::text AS privilege_type,
    acl.is_grantable
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
  JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
  CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) AS acl
  WHERE n.nspname = 'research'
    AND acl.grantee = 0
    AND acl.privilege_type = 'EXECUTE'
) e
ORDER BY e.function_name COLLATE "C", e.identity_args COLLATE "C"
;

-- === G08 EFFECTIVE FUNCTION EXECUTION ===
-- Evidence: EV-FUNCTION-EXEC-001, EV-FUNCTION-EFFECTIVE

WITH RECURSIVE
mem AS (
  SELECT
    m.member AS member_oid,
    m.roleid AS granted_oid,
    ARRAY[m.member, m.roleid]::oid[] AS path_oids,
    1 AS depth
  FROM pg_catalog.pg_auth_members m
  UNION ALL
  SELECT
    mem.member_oid,
    m.roleid,
    (mem.path_oids || m.roleid)::oid[],
    mem.depth + 1
  FROM mem
  JOIN pg_catalog.pg_auth_members m ON m.member = mem.granted_oid
  WHERE NOT (m.roleid = ANY (mem.path_oids))
    AND mem.depth < 64
),
funcs AS (
  SELECT
    p.oid AS function_oid,
    n.nspname::text AS schema_name,
    p.proname::text AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid)::text AS identity_args,
    p.proowner AS owner_oid,
    r.rolname::text AS owner_name,
    COALESCE(p.proacl, acldefault('f', p.proowner)) AS effective_acl
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
  JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
  WHERE n.nspname = 'research'
),
acl_rows AS (
  SELECT
    f.function_oid,
    f.schema_name,
    f.function_name,
    f.identity_args,
    f.owner_oid,
    f.owner_name,
    acl.grantee AS grantee_oid,
    acl.privilege_type::text AS privilege_type
  FROM funcs f
  CROSS JOIN LATERAL aclexplode(f.effective_acl) AS acl
  WHERE acl.privilege_type = 'EXECUTE'
),
role_base AS (
  SELECT r.oid AS role_oid, r.rolname::text AS role_name, r.rolsuper, r.rolinherit
  FROM pg_catalog.pg_roles r
),
paths AS (
  SELECT
    f.function_oid,
    f.schema_name,
    f.function_name,
    f.identity_args,
    f.owner_oid,
    f.owner_name,
    rb.role_oid,
    rb.role_name,
    rb.rolsuper,
    rb.rolinherit,
    EXISTS (
      SELECT 1 FROM acl_rows a
      WHERE a.function_oid = f.function_oid
        AND a.grantee_oid = rb.role_oid
    ) AS direct_execute,
    EXISTS (
      SELECT 1 FROM acl_rows a
      WHERE a.function_oid = f.function_oid
        AND a.grantee_oid = 0
    ) AS public_execute,
    EXISTS (
      SELECT 1
      FROM mem m
      JOIN acl_rows a ON a.grantee_oid = m.granted_oid
      JOIN pg_catalog.pg_roles mid ON mid.oid = m.member_oid
      WHERE m.member_oid = rb.role_oid
        AND a.function_oid = f.function_oid
        AND rb.rolinherit
        AND mid.rolinherit
    ) AS inherited_execute,
    EXISTS (
      SELECT 1
      FROM mem m
      JOIN acl_rows a ON a.grantee_oid = m.granted_oid
      WHERE m.member_oid = rb.role_oid
        AND a.function_oid = f.function_oid
    )
    AND NOT (
      EXISTS (
        SELECT 1 FROM acl_rows a
        WHERE a.function_oid = f.function_oid
          AND a.grantee_oid = rb.role_oid
      )
      OR (
        EXISTS (
          SELECT 1
          FROM mem m
          JOIN acl_rows a ON a.grantee_oid = m.granted_oid
          WHERE m.member_oid = rb.role_oid
            AND a.function_oid = f.function_oid
            AND rb.rolinherit
        )
      )
    ) AS set_role_only_execute,
    (rb.role_oid = f.owner_oid) AS owner_derived,
    rb.rolsuper AS superuser_derived,
    COALESCE(has_schema_privilege(rb.role_oid, 'research', 'USAGE'), false) AS schema_usage,
    has_function_privilege(rb.role_oid, f.function_oid, 'EXECUTE') AS catalog_has_execute
  FROM funcs f
  CROSS JOIN role_base rb
)
SELECT
  'EV-FUNCTION-EXEC-001'::text AS evidence_set,
  ('function|' || p.schema_name || '|' || replace(replace(p.function_name, E'\\', E'\\\\'), '|', E'\\|')
     || '|' || replace(replace(p.identity_args, E'\\', E'\\\\'), '|', E'\\|')
     || '|' || p.role_name || '|EXECUTE')::text AS row_key,
  p.schema_name,
  p.function_name,
  p.identity_args,
  p.role_name,
  p.direct_execute,
  p.public_execute,
  p.inherited_execute,
  p.set_role_only_execute,
  p.owner_derived,
  p.superuser_derived,
  p.schema_usage,
  -- Final exercisable without SET ROLE: schema USAGE (or superuser) and a usable grant path
  (
    (p.superuser_derived OR p.schema_usage)
    AND (
      p.superuser_derived
      OR p.owner_derived
      OR p.direct_execute
      OR p.public_execute
      OR p.inherited_execute
    )
  ) AS final_exercisable_execute,
  p.catalog_has_execute,
  p.function_oid AS function_oid_unstable_xref
FROM paths p
ORDER BY
  p.function_name COLLATE "C",
  p.identity_args COLLATE "C",
  p.role_name COLLATE "C"
;

-- === G09 BASE TABLES ===
-- Evidence: EV-TABLE-001, EV-TABLES

SELECT
  'EV-TABLE-001'::text AS evidence_set,
  ('table|' || n.nspname || '|' || c.relname)::text AS row_key,
  c.oid AS table_oid_unstable_xref,
  n.nspname::text AS schema_name,
  c.relname::text AS table_name,
  r.rolname::text AS owner_name,
  CASE c.relpersistence
    WHEN 'p' THEN 'permanent'
    WHEN 'u' THEN 'unlogged'
    WHEN 't' THEN 'temporary'
    ELSE c.relpersistence::text
  END AS persistence,
  c.relrowsecurity AS rls_enabled,
  c.relforcerowsecurity AS rls_forced,
  c.relacl::text AS raw_relacl_text,
  (c.relacl IS NULL) AS relacl_is_null_defaults_apply
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
WHERE n.nspname = 'research'
  AND c.relkind = 'r'
ORDER BY c.relname COLLATE "C"
;

-- === G10 RELATION ACL EXPANSION ===
-- Evidence: EV-TABLE-ACL-001, EV-TABLE-ACLS

WITH tables AS (
  SELECT
    c.oid AS table_oid,
    n.nspname::text AS schema_name,
    c.relname::text AS table_name,
    c.relowner AS owner_oid,
    r.rolname::text AS owner_name,
    c.relacl AS raw_relacl,
    COALESCE(c.relacl, acldefault('r', c.relowner)) AS effective_acl
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
  WHERE n.nspname = 'research'
    AND c.relkind = 'r'
),
expanded AS (
  SELECT
    t.*,
    acl.grantor AS grantor_oid,
    acl.grantee AS grantee_oid,
    acl.privilege_type::text AS privilege_type,
    acl.is_grantable AS is_grantable,
    CASE WHEN acl.grantee = 0 THEN true ELSE false END AS is_public,
    CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
         ELSE COALESCE(gr.rolname::text, ('unknown_oid_' || acl.grantee::text))
    END AS grantee_name,
    CASE WHEN acl.grantor = 0 THEN 'PUBLIC'
         ELSE COALESCE(gor.rolname::text, ('unknown_oid_' || acl.grantor::text))
    END AS grantor_name,
    (acl.grantee = t.owner_oid) AS grantee_is_owner
  FROM tables t
  CROSS JOIN LATERAL aclexplode(t.effective_acl) AS acl
  LEFT JOIN pg_catalog.pg_roles gr ON gr.oid = acl.grantee AND acl.grantee <> 0
  LEFT JOIN pg_catalog.pg_roles gor ON gor.oid = acl.grantor AND acl.grantor <> 0
)
SELECT
  'EV-TABLE-ACL-001'::text AS evidence_set,
  ('table|' || e.schema_name || '|' || e.table_name || '|' || e.grantee_name || '|' || e.privilege_type)::text AS row_key,
  e.schema_name,
  e.table_name,
  e.owner_name,
  e.raw_relacl::text AS raw_relacl_text,
  e.grantor_name,
  e.grantee_name,
  e.is_public,
  e.privilege_type,
  e.is_grantable,
  e.grantee_is_owner,
  e.table_oid AS table_oid_unstable_xref
FROM expanded e
ORDER BY
  e.table_name COLLATE "C",
  e.grantee_name COLLATE "C",
  e.privilege_type COLLATE "C",
  e.grantor_name COLLATE "C"
;

-- === G11 EFFECTIVE TABLE PRIVILEGES ===
-- Evidence: EV-TABLE-WRITE-001, EV-TABLE-WRITE-002, EV-TABLE-WRITES

WITH RECURSIVE
mem AS (
  SELECT m.member AS member_oid, m.roleid AS granted_oid,
         ARRAY[m.member, m.roleid]::oid[] AS path_oids, 1 AS depth
  FROM pg_catalog.pg_auth_members m
  UNION ALL
  SELECT mem.member_oid, m.roleid, (mem.path_oids || m.roleid)::oid[], mem.depth + 1
  FROM mem
  JOIN pg_catalog.pg_auth_members m ON m.member = mem.granted_oid
  WHERE NOT (m.roleid = ANY (mem.path_oids))
    AND mem.depth < 64
),
tables AS (
  SELECT
    c.oid AS table_oid,
    n.nspname::text AS schema_name,
    c.relname::text AS table_name,
    c.relowner AS owner_oid,
    COALESCE(c.relacl, acldefault('r', c.relowner)) AS effective_acl
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'research'
    AND c.relkind = 'r'
),
privs AS (
  SELECT unnest(ARRAY[
    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
  ])::text AS privilege_type
),
acl_rows AS (
  SELECT
    t.table_oid,
    t.schema_name,
    t.table_name,
    t.owner_oid,
    acl.grantee AS grantee_oid,
    acl.privilege_type::text AS privilege_type
  FROM tables t
  CROSS JOIN LATERAL aclexplode(t.effective_acl) AS acl
),
crosswalk AS (
  SELECT
    t.table_oid,
    t.schema_name,
    t.table_name,
    t.owner_oid,
    r.oid AS role_oid,
    r.rolname::text AS role_name,
    r.rolsuper,
    r.rolinherit,
    p.privilege_type,
    EXISTS (
      SELECT 1 FROM acl_rows a
      WHERE a.table_oid = t.table_oid
        AND a.grantee_oid = r.oid
        AND a.privilege_type = p.privilege_type
    ) AS direct_grant,
    EXISTS (
      SELECT 1 FROM acl_rows a
      WHERE a.table_oid = t.table_oid
        AND a.grantee_oid = 0
        AND a.privilege_type = p.privilege_type
    ) AS public_grant,
    EXISTS (
      SELECT 1
      FROM mem m
      JOIN acl_rows a ON a.grantee_oid = m.granted_oid AND a.privilege_type = p.privilege_type
      WHERE m.member_oid = r.oid
        AND a.table_oid = t.table_oid
        AND r.rolinherit
    ) AS inherited_grant,
    EXISTS (
      SELECT 1
      FROM mem m
      JOIN acl_rows a ON a.grantee_oid = m.granted_oid AND a.privilege_type = p.privilege_type
      WHERE m.member_oid = r.oid
        AND a.table_oid = t.table_oid
    )
    AND NOT EXISTS (
      SELECT 1 FROM acl_rows a
      WHERE a.table_oid = t.table_oid
        AND a.grantee_oid = r.oid
        AND a.privilege_type = p.privilege_type
    )
    AND NOT (
      r.rolinherit
      AND EXISTS (
        SELECT 1
        FROM mem m
        JOIN acl_rows a ON a.grantee_oid = m.granted_oid AND a.privilege_type = p.privilege_type
        WHERE m.member_oid = r.oid
          AND a.table_oid = t.table_oid
      )
    ) AS set_role_only_grant,
    (r.oid = t.owner_oid) AS owner_derived,
    r.rolsuper AS superuser_derived,
    COALESCE(has_schema_privilege(r.oid, 'research', 'USAGE'), false) AS schema_usage,
    has_table_privilege(r.oid, t.table_oid, p.privilege_type) AS catalog_has_privilege
  FROM tables t
  CROSS JOIN pg_catalog.pg_roles r
  CROSS JOIN privs p
)
SELECT
  'EV-TABLE-WRITE-001'::text AS evidence_set,
  ('table|' || c.schema_name || '|' || c.table_name || '|' || c.role_name || '|' || c.privilege_type)::text AS row_key,
  c.schema_name,
  c.table_name,
  c.role_name,
  c.privilege_type,
  c.direct_grant,
  c.public_grant,
  c.inherited_grant,
  c.set_role_only_grant,
  c.owner_derived,
  c.superuser_derived,
  c.schema_usage,
  (
    (c.superuser_derived OR c.schema_usage)
    AND (
      c.superuser_derived
      OR c.owner_derived
      OR c.direct_grant
      OR c.public_grant
      OR c.inherited_grant
    )
  ) AS final_exercisable,
  c.catalog_has_privilege,
  c.table_oid AS table_oid_unstable_xref
FROM crosswalk c
ORDER BY
  c.table_name COLLATE "C",
  c.role_name COLLATE "C",
  c.privilege_type COLLATE "C"
;

-- Revision 7 assertion: research_app DELETE = Y on every research base table
WITH tables AS (
  SELECT c.oid AS table_oid, c.relname::text AS table_name,
         COALESCE(c.relacl, acldefault('r', c.relowner)) AS effective_acl,
         c.relowner AS owner_oid
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'research' AND c.relkind = 'r'
),
app AS (
  SELECT oid AS role_oid FROM pg_catalog.pg_roles WHERE rolname = 'research_app'
),
eval AS (
  SELECT
    t.table_name,
    (SELECT count(*) FROM app) = 1 AS research_app_present,
    EXISTS (
      SELECT 1
      FROM tables t2
      CROSS JOIN LATERAL aclexplode(t2.effective_acl) acl
      WHERE t2.table_oid = t.table_oid
        AND acl.privilege_type = 'DELETE'
        AND acl.grantee = (SELECT role_oid FROM app)
    ) AS direct_delete,
    has_table_privilege(
      (SELECT role_oid FROM app),
      t.table_oid,
      'DELETE'
    ) AS catalog_has_delete
  FROM tables t
  WHERE EXISTS (SELECT 1 FROM app)
)
SELECT
  'EV-TABLE-WRITE-002'::text AS evidence_set,
  ('rev7_delete|' || e.table_name || '|research_app')::text AS row_key,
  'research_app DELETE = Y on every table'::text AS revision7_assertion,
  e.table_name,
  e.research_app_present,
  e.direct_delete,
  e.catalog_has_delete,
  CASE
    WHEN NOT e.research_app_present THEN 'BLOCKED_MISSING_CATALOG_DETAIL'
    WHEN e.direct_delete THEN 'CONFIRMS'
    ELSE 'CONTRADICTS'
  END AS assertion_result,
  CASE
    WHEN e.direct_delete THEN 'direct ACL EXECUTE-path N/A; direct DELETE grant present for research_app'
    ELSE 'direct DELETE grant absent for research_app on this table'
  END AS evidence_note
FROM eval e
ORDER BY e.table_name COLLATE "C"
;

-- If research_app role is absent, emit a single blocker row
SELECT
  'EV-TABLE-WRITE-002'::text AS evidence_set,
  'rev7_delete|ALL|research_app'::text AS row_key,
  'research_app DELETE = Y on every table'::text AS revision7_assertion,
  'BLOCKED_MISSING_CATALOG_DETAIL'::text AS assertion_result,
  'role research_app not present'::text AS evidence_note
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'research_app')
;

-- === G12 COLUMN ACLS ===
-- Evidence: EV-COLUMN-ACL-001, EV-COLUMN-EFF-001, EV-COLUMNS, EV-COLUMN-ACLS, EV-COLUMN-EFFECTIVE
-- NOTE: Do NOT apply acldefault to attacl. Null attacl = no column-specific ACL.

WITH cols AS (
  SELECT
    c.oid AS table_oid,
    n.nspname::text AS schema_name,
    c.relname::text AS table_name,
    a.attnum AS ordinal,
    a.attname::text AS column_name,
    a.attacl AS raw_attacl,
    (a.attacl IS NULL) AS explicit_column_acl_absent,
    c.relowner AS owner_oid
  FROM pg_catalog.pg_attribute a
  JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'research'
    AND c.relkind = 'r'
    AND a.attnum > 0
    AND NOT a.attisdropped
),
expanded AS (
  SELECT
    cols.*,
    acl.grantor AS grantor_oid,
    acl.grantee AS grantee_oid,
    acl.privilege_type::text AS privilege_type,
    acl.is_grantable AS is_grantable,
    CASE WHEN acl.grantee = 0 THEN true ELSE false END AS is_public,
    CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
         ELSE COALESCE(gr.rolname::text, ('unknown_oid_' || acl.grantee::text))
    END AS grantee_name
  FROM cols
  LEFT JOIN LATERAL aclexplode(cols.raw_attacl) AS acl ON cols.raw_attacl IS NOT NULL
  LEFT JOIN pg_catalog.pg_roles gr ON gr.oid = acl.grantee AND acl.grantee <> 0
)
SELECT
  'EV-COLUMN-ACL-001'::text AS evidence_set,
  ('column|' || e.schema_name || '|' || e.table_name || '|' || e.ordinal::text || '|'
     || e.column_name || '|' || COALESCE(e.grantee_name, '\N') || '|'
     || COALESCE(e.privilege_type, '\N'))::text AS row_key,
  e.schema_name,
  e.table_name,
  e.ordinal,
  e.column_name,
  e.raw_attacl::text AS raw_attacl_text,
  e.explicit_column_acl_absent,
  e.grantee_name,
  e.is_public,
  e.privilege_type,
  e.is_grantable,
  e.table_oid AS table_oid_unstable_xref
FROM expanded e
ORDER BY
  e.table_name COLLATE "C",
  e.ordinal,
  e.column_name COLLATE "C",
  COALESCE(e.grantee_name, '') COLLATE "C",
  COALESCE(e.privilege_type, '') COLLATE "C"
;

WITH cols AS (
  SELECT
    c.oid AS table_oid,
    n.nspname::text AS schema_name,
    c.relname::text AS table_name,
    a.attnum AS ordinal,
    a.attname::text AS column_name,
    a.attacl AS raw_attacl,
    format('%I.%I', n.nspname, c.relname)::text AS qualified_table
  FROM pg_catalog.pg_attribute a
  JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'research'
    AND c.relkind = 'r'
    AND a.attnum > 0
    AND NOT a.attisdropped
),
privs AS (
  SELECT unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'REFERENCES'])::text AS privilege_type
)
SELECT
  'EV-COLUMN-EFF-001'::text AS evidence_set,
  ('column|' || cols.schema_name || '|' || cols.table_name || '|' || cols.ordinal::text || '|'
     || cols.column_name || '|' || r.rolname || '|' || p.privilege_type)::text AS row_key,
  cols.schema_name,
  cols.table_name,
  cols.ordinal,
  cols.column_name,
  r.rolname::text AS role_name,
  p.privilege_type,
  (cols.raw_attacl IS NULL) AS explicit_column_acl_absent,
  has_column_privilege(r.oid, cols.table_oid, cols.column_name, p.privilege_type) AS catalog_has_column_privilege,
  has_table_privilege(r.oid, cols.table_oid, p.privilege_type) AS catalog_has_table_privilege,
  COALESCE(has_schema_privilege(r.oid, 'research', 'USAGE'), false) AS schema_usage
FROM cols
CROSS JOIN pg_catalog.pg_roles r
CROSS JOIN privs p
ORDER BY
  cols.table_name COLLATE "C",
  cols.ordinal,
  r.rolname COLLATE "C",
  p.privilege_type COLLATE "C"
;

-- === G13 VIEWS + MATVIEWS ===
-- Evidence: EV-VIEW-001, EV-VIEWS

SELECT
  'EV-VIEW-001'::text AS evidence_set,
  ('view|' || n.nspname || '|' || c.relname || '|' || c.relkind::text)::text AS row_key,
  n.nspname::text AS schema_name,
  c.relname::text AS view_name,
  CASE c.relkind WHEN 'v' THEN 'view' WHEN 'm' THEN 'materialized_view' ELSE c.relkind::text END AS view_kind,
  r.rolname::text AS owner_name,
  md5(COALESCE(pg_catalog.pg_get_viewdef(c.oid, true), '')) AS definition_md5,
  length(COALESCE(pg_catalog.pg_get_viewdef(c.oid, true), '')) AS definition_length,
  c.relacl::text AS raw_relacl_text,
  COALESCE(c.relacl, acldefault('r', c.relowner))::text AS defaulted_acl_text,
  c.oid AS view_oid_unstable_xref
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
WHERE n.nspname = 'research'
  AND c.relkind IN ('v', 'm')
ORDER BY c.relkind COLLATE "C", c.relname COLLATE "C"
;

-- === G14 SEQUENCES ===
-- Evidence: EV-SEQUENCE-001, EV-SEQUENCES

WITH seqs AS (
  SELECT
    c.oid AS sequence_oid,
    n.nspname::text AS schema_name,
    c.relname::text AS sequence_name,
    c.relowner AS owner_oid,
    r.rolname::text AS owner_name,
    c.relacl AS raw_relacl,
    COALESCE(c.relacl, acldefault('s', c.relowner)) AS effective_acl
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
  WHERE n.nspname = 'research'
    AND c.relkind = 'S'
),
expanded AS (
  SELECT
    s.*,
    acl.privilege_type::text AS privilege_type,
    acl.is_grantable,
    CASE WHEN acl.grantee = 0 THEN true ELSE false END AS is_public,
    CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
         ELSE COALESCE(gr.rolname::text, ('unknown_oid_' || acl.grantee::text))
    END AS grantee_name,
    CASE WHEN acl.grantor = 0 THEN 'PUBLIC'
         ELSE COALESCE(gor.rolname::text, ('unknown_oid_' || acl.grantor::text))
    END AS grantor_name
  FROM seqs s
  CROSS JOIN LATERAL aclexplode(s.effective_acl) AS acl
  LEFT JOIN pg_catalog.pg_roles gr ON gr.oid = acl.grantee AND acl.grantee <> 0
  LEFT JOIN pg_catalog.pg_roles gor ON gor.oid = acl.grantor AND acl.grantor <> 0
)
SELECT
  'EV-SEQUENCE-001'::text AS evidence_set,
  ('sequence|' || e.schema_name || '|' || e.sequence_name || '|' || e.grantee_name || '|' || e.privilege_type)::text AS row_key,
  e.schema_name,
  e.sequence_name,
  e.owner_name,
  e.raw_relacl::text AS raw_relacl_text,
  e.effective_acl::text AS defaulted_acl_text,
  e.grantor_name,
  e.grantee_name,
  e.is_public,
  e.privilege_type,
  e.is_grantable,
  e.sequence_oid AS sequence_oid_unstable_xref
FROM expanded e
ORDER BY
  e.sequence_name COLLATE "C",
  e.grantee_name COLLATE "C",
  e.privilege_type COLLATE "C"
;

-- === G15 TRIGGERS ===
-- Evidence: EV-TRIGGER-001, EV-TRIGGERS

SELECT
  'EV-TRIGGER-001'::text AS evidence_set,
  ('trigger|' || n.nspname || '|' || c.relname || '|' || t.tgname)::text AS row_key,
  n.nspname::text AS schema_name,
  c.relname::text AS table_name,
  t.tgname::text AS trigger_name,
  CASE t.tgenabled
    WHEN 'O' THEN 'origin'
    WHEN 'D' THEN 'disabled'
    WHEN 'R' THEN 'replica'
    WHEN 'A' THEN 'always'
    ELSE t.tgenabled::text
  END AS enabled_state,
  pg_catalog.pg_get_triggerdef(t.oid, true)::text AS trigger_def,
  np.nspname::text AS function_schema,
  p.proname::text AS function_name,
  pg_catalog.pg_get_function_identity_arguments(p.oid)::text AS function_identity_args,
  t.tgisinternal AS is_internal,
  t.oid AS trigger_oid_unstable_xref
FROM pg_catalog.pg_trigger t
JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
JOIN pg_catalog.pg_namespace np ON np.oid = p.pronamespace
WHERE n.nspname = 'research'
ORDER BY c.relname COLLATE "C", t.tgname COLLATE "C"
;

-- === G16 RLS POLICIES ===
-- Evidence: EV-RLS-001, EV-RLS

SELECT
  'EV-RLS-001'::text AS evidence_set,
  ('rls|' || n.nspname || '|' || c.relname || '|' || p.polname)::text AS row_key,
  n.nspname::text AS schema_name,
  c.relname::text AS table_name,
  p.polname::text AS policy_name,
  CASE p.polcmd
    WHEN 'r' THEN 'SELECT'
    WHEN 'a' THEN 'INSERT'
    WHEN 'w' THEN 'UPDATE'
    WHEN 'd' THEN 'DELETE'
    WHEN '*' THEN 'ALL'
    ELSE p.polcmd::text
  END AS policy_command,
  CASE WHEN p.polpermissive THEN 'PERMISSIVE' ELSE 'RESTRICTIVE' END AS permissive_or_restrictive,
  COALESCE(
    (
      SELECT string_agg(pr.rolname::text, ',' ORDER BY pr.rolname COLLATE "C")
      FROM pg_catalog.pg_roles pr
      WHERE pr.oid = ANY (p.polroles)
    ),
    CASE WHEN p.polroles = '{0}'::oid[] OR p.polroles = '{}'::oid[] THEN 'PUBLIC' ELSE '' END
  ) AS policy_roles,
  pg_catalog.pg_get_expr(p.polqual, p.polrelid)::text AS using_expression,
  pg_catalog.pg_get_expr(p.polwithcheck, p.polrelid)::text AS with_check_expression
FROM pg_catalog.pg_policy p
JOIN pg_catalog.pg_class c ON c.oid = p.polrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'research'
ORDER BY c.relname COLLATE "C", p.polname COLLATE "C"
;

-- === G17 CONSTRAINTS AND INDEXES ===
-- Evidence: EV-CONSTRAINT-001, EV-INDEX-001, EV-CONSTRAINTS, EV-INDEXES

SELECT
  'EV-CONSTRAINT-001'::text AS evidence_set,
  ('constraint|' || n.nspname || '|' || c.relname || '|' || con.conname)::text AS row_key,
  n.nspname::text AS schema_name,
  c.relname::text AS table_name,
  con.conname::text AS constraint_name,
  CASE con.contype
    WHEN 'p' THEN 'PRIMARY KEY'
    WHEN 'u' THEN 'UNIQUE'
    WHEN 'f' THEN 'FOREIGN KEY'
    WHEN 'c' THEN 'CHECK'
    WHEN 'x' THEN 'EXCLUDE'
    WHEN 't' THEN 'TRIGGER'
    WHEN 'n' THEN 'NOT NULL'
    ELSE con.contype::text
  END AS constraint_type,
  pg_catalog.pg_get_constraintdef(con.oid, true)::text AS constraint_def,
  con.convalidated AS is_validated,
  con.condeferrable AS is_deferrable,
  con.condeferred AS is_deferred,
  con.conislocal AS is_local
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'research'
  AND con.conrelid <> 0
ORDER BY c.relname COLLATE "C", con.conname COLLATE "C"
;

SELECT
  'EV-INDEX-001'::text AS evidence_set,
  ('index|' || n.nspname || '|' || c.relname || '|' || i.relname)::text AS row_key,
  n.nspname::text AS schema_name,
  c.relname::text AS table_name,
  i.relname::text AS index_name,
  ix.indisunique AS is_unique,
  ix.indisprimary AS is_primary,
  ix.indisvalid AS is_valid,
  ix.indisready AS is_ready,
  ix.indislive AS is_live,
  pg_catalog.pg_get_indexdef(ix.indexrelid)::text AS index_def,
  pg_catalog.pg_get_expr(ix.indpred, ix.indrelid)::text AS index_predicate
FROM pg_catalog.pg_index ix
JOIN pg_catalog.pg_class c ON c.oid = ix.indrelid
JOIN pg_catalog.pg_class i ON i.oid = ix.indexrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'research'
ORDER BY c.relname COLLATE "C", i.relname COLLATE "C"
;

-- === G18 DEFAULT PRIVILEGES + PROVENANCE ===
-- Evidence: EV-DEFACL-001, EV-DEFACL-002, EV-DEFAULT-PRIVS

WITH defacl AS (
  SELECT
    d.oid AS defacl_oid,
    r.rolname::text AS target_owner_name,
    d.defaclrole AS target_owner_oid,
    COALESCE(n.nspname::text, '\N') AS schema_name,
    d.defaclnamespace AS schema_oid,
    CASE d.defaclobjtype
      WHEN 'r' THEN 'table'
      WHEN 'S' THEN 'sequence'
      WHEN 'f' THEN 'function'
      WHEN 'T' THEN 'type'
      WHEN 'n' THEN 'schema'
      ELSE d.defaclobjtype::text
    END AS object_type,
    d.defaclacl AS raw_defaclacl
  FROM pg_catalog.pg_default_acl d
  JOIN pg_catalog.pg_roles r ON r.oid = d.defaclrole
  LEFT JOIN pg_catalog.pg_namespace n ON n.oid = d.defaclnamespace
),
expanded AS (
  SELECT
    d.*,
    acl.privilege_type::text AS privilege_type,
    acl.is_grantable,
    CASE WHEN acl.grantee = 0 THEN true ELSE false END AS is_public,
    CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
         ELSE COALESCE(gr.rolname::text, ('unknown_oid_' || acl.grantee::text))
    END AS grantee_name,
    CASE WHEN acl.grantor = 0 THEN 'PUBLIC'
         ELSE COALESCE(gor.rolname::text, ('unknown_oid_' || acl.grantor::text))
    END AS grantor_name
  FROM defacl d
  CROSS JOIN LATERAL aclexplode(d.raw_defaclacl) AS acl
  LEFT JOIN pg_catalog.pg_roles gr ON gr.oid = acl.grantee AND acl.grantee <> 0
  LEFT JOIN pg_catalog.pg_roles gor ON gor.oid = acl.grantor AND acl.grantor <> 0
)
SELECT
  'EV-DEFACL-001'::text AS evidence_set,
  ('default_acl|' || e.target_owner_name || '|' || e.schema_name || '|' || e.object_type
     || '|' || e.grantee_name || '|' || e.privilege_type)::text AS row_key,
  e.target_owner_name,
  e.schema_name,
  e.object_type,
  e.grantor_name,
  e.grantee_name,
  e.is_public,
  e.privilege_type,
  e.is_grantable,
  e.raw_defaclacl::text AS raw_defacl_text
FROM expanded e
ORDER BY
  e.target_owner_name COLLATE "C",
  e.schema_name COLLATE "C",
  e.object_type COLLATE "C",
  e.grantee_name COLLATE "C",
  e.privilege_type COLLATE "C"
;

WITH tables AS (
  SELECT
    c.oid AS table_oid,
    n.nspname::text AS schema_name,
    c.relname::text AS table_name,
    c.relowner AS owner_oid,
    r.rolname::text AS owner_name
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
  WHERE n.nspname = 'research'
    AND c.relkind = 'r'
),
matching AS (
  SELECT
    t.table_name,
    t.owner_name,
    count(d.oid) AS matching_defacl_rows
  FROM tables t
  LEFT JOIN pg_catalog.pg_default_acl d
    ON d.defaclrole = t.owner_oid
   AND d.defaclobjtype = 'r'
   AND (d.defaclnamespace = 0 OR d.defaclnamespace = (
          SELECT n2.oid FROM pg_catalog.pg_namespace n2 WHERE n2.nspname = 'research'
        ))
  GROUP BY t.table_name, t.owner_name
)
SELECT
  'EV-DEFACL-002'::text AS evidence_set,
  ('defacl_prov|' || m.table_name || '|' || m.owner_name)::text AS row_key,
  m.table_name,
  m.owner_name,
  m.matching_defacl_rows,
  CASE
    WHEN m.matching_defacl_rows = 1 THEN 'matching_owner_default_privilege'
    WHEN m.matching_defacl_rows = 0 THEN 'no_matching_owner_default_privilege'
    ELSE 'ambiguous_provenance'
  END AS provenance_class
FROM matching m
ORDER BY m.table_name COLLATE "C"
;

-- === G19 APPLICATION-BASELINE DISCOVERY (names/metadata only; no secret values) ===
-- Evidence: EV-APP-DISCOVERY-001, EV-SAFETY-BASELINE (candidates), EV-RESERVATION-STATE (candidates),
--           EV-CUTOVER-STATE (candidates)

WITH research_tables AS (
  SELECT
    c.oid AS table_oid,
    c.relname::text AS table_name
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'research'
    AND c.relkind = 'r'
),
cols AS (
  SELECT
    t.table_name,
    a.attnum AS ordinal,
    a.attname::text AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod)::text AS data_type
  FROM research_tables t
  JOIN pg_catalog.pg_attribute a ON a.attrelid = t.table_oid
  WHERE a.attnum > 0
    AND NOT a.attisdropped
),
classified AS (
  SELECT
    t.table_name,
    CASE
      WHEN t.table_name ~* '(^|_)providers?($|_)' THEN 'providers'
      WHEN t.table_name ~* '(^|_)models?($|_)' THEN 'models'
      WHEN t.table_name ~* 'credential' THEN 'credentials'
      WHEN t.table_name ~* 'proposal' THEN 'proposals'
      WHEN t.table_name ~* 'authorization' THEN 'authorizations'
      WHEN t.table_name ~* 'workflow' THEN 'workflows'
      WHEN t.table_name ~* 'envelope' THEN 'envelopes'
      WHEN t.table_name ~* '(^|_)usage($|_)|paid_cost|token_usage' THEN 'usage'
      WHEN t.table_name ~* 'spend|budget' THEN 'spend'
      WHEN t.table_name ~* 'reservation' THEN 'reservations'
      WHEN t.table_name ~* 'cutover' AND t.table_name ~* 'checkpoint' THEN 'cutover_checkpoints'
      WHEN t.table_name ~* 'cutover' THEN 'cutover_state'
      ELSE 'other'
    END AS discovery_class
  FROM research_tables t
),
secret_cols AS (
  SELECT
    c.table_name,
    c.ordinal,
    c.column_name,
    c.data_type,
    true AS secret_risk_name_match,
    CASE
      WHEN lower(c.column_name) LIKE '%secret%' THEN 'secret'
      WHEN lower(c.column_name) LIKE '%token%' THEN 'token'
      WHEN lower(c.column_name) LIKE '%api_key%' OR lower(c.column_name) LIKE '%apikey%' THEN 'api_key'
      WHEN lower(c.column_name) LIKE '%password%' THEN 'password'
      WHEN lower(c.column_name) LIKE '%private_key%' THEN 'private_key'
      WHEN lower(c.column_name) LIKE '%cipher%' THEN 'cipher'
      WHEN lower(c.column_name) LIKE '%encrypted%' THEN 'encrypted'
      WHEN lower(c.column_name) LIKE '%plaintext%' THEN 'plaintext'
      ELSE 'other_pattern'
    END AS matched_pattern
  FROM cols c
  WHERE lower(c.column_name) LIKE '%secret%'
     OR lower(c.column_name) LIKE '%token%'
     OR lower(c.column_name) LIKE '%api_key%'
     OR lower(c.column_name) LIKE '%apikey%'
     OR lower(c.column_name) LIKE '%password%'
     OR lower(c.column_name) LIKE '%private_key%'
     OR lower(c.column_name) LIKE '%cipher%'
     OR lower(c.column_name) LIKE '%encrypted%'
     OR lower(c.column_name) LIKE '%plaintext%'
)
SELECT
  'EV-APP-DISCOVERY-001'::text AS evidence_set,
  ('appdisc|table|' || cl.discovery_class || '|' || cl.table_name)::text AS row_key,
  'table_candidate'::text AS discovery_kind,
  cl.discovery_class,
  cl.table_name,
  NULL::integer AS ordinal,
  NULL::text AS column_name,
  NULL::text AS data_type,
  false AS secret_risk_name_match,
  NULL::text AS matched_pattern
FROM classified cl
WHERE cl.discovery_class <> 'other'
UNION ALL
SELECT
  'EV-APP-DISCOVERY-001'::text,
  ('appdisc|column|' || s.table_name || '|' || s.ordinal::text || '|' || s.column_name)::text,
  'secret_risk_column'::text,
  'secret_risk'::text,
  s.table_name,
  s.ordinal,
  s.column_name,
  s.data_type,
  s.secret_risk_name_match,
  s.matched_pattern
FROM secret_cols s
UNION ALL
SELECT
  'EV-APP-DISCOVERY-001'::text,
  ('appdisc|column_inventory|' || c.table_name || '|' || c.ordinal::text || '|' || c.column_name)::text,
  'column_inventory'::text,
  COALESCE(cl.discovery_class, 'other'),
  c.table_name,
  c.ordinal,
  c.column_name,
  c.data_type,
  EXISTS (
    SELECT 1 FROM secret_cols s
    WHERE s.table_name = c.table_name AND s.column_name = c.column_name
  ) AS secret_risk_name_match,
  (
    SELECT s.matched_pattern FROM secret_cols s
    WHERE s.table_name = c.table_name AND s.column_name = c.column_name
    LIMIT 1
  ) AS matched_pattern
FROM cols c
LEFT JOIN classified cl ON cl.table_name = c.table_name
WHERE cl.discovery_class IS DISTINCT FROM 'other'
ORDER BY 2 COLLATE "C"
;

-- === G20 APPLICATION SAFETY-BASELINE TEMPLATE (PLACEHOLDERS ONLY) ===
-- Evidence: EV-SAFETY-BASELINE / EV-RESERVATION-STATE / EV-CUTOVER-STATE (template)
-- DO NOT fill placeholders with guesses.
-- Execution protocol: copy this section to a run-specific file; replace placeholders
-- only from unique G19 discovery results. If not unique → BLOCKED_MISSING_CATALOG_DETAIL.

SELECT
  'EV-SAFETY-BASELINE-TEMPLATE'::text AS evidence_set,
  'g20|template|instructions'::text AS row_key,
  'BLOCKED_UNTIL_G19_UNIQUE_RESOLUTION'::text AS status,
  'Populate run-specific copy from unique G19 results only'::text AS instruction,
  '{{PROVIDERS_TABLE}}'::text AS ph_providers_table,
  '{{MODELS_TABLE}}'::text AS ph_models_table,
  '{{CREDENTIALS_TABLE}}'::text AS ph_credentials_table,
  '{{PROPOSALS_TABLE}}'::text AS ph_proposals_table,
  '{{AUTHORIZATIONS_TABLE}}'::text AS ph_authorizations_table,
  '{{WORKFLOWS_TABLE}}'::text AS ph_workflows_table,
  '{{ENVELOPES_TABLE}}'::text AS ph_envelopes_table,
  '{{USAGE_TABLE}}'::text AS ph_usage_table,
  '{{SPEND_TABLE}}'::text AS ph_spend_table,
  '{{RESERVATIONS_TABLE}}'::text AS ph_reservations_table,
  '{{CUTOVER_STATE_TABLE}}'::text AS ph_cutover_state_table,
  '{{CUTOVER_CHECKPOINT_TABLE}}'::text AS ph_cutover_checkpoint_table,
  '{{PROVIDER_CODE_COLUMN}}'::text AS ph_provider_code_column,
  '{{MODEL_CODE_COLUMN}}'::text AS ph_model_code_column,
  '{{ENABLED_FLAG_COLUMN}}'::text AS ph_enabled_flag_column,
  '{{CREDENTIAL_STATUS_COLUMN}}'::text AS ph_credential_status_column,
  '{{CREDENTIAL_LABEL_COLUMN}}'::text AS ph_credential_label_column,
  '{{PROPOSAL_STATUS_COLUMN}}'::text AS ph_proposal_status_column,
  '{{AUTHORIZATION_STATUS_COLUMN}}'::text AS ph_authorization_status_column,
  '{{RESERVATION_STATE_COLUMN}}'::text AS ph_reservation_state_column,
  'Allowed non-secret evidence after unique resolution: identifiers; provider/model relationships; enabled status; credential status; non-secret credential label; proposal/authorization status counts; active workflow count; envelope count; live-call evidence count; total paid usage; reservation State A/B/C; cutover-state presence. Never select secret/token/api_key/password/private_key/cipher/encrypted/plaintext values.'::text AS allowed_evidence_note,
  'BLOCKED_MISSING_CATALOG_DETAIL'::text AS nonunique_resolution_token
;

-- Example shape only (commented; not executed). Replace placeholders after G19 uniqueness checks.
-- SELECT
--   'EV-SAFETY-BASELINE' AS evidence_set,
--   count(*) AS provider_rows
-- FROM research.{{PROVIDERS_TABLE}};

SELECT
  'EV-RESERVATION-STATE-TEMPLATE'::text AS evidence_set,
  'g20|template|reservations'::text AS row_key,
  'BLOCKED_UNTIL_G19_UNIQUE_RESOLUTION'::text AS status,
  '{{RESERVATIONS_TABLE}}'::text AS ph_reservations_table,
  '{{RESERVATION_STATE_COLUMN}}'::text AS ph_reservation_state_column,
  'State A/B/C inventory requires unique table+column from G19'::text AS instruction,
  'BLOCKED_MISSING_CATALOG_DETAIL'::text AS nonunique_resolution_token
;

SELECT
  'EV-CUTOVER-STATE-TEMPLATE'::text AS evidence_set,
  'g20|template|cutover'::text AS row_key,
  'BLOCKED_UNTIL_G19_UNIQUE_RESOLUTION'::text AS status,
  '{{CUTOVER_STATE_TABLE}}'::text AS ph_cutover_state_table,
  '{{CUTOVER_CHECKPOINT_TABLE}}'::text AS ph_cutover_checkpoint_table,
  'Presence/absence only after unique G19 resolution'::text AS instruction,
  'BLOCKED_MISSING_CATALOG_DETAIL'::text AS nonunique_resolution_token
;

-- === G99 END DRIFT + ROLLBACK ===
-- Evidence: EV-DRIFT-END

WITH catalog_nk AS (
  SELECT ('role|' || r.rolname)::text AS nk
  FROM pg_catalog.pg_roles r
  UNION ALL
  SELECT ('function|research|' || p.proname || '|' || pg_catalog.pg_get_function_identity_arguments(p.oid))::text
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'research'
  UNION ALL
  SELECT ('table|research|' || c.relname)::text
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'research'
    AND c.relkind = 'r'
    AND NOT c.relispartition
),
agg AS (
  SELECT COALESCE(string_agg(nk, E'\n' ORDER BY nk COLLATE "C"), '') AS payload
  FROM catalog_nk
)
SELECT
  'EV-DRIFT-END'::text AS evidence_set,
  'drift|end'::text AS row_key,
  md5(a.payload) AS drift_digest_md5_fallback,
  length(a.payload) AS drift_payload_bytes,
  'Compare drift_digest_md5_fallback to EV-DRIFT-START; any difference => MUTATION_OR_CATALOG_DRIFT_DETECTED'::text AS comparison_instruction,
  'natural_keys_roles_functions_tables_v1'::text AS drift_algorithm,
  current_setting('transaction_read_only')::text AS transaction_read_only_end
FROM agg a
;

ROLLBACK;
