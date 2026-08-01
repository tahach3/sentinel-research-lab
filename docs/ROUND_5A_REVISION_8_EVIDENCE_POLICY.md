# Round 5A — Revision 8 Evidence Policy

**Status:** Normative evidence-class policy for Revision 8. Not schema-9 implementation. Not Revision 8 architecture.
**Amendment date:** 2026-08-01
**Companion Decision Record:** `docs/ROUND_5A_REVISION_8_NORMATIVE_DECISION_RECORD.md`
**Evidence class of reference artifacts:** `RECONSTRUCTED_REFERENCE_SCHEMA8`
**Canonical manifest SHA-256:** `09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2`
**Evidence crosswalk SHA-256:** `9D38F04D3BE2B519C59837ACD825B9DD74CA3724D793BAC7495B29C4B66E141F`
**Evidence root (audit):** `C:\Users\tahai\AppData\Local\Temp\srl-schema8-reconstruction-20260801_151349`
**Canonical manifest artifact:** `SHA256SUMS.txt` under the evidence root (hash above is SHA-256 of that file)

## Absolute limitation

Historical live schema-8 catalog state was **not** recovered. Reconstructed reference evidence is produced by restoring a schema-5 backup and replaying migrations 6–8 in an isolated disposable PostgreSQL environment. It must never be labeled or treated as `LIVE_CATALOG` or as a reproduction of historical live schema-8.

Marker totals from actual crosswalk rows (`RECONSTRUCTED_EVIDENCE_CROSSWALK.tsv`):

| Classification in crosswalk | Count | Normative disposition |
| --- | ---: | --- |
| `RESOLVABLE_FROM_RECONSTRUCTED_REFERENCE` | 17 | `RECONSTRUCTED_REFERENCE_ACCEPTED` for Revision 8 design of deterministic schema/migration facts only |
| `REQUIRES_HISTORICAL_LIVE_CATALOG` | 11 | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` — not resolved |
| `REQUIRES_CURRENT_RUNTIME_STATE` | 3 | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED` — not resolved |
| **Total** | **31** | All prior `EV-*` identities preserved |

---

## 1. Evidence hierarchy (Classes 1–4)

### Class 1 — LIVE_CATALOG

Definition:

```text
Evidence observed directly from the target database immediately before the governed operation.
```

May prove:

* current roles;
* current ACLs;
* current functions and overloads;
* current table and column privileges;
* current owners;
* current default privileges;
* current triggers, policies, views, extensions, and indexes;
* current runtime reservation and cutover state.

No marker in this amendment is labeled `LIVE_CATALOG`. Zero current markers are falsely classified as live catalog observations.

### Class 2 — RECONSTRUCTED_REFERENCE_SCHEMA8

Definition:

```text
Evidence produced by restoring the schema-5 backup and replaying committed authoritative migrations 6–8 in an isolated PostgreSQL environment.
```

Required metadata (must appear on every reconstructed provenance citation):

```text
SOURCE_BACKUP_SCHEMA = 5
REPLAYED_MIGRATIONS = 6,7,8
NOT_HISTORICAL_LIVE_CATALOG = true
```

May prove only deterministic consequences of:

* the preserved schema-5 backup;
* committed migrations 6–8;
* PostgreSQL catalog semantics;
* deterministic migration data transformations.

Must not claim to prove:

* historical manual grants or revokes;
* roles created outside migrations;
* post-migration manual objects;
* post-backup runtime changes;
* credential health;
* provider/model state after backup;
* workflow activation after backup;
* paid usage after backup;
* reservation or cutover rows created after backup;
* operator interventions.

### Class 3 — EXECUTION_TIME_LIVE_PREFLIGHT

Definition:

```text
A mandatory live-catalog observation performed against the actual target database immediately before schema-9 execution.
```

Failure behavior:

```text
BLOCKED_LIVE_PREFLIGHT_REQUIRED
```

or:

```text
failed_frozen
```

when execution has already entered a governed migration state.

### Class 4 — PILOT_TIME_RUNTIME_REVALIDATION

Definition:

```text
A mandatory runtime-state observation performed immediately before enabling the Research Lab pilot or any live provider, workflow, or paid operation.
```

Failure behavior:

```text
BLOCKED_RUNTIME_REVALIDATION_REQUIRED
```

No live or paid operation may proceed without it.

---

## 2. Evidence precedence

Ordered precedence (highest first):

```text
1. current LIVE_CATALOG evidence
2. execution-time live preflight
3. reconstructed reference evidence
4. migration intent or prose
```

Rules:

* live evidence overrides reconstructed reference when both describe current state;
* a mismatch is not silently normalized;
* a mismatch produces a recorded discrepancy;
* migration intent never overrides observed catalog evidence;
* reconstructed reference may define expected deterministic structure;
* reconstructed reference may not prove absence of manual runtime changes.

---

## 3. Comparison outcomes

For every execution-time live check against reconstructed reference, the outcome is exactly one of:

```text
MATCHES_RECONSTRUCTED_REFERENCE
SAFE_DECLARED_VARIANCE
UNSAFE_UNDECLARED_VARIANCE
MISSING_REQUIRED_OBJECT
UNKNOWN_EXTRA_OBJECT
PRIVILEGE_EXPANSION
PRIVILEGE_REDUCTION
OWNER_MISMATCH
RUNTIME_STATE_MISMATCH
```

Proceed rules:

* `MATCHES_RECONSTRUCTED_REFERENCE` may proceed;
* `SAFE_DECLARED_VARIANCE` may proceed only when an `ND-*` row explicitly permits that variance;
* every other outcome blocks with `BLOCKED_LIVE_PREFLIGHT_REQUIRED` (pre-execution) or enters `failed_frozen` (in governed migration state).

No automatic repair is permitted.

---

## 4. Marker reclassification table (all 31)

Column meanings:

* **Proven value or deferred fact** — reconstructed resolved value for design, or explicit unknown until the named gate.
* **Revalidation gate** — none for accepted reconstructed design facts; otherwise the mandatory class-3 or class-4 gate.
* **Provenance** — always includes canonical manifest hash for reconstructed citations; never claims historical live reproduction.

| Marker | Decision section | Evidence class | Permitted evidence artifact | Proven value or deferred fact | Revalidation gate | Failure behavior | Provenance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EV-PG-VERSION | §1; ND-DIGEST / baseline | RECONSTRUCTED_REFERENCE_SCHEMA8 | `schema8_catalog.txt` row `pg_version`; bundle EV-PG-VERSION | `PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1) on x86_64-pc-linux-gnu...` from pinned image digest | none for Rev8 design of engine major/minor string from reconstruction | N/A for design acceptance; live host identity still subject to preflight when host identity is operationally material | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-PG-VERSION); manifest `09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2`; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; limitation: not historical live host identity beyond image/version string |
| EV-SCHEMA-VERSION | §1; ND-CHECKPOINT / cutover baseline | RECONSTRUCTED_REFERENCE_SCHEMA8 | `final_schema_version.txt`; `schema8_verify.txt` max/version rows | `max(version)=8`; rows 1–8 present with migration notes through Round 5A final | none for Rev8 design of schema_version ladder after replay | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-SCHEMA-VERSION); manifest hash above; migrations 6–8 applied; limitation: Phase1 template G20 detail remains blocked in bundle templates; verified via direct reconstructed SQL |
| EV-ROLES | §1; ND-CHECKPOINT-02 | EXECUTION_TIME_LIVE_PREFLIGHT | Live `pg_roles` / role attribute inventory | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-ROLES retained; dump has no CREATE ROLE; disposable placeholders are not historical live inventory |
| EV-MEMBERSHIPS | §1; ND-CHECKPOINT-02 | EXECUTION_TIME_LIVE_PREFLIGHT | Live `pg_auth_members` graph | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-MEMBERSHIPS retained; reconstructed memberships reflect placeholders/defaults only |
| EV-SCHEMAS | §1; ND-CHECKPOINT-01/02/17 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `schema8_catalog.txt` namespace rows | schemas `research`, `n8n`, `public` present; research/n8n owners `postgres` at restore time | none for Rev8 design of schema presence from backup | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-SCHEMAS); manifest hash; limitation: owners are restore-time postgres and may differ if historical ownership diverged |
| EV-SCHEMA-PRIVS | §1; ND-CHECKPOINT-02 | EXECUTION_TIME_LIVE_PREFLIGHT | Live schema USAGE/CREATE ACL including PUBLIC | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-SCHEMA-PRIVS retained; backup grantless; Round0B init grants not replayed |
| EV-EXTENSIONS | §1; ND-CHECKPOINT-01; ND-DIGEST | RECONSTRUCTED_REFERENCE_SCHEMA8 | `schema8_catalog.txt` extension rows | `pgcrypto`/`public`, `uuid-ossp`/`n8n`, `vector`/`public` (plus `plpgsql`/`pg_catalog`) | none for Rev8 design of extension/schema locations from backup+replay | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-EXTENSIONS); manifest hash; SOURCE_BACKUP_SCHEMA=5 |
| EV-FUNCTIONS | §1; ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE | RECONSTRUCTED_REFERENCE_SCHEMA8 | `schema8_verify.txt` count; catalog function inventory; bundle EV-FUNCTION-* | `52` research functions after migrations 6–8; identities captured | none for Rev8 design of function natural identities from replay | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS); manifest hash; limitation: seed-side UUID/timestamp values nondeterministic |
| EV-FUNCTION-ACLS | §1; ND-CHECKPOINT-05..12,16; ND-FREEZE-REVOKE-EXECUTE | EXECUTION_TIME_LIVE_PREFLIGHT | Live `COALESCE(proacl, acldefault('f', proowner))` expansion | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-FUNCTION-ACLS retained; migration-6 GRANT surface not authoritative historical live ACL |
| EV-FUNCTION-PUBLIC | §1; ND-CHECKPOINT function ACL cells | EXECUTION_TIME_LIVE_PREFLIGHT | Live PUBLIC (OID 0) EXECUTE presence | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-FUNCTION-PUBLIC retained; depends on default privileges/init path not fully replayed |
| EV-FUNCTION-EFFECTIVE | §1; ND-CHECKPOINT-05/15; ND-CHECKPOINT-COMMON | EXECUTION_TIME_LIVE_PREFLIGHT | Live effective EXECUTE matrix | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-FUNCTION-EFFECTIVE retained; depends on roles/memberships/schema USAGE |
| EV-TABLES | §1; ND-CHECKPOINT-03/08/10/17; identities | RECONSTRUCTED_REFERENCE_SCHEMA8 | `schema8_verify.txt` / catalog table list | `48` research base tables including v6/v8 objects; no schema-9 tables | none for Rev8 design of table natural identities from replay | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-TABLES); manifest hash; NOT_HISTORICAL_LIVE_CATALOG=true |
| EV-TABLE-ACLS | §1; ND-CHECKPOINT-03/08/10 | EXECUTION_TIME_LIVE_PREFLIGHT | Live `COALESCE(relacl, acldefault('r', relowner))` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-TABLE-ACLS retained; missing init schema/default privileges in disposable path |
| EV-TABLE-WRITES | §1; ND-CHECKPOINT-03/08/10; ND-FREEZE-REVOKE-WRITES; ND-CHECKPOINT-COMMON | EXECUTION_TIME_LIVE_PREFLIGHT | Live effective INSERT/UPDATE/DELETE by role | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-TABLE-WRITES retained; effective writes depend on privilege path |
| EV-COLUMNS | §1; ND-IDENTITY-*; ND-RECON-* | RECONSTRUCTED_REFERENCE_SCHEMA8 | `information_schema` / catalog column inventory | Research columns enumerated after replay including `pilot_capacity_reservations` PK `id` and State columns | none for Rev8 design of column natural identities | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-COLUMNS); manifest hash; limitation: no dedicated EV-COLUMNS set name in bundle; natural identities available |
| EV-COLUMN-ACLS | §1; ND-DIGEST column ACL cells | EXECUTION_TIME_LIVE_PREFLIGHT | Live column ACL rows (`attacl`) | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-COLUMN-ACLS retained; role baseline non-historical |
| EV-COLUMN-EFFECTIVE | §1; ND-DIGEST column privilege cells | EXECUTION_TIME_LIVE_PREFLIGHT | Live effective column privileges | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-COLUMN-EFFECTIVE retained |
| EV-VIEWS | §1; ND-CHECKPOINT-17 | RECONSTRUCTED_REFERENCE_SCHEMA8 | Bundle EV-VIEW-001 + catalog | Views including gemini pilot status view from migration 6 present | none for Rev8 design of view identities | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-VIEWS); manifest hash; migration 6 provenance |
| EV-SEQUENCES | §1; ND-CHECKPOINT-17 | RECONSTRUCTED_REFERENCE_SCHEMA8 | Catalog sequence inventory | No research sequences observed (empty inventory treated as reconstructed fact) | none for Rev8 design empty-set fact | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-SEQUENCES); manifest hash; bundle emitted no EV-SEQUENCE rows |
| EV-TRIGGERS | §1; ND-CHECKPOINT-14 | RECONSTRUCTED_REFERENCE_SCHEMA8 | Catalog / EV-TRIGGER inventory | Triggers including authorization validity guard from migrations 7/8 captured | none for Rev8 design of trigger identities | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-TRIGGERS); manifest hash; migrations 7/8 |
| EV-RLS | §1; ND-DIGEST / baseline | RECONSTRUCTED_REFERENCE_SCHEMA8 | `pg_policies` on research | No row-security policies on research in reconstructed DB (empty inventory) | none for Rev8 design empty-set fact | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RLS); manifest hash; bundle has no EV-RLS set |
| EV-CONSTRAINTS | §1; ND-CHECKPOINT-04/08/10; ND-RECON | RECONSTRUCTED_REFERENCE_SCHEMA8 | Bundle EV-CONSTRAINT-001 | `266` constraint rows captured including reservation PK/UNIQUE/CHECK/FK set | none for Rev8 design of constraint definitions from replay | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-CONSTRAINTS); manifest hash |
| EV-INDEXES | §1; ND-CHECKPOINT-03/04/08/10 | RECONSTRUCTED_REFERENCE_SCHEMA8 | Bundle EV-INDEX-001 | `76` index rows captured including reservation unique indexes | none for Rev8 design of index definitions from replay | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-INDEXES); manifest hash |
| EV-DEFAULT-PRIVS | §1; ND-CHECKPOINT-02/18 | EXECUTION_TIME_LIVE_PREFLIGHT | Live `pg_default_acl` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` or `failed_frozen` | Prior marker EV-DEFAULT-PRIVS retained; Round0B ALTER DEFAULT PRIVILEGES not applied in disposable restore |
| EV-SAFETY-BASELINE | §1; ND-RECON-02..16; ND-IDENTITY-CONFLICT/ORPHAN; ND-STATE-B | PILOT_TIME_RUNTIME_REVALIDATION | Live non-secret provider/model/credential-status/proposal/authorization/envelope/usage/workflow flags | `UNKNOWN_UNTIL_RUNTIME_REVALIDATION` | PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED | `BLOCKED_RUNTIME_REVALIDATION_REQUIRED`; pilot/live/paid prohibited until resolved | Prior marker EV-SAFETY-BASELINE retained; reconstructed partial flags insufficient alone |
| EV-RESERVATION-STATE | §1; ND-IDENTITY-SOURCE; ND-RECON-*; ND-STATE-A/B | RECONSTRUCTED_REFERENCE_SCHEMA8 | `schema8_verify_extra.txt`; catalog reservation table | `pilot_capacity_reservations` exists; `0` rows after deterministic migration 8; State A/B/C inventory empty | none for Rev8 design of empty post-migration-8 inventory shape | N/A for design acceptance of empty reconstructed inventory; live row presence after backup remains a live concern via precedence | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE); manifest hash; migration 8; limitation: cannot prove absence of post-backup live rows |
| EV-CUTOVER-STATE | §1; ND-CHECKPOINT-COMMON | RECONSTRUCTED_REFERENCE_SCHEMA8 | `schema8_verify.txt` absence flags | No `schema_version=9`; no `research_crypto`; no `taha_governance_actions` / `accounting_discrepancies` cutover objects | none for Rev8 design of pre-schema-9 absence from replay | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-CUTOVER-STATE); manifest hash; limitation: absence verified in reconstruction only |
| EV-HELPER-FUNCTIONS | §1; ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST | RECONSTRUCTED_REFERENCE_SCHEMA8 | Catalog helper identities/locations | Helper identities/locations captured in `research` post-migration | none for Rev8 design of helper natural identities | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-HELPER-FUNCTIONS); manifest hash; limitation: ACL portions inherit role caveats (ACLs remain preflight) |
| EV-CRYPTO-LOCATION | §1; ND-CHECKPOINT-01/11/16 | RECONSTRUCTED_REFERENCE_SCHEMA8 | Catalog extension/proc location | `pgcrypto` in `public`; `digest`/`gen_random_uuid` located there — not `research_crypto` | none for Rev8 design of pre-cutover crypto location | N/A for design acceptance | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-CRYPTO-LOCATION); manifest hash; NOT schema-9 target location |
| EV-DRIFT-START | §1; evidence window | PILOT_TIME_RUNTIME_REVALIDATION | Live catalog drift digest at evidence start | `UNKNOWN_UNTIL_RUNTIME_REVALIDATION` | PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED | `BLOCKED_RUNTIME_REVALIDATION_REQUIRED`; pilot/live/paid prohibited | Prior marker EV-DRIFT-START retained; reconstructed digest is not a historical live evidence-window marker |
| EV-DRIFT-END | §1; evidence window | PILOT_TIME_RUNTIME_REVALIDATION | Live catalog drift digest at evidence end | `UNKNOWN_UNTIL_RUNTIME_REVALIDATION` | PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED | `BLOCKED_RUNTIME_REVALIDATION_REQUIRED`; pilot/live/paid prohibited | Prior marker EV-DRIFT-END retained; reconstructed session match is not historical live drift proof |

---

## 5. Execution-time live preflight predicates (11 markers)

Each of the following is **not resolved**. Design may specify the predicate; current value remains `UNKNOWN_UNTIL_LIVE_PREFLIGHT`. Comparison uses §3 outcomes. Natural identity is OID-free. Mismatch is recorded; no silent normalization; no automatic repair.

### EV-ROLES

* **Live query:** inventory of relevant roles (`postgres`, `research_app`, `n8n_app`, `research_governance`, `research_test`, and any other research/n8n-scoped roles) with `rolcanlogin`, `rolinherit`, `rolsuper`, `rolcreaterole`, `rolcreatedb`.
* **Expected / permitted:** roles required by ND-CHECKPOINT-02 exist with designed LOGIN/NOINHERIT attributes; unexpected superuser/login expansions classified per §3.
* **Natural identity:** `rolname`.
* **vs reconstructed:** reconstructed only had disposable `postgres`/`research_app`/`n8n_app` placeholders — never treat reconstructed role list as historical live.
* **Mismatch classification:** `MISSING_REQUIRED_OBJECT`, `UNKNOWN_EXTRA_OBJECT`, `UNSAFE_UNDECLARED_VARIANCE`, or `SAFE_DECLARED_VARIANCE` only if an `ND-*` row permits.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-MEMBERSHIPS

* **Live query:** direct and transitive `pg_auth_members` paths among relevant roles with grantor and admin option.
* **Expected / permitted:** membership tuples required by ND-CHECKPOINT-02; no undeclared privilege-bearing memberships.
* **Natural identity:** `role_name` + `member_name` + `grantor_name` + `admin_option(t/f)`.
* **vs reconstructed:** reconstructed memberships are disposable-only.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNKNOWN_EXTRA_OBJECT`, `MISSING_REQUIRED_OBJECT`, `UNSAFE_UNDECLARED_VARIANCE`.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-SCHEMA-PRIVS

* **Live query:** schema USAGE/CREATE for `research`, `research_crypto` (if present), `n8n`, `public` for APP/N8N/GOV/TEST/PUBLIC.
* **Expected / permitted:** CREATE denied for runtime roles per ND-CHECKPOINT-02; USAGE as designed.
* **Natural identity:** `nspname` + grantee + privilege.
* **vs reconstructed:** reconstructed path did not replay Round0B init grants — reconstructed absence of grants is not proof of live absence.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNSAFE_UNDECLARED_VARIANCE`, `OWNER_MISMATCH` when coupled with owner drift.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-FUNCTION-ACLS

* **Live query:** per-function ACL expansion with `COALESCE(proacl, acldefault('f', proowner))` for every research function identity.
* **Expected / permitted:** freeze/restore EXECUTE surface per ND-FREEZE-REVOKE-EXECUTE / checkpoint contracts; no early EXECUTE to APP/N8N/PUBLIC/TEST where forbidden.
* **Natural identity:** function natural identity + grantee + privilege.
* **vs reconstructed:** migration-6 blanket GRANT is deterministic only if roles exist; not historical live ACL authority.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNSAFE_UNDECLARED_VARIANCE`, `MATCHES_RECONSTRUCTED_REFERENCE` when equal to reconstructed expansion **and** roles match live.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-FUNCTION-PUBLIC

* **Live query:** PUBLIC (OID 0) EXECUTE presence on each research function.
* **Expected / permitted:** PUBLIC EXECUTE absent except where an `ND-*` row explicitly permits.
* **Natural identity:** function natural identity + `PUBLIC` + `EXECUTE`.
* **vs reconstructed:** PUBLIC EXECUTE may appear in reconstructed ACLs due to defaults — not historical proof.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNSAFE_UNDECLARED_VARIANCE`.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-FUNCTION-EFFECTIVE

* **Live query:** effective EXECUTE considering direct/PUBLIC/inherited/SET ROLE/owner/superuser/schema-USAGE for every relevant role × function.
* **Expected / permitted:** ND-CHECKPOINT and freeze contracts; builders non-executable until restoration where required.
* **Natural identity:** function natural identity + role + final exercisable `t/f`.
* **vs reconstructed:** reconstructed effective matrix is non-authoritative.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNSAFE_UNDECLARED_VARIANCE`, `RUNTIME_STATE_MISMATCH` when session attributes alter exercisability.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-TABLE-ACLS

* **Live query:** per-table ACL expansion with `COALESCE(relacl, acldefault('r', relowner))`.
* **Expected / permitted:** checkpoint/freeze ACL contracts for governance/capacity/discrepancy tables and research base tables.
* **Natural identity:** `schemaname.relname` + grantee + privilege.
* **vs reconstructed:** post-migration GRANT surface only partially present in reconstruction.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNSAFE_UNDECLARED_VARIANCE`, `OWNER_MISMATCH`.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-TABLE-WRITES

* **Live query:** effective INSERT/UPDATE/DELETE for every discovered relevant role on every research base table.
* **Expected / permitted:** Direct WRITE NONE for runtime roles where ND-CHECKPOINT / ND-FREEZE-REVOKE-WRITES require it.
* **Natural identity:** `schemaname.relname` + role + `{INSERT|UPDATE|DELETE}` + effective `t/f`.
* **vs reconstructed:** reconstructed write matrix incomplete without init privilege path.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNSAFE_UNDECLARED_VARIANCE`.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-COLUMN-ACLS

* **Live query:** column ACL rows; null `attacl` means no column-specific grant.
* **Expected / permitted:** no undeclared column privilege expansions on sensitive columns.
* **Natural identity:** `schemaname.relname.attname` + grantee + privilege.
* **vs reconstructed:** reconstructed expansion uses non-historical roles.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNSAFE_UNDECLARED_VARIANCE`.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-COLUMN-EFFECTIVE

* **Live query:** effective column privileges for relevant roles.
* **Expected / permitted:** designed column privilege surface; no silent elevation.
* **Natural identity:** `schemaname.relname.attname` + role + privilege + effective `t/f`.
* **vs reconstructed:** non-authoritative.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `UNSAFE_UNDECLARED_VARIANCE`.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

### EV-DEFAULT-PRIVS

* **Live query:** `pg_default_acl` rows and owner provenance for `postgres` (and other owners if present) in `research` / `research_crypto`.
* **Expected / permitted:** revoke-all normative tuples per ND-CHECKPOINT-02/18; no future PUBLIC EXECUTE default for those schemas.
* **Natural identity:** `role_name` + `schema_name` + `objtype` + expanded ACL text with PUBLIC for OID 0.
* **vs reconstructed:** disposable EV-DEFACL reflects disposable state only.
* **Mismatch classification:** `PRIVILEGE_EXPANSION`, `PRIVILEGE_REDUCTION`, `MISSING_REQUIRED_OBJECT`, `UNSAFE_UNDECLARED_VARIANCE`.
* **Fail-closed:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen`.

---

## 6. Pilot-time runtime revalidation (3 markers)

Each is **not resolved**. Current value: `UNKNOWN_UNTIL_RUNTIME_REVALIDATION`. Pilot, live provider calls, workflow activation, and paid usage are prohibited until the gate resolves successfully.

### EV-SAFETY-BASELINE

* **Runtime state to inspect:** provider/model enabled flags; credential non-secret status fields; proposals; authorizations; envelopes; usage/paid-cost aggregates; workflow activation indicators.
* **Safe non-secret columns only:** enabled flags, status enums, counts, non-secret labels, timestamps of last change — never secret payloads, tokens, or credential material.
* **Freshness:** observation immediately before enabling pilot/live/paid; evidence older than the governed enablement window is stale → fail.
* **Expected state:** Gemini/provider pilot remains disabled until explicit authorization; no paid usage without authorization; credential health must match governance decision — exact permitted tuples defined by future Phase 3 architecture citing this gate, not invented here.
* **Mismatch behavior:** `RUNTIME_STATE_MISMATCH` → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED`.
* **Prohibition:** no pilot enablement, live calls, workflow activation, or paid usage until resolved.

### EV-DRIFT-START

* **Runtime state to inspect:** catalog drift digest at the start of the live evidence window immediately before the governed operation.
* **Safe non-secret columns:** OID-free digest payload fields only.
* **Freshness:** must be captured at evidence-window start for the same operation that will use EV-DRIFT-END.
* **Expected state:** digest algorithm and covered object set as defined by Decision Record encoding conventions; value itself is live-observed, not reconstructed.
* **Mismatch behavior:** missing/stale start digest → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED`.
* **Prohibition:** no pilot/live/paid until start+end drift pair validates.

### EV-DRIFT-END

* **Runtime state to inspect:** catalog drift digest at evidence-window end.
* **Safe non-secret columns:** OID-free digest payload fields only.
* **Freshness:** must pair with EV-DRIFT-START from the same window; end before start is invalid.
* **Expected state:** equality with start when the operation forbids catalog mutation; any undeclared drift → `RUNTIME_STATE_MISMATCH`.
* **Mismatch behavior:** `RUNTIME_STATE_MISMATCH` or missing end digest → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED` / `failed_frozen` if already in governed state.
* **Prohibition:** no pilot/live/paid until resolved.

---

## 7. Fail-closed behavior (summary)

| Condition | Behavior |
| --- | --- |
| Missing execution-time live preflight for any of the 11 markers | `BLOCKED_LIVE_PREFLIGHT_REQUIRED` |
| Preflight mismatch other than `MATCHES_RECONSTRUCTED_REFERENCE` or permitted `SAFE_DECLARED_VARIANCE` | block or `failed_frozen` |
| Missing/stale pilot-time runtime revalidation for any of the 3 markers | `BLOCKED_RUNTIME_REVALIDATION_REQUIRED` |
| Attempt to treat reconstructed evidence as historical live | prohibited; documentation defect |
| Invented default for unknown deferred fact | prohibited |
| Automatic repair of privilege/object mismatch | prohibited |

---

## 8. Future Phase 3 obligations

Revision 8 Phase 3 architecture (when authorized) **must**:

* may use the 17 reconstructed-reference facts;
* must label them as reconstructed (`RECONSTRUCTED_REFERENCE_SCHEMA8` / `RECONSTRUCTED_REFERENCE_ACCEPTED`);
* must not call them live catalog observations;
* must include executable preflight predicates for all 11 live-dependent markers;
* must include runtime gates for all 3 runtime-dependent markers;
* must represent unresolved values as unknown (`UNKNOWN_UNTIL_LIVE_PREFLIGHT` / `UNKNOWN_UNTIL_RUNTIME_REVALIDATION`);
* must not invent a default;
* must fail closed when required evidence is unavailable;
* must include provenance on every inventory and checkpoint row (including canonical manifest hash when citing reconstructed reference).

Phase 3 is **not** authorized by this document alone.

---

## 9. Future Phase 4 obligations

Phase 4 tests **must** include:

* reconstructed-reference match;
* live-catalog exact match;
* safe declared variance;
* unknown extra object;
* missing required object;
* privilege expansion;
* privilege reduction;
* ownership mismatch;
* reconstructed/live digest mismatch;
* runtime revalidation missing;
* runtime evidence stale;
* no live catalog available;
* fail-closed behavior for every unresolved evidence class.

Expected test calculations must remain independent from the production preflight implementation.

---

## 10. Disposable audit environment (record only)

| Field | Value |
| --- | --- |
| container | `srl-schema8-reconstruction-20260801_151349` |
| status | exited (audit-preserved; do not restart) |
| volume | `srl_schema8_reconstruction_20260801_151349` (preserved) |
| network | `srl_schema8_reconstruction_net_20260801_151349` |
| cleanup authorized | false |
| cleanup performed | no |

Do not restart, delete, or alter the container, volume, or database. Do not rerun migrations or catalog extraction.

---

## 11. Encoding of classed markers

Prior generic form (superseded for unresolved catalog dependence):

```text
EVIDENCE_REQUIRED(EV-...)
```

Amended classed forms (original EV identity preserved):

```text
RECONSTRUCTED_REFERENCE_ACCEPTED(EV-...)
EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-...)
PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-...)
```

When a Decision Record cell lists multiple EV identifiers of different classes, each identifier appears under its class wrapper; compound cells may join wrappers with `; `.
