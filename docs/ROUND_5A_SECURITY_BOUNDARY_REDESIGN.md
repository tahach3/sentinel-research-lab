# Round 5A — Security Boundary Redesign (Revision 3)

**Status:** Design only. Not implemented.
**Baseline HEAD:** `db4287e3ff0c3bfe488f054118748759bdd991f8` / schema version 8 runtime
**Supersedes:** Revision 2 content of this file at that commit
**Scope:** Machine-exact privilege, governance, capacity, discrepancy, enablement/disablement, and schema 8→9 migration state machine for Gemini pilot + Round 1–4 runtime compatibility.
**Non-goals:** Implementing SQL in this round; storing API keys; Round 5B live HTTP; Equitify/SENTINEL changes; advancing schema version; changing live roles/grants.

Resolves Codex findings: schema CREATE / shadow objects; governance-action identity; allowlist exactness; legacy null-envelope reservations; discrepancy durability; migration restart/partial-cutover; enablement/disablement completeness.

---

## 1. Threat model

Must eliminate at the **privilege and ownership** layer:

1. Session-GUC activation
2. Mutable/deletable capacity evidence
3. Application-callable approval/arm helpers
4. Direct envelope insertion
5. Schema-CREATE shadow objects against SECURITY DEFINER resolution
6. Unqualified name resolution via `search_path` / `pg_temp`

Adversary: `research_app` / `n8n_app` with any SQL allowed by their grants, including `set_config`, `SET ROLE` attempts, `CREATE` attempts, and `PUBLIC` defaults.

---

## 2. Roles and ownership

| Role | Attributes | Purpose |
| --- | --- | --- |
| `postgres` | Login; migration/database owner | Owns all `research` objects; sole CREATE on schema `research`; sole granter of `research_governance` membership |
| `research_governance` | LOGIN; NOINHERIT; NOT member of `research_app` or `n8n_app` | Taha-controlled governance session only |
| `research_app` | LOGIN; MUST NOT be member of `research_governance`; MUST NOT `SET ROLE research_governance` | Application / automation runtime |
| `n8n_app` | LOGIN; same membership prohibitions as `research_app` | n8n runtime |
| `research_test` | LOGIN; USAGE+CREATE only on schema `research_test`; NO CREATE on schema `research` | Non-prod test helpers only |
| Taha | Human | Sole approval authority; operates as `research_governance` after intentional local login |

Object owner for all security-sensitive `research` tables, views, triggers, and elevated functions: **`postgres`**. Runtime roles must not own objects in `research`. Runtime roles must not `ALTER` functions, triggers, tables, sequences, views, schemas, or ownership.

---

## 3. Schema privileges and shadow-object prevention

Exact schema privileges after cutover:

```text
REVOKE CREATE ON SCHEMA research FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
GRANT USAGE ON SCHEMA research TO research_app, n8n_app, research_governance;
```

Only `postgres` may CREATE or REPLACE objects in schema `research`.

`research_test` schema (created in migration step 3 if absent):

```text
CREATE SCHEMA IF NOT EXISTS research_test AUTHORIZATION research_test;
REVOKE ALL ON SCHEMA research_test FROM PUBLIC, research_app, n8n_app, research_governance;
GRANT USAGE, CREATE ON SCHEMA research_test TO research_test;
```

Catalog assertion: zero rows where `research_app`, `n8n_app`, `research_governance`, `research_test`, or `PUBLIC` hold `CREATE` on schema `research`.

---

## 4. SECURITY DEFINER contract (normative)

Every elevated function MUST satisfy all of:

1. OWNER = `postgres`
2. `SECURITY DEFINER`
3. `SET search_path = pg_catalog` (exactly; no `research`; no `pg_temp`; no `public`)
4. Every object reference fully qualified as `research.<name>` or `pg_catalog.<name>`
5. NEVER unqualified identifiers for tables, views, sequences, functions, types, or operators that resolve via search_path
6. NEVER rely on `research` being present in `search_path`
7. `REVOKE ALL ON FUNCTION … FROM PUBLIC;`
8. `EXECUTE` granted to exactly the role enumerated in Appendix A
9. Reject caller-controlled role, authority, or schema values; `authority_identifier` is constant `'Taha'` inside DEFINER bodies

Configured `search_path` alone is insufficient without fully qualified references.

---

## 5. Enablement and disablement lifecycle

### 5.1 Exact enablement sequence

```text
credential confirmed
→ pilot approved
→ provider enabled for proposal
→ model enabled for proposal
→ authorization activated
→ envelope preparation permitted
```

Mapped functions (all OWNER `postgres`, SECURITY DEFINER, EXECUTE `research_governance` only except builders):

| Step | Function | Governance action_type appended |
| --- | --- | --- |
| 1 | `research.confirm_provider_credential_status(p_provider_code text, p_n8n_credential_label text, p_note text)` | `credential_status_confirmed` |
| 2 | `research.approve_pilot_proposal(p_pilot_code text)` | `pilot_approved` |
| 3 | `research.enable_provider_for_pilot(p_pilot_code text, p_provider_code text)` | `provider_enabled_for_proposal` |
| 4 | `research.enable_model_for_pilot(p_pilot_code text, p_provider_code text, p_model_id_provisional text)` | `model_enabled_for_proposal` |
| 5 | `research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text)` | `authorization_activation_approved` |
| 6 | `research.build_provider_request_envelope(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_canonical_request jsonb, p_claimed_credential_status text)` as `research_app` | none (consumes capacity) |

Each step fails closed with no table mutation when any prior step’s matching non-superseded governance action is missing, expired, fingerprint-mismatched, or revoked. Provider/model enablement is **proposal-scoped**: `providers.enabled` / `provider_model_candidates.enabled` may be set true only when a non-superseded `provider_enabled_for_proposal` / `model_enabled_for_proposal` action exists for that exact `(proposal_id, provider_id[, model_id])`. Enablement for one proposal does not authorize unrelated pilots.

Preconditions for enable functions (fail closed; no mutation on failure):

- Pilot exists; non-superseded `pilot_approved` action; not expired
- Credential status for provider = `present` via non-superseded `credential_status_confirmed`
- Provider/model identity matches pilot row exactly
- Function appends the authorizing action via `append_governance_action` in the same transaction
- Pilot cost = 0; retries false; fallback false; confidentiality = `public_or_synthetic`
- Enablement expiry recorded on the governance action as `min(pilot.expires_at, issued_at + pilot.expiry_hours_after_approval)`

### 5.2 Disablement

Functions:

- `research.disable_provider_for_pilot(p_pilot_code text, p_provider_code text)` → appends `provider_disabled_for_proposal`
- `research.disable_model_for_pilot(p_pilot_code text, p_provider_code text, p_model_id_provisional text)` → appends `model_disabled_for_proposal`

Effects (exact):

1. Immediately blocks new `live_preflight` success and new envelope creation for that proposal binding
2. Active authorization rows remain as historical rows but become **non-executable** (preflight/builder treat as denied while disable supersedes the matching enable action)
3. Prepared envelopes: allow exact idempotent retrieval of existing envelope JSON via builder replay; permanently prohibit execution (`executable` remains false; return flag `execution_denied=true` after disable)
4. No new envelopes; no expiry extension
5. Re-enable requires a **NEW** matching governance enable action (new row)
6. Disable does **not** restore capacity
7. Disable does **not** delete audit rows, capacity events, envelopes, or authorizations

---

## 6. `research.taha_governance_actions` (append-only; NO status column)

```text
research.taha_governance_actions (
  governance_action_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  action_type            TEXT NOT NULL CHECK (action_type IN (
    'pilot_approved',
    'pilot_rejected',
    'provider_enabled_for_proposal',
    'provider_disabled_for_proposal',
    'model_enabled_for_proposal',
    'model_disabled_for_proposal',
    'authorization_activation_approved',
    'credential_status_confirmed',
    'governance_revoked',
    'accounting_discrepancy_acknowledged'
  )),
  proposal_id            UUID NULL REFERENCES research.provider_pilot_proposals(id),
  authorization_id       UUID NULL REFERENCES research.provider_authorization_records(id),
  provider_id            UUID NULL REFERENCES research.providers(id),
  model_id               UUID NULL REFERENCES research.provider_model_candidates(id),
  decision_value         TEXT NOT NULL,
  authority_identifier   TEXT NOT NULL CHECK (authority_identifier = 'Taha'),
  material_fingerprint   CHAR(64) NOT NULL CHECK (material_fingerprint ~ '^[0-9a-f]{64}$'),
  supersedes_action_id   UUID NULL REFERENCES research.taha_governance_actions(governance_action_id),
  issued_at              TIMESTAMPTZ NOT NULL,
  expires_at             TIMESTAMPTZ NULL CHECK (expires_at IS NULL OR issued_at < expires_at),
  recorded_by_role       TEXT NOT NULL CHECK (recorded_by_role IN ('research_governance', 'postgres')),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload                JSONB NOT NULL DEFAULT '{}'::jsonb
)
```

**NO `status` column.** Supersession, revocation, rejection, or cancellation = NEW row with `supersedes_action_id` set.

### 6.1 Type-dependent FK requirements

| action_type | proposal_id | authorization_id | provider_id | model_id | supersedes_action_id |
| --- | --- | --- | --- | --- | --- |
| `credential_status_confirmed` | OPTIONAL | FORBIDDEN | REQUIRED | FORBIDDEN | FORBIDDEN |
| `pilot_approved` | REQUIRED | FORBIDDEN | REQUIRED | REQUIRED | FORBIDDEN |
| `pilot_rejected` | REQUIRED | FORBIDDEN | REQUIRED | REQUIRED | FORBIDDEN |
| `provider_enabled_for_proposal` | REQUIRED | FORBIDDEN | REQUIRED | FORBIDDEN | FORBIDDEN |
| `provider_disabled_for_proposal` | REQUIRED | FORBIDDEN | REQUIRED | FORBIDDEN | FORBIDDEN |
| `model_enabled_for_proposal` | REQUIRED | FORBIDDEN | REQUIRED | REQUIRED | FORBIDDEN |
| `model_disabled_for_proposal` | REQUIRED | FORBIDDEN | REQUIRED | REQUIRED | FORBIDDEN |
| `authorization_activation_approved` | REQUIRED | REQUIRED | REQUIRED | REQUIRED | FORBIDDEN |
| `governance_revoked` | OPTIONAL | FORBIDDEN | FORBIDDEN | FORBIDDEN | REQUIRED |
| `accounting_discrepancy_acknowledged` | REQUIRED | FORBIDDEN | FORBIDDEN | FORBIDDEN | OPTIONAL |

Enforced inside `research.append_governance_action` before insert. Violation → fail closed; no row inserted.

For `pilot_approved` / `pilot_rejected`: `provider_id` MUST equal `research.provider_pilot_proposals.provider_id` and `model_id` MUST equal `research.provider_pilot_proposals.model_candidate_id` for the given `proposal_id`.

### 6.2 Material fingerprint

`material_fingerprint = encode(digest(convert_to(canonical_json, 'UTF8'), 'sha256'), 'hex')` — exactly 64 lowercase hex characters.

Canonical JSON fields (sorted keys; no secrets):

- `pilot_code`, `proposal_id`, `provider_code`, `model_id_provisional`
- `benchmark_case_ids` (ordered), `benchmark_case_codes` (ordered)
- `max_successful_calls`, `max_attempts_per_case`, `max_total_requests`
- `max_total_input_tokens`, `max_total_output_tokens`, `max_authorized_cost_usd`
- `retries_allowed`, `fallback_provider_allowed`, `confidentiality_class`
- `expiry_hours_after_approval`, `authority_identifier`
- `action_type`, `decision_value`

Altered proposal content, provider/model binding, limits, policies, or validity ⇒ different fingerprint ⇒ prior non-superseded approval does not authorize the new material.

### 6.3 Uniqueness and active-action detection

Partial unique index (exact):

```text
CREATE UNIQUE INDEX uq_taha_gov_action_material
  ON research.taha_governance_actions (action_type, proposal_id, material_fingerprint)
  WHERE action_type NOT IN ('governance_revoked', 'accounting_discrepancy_acknowledged');
```

Duplicate insert of same `(action_type, proposal_id, material_fingerprint)` for constrained types → unique violation → fail closed.

**Active (non-superseded) detection:** a row `A` is active iff no later row `R` exists with `R.supersedes_action_id = A.governance_action_id`. Stale: `expires_at IS NOT NULL AND expires_at < now()`. Copied action with same fingerprint while prior active exists → reject. Conflicting fingerprints for same `(proposal_id, action_type)` while both active → reject second. Revocation: insert `governance_revoked` with `supersedes_action_id` pointing at target; never UPDATE the target.

### 6.4 Creation protocol

ONE function:

```text
research.append_governance_action(
  p_action_type text,
  p_proposal_id uuid,
  p_authorization_id uuid,
  p_provider_id uuid,
  p_model_id uuid,
  p_decision_value text,
  p_material_fingerprint char(64),
  p_supersedes_action_id uuid,
  p_issued_at timestamptz,
  p_expires_at timestamptz,
  p_payload jsonb
) RETURNS uuid
```

OWNER `postgres`; SECURITY DEFINER; `SET search_path = pg_catalog`; EXECUTE **only** `research_governance`.

Higher-level governance functions (`confirm_*`, `approve_*`, `enable_*`, `disable_*`, `activate_pilot_authorization`) MUST call `append_governance_action` in the same transaction; they do not INSERT directly.

Privileges on table: `research_app` / `n8n_app` / `research_governance` / `PUBLIC` → **SELECT only**. No INSERT/UPDATE/DELETE for app/n8n/governance. Writes only via DEFINER.

---

## 7. Capacity accounting

### 7.1 Table `research.pilot_capacity_events`

```text
research.pilot_capacity_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pilot_proposal_id UUID NOT NULL REFERENCES research.provider_pilot_proposals(id),
  authorization_id UUID NOT NULL REFERENCES research.provider_authorization_records(id),
  benchmark_case_id UUID NOT NULL REFERENCES research.benchmark_cases(id),
  event_type TEXT NOT NULL CHECK (event_type = 'attempt_consumed'),
  idempotency_key TEXT NOT NULL,
  projected_input_tokens INT NOT NULL CHECK (projected_input_tokens >= 0),
  projected_output_tokens INT NOT NULL CHECK (projected_output_tokens >= 0),
  projected_cost_usd NUMERIC NOT NULL CHECK (projected_cost_usd = 0),
  envelope_id UUID NULL,
  consumption_kind TEXT NOT NULL CHECK (consumption_kind IN ('normal', 'legacy_orphan')),
  legacy_reservation_id UUID NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT pilot_capacity_events_kind_link CHECK (
    (consumption_kind = 'normal' AND envelope_id IS NOT NULL AND legacy_reservation_id IS NULL)
    OR
    (consumption_kind = 'legacy_orphan' AND envelope_id IS NULL AND legacy_reservation_id IS NOT NULL)
  ),
  UNIQUE (pilot_proposal_id, idempotency_key),
  UNIQUE (pilot_proposal_id, benchmark_case_id)
)
```

Single event type: `attempt_consumed` only.

### 7.2 Metric authorities

| Metric | Authoritative source |
| --- | --- |
| Total requests | `COUNT(*)` of `attempt_consumed` for pilot only |
| Attempts per case | Unique `(pilot_proposal_id, benchmark_case_id)` on events |
| Input tokens | `SUM(projected_input_tokens)` of events only |
| Output tokens | `SUM(projected_output_tokens)` of events only |
| Cost | Events require `projected_cost_usd = 0`; any ledger `estimated_cost_usd > 0` for pilot → discrepancy path |
| Successful calls | `COUNT(*)` of `provider_usage_ledger` where `pilot_proposal_id` set AND `success IS TRUE` AND `test_fixture_id IS NULL` |

`provider_usage_ledger.request_count` is reporting-only. Aggregate request enforcement MUST NEVER compute `events + ledger.request_count`.

### 7.3 Insert ordering (no post-insert UPDATE of events)

1. Lock pilot `FOR UPDATE`; lock auth `FOR UPDATE`
2. Idempotency lookup
3. Validate limits using events (+ success from ledger)
4. `envelope_id := gen_random_uuid()`
5. `INSERT research.pilot_capacity_events (…, envelope_id, consumption_kind='normal')`
6. `INSERT research.live_request_envelopes (id := envelope_id, …)` same transaction
7. Commit

No UPDATE of events. BEFORE UPDATE OR DELETE on `pilot_capacity_events` always raises.

### 7.4 Legacy reservations (schema 8 statuses: `reserved` | `finalized` | `released`)

| Legacy state | Treatment |
| --- | --- |
| `reserved`/`finalized` WITH `envelope_id` | Backfill `attempt_consumed` `consumption_kind='normal'` with that `envelope_id` |
| `reserved`/`finalized` WITHOUT `envelope_id` | Backfill `attempt_consumed` `consumption_kind='legacy_orphan'`, `envelope_id NULL`, `legacy_reservation_id` set; permanently consumes capacity; no executable envelope |
| `released` | Copy row to `research.legacy_reservation_archive` (append-only audit); DO NOT create `attempt_consumed` (zero capacity impact); never silently restore beyond that intentional non-count |
| malformed/conflicts (duplicate case, duplicate idempotency, reservation/ledger conflict, unparseable) | Quarantine as `legacy_orphan` consumption + durable discrepancy; block pilot; never restore capacity |

After successful backfill of all non-released rows and archive of released rows: DROP `research.pilot_capacity_reservations`.

### 7.5 `research.legacy_reservation_archive`

```text
research.legacy_reservation_archive (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legacy_reservation_id UUID NOT NULL,
  archived_status TEXT NOT NULL CHECK (archived_status = 'released'),
  archived_row JSONB NOT NULL,
  archived_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

Append-only. SELECT allowed for audit roles per Appendix A. No UPDATE/DELETE for runtime roles.

---

## 8. Discrepancy persistence (chosen architecture)

Two-step, **separate commits**:

1. `research.build_provider_request_envelope` / `research.live_preflight` validate. On accounting conflict: RETURN jsonb fail-closed result including `discrepancy_fingerprint` and `discrepancy_payload`. DO NOT RAISE after any insert. DO NOT insert discrepancy inside that transaction.
2. Caller (`research_app`) in a **NEW** transaction calls `research.record_accounting_discrepancy(p_discrepancy_fingerprint char(64), p_discrepancy_payload jsonb)` — SECURITY DEFINER, OWNER `postgres`, `SET search_path = pg_catalog`, EXECUTE granted to `research_app` **AND** `research_governance`. Inserts into `research.accounting_discrepancies` (append-only) keyed by `discrepancy_fingerprint UNIQUE`. Idempotent duplicate returns existing id.
3. Envelope creation remains denied regardless.
4. If discrepancy recording fails: request still blocked; return `recording_failed`; pilot stays fail-closed via conflict re-detection on next call.

Inserts of discrepancy NEVER share the failed build transaction.

### 8.1 Table `research.accounting_discrepancies`

```text
research.accounting_discrepancies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  discrepancy_fingerprint CHAR(64) NOT NULL UNIQUE CHECK (discrepancy_fingerprint ~ '^[0-9a-f]{64}$'),
  pilot_proposal_id UUID NOT NULL REFERENCES research.provider_pilot_proposals(id),
  discrepancy_payload JSONB NOT NULL,
  recorded_by_role TEXT NOT NULL CHECK (recorded_by_role IN ('research_app', 'research_governance', 'postgres')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

Governance later acknowledges via `accounting_discrepancy_acknowledged` action; acknowledgement does not restore capacity or unblock automatically without a separate explicit remediation migration authorized by Taha.

---

## 9. Envelope creation

### 9.1 Pilot path

`research.build_provider_request_envelope` — SECURITY DEFINER; OWNER `postgres`; `SET search_path = pg_catalog`; EXECUTE `research_app` only; requires authorization `pilot_proposal_id IS NOT NULL`. Direct INSERT on `live_request_envelopes` revoked from app/n8n/PUBLIC/governance.

### 9.2 Round 4 non-pilot path

`research.build_non_pilot_request_envelope` — **EXACT same signature** as `build_provider_request_envelope`:

```text
research.build_non_pilot_request_envelope(
  p_provider_code text,
  p_model_provisional text,
  p_benchmark_case_id uuid,
  p_authorization_id uuid,
  p_role_code text,
  p_confidentiality_class text,
  p_canonical_request jsonb,
  p_claimed_credential_status text DEFAULT NULL
) RETURNS jsonb
```

SECURITY DEFINER; OWNER `postgres`; `SET search_path = pg_catalog`; EXECUTE `research_app` only; requires `pilot_proposal_id IS NULL`; does not write `pilot_capacity_events`; still enforces Round 4 live_preflight gates. Wrong builder for pilot-linked auth fails closed.

---

## 10. Helper isolation

Move all of the following from `research` to `research_test` (Disposition = `MOVED TO research_test`), or DROP from `research` if already absent after move:

| Schema-8 symbol | Disposition |
| --- | --- |
| `research._r3_clone_question(p_code text, p_scenario text)` | MOVED TO research_test |
| `research._r3_new_run(p_code text, p_qid uuid, p_scenario text, p_budget numeric)` | MOVED TO research_test |
| `research._r4_arm_provider(p_code text, p_enable_provider boolean, p_enable_model boolean, p_verify_model boolean, p_free_confirmed boolean, p_cred_present boolean, p_daily_req integer, p_daily_tok integer)` | MOVED TO research_test |
| `research._r4_case_id()` | MOVED TO research_test |
| `research._r4_make_auth(p_provider text, p_model_id uuid, p_case uuid, p_max_req integer, p_max_tok integer, p_max_cost numeric, p_expires timestamptz)` | MOVED TO research_test |
| `research._r4_reset_defaults()` | MOVED TO research_test |
| `research._r5a_assert_final_pilot_state()` | MOVED TO research_test |
| `research._r5a_final_arm_gates()` | MOVED TO research_test |
| `research._r5a_final_assert_state()` | MOVED TO research_test |
| `research._r5a_final_reset_defaults()` | MOVED TO research_test |
| `research._r5a_insert_fixture_auth(p_fixture text, p_pilot uuid, p_case uuid, p_provider uuid, p_model uuid)` | MOVED TO research_test |
| `research._r5a_repair_reset_defaults()` | MOVED TO research_test |
| `research.cleanup_test_fixture(p_fixture_id text)` | MOVED TO research_test |
| `research.record_pilot_usage_for_tests(p_authorization_id uuid, p_input_tokens integer, p_output_tokens integer, p_success boolean, p_fixture_id text, p_is_retry boolean)` | MOVED TO research_test |

`research_app` / `n8n_app` / `research_governance` / `PUBLIC`: USAGE on `research_test` = NONE; EXECUTE on moved helpers = NONE. After move, symbols live as `research_test.<same_name>` with identical argument signatures, OWNER `postgres`, EXECUTE granted only to `research_test`. `research_test` has NO USAGE on schema `research`; moved helpers that must read/write `research` tables are SECURITY DEFINER with `SET search_path = pg_catalog` and fully qualified `research.*` references. Remove `allow_pilot_activation` GUC paths from triggers entirely.

---

## 11. Migration state machine (schema 8 → 9)

Schema version advances to **9 ONLY after step 20 assertions**. Partial cutover leaves runtime blocked. Every step is rerun-idempotent. No application runtime during cutover. Failure after privilege revocation must not re-grant broad access. Failure after legacy backfill must not double-consume. Failure after function replacement must not expose old and new builders simultaneously.

| Step | Precondition | Object affected | Postcondition | Rerun behavior | Failure behavior | Recovery | Catalog assertion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Connected as `postgres`; exclusive advisory lock free | Session advisory lock `pg_advisory_lock(hashtext('srl_schema9_cutover'))` | Lock held for migration session | Re-acquire same lock; no-op if held by this session | Abort; version stays 8 | Release lock; retry from step 1 | `pg_locks` shows advisory lock for this backend |
| 2 | Lock held; `research.schema_version` max = 8 | Catalog inventory vs Appendix A schema-8 baseline | Expected tables/views/functions present; unexpected objects listed | Re-verify; continue if still match | Abort; no DDL | Fix inventory mismatch manually; restart | `SELECT max(version) FROM research.schema_version` = 8 |
| 3 | Step 2 passed | Roles `research_governance`, `research_test`; schemas | Roles exist with LOGIN; governance NOINHERIT; membership matrix empty between app/n8n/gov; `research_test` schema owned by `research_test` | `CREATE ROLE IF NOT EXISTS` / attribute ALTER idempotent | Abort; no privilege cutover | Drop incomplete role only if unused; retry | `rolinherit=false` for governance; no membership edges APP↔GOV |
| 4 | Step 3 passed | Schema `research` CREATE privilege | CREATE revoked from PUBLIC, research_app, n8n_app, research_governance, research_test | Re-REVOKE idempotent | Abort; leave CREATE revoked (fail closed) | Keep revoked; fix cause; continue from 4 | `has_schema_privilege(role,'research','CREATE')` = false for those roles |
| 5 | Step 4 passed | PUBLIC EXECUTE; default privileges | PUBLIC EXECUTE revoked on all research functions; `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research REVOKE ALL ON TABLES/FUNCTIONS/SEQUENCES FROM PUBLIC, research_app, n8n_app, research_governance` | Re-REVOKE / re-ALTER DEFAULT idempotent | Abort; defaults remain revoked | Do not re-grant; continue | Zero PUBLIC EXECUTE on research functions; default ACL empty for listed roles |
| 6 | Step 5 passed | `taha_governance_actions`, `accounting_discrepancies` | Tables exist with exact constraints; append-only triggers installed | `CREATE TABLE IF NOT EXISTS` + constraint guards | Abort; tables may exist empty | Drop only if empty and unreferenced; recreate | Constraints/indexes match §6 and §8.1 |
| 7 | Step 6 passed | `pilot_capacity_events`, `legacy_reservation_archive` | Tables exist with exact CHECKs/UNIQUEs | IF NOT EXISTS + assert constraints | Abort | Same as step 6 | Event schema matches §7 |
| 8 | Step 7 passed; reservations table still present or already backfilled marker | `pilot_capacity_reservations` rows | Every reserved/finalized backfilled; released archived; malformed quarantined | Skip rows already represented by events/archive via `legacy_reservation_id` / envelope_id match | Abort mid-backfill; events unique constraints prevent double-consume on rerun | Resume; insert only missing | Count(events from legacy)+count(archive) reconciles to prior reservation count |
| 9 | Step 8 passed | Ledger vs events | Conflicts produce discrepancy rows; affected pilots blocked | Idempotent fingerprint inserts | Abort; pilots remain blocked if conflict recorded | Resume discrepancy inserts | No silent capacity restore |
| 10 | Step 9 passed | New governance/builder function shells | `append_governance_action`, enable/disable/confirm/approve, `record_accounting_discrepancy`, `build_non_pilot_request_envelope` exist | CREATE OR REPLACE idempotent | Abort; old builders may still exist until step 11 | Continue to step 11 which replaces unsafely | Functions exist with OWNER postgres |
| 11 | Step 10 passed | All SECURITY DEFINER bodies | All elevated functions use `search_path=pg_catalog` and fully qualified refs; GUC activation removed | CREATE OR REPLACE | Abort; if replace partial, REVOKE EXECUTE on both old and new from APP until fixed | Revoke APP EXECUTE on builders; fix; rerun 11 | `proconfig` search_path = `pg_catalog`; no `allow_pilot_activation` |
| 12 | Step 11 passed | Table ACLs on gated/lifecycle tables | Direct mutations revoked per Appendix A; INSERT/UPDATE only where listed | Re-REVOKE/GRANT exact | Abort; leave gated writes revoked | Do not broaden; resume grants | APP cannot INSERT envelopes/events/governance |
| 13 | Step 12 passed | `_r3*` `_r4*` `_r5a*` `cleanup_test_fixture` `record_pilot_usage_for_tests` | Absent from `research` or non-executable; present under `research_test` only | DROP IF EXISTS from research after create in research_test | Abort; ensure APP EXECUTE = none on any residual | Drop residual from research | Inventory query empty in research for those names |
| 14 | Step 13 passed | Round 4 caller docs/SQL wrappers in-repo | Non-pilot path documented to call `build_non_pilot_request_envelope`; no dual-builder EXECUTE for obsolete path | Idempotent doc/SQL guard | Abort migration SQL if obsolete research wrapper still EXECUTABLE by APP | Revoke obsolete; continue | APP EXECUTE on pilot builder and non-pilot builder only as allowlisted |
| 15 | Step 14 passed | Exact allowlist grants | Appendix A grants applied exactly | Re-apply GRANT/REVOKE matrix | Abort; keep prior revocations | Apply remaining grants without elevating gated writes | ACL matrix equals Appendix A |
| 16 | Step 15 passed | Privilege/ownership assertions | All Appendix A owner=`postgres`; EXECUTE matrix matches | Re-run asserts | Abort; version stays 8 | Fix ACL; rerun 16 | Assertion query returns zero drift rows |
| 17 | Step 16 passed | `providers` / `provider_model_candidates` for gemini | Gemini provider disabled; `gemini-2.5-flash` disabled | Re-assert | Abort | Leave disabled; fix | `enabled=false` for gemini provider and model |
| 18 | Step 17 passed | `provider_credential_status` | Credential status unchanged from pre-migration snapshot (expect `missing` for gemini) | Re-assert | Abort | Do not create credentials | Snapshot match |
| 19 | Step 18 passed | Proposals/authorizations | Zero new approvals/activations caused by migration; production pilot auths remain proposed | Re-assert | Abort | Do not approve/activate | 3 proposed production pilot auths; 0 active |
| 20 | Steps 1–19 passed | `research.schema_version` | Insert version 9 note; release advisory lock | ON CONFLICT DO NOTHING only if asserts still pass | If assert fails do not insert 9 | Fix; rerun from failed step; only then insert 9 | `max(version)=9` and all asserts green |

Partial privilege cutover: runtime execution of builders and governance remains **blocked** (EXECUTE revoked or functions absent) until step 16 passes.

---

## 12. Default privileges (future objects)

```text
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research
  REVOKE ALL ON TABLES FROM PUBLIC, research_app, n8n_app, research_governance;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research
  REVOKE ALL ON FUNCTIONS FROM PUBLIC, research_app, n8n_app, research_governance;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research
  REVOKE ALL ON SEQUENCES FROM PUBLIC, research_app, n8n_app, research_governance;
```

Future objects = NONE until an explicit allowlist migration updates Appendix A and applies grants.

---

## 13. Design decisions (locked)

| Topic | Decision |
| --- | --- |
| Schema CREATE | Revoked from PUBLIC and all runtime roles; only postgres creates in `research` |
| SECURITY DEFINER search_path | `pg_catalog` only; all refs fully qualified `research.*` / `pg_catalog.*` |
| Governance-action creation | `research.append_governance_action` DEFINER; EXECUTE research_governance only |
| Governance mutability | Append-only; no status column; supersession via new row |
| Discrepancy persistence | Two-step separate commits; `record_accounting_discrepancy` EXECUTE app+gov |
| Null-envelope legacy | `legacy_orphan` attempt_consumed; permanently consumes; no executable envelope |
| Released legacy | Archive only; zero capacity impact |
| Disablement on active auths | Remain historical; become non-executable |
| Disablement on prepared envelopes | Idempotent JSON retrieval allowed; `execution_denied=true`; executable false |
| Total request authority | `COUNT(attempt_consumed)` only |
| Schema-version advancement | Version 9 only after step 20 assertions |

---

## Appendix A — Machine-exact object allowlist

**Rule:** Any `research` object not listed is denied (`NONE`) to `research_app`, `n8n_app`, `research_governance`, and `PUBLIC` unless a row below grants otherwise.
**Owner:** `postgres` for every live `research` object below unless Disposition says MOVED.

Privilege cells use exact tokens: `NONE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `EXECUTE`, `USAGE`, `MOVED TO research_test`, `DROP`.

### A.1 Tables

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
| research.pilot_capacity_reservations | table | postgres | NONE | NONE | NONE | NONE | NONE | DROP after backfill |
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
| research.accounting_discrepancies | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | NEW schema-9; INSERT via function only |
| research.legacy_reservation_archive | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | NEW schema-9 |

DELETE = NONE for every table for every runtime role.

### A.2 Views

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

None exist in schema `research` at schema version 8.

Any future sequence: PUBLIC / research_app / n8n_app / research_governance = NONE until an allowlist migration explicitly grants USAGE/SELECT and updates this appendix.

### A.4 Functions

Columns: PUBLIC / research_app / n8n_app / research_governance EXECUTE (`Y` or `N`). research_test EXECUTE = `N` for all `research.*` functions.

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
| research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text) | function DEFINER | postgres | N | N | N | Y | KEEP; redefine per §4 |
| research.append_governance_action(p_action_type text, p_proposal_id uuid, p_authorization_id uuid, p_provider_id uuid, p_model_id uuid, p_decision_value text, p_material_fingerprint char(64), p_supersedes_action_id uuid, p_issued_at timestamptz, p_expires_at timestamptz, p_payload jsonb) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.approve_pilot_proposal(p_pilot_code text) | function DEFINER | postgres | N | N | N | Y | NEW |
| research.build_decision_card(p_run_id uuid) | function | postgres | N | Y | N | N | KEEP |
| research.build_non_pilot_request_envelope(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_canonical_request jsonb, p_claimed_credential_status text) | function DEFINER | postgres | N | Y | N | N | NEW |
| research.build_provider_request_envelope(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_canonical_request jsonb, p_claimed_credential_status text) | function DEFINER | postgres | N | Y | N | N | KEEP; redefine per §4 |
| research.cancel_research_run(p_run_id uuid, p_reason text) | function | postgres | N | Y | N | N | KEEP |
| research.cleanup_test_fixture(p_fixture_id text) | function | postgres | N | N | N | N | MOVED TO research_test |
| research.compute_priority_v1(constitutional_impact numeric, measured_performance_gap numeric, safety_impact numeric, expected_value numeric, urgency numeric, evidence_availability numeric, implementation_cost numeric, duplication_penalty numeric) | function | postgres | N | Y | N | N | KEEP |
| research.confirm_provider_credential_status(p_provider_code text, p_n8n_credential_label text, p_note text) | function DEFINER | postgres | N | N | N | Y | NEW |
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
| research.pilot_capacity_snapshot(p_pilot_id uuid) | function | postgres | N | Y | N | Y | KEEP |
| research.pilot_case_attempt_count(p_pilot_id uuid, p_benchmark_case_id uuid) | function | postgres | N | Y | N | Y | KEEP |
| research.proposal_has_evidence(p_evidence_ids uuid[]) | function | postgres | N | Y | N | N | KEEP |
| research.record_accounting_discrepancy(p_discrepancy_fingerprint char(64), p_discrepancy_payload jsonb) | function DEFINER | postgres | N | Y | N | Y | NEW |
| research.record_authorization_spend(p_authorization_id uuid, p_requests integer, p_tokens integer, p_cost numeric, p_note text) | function DEFINER | postgres | N | Y | N | N | KEEP; rejects pilot-linked |
| research.record_pilot_usage_for_tests(p_authorization_id uuid, p_input_tokens integer, p_output_tokens integer, p_success boolean, p_fixture_id text, p_is_retry boolean) | function | postgres | N | N | N | N | MOVED TO research_test |
| research.run_stage(p_run_id uuid, p_stage text, p_scenario_hint text) | function | postgres | N | Y | N | N | KEEP |
| research.sha256_hex(p_text text) | function | postgres | N | Y | N | N | KEEP |
| research.trg_authorization_validity_guard() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_block_evidence_delete_after_decision() | trigger function | postgres | N | N | N | N | KEEP |
| research.trg_envelope_immutability() | trigger function | postgres | N | N | N | N | KEEP |
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

### A.5 Schema privileges summary

| Object | PUBLIC | research_app | n8n_app | research_governance | research_test |
| --- | --- | --- | --- | --- | --- |
| SCHEMA research | NONE | USAGE | USAGE | USAGE | NONE |
| SCHEMA research CREATE | NONE | NONE | NONE | NONE | NONE |
| SCHEMA research_test | NONE | NONE | NONE | NONE | USAGE, CREATE |

---

## Appendix B — Open risks (accepted)

- Owner/`postgres` break-glass UPDATE still possible; mitigated by immutability triggers + ops procedure.
- Theft of `research_governance` login equals full governance power; keep local-only.
- Round 4 adapters must call `build_non_pilot_request_envelope` after schema 9 implementation.
- Human operator error during migration windows; mitigated by advisory lock and version-8 hold until step 20.
