# Round 5A — Revision 8 Normative Decision Record

**Status:** Normative decisions only. Not schema-9 implementation.
**Baseline HEAD at authoring:** `a8d996a4f142d904dedfb523aecc591b3f5b547c`
**Revision 7 source verified:** `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md` (Revision 7)
**Scope:** Close Codex findings #4, #5, and #6 with exact checkpoint, digest, reconciliation, mapping, and State A/B decisions.
**Non-goals:** Catalog fact invention; schema-9 SQL/controller implementation; Revision 7 redesign edits; test-plan edits.

Governing decisions accepted for this record:

1. Phase 1 (`EV-*`) and Phase 2 (`ND-*`) are independent workstreams.
2. Reconciliation uses an ordered 22-rule cascade (rules 1–21 define outcomes; rule 22 = `UNCLASSIFIABLE → failed_frozen`).
3. Source/outcome mapping is a total deterministic mapping from every source identity to exactly one outcome slot (events are not the codomain; shared events store canonical source-reference sets). The word “bijection” is forbidden in normative text.
4. Every normative row carries `EV-*` and/or `ND-*` provenance. Catalog-dependent fields use `EVIDENCE_REQUIRED(<exact evidence set or row>)`. Missing input yields `BLOCKED_MISSING_INPUT`.

---

## 0. Decision record convention

Every decision below states:

| Field | Meaning |
| --- | --- |
| identifier | Stable `ND-*` id |
| decision | Normative choice |
| rationale | Why this choice is locked |
| normative input | Revision 7 / governing decision text used |
| catalog input required | Exact `EVIDENCE_REQUIRED(...)` or `none` |
| failure behavior | Exact fail-closed state |
| test obligation | Exact `ND-TEST-*` coverage required |

Encoding conventions used by all digests in this record:

* UTF-8
* field separator U+001F
* record separator U+001E
* null = `\N`
* Boolean = `t` / `f`
* text = exact PostgreSQL `text` bytes after `COLLATE "C"` sort
* UUID text = lowercase `uuid::text` without braces
* numeric text = canonical base-10 with no locale
* prohibited in digest input: OIDs, `ctid`, xmin/xmax, toast pointers, wall-clock `now()`, row physical order

---

## 1. Evidence identifier catalog (required inputs; not observed facts)

These identifiers name the Phase 1 evidence sets that must resolve before Revision 8 architecture authoring. Values are not invented here.

| EV ID | Evidence set |
| --- | --- |
| EV-PG-VERSION | Live PostgreSQL major/minor/version string |
| EV-SCHEMA-VERSION | `research.schema_version` max version row |
| EV-ROLES | Login/non-login roles and attributes relevant to Research Lab DB |
| EV-MEMBERSHIPS | Direct and transitive `pg_auth_members` paths |
| EV-SCHEMAS | Schema names and owners |
| EV-SCHEMA-PRIVS | Schema USAGE/CREATE by role including PUBLIC |
| EV-EXTENSIONS | Extensions, owners, and extension schemas |
| EV-FUNCTIONS | Every schema-8 function/overload natural identity |
| EV-FUNCTION-ACLS | Per-function ACL expansion with `COALESCE(proacl, acldefault('f', proowner))` |
| EV-FUNCTION-PUBLIC | PUBLIC EXECUTE presence (OID 0) |
| EV-FUNCTION-EFFECTIVE | Direct/PUBLIC/inherited/SET ROLE/owner/superuser/schema-USAGE/final exercisable EXECUTE |
| EV-TABLES | Every base table natural identity and owner |
| EV-TABLE-ACLS | Per-table ACL expansion with `COALESCE(relacl, acldefault('r', relowner))` |
| EV-TABLE-WRITES | Effective INSERT/UPDATE/DELETE by every discovered relevant role |
| EV-COLUMNS | Every column natural identity |
| EV-COLUMN-ACLS | Column ACL rows; null `attacl` means no column-specific grant |
| EV-COLUMN-EFFECTIVE | Effective column privileges |
| EV-VIEWS | Views and materialized views |
| EV-SEQUENCES | Sequences and ACL with `COALESCE(relacl, acldefault('s', relowner))` |
| EV-TRIGGERS | Trigger identities, enabled flags, tables, functions |
| EV-RLS | Row-security policies |
| EV-CONSTRAINTS | Constraint names, types, and definitions |
| EV-INDEXES | Index names, uniqueness, and indexed columns |
| EV-DEFAULT-PRIVS | `pg_default_acl` rows and owner provenance |
| EV-SAFETY-BASELINE | Provider/model enabled flags; credential non-secret status; proposals; authorizations; envelopes; usage/paid-cost; workflows |
| EV-RESERVATION-STATE | Legacy reservation State A/B/C inventory |
| EV-CUTOVER-STATE | Cutover-state and checkpoint presence/absence |
| EV-HELPER-FUNCTIONS | `_r3*`, `_r4*`, `_r5a*`, `cleanup_test_fixture`, `record_pilot_usage_for_tests` catalog locations/ACLs |
| EV-CRYPTO-LOCATION | pgcrypto / `digest` / `gen_random_uuid` schema locations |
| EV-DRIFT-START | Catalog drift digest at evidence start |
| EV-DRIFT-END | Catalog drift digest at evidence end |

---

## 2. Checkpoint decisions

### ND-CHECKPOINT-SET — authoritative checkpoint names

| Field | Value |
| --- | --- |
| identifier | ND-CHECKPOINT-SET |
| decision | Exactly these 18 checkpoint_id values, verified against Revision 7 §13.8, in transform order |
| rationale | Removes ellipsis and external-summary drift |
| normative input | Revision 7 §13.8 checkpoint table |
| catalog input required | none for names; object completion uses EV sets below |
| failure behavior | Any other checkpoint_id → `failed_frozen` |
| test obligation | ND-TEST-CP-SET |

Authoritative names (order fixed):

1. `crypto_schema_complete`
2. `role_and_default_privileges_complete`
3. `governance_tables_complete`
4. `governance_chain_constraints_complete`
5. `credential_scope_complete`
6. `provider_model_enablement_complete`
7. `authorization_activation_invariants_complete`
8. `discrepancy_structures_complete`
9. `discrepancy_functions_complete`
10. `capacity_event_structures_complete`
11. `pilot_builder_complete`
12. `non_pilot_builder_complete`
13. `append_only_trigger_functions_complete`
14. `append_only_triggers_attached`
15. `test_helpers_isolated`
16. `unsafe_functions_replaced`
17. `ownership_locked`
18. `default_privileges_locked`

### ND-DIGEST-CHECKPOINT-V1 — canonical checkpoint digest algorithm

| Field | Value |
| --- | --- |
| identifier | ND-DIGEST-CHECKPOINT-V1 |
| decision | One algorithm `schema9_checkpoint_digest_v1` for every checkpoint `catalog_digest` |
| rationale | Flag-without-digest is invalid; digests must be OID-free and reorder-stable |
| normative input | Governing Decision 4; Revision 7 §13.8 digest requirement |
| catalog input required | EVIDENCE_REQUIRED(EV-FUNCTIONS, EV-FUNCTION-ACLS, EV-TABLES, EV-TABLE-ACLS, EV-COLUMNS, EV-COLUMN-ACLS, EV-CONSTRAINTS, EV-INDEXES, EV-TRIGGERS, EV-EXTENSIONS, EV-SCHEMAS, EV-SCHEMA-PRIVS, EV-ROLES, EV-MEMBERSHIPS, EV-DEFAULT-PRIVS, EV-CRYPTO-LOCATION) as applicable per checkpoint |
| failure behavior | Digest mismatch / algorithm-version mismatch → `failed_frozen` |
| test obligation | ND-TEST-DIGEST-* |

Algorithm:

1. `algorithm_version` = `schema9_checkpoint_digest_v1`
2. Collect the checkpoint’s exact snapshot rows (see per-checkpoint tables).
3. Natural identity key per row type (never OID):
   * schema: `nspname`
   * role: `rolname`
   * membership: `role_name` + `member_name` + `grantor_name` + `admin_option(t/f)`
   * extension: `extname` + `extschema`
   * table/view/sequence: `schemaname` + `.` + `relname` + `relkind`
   * column: `schemaname.relname.attname`
   * function: `schemaname.proname(pg_get_function_identity_arguments)` + `prorettype_name` + `prosecdef(t/f)` + `proowner_name`
   * constraint: `schemaname.relname.conname` + `contype` + `pg_get_constraintdef` normalized
   * index: `schemaname.indexname` + `tablename` + `indexdef` normalized
   * trigger: `schemaname.relname.tgname` + `tgtype` + `tgenabled` + function identity
   * default ACL: `role_name` + `schema_name` + `objtype` + expanded ACL text with PUBLIC for OID 0
4. Prohibited fields: any OID, `oid`, `*oid`, `tableoid`, `xmin`, `xmax`, `cmin`, `cmax`, `ctid`
5. Null encoding `\N`; Boolean `t`/`f`
6. Sort rows by natural identity under `COLLATE "C"`
7. Within each row, emit fields in the checkpoint-declared column order, joined by U+001F
8. Join rows with U+001E; empty set emits zero rows and zero separators
9. SHA-256 over UTF-8 bytes of the framed payload prefixed by `algorithm_version` + U+001F
10. Output lowercase hex digest
11. Empty-set digest = SHA-256 of `schema9_checkpoint_digest_v1` + U+001F with no rows

Bidirectional evidence (ND-DIGEST-BIDIR):

* checkpoint row present without matching recomputed catalog snapshot → fail
* matching catalog snapshot without required checkpoint row → fail
* multiple checkpoint rows for one `(migration_id, checkpoint_id)` → fail
* `algorithm_version` ≠ `schema9_checkpoint_digest_v1` → fail
* stored digest ≠ recomputed digest → fail

Failure state for all digest failures: `failed_frozen`.

### 2.1 Per-checkpoint contracts

Column meanings for the master table:

* Exact object set = normative target identities (schema-9 transform products + required schema-8 predecessors)
* Exact catalog predicates = executable predicates after the checkpoint commits
* Canonical snapshot columns = fields included in ND-DIGEST-CHECKPOINT-V1 for that checkpoint
* Ordering / Serialization / Digest = ND-DIGEST-CHECKPOINT-V1 unless noted
* Completion evidence = one row in `research.schema9_cutover_checkpoints` with matching digest
* No-op predicate = re-running script changes zero catalog bits covered by the digest
* Conflict predicate = any conflicting partial/extra object
* Failure state = `failed_frozen`
* EV dependencies = required evidence before Revision 8 may assert baseline facts for that checkpoint

| ND ID | Checkpoint | Exact object set | Exact catalog predicates | Canonical snapshot columns | Ordering | Serialization | Digest algorithm | Completion evidence | No-op predicate | Conflict predicate | Failure state | EV dependencies |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ND-CHECKPOINT-01 | `crypto_schema_complete` | Schema `research_crypto`; extension `pgcrypto` relocated into `research_crypto`; procedures `research_crypto.digest(bytea,text)` and `research_crypto.gen_random_uuid()` | `EVIDENCE_REQUIRED(EV-CRYPTO-LOCATION)` proves extschema=`research_crypto`; both procedures resolve in `research_crypto`; no `digest`/`gen_random_uuid` remain executable as unqualified public/research shadows for runtime roles | `extname,extschema,proc_identity,proc_schema,proc_owner` | COLLATE "C" by natural key | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | predicates already true and digest unchanged | pgcrypto in other schema OR either procedure missing/wrong schema | failed_frozen | EVIDENCE_REQUIRED(EV-CRYPTO-LOCATION, EV-EXTENSIONS, EV-FUNCTIONS, EV-FUNCTION-ACLS) |
| ND-CHECKPOINT-02 | `role_and_default_privileges_complete` | Roles `research_governance`, `research_test`; memberships per §2; default privileges statements in §14 | Roles exist with LOGIN/NOINHERIT attributes as designed; CREATE denied on `research`/`research_crypto` for APP/N8N/GOV/TEST/PUBLIC; default ACL rows match §14 revoke-all set | `rolname,rolcanlogin,rolinherit,member_tuple,schema_priv_tuple,default_acl_tuple` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | roles+defaults digest unchanged | extra membership OR CREATE privilege present | failed_frozen | EVIDENCE_REQUIRED(EV-ROLES, EV-MEMBERSHIPS, EV-SCHEMA-PRIVS, EV-DEFAULT-PRIVS) |
| ND-CHECKPOINT-03 | `governance_tables_complete` | `research.taha_governance_actions` with indexes `EVIDENCE_REQUIRED(EV-INDEXES)` for PK/`uq_taha_gov_one_child_per_parent` and any additional indexes named in EV-INDEXES for that table | Table exists; owner=`postgres`; APP/N8N/GOV/PUBLIC Direct INSERT/UPDATE/DELETE = NONE (`EVIDENCE_REQUIRED(EV-TABLE-WRITES)`); required indexes present | `rel_identity,owner,acl_expanded,index_identity,indexdef` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | relation+index digest unchanged | table missing required index OR writable by runtime role | failed_frozen | EVIDENCE_REQUIRED(EV-TABLES, EV-TABLE-ACLS, EV-TABLE-WRITES, EV-INDEXES) |
| ND-CHECKPOINT-04 | `governance_chain_constraints_complete` | Constraints on `research.taha_governance_actions`: CHECK action_type set; CHECK authority_identifier=`Taha`; CHECK decision_value map; CHECK expires_at; FK parent; unique one-child-per-parent index; plus `EVIDENCE_REQUIRED(EV-CONSTRAINTS)` exact names/definitions | Every listed constraint/index definition equals normative text after whitespace-normalized `pg_get_constraintdef` / `pg_get_indexdef` | `conname,contype,condef,index_identity,indexdef` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | constraint digest unchanged | missing/extra/altered constraint | failed_frozen | EVIDENCE_REQUIRED(EV-CONSTRAINTS, EV-INDEXES) |
| ND-CHECKPOINT-05 | `credential_scope_complete` | `research.confirm_provider_credential_status(p_pilot_proposal_id uuid, p_provider_code text, p_n8n_credential_label text, p_governance_action_id uuid, p_note text)` SECURITY DEFINER OWNER postgres | Identity exact; EXECUTE NONE to APP/N8N/GOV/PUBLIC/TEST until restore (`EVIDENCE_REQUIRED(EV-FUNCTION-ACLS, EV-FUNCTION-EFFECTIVE)`); body contains no secret credential payload parameters | `proc_identity,owner,prosecdef,acl_expanded,prosrc_sha256` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | identity+acl+prosrc digest unchanged | wrong signature OR EXECUTE granted early | failed_frozen | EVIDENCE_REQUIRED(EV-FUNCTIONS, EV-FUNCTION-ACLS, EV-FUNCTION-EFFECTIVE) |
| ND-CHECKPOINT-06 | `provider_model_enablement_complete` | Exactly four functions: `enable_provider_for_pilot`, `disable_provider_for_pilot`, `enable_model_for_pilot`, `disable_model_for_pilot` with Appendix A.4 identities | All four exist; OWNER postgres; SECURITY DEFINER; EXECUTE NONE until restore | `proc_identity,owner,prosecdef,acl_expanded` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | identity+acl digest unchanged | missing function OR EXECUTE granted early | failed_frozen | EVIDENCE_REQUIRED(EV-FUNCTIONS, EV-FUNCTION-ACLS) |
| ND-CHECKPOINT-07 | `authorization_activation_invariants_complete` | `research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text)`; `research.trg_authorization_validity_guard()` | `prosrc` contains no `allow_pilot_activation` GUC path; EXECUTE NONE to APP/N8N/PUBLIC/TEST until restore (GOV final later); validity guard redefined without session-GUC bypass | `proc_identity,owner,prosecdef,acl_expanded,prosrc_sha256,guc_path_absent(t/f)` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | prosrc+acl digest unchanged | GUC path present OR EXECUTE granted to APP | failed_frozen | EVIDENCE_REQUIRED(EV-FUNCTIONS, EV-FUNCTION-ACLS) |
| ND-CHECKPOINT-08 | `discrepancy_structures_complete` | `research.accounting_discrepancies` + UNIQUE(`discrepancy_fingerprint`) + append-only readiness predicates | Table exists; UNIQUE present; Direct WRITE NONE for APP/N8N/GOV/PUBLIC/TEST | `rel_identity,owner,acl_expanded,unique_index_identity` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | relation digest unchanged | writable by APP OR unique missing | failed_frozen | EVIDENCE_REQUIRED(EV-TABLES, EV-TABLE-WRITES, EV-INDEXES, EV-CONSTRAINTS) |
| ND-CHECKPOINT-09 | `discrepancy_functions_complete` | `research.build_accounting_discrepancy_payload(...)` and `research.record_accounting_discrepancy(...)` exact Appendix A.4 identities | Signatures exact; OWNER postgres; SECURITY DEFINER; EXECUTE NONE for build to APP/N8N/GOV/PUBLIC; record EXECUTE NONE until restore | `proc_identity,owner,prosecdef,acl_expanded` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | identity+acl digest unchanged | EXECUTE granted early OR signature drift | failed_frozen | EVIDENCE_REQUIRED(EV-FUNCTIONS, EV-FUNCTION-ACLS) |
| ND-CHECKPOINT-10 | `capacity_event_structures_complete` | `research.pilot_capacity_events`; `research.legacy_reservation_archive`; UNIQUEs `(pilot_proposal_id, idempotency_key)`, `(pilot_proposal_id, benchmark_case_id)`, `(legacy_reservation_id)` | Tables exist; UNIQUEs present; Direct WRITE NONE for runtime roles | `rel_identity,owner,acl_expanded,unique_index_identity` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | relation digest unchanged | missing unique OR writable | failed_frozen | EVIDENCE_REQUIRED(EV-TABLES, EV-TABLE-WRITES, EV-INDEXES, EV-CONSTRAINTS) |
| ND-CHECKPOINT-11 | `pilot_builder_complete` | `research.build_provider_request_envelope(...)` redefined SECURITY DEFINER; crypto calls fully qualified to `research_crypto.*` | Signature exact; EXECUTE NONE until restore; `prosrc` has zero unqualified `digest`/`gen_random_uuid` | `proc_identity,owner,prosecdef,acl_expanded,prosrc_sha256,unqualified_crypto_count` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | prosrc+acl digest unchanged | EXECUTE granted OR unqualified crypto remains | failed_frozen | EVIDENCE_REQUIRED(EV-FUNCTIONS, EV-FUNCTION-ACLS, EV-CRYPTO-LOCATION) |
| ND-CHECKPOINT-12 | `non_pilot_builder_complete` | `research.build_non_pilot_request_envelope(...)` exact Appendix A.4 identity | Signature exact; OWNER postgres; SECURITY DEFINER; EXECUTE NONE until restore | `proc_identity,owner,prosecdef,acl_expanded` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | identity+acl digest unchanged | EXECUTE granted early | failed_frozen | EVIDENCE_REQUIRED(EV-FUNCTIONS, EV-FUNCTION-ACLS) |
| ND-CHECKPOINT-13 | `append_only_trigger_functions_complete` | Exactly: `reject_taha_governance_action_mutation`, `reject_pilot_capacity_event_mutation`, `reject_accounting_discrepancy_mutation`, `reject_legacy_reservation_archive_mutation`, `reject_legacy_capacity_table_mutation` | All five exist in `research`; OWNER postgres; identities exact | `proc_identity,owner` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | identity digest unchanged | missing/extra reject_* function | failed_frozen | EVIDENCE_REQUIRED(EV-FUNCTIONS) |
| ND-CHECKPOINT-14 | `append_only_triggers_attached` | Exactly five ENABLE triggers in Appendix A.4b | `pg_trigger` rows match names/tables/functions/enabled; no disabled required trigger | `tg_identity,table_identity,function_identity,enabled` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | trigger digest unchanged | disabled/missing/extra required trigger | failed_frozen | EVIDENCE_REQUIRED(EV-TRIGGERS) |
| ND-CHECKPOINT-15 | `test_helpers_isolated` | Helper set: `_r3_clone_question`, `_r3_new_run`, `_r4_arm_provider`, `_r4_case_id`, `_r4_make_auth`, `_r4_reset_defaults`, `_r5a_assert_final_pilot_state`, `_r5a_final_arm_gates`, `_r5a_final_assert_state`, `_r5a_final_reset_defaults`, `_r5a_insert_fixture_auth`, `_r5a_repair_reset_defaults`, `cleanup_test_fixture`, `record_pilot_usage_for_tests` | Each helper is absent from `research` **or** EXECUTE NONE for APP/N8N/GOV/PUBLIC; helpers live in `research_test` when moved | `proc_identity,schema,acl_expanded,app_exec(t/f),n8n_exec(t/f),gov_exec(t/f)` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | helper inventory digest unchanged | helper still APP-executable in `research` | failed_frozen | EVIDENCE_REQUIRED(EV-HELPER-FUNCTIONS, EV-FUNCTIONS, EV-FUNCTION-EFFECTIVE) |
| ND-CHECKPOINT-16 | `unsafe_functions_replaced` | All elevated/runtime bodies that must call crypto/`gen_random_uuid` | Zero unqualified `digest`/`gen_random_uuid` in covered `prosrc`; `search_path=pg_catalog` where SECURITY DEFINER required; `prosecdef` matches disposition | `proc_identity,prosecdef,search_path_setting,unqualified_crypto_count,prosrc_sha256` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | prosrc scan digest unchanged | any unqualified crypto remains | failed_frozen | EVIDENCE_REQUIRED(EV-FUNCTIONS, EV-FUNCTION-ACLS, EV-CRYPTO-LOCATION) |
| ND-CHECKPOINT-17 | `ownership_locked` | All security objects in `research` and `research_crypto` | Every covered table/view/sequence/function/trigger function owner = `postgres`; no runtime role owner | `object_class,object_identity,owner_name` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | owner digest unchanged | runtime role owns object | failed_frozen | EVIDENCE_REQUIRED(EV-TABLES, EV-VIEWS, EV-SEQUENCES, EV-FUNCTIONS, EV-TRIGGERS) |
| ND-CHECKPOINT-18 | `default_privileges_locked` | §14 default-privilege revoke set for `postgres` in `research` and `research_crypto` | `pg_default_acl` matches revoke-all normative tuples; no future PUBLIC EXECUTE default for those schemas | `role_name,schema_name,objtype,acl_expanded` | COLLATE "C" | U+001F/U+001E | ND-DIGEST-CHECKPOINT-V1 | checkpoint row + digest | default_acl digest unchanged | PUBLIC EXECUTE default present OR revoke missing | failed_frozen | EVIDENCE_REQUIRED(EV-DEFAULT-PRIVS) |

### ND-CHECKPOINT-COMMON — common checkpoint failure rules

| Field | Value |
| --- | --- |
| identifier | ND-CHECKPOINT-COMMON |
| decision | Runtime remains frozen through all 18 checkpoints; builders non-executable until restoration; any conflict/partial object → `failed_frozen` |
| rationale | Matches Revision 7 cutover safety |
| normative input | Revision 7 §13.8 requirements paragraph |
| catalog input required | EVIDENCE_REQUIRED(EV-CUTOVER-STATE, EV-FUNCTION-EFFECTIVE, EV-TABLE-WRITES) |
| failure behavior | `failed_frozen` |
| test obligation | ND-TEST-CP-COMMON |

---

## 3. Reconciliation identities and outcomes

### ND-IDENTITY-SOURCE

| Field | Value |
| --- | --- |
| identifier | ND-IDENTITY-SOURCE |
| decision | Source reservation identity `S` = `legacy_reservation_id` UUID of `research.pilot_capacity_reservations` (pre-rename) / `research.pilot_capacity_reservations_legacy` (post-rename) primary key |
| rationale | Natural durable key; no OID; no migration row order |
| normative input | Revision 7 §7.4 |
| catalog input required | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-TABLES, EV-COLUMNS) for exact PK/column names present in schema 8 |
| failure behavior | Missing PK column → `BLOCKED_MISSING_INPUT`; during reconcile → `failed_frozen` |
| test obligation | ND-TEST-IDENTITY-SOURCE |

Canonical source-identity serialization (`ND-IDENTITY-SOURCE-SER`):

```text
source_v1 | <lowercase uuid text>
```

### ND-IDENTITY-EVENT

| Field | Value |
| --- | --- |
| identifier | ND-IDENTITY-EVENT |
| decision | Event identity = `(pilot_proposal_id, idempotency_key)` for `attempt_consumed` rows in `research.pilot_capacity_events` |
| rationale | Matches UNIQUE contract in Revision 7 §7.1 |
| normative input | Revision 7 §7.1 |
| catalog input required | none for target schema-9 shape; baseline absence uses EVIDENCE_REQUIRED(EV-TABLES) |
| failure behavior | Duplicate natural key → conflict path under cascade |
| test obligation | ND-TEST-IDENTITY-EVENT |

### ND-IDENTITY-ARCHIVE

| Field | Value |
| --- | --- |
| identifier | ND-IDENTITY-ARCHIVE |
| decision | Archive outcome identity = `legacy_reservation_id` in `research.legacy_reservation_archive` |
| rationale | UNIQUE(`legacy_reservation_id`) |
| normative input | Revision 7 §7.5 |
| catalog input required | none for target; presence EVIDENCE_REQUIRED(EV-TABLES) after checkpoint 10 |
| failure behavior | Duplicate archive identity → `failed_frozen` |
| test obligation | ND-TEST-IDENTITY-ARCHIVE |

### ND-IDENTITY-DISCREPANCY

| Field | Value |
| --- | --- |
| identifier | ND-IDENTITY-DISCREPANCY |
| decision | Discrepancy identity = `discrepancy_fingerprint` CHAR(64) lowercase hex |
| rationale | UNIQUE fingerprint is the durable natural key |
| normative input | Revision 7 §8 / §13.9 uniqueness keys |
| catalog input required | none for target |
| failure behavior | Missing fingerprint on conflict path → `failed_frozen` |
| test obligation | ND-TEST-IDENTITY-DISC |

### ND-IDENTITY-CONFLICT / ND-IDENTITY-ORPHAN

| Field | Value |
| --- | --- |
| identifier | ND-IDENTITY-CONFLICT |
| decision | Conflict evidence identity = `conflict_kind` + U+001F + `source_v1\|<uuid>` (+ optional secondary natural keys sorted) |
| identifier | ND-IDENTITY-ORPHAN |
| decision | Orphan evidence identity = `orphan_kind` + U+001F + durable natural key of orphaned ledger/envelope row (`ledger_id` or `envelope_id` lowercase uuid) |
| rationale | OID-free conflict/orphan addressing |
| normative input | Revision 7 §13.9 orphan/conflict categories |
| catalog input required | EVIDENCE_REQUIRED(EV-SAFETY-BASELINE, EV-COLUMNS) for exact ledger/envelope PK column names |
| failure behavior | Unaddressable orphan/conflict → rule 22 / `failed_frozen` |
| test obligation | ND-TEST-IDENTITY-CONFLICT, ND-TEST-IDENTITY-ORPHAN |

### ND-IDENTITY-SHARED-EVENT-REFS

| Field | Value |
| --- | --- |
| identifier | ND-IDENTITY-SHARED-EVENT-REFS |
| decision | When multiple source identities reference one event, the event stores `source_refs` = sorted unique array of canonical source serializations under `COLLATE "C"`; every ref points to exactly one classified source identity |
| rationale | Governing Decision 3; events are not mapping codomain |
| normative input | Governing Decision 3 |
| catalog input required | none |
| failure behavior | Incomplete/unsorted/unknown refs → `failed_frozen` |
| test obligation | ND-TEST-SHARED-EVENT |

### ND-OUTCOME-SLOT

| Field | Value |
| --- | --- |
| identifier | ND-OUTCOME-SLOT |
| decision | Outcome slot `O` is one of: `slot_event_normal`, `slot_event_legacy_orphan`, `slot_archive_released`, `slot_conflict`, `slot_discrepancy`, `slot_orphan_ledger`, `slot_orphan_envelope`, `slot_failed_frozen` |
| rationale | Codomain of classify(S); not event rows |
| normative input | Governing Decision 3; Revision 7 §13.9 effects |
| catalog input required | none |
| failure behavior | No slot / multiple slots → `failed_frozen` |
| test obligation | ND-TEST-OUTCOME-SLOT |

---

## 4. Ordered 22-rule reconciliation cascade

### ND-RECON-CASCADE-ORDER

| Field | Value |
| --- | --- |
| identifier | ND-RECON-CASCADE-ORDER |
| decision | First-match-wins over the fixed order below. Evaluation order follows Revision 7 §13.9 text: invalid_status → missing_* → duplicates → conflicts → happy paths; then rule 22 fallback |
| rationale | Deterministic selection; semantic correctness proven by witness tests |
| normative input | Revision 7 §13.9 (“invalid_status → missing_* → duplicates → conflicts → happy paths”); Governing Decision 2 |
| catalog input required | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS, EV-SAFETY-BASELINE) for exact source column names and related row sets |
| failure behavior | Rule 22 → cutover state `failed_frozen` |
| test obligation | ND-TEST-RECON-PRECEDENCE, ND-TEST-RECON-SHADOW, ND-TEST-RECON-REACH, ND-TEST-RECON-FALLBACK, ND-TEST-RECON-MUTATE |

### ND-RECON-DUP-ORDER — deterministic duplicate ownership

When duplicate groups are detected:

1. Group key as defined by the duplicate rule.
2. Winner = minimum `legacy_reservation_id` UUID text under `COLLATE "C"`.
3. Tie-breaker (if ever needed beyond UUID PK): minimum canonical source serialization.
4. Non-winners enter `slot_conflict` with conflict_kind = the duplicate rule name.

### Rules 1–21

Unless noted, `Source identity` = ND-IDENTITY-SOURCE serialization. Capacity effect “consumed fail-closed” means capacity remains consumed and is never restored. Pilot blocked means pilot-scoped builders must deny.

| Rule | ND ID | Exact predicate | Explicit exclusions | Source identity | Capacity effect | Outcome slot | Event/archive behavior | Discrepancy behavior | Pilot state | Automatic recovery | Owner action | EV dependencies |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ND-RECON-01 | `status IS NULL OR status NOT IN ('reserved','finalized','released')` | none | S | consumed fail-closed | slot_conflict + slot_discrepancy | conflict record keyed by S; no archive; no happy-path event | discrepancy_type=`invalid_status` | pilot blocked | N | classify/fix | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 2 | ND-RECON-02 | `pilot_proposal_id IS NULL OR NOT EXISTS (SELECT 1 FROM research.provider_pilot_proposals p WHERE p.id = source.pilot_proposal_id)` | excludes rule 1 true | S | consumed fail-closed | slot_conflict + slot_discrepancy | conflict record; no archive | discrepancy_type=`missing_proposal` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-SAFETY-BASELINE, EV-COLUMNS) |
| 3 | ND-RECON-03 | `authorization_id IS NULL OR NOT EXISTS (SELECT 1 FROM research.provider_authorization_records a WHERE a.id = source.authorization_id)` | excludes rules 1–2 true | S | consumed fail-closed | slot_conflict + slot_discrepancy | conflict record | discrepancy_type=`missing_authorization` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-SAFETY-BASELINE, EV-COLUMNS) |
| 4 | ND-RECON-04 | `benchmark_case_id IS NULL OR NOT EXISTS (SELECT 1 FROM research.benchmark_cases c WHERE c.id = source.benchmark_case_id)` | excludes rules 1–3 true | S | consumed fail-closed | slot_conflict + slot_discrepancy | conflict record | discrepancy_type=`missing_case` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-SAFETY-BASELINE, EV-COLUMNS) |
| 5 | ND-RECON-05 | Exists another source S2 with same `(pilot_proposal_id, benchmark_case_id, idempotency_key)` and S2 ≠ S and both pass rules 1–4 false; S is not the ND-RECON-DUP-ORDER winner | excludes rules 1–4 true; winners excluded | S | capacity held once for winner only | slot_conflict + slot_discrepancy for non-winners | non-winner: conflict only; winner deferred to later matching rule | discrepancy_type=`duplicate_idempotency_key` | pilot blocked | N | dedupe approve | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 6 | ND-RECON-06 | Exists another source S2 with same `(pilot_proposal_id, benchmark_case_id)`, both would create `attempt_consumed`, S is not ND-RECON-DUP-ORDER winner among that group after excluding rule-5 non-winners | excludes rules 1–5 true | S | capacity held once | slot_conflict + slot_discrepancy | conflict on non-winner | discrepancy_type=`duplicate_case_attempt` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 7 | ND-RECON-07 | `envelope_id IS NOT NULL` AND exists another source/event claiming same `envelope_id` with different S, and S is not winner by min(envelope claim source serialization) | excludes rules 1–6 true | S | capacity held | slot_conflict + slot_discrepancy | conflict | discrepancy_type=`duplicate_envelope_link` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-SAFETY-BASELINE, EV-COLUMNS) |
| 8 | ND-RECON-08 | Source status in (`reserved`,`finalized`) AND after attempting event materialization, required event natural key missing OR event fields mismatch source (`pilot_proposal_id`,`authorization_id`,`benchmark_case_id`,`idempotency_key`, envelope/legacy linkage) | excludes rules 1–7 true | S | consumed | slot_conflict + slot_discrepancy | conflict row; no silent rewrite | discrepancy_type=`reservation_event_conflict` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE) |
| 9 | ND-RECON-09 | For source pilot scope, `provider_usage_ledger` reporting request aggregates for bound auth/case are not equal to event-count authority defined in §7.2 (events-only request authority). Equality predicate: `ledger_request_count_reporting = COUNT(events)` is NOT required to authorize; conflict when ledger is used as enforcement input OR when recorded ledger request fields contradict event-derived request count under the typed discrepancy payload comparison | excludes rules 1–8 true | S | consumed; builder blocks | slot_discrepancy | events unchanged | discrepancy_type=`reservation_ledger_request_conflict` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-SAFETY-BASELINE) |
| 10 | ND-RECON-10 | Ledger success count for pilot-bound non-test rows ≠ COUNT of success authority rows defined in §7.2 while source is in scope | excludes rules 1–9 true | S | consumed; builder blocks | slot_discrepancy | events unchanged | discrepancy_type=`reservation_ledger_success_conflict` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-SAFETY-BASELINE) |
| 11 | ND-RECON-11 | Projected token sums from events for the source’s pilot/case scope ≠ policy max token fields on the bound authorization/policy row under typed integer equality | excludes rules 1–10 true | S | consumed; builder blocks | slot_conflict + slot_discrepancy | conflict | discrepancy_type=`token_conflict` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-SAFETY-BASELINE) |
| 12 | ND-RECON-12 | `projected_cost_usd <> 0` on materializing event OR ledger `estimated_cost_usd > 0` for free-pilot scope OR cost fields disagree under numeric(20,8) eight-decimal equality | excludes rules 1–11 true | S | consumed; builder blocks | slot_conflict + slot_discrepancy | conflict | discrepancy_type=`cost_conflict` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-SAFETY-BASELINE) |
| 13 | ND-RECON-13 | Any counter among source-linked projected/ledger/policy integer fields is NULL where NOT NULL required OR value < 0 | excludes rules 1–12 true | S | consumed fail-closed | slot_conflict + slot_discrepancy | conflict | discrepancy_type=`negative_or_malformed_counters` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS, EV-SAFETY-BASELINE) |
| 14 | ND-RECON-14 | Exists `accounting_discrepancies` row for source pilot scope with no terminal `accounting_discrepancy_acknowledged` governance action in discrepancy scope | excludes rules 1–13 true | S | consumed; builder blocks | slot_discrepancy | retain existing discrepancy | discrepancy retained | pilot blocked | N | acknowledge | EVIDENCE_REQUIRED(EV-SAFETY-BASELINE) |
| 15 | ND-RECON-15 | Exists ledger row in pilot scope with no reservation/auth binding natural key matching any source S or event identity | excludes rules 1–14 true; evaluated over ledger orphans discovered during reconcile | ledger orphan natural key | no capacity restore | slot_orphan_ledger + slot_discrepancy | orphan conflict | discrepancy_type=`orphaned_ledger_row` | pilot blocked if pilot-scoped | N | inspect | EVIDENCE_REQUIRED(EV-SAFETY-BASELINE, EV-COLUMNS) |
| 16 | ND-RECON-16 | Exists envelope row with no matching capacity event natural key after reconcile pass | excludes rules 1–15 true | envelope natural key | no capacity restore | slot_orphan_envelope + slot_discrepancy | orphan conflict | discrepancy_type=`orphaned_envelope_row` | pilot blocked | N | inspect | EVIDENCE_REQUIRED(EV-SAFETY-BASELINE, EV-COLUMNS) |
| 17 | ND-RECON-17 | `status='reserved' AND envelope_id IS NOT NULL` | excludes rules 1–16 true | S | attempt_consumed normal | slot_event_normal | insert/reuse event with `consumption_kind='normal'` and that `envelope_id`; no archive; event `source_refs` includes S | none | capacity held | Y if UNIQUE ok | none | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 18 | ND-RECON-18 | `status='reserved' AND envelope_id IS NULL` | excludes rules 1–17 true | S | legacy_orphan consumed | slot_event_legacy_orphan | event `consumption_kind='legacy_orphan'`, `envelope_id NULL`, `legacy_reservation_id=S`; no archive | none unless later ledger conflict rules already excluded | capacity held | Y | none | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 19 | ND-RECON-19 | `status='finalized' AND envelope_id IS NOT NULL` | excludes rules 1–18 true | S | attempt_consumed normal | slot_event_normal | event linked as normal; no archive | none | capacity held | Y | none | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 20 | ND-RECON-20 | `status='finalized' AND envelope_id IS NULL` | excludes rules 1–19 true | S | legacy_orphan consumed | slot_event_legacy_orphan | event legacy_orphan; no archive | none | capacity held | Y | none | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 21 | ND-RECON-21 | `status='released'` | excludes rules 1–20 true | S | zero capacity | slot_archive_released | archive row UNIQUE(legacy_reservation_id=S), `archived_status='released'`; no `attempt_consumed` | none | unchanged | Y | none | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-COLUMNS) |

### Rule 22 — ND-RECON-22

| Field | Value |
| --- | --- |
| identifier | ND-RECON-22 |
| decision | `UNCLASSIFIABLE → failed_frozen` |
| exact predicate | Source or orphan/conflict unit remains after rules 1–21 all false |
| outcome slot | `slot_failed_frozen` |
| capacity effect | consumed fail-closed; no capacity restore |
| event/archive behavior | no happy-path write; durable failure evidence recorded in cutover reconciliation_evidence |
| pilot state | blocked |
| automatic recovery | N |
| owner action | redesign/classify |
| failure behavior | set cutover state `failed_frozen` |
| test obligation | ND-TEST-RECON-FALLBACK |

---

## 5. Total source-to-outcome mapping

### ND-OUTCOME-MAP-TOTAL

| Field | Value |
| --- | --- |
| identifier | ND-OUTCOME-MAP-TOTAL |
| decision | For every source identity S in the reconcile domain, `classify(S)` returns exactly one primary outcome slot O via the cascade; side-effect records (conflict/discrepancy) are attached to that classification but do not create a second primary slot for S |
| rationale | Governing Decision 3 totality and determinism |
| normative input | Governing Decision 3 |
| catalog input required | EVIDENCE_REQUIRED(EV-RESERVATION-STATE) for domain membership |
| failure behavior | Unclassified S → rule 22 / `failed_frozen`; multiple primary slots → `failed_frozen` |
| test obligation | ND-TEST-MAP-TOTAL |

Requirements locked:

* totality over all source identities in EV-RESERVATION-STATE domain
* determinism for fixed evidence snapshot
* one primary outcome slot per source identity
* no source identity in multiple primary slots
* no silent unclassified source
* shared events may reference multiple source identities
* each shared event stores canonical sorted `source_refs`
* every source reference points back to exactly one classified source identity
* aggregate counts are never accepted as proof of mapping completeness

---

## 6. State A and State B completeness

### ND-STATE-A-EQUALITY

| Field | Value |
| --- | --- |
| identifier | ND-STATE-A-EQUALITY |
| decision | State A completeness is set equality over identities, not counts |
| rationale | Revision 7 §13.10 strengthened to identity sets |
| normative input | Revision 7 §13.10; Governing Decision 3 |
| catalog input required | EVIDENCE_REQUIRED(EV-RESERVATION-STATE) |
| failure behavior | Inequality → `failed_frozen` |
| test obligation | ND-TEST-STATE-A |

Define:

* `SourceSet` = all ND-IDENTITY-SOURCE serializations in reconcile domain
* `ClassifiedSet` = all S for which classify(S) returned a primary slot
* `EventRefSet` = union of all event `source_refs` plus singleton refs implied by `legacy_reservation_id` on legacy_orphan events
* `ArchiveRefSet` = all archive `legacy_reservation_id` serializations
* `DiscrepancyRefSet` = all discrepancy-linked source serializations
* `FallbackRefSet` = all sources classified by rule 22
* `ConflictRefSet` = all conflict-linked source serializations

Required equalities:

```text
SourceSet = ClassifiedSet
SourceSet = (EventRefSet ∪ ArchiveRefSet ∪ ConflictRefSet ∪ DiscrepancyRefSet ∪ FallbackRefSet)
|slot(S)| = 1 for every S in SourceSet
```

Duplicate handling: non-winners appear in ConflictRefSet/DiscrepancyRefSet only; winners appear in their happy-path or later conflict sets exactly once. Orphan ledger/envelope identities are tracked in orphan sets and must not fabricate source identities.

Digests persisted (`reconciliation_algorithm_version` = `schema9_reconcile_v2`):

* `source_pk_set_digest`
* `classified_identity_set_digest`
* `event_source_ref_set_digest`
* `archive_identity_set_digest`
* `conflict_identity_set_digest`
* `discrepancy_identity_set_digest`
* `fallback_identity_set_digest`

Each set digest = SHA-256 over sorted unique identity strings joined by U+001E under `schema9_set_digest_v1` prefix (OID-free).

### ND-STATE-B-RECOMPUTE

| Field | Value |
| --- | --- |
| identifier | ND-STATE-B-RECOMPUTE |
| decision | State B independently recomputes all State A sets and digests from durable legacy + schema-9 tables only; checkpoint presence is insufficient |
| rationale | Prevents flag-only false completion |
| normative input | Revision 7 §13.7 / §13.10 independent completeness proof |
| catalog input required | EVIDENCE_REQUIRED(EV-RESERVATION-STATE, EV-TABLES, EV-SAFETY-BASELINE) |
| failure behavior | Any mismatch → `failed_frozen` |
| test obligation | ND-TEST-STATE-B |

State B inputs (only):

* durable legacy reservation table (current name from evidence: `pilot_capacity_reservations` or `pilot_capacity_reservations_legacy`)
* `research.pilot_capacity_events`
* `research.legacy_reservation_archive`
* `research.accounting_discrepancies`
* conflict/orphan evidence tables/rows persisted by reconcile
* bound proposal/auth/case/ledger/envelope durable rows needed by predicates

State B must recompute:

* SourceSet, EventRefSet, ArchiveRefSet, DiscrepancyRefSet, outcome-slot assignment map, algorithm version, all set digests
* assert zero missing identities, zero multiply classified identities, zero unknown references
* must not read `schema9_cutover_checkpoints` as proof of completeness
* must not reference the pre-rename table name after rename checkpoint commits

---

## 7. Cascade and checkpoint test obligations

| ND ID | Obligation |
| --- | --- |
| ND-TEST-CP-SET | Assert exactly 18 checkpoint ids and order |
| ND-TEST-DIGEST-EMPTY | Empty-set digest stable |
| ND-TEST-DIGEST-OID-FREE | Fixture containing OIDs rejected from digest input |
| ND-TEST-DIGEST-BIDIR | Both-direction evidence failures |
| ND-TEST-CP-01 … ND-TEST-CP-18 | For each checkpoint: valid pair; checkpoint+catalog mismatch; catalog+missing checkpoint; digest mismatch; algorithm-version mismatch; partial object set; conflicting definition; rerun no-op; failure → `failed_frozen` (9 cases each) |
| ND-TEST-RECON-PRECEDENCE | For each rule j in 1..21, witness Wj satisfies rule j and cascade returns j |
| ND-TEST-RECON-SHADOW | For each Wj, predicates 1..j-1 are false |
| ND-TEST-RECON-REACH | Every rule 1–21 reachable by at least one witness |
| ND-TEST-RECON-FALLBACK | At least one witness fails 1–21 and reaches rule 22 → `failed_frozen` |
| ND-TEST-RECON-MUTATE | For each witness, mutate each decisive field; result is adjacent intended rule or fallback |
| ND-TEST-MAP-TOTAL | Every fixture source maps to exactly one primary slot |
| ND-TEST-SHARED-EVENT | Multi-source event has canonical sorted source_refs |
| ND-TEST-STATE-A | Identity-set equalities hold; count-only spoof fails |
| ND-TEST-STATE-B | Independent recomputation mismatch → `failed_frozen` |
| ND-TEST-IDENTITY-* | Natural-key serialization tests for each identity type |

---

## 8. Freeze / final disposition normative tags

These dispositions are normative for Revision 8 architecture rows and must be cited as `ND-*` (catalog current ACLs remain `EV-*`).

| ND ID | Decision |
| --- | --- |
| ND-FREEZE-REVOKE-WRITES | During freeze, REVOKE INSERT/UPDATE/DELETE from all runtime roles on all research base tables that currently grant them (`EVIDENCE_REQUIRED(EV-TABLE-WRITES)` enumerates cells) |
| ND-FREEZE-REVOKE-EXECUTE | During freeze, REVOKE EXECUTE on all functions not in the keep-EXECUTE set; keep-EXECUTE set is normative names `gemini_pilot_5a_gate_status`, `sha256_hex`, `compute_priority_v1`, `proposal_has_evidence`, `estimate_provider_cost_usd`, `pilot_capacity_snapshot`, `pilot_case_attempt_count` only after EV-FUNCTIONS confirms identities |
| ND-FINAL-GRANT-APPENDIX-A | Final grants after restoration txn A are exactly Appendix A tables/functions; no ALL; no PUBLIC elevated |
| ND-FINAL-HELPERS-TEST | Helpers final EXECUTE only `research_test` after move |

---

## 9. EVIDENCE_REQUIRED marker inventory

Total markers used in this record (unique):

1. EV-PG-VERSION
2. EV-SCHEMA-VERSION
3. EV-ROLES
4. EV-MEMBERSHIPS
5. EV-SCHEMAS
6. EV-SCHEMA-PRIVS
7. EV-EXTENSIONS
8. EV-FUNCTIONS
9. EV-FUNCTION-ACLS
10. EV-FUNCTION-PUBLIC
11. EV-FUNCTION-EFFECTIVE
12. EV-TABLES
13. EV-TABLE-ACLS
14. EV-TABLE-WRITES
15. EV-COLUMNS
16. EV-COLUMN-ACLS
17. EV-COLUMN-EFFECTIVE
18. EV-VIEWS
19. EV-SEQUENCES
20. EV-TRIGGERS
21. EV-RLS
22. EV-CONSTRAINTS
23. EV-INDEXES
24. EV-DEFAULT-PRIVS
25. EV-SAFETY-BASELINE
26. EV-RESERVATION-STATE
27. EV-CUTOVER-STATE
28. EV-HELPER-FUNCTIONS
29. EV-CRYPTO-LOCATION
30. EV-DRIFT-START
31. EV-DRIFT-END

No catalog fact in this document is asserted as observed. All catalog-dependent fields remain `EVIDENCE_REQUIRED(...)`.

---

## 10. Unresolved normative decisions

NONE within Phase 2 scope. Remaining work is evidence resolution (Phase 1) before Revision 8 architecture authoring.

---

## 11. Validation checklist (Phase 2)

* docs-only file: `docs/ROUND_5A_REVISION_8_NORMATIVE_DECISION_RECORD.md`
* Revision 7 redesign untouched in this phase
* test plan untouched in this phase
* no SQL / schema-9 implementation added
* no catalog facts invented
* 18 checkpoints named exactly from Revision 7 §13.8
* 22-rule cascade defined with rule 22 fallback
* total source-to-outcome mapping defined without calling it a bijection
* State A identity-set equality and State B independent recomputation defined
