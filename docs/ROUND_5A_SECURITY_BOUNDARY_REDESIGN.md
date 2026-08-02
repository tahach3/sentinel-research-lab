# Round 5A — Security Boundary Redesign

**Revision:** 8 — Evidence-Class-Aware Architecture
**Status:** DESIGN ONLY. Not schema-9 implementation.
**Supersedes:** Revision 7 content of this file (commit `5e705abc7e8958809cfb3dd41cbc38345585821b` and subsequent Revision 7 text).
**Baseline HEAD at Phase 3 authoring:** `7f10e1e32f7f0df2255b70d624ec3928b4c33737`
**Phase 2 Decision Record:** `docs/ROUND_5A_REVISION_8_NORMATIVE_DECISION_RECORD.md` (commit `eb1d0b7a936df8ed98cd7a0913457fdeb208e233`)
**Phase 2 Evidence Policy:** `docs/ROUND_5A_REVISION_8_EVIDENCE_POLICY.md` (commit `7f10e1e32f7f0df2255b70d624ec3928b4c33737`)
**Reconstructed-reference manifest SHA-256:** `09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2`
**Evidence crosswalk SHA-256:** `9D38F04D3BE2B519C59837ACD825B9DD74CA3724D793BAC7495B29C4B66E141F`
**Evidence root (audit):** `C:\Users\tahai\AppData\Local\Temp\srl-schema8-reconstruction-20260801_151349`
**Evidence class of reference artifacts:** `RECONSTRUCTED_REFERENCE_SCHEMA8`

```text
REVISION 8 ARCHITECTURE: DESIGN ONLY
SCHEMA 9 IMPLEMENTATION: NOT AUTHORIZED
ROUND 5B: NOT STARTED
LIVE PILOT: NOT STARTED
```

## Absolute limitation

Historical live schema-8 catalog state was **not** recovered. Schema-8 reference evidence was reconstructed by restoring a schema-5 backup and replaying authoritative migrations 6–8 in an isolated disposable PostgreSQL environment. Reconstruction does **not** prove post-backup manual grants, roles, ACLs, default privileges, runtime rows, credential health, provider/model enablement, workflow activation, or paid usage. Reconstructed evidence must not be labeled or treated as `LIVE_CATALOG`, historical live catalog, current production state, or recovered production state.

Marker disposition (Evidence Policy + Decision Record Evidence-Class Amendment): **31** total; **17** `RECONSTRUCTED_REFERENCE_ACCEPTED`; **11** `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` (`UNKNOWN_UNTIL_LIVE_PREFLIGHT`); **3** `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED` (`UNKNOWN_UNTIL_RUNTIME_REVALIDATION`); **0** ambiguous; **0** unclassified; **0** falsely labeled `LIVE_CATALOG`.

---

## 0. Mandatory provenance model

Every normative inventory row, checkpoint, reconciliation rule, state predicate, digest rule, and execution gate cites:

1. at least one `ND-*` decision identifier;
2. the applicable evidence-class marker;
3. an `EV-*` reference where evidence exists.

Exact evidence labels:

```text
RECONSTRUCTED_REFERENCE_ACCEPTED(EV-...)
EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-...)
PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-...)
```

For reconstructed citations:

```text
Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8
Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2
SOURCE_BACKUP_SCHEMA=5
REPLAYED_MIGRATIONS=6,7,8
NOT_HISTORICAL_LIVE_CATALOG=true
```

Deferred facts use exactly `UNKNOWN_UNTIL_LIVE_PREFLIGHT` or `UNKNOWN_UNTIL_RUNTIME_REVALIDATION`. Invented defaults are prohibited. Generic `EVIDENCE_REQUIRED(...)` is banned.

Non-normative note (banned terms): this architecture must not positively claim `bijection`, `historical live catalog reproduced`, `all evidence resolved`, `uniform function ACL`, `research_app DELETE on every table`, `all roles are fixed`, `reasonable default`, or `assume current value`.

---

## 1. Evidence precedence and comparison outcomes

**ND reference:** Decision Record §Revision 8 Evidence-Class Amendment; Evidence Policy §§2–3.

Ordered precedence (highest first):

```text
1. current LIVE_CATALOG
2. execution-time live preflight
3. reconstructed reference
4. migration intent or prose
```

Architecture rules:

* observed live state overrides reconstructed expectations;
* mismatch produces a recorded discrepancy — never silent normalization;
* migration intent never overrides catalog evidence;
* undeclared variance blocks execution;
* no automatic privilege or ownership repair;
* unavailable required evidence fails closed.

Comparison outcomes (exactly one per live-vs-reconstructed check):

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

Proceed only on `MATCHES_RECONSTRUCTED_REFERENCE`, or `SAFE_DECLARED_VARIANCE` when an explicit `ND-*` row permits that variance. All other outcomes → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` (pre-execution) or `failed_frozen` (governed migration).

---

## 2. Threat model (normative target; privileges gated)

**ND reference:** retained Revision 7 threat framing; privilege cells gated by `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED`.

Must eliminate at the privilege and ownership layer:

1. Session-GUC activation
2. Mutable/deletable capacity evidence
3. Application-callable approval/arm helpers
4. Direct envelope insertion
5. Schema-CREATE shadow objects against SECURITY DEFINER resolution
6. Unqualified name resolution via `search_path` / `pg_temp` / `public`
7. Unqualified cryptographic or UUID functions

Adversary model: `research_app` / `n8n_app` with any SQL allowed by their grants, including `set_config`, `SET ROLE` attempts, `CREATE` attempts, and `PUBLIC` defaults. Current live grants for those roles are `UNKNOWN_UNTIL_LIVE_PREFLIGHT` (`EV-ROLES`, `EV-MEMBERSHIPS`, `EV-SCHEMA-PRIVS`, `EV-FUNCTION-*`, `EV-TABLE-*`, `EV-COLUMN-*`, `EV-DEFAULT-PRIVS`).

---

## 3. Marker master inventory (all 31)

| Marker | Evidence class disposition | Current value for architecture | Gate | Provenance |
| --- | --- | --- | --- | --- |
| `EV-PG-VERSION` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1) on x86_64-pc-linux-gnu... (reconstructed image/version string) | none for Rev8 design of engine string | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-DIGEST / baseline` |
| `EV-SCHEMA-VERSION` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | max(version)=8; rows 1–8 present through Round 5A final | none for Rev8 design of ladder | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT / cutover baseline` |
| `EV-SCHEMAS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | schemas research, n8n, public; research/n8n owners postgres at restore | none for Rev8 design of presence | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-01/02/17` |
| `EV-EXTENSIONS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | pgcrypto/public; uuid-ossp/n8n; vector/public; plpgsql/pg_catalog | none for Rev8 design | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-01; ND-DIGEST` |
| `EV-FUNCTIONS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | 52 research functions; natural identities captured; OWNER postgres; prosecdef=f in reconstruction | none for Rev8 design of identities | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` |
| `EV-TABLES` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | 48 research base tables; no schema-9 tables | none for Rev8 design of identities | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-03/08/10/17` |
| `EV-COLUMNS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | research columns enumerated incl. pilot_capacity_reservations PK id and State columns | none for Rev8 design | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-IDENTITY-*; ND-RECON-*` |
| `EV-VIEWS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | 23 research views incl. v_gemini_pilot_5a | none for Rev8 design | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-17` |
| `EV-SEQUENCES` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | empty research sequence inventory (0 rows) | none for Rev8 design empty-set | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-17` |
| `EV-TRIGGERS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | 28 research triggers incl. provider_authorization_validity_guard | none for Rev8 design | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-14` |
| `EV-RLS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | empty research pg_policies inventory (0 rows) | none for Rev8 design empty-set | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-DIGEST / baseline` |
| `EV-CONSTRAINTS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | 266 constraint rows captured | none for Rev8 design | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-04/08/10; ND-RECON` |
| `EV-INDEXES` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | 76 index rows captured | none for Rev8 design | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-03/04/08/10` |
| `EV-RESERVATION-STATE` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | pilot_capacity_reservations exists; 0 rows; State A/B/C empty in reconstruction | none for Rev8 design of empty inventory shape | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-IDENTITY-SOURCE; ND-STATE-A/B` |
| `EV-CUTOVER-STATE` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | no schema_version=9; no research_crypto; no taha_governance_actions / accounting_discrepancies | none for Rev8 design of pre-schema-9 absence | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-COMMON` |
| `EV-HELPER-FUNCTIONS` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | helper identities/locations in research post-migration (ACL portions remain preflight) | none for Rev8 design of identities | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` |
| `EV-CRYPTO-LOCATION` | `RECONSTRUCTED_REFERENCE_ACCEPTED` | pgcrypto in public; digest/gen_random_uuid located there — not research_crypto | none for Rev8 design of pre-cutover location | RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; `ND-CHECKPOINT-01/11/16` |
| `EV-ROLES` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-MEMBERSHIPS` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-SCHEMA-PRIVS` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-FUNCTION-ACLS` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-FUNCTION-PUBLIC` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-FUNCTION-EFFECTIVE` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-TABLE-ACLS` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-TABLE-WRITES` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-COLUMN-ACLS` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-COLUMN-EFFECTIVE` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-DEFAULT-PRIVS` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED` → `BLOCKED_LIVE_PREFLIGHT_REQUIRED` / `failed_frozen` | Prior marker retained; Evidence Policy §5; Decision Record marker inventory |
| `EV-SAFETY-BASELINE` | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED` | `UNKNOWN_UNTIL_RUNTIME_REVALIDATION` | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED` → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED` | Prior marker retained; Evidence Policy §6; Decision Record marker inventory |
| `EV-DRIFT-START` | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED` | `UNKNOWN_UNTIL_RUNTIME_REVALIDATION` | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED` → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED` | Prior marker retained; Evidence Policy §6; Decision Record marker inventory |
| `EV-DRIFT-END` | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED` | `UNKNOWN_UNTIL_RUNTIME_REVALIDATION` | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED` → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED` | Prior marker retained; Evidence Policy §6; Decision Record marker inventory |

---

## 4. Exact reconstructed inventories (17 markers)

Inventory column contract for every normative reconstructed row:

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |

### 4.1 EV-PG-VERSION

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `pg_version` | PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-PG-VERSION` | `ND-DIGEST-CHECKPOINT-V1 encoding baseline` | N for Rev8 design; host identity operationally subject to live preflight when material | record discrepancy; do not treat as historical live host |

Provenance: RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; artifact `schema8_catalog.txt` row `pg_version`.

### 4.2 EV-SCHEMA-VERSION

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.schema_version.max(version)` | 8 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.schema_version.version=1` | Round 0B foundation: schemas, roles, pgvector | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | failed_frozen if ladder incomplete at cutover start after live confirm |
| `research.schema_version.version=2` | Round 1: provider benchmarking evidence schema | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | failed_frozen if ladder incomplete at cutover start after live confirm |
| `research.schema_version.version=3` | Round 2: research question and decision lifecycle | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | failed_frozen if ladder incomplete at cutover start after live confirm |
| `research.schema_version.version=4` | Round 3: simulated multi-model research orchestration (mock adapters only) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | failed_frozen if ladder incomplete at cutover start after live confirm |
| `research.schema_version.version=5` | Round 4: gated live provider readiness and budget controls (disabled; no live calls) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | failed_frozen if ladder incomplete at cutover start after live confirm |
| `research.schema_version.version=6` | Round 5A: Gemini bounded pilot preparation (disabled; awaiting Taha credential) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | failed_frozen if ladder incomplete at cutover start after live confirm |
| `research.schema_version.version=7` | Round 5A repair: 24h approval expiry + aggregate pilot preflight + residue revoke | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | failed_frozen if ladder incomplete at cutover start after live confirm |
| `research.schema_version.version=8` | Round 5A final: immutable activation + atomic pilot capacity reservations | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMA-VERSION` | `ND-CHECKPOINT-COMMON` | N for Rev8 design | failed_frozen if ladder incomplete at cutover start after live confirm |

Provenance: RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; artifacts `final_schema_version.txt`, `schema8_verify.txt`.

### 4.3 EV-SCHEMAS

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `nspname=research` | present; owner=postgres at restore time (ownership may diverge historically) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMAS` | `ND-CHECKPOINT-01/02/17` | owner subject to live observation when ownership material | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `nspname=n8n` | present; owner=postgres at restore time | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMAS` | `ND-CHECKPOINT-01/02/17` | owner subject to live observation when ownership material | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `nspname=public` | present; owner=pg_database_owner at restore time | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMAS` | `ND-CHECKPOINT-01/02/17` | N for Rev8 design of presence | UNKNOWN_EXTRA_OBJECT / OWNER_MISMATCH as applicable |
| `nspname=research_crypto` | ABSENT in reconstructed schema-8 (schema-9 target only) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SCHEMAS; EV-CUTOVER-STATE; EV-CRYPTO-LOCATION` | `ND-CHECKPOINT-01` | N for Rev8 pre-cutover absence fact | if present before CP-01 unexpectedly → UNSAFE_UNDECLARED_VARIANCE |

### 4.4 EV-EXTENSIONS

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `extname=pgcrypto + extschema=public` | present (pre-cutover; NOT research_crypto) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-EXTENSIONS; EV-CRYPTO-LOCATION` | `ND-CHECKPOINT-01` | N for Rev8 design of pre-cutover location | OWNER_MISMATCH / MISSING_REQUIRED_OBJECT |
| `extname=uuid-ossp + extschema=n8n` | present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-EXTENSIONS` | `ND-DIGEST-CHECKPOINT-V1` | N | MISSING_REQUIRED_OBJECT |
| `extname=vector + extschema=public` | present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-EXTENSIONS` | `ND-DIGEST-CHECKPOINT-V1` | N | MISSING_REQUIRED_OBJECT |
| `extname=plpgsql + extschema=pg_catalog` | present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-EXTENSIONS` | `ND-DIGEST-CHECKPOINT-V1` | N | MISSING_REQUIRED_OBJECT |

### 4.5 EV-CRYPTO-LOCATION

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `pgcrypto.extschema` | public (reconstructed pre-cutover) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CRYPTO-LOCATION` | `ND-CHECKPOINT-01/11/16` | N for Rev8 design | failed_frozen if CP-01 cannot relocate |
| `digest / gen_random_uuid location` | located with pgcrypto in public — NOT research_crypto | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CRYPTO-LOCATION` | `ND-CHECKPOINT-01/11/16` | N for Rev8 design | failed_frozen if unqualified shadows remain after CP-01 |

### 4.6 EV-TABLES (48 research base tables)

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.automatic_scores` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.benchmark_cases` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.benchmark_runs` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.benchmark_suites` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.decision_rationales` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.evidence_claim_links` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.evidence_items` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.gemini_pilot_request_builder_specs` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.improvement_proposals` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.live_request_envelopes` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.model_outputs` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.models` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.monthly_role_rankings` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.orchestration_failures` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.pilot_capacity_reservations` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.proposal_versions` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_adapter_requests` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_adapter_responses` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_adapter_versions` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_authorization_records` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_budget_policies` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_capabilities` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_credential_status` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_health_checks` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_model_candidates` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_pilot_proposals` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_policy_verifications` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_rate_limit_policies` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.provider_usage_ledger` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.providers` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.question_status_transitions` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.reconsideration_conditions` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.repair_attempts` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_closure_records` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_findings` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_priorities` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_question_relationships` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_question_versions` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_questions` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_run_stages` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_runs` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.research_status_history` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.run_failures` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.schema_version` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.source_snapshots` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.sources` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.taha_decisions` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.taha_scores` | base table present; owner=postgres; relkind=r; no schema-9 cutover tables | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES` | `ND-CHECKPOINT-03/08/10/17; ND-IDENTITY-SOURCE` | ACLs/writes: Y via EV-TABLE-ACLS/EV-TABLE-WRITES | MISSING_REQUIRED_OBJECT / OWNER_MISMATCH |
| `research.taha_governance_actions` | ABSENT (schema-9 target) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES; EV-CUTOVER-STATE` | `ND-CHECKPOINT-03` | N for pre-cutover absence | UNKNOWN_EXTRA_OBJECT if present early without CP |
| `research.accounting_discrepancies` | ABSENT (schema-9 target) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES; EV-CUTOVER-STATE` | `ND-CHECKPOINT-08` | N for pre-cutover absence | UNKNOWN_EXTRA_OBJECT if present early without CP |
| `research.pilot_capacity_events` | ABSENT (schema-9 target) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES; EV-CUTOVER-STATE` | `ND-CHECKPOINT-10` | N for pre-cutover absence | UNKNOWN_EXTRA_OBJECT if present early without CP |
| `research.legacy_reservation_archive` | ABSENT (schema-9 target) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TABLES; EV-CUTOVER-STATE` | `ND-CHECKPOINT-10` | N for pre-cutover absence | UNKNOWN_EXTRA_OBJECT if present early without CP |

### 4.7 EV-FUNCTIONS (52 research functions)

Natural identity = `research.<proname>(<args>)` + owner + prosecdef(t/f). ACL cells are **not** asserted here.

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research._allowed_source_ids(p_question_uuid uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._append_completed_stage(p_run_id uuid, p_stage text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._evidence_bundle_for_question(p_question_uuid uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r3_clone_question(p_code text, p_scenario text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r3_new_run(p_code text, p_qid uuid, p_scenario text, p_budget numeric)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r4_arm_provider(p_code text, p_enable_provider boolean, p_enable_model boolean, p_verify_model boolean, p_free_confirmed boolean, p_cred_present boolean, p_daily_req integer, p_daily_tok integer)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r4_case_id()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r4_make_auth(p_provider text, p_model_id uuid, p_case uuid, p_max_req integer, p_max_tok integer, p_max_cost numeric, p_expires timestamp with time zone)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r4_reset_defaults()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r5a_final_arm_gates()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r5a_final_reset_defaults()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._r5a_insert_fixture_auth(p_fixture text, p_pilot uuid, p_case uuid, p_provider uuid, p_model uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research._record_failure(p_run_id uuid, p_stage text, p_class text, p_detail text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.build_decision_card(p_run_id uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.build_provider_request_envelope(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_canonical_request jsonb, p_claimed_credential_status text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.cancel_research_run(p_run_id uuid, p_reason text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.cleanup_test_fixture(p_fixture_id text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.compute_priority_v1(constitutional_impact numeric, measured_performance_gap numeric, safety_impact numeric, expected_value numeric, urgency numeric, evidence_availability numeric, implementation_cost numeric, duplication_penalty numeric)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.enforce_completed_run_evidence()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.estimate_provider_cost_usd(p_provider_code text, p_input_tokens integer, p_output_tokens integer)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.forbid_mutation()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.forbid_terminal_run_wipe()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.gemini_pilot_5a_gate_status()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.live_preflight(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_claimed_credential_status text, p_projected_input_tokens integer, p_projected_output_tokens integer, p_is_retry boolean, p_fallback_provider text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.materialize_proposal_from_run(p_run_id uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.mock_adapter_invoke(p_request_id uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.mock_model_for_stage(p_stage text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.mock_provider_for_stage(p_stage text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.orchestrate_research_run(p_run_id uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.parse_provider_fixture_response(p_provider_code text, p_fixture jsonb)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.pilot_capacity_snapshot(p_pilot_id uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.pilot_case_attempt_count(p_pilot_id uuid, p_benchmark_case_id uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.proposal_has_evidence(p_evidence_ids uuid[])` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.record_authorization_spend(p_authorization_id uuid, p_requests integer, p_tokens integer, p_cost numeric, p_note text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.record_pilot_usage_for_tests(p_authorization_id uuid, p_input_tokens integer, p_output_tokens integer, p_success boolean, p_fixture_id text, p_is_retry boolean)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.run_stage(p_run_id uuid, p_stage text, p_scenario_hint text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.sha256_hex(p_text text)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_authorization_validity_guard()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_block_evidence_delete_after_decision()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_envelope_immutability()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_evidence_immutable_body()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_proposal_ready_requires_evidence()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_question_decision_requires_supported_proposal()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_question_status_change()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_question_status_history()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_question_status_validate()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_run_stage_immutable()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_set_priority_scores()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_sync_question_priority()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.trg_usage_ledger_immutability()` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |
| `research.try_enter_decision_from_partial(p_run_id uuid)` | owner=postgres; prosecdef=f in reconstruction (INVOKER observed); natural identity present | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-FUNCTIONS` | `ND-CHECKPOINT-05..16; ND-FREEZE-REVOKE-EXECUTE` | ACLs/effective: Y via EV-FUNCTION-ACLS/PUBLIC/EFFECTIVE | MISSING_REQUIRED_OBJECT |

Keep-EXECUTE freeze name set (normative names; identities confirmed by EV-FUNCTIONS): `gemini_pilot_5a_gate_status`, `sha256_hex`, `compute_priority_v1`, `proposal_has_evidence`, `estimate_provider_cost_usd`, `pilot_capacity_snapshot`, `pilot_case_attempt_count` — **ND-FREEZE-REVOKE-EXECUTE**. Current EXECUTE grants: `UNKNOWN_UNTIL_LIVE_PREFLIGHT`.

### 4.8 EV-HELPER-FUNCTIONS

Helpers observed in reconstructed `research` (identities only; ACLs preflight):

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research._r3_clone_question(p_code text, p_scenario text)` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r3_new_run(p_code text, p_qid uuid, p_scenario text, p_budget numeric)` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r4_arm_provider(p_code text, p_enable_provider boolean, p_enable_model boolean, p_verify_model boolean, p_free_confirmed boolean, p_cred_present boolean, p_daily_req integer, p_daily_tok integer)` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r4_case_id()` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r4_make_auth(p_provider text, p_model_id uuid, p_case uuid, p_max_req integer, p_max_tok integer, p_max_cost numeric, p_expires timestamp with time zone)` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r4_reset_defaults()` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r5a_final_arm_gates()` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r5a_final_reset_defaults()` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r5a_insert_fixture_auth(p_fixture text, p_pilot uuid, p_case uuid, p_provider uuid, p_model uuid)` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research.cleanup_test_fixture(p_fixture_id text)` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research.record_pilot_usage_for_tests(p_authorization_id uuid, p_input_tokens integer, p_output_tokens integer, p_success boolean, p_fixture_id text, p_is_retry boolean)` | present in research post-migration; final disposition MOVED TO research_test / EXECUTE NONE for APP/N8N/GOV/PUBLIC per ND-CHECKPOINT-15 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST` | Y (EV-FUNCTION-EFFECTIVE) | helper still APP-executable in research → failed_frozen |
| `research._r5a_assert_final_pilot_state()` | NOT present in reconstructed catalog; ND-CHECKPOINT-15 permits absent OR EXECUTE NONE | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15` | Y if appears live | if present with APP EXECUTE → failed_frozen |
| `research._r5a_final_assert_state()` | NOT present in reconstructed catalog; ND-CHECKPOINT-15 permits absent OR EXECUTE NONE | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15` | Y if appears live | if present with APP EXECUTE → failed_frozen |
| `research._r5a_repair_reset_defaults()` | NOT present in reconstructed catalog; ND-CHECKPOINT-15 permits absent OR EXECUTE NONE | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-HELPER-FUNCTIONS` | `ND-CHECKPOINT-15` | Y if appears live | if present with APP EXECUTE → failed_frozen |

### 4.9 EV-VIEWS (23)

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.v_active_research_queue` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_cost_per_successful_run` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_decision_history_by_topic` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_duplicate_question_warnings` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_enabled_provider_readiness` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_failure_rate` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_gemini_pilot_5a` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_highest_priority_unanswered` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_insufficient_evidence_warning` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_latency_percentile_summary` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_latest_monthly_ranking` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_missing_credentials` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_models_awaiting_verification` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_proposals_awaiting_taha` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_provider_health_summary` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_provider_performance_by_role` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_questions_blocked_missing_evidence` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_rejected_eligible_reconsideration` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_remaining_daily_quota` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_remaining_monthly_budget` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_settled_questions` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_simulated_decision_cards` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |
| `research.v_unauthorized_call_warnings` | view present; owner=postgres expected by ownership_locked target | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-VIEWS` | `ND-CHECKPOINT-17` | privilege cells via live preflight when required | MISSING_REQUIRED_OBJECT |

### 4.10 EV-SEQUENCES

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.* sequences` | empty inventory (0 rows) — reconstructed empty-set fact | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-SEQUENCES` | `ND-CHECKPOINT-17` | N for empty-set design fact | UNKNOWN_EXTRA_OBJECT if sequences appear undeclared |

### 4.11 EV-TRIGGERS (28)

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.automatic_scores.automatic_scores_no_update` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.benchmark_runs.benchmark_runs_completion_evidence` | tgenabled=O; function=research.enforce_completed_run_evidence | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.benchmark_runs.benchmark_runs_no_uncomplete` | tgenabled=O; function=research.forbid_terminal_run_wipe | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.decision_rationales.decision_rationales_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.evidence_items.evidence_items_immutable_body` | tgenabled=O; function=research.trg_evidence_immutable_body | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.evidence_items.evidence_items_no_delete` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.improvement_proposals.improvement_proposals_evidence_guard` | tgenabled=O; function=research.trg_proposal_ready_requires_evidence | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.live_request_envelopes.live_request_envelopes_immutability` | tgenabled=O; function=research.trg_envelope_immutability | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.model_outputs.model_outputs_no_update` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.orchestration_failures.orchestration_failures_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.provider_adapter_requests.provider_adapter_requests_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.provider_adapter_responses.provider_adapter_responses_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.provider_authorization_records.provider_authorization_no_delete` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.provider_authorization_records.provider_authorization_validity_guard` | tgenabled=O; function=research.trg_authorization_validity_guard | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.provider_usage_ledger.provider_usage_ledger_immutability` | tgenabled=O; function=research.trg_usage_ledger_immutability | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.repair_attempts.repair_attempts_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.research_closure_records.research_closure_records_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.research_priorities.research_priorities_compute` | tgenabled=O; function=research.trg_set_priority_scores | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.research_priorities.research_priorities_sync_question` | tgenabled=O; function=research.trg_sync_question_priority | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.research_questions.research_questions_decision_gate` | tgenabled=O; function=research.trg_question_decision_requires_supported_proposal | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.research_questions.research_questions_status_history` | tgenabled=O; function=research.trg_question_status_history | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.research_questions.research_questions_status_validate` | tgenabled=O; function=research.trg_question_status_validate | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.research_run_stages.research_run_stages_immutable` | tgenabled=O; function=research.trg_run_stage_immutable | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.research_status_history.research_status_history_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.run_failures.run_failures_no_update` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.source_snapshots.source_snapshots_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.taha_decisions.taha_decisions_no_mutation` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |
| `research.taha_scores.taha_scores_no_update` | tgenabled=O; function=research.forbid_mutation | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-TRIGGERS` | `ND-CHECKPOINT-14` | N for identity; enablement rechecked at CP-14 | disabled/missing/extra → failed_frozen at CP-14 |

### 4.12 EV-RLS

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.pg_policies` | empty inventory (0 rows) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-RLS` | `ND-DIGEST-CHECKPOINT-V1 baseline` | N for empty-set design fact | UNKNOWN_EXTRA_OBJECT if undeclared policies appear |

### 4.13 EV-COLUMNS (reservation + identity-critical excerpt)

Full research column natural identities are enumerated in reconstructed `schema8_catalog.txt` / information_schema after replay. Identity-critical reservation columns:

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.pilot_capacity_reservations.id` | uuid NOT NULL; PRIMARY KEY — ND-IDENTITY-SOURCE | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.pilot_proposal_id` | uuid NOT NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.authorization_id` | uuid NOT NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.benchmark_case_id` | uuid NOT NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.idempotency_key` | text NOT NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.projected_input_tokens` | integer NOT NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.projected_output_tokens` | integer NOT NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.projected_cost_usd` | numeric NOT NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.envelope_id` | uuid NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.status` | text NOT NULL; CHECK reserved|finalized|released | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.test_fixture_id` | text NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |
| `research.pilot_capacity_reservations.created_at` | timestamptz NOT NULL | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-COLUMNS; EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-RECON-01..21` | column ACLs: Y via EV-COLUMN-ACLS | BLOCKED_MISSING_INPUT / failed_frozen |

### 4.14 EV-CONSTRAINTS (266 rows — full natural identities)

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.automatic_scores.automatic_scores_dimension_check` | contype=c; def=CHECK ((dimension = ANY (ARRAY['factual_accuracy'::text, 'evidence_quality'::text, 'instruction_compliance'::text, 'reasoning_completeness'::text, 'output_structure'::text, 'citation_correctness'::text, 'hallucination_rate'::text, 'latency'::text, 'token_use'::text, 'cost'::text, 'retry_rate'::text, 'rate_limit_failures'::text, 'schema_valid_response_rate'::text, 'agreement_with_taha'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.automatic_scores.automatic_scores_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.automatic_scores.automatic_scores_range` | contype=c; def=CHECK (((score >= (0)::numeric) AND (score <= (100)::numeric))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.automatic_scores.automatic_scores_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.benchmark_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases.benchmark_cases_cost_nonneg` | contype=c; def=CHECK ((max_cost_usd >= (0)::numeric)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases.benchmark_cases_fingerprint_sha256` | contype=c; def=CHECK ((input_fingerprint ~ '^[a-f0-9]{64}$'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases.benchmark_cases_kind_check` | contype=c; def=CHECK ((case_kind = ANY (ARRAY['normal'::text, 'ambiguous'::text, 'adversarial'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases.benchmark_cases_latency_positive` | contype=c; def=CHECK ((max_latency_ms > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases.benchmark_cases_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases.benchmark_cases_suite_code_unique` | contype=u; def=UNIQUE (suite_id, case_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases.benchmark_cases_suite_id_fkey` | contype=f; def=FOREIGN KEY (suite_id) REFERENCES research.benchmark_suites(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases.benchmark_cases_tokens_positive` | contype=c; def=CHECK ((max_token_budget > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_case_id_fkey` | contype=f; def=FOREIGN KEY (case_id) REFERENCES research.benchmark_cases(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_cost_nonneg` | contype=c; def=CHECK (((cost_usd_estimate IS NULL) OR (cost_usd_estimate >= (0)::numeric))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_execution_identity_unique` | contype=u; def=UNIQUE (execution_identity) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_fingerprint_sha256` | contype=c; def=CHECK ((input_fingerprint ~ '^[a-f0-9]{64}$'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_latency_nonneg` | contype=c; def=CHECK (((latency_ms IS NULL) OR (latency_ms >= 0))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_model_id_fkey` | contype=f; def=FOREIGN KEY (model_id) REFERENCES research.models(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_retry_nonneg` | contype=c; def=CHECK ((retry_count >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'failed'::text, 'cancelled'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs.benchmark_runs_tokens_nonneg` | contype=c; def=CHECK ((((prompt_tokens IS NULL) OR (prompt_tokens >= 0)) AND ((completion_tokens IS NULL) OR (completion_tokens >= 0)) AND ((total_tokens IS NULL) OR (total_tokens >= 0)))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_suites.benchmark_suites_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_suites.benchmark_suites_role_check` | contype=c; def=CHECK ((role_code = ANY (ARRAY['researcher'::text, 'planner'::text, 'implementation_proposal_writer'::text, 'qa_checker'::text, 'independent_reviewer'::text, 'debugger'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_suites.benchmark_suites_role_version_unique` | contype=u; def=UNIQUE (role_code, suite_version) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.decision_rationales.decision_rationales_decision_id_fkey` | contype=f; def=FOREIGN KEY (decision_id) REFERENCES research.taha_decisions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.decision_rationales.decision_rationales_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.decision_rationales.dr_rationale_nonempty` | contype=c; def=CHECK ((length(TRIM(BOTH FROM concise_rationale)) > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_claim_links.ecl_stance_check` | contype=c; def=CHECK ((stance = ANY (ARRAY['supports'::text, 'contradicts'::text, 'contextual'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_claim_links.evidence_claim_links_evidence_id_fkey` | contype=f; def=FOREIGN KEY (evidence_id) REFERENCES research.evidence_items(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_claim_links.evidence_claim_links_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_claim_links.evidence_claim_links_question_id_fkey` | contype=f; def=FOREIGN KEY (question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_items.evidence_confidence_range` | contype=c; def=CHECK (((confidence_score >= (0)::numeric) AND (confidence_score <= (100)::numeric))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_items.evidence_excerpt_maxlen` | contype=c; def=CHECK ((char_length(quoted_excerpt) <= 1000)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_items.evidence_items_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_items.evidence_items_source_snapshot_id_fkey` | contype=f; def=FOREIGN KEY (source_snapshot_id) REFERENCES research.source_snapshots(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_items.evidence_items_supersedes_evidence_id_fkey` | contype=f; def=FOREIGN KEY (supersedes_evidence_id) REFERENCES research.evidence_items(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_items.evidence_reliability_check` | contype=c; def=CHECK ((reliability_class = ANY (ARRAY['high'::text, 'medium'::text, 'low'::text, 'unverified'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_items.evidence_version_positive` | contype=c; def=CHECK ((version_number >= 1)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_findings.findings_confidence_range` | contype=c; def=CHECK (((confidence_score >= (0)::numeric) AND (confidence_score <= (100)::numeric))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.gemini_pilot_request_builder_specs.gemini_pilot_request_builder_specs_grounding_enabled_check` | contype=c; def=CHECK ((grounding_enabled = false)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.gemini_pilot_request_builder_specs.gemini_pilot_request_builder_specs_live_execution_allowed_check` | contype=c; def=CHECK ((live_execution_allowed = false)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.gemini_pilot_request_builder_specs.gemini_pilot_request_builder_specs_pilot_code_key` | contype=u; def=UNIQUE (pilot_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.gemini_pilot_request_builder_specs.gemini_pilot_request_builder_specs_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.improvement_proposals.improvement_proposals_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.improvement_proposals.improvement_proposals_proposal_code_key` | contype=u; def=UNIQUE (proposal_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.improvement_proposals.improvement_proposals_question_id_fkey` | contype=f; def=FOREIGN KEY (question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.improvement_proposals.ip_size_check` | contype=c; def=CHECK ((estimated_size = ANY (ARRAY['XS'::text, 'S'::text, 'M'::text, 'L'::text, 'XL'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.improvement_proposals.ip_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['draft'::text, 'evidence_incomplete'::text, 'ready_for_decision'::text, 'decided'::text, 'withdrawn'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.live_request_envelopes.live_request_envelopes_authorization_id_fkey` | contype=f; def=FOREIGN KEY (authorization_id) REFERENCES research.provider_authorization_records(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.live_request_envelopes.live_request_envelopes_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.live_request_envelopes.live_request_envelopes_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.live_request_envelopes.lre_flag_check` | contype=c; def=CHECK (((envelope ->> 'live_execution_allowed'::text) = 'false'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.live_request_envelopes.lre_not_executable` | contype=c; def=CHECK ((executable = false)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.model_outputs.model_outputs_fingerprint_sha256` | contype=c; def=CHECK ((output_fingerprint ~ '^[a-f0-9]{64}$'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.model_outputs.model_outputs_has_body` | contype=c; def=CHECK (((output_json IS NOT NULL) OR (output_text IS NOT NULL))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.model_outputs.model_outputs_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.model_outputs.model_outputs_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.benchmark_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.model_outputs.model_outputs_run_id_key` | contype=u; def=UNIQUE (run_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.models.models_code_nonempty` | contype=c; def=CHECK ((length(TRIM(BOTH FROM model_code)) > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.models.models_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.models.models_provider_code_version_unique` | contype=u; def=UNIQUE (provider_id, model_code, model_version) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.models.models_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_counts_nonneg` | contype=c; def=CHECK (((case_count >= 0) AND (adversarial_count >= 0) AND (unresolved_critical_safety_count >= 0))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_evidence_threshold` | contype=c; def=CHECK (((evidence_sufficient = true) AND (case_count >= 10) AND (adversarial_count >= 2) AND (technical_failure_rate < 0.20) AND (unresolved_critical_safety_count = 0))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_failure_rate_range` | contype=c; def=CHECK (((technical_failure_rate >= (0)::numeric) AND (technical_failure_rate <= (1)::numeric))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_model_id_fkey` | contype=f; def=FOREIGN KEY (model_id) REFERENCES research.models(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_rank_positive` | contype=c; def=CHECK ((rank >= 1)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_role_check` | contype=c; def=CHECK ((role_code = ANY (ARRAY['researcher'::text, 'planner'::text, 'implementation_proposal_writer'::text, 'qa_checker'::text, 'independent_reviewer'::text, 'debugger'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_unique` | contype=u; def=UNIQUE (role_code, year_month, model_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings.monthly_role_rankings_ym_check` | contype=c; def=CHECK ((year_month ~ '^[0-9]{4}-[0-9]{2}$'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.orchestration_failures.of_failure_check` | contype=c; def=CHECK ((failure_class = ANY (ARRAY['quota_exhausted'::text, 'budget_blocked'::text, 'timeout'::text, 'rate_limited'::text, 'invalid_schema'::text, 'unsupported_citation'::text, 'provider_unavailable'::text, 'unsafe_output'::text, 'mock_failure'::text, 'partial_blocked'::text, 'stagnation'::text, 'cancelled'::text, 'duplicate_stage'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.orchestration_failures.orchestration_failures_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.orchestration_failures.orchestration_failures_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.research_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.par_authority` | contype=c; def=CHECK ((approving_authority = 'Taha'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_requests.par_conf_check` | contype=c; def=CHECK ((confidentiality_class = ANY (ARRAY['public_or_synthetic'::text, 'internal_lab'::text, 'restricted'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_requests.par_fp_sha` | contype=c; def=CHECK ((input_fingerprint ~ '^[a-f0-9]{64}$'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.par_spend_bounds` | contype=c; def=CHECK (((requests_spent <= max_requests) AND (tokens_spent <= max_tokens) AND (cost_spent_usd <= max_cost_usd))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_requests.par_stage_check` | contype=c; def=CHECK ((stage = ANY (ARRAY['researcher'::text, 'planner'::text, 'implementation_proposal_writer'::text, 'qa_checker'::text, 'independent_reviewer'::text, 'debugger'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.par_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['proposed'::text, 'active'::text, 'revoked'::text, 'exhausted'::text, 'expired'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses.pares_failure_check` | contype=c; def=CHECK (((failure_class IS NULL) OR (failure_class = ANY (ARRAY['quota_exhausted'::text, 'budget_blocked'::text, 'timeout'::text, 'rate_limited'::text, 'invalid_schema'::text, 'unsupported_citation'::text, 'provider_unavailable'::text, 'unsafe_output'::text, 'mock_failure'::text])))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses.pares_finish_check` | contype=c; def=CHECK ((finish_reason = ANY (ARRAY['success'::text, 'error'::text, 'timeout'::text, 'rate_limited'::text, 'budget_blocked'::text, 'cancelled'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses.pares_out_fp` | contype=c; def=CHECK (((output_fingerprint IS NULL) OR (output_fingerprint ~ '^[a-f0-9]{64}$'::text))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_versions.pav_live_off_round4` | contype=c; def=CHECK ((live_execution_enabled = false)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_versions.pav_unique` | contype=u; def=UNIQUE (provider_id, adapter_version) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_capabilities.pc_code_nonempty` | contype=c; def=CHECK ((length(TRIM(BOTH FROM capability_code)) > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_capabilities.pc_unique` | contype=u; def=UNIQUE (provider_id, capability_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pcr_idempotency_unique` | contype=u; def=UNIQUE (pilot_proposal_id, idempotency_key) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pcr_zero_cost` | contype=c; def=CHECK ((projected_cost_usd = (0)::numeric)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_credential_status.pcs_no_secret_in_label` | contype=c; def=CHECK (((n8n_credential_label IS NULL) OR ((n8n_credential_label !~* 'sk- | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_credential_status.pcs_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['missing'::text, 'present'::text, 'unknown'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_health_checks.phc_kind_check` | contype=c; def=CHECK ((check_kind = ANY (ARRAY['registry_only'::text, 'credential_status_only'::text, 'fixture_parse'::text, 'live_probe_forbidden'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_authorization_id_fkey` | contype=f; def=FOREIGN KEY (authorization_id) REFERENCES research.provider_authorization_records(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_benchmark_case_id_fkey` | contype=f; def=FOREIGN KEY (benchmark_case_id) REFERENCES research.benchmark_cases(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_envelope_id_fkey` | contype=f; def=FOREIGN KEY (envelope_id) REFERENCES research.live_request_envelopes(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_pilot_proposal_id_fkey` | contype=f; def=FOREIGN KEY (pilot_proposal_id) REFERENCES research.provider_pilot_proposals(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_projected_cost_usd_check` | contype=c; def=CHECK ((projected_cost_usd >= (0)::numeric)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_projected_input_tokens_check` | contype=c; def=CHECK ((projected_input_tokens >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_projected_output_tokens_check` | contype=c; def=CHECK ((projected_output_tokens >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations.pilot_capacity_reservations_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['reserved'::text, 'finalized'::text, 'released'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_model_candidates.pmc_free_check` | contype=c; def=CHECK ((free_tier_status = ANY (ARRAY['unverified'::text, 'free_confirmed'::text, 'paid_only'::text, 'unknown'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_model_candidates.pmc_unique` | contype=u; def=UNIQUE (provider_id, model_id_provisional) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_model_candidates.pmc_verify_check` | contype=c; def=CHECK ((verification_status = ANY (ARRAY['unverified'::text, 'verified'::text, 'rejected'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.ppp_not_live_yet` | contype=c; def=CHECK (((status <> 'approved'::text) OR (taha_approved_at IS NOT NULL))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.ppp_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['proposed'::text, 'awaiting_taha_credential'::text, 'awaiting_taha_approval'::text, 'approved'::text, 'rejected'::text, 'expired'::text, 'cancelled'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.ppp_three_cases` | contype=c; def=CHECK (((cardinality(benchmark_case_ids) = 3) AND (cardinality(benchmark_case_codes) = 3))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_rate_limit_policies.prlp_scope` | contype=u; def=UNIQUE (provider_id, model_candidate_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.proposal_versions.proposal_versions_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.proposal_versions.proposal_versions_proposal_id_fkey` | contype=f; def=FOREIGN KEY (proposal_id) REFERENCES research.improvement_proposals(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_requests.provider_adapter_requests_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_requests.provider_adapter_requests_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.research_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_requests.provider_adapter_requests_stage_row_id_fkey` | contype=f; def=FOREIGN KEY (stage_row_id) REFERENCES research.research_run_stages(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses.provider_adapter_responses_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses.provider_adapter_responses_request_id_fkey` | contype=f; def=FOREIGN KEY (request_id) REFERENCES research.provider_adapter_requests(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses.provider_adapter_responses_request_id_key` | contype=u; def=UNIQUE (request_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses.provider_adapter_responses_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.research_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_versions.provider_adapter_versions_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_versions.provider_adapter_versions_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_benchmark_case_id_fkey` | contype=f; def=FOREIGN KEY (benchmark_case_id) REFERENCES research.benchmark_cases(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_cost_spent_usd_check` | contype=c; def=CHECK ((cost_spent_usd >= (0)::numeric)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_max_cost_usd_check` | contype=c; def=CHECK ((max_cost_usd >= (0)::numeric)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_max_requests_check` | contype=c; def=CHECK ((max_requests >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_max_tokens_check` | contype=c; def=CHECK ((max_tokens >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_model_candidate_id_fkey` | contype=f; def=FOREIGN KEY (model_candidate_id) REFERENCES research.provider_model_candidates(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_pilot_proposal_id_fkey` | contype=f; def=FOREIGN KEY (pilot_proposal_id) REFERENCES research.provider_pilot_proposals(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_requests_spent_check` | contype=c; def=CHECK ((requests_spent >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records.provider_authorization_records_tokens_spent_check` | contype=c; def=CHECK ((tokens_spent >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_budget_policies.provider_budget_caps_nonneg` | contype=c; def=CHECK (((daily_request_cap >= 0) AND (daily_token_cap >= 0) AND (monthly_cost_ceiling_usd >= (0)::numeric))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_budget_policies.provider_budget_paid_requires_ceiling` | contype=c; def=CHECK (((paid_usage_authorized = false) OR (monthly_cost_ceiling_usd > (0)::numeric))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_budget_policies.provider_budget_policies_daily_cost_limit_usd_check` | contype=c; def=CHECK ((daily_cost_limit_usd >= (0)::numeric)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_budget_policies.provider_budget_policies_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_budget_policies.provider_budget_policies_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_budget_policies.provider_budget_policies_provider_id_key` | contype=u; def=UNIQUE (provider_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_capabilities.provider_capabilities_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_capabilities.provider_capabilities_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_credential_status.provider_credential_status_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_credential_status.provider_credential_status_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_credential_status.provider_credential_status_provider_id_key` | contype=u; def=UNIQUE (provider_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_health_checks.provider_health_checks_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_health_checks.provider_health_checks_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_model_candidates.provider_model_candidates_max_requests_per_day_check` | contype=c; def=CHECK ((max_requests_per_day >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_model_candidates.provider_model_candidates_max_tokens_per_day_check` | contype=c; def=CHECK ((max_tokens_per_day >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_model_candidates.provider_model_candidates_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_model_candidates.provider_model_candidates_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_approving_authority_check` | contype=c; def=CHECK ((approving_authority = 'Taha'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_confidentiality_class_check` | contype=c; def=CHECK ((confidentiality_class = 'public_or_synthetic'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_fallback_provider_allowed_check` | contype=c; def=CHECK ((fallback_provider_allowed = false)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_max_attempts_per_case_check` | contype=c; def=CHECK ((max_attempts_per_case = 1)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_max_authorized_cost_usd_check` | contype=c; def=CHECK ((max_authorized_cost_usd = (0)::numeric)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_max_successful_calls_check` | contype=c; def=CHECK ((max_successful_calls = 3)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_max_total_input_tokens_check` | contype=c; def=CHECK ((max_total_input_tokens > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_max_total_output_tokens_check` | contype=c; def=CHECK ((max_total_output_tokens > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_max_total_requests_check` | contype=c; def=CHECK ((max_total_requests = 3)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_model_candidate_id_fkey` | contype=f; def=FOREIGN KEY (model_candidate_id) REFERENCES research.provider_model_candidates(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_pilot_code_key` | contype=u; def=UNIQUE (pilot_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_policy_verification_id_fkey` | contype=f; def=FOREIGN KEY (policy_verification_id) REFERENCES research.provider_policy_verifications(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals.provider_pilot_proposals_retries_allowed_check` | contype=c; def=CHECK ((retries_allowed = false)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_policy_verifications.provider_policy_verifications_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_policy_verifications.provider_policy_verifications_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_rate_limit_policies.provider_rate_limit_policies_model_candidate_id_fkey` | contype=f; def=FOREIGN KEY (model_candidate_id) REFERENCES research.provider_model_candidates(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_rate_limit_policies.provider_rate_limit_policies_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_rate_limit_policies.provider_rate_limit_policies_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_rate_limit_policies.provider_rate_limit_policies_requests_per_minute_check` | contype=c; def=CHECK ((requests_per_minute >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_rate_limit_policies.provider_rate_limit_policies_tokens_per_minute_check` | contype=c; def=CHECK ((tokens_per_minute >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_authorization_id_fkey` | contype=f; def=FOREIGN KEY (authorization_id) REFERENCES research.provider_authorization_records(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_benchmark_case_id_fkey` | contype=f; def=FOREIGN KEY (benchmark_case_id) REFERENCES research.benchmark_cases(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_estimated_cost_usd_check` | contype=c; def=CHECK ((estimated_cost_usd >= (0)::numeric)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_input_tokens_check` | contype=c; def=CHECK ((input_tokens >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_model_candidate_id_fkey` | contype=f; def=FOREIGN KEY (model_candidate_id) REFERENCES research.provider_model_candidates(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_output_tokens_check` | contype=c; def=CHECK ((output_tokens >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_pilot_proposal_id_fkey` | contype=f; def=FOREIGN KEY (pilot_proposal_id) REFERENCES research.provider_pilot_proposals(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_provider_id_fkey` | contype=f; def=FOREIGN KEY (provider_id) REFERENCES research.providers(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.provider_usage_ledger_request_count_check` | contype=c; def=CHECK ((request_count > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.providers.providers_code_key` | contype=u; def=UNIQUE (code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.providers.providers_code_nonempty` | contype=c; def=CHECK ((length(TRIM(BOTH FROM code)) > 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.providers.providers_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger.pul_round4_no_live` | contype=c; def=CHECK ((live_executed = false)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.proposal_versions.pv_evidence_required_for_decision` | contype=c; def=CHECK (true) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.proposal_versions.pv_unique` | contype=u; def=UNIQUE (proposal_id, version_number) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.proposal_versions.pv_version_positive` | contype=c; def=CHECK ((version_number >= 1)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.question_status_transitions.qst_from_check` | contype=c; def=CHECK ((from_status = ANY (ARRAY['proposed'::text, 'triage_required'::text, 'approved_for_research'::text, 'active'::text, 'evidence_review'::text, 'decision_required'::text, 'accepted'::text, 'rejected'::text, 'deferred'::text, 'closed'::text, 'superseded'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.question_status_transitions.qst_to_check` | contype=c; def=CHECK ((to_status = ANY (ARRAY['proposed'::text, 'triage_required'::text, 'approved_for_research'::text, 'active'::text, 'evidence_review'::text, 'decision_required'::text, 'accepted'::text, 'rejected'::text, 'deferred'::text, 'closed'::text, 'superseded'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.question_status_transitions.question_status_transitions_pkey` | contype=p; def=PRIMARY KEY (from_status, to_status) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.repair_attempts.ra_attempt_pos` | contype=c; def=CHECK (((attempt_number >= 1) AND (attempt_number <= 2))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.repair_attempts.ra_outcome_check` | contype=c; def=CHECK ((outcome = ANY (ARRAY['repaired'::text, 'escalated_same_failure'::text, 'escalated_budget'::text, 'blocked'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.repair_attempts.ra_unique` | contype=u; def=UNIQUE (run_id, stage, attempt_number) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_closure_records.rcr_kind_check` | contype=c; def=CHECK ((closure_kind = ANY (ARRAY['accepted_closed'::text, 'rejected_closed'::text, 'deferred_closed'::text, 'superseded_closed'::text, 'merged_duplicate'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.reconsideration_conditions.reconsideration_conditions_decision_id_fkey` | contype=f; def=FOREIGN KEY (decision_id) REFERENCES research.taha_decisions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.reconsideration_conditions.reconsideration_conditions_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.repair_attempts.repair_attempts_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.repair_attempts.repair_attempts_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.research_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_closure_records.research_closure_records_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_closure_records.research_closure_records_question_id_fkey` | contype=f; def=FOREIGN KEY (question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_closure_records.research_closure_records_related_decision_id_fkey` | contype=f; def=FOREIGN KEY (related_decision_id) REFERENCES research.taha_decisions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_findings.research_findings_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_findings.research_findings_question_id_fkey` | contype=f; def=FOREIGN KEY (question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_priorities.research_priorities_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_priorities.research_priorities_question_id_fkey` | contype=f; def=FOREIGN KEY (question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_relationships.research_question_relationships_from_question_id_fkey` | contype=f; def=FOREIGN KEY (from_question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_relationships.research_question_relationships_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_relationships.research_question_relationships_to_question_id_fkey` | contype=f; def=FOREIGN KEY (to_question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_versions.research_question_versions_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_versions.research_question_versions_question_uuid_fkey` | contype=f; def=FOREIGN KEY (question_uuid) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.research_questions_canonical_question_id_fkey` | contype=f; def=FOREIGN KEY (canonical_question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.research_questions_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.research_questions_question_id_key` | contype=u; def=UNIQUE (question_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.research_questions_superseded_by_question_id_fkey` | contype=f; def=FOREIGN KEY (superseded_by_question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages.research_run_stages_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages.research_run_stages_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.research_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs.research_runs_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs.research_runs_question_uuid_fkey` | contype=f; def=FOREIGN KEY (question_uuid) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs.research_runs_run_code_key` | contype=u; def=UNIQUE (run_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_status_history.research_status_history_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_status_history.research_status_history_question_id_fkey` | contype=f; def=FOREIGN KEY (question_id) REFERENCES research.research_questions(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_priorities.rp_components_range` | contype=c; def=CHECK (((constitutional_impact >= (0)::numeric) AND (constitutional_impact <= (100)::numeric) AND ((measured_performance_gap >= (0)::numeric) AND (measured_performance_gap <= (100)::numeric)) AND ((safety_impact >= (0)::numeric) AND (safety_impact <= (100)::numeric)) AND ((expected_value >= (0)::numeric) AND (expected_value <= (100)::numeric)) AND ((urgency >= (0)::numeric) AND (urgency <= (100)::numeric)) AND ((evidence_availability >= (0)::numeric) AND (evidence_availability <= (100)::numeric)) AND ((implementation_cost >= (0)::numeric) AND (implementation_cost <= (100)::numeric)) AND ((duplication_penalty >= (0)::numeric) AND (duplication_penalty <= (100)::numeric)))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_priorities.rp_override_requires_rationale` | contype=c; def=CHECK ((((override_score IS NULL) AND (override_rationale IS NULL)) OR ((override_score IS NOT NULL) AND (override_rationale IS NOT NULL) AND (length(TRIM(BOTH FROM override_rationale)) > 0)))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.rq_class_check` | contype=c; def=CHECK ((question_class = ANY (ARRAY['constitutional'::text, 'measured_gap'::text, 'reliability'::text, 'cost'::text, 'security'::text, 'provider_capability'::text, 'workflow_improvement'::text, 'external_opportunity'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.rq_conf_check` | contype=c; def=CHECK ((confidentiality_class = ANY (ARRAY['public_or_synthetic'::text, 'internal_lab'::text, 'restricted'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.rq_fingerprint_sha256` | contype=c; def=CHECK ((duplicate_fingerprint ~ '^[a-f0-9]{64}$'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.rq_no_self_canonical` | contype=c; def=CHECK ((canonical_question_id IS DISTINCT FROM id)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.rq_no_self_supersede` | contype=c; def=CHECK ((superseded_by_question_id IS DISTINCT FROM id)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.rq_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['proposed'::text, 'triage_required'::text, 'approved_for_research'::text, 'active'::text, 'evidence_review'::text, 'decision_required'::text, 'accepted'::text, 'rejected'::text, 'deferred'::text, 'closed'::text, 'superseded'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions.rq_version_positive` | contype=c; def=CHECK ((current_version >= 1)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_relationships.rqr_no_self` | contype=c; def=CHECK ((from_question_id <> to_question_id)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_relationships.rqr_type_check` | contype=c; def=CHECK ((relationship_type = ANY (ARRAY['duplicate_of'::text, 'supersedes'::text, 'related_to'::text, 'blocks'::text, 'blocked_by'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_relationships.rqr_unique` | contype=u; def=UNIQUE (from_question_id, to_question_id, relationship_type) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_versions.rqv_unique` | contype=u; def=UNIQUE (question_uuid, version_number) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_versions.rqv_version_positive` | contype=c; def=CHECK ((version_number >= 1)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs.rr_final_status_check` | contype=c; def=CHECK (((final_status IS NULL) OR (final_status = ANY (ARRAY['pending'::text, 'running'::text, 'awaiting_qa'::text, 'awaiting_review'::text, 'repair_required'::text, 'decision_ready'::text, 'failed'::text, 'blocked'::text, 'cancelled'::text])))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs.rr_max_repair` | contype=c; def=CHECK ((max_repair_attempts = 2)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs.rr_repair_nonneg` | contype=c; def=CHECK ((repair_attempt_count >= 0)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs.rr_stage_check` | contype=c; def=CHECK (((current_stage IS NULL) OR (current_stage = ANY (ARRAY['researcher'::text, 'planner'::text, 'implementation_proposal_writer'::text, 'qa_checker'::text, 'independent_reviewer'::text, 'debugger'::text, 'finalizer'::text])))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs.rr_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'awaiting_qa'::text, 'awaiting_review'::text, 'repair_required'::text, 'decision_ready'::text, 'failed'::text, 'blocked'::text, 'cancelled'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages.rrs_attempt_pos` | contype=c; def=CHECK ((attempt_number >= 1)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages.rrs_fp_sha` | contype=c; def=CHECK ((input_fingerprint ~ '^[a-f0-9]{64}$'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages.rrs_out_fp_sha` | contype=c; def=CHECK (((output_fingerprint IS NULL) OR (output_fingerprint ~ '^[a-f0-9]{64}$'::text))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages.rrs_stage_check` | contype=c; def=CHECK ((stage = ANY (ARRAY['researcher'::text, 'planner'::text, 'implementation_proposal_writer'::text, 'qa_checker'::text, 'independent_reviewer'::text, 'debugger'::text, 'finalizer'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages.rrs_status_check` | contype=c; def=CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'skipped'::text, 'blocked'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages.rrs_unique_attempt` | contype=u; def=UNIQUE (run_id, stage, attempt_number) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.run_failures.run_failures_class_check` | contype=c; def=CHECK ((failure_class = ANY (ARRAY['schema_invalid'::text, 'timeout'::text, 'rate_limit'::text, 'quota_exhausted'::text, 'provider_error'::text, 'safety'::text, 'instruction_violation'::text, 'empty_output'::text, 'budget_exceeded'::text, 'cancelled'::text, 'other'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.run_failures.run_failures_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.run_failures.run_failures_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.benchmark_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.schema_version.schema_version_pkey` | contype=p; def=PRIMARY KEY (version) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.source_snapshots.source_snapshots_fp_check` | contype=c; def=CHECK ((content_fingerprint ~ '^[a-f0-9]{64}$'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.source_snapshots.source_snapshots_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.source_snapshots.source_snapshots_source_id_fkey` | contype=f; def=FOREIGN KEY (source_id) REFERENCES research.sources(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.sources.sources_identity_unique` | contype=u; def=UNIQUE (source_url_or_id, publisher) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.sources.sources_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.sources.sources_reliability_check` | contype=c; def=CHECK ((reliability_class = ANY (ARRAY['high'::text, 'medium'::text, 'low'::text, 'unverified'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.sources.sources_type_check` | contype=c; def=CHECK ((source_type = ANY (ARRAY['official_docs'::text, 'public_changelog'::text, 'synthetic_fixture'::text, 'lab_metric'::text, 'incident_fixture'::text, 'other_public'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_decisions.taha_decisions_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_decisions.taha_decisions_proposal_id_fkey` | contype=f; def=FOREIGN KEY (proposal_id) REFERENCES research.improvement_proposals(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_scores.taha_scores_dimension_check` | contype=c; def=CHECK ((dimension = ANY (ARRAY['factual_accuracy'::text, 'evidence_quality'::text, 'instruction_compliance'::text, 'reasoning_completeness'::text, 'output_structure'::text, 'citation_correctness'::text, 'hallucination_rate'::text, 'latency'::text, 'token_use'::text, 'cost'::text, 'retry_rate'::text, 'rate_limit_failures'::text, 'schema_valid_response_rate'::text, 'agreement_with_taha'::text, 'overall_human_judgment'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_scores.taha_scores_pkey` | contype=p; def=PRIMARY KEY (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_scores.taha_scores_range` | contype=c; def=CHECK (((score >= (0)::numeric) AND (score <= (100)::numeric))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_scores.taha_scores_run_id_fkey` | contype=f; def=FOREIGN KEY (run_id) REFERENCES research.benchmark_runs(id) ON DELETE RESTRICT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_decisions.td_authority_check` | contype=c; def=CHECK ((deciding_authority = 'Taha'::text)) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_decisions.td_decision_check` | contype=c; def=CHECK ((decision = ANY (ARRAY['approved'::text, 'rejected'::text, 'deferred'::text, 'research_more'::text, 'superseded'::text]))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_decisions.td_deferred_needs_review` | contype=c; def=CHECK (((decision <> 'deferred'::text) OR (review_or_expiry_at IS NOT NULL) OR (conditions_text IS NOT NULL))) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CONSTRAINTS` | `ND-CHECKPOINT-04/08/10; ND-RECON` | N for definition presence | missing/extra/altered → failed_frozen |

### 4.15 EV-INDEXES (76 rows — full natural identities)

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.automatic_scores_pkey on automatic_scores` | CREATE UNIQUE INDEX automatic_scores_pkey ON research.automatic_scores USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases_pkey on benchmark_cases` | CREATE UNIQUE INDEX benchmark_cases_pkey ON research.benchmark_cases USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_cases_suite_code_unique on benchmark_cases` | CREATE UNIQUE INDEX benchmark_cases_suite_code_unique ON research.benchmark_cases USING btree (suite_id, case_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs_execution_identity_unique on benchmark_runs` | CREATE UNIQUE INDEX benchmark_runs_execution_identity_unique ON research.benchmark_runs USING btree (execution_identity) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_runs_pkey on benchmark_runs` | CREATE UNIQUE INDEX benchmark_runs_pkey ON research.benchmark_runs USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_suites_pkey on benchmark_suites` | CREATE UNIQUE INDEX benchmark_suites_pkey ON research.benchmark_suites USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.benchmark_suites_role_version_unique on benchmark_suites` | CREATE UNIQUE INDEX benchmark_suites_role_version_unique ON research.benchmark_suites USING btree (role_code, suite_version) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.decision_rationales_pkey on decision_rationales` | CREATE UNIQUE INDEX decision_rationales_pkey ON research.decision_rationales USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_claim_links_pkey on evidence_claim_links` | CREATE UNIQUE INDEX evidence_claim_links_pkey ON research.evidence_claim_links USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.evidence_items_pkey on evidence_items` | CREATE UNIQUE INDEX evidence_items_pkey ON research.evidence_items USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.gemini_pilot_request_builder_specs_pilot_code_key on gemini_pilot_request_builder_specs` | CREATE UNIQUE INDEX gemini_pilot_request_builder_specs_pilot_code_key ON research.gemini_pilot_request_builder_specs USING btree (pilot_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.gemini_pilot_request_builder_specs_pkey on gemini_pilot_request_builder_specs` | CREATE UNIQUE INDEX gemini_pilot_request_builder_specs_pkey ON research.gemini_pilot_request_builder_specs USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.idx_pilot_capacity_reservations_pilot on pilot_capacity_reservations` | CREATE INDEX idx_pilot_capacity_reservations_pilot ON research.pilot_capacity_reservations USING btree (pilot_proposal_id) WHERE (status = ANY (ARRAY['reserved'::text, 'finalized'::text])) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.improvement_proposals_pkey on improvement_proposals` | CREATE UNIQUE INDEX improvement_proposals_pkey ON research.improvement_proposals USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.improvement_proposals_proposal_code_key on improvement_proposals` | CREATE UNIQUE INDEX improvement_proposals_proposal_code_key ON research.improvement_proposals USING btree (proposal_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.live_request_envelopes_pkey on live_request_envelopes` | CREATE UNIQUE INDEX live_request_envelopes_pkey ON research.live_request_envelopes USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.model_outputs_pkey on model_outputs` | CREATE UNIQUE INDEX model_outputs_pkey ON research.model_outputs USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.model_outputs_run_id_key on model_outputs` | CREATE UNIQUE INDEX model_outputs_run_id_key ON research.model_outputs USING btree (run_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.models_pkey on models` | CREATE UNIQUE INDEX models_pkey ON research.models USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.models_provider_code_version_unique on models` | CREATE UNIQUE INDEX models_provider_code_version_unique ON research.models USING btree (provider_id, model_code, model_version) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings_pkey on monthly_role_rankings` | CREATE UNIQUE INDEX monthly_role_rankings_pkey ON research.monthly_role_rankings USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.monthly_role_rankings_unique on monthly_role_rankings` | CREATE UNIQUE INDEX monthly_role_rankings_unique ON research.monthly_role_rankings USING btree (role_code, year_month, model_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.orchestration_failures_pkey on orchestration_failures` | CREATE UNIQUE INDEX orchestration_failures_pkey ON research.orchestration_failures USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pav_unique on provider_adapter_versions` | CREATE UNIQUE INDEX pav_unique ON research.provider_adapter_versions USING btree (provider_id, adapter_version) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pc_unique on provider_capabilities` | CREATE UNIQUE INDEX pc_unique ON research.provider_capabilities USING btree (provider_id, capability_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pcr_idempotency_unique on pilot_capacity_reservations` | CREATE UNIQUE INDEX pcr_idempotency_unique ON research.pilot_capacity_reservations USING btree (pilot_proposal_id, idempotency_key) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pilot_capacity_reservations_pkey on pilot_capacity_reservations` | CREATE UNIQUE INDEX pilot_capacity_reservations_pkey ON research.pilot_capacity_reservations USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pmc_unique on provider_model_candidates` | CREATE UNIQUE INDEX pmc_unique ON research.provider_model_candidates USING btree (provider_id, model_id_provisional) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.prlp_scope on provider_rate_limit_policies` | CREATE UNIQUE INDEX prlp_scope ON research.provider_rate_limit_policies USING btree (provider_id, model_candidate_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.proposal_versions_pkey on proposal_versions` | CREATE UNIQUE INDEX proposal_versions_pkey ON research.proposal_versions USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_requests_pkey on provider_adapter_requests` | CREATE UNIQUE INDEX provider_adapter_requests_pkey ON research.provider_adapter_requests USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses_pkey on provider_adapter_responses` | CREATE UNIQUE INDEX provider_adapter_responses_pkey ON research.provider_adapter_responses USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_responses_request_id_key on provider_adapter_responses` | CREATE UNIQUE INDEX provider_adapter_responses_request_id_key ON research.provider_adapter_responses USING btree (request_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_adapter_versions_pkey on provider_adapter_versions` | CREATE UNIQUE INDEX provider_adapter_versions_pkey ON research.provider_adapter_versions USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_authorization_records_pkey on provider_authorization_records` | CREATE UNIQUE INDEX provider_authorization_records_pkey ON research.provider_authorization_records USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_budget_policies_pkey on provider_budget_policies` | CREATE UNIQUE INDEX provider_budget_policies_pkey ON research.provider_budget_policies USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_budget_policies_provider_id_key on provider_budget_policies` | CREATE UNIQUE INDEX provider_budget_policies_provider_id_key ON research.provider_budget_policies USING btree (provider_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_capabilities_pkey on provider_capabilities` | CREATE UNIQUE INDEX provider_capabilities_pkey ON research.provider_capabilities USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_credential_status_pkey on provider_credential_status` | CREATE UNIQUE INDEX provider_credential_status_pkey ON research.provider_credential_status USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_credential_status_provider_id_key on provider_credential_status` | CREATE UNIQUE INDEX provider_credential_status_provider_id_key ON research.provider_credential_status USING btree (provider_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_health_checks_pkey on provider_health_checks` | CREATE UNIQUE INDEX provider_health_checks_pkey ON research.provider_health_checks USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_model_candidates_pkey on provider_model_candidates` | CREATE UNIQUE INDEX provider_model_candidates_pkey ON research.provider_model_candidates USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals_pilot_code_key on provider_pilot_proposals` | CREATE UNIQUE INDEX provider_pilot_proposals_pilot_code_key ON research.provider_pilot_proposals USING btree (pilot_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_pilot_proposals_pkey on provider_pilot_proposals` | CREATE UNIQUE INDEX provider_pilot_proposals_pkey ON research.provider_pilot_proposals USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_policy_verifications_pkey on provider_policy_verifications` | CREATE UNIQUE INDEX provider_policy_verifications_pkey ON research.provider_policy_verifications USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_rate_limit_policies_pkey on provider_rate_limit_policies` | CREATE UNIQUE INDEX provider_rate_limit_policies_pkey ON research.provider_rate_limit_policies USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.provider_usage_ledger_pkey on provider_usage_ledger` | CREATE UNIQUE INDEX provider_usage_ledger_pkey ON research.provider_usage_ledger USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.providers_code_key on providers` | CREATE UNIQUE INDEX providers_code_key ON research.providers USING btree (code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.providers_pkey on providers` | CREATE UNIQUE INDEX providers_pkey ON research.providers USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.pv_unique on proposal_versions` | CREATE UNIQUE INDEX pv_unique ON research.proposal_versions USING btree (proposal_id, version_number) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.question_status_transitions_pkey on question_status_transitions` | CREATE UNIQUE INDEX question_status_transitions_pkey ON research.question_status_transitions USING btree (from_status, to_status) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.ra_unique on repair_attempts` | CREATE UNIQUE INDEX ra_unique ON research.repair_attempts USING btree (run_id, stage, attempt_number) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.reconsideration_conditions_pkey on reconsideration_conditions` | CREATE UNIQUE INDEX reconsideration_conditions_pkey ON research.reconsideration_conditions USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.repair_attempts_pkey on repair_attempts` | CREATE UNIQUE INDEX repair_attempts_pkey ON research.repair_attempts USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_closure_records_pkey on research_closure_records` | CREATE UNIQUE INDEX research_closure_records_pkey ON research.research_closure_records USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_findings_pkey on research_findings` | CREATE UNIQUE INDEX research_findings_pkey ON research.research_findings USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_priorities_pkey on research_priorities` | CREATE UNIQUE INDEX research_priorities_pkey ON research.research_priorities USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_relationships_pkey on research_question_relationships` | CREATE UNIQUE INDEX research_question_relationships_pkey ON research.research_question_relationships USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_question_versions_pkey on research_question_versions` | CREATE UNIQUE INDEX research_question_versions_pkey ON research.research_question_versions USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions_pkey on research_questions` | CREATE UNIQUE INDEX research_questions_pkey ON research.research_questions USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_questions_question_id_key on research_questions` | CREATE UNIQUE INDEX research_questions_question_id_key ON research.research_questions USING btree (question_id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_run_stages_pkey on research_run_stages` | CREATE UNIQUE INDEX research_run_stages_pkey ON research.research_run_stages USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs_pkey on research_runs` | CREATE UNIQUE INDEX research_runs_pkey ON research.research_runs USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_runs_run_code_key on research_runs` | CREATE UNIQUE INDEX research_runs_run_code_key ON research.research_runs USING btree (run_code) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.research_status_history_pkey on research_status_history` | CREATE UNIQUE INDEX research_status_history_pkey ON research.research_status_history USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.rqr_unique on research_question_relationships` | CREATE UNIQUE INDEX rqr_unique ON research.research_question_relationships USING btree (from_question_id, to_question_id, relationship_type) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.rqv_unique on research_question_versions` | CREATE UNIQUE INDEX rqv_unique ON research.research_question_versions USING btree (question_uuid, version_number) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.rrs_unique_attempt on research_run_stages` | CREATE UNIQUE INDEX rrs_unique_attempt ON research.research_run_stages USING btree (run_id, stage, attempt_number) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.run_failures_pkey on run_failures` | CREATE UNIQUE INDEX run_failures_pkey ON research.run_failures USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.schema_version_pkey on schema_version` | CREATE UNIQUE INDEX schema_version_pkey ON research.schema_version USING btree (version) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.source_snapshots_pkey on source_snapshots` | CREATE UNIQUE INDEX source_snapshots_pkey ON research.source_snapshots USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.sources_identity_unique on sources` | CREATE UNIQUE INDEX sources_identity_unique ON research.sources USING btree (source_url_or_id, publisher) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.sources_pkey on sources` | CREATE UNIQUE INDEX sources_pkey ON research.sources USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_decisions_pkey on taha_decisions` | CREATE UNIQUE INDEX taha_decisions_pkey ON research.taha_decisions USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.taha_scores_pkey on taha_scores` | CREATE UNIQUE INDEX taha_scores_pkey ON research.taha_scores USING btree (id) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |
| `research.uq_pilot_capacity_one_attempt_per_case on pilot_capacity_reservations` | CREATE UNIQUE INDEX uq_pilot_capacity_one_attempt_per_case ON research.pilot_capacity_reservations USING btree (pilot_proposal_id, benchmark_case_id) WHERE (status = ANY (ARRAY['reserved'::text, 'finalized'::text])) | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-INDEXES` | `ND-CHECKPOINT-03/04/08/10` | N for definition presence | missing/extra/altered → failed_frozen |

### 4.16 EV-RESERVATION-STATE

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.pilot_capacity_reservations` | table exists after migration 8 | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-RESERVATION-STATE` | `ND-IDENTITY-SOURCE; ND-STATE-A-EQUALITY` | live row presence after backup remains live concern via precedence | MISSING_REQUIRED_OBJECT |
| `research.pilot_capacity_reservations rowcount` | 0 rows after deterministic migration 8 in reconstruction; State A/B/C inventory empty | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-RESERVATION-STATE` | `ND-STATE-A-EQUALITY; ND-STATE-B-RECOMPUTE` | cannot prove absence of post-backup live rows | live non-empty domain still classifies via cascade; empty reconstructed domain is design fact only |

### 4.17 EV-CUTOVER-STATE

| Object identity | Expected deterministic state | Evidence class | EV reference | ND reference | Live revalidation required | Mismatch behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `research.schema_version version=9` | ABSENT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CUTOVER-STATE` | `ND-CHECKPOINT-COMMON` | N for pre-cutover absence | has_version_9 → cutover already advanced |
| `schema research_crypto` | ABSENT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CUTOVER-STATE; EV-CRYPTO-LOCATION` | `ND-CHECKPOINT-01` | N | present early without CP → variance |
| `research.taha_governance_actions` | ABSENT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CUTOVER-STATE` | `ND-CHECKPOINT-03` | N | UNKNOWN_EXTRA_OBJECT |
| `research.accounting_discrepancies` | ABSENT | RECONSTRUCTED_REFERENCE_SCHEMA8 | `EV-CUTOVER-STATE` | `ND-CHECKPOINT-08` | N | UNKNOWN_EXTRA_OBJECT |

Provenance for all §4 rows: RECONSTRUCTED_REFERENCE_ACCEPTED; Evidence class: RECONSTRUCTED_REFERENCE_SCHEMA8; Manifest: 09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2; SOURCE_BACKUP_SCHEMA=5; REPLAYED_MIGRATIONS=6,7,8; NOT_HISTORICAL_LIVE_CATALOG=true; crosswalk `9D38F04D3BE2B519C59837ACD825B9DD74CA3724D793BAC7495B29C4B66E141F`.

---

## 5. Execution-time live preflight (11 markers)

**Timing:** inspect the actual target database immediately before schema-9 execution. **Current values:** all eleven remain `UNKNOWN_UNTIL_LIVE_PREFLIGHT`. **Natural identities:** OID-free. **Repair:** none automatic. **Failure before migration begins:** `BLOCKED_LIVE_PREFLIGHT_REQUIRED`. **Failure after governed migration state begins:** `failed_frozen`.

| Marker | Object set | Exact live query or predicate | Reconstructed expectation | Permitted variance | Comparison outcome | Blocking behavior | Provenance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `EV-ROLES` | `postgres, research_app, n8n_app, research_governance, research_test, and any other research/n8n-scoped roles` | `Inventory `pg_roles` attributes: rolname, rolcanlogin, rolinherit, rolsuper, rolcreaterole, rolcreatedb. Natural identity: rolname. Sort COLLATE "C".` | `Disposable placeholders only (postgres/research_app/n8n_app); research_governance/research_test absent — never historical live` | `SAFE_DECLARED_VARIANCE only if an ND-* row permits; ND-CHECKPOINT-02 requires governance/test roles with LOGIN/NOINHERIT` | `MISSING_REQUIRED_OBJECT / UNKNOWN_EXTRA_OBJECT / UNSAFE_UNDECLARED_VARIANCE / SAFE_DECLARED_VARIANCE` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-ROLES); ND-CHECKPOINT-02` |
| `EV-MEMBERSHIPS` | `direct and transitive pg_auth_members among relevant roles` | `Emit role_name+member_name+grantor_name+admin_option(t/f). Sort COLLATE "C".` | `Disposable-only memberships — non-authoritative` | `membership tuples required by ND-CHECKPOINT-02; no undeclared privilege-bearing memberships` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNKNOWN_EXTRA_OBJECT / MISSING_REQUIRED_OBJECT / UNSAFE_UNDECLARED_VARIANCE` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-MEMBERSHIPS); ND-CHECKPOINT-02` |
| `EV-SCHEMA-PRIVS` | `schemas research, research_crypto (if present), n8n, public × APP/N8N/GOV/TEST/PUBLIC` | `USAGE/CREATE ACL rows; natural identity nspname+grantee+privilege; sort COLLATE "C".` | `Round0B init grants not replayed — reconstructed absence is not live absence proof` | `CREATE denied for runtime roles per ND-CHECKPOINT-02; USAGE as designed` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNSAFE_UNDECLARED_VARIANCE / OWNER_MISMATCH` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-SCHEMA-PRIVS); ND-CHECKPOINT-02` |
| `EV-FUNCTION-ACLS` | `every research function natural identity` | `COALESCE(proacl, acldefault('f', proowner)) expansion; identity = function natural identity + grantee + privilege; sort COLLATE "C".` | `migration-6 GRANT surface not authoritative historical live ACL` | `freeze/restore EXECUTE surface per ND-FREEZE-REVOKE-EXECUTE / checkpoint contracts` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNSAFE_UNDECLARED_VARIANCE / MATCHES_RECONSTRUCTED_REFERENCE when equal and roles match live` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS); ND-CHECKPOINT-05..12,16; ND-FREEZE-REVOKE-EXECUTE` |
| `EV-FUNCTION-PUBLIC` | `PUBLIC (OID 0) EXECUTE on each research function` | `Presence boolean per function natural identity + PUBLIC + EXECUTE; sort COLLATE "C".` | `PUBLIC EXECUTE may appear due to defaults — not historical proof` | `PUBLIC EXECUTE absent except where an ND-* row explicitly permits` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNSAFE_UNDECLARED_VARIANCE` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-PUBLIC); ND-CHECKPOINT function ACL cells` |
| `EV-FUNCTION-EFFECTIVE` | `every relevant role × research function` | `Effective EXECUTE considering direct/PUBLIC/inherited/SET ROLE/owner/superuser/schema-USAGE; identity = function + role + final exercisable t/f; sort COLLATE "C".` | `reconstructed effective matrix non-authoritative` | `ND-CHECKPOINT and freeze contracts; builders non-executable until restoration where required` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNSAFE_UNDECLARED_VARIANCE / RUNTIME_STATE_MISMATCH` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-EFFECTIVE); ND-CHECKPOINT-05/15; ND-CHECKPOINT-COMMON` |
| `EV-TABLE-ACLS` | `every research base table` | `COALESCE(relacl, acldefault('r', relowner)); identity = schemaname.relname + grantee + privilege; sort COLLATE "C".` | `post-migration GRANT surface only partially present in reconstruction` | `checkpoint/freeze ACL contracts for governance/capacity/discrepancy and research base tables` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNSAFE_UNDECLARED_VARIANCE / OWNER_MISMATCH` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-TABLE-ACLS); ND-CHECKPOINT-03/08/10` |
| `EV-TABLE-WRITES` | `every research base table × every discovered relevant role` | `Effective INSERT/UPDATE/DELETE; identity = schemaname.relname + role + {INSERT|UPDATE|DELETE} + effective t/f; sort COLLATE "C".` | `reconstructed write matrix incomplete without init privilege path` | `Direct WRITE NONE for runtime roles where ND-CHECKPOINT / ND-FREEZE-REVOKE-WRITES require it` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNSAFE_UNDECLARED_VARIANCE` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-TABLE-WRITES); ND-FREEZE-REVOKE-WRITES; ND-CHECKPOINT-COMMON` |
| `EV-COLUMN-ACLS` | `research columns with attacl rows; null attacl = no column-specific grant` | `identity = schemaname.relname.attname + grantee + privilege; sort COLLATE "C".` | `reconstructed expansion uses non-historical roles` | `no undeclared column privilege expansions on sensitive columns` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNSAFE_UNDECLARED_VARIANCE` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-COLUMN-ACLS); ND-DIGEST column ACL cells` |
| `EV-COLUMN-EFFECTIVE` | `relevant roles × research columns` | `Effective column privileges; identity = schemaname.relname.attname + role + privilege + effective t/f; sort COLLATE "C".` | `non-authoritative in reconstruction` | `designed column privilege surface; no silent elevation` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / UNSAFE_UNDECLARED_VARIANCE` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-COLUMN-EFFECTIVE); ND-DIGEST column privilege cells` |
| `EV-DEFAULT-PRIVS` | `pg_default_acl for postgres (and other owners if present) in research / research_crypto` | `identity = role_name + schema_name + objtype + expanded ACL text with PUBLIC for OID 0; sort COLLATE "C".` | `disposable EV-DEFACL reflects disposable state only; Round0B ALTER DEFAULT PRIVILEGES not applied` | `revoke-all normative tuples per ND-CHECKPOINT-02/18; no future PUBLIC EXECUTE default for those schemas` | `PRIVILEGE_EXPANSION / PRIVILEGE_REDUCTION / MISSING_REQUIRED_OBJECT / UNSAFE_UNDECLARED_VARIANCE` | `BLOCKED_LIVE_PREFLIGHT_REQUIRED / failed_frozen` | `EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-DEFAULT-PRIVS); ND-CHECKPOINT-02/18` |

Unknown and extra-object handling: extras → `UNKNOWN_EXTRA_OBJECT`; missing required → `MISSING_REQUIRED_OBJECT`; privilege up → `PRIVILEGE_EXPANSION`; privilege down → `PRIVILEGE_REDUCTION`; owner drift → `OWNER_MISMATCH`. No silent normalization. No automatic GRANT/REVOKE/ownership change.

---

## 6. Pilot-time runtime revalidation (3 markers)

Current value for all three: `UNKNOWN_UNTIL_RUNTIME_REVALIDATION`. While any remains unknown, **prohibited:** pilot enablement, live API/provider calls, workflow activation, paid usage, provider/model enablement. Failure: `BLOCKED_RUNTIME_REVALIDATION_REQUIRED`.

| Marker | Runtime state | Safe columns | Freshness requirement | Required value or permitted set | Failure outcome | Prohibited action until resolved | Provenance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `EV-SAFETY-BASELINE` | provider/model enabled flags; credential non-secret status; proposals; authorizations; envelopes; usage/paid-cost aggregates; workflow activation indicators | enabled flags, status enums, counts, non-secret labels, timestamps of last change — never secret payloads/tokens/credential material | observation immediately before enabling pilot/live/paid; older than governed enablement window → stale fail | `UNKNOWN_UNTIL_RUNTIME_REVALIDATION` until live observation; reconstructed partial flags (gemini disabled; pilot awaiting_taha_credential) insufficient alone; Gemini/provider pilot remains disabled until explicit authorization; no paid usage without authorization | `RUNTIME_STATE_MISMATCH` → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED` | pilot/live/paid/workflow/provider-model enablement | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE)`; ND-RECON-02..16; ND-IDENTITY-CONFLICT/ORPHAN; ND-STATE-B |
| `EV-DRIFT-START` | catalog drift digest at start of live evidence window immediately before governed operation | OID-free digest payload fields only | captured at evidence-window start for the same operation that will use EV-DRIFT-END | algorithm and covered object set per Decision Record encoding; value itself live-observed, not reconstructed | missing/stale start digest → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED` | pilot/live/paid until start+end pair validates | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-DRIFT-START)` |
| `EV-DRIFT-END` | catalog drift digest at evidence-window end | OID-free digest payload fields only | must pair with EV-DRIFT-START from same window; end before start invalid | equality with start when operation forbids catalog mutation; undeclared drift → `RUNTIME_STATE_MISMATCH` | `RUNTIME_STATE_MISMATCH` or missing end → `BLOCKED_RUNTIME_REVALIDATION_REQUIRED` / `failed_frozen` if governed | pilot/live/paid until resolved | `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-DRIFT-END)` |

---

## 7. Roles, ownership, schema privileges, SECURITY DEFINER, research_crypto (target design)

### 7.1 Target roles (ND-CHECKPOINT-02)

| Role | Target attributes | Purpose | Current live value |
| --- | --- | --- | --- |
| `postgres` | Login; migration/database owner | Owns all `research` and `research_crypto` objects | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` (`EV-ROLES`) |
| `research_governance` | LOGIN; NOINHERIT; NOT member of APP/N8N | Taha-controlled governance | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` |
| `research_app` | LOGIN; MUST NOT be member of governance; MUST NOT SET ROLE governance | Application runtime | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` |
| `n8n_app` | LOGIN; same membership prohibitions as APP | n8n runtime | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` |
| `research_test` | LOGIN; USAGE+CREATE only on `research_test` | Non-prod helpers | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` |

Object owner target for security-sensitive objects: **`postgres`**. Live owners: observe via preflight / ND-CHECKPOINT-17.

### 7.2 Target schema privileges

```text
REVOKE CREATE ON SCHEMA research FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
GRANT USAGE ON SCHEMA research TO research_app, n8n_app, research_governance;
```

`research_crypto` (created at ND-CHECKPOINT-01): REVOKE ALL from PUBLIC and runtime roles; no USAGE to runtime roles. Current schema ACL cells: `UNKNOWN_UNTIL_LIVE_PREFLIGHT` (`EV-SCHEMA-PRIVS`).

### 7.3 SECURITY DEFINER contract

Every elevated function MUST satisfy: OWNER=postgres; SECURITY DEFINER; `SET search_path = pg_catalog` exactly; fully qualified `research.*` / `research_crypto.*` / `pg_catalog.*`; never unqualified `digest`/`gen_random_uuid`; `REVOKE ALL ON FUNCTION … FROM PUBLIC`; EXECUTE only per Appendix A; `authority_identifier` constant `'Taha'`. Current EXECUTE/PUBLIC cells: `UNKNOWN_UNTIL_LIVE_PREFLIGHT`.

### 7.4 Trusted cryptographic schema `research_crypto` (schema-9 transform target)

```text
CREATE SCHEMA research_crypto AUTHORIZATION postgres;
ALTER EXTENSION pgcrypto SET SCHEMA research_crypto;
```

Reconstructed pre-cutover fact (`RECONSTRUCTED_REFERENCE_ACCEPTED(EV-CRYPTO-LOCATION)`): pgcrypto is in `public`. CP-01 relocates it. Failure to move/verify → `failed_frozen`; version stays 8.

---

## 8. Canonical checkpoint digest contract (ND-DIGEST-CHECKPOINT-V1)

Algorithm identifier: `schema9_checkpoint_digest_v1` for every checkpoint `catalog_digest`.

Encoding conventions:

* UTF-8
* field separator U+001F
* record separator U+001E
* null = `\N`
* Boolean = `t` / `f`
* text = exact PostgreSQL `text` bytes after `COLLATE "C"` sort
* UUID text = lowercase `uuid::text` without braces
* numeric text = canonical base-10 with no locale
* prohibited in digest input: OIDs, `ctid`, xmin/xmax, toast pointers, wall-clock `now()`, row physical order

Algorithm steps:

1. `algorithm_version` = `schema9_checkpoint_digest_v1`
2. Collect the checkpoint’s exact snapshot rows.
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

Bidirectional evidence (ND-DIGEST-BIDIR) — reject all of:

* checkpoint row present without matching recomputed catalog snapshot
* matching catalog snapshot without required checkpoint row
* multiple checkpoint rows for one `(migration_id, checkpoint_id)`
* `algorithm_version` ≠ `schema9_checkpoint_digest_v1`
* stored digest ≠ recomputed digest
* partial object set
* conflicting object definition

Failure state for all digest failures: `failed_frozen`. Expected digest values must not be generated by the same implementation later under test.

---

## 9. Exact checkpoint architecture (18 checkpoints)

**ND-CHECKPOINT-SET** authoritative names in transform order:

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

Any other `checkpoint_id` → `failed_frozen`. Runtime remains frozen through all 18; builders non-executable until restoration (`ND-CHECKPOINT-COMMON`).

| Checkpoint | ND ID | Exact object set | Exact catalog/data predicates | Evidence class | Canonical snapshot fields | Ordering | Serialization | Digest algorithm/version | Completion evidence | No-op predicate | Conflict predicate | Failure state |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `crypto_schema_complete` | `ND-CHECKPOINT-01` | Schema research_crypto; extension pgcrypto relocated into research_crypto; procedures research_crypto.digest(bytea,text) and research_crypto.gen_random_uuid() | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-CRYPTO-LOCATION) baseline proves pre-cutover public; after CP extschema=research_crypto; both procedures resolve in research_crypto; no digest/gen_random_uuid remain executable as unqualified public/research shadows for runtime roles; EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS) for ACL cells | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-CRYPTO-LOCATION, EV-EXTENSIONS, EV-FUNCTIONS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS) | `extname,extschema,proc_identity,proc_schema,proc_owner` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `role_and_default_privileges_complete` | `ND-CHECKPOINT-02` | Roles research_governance, research_test; memberships per design; default privileges revoke-all set for postgres in research/research_crypto | Roles exist with LOGIN/NOINHERIT; CREATE denied on research/research_crypto for APP/N8N/GOV/TEST/PUBLIC; default ACL rows match revoke-all; all privilege cells UNKNOWN_UNTIL_LIVE_PREFLIGHT until preflight | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-ROLES, EV-MEMBERSHIPS, EV-SCHEMA-PRIVS, EV-DEFAULT-PRIVS) | `rolname,rolcanlogin,rolinherit,member_tuple,schema_priv_tuple,default_acl_tuple` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `governance_tables_complete` | `ND-CHECKPOINT-03` | research.taha_governance_actions with PK and uq_taha_gov_one_child_per_parent and any additional indexes named in EV-INDEXES for that table | Table exists; owner=postgres; APP/N8N/GOV/PUBLIC Direct INSERT/UPDATE/DELETE = NONE (EV-TABLE-WRITES live); required indexes present (EV-INDEXES reconstructed names + live confirm) | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-TABLES, EV-INDEXES); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-TABLE-ACLS, EV-TABLE-WRITES) | `rel_identity,owner,acl_expanded,index_identity,indexdef` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `governance_chain_constraints_complete` | `ND-CHECKPOINT-04` | Constraints on research.taha_governance_actions: CHECK action_type set; CHECK authority_identifier=Taha; CHECK decision_value map; CHECK expires_at; FK parent; unique one-child-per-parent index; plus EV-CONSTRAINTS exact names/definitions for that table after creation | Every listed constraint/index definition equals normative text after whitespace-normalized pg_get_constraintdef / pg_get_indexdef | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-CONSTRAINTS, EV-INDEXES) | `conname,contype,condef,index_identity,indexdef` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `credential_scope_complete` | `ND-CHECKPOINT-05` | research.confirm_provider_credential_status(p_pilot_proposal_id uuid, p_provider_code text, p_n8n_credential_label text, p_governance_action_id uuid, p_note text) SECURITY DEFINER OWNER postgres | Identity exact; EXECUTE NONE to APP/N8N/GOV/PUBLIC/TEST until restore (EV-FUNCTION-ACLS/EFFECTIVE live); body contains no secret credential payload parameters | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS, EV-FUNCTION-EFFECTIVE) | `proc_identity,owner,prosecdef,acl_expanded,prosrc_sha256` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `provider_model_enablement_complete` | `ND-CHECKPOINT-06` | Exactly four functions: enable_provider_for_pilot, disable_provider_for_pilot, enable_model_for_pilot, disable_model_for_pilot with Appendix A.4 identities | All four exist; OWNER postgres; SECURITY DEFINER; EXECUTE NONE until restore | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS) | `proc_identity,owner,prosecdef,acl_expanded` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `authorization_activation_invariants_complete` | `ND-CHECKPOINT-07` | research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text); research.trg_authorization_validity_guard() | prosrc contains no allow_pilot_activation GUC path; EXECUTE NONE to APP/N8N/PUBLIC/TEST until restore (GOV final later); validity guard redefined without session-GUC bypass | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS) | `proc_identity,owner,prosecdef,acl_expanded,prosrc_sha256,guc_path_absent(t/f)` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `discrepancy_structures_complete` | `ND-CHECKPOINT-08` | research.accounting_discrepancies + UNIQUE(discrepancy_fingerprint) + append-only readiness predicates | Table exists; UNIQUE present; Direct WRITE NONE for APP/N8N/GOV/PUBLIC/TEST | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-TABLES, EV-INDEXES, EV-CONSTRAINTS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-TABLE-WRITES) | `rel_identity,owner,acl_expanded,unique_index_identity` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `discrepancy_functions_complete` | `ND-CHECKPOINT-09` | research.build_accounting_discrepancy_payload(...) and research.record_accounting_discrepancy(...) exact Appendix A.4 identities | Signatures exact; OWNER postgres; SECURITY DEFINER; EXECUTE NONE for build to APP/N8N/GOV/PUBLIC; record EXECUTE NONE until restore | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS) | `proc_identity,owner,prosecdef,acl_expanded` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `capacity_event_structures_complete` | `ND-CHECKPOINT-10` | research.pilot_capacity_events; research.legacy_reservation_archive; UNIQUEs (pilot_proposal_id, idempotency_key), (pilot_proposal_id, benchmark_case_id), (legacy_reservation_id) | Tables exist; UNIQUEs present; Direct WRITE NONE for runtime roles | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-TABLES, EV-INDEXES, EV-CONSTRAINTS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-TABLE-WRITES) | `rel_identity,owner,acl_expanded,unique_index_identity` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `pilot_builder_complete` | `ND-CHECKPOINT-11` | research.build_provider_request_envelope(...) redefined SECURITY DEFINER; crypto calls fully qualified to research_crypto.* | Signature exact; EXECUTE NONE until restore; prosrc has zero unqualified digest/gen_random_uuid | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS, EV-CRYPTO-LOCATION); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS) | `proc_identity,owner,prosecdef,acl_expanded,prosrc_sha256,unqualified_crypto_count` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `non_pilot_builder_complete` | `ND-CHECKPOINT-12` | research.build_non_pilot_request_envelope(...) exact Appendix A.4 identity | Signature exact; OWNER postgres; SECURITY DEFINER; EXECUTE NONE until restore | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS) | `proc_identity,owner,prosecdef,acl_expanded` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `append_only_trigger_functions_complete` | `ND-CHECKPOINT-13` | Exactly: reject_taha_governance_action_mutation, reject_pilot_capacity_event_mutation, reject_accounting_discrepancy_mutation, reject_legacy_reservation_archive_mutation, reject_legacy_capacity_table_mutation | All five exist in research; OWNER postgres; identities exact | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS) | `proc_identity,owner` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `append_only_triggers_attached` | `ND-CHECKPOINT-14` | Exactly five ENABLE triggers in Appendix A.4b | pg_trigger rows match names/tables/functions/enabled; no disabled required trigger | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-TRIGGERS) | `tg_identity,table_identity,function_identity,enabled` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `test_helpers_isolated` | `ND-CHECKPOINT-15` | Helper set: _r3_clone_question, _r3_new_run, _r4_arm_provider, _r4_case_id, _r4_make_auth, _r4_reset_defaults, _r5a_assert_final_pilot_state, _r5a_final_arm_gates, _r5a_final_assert_state, _r5a_final_reset_defaults, _r5a_insert_fixture_auth, _r5a_repair_reset_defaults, cleanup_test_fixture, record_pilot_usage_for_tests | Each helper is absent from research OR EXECUTE NONE for APP/N8N/GOV/PUBLIC; helpers live in research_test when moved | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-HELPER-FUNCTIONS, EV-FUNCTIONS); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-EFFECTIVE) | `proc_identity,schema,acl_expanded,app_exec(t/f),n8n_exec(t/f),gov_exec(t/f)` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `unsafe_functions_replaced` | `ND-CHECKPOINT-16` | All elevated/runtime bodies that must call crypto/gen_random_uuid | Zero unqualified digest/gen_random_uuid in covered prosrc; search_path=pg_catalog where SECURITY DEFINER required; prosecdef matches disposition | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-FUNCTIONS, EV-CRYPTO-LOCATION); EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-FUNCTION-ACLS) | `proc_identity,prosecdef,search_path_setting,unqualified_crypto_count,prosrc_sha256` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `ownership_locked` | `ND-CHECKPOINT-17` | All security objects in research and research_crypto | Every covered table/view/sequence/function/trigger function owner = postgres; no runtime role owner | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-TABLES, EV-VIEWS, EV-SEQUENCES, EV-FUNCTIONS, EV-TRIGGERS) | `object_class,object_identity,owner_name` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |
| `default_privileges_locked` | `ND-CHECKPOINT-18` | §14/Appendix default-privilege revoke set for postgres in research and research_crypto | pg_default_acl matches revoke-all normative tuples; no future PUBLIC EXECUTE default for those schemas | EXECUTION_TIME_LIVE_PREFLIGHT_REQUIRED(EV-DEFAULT-PRIVS) | `role_name,schema_name,objtype,acl_expanded` | COLLATE "C" by natural key | U+001F/U+001E | `schema9_checkpoint_digest_v1` / ND-DIGEST-CHECKPOINT-V1 | one row in research.schema9_cutover_checkpoints with matching digest | re-running script changes zero catalog bits covered by the digest | partial/extra/conflicting object OR privilege expansion | `failed_frozen` |

### 9.1 Cutover controller outline (design only; not implemented)

States include: `blocked_preflight`, `migrating`, `failed_frozen`, `state_a_complete`, `state_b_verified`, `pilot_blocked`, `pilot_ready` (see §15). Schema version remains 8 until all checkpoints + State A/B succeed. No schema-9 SQL ships in this phase.

---

## 10. Ordered 22-rule reconciliation cascade

**ND-RECON-CASCADE-ORDER:** first-match-wins. Evaluation order: invalid_status → missing_* → duplicates → conflicts → happy paths; then rule 22 fallback.

**ND-RECON-DUP-ORDER:** group by duplicate rule key; winner = minimum `legacy_reservation_id` UUID text under `COLLATE "C"`; non-winners → `slot_conflict` with conflict_kind = duplicate rule name.

Source identity S = `source_v1 | <lowercase uuid text>` of `pilot_capacity_reservations` / `pilot_capacity_reservations_legacy` PK (`ND-IDENTITY-SOURCE`). Capacity effect “consumed fail-closed” means capacity remains consumed and is never restored.

| Order | Rule ID | ND ID | Exact predicate | Explicit exclusions | Source identity | Outcome slot | Capacity effect | Event/archive behavior | Discrepancy behavior | Pilot state | Automatic recovery | Owner action | Evidence class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `ND-RECON-01` | `ND-RECON-01` | `status IS NULL OR status NOT IN ('reserved','finalized','released')` | none | S | slot_conflict + slot_discrepancy | consumed fail-closed | conflict record keyed by S; no archive; no happy-path event | discrepancy_type=`invalid_status` | pilot blocked | N | classify/fix | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 2 | `ND-RECON-02` | `ND-RECON-02` | `pilot_proposal_id IS NULL OR NOT EXISTS (SELECT 1 FROM research.provider_pilot_proposals p WHERE p.id = source.pilot_proposal_id)` | excludes rule 1 true | S | slot_conflict + slot_discrepancy | consumed fail-closed | conflict record; no archive | discrepancy_type=`missing_proposal` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 3 | `ND-RECON-03` | `ND-RECON-03` | `authorization_id IS NULL OR NOT EXISTS (SELECT 1 FROM research.provider_authorization_records a WHERE a.id = source.authorization_id)` | excludes rules 1–2 true | S | slot_conflict + slot_discrepancy | consumed fail-closed | conflict record | discrepancy_type=`missing_authorization` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 4 | `ND-RECON-04` | `ND-RECON-04` | `benchmark_case_id IS NULL OR NOT EXISTS (SELECT 1 FROM research.benchmark_cases c WHERE c.id = source.benchmark_case_id)` | excludes rules 1–3 true | S | slot_conflict + slot_discrepancy | consumed fail-closed | conflict record | discrepancy_type=`missing_case` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 5 | `ND-RECON-05` | `ND-RECON-05` | Exists another source S2 with same `(pilot_proposal_id, benchmark_case_id, idempotency_key)` and S2 ≠ S and both pass rules 1–4 false; S is not the ND-RECON-DUP-ORDER winner | excludes rules 1–4 true; winners excluded | S | slot_conflict + slot_discrepancy for non-winners | capacity held once for winner only | non-winner: conflict only; winner deferred to later matching rule | discrepancy_type=`duplicate_idempotency_key` | pilot blocked | N | dedupe approve | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 6 | `ND-RECON-06` | `ND-RECON-06` | Exists another source S2 with same `(pilot_proposal_id, benchmark_case_id)`, both would create `attempt_consumed`, S is not ND-RECON-DUP-ORDER winner among that group after excluding rule-5 non-winners | excludes rules 1–5 true | S | slot_conflict + slot_discrepancy | capacity held once | conflict on non-winner | discrepancy_type=`duplicate_case_attempt` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 7 | `ND-RECON-07` | `ND-RECON-07` | `envelope_id IS NOT NULL` AND exists another source/event claiming same `envelope_id` with different S, and S is not winner by min(envelope claim source serialization) | excludes rules 1–6 true | S | slot_conflict + slot_discrepancy | capacity held | conflict | discrepancy_type=`duplicate_envelope_link` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 8 | `ND-RECON-08` | `ND-RECON-08` | Source status in (`reserved`,`finalized`) AND after attempting event materialization, required event natural key missing OR event fields mismatch source (`pilot_proposal_id`,`authorization_id`,`benchmark_case_id`,`idempotency_key`, envelope/legacy linkage) | excludes rules 1–7 true | S | slot_conflict + slot_discrepancy | consumed | conflict row; no silent rewrite | discrepancy_type=`reservation_event_conflict` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE) |
| 9 | `ND-RECON-09` | `ND-RECON-09` | For source pilot scope, `provider_usage_ledger` reporting request aggregates for bound auth/case are not equal to event-count authority defined in capacity metric rules (events-only request authority). Conflict when ledger is used as enforcement input OR when recorded ledger request fields contradict event-derived request count under the typed discrepancy payload comparison | excludes rules 1–8 true | S | slot_discrepancy | consumed; builder blocks | events unchanged | discrepancy_type=`reservation_ledger_request_conflict` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 10 | `ND-RECON-10` | `ND-RECON-10` | Ledger success count for pilot-bound non-test rows ≠ COUNT of success authority rows defined in capacity metric rules while source is in scope | excludes rules 1–9 true | S | slot_discrepancy | consumed; builder blocks | events unchanged | discrepancy_type=`reservation_ledger_success_conflict` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 11 | `ND-RECON-11` | `ND-RECON-11` | Projected token sums from events for the source’s pilot/case scope ≠ policy max token fields on the bound authorization/policy row under typed integer equality | excludes rules 1–10 true | S | slot_conflict + slot_discrepancy | consumed; builder blocks | conflict | discrepancy_type=`token_conflict` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 12 | `ND-RECON-12` | `ND-RECON-12` | `projected_cost_usd <> 0` on materializing event OR ledger `estimated_cost_usd > 0` for free-pilot scope OR cost fields disagree under numeric(20,8) eight-decimal equality | excludes rules 1–11 true | S | slot_conflict + slot_discrepancy | consumed; builder blocks | conflict | discrepancy_type=`cost_conflict` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 13 | `ND-RECON-13` | `ND-RECON-13` | Any counter among source-linked projected/ledger/policy integer fields is NULL where NOT NULL required OR value < 0 | excludes rules 1–12 true | S | slot_conflict + slot_discrepancy | consumed fail-closed | conflict | discrepancy_type=`negative_or_malformed_counters` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 14 | `ND-RECON-14` | `ND-RECON-14` | Exists `accounting_discrepancies` row for source pilot scope with no terminal `accounting_discrepancy_acknowledged` governance action in discrepancy scope | excludes rules 1–13 true | S | slot_discrepancy | consumed; builder blocks | retain existing discrepancy | discrepancy retained | pilot blocked | N | acknowledge | PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 15 | `ND-RECON-15` | `ND-RECON-15` | Exists ledger row in pilot scope with no reservation/auth binding natural key matching any source S or event identity | excludes rules 1–14 true; evaluated over ledger orphans discovered during reconcile | ledger orphan natural key | slot_orphan_ledger + slot_discrepancy | no capacity restore | orphan conflict | discrepancy_type=`orphaned_ledger_row` | pilot blocked if pilot-scoped | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-COLUMNS); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 16 | `ND-RECON-16` | `ND-RECON-16` | Exists envelope row with no matching capacity event natural key after reconcile pass | excludes rules 1–15 true | envelope natural key | slot_orphan_envelope + slot_discrepancy | no capacity restore | orphan conflict | discrepancy_type=`orphaned_envelope_row` | pilot blocked | N | inspect | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-COLUMNS); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) |
| 17 | `ND-RECON-17` | `ND-RECON-17` | `status='reserved' AND envelope_id IS NOT NULL` | excludes rules 1–16 true | S | slot_event_normal | attempt_consumed normal | insert/reuse event with `consumption_kind='normal'` and that `envelope_id`; no archive; event `source_refs` includes S | none | capacity held | Y if UNIQUE ok | none | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 18 | `ND-RECON-18` | `ND-RECON-18` | `status='reserved' AND envelope_id IS NULL` | excludes rules 1–17 true | S | slot_event_legacy_orphan | legacy_orphan consumed | event `consumption_kind='legacy_orphan'`, `envelope_id NULL`, `legacy_reservation_id=S`; no archive | none unless later ledger conflict rules already excluded | capacity held | Y | none | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 19 | `ND-RECON-19` | `ND-RECON-19` | `status='finalized' AND envelope_id IS NOT NULL` | excludes rules 1–18 true | S | slot_event_normal | attempt_consumed normal | event linked as normal; no archive | none | capacity held | Y | none | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 20 | `ND-RECON-20` | `ND-RECON-20` | `status='finalized' AND envelope_id IS NULL` | excludes rules 1–19 true | S | slot_event_legacy_orphan | legacy_orphan consumed | event legacy_orphan; no archive | none | capacity held | Y | none | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS) |
| 21 | `ND-RECON-21` | `ND-RECON-21` | `status='released'` | excludes rules 1–20 true | S | slot_archive_released | zero capacity | archive row UNIQUE(legacy_reservation_id=S), `archived_status='released'`; no `attempt_consumed` | none | unchanged | Y | none | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-COLUMNS) |

### Rule 22 — ND-RECON-22

```text
UNCLASSIFIABLE → failed_frozen
```

| Field | Value |
| --- | --- |
| exact predicate | Source or orphan/conflict unit remains after rules 1–21 all false |
| outcome slot | `slot_failed_frozen` |
| capacity effect | consumed fail-closed; no capacity restore |
| event/archive behavior | no happy-path write; durable failure evidence recorded in cutover reconciliation_evidence |
| pilot state | blocked |
| automatic recovery | N |
| owner action | redesign/classify |
| failure behavior | set cutover state `failed_frozen` |
| evidence class | cascade totality; no invented classification |

---

## 11. Total deterministic source mapping (ND-OUTCOME-MAP-TOTAL)

```text
For every source identity S, classify(S) returns exactly one outcome slot O.
```

Outcome slot O ∈ {`slot_event_normal`, `slot_event_legacy_orphan`, `slot_archive_released`, `slot_conflict`, `slot_discrepancy`, `slot_orphan_ledger`, `slot_orphan_envelope`, `slot_failed_frozen`}.

Required properties:

* total over all source identities in EV-RESERVATION-STATE domain
* deterministic for fixed evidence snapshot
* exactly one primary outcome slot per source identity
* no source identity in multiple primary slots
* no silent unclassified source — rule 22 owns every otherwise unclassifiable identity
* multiple source identities may reference one event
* shared events store the complete canonical sorted `source_refs` under `COLLATE "C"` (`ND-IDENTITY-SHARED-EVENT-REFS`)
* every event source reference points to exactly one classified source identity
* aggregate row counts do not prove mapping correctness

Natural identities:

| Kind | Identity | ND |
| --- | --- | --- |
| source reservation | `source_v1 \| <lowercase uuid>` of legacy reservation PK | ND-IDENTITY-SOURCE |
| event | `(pilot_proposal_id, idempotency_key)` for attempt_consumed | ND-IDENTITY-EVENT |
| archive | `legacy_reservation_id` in legacy_reservation_archive | ND-IDENTITY-ARCHIVE |
| discrepancy | `discrepancy_fingerprint` CHAR(64) lowercase hex | ND-IDENTITY-DISCREPANCY |
| conflict | `conflict_kind` + U+001F + `source_v1\|uuid` (+ optional secondary keys sorted) | ND-IDENTITY-CONFLICT |
| orphan | `orphan_kind` + U+001F + durable natural key (`ledger_id` or `envelope_id`) | ND-IDENTITY-ORPHAN |
| shared-event refs | sorted unique array of canonical source serializations | ND-IDENTITY-SHARED-EVENT-REFS |
| outcome slot | exactly one O per S | ND-OUTCOME-SLOT |

---

## 12. State A proof (ND-STATE-A-EQUALITY)

State A completeness is set equality over identities, not counts.

Sets:

```text
source_identity_set      = SourceSet = all ND-IDENTITY-SOURCE serializations in reconcile domain
classified_identity_set  = ClassifiedSet = all S for which classify(S) returned a primary slot
event_source_reference_set = EventRefSet = union of all event source_refs plus singleton refs implied by legacy_reservation_id on legacy_orphan events
archive_source_reference_set = ArchiveRefSet = all archive legacy_reservation_id serializations
discrepancy_source_reference_set = DiscrepancyRefSet
fallback_source_reference_set = FallbackRefSet = all sources classified by rule 22
conflict_identity_set = ConflictRefSet
outcome_slot_set = {slot(S) for S in SourceSet}
```

Required equalities:

```text
SourceSet = ClassifiedSet
SourceSet = (EventRefSet ∪ ArchiveRefSet ∪ ConflictRefSet ∪ DiscrepancyRefSet ∪ FallbackRefSet)
|slot(S)| = 1 for every S in SourceSet
```

Duplicate handling: non-winners appear in ConflictRefSet/DiscrepancyRefSet only; winners appear in their happy-path or later conflict sets exactly once. Orphan ledger/envelope identities are tracked in orphan sets and must not fabricate source identities.

Digests (`reconciliation_algorithm_version` = `schema9_reconcile_v2`), each = SHA-256 over sorted unique identity strings joined by U+001E under `schema9_set_digest_v1` prefix (OID-free):

* `source_pk_set_digest`
* `classified_identity_set_digest`
* `event_source_ref_set_digest`
* `archive_identity_set_digest`
* `conflict_identity_set_digest`
* `discrepancy_identity_set_digest`
* `fallback_identity_set_digest`

Missing identity, multiply classified identity, or unknown reference → `failed_frozen`. Inequality → `failed_frozen`. Evidence: `RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE)`.

State A succeeds only when every source identity appears in exactly one valid outcome slot.

---

## 13. State B independent proof (ND-STATE-B-RECOMPUTE)

State B independently recomputes all State A sets and digests from durable legacy + schema-9 tables only. Checkpoint presence is insufficient. Must not trust State A’s cached classification as its only source. Must not read `schema9_cutover_checkpoints` as proof of completeness. Must not reference the pre-rename table name after rename checkpoint commits.

Inputs only:

* durable legacy reservation table (current name from evidence: `pilot_capacity_reservations` or `pilot_capacity_reservations_legacy`)
* `research.pilot_capacity_events`
* `research.legacy_reservation_archive`
* `research.accounting_discrepancies`
* conflict/orphan evidence tables/rows persisted by reconcile
* bound proposal/auth/case/ledger/envelope durable rows needed by predicates

Must recompute: SourceSet, EventRefSet, ArchiveRefSet, DiscrepancyRefSet, FallbackRefSet, outcome-slot assignment map, algorithm version, all set digests; assert zero missing identities, zero multiply classified identities, zero unknown references.

Any mismatch → `failed_frozen`. Evidence: `RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-TABLES)`; `PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE)`.

---

## 14. Freeze and final privilege architecture

| Phase | Behavior | Privilege values |
| --- | --- | --- |
| Migration freeze | ND-FREEZE-REVOKE-WRITES: REVOKE INSERT/UPDATE/DELETE from all runtime roles on all research base tables that currently grant them | cells from `EV-TABLE-WRITES` = `UNKNOWN_UNTIL_LIVE_PREFLIGHT` until preflight |
| Runtime freeze | ND-FREEZE-REVOKE-EXECUTE: REVOKE EXECUTE on all functions not in keep-EXECUTE set | keep set names confirmed by EV-FUNCTIONS; current EXECUTE = `UNKNOWN_UNTIL_LIVE_PREFLIGHT` |
| PUBLIC function execution | target NONE elevated; observe live | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` (`EV-FUNCTION-PUBLIC`) |
| Direct / inherited / SET ROLE-only execution | effective matrix | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` (`EV-FUNCTION-EFFECTIVE`) |
| Owners | target postgres for security objects | confirmed at ND-CHECKPOINT-17; live owners via preflight when material |
| Superusers | inventory via EV-ROLES | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` |
| Schema USAGE/CREATE | ND-CHECKPOINT-02 targets | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` (`EV-SCHEMA-PRIVS`) |
| Table / column writes | freeze then Appendix A restore | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` |
| Default privileges | revoke-all locked at CP-18 | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` (`EV-DEFAULT-PRIVS`) |
| Post-blanket-grant functions | migration-6 GRANT surface not historical authority | live ACL preflight required |
| Final least-privilege | ND-FINAL-GRANT-APPENDIX-A after restoration txn A — exactly Appendix A; no ALL; no PUBLIC elevated | live ACL must match Appendix A after restore |
| Helpers final | ND-FINAL-HELPERS-TEST — EXECUTE only research_test after move | `UNKNOWN_UNTIL_LIVE_PREFLIGHT` until effective matrix confirms |

No preflight mismatch may trigger automatic `GRANT`, `REVOKE`, or ownership changes.

---

## 15. Failure-state architecture

| State | Entry predicate | Required evidence | Evidence class | Allowed operations | Prohibited operations | Recovery authority | Audit artifact | Exit predicate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `blocked_preflight` | any of 11 live markers unresolved or comparison not MATCHES/SAFE_DECLARED | all 11 preflight markers | EXECUTION_TIME_LIVE_PREFLIGHT | read-only inspection; documentation | schema-9 execution; privilege mutation; pilot/live/paid | human operator after evidence collected | preflight discrepancy log | all 11 resolve with permitted outcomes |
| `migrating` | preflight passed; transform scripts executing checkpoints 1–18 | checkpoint digests + classed EV deps | reconstructed + live as per checkpoint | checkpoint scripts only | runtime grants; pilot; live calls | none automatic | schema9_cutover_checkpoints rows | all 18 checkpoints present with matching digests |
| `failed_frozen` | digest mismatch, conflict predicate, rule 22, State A/B mismatch, or privilege conflict in governed state | failure evidence row | classed per failing gate | freeze holds; diagnostics | further transform; restore grants; pilot/live/paid | redesign/owner classify; no automatic repair | reconciliation_evidence / cutover failure record | only explicit owner-authorized redesign path |
| `state_a_complete` | State A identity-set equalities hold | EV-RESERVATION-STATE domain + set digests | RECONSTRUCTED_REFERENCE_ACCEPTED + live domain rows under precedence | proceed to State B | pilot/live/paid | n/a | State A digests | State B starts |
| `state_b_verified` | independent recomputation matches State A digests/sets | durable tables only | RECONSTRUCTED_REFERENCE_ACCEPTED(EV-RESERVATION-STATE, EV-TABLES); PILOT_TIME_RUNTIME_REVALIDATION_REQUIRED(EV-SAFETY-BASELINE) for related rows | proceed toward runtime restore under freeze | pilot/live/paid until runtime gates pass | n/a | State B digests | runtime restoration authorized |
| `pilot_blocked` | any of 3 runtime markers unknown/mismatch OR cascade pilot-blocked slots | EV-SAFETY-BASELINE, EV-DRIFT-START, EV-DRIFT-END | PILOT_TIME_RUNTIME_REVALIDATION | none of pilot/live/paid | pilot enablement; live API; workflows; paid | owner after runtime revalidation | runtime revalidation log | all 3 runtime markers resolve |
| `pilot_ready` | State B verified AND all 3 runtime markers resolved AND no blocking discrepancy | runtime markers + safety baseline | PILOT_TIME_RUNTIME_REVALIDATION + LIVE_CATALOG when observed | pilot operations explicitly authorized by governance | none beyond governance scope | Taha via research_governance | enablement governance actions | disablement / expiry / discrepancy returns to pilot_blocked |

Unknown evidence must never transition directly to a permissive state.

---

## 16. Security invariants

* no live provider or model call during migration
* no paid usage during migration or while runtime markers unknown
* no workflow activation while runtime markers unknown
* no credential secret extraction (safe non-secret columns only)
* no Equitify access
* no SENTINEL modification
* no schema-9 execution before live preflight for all 11 markers
* no pilot before runtime revalidation for all 3 markers
* no automatic privilege remediation
* no silent acceptance of extra objects
* no reconstructed evidence represented as live evidence

---

## 17. Enablement, governance, capacity, discrepancy, envelopes, activation, helpers (design targets)

Revision 7 enablement sequence, governance chain rules, capacity event tables, discrepancy fingerprinting, envelope builders, GUC-free activation, helper isolation, and append-only triggers remain the **target design**. They are not re-asserted as current live ACL facts. Where those sections previously implied fixed current grants, Revision 8 replaces those implications with `UNKNOWN_UNTIL_LIVE_PREFLIGHT` / `UNKNOWN_UNTIL_RUNTIME_REVALIDATION` and the Decision Record ND-* identifiers.

Normative pointers:

* Enable/disable lifecycle → ND-CHECKPOINT-05/06/07; EV-SAFETY-BASELINE runtime gate
* `taha_governance_actions` linear chains → ND-CHECKPOINT-03/04
* Capacity events / legacy archive → ND-CHECKPOINT-10; ND-IDENTITY-*; ND-RECON-*
* Discrepancy persistence → ND-CHECKPOINT-08/09; ND-IDENTITY-DISCREPANCY
* Envelope builders → ND-CHECKPOINT-11/12
* Activation invariant (no GUC) → ND-CHECKPOINT-07
* Helper isolation → ND-CHECKPOINT-15; ND-FINAL-HELPERS-TEST
* Append-only triggers → ND-CHECKPOINT-13/14

---

## 18. Default privileges (future objects)

Target (ND-CHECKPOINT-18 / ND-FINAL):

```text
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research REVOKE ALL ON TABLES FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research REVOKE ALL ON FUNCTIONS FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research_crypto REVOKE ALL ON TABLES FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research_crypto REVOKE ALL ON FUNCTIONS FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
```

Current `pg_default_acl`: `UNKNOWN_UNTIL_LIVE_PREFLIGHT` (`EV-DEFAULT-PRIVS`). Future objects = NONE until an explicit allowlist migration updates Appendix A.

---

## 19. Phase 4 obligations (tests not written here)

Phase 4 **must** implement obligations (not cases in this phase):

* all 18 checkpoints (ND-TEST-CP-SET; ND-TEST-CP-01…18)
* all 22 reconciliation rules
* witness `W1..W22`
* precedence (ND-TEST-RECON-PRECEDENCE)
* witness-based shadowing (ND-TEST-RECON-SHADOW)
* reachability (ND-TEST-RECON-REACH)
* fallback (ND-TEST-RECON-FALLBACK)
* boundary witnesses `B1..B21`
* decisive-field mutation (ND-TEST-RECON-MUTATE)
* reconstructed-reference match
* live-catalog exact match
* safe declared variance
* unknown extra object
* missing required object
* privilege expansion
* privilege reduction
* owner mismatch
* reconstructed/live digest mismatch
* no live catalog
* stale runtime evidence
* missing runtime evidence
* State A identity-set mismatch
* State B independent recomputation mismatch
* shared-event references
* aggregate counts matching while identities differ
* ND-TEST-DIGEST-EMPTY / OID-FREE / BIDIR
* ND-TEST-MAP-TOTAL / ND-TEST-SHARED-EVENT / ND-TEST-IDENTITY-*

Expected test calculations must remain independent from the production preflight implementation.

---

## 20. Banned language validation

This document contains **zero** positive architectural claims of: `bijection`; `historical live catalog reproduced`; `all evidence resolved`; `uniform function ACL`; `research_app DELETE on every table`; `all roles are fixed`; `reasonable default`; `assume current value`. Corrective prose mentioning bans is labeled non-normative in §0. Unresolved generic `EVIDENCE_REQUIRED(...)` markers are absent; every marker has an explicit evidence class.

---

## Appendix A — Machine-exact object allowlist (final target after restoration)

**Rule:** Any `research` / `research_crypto` object not listed is denied (`NONE`) to runtime roles and PUBLIC unless a row grants otherwise.
**Owner:** `postgres` unless Disposition says MOVED.
**Current live privilege cells:** `UNKNOWN_UNTIL_LIVE_PREFLIGHT` until execution-time preflight and restoration txn A complete.

Privilege tokens: `NONE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `EXECUTE`, `USAGE`, `MOVED TO research_test`, `RENAMED`, `DEPRECATED`.

### A.1 Tables (final target)

| Object identity | Type | Owner | PUBLIC | research_app | n8n_app | research_governance | research_test | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| research.automatic_scores | table | postgres | NONE | SELECT,INSERT,UPDATE | SELECT | SELECT | NONE | KEEP |
| research.benchmark_cases | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.benchmark_runs | table | postgres | NONE | SELECT,INSERT,UPDATE | SELECT | SELECT | NONE | KEEP |
| research.benchmark_suites | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.decision_rationales | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.evidence_claim_links | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.evidence_items | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.gemini_pilot_request_builder_specs | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.improvement_proposals | table | postgres | NONE | SELECT,INSERT,UPDATE | SELECT | SELECT | NONE | KEEP |
| research.live_request_envelopes | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.model_outputs | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.models | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.monthly_role_rankings | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.orchestration_failures | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.pilot_capacity_reservations_legacy | table | postgres | NONE | NONE | NONE | NONE | NONE | RENAMED from pilot_capacity_reservations; DEPRECATED |
| research.proposal_versions | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.provider_adapter_requests | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.provider_adapter_responses | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.provider_adapter_versions | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_authorization_records | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_budget_policies | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_capabilities | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_credential_status | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_health_checks | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.provider_model_candidates | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_pilot_proposals | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_policy_verifications | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_rate_limit_policies | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_usage_ledger | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.providers | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.question_status_transitions | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.reconsideration_conditions | table | postgres | NONE | SELECT,INSERT,UPDATE | SELECT | SELECT | NONE | KEEP |
| research.repair_attempts | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.research_closure_records | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.research_findings | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.research_priorities | table | postgres | NONE | SELECT,INSERT,UPDATE | SELECT | SELECT | NONE | KEEP |
| research.research_question_relationships | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.research_question_versions | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.research_questions | table | postgres | NONE | SELECT,INSERT,UPDATE | SELECT | SELECT | NONE | KEEP |
| research.research_run_stages | table | postgres | NONE | SELECT,INSERT,UPDATE | SELECT | SELECT | NONE | KEEP |
| research.research_runs | table | postgres | NONE | SELECT,INSERT,UPDATE | SELECT | SELECT | NONE | KEEP |
| research.research_status_history | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.run_failures | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.schema_version | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.source_snapshots | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.sources | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.taha_decisions | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.taha_scores | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.taha_governance_actions | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | NEW schema-9 |
| research.pilot_capacity_events | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | NEW schema-9 |
| research.accounting_discrepancies | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | NEW schema-9 |
| research.legacy_reservation_archive | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | NEW schema-9 |
| research.schema9_cutover_state | table | postgres | NONE | NONE | NONE | NONE | NONE | NEW schema-9 |
| research.schema9_cutover_checkpoints | table | postgres | NONE | NONE | NONE | NONE | NONE | NEW schema-9 |

DELETE = NONE for every table for every runtime role in the final target. `research.pilot_capacity_reservations` (unrenamed) MUST NOT exist after the rename checkpoint commits. Final APP write cells above are **targets**, not current live claims.

### A.2 Views (final target)

| Object identity | Type | Owner | PUBLIC | research_app | n8n_app | research_governance | research_test | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| research.v_active_research_queue | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_cost_per_successful_run | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_decision_history_by_topic | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_duplicate_question_warnings | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_enabled_provider_readiness | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_failure_rate | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_gemini_pilot_5a | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_highest_priority_unanswered | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_insufficient_evidence_warning | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_latency_percentile_summary | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_latest_monthly_ranking | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_missing_credentials | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_models_awaiting_verification | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_proposals_awaiting_taha | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_provider_health_summary | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_provider_performance_by_role | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_questions_blocked_missing_evidence | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_rejected_eligible_reconsideration | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_remaining_daily_quota | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_remaining_monthly_budget | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_settled_questions | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_simulated_decision_cards | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.v_unauthorized_call_warnings | view | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |

### A.3 Sequences

None in schema `research` or `research_crypto` for application use at schema 9 (`RECONSTRUCTED_REFERENCE_ACCEPTED(EV-SEQUENCES)` empty-set). Future sequences: NONE to runtime roles until allowlist migration.

### A.4 Functions

Columns: PUBLIC / research_app / n8n_app / research_governance EXECUTE (`Y` or `N`). research_test EXECUTE = `N` for all `research.*` functions unless noted.

| Object identity | Type | Owner | PUBLIC | research_app | n8n_app | research_governance | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| research._allowed_source_ids(p_question_uuid uuid) | function | postgres | N | Y | N | N | KEEP |
| research._append_completed_stage(p_run_id uuid, p_stage text) | function | postgres | N | Y | N | N | KEEP |
| research._evidence_bundle_for_question(p_question_uuid uuid) | function | postgres | N | Y | N | N | KEEP |
| research._r3_clone_question(p_code text, p_scenario text) | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r3_new_run(p_code text, p_qid uuid, p_scenario text, p_budget numeric) | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r4_arm_provider(p_code text, p_enable_provider boolean, p_enable_model boolean, p_verify_model boolean, p_free_confirmed boolean, p_cred_present boolean, p_daily_req integer, p_daily_tok integer) | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r4_case_id() | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r4_make_auth(p_provider text, p_model_id uuid, p_case uuid, p_max_req integer, p_max_tok integer, p_max_cost numeric, p_expires timestamptz) | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r4_reset_defaults() | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r5a_assert_final_pilot_state() | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r5a_final_arm_gates() | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r5a_final_assert_state() | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r5a_final_reset_defaults() | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r5a_insert_fixture_auth(p_fixture text, p_pilot uuid, p_case uuid, p_provider uuid, p_model uuid) | function | postgres | N | N | N | N | MOVED TO research_test |
| research._r5a_repair_reset_defaults() | function | postgres | N | N | N | N | MOVED TO research_test |
| research._record_failure(p_run_id uuid, p_stage text, p_class text, p_detail text) | function | postgres | N | Y | N | N | KEEP |
| research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text) | function DEFINER | postgres | N | N | N | Y | KEEP; redefine per §10 |
| research.append_governance_action(p_action_type text, p_proposal_id uuid, p_authorization_id uuid, p_provider_id uuid, p_model_id uuid, p_decision_value text, p_material_fingerprint char(64), p_supersedes_action_id uuid, p_issued_at timestamptz, p_expires_at timestamptz, p_payload jsonb) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.approve_pilot_proposal(p_pilot_code text) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.build_accounting_discrepancy_payload(p_discrepancy_type text, p_pilot_proposal_id uuid, p_authorization_id uuid, p_provider_id uuid, p_model_id uuid, p_benchmark_case_id uuid, p_idempotency_key text, p_operation text, p_observed_attempt_count bigint, p_observed_success_count bigint, p_observed_input_tokens bigint, p_observed_output_tokens bigint, p_observed_cost_usd numeric, p_expected_max_requests integer, p_expected_max_successful_calls integer, p_expected_max_input_tokens integer, p_expected_max_output_tokens integer, p_expected_max_cost_usd numeric, p_ledger_request_count bigint, p_ledger_success_count bigint, p_ledger_input_tokens bigint, p_ledger_output_tokens bigint, p_ledger_cost_usd numeric, p_schema_version integer) | function DEFINER | postgres | N | N | N | N | NEW; DEFINER-internal only |
| research.build_decision_card(p_run_id uuid) | function | postgres | N | Y | N | N | KEEP |
| research.build_non_pilot_request_envelope(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_canonical_request jsonb, p_claimed_credential_status text) | function DEFINER | postgres | N | Y | N | N | NEW |
| research.build_provider_request_envelope(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_canonical_request jsonb, p_claimed_credential_status text) | function DEFINER | postgres | N | Y | N | N | KEEP; redefine per §4 |
| research.cancel_research_run(p_run_id uuid, p_reason text) | function | postgres | N | Y | N | N | KEEP |
| research.cleanup_test_fixture(p_fixture_id text) | function | postgres | N | N | N | N | MOVED TO research_test |
| research.compute_priority_v1(constitutional_impact numeric, measured_performance_gap numeric, safety_impact numeric, expected_value numeric, urgency numeric, evidence_availability numeric, implementation_cost numeric, duplication_penalty numeric) | function | postgres | N | Y | N | N | KEEP |
| research.confirm_provider_credential_status(p_pilot_proposal_id uuid, p_provider_code text, p_n8n_credential_label text, p_governance_action_id uuid, p_note text) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.disable_model_for_pilot(p_pilot_code text, p_provider_code text, p_model_id_provisional text) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.disable_provider_for_pilot(p_pilot_code text, p_provider_code text) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.enable_model_for_pilot(p_pilot_code text, p_provider_code text, p_model_id_provisional text) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.enable_provider_for_pilot(p_pilot_code text, p_provider_code text) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.enforce_completed_run_evidence() | trigger function | postgres | N | N | N | N | KEEP |
| research.estimate_provider_cost_usd(p_provider_code text, p_input_tokens integer, p_output_tokens integer) | function | postgres | N | Y | N | N | KEEP |
| research.forbid_mutation() | trigger function | postgres | N | N | N | N | KEEP |
| research.forbid_terminal_run_wipe() | trigger function | postgres | N | N | N | N | KEEP |
| research.gemini_pilot_5a_gate_status() | function | postgres | N | Y | N | Y | KEEP |
| research.live_preflight(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_claimed_credential_status text, p_projected_input_tokens integer, p_projected_output_tokens integer, p_is_retry boolean, p_fallback_provider text) | function DEFINER | postgres | N | Y | N | N | KEEP; redefine per §4 |
| research.materialize_proposal_from_run(p_run_id uuid) | function | postgres | N | Y | N | N | KEEP |
| research.mock_adapter_invoke(p_request_id uuid) | function | postgres | N | Y | N | N | KEEP |
| research.mock_model_for_stage(p_stage text) | function | postgres | N | Y | N | N | KEEP |
| research.mock_provider_for_stage(p_stage text) | function | postgres | N | Y | N | N | KEEP |
| research.orchestrate_research_run(p_run_id uuid) | function | postgres | N | Y | N | N | KEEP |
| research.parse_provider_fixture_response(p_provider_code text, p_fixture jsonb) | function | postgres | N | Y | N | N | KEEP |
| research.pilot_capacity_snapshot(p_pilot_id uuid) | function | postgres | N | Y | N | Y | KEEP; rewrite events-only |
| research.pilot_case_attempt_count(p_pilot_id uuid, p_benchmark_case_id uuid) | function | postgres | N | Y | N | Y | KEEP; rewrite events-only |
| research.proposal_has_evidence(p_evidence_ids uuid[]) | function | postgres | N | Y | N | N | KEEP |
| research.record_accounting_discrepancy(p_discrepancy_type text, p_pilot_proposal_id uuid, p_authorization_id uuid, p_provider_id uuid, p_model_id uuid, p_benchmark_case_id uuid, p_idempotency_key text, p_operation text, p_observed_attempt_count bigint, p_observed_success_count bigint, p_observed_input_tokens bigint, p_observed_output_tokens bigint, p_observed_cost_usd numeric, p_expected_max_requests integer, p_expected_max_successful_calls integer, p_expected_max_input_tokens integer, p_expected_max_output_tokens integer, p_expected_max_cost_usd numeric, p_ledger_request_count bigint, p_ledger_success_count bigint, p_ledger_input_tokens bigint, p_ledger_output_tokens bigint, p_ledger_cost_usd numeric, p_schema_version integer, p_expected_fingerprint char(64)) | function DEFINER | postgres | N | Y | N | Y | NEW |
| research.record_authorization_spend(p_authorization_id uuid, p_requests integer, p_tokens integer, p_cost numeric, p_note text) | function DEFINER | postgres | N | Y | N | N | KEEP; rejects pilot-linked |
| research.record_pilot_usage_for_tests(p_authorization_id uuid, p_input_tokens integer, p_output_tokens integer, p_success boolean, p_fixture_id text, p_is_retry boolean) | function | postgres | N | N | N | N | MOVED TO research_test |
| research.reject_accounting_discrepancy_mutation() | trigger function | postgres | N | N | N | N | NEW |
| research.reject_legacy_capacity_table_mutation() | trigger function | postgres | N | N | N | N | NEW |
| research.reject_legacy_reservation_archive_mutation() | trigger function | postgres | N | N | N | N | NEW |
| research.reject_pilot_capacity_event_mutation() | trigger function | postgres | N | N | N | N | NEW |
| research.reject_taha_governance_action_mutation() | trigger function | postgres | N | N | N | N | NEW |
| research.run_stage(p_run_id uuid, p_stage text, p_scenario_hint text) | function | postgres | N | Y | N | N | KEEP |
| research.sha256_hex(p_text text) | function | postgres | N | Y | N | N | KEEP; redefine to research_crypto.digest |
| research.trg_authorization_validity_guard() | trigger function | postgres | N | N | N | N | KEEP; redefine per §10 |
| research.trg_block_evidence_delete_after_decision() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_envelope_immutability() | trigger function | postgres | N | N | N | N | KEEP; rewrite remove reservation refs |
| research.trg_evidence_immutable_body() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_proposal_ready_requires_evidence() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_question_decision_requires_supported_proposal() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_question_status_history() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_question_status_validate() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_run_stage_immutable() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_set_priority_scores() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_sync_question_priority() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_usage_ledger_immutability() | trigger function | postgres | N | N | N | N | KEEP |
| research.try_enter_decision_from_partial(p_run_id uuid) | function | postgres | N | Y | N | N | KEEP |
| research_crypto.digest(bytea, text) | extension function | postgres | N | N | N | N | pgcrypto moved; no runtime EXECUTE |
| research_crypto.gen_random_uuid() | extension function | postgres | N | N | N | N | pgcrypto moved; no runtime EXECUTE |


### A.4b Trigger objects

| Object identity | Type | Owner context | Enabled | Table | Function | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| research.trg_reject_taha_governance_action_mutation | trigger | postgres | ENABLE | research.taha_governance_actions | research.reject_taha_governance_action_mutation() | NEW |
| research.trg_reject_pilot_capacity_event_mutation | trigger | postgres | ENABLE | research.pilot_capacity_events | research.reject_pilot_capacity_event_mutation() | NEW |
| research.trg_reject_accounting_discrepancy_mutation | trigger | postgres | ENABLE | research.accounting_discrepancies | research.reject_accounting_discrepancy_mutation() | NEW |
| research.trg_reject_legacy_reservation_archive_mutation | trigger | postgres | ENABLE | research.legacy_reservation_archive | research.reject_legacy_reservation_archive_mutation() | NEW |
| research.trg_reject_legacy_capacity_table_mutation | trigger | postgres | ENABLE | research.pilot_capacity_reservations_legacy | research.reject_legacy_capacity_table_mutation() | NEW |

### A.5 Schema privileges summary

| Object | PUBLIC | research_app | n8n_app | research_governance | research_test |
| --- | --- | --- | --- | --- | --- |
| SCHEMA research | NONE | USAGE | USAGE | USAGE | NONE |
| SCHEMA research CREATE | NONE | NONE | NONE | NONE | NONE |
| SCHEMA research_crypto | NONE | NONE | NONE | NONE | NONE |
| SCHEMA research_crypto CREATE | NONE | NONE | NONE | NONE | NONE |
| SCHEMA research_test | NONE | NONE | NONE | NONE | USAGE, CREATE |

---


**Revision 8 note:** Final EXECUTE/PUBLIC/effective privilege cells in the tables above are **targets after restoration txn A** (ND-FINAL-GRANT-APPENDIX-A). Current live values remain UNKNOWN_UNTIL_LIVE_PREFLIGHT (EV-FUNCTION-ACLS, EV-FUNCTION-PUBLIC, EV-FUNCTION-EFFECTIVE, EV-TABLE-WRITES, EV-SCHEMA-PRIVS, EV-DEFAULT-PRIVS). Do not treat these rows as current live catalog observations.

## Appendix B — Open risks (accepted)

- Owner/`postgres` break-glass DML still possible; mitigated by append-only and activation triggers recomputing prerequisites.
- Theft of `research_governance` login equals full governance power; keep local-only.
- Round 4 adapters must call `build_non_pilot_request_envelope` after schema 9 implementation.
- Human operator error during cutover windows; mitigated by durable freeze ACLs, catalog-derived restart classification, and version-8 hold until validation under freeze succeeds.
- `ALTER EXTENSION … SET SCHEMA` requires exclusive migration window; failure keeps version 8 and runtime frozen (`failed_frozen`).
- Historical live schema-8 was not recovered; live preflight and runtime revalidation remain mandatory gates.

---

## Appendix C — Validation checklist (Phase 3)

* architecture-only file: `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md`
* Decision Record untouched
* Evidence Policy untouched
* test plan untouched
* no SQL / schema-9 implementation
* 31 markers; 17/11/3; 0 ambiguous; 0 unclassified
* 18 checkpoints; 22 rules; rule 22 fail-closed
* total deterministic source mapping (word `bijection` absent as positive claim)
* State A identity-set equality; State B independent recomputation
* provenance on every normative inventory/checkpoint/rule row
* no unknown value stated as fact
* no OID in identities/digests
* reconstructed manifest `09C2EA9957FEF7357B89824796B46C36DE5E0B9DE414D617F642F4EFC1D5BCB2`
