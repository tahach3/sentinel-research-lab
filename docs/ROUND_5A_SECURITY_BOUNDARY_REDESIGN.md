# Round 5A — Security Boundary Redesign (Revision 5)

**Status:** Design only. Not implemented.
**Baseline HEAD:** `ed8d8931e40388a9f26b75d3146dd646e68072c9` / schema version 8 runtime
**Supersedes:** Revision 4 content of this file at that commit
**Scope:** Machine-exact privilege, linear governance chains, trusted crypto, activation invariants, capacity, typed discrepancy identity, enforceable cutover freeze, legacy restart branches, and schema 8→9 migration.
**Non-goals:** Implementing SQL in this round; storing API keys; Round 5B live HTTP; Equitify/SENTINEL changes; advancing schema version; changing live roles/grants.

Resolves Codex Revision-4 findings: partial-cutover runtime freeze; proposal-scoped credential confirmation; typed discrepancy recorder; numeric canonicalization; post-rename State A/B/C; exact trigger object names; adversarial test expansion.

---

## 1. Threat model

Must eliminate at the **privilege and ownership** layer:

1. Session-GUC activation
2. Mutable/deletable capacity evidence
3. Application-callable approval/arm helpers
4. Direct envelope insertion
5. Schema-CREATE shadow objects against SECURITY DEFINER resolution
6. Unqualified name resolution via `search_path` / `pg_temp` / `public`
7. Unqualified cryptographic or UUID functions

Adversary: `research_app` / `n8n_app` with any SQL allowed by their grants, including `set_config`, `SET ROLE` attempts, `CREATE` attempts, and `PUBLIC` defaults.

---

## 2. Roles and ownership

| Role | Attributes | Purpose |
| --- | --- | --- |
| `postgres` | Login; migration/database owner | Owns all `research` and `research_crypto` objects; sole CREATE on those schemas; sole granter of `research_governance` membership |
| `research_governance` | LOGIN; NOINHERIT; NOT member of `research_app` or `n8n_app` | Taha-controlled governance session only |
| `research_app` | LOGIN; MUST NOT be member of `research_governance`; MUST NOT `SET ROLE research_governance` | Application / automation runtime |
| `n8n_app` | LOGIN; same membership prohibitions as `research_app` | n8n runtime |
| `research_test` | LOGIN; USAGE+CREATE only on schema `research_test`; NO CREATE on `research` or `research_crypto` | Non-prod test helpers only |
| Taha | Human | Sole approval authority; operates as `research_governance` after intentional local login |

Object owner for all security-sensitive tables, views, triggers, elevated functions, and crypto schema objects: **`postgres`**. Runtime roles must not own objects in `research` or `research_crypto`. Runtime roles must not `ALTER` functions, triggers, tables, sequences, views, schemas, extensions, or ownership.

---

## 3. Schema privileges and shadow-object prevention

Exact schema privileges after cutover:

```text
REVOKE CREATE ON SCHEMA research FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
GRANT USAGE ON SCHEMA research TO research_app, n8n_app, research_governance;
```

Only `postgres` may CREATE or REPLACE objects in schema `research`.

`research_test` schema (created in migration if absent):

```text
CREATE SCHEMA IF NOT EXISTS research_test AUTHORIZATION research_test;
REVOKE ALL ON SCHEMA research_test FROM PUBLIC, research_app, n8n_app, research_governance;
GRANT USAGE, CREATE ON SCHEMA research_test TO research_test;
```

Catalog assertion: zero rows where `research_app`, `n8n_app`, `research_governance`, `research_test`, or `PUBLIC` hold `CREATE` on schema `research` or `research_crypto`.

---

## 4. SECURITY DEFINER contract (normative)

Every elevated function MUST satisfy all of:

1. OWNER = `postgres`
2. `SECURITY DEFINER`
3. `SET search_path = pg_catalog` (exactly; no `research`; no `pg_temp`; no `public`; no `research_crypto` on path)
4. Every object reference fully qualified as `research.<name>`, `research_crypto.<name>`, or `pg_catalog.<name>`
5. NEVER unqualified identifiers for tables, views, sequences, functions, types, or operators
6. NEVER call unqualified `digest`, `gen_random_uuid`, or other pgcrypto symbols
7. Cryptographic calls use only `research_crypto.digest(...)` and `research_crypto.gen_random_uuid()` (or `research.sha256_hex` which itself calls only FQ `research_crypto.*`)
8. `REVOKE ALL ON FUNCTION … FROM PUBLIC;`
9. `EXECUTE` granted to exactly the role enumerated in Appendix A
10. Reject caller-controlled role, authority, or schema values; `authority_identifier` is constant `'Taha'` inside DEFINER bodies

Configured `search_path` alone is insufficient without fully qualified references.

---

## 4A. Trusted cryptographic schema `research_crypto`

```text
CREATE SCHEMA research_crypto AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA research_crypto FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
-- No USAGE grant to runtime roles. Only postgres (and DEFINER bodies running as postgres) resolve objects here.
```

Migration moves the installed `pgcrypto` extension into schema `research_crypto`:

```text
ALTER EXTENSION pgcrypto SET SCHEMA research_crypto;
```

Rules:

* Owner of schema and extension-owned functions: `postgres`
* `CREATE` revoked from PUBLIC and all runtime roles on `research_crypto`
* Runtime roles receive no USAGE, no EXECUTE, no mutation rights on `research_crypto`
* Elevated functions MUST call `research_crypto.digest(...)` and `research_crypto.gen_random_uuid()` with full qualification
* `research.sha256_hex(p_text text)` MUST be redefined to:

```text
RETURN encode(research_crypto.digest(convert_to(p_text, 'UTF8'), 'sha256'), 'hex');
```

* Migration assertions verify: extension schema = `research_crypto`; `digest` and `gen_random_uuid` reside in `research_crypto`; OWNER = `postgres`; zero unqualified crypto refs in elevated function bodies
* Failure to move or verify blocks schema-9 completion (version stays 8)

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

| Step | Function | Governance action_type | Required decision_value |
| --- | --- | --- | --- |
| 1 | `research.confirm_provider_credential_status(p_pilot_proposal_id uuid, p_provider_code text, p_n8n_credential_label text, p_governance_action_id uuid, p_note text)` | `credential_status_confirmed` (must already be terminal for scope) | `confirmed` |
| 2 | `research.approve_pilot_proposal(p_pilot_code text)` | `pilot_approved` | `approved` |
| 3 | `research.enable_provider_for_pilot(p_pilot_code text, p_provider_code text)` | `provider_enabled_for_proposal` | `enabled` |
| 4 | `research.enable_model_for_pilot(p_pilot_code text, p_provider_code text, p_model_id_provisional text)` | `model_enabled_for_proposal` | `enabled` |
| 5 | `research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text)` | `authorization_activation_approved` | `approved` |
| 6 | `research.build_provider_request_envelope` as `research_app` (full signature Appendix A.4) | none | n/a |

### 5.1.1 Proposal-scoped credential confirmation

Exact production signature:

```text
research.confirm_provider_credential_status(
  p_pilot_proposal_id uuid,
  p_provider_code text,
  p_n8n_credential_label text,
  p_governance_action_id uuid,
  p_note text
) RETURNS research.provider_credential_status
```

OWNER `postgres`; SECURITY DEFINER; `SET search_path = pg_catalog`; EXECUTE **only** `research_governance` after cutover complete (revoked during freeze).

Normative behavior:

1. `p_pilot_proposal_id` is mandatory; proposal must exist.
2. Proposal `provider_id` MUST match `providers.code = p_provider_code`.
3. Caller first appends `credential_status_confirmed` via `append_governance_action` for scope `(proposal_id, provider_id)`; then passes that row’s `governance_action_id`.
4. Function requires that action to be: `action_type = credential_status_confirmed`; `decision_value = confirmed`; terminal in credential scope; unexpired; fingerprint-valid against live proposal material; `authority_identifier = Taha`; scope identifiers exact match.
5. Credential label must match the proposal’s expected provider configuration (non-secret label only).
6. Function records only non-secret credential status metadata (`present` / label / note). **No** key or credential payload accepted.
7. No provider-only lookup may select among proposals; ambiguous multi-proposal selection is impossible because proposal ID is required.
8. Each `(proposal_id, provider_id)` has its own governance chain; confirmation for proposal A cannot enable or activate proposal B.
9. Wrong binding, wrong/expired/superseded action, or missing proposal → fail closed; no mutation.

Enablement, activation, and preflight MUST require the terminal credential governance action for the **same** `proposal_id`, not merely provider-level `credential_status = present`.

Each enablement step fails closed with no table mutation when the required terminal governance state for that scope is missing, expired, fingerprint-mismatched, or disabled/revoked. Provider/model enablement is **proposal-scoped**. Enablement for one proposal does not authorize unrelated pilots.

### 5.2 Disablement

Functions:

* `research.disable_provider_for_pilot(p_pilot_code text, p_provider_code text)` → appends `provider_disabled_for_proposal` with `decision_value='disabled'`, parent = current terminal **enable**
* `research.disable_model_for_pilot(p_pilot_code text, p_provider_code text, p_model_id_provisional text)` → appends `model_disabled_for_proposal` with `decision_value='disabled'`, parent = current terminal **enable**

Exact effects:

1. Immediately blocks new `live_preflight` success and new envelope creation for that proposal binding
2. Active authorization rows remain immutable historical records but become **non-executable**
3. Consumed capacity remains consumed; disable does not restore capacity
4. Disabling does not extend authorization expiry; `activated_at` / `expires_at` remain immutable
5. Prepared envelopes become permanently non-executable; idempotent lookup may return stored metadata only with `execution_denied = true`
6. Re-enable requires a **new** matching enable governance action whose parent is the current terminal **disable**
7. Re-enable does **not** reactivate expired authorizations; a new authorization row is required after expiry
8. Disable does **not** delete audit rows, capacity events, envelopes, or authorizations
9. Historical enable actions remain immutable; disable does not mutate or remove them

---

## 6. `research.taha_governance_actions` — linear append-only chains

```text
research.taha_governance_actions (
  governance_action_id   UUID PRIMARY KEY DEFAULT research_crypto.gen_random_uuid(),
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
  payload                JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT taha_gov_decision_value_map CHECK (
    (action_type = 'pilot_approved' AND decision_value = 'approved')
    OR (action_type = 'pilot_rejected' AND decision_value = 'rejected')
    OR (action_type = 'provider_enabled_for_proposal' AND decision_value = 'enabled')
    OR (action_type = 'provider_disabled_for_proposal' AND decision_value = 'disabled')
    OR (action_type = 'model_enabled_for_proposal' AND decision_value = 'enabled')
    OR (action_type = 'model_disabled_for_proposal' AND decision_value = 'disabled')
    OR (action_type = 'authorization_activation_approved' AND decision_value = 'approved')
    OR (action_type = 'credential_status_confirmed' AND decision_value = 'confirmed')
    OR (action_type = 'governance_revoked' AND decision_value = 'revoked')
    OR (action_type = 'accounting_discrepancy_acknowledged' AND decision_value = 'acknowledged')
  )
)
```

**NO `status` column.** Existing actions are never UPDATE'd or DELETE'd.

### 6.1 Governance scopes

| Scope name | Scope key | Legal action types in chain |
| --- | --- | --- |
| pilot decision | `(proposal_id)` | `pilot_approved`, `pilot_rejected`, `governance_revoked` (revoking a pilot decision) |
| provider enablement | `(proposal_id, provider_id)` | `provider_enabled_for_proposal`, `provider_disabled_for_proposal` |
| model enablement | `(proposal_id, provider_id, model_id)` | `model_enabled_for_proposal`, `model_disabled_for_proposal` |
| authorization activation approval | `(proposal_id, authorization_id)` | `authorization_activation_approved`, `governance_revoked` (revoking that approval) |
| credential confirmation | `(proposal_id, provider_id)` | `credential_status_confirmed`, `governance_revoked` (revoking confirmation) |
| discrepancy acknowledgement | `(proposal_id)` + payload linkage | `accounting_discrepancy_acknowledged` |

`supersedes_action_id` is the **immediate parent** action in the **same scope**.

### 6.2 Linear chain rules (normative)

1. The first action in a scope has `supersedes_action_id IS NULL`.
2. Every later state-changing action MUST reference the current terminal action as parent.
3. A referenced parent may have at most one child.
4. Branching governance chains are forbidden.
5. Cross-scope supersession is forbidden.
6. A child MUST match all scope identifiers of its parent.
7. Append operations lock the scope (`SELECT … FOR UPDATE` on proposal/provider/model/auth as applicable) before determining the terminal action.
8. Duplicate or concurrent child creation fails deterministically (unique violation or fail-closed raise).
9. Existing actions are never updated or deleted.

Exact one-child-per-parent index:

```text
CREATE UNIQUE INDEX uq_taha_gov_one_child_per_parent
  ON research.taha_governance_actions (supersedes_action_id)
  WHERE supersedes_action_id IS NOT NULL;
```

### 6.3 Provider / model state transitions

Provider chain (only legal transitions):

```text
no action
→ provider_enabled_for_proposal   (supersedes_action_id IS NULL)
→ provider_disabled_for_proposal  (parent = terminal enable)
→ provider_enabled_for_proposal   (parent = terminal disable)
→ provider_disabled_for_proposal  (parent = terminal enable)
→ …
```

Rules:

* Initial enable has no parent
* Disable MUST supersede the current terminal enable (`supersedes_action_id` REQUIRED)
* Re-enable MUST supersede the current terminal disable (`supersedes_action_id` REQUIRED)
* Enable cannot supersede enable
* Disable cannot supersede disable
* Historical enable rows remain immutable

Model chain: identical alternating pattern for `model_enabled_for_proposal` ↔ `model_disabled_for_proposal` with exact `(proposal_id, provider_id, model_id)` binding.

### 6.4 Type-dependent FK and parent requirements

| action_type | proposal_id | authorization_id | provider_id | model_id | supersedes_action_id |
| --- | --- | --- | --- | --- | --- |
| `credential_status_confirmed` | REQUIRED | FORBIDDEN | REQUIRED | FORBIDDEN | NULL if first in scope; else REQUIRED → prior terminal in credential scope |
| `pilot_approved` | REQUIRED | FORBIDDEN | REQUIRED | REQUIRED | NULL if first; else REQUIRED → prior terminal in pilot scope |
| `pilot_rejected` | REQUIRED | FORBIDDEN | REQUIRED | REQUIRED | NULL if first; else REQUIRED → prior terminal in pilot scope |
| `provider_enabled_for_proposal` | REQUIRED | FORBIDDEN | REQUIRED | FORBIDDEN | NULL if first enable; REQUIRED → terminal disable on re-enable |
| `provider_disabled_for_proposal` | REQUIRED | FORBIDDEN | REQUIRED | FORBIDDEN | REQUIRED → terminal enable |
| `model_enabled_for_proposal` | REQUIRED | FORBIDDEN | REQUIRED | REQUIRED | NULL if first enable; REQUIRED → terminal disable on re-enable |
| `model_disabled_for_proposal` | REQUIRED | FORBIDDEN | REQUIRED | REQUIRED | REQUIRED → terminal enable |
| `authorization_activation_approved` | REQUIRED | REQUIRED | REQUIRED | REQUIRED | NULL if first; else REQUIRED → prior terminal in auth-approval scope |
| `governance_revoked` | scope-dependent | FORBIDDEN unless auth-scope revoke | FORBIDDEN unless provider/model scope | FORBIDDEN unless model scope | REQUIRED → target terminal being revoked |
| `accounting_discrepancy_acknowledged` | REQUIRED | FORBIDDEN | FORBIDDEN | FORBIDDEN | OPTIONAL → prior ack in same proposal discrepancy thread |

For `pilot_approved` / `pilot_rejected`: `provider_id` MUST equal `provider_pilot_proposals.provider_id` and `model_id` MUST equal `model_candidate_id`.

Transition legality (enable↔disable, parent type match, scope id match) is enforced inside `research.append_governance_action` before insert. Violation → fail closed; no row inserted.

### 6.5 Closed decision_value mapping

| `action_type` | Required `decision_value` |
| --- | --- |
| `pilot_approved` | `approved` |
| `pilot_rejected` | `rejected` |
| `provider_enabled_for_proposal` | `enabled` |
| `provider_disabled_for_proposal` | `disabled` |
| `model_enabled_for_proposal` | `enabled` |
| `model_disabled_for_proposal` | `disabled` |
| `authorization_activation_approved` | `approved` |
| `credential_status_confirmed` | `confirmed` |
| `governance_revoked` | `revoked` |
| `accounting_discrepancy_acknowledged` | `acknowledged` |

No other decision string is valid. Enforced by `taha_gov_decision_value_map` CHECK.

### 6.6 Material fingerprint

```text
material_fingerprint = research.sha256_hex(canonical_json)
```

where `research.sha256_hex` uses only `research_crypto.digest`. Result is exactly 64 lowercase hex characters.

Canonical JSON fields (sorted keys; no secrets):

* `pilot_code`, `proposal_id`, `provider_code`, `model_id_provisional`
* `benchmark_case_ids` (ordered), `benchmark_case_codes` (ordered)
* `max_successful_calls`, `max_attempts_per_case`, `max_total_requests`
* `max_total_input_tokens`, `max_total_output_tokens`, `max_authorized_cost_usd`
* `retries_allowed`, `fallback_provider_allowed`, `confidentiality_class`
* `expiry_hours_after_approval`, `authority_identifier`
* `action_type`, `decision_value`

Altered proposal content, provider/model binding, limits, policies, or validity ⇒ different fingerprint ⇒ prior terminal enable/approval does not authorize the new material.

### 6.7 Terminal-state detection (active vs disabled)

The **terminal action** for a scope is the unique action `T` in that scope for which no row `R` exists with `R.supersedes_action_id = T.governance_action_id`.

Provider/model **enabled** (executable path may proceed for that binding) only when terminal `T`:

* `action_type` is the matching enable action;
* `expires_at IS NULL OR expires_at >= now()`;
* has not been superseded (is terminal);
* matches exact proposal, provider, and model (model scope);
* `material_fingerprint` matches live material;
* `authority_identifier = 'Taha'`;
* `decision_value` matches the closed map.

Provider/model **disabled** when terminal `T` is the matching disable action.

**Do not** infer active/enabled state from the historical existence of any enable row.

Pilot approved / credential confirmed / activation approved similarly use terminal-action-only detection within their scopes.

### 6.8 Duplicate protection (enable uniqueness)

Remove any uniqueness rule that permanently prevents a valid enable after disablement.

Exact duplicate-protection unique index:

```text
CREATE UNIQUE INDEX uq_taha_gov_transition_identity
  ON research.taha_governance_actions (
    action_type,
    proposal_id,
    COALESCE(provider_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(model_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(authorization_id, '00000000-0000-0000-0000-000000000000'::uuid),
    material_fingerprint,
    COALESCE(supersedes_action_id, '00000000-0000-0000-0000-000000000000'::uuid)
  )
  WHERE action_type NOT IN ('governance_revoked', 'accounting_discrepancy_acknowledged');
```

* Duplicate of the same state transition and parent → unique violation → fail closed
* Valid re-enable after disable succeeds because `supersedes_action_id` differs (new parent = terminal disable)

### 6.9 Creation protocol

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

Higher-level governance functions MUST call `append_governance_action` in the same transaction; they do not INSERT directly.

Privileges on table: `research_app` / `n8n_app` / `research_governance` / `PUBLIC` → **SELECT only**. No INSERT/UPDATE/DELETE. Writes only via DEFINER. Append-only trigger `reject_taha_governance_action_mutation` rejects UPDATE/DELETE even for owner-issued DML outside the controlled path policy (see §14).

---

## 7. Capacity accounting

### 7.1 Table `research.pilot_capacity_events`

```text
research.pilot_capacity_events (
  id UUID PRIMARY KEY DEFAULT research_crypto.gen_random_uuid(),
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
4. `envelope_id := research_crypto.gen_random_uuid()`
5. `INSERT research.pilot_capacity_events (…, envelope_id, consumption_kind='normal')`
6. `INSERT research.live_request_envelopes (id := envelope_id, …)` same transaction
7. Commit

No UPDATE of events. Trigger `reject_pilot_capacity_event_mutation` rejects UPDATE and DELETE.

### 7.4 Legacy reservations (schema 8 statuses: `reserved` | `finalized` | `released`)

| Legacy state | Treatment |
| --- | --- |
| `reserved`/`finalized` WITH `envelope_id` | Backfill `attempt_consumed` `consumption_kind='normal'` with that `envelope_id` |
| `reserved`/`finalized` WITHOUT `envelope_id` | Backfill `attempt_consumed` `consumption_kind='legacy_orphan'`, `envelope_id NULL`, `legacy_reservation_id` set; permanently consumes; no executable envelope |
| `released` | Copy to `research.legacy_reservation_archive`; DO NOT create `attempt_consumed`; never reinterpret as active attempts |
| malformed/conflicts | Quarantine as `legacy_orphan` + durable discrepancy; block pilot; never restore capacity |

**Do not DROP** the legacy reservation table in schema 9. After backfill and dependency rewrite:

```text
ALTER TABLE research.pilot_capacity_reservations
  RENAME TO pilot_capacity_reservations_legacy;
```

Then: revoke all privileges from runtime and governance roles; owner-only SELECT for audit; attach `reject_legacy_capacity_table_mutation` rejecting INSERT/UPDATE/DELETE; mark deprecated in inventory. No production function may reference it after cutover. Migration fails before version advancement if any production dependency still references the legacy name or renamed table.

### 7.5 `research.legacy_reservation_archive`

```text
research.legacy_reservation_archive (
  id UUID PRIMARY KEY DEFAULT research_crypto.gen_random_uuid(),
  legacy_reservation_id UUID NOT NULL,
  archived_status TEXT NOT NULL CHECK (archived_status = 'released'),
  archived_row JSONB NOT NULL,
  archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (legacy_reservation_id)
)
```

Append-only via `reject_legacy_reservation_archive_mutation`. Reruns use `ON CONFLICT (legacy_reservation_id) DO NOTHING` (or equivalent) and cannot duplicate archive rows. Released rows never consume schema-9 capacity; immutable after archival.

---

## 8. Discrepancy persistence

### 8.1 Canonical payload and numeric rules

One exact closed JSONB object. Every key always present. Unavailable values use JSON `null` only. Arbitrary caller fields forbidden. Timestamps excluded from fingerprint. UUIDs/IDs: lowercase hex textual form without braces (`uuid::text` lowercase).

**Exact normalized types before JSON construction:**

| Field class | Type | Serialization |
| --- | --- | --- |
| counts / tokens (`observed_*`, `ledger_*` counts/tokens, expected max request/success/token ints promoted) | non-negative `bigint` | base-10 integer text in JSON number form; no leading zeros; no `+` sign |
| schema_version | positive integer | base-10 integer |
| monetary (`observed_cost_usd`, `expected_max_cost_usd`, `ledger_cost_usd`) | `numeric(20,8)` | **fixed eight-decimal string** inside JSON string quotes (exact), e.g. `"0.00000000"` |
| UUID fields | `uuid` or JSON null | lowercase `uuid::text` or null |
| text fields | `text` | JSON string |

Before payload construction:

* cast every monetary value to `numeric(20,8)`;
* reject values that cannot cast without overflow/rounding beyond `(20,8)`;
* reject NaN, infinity, negative zero tricks, and negative cost (cost must be `>= 0`);
* reject negative counts/tokens;
* `0`, `0.0`, and `0.00000000` all become monetary string `"0.00000000"` and produce the **same** fingerprint;
* JSON `null` is the only representation for unavailable values.

Closed field set (alphabetical keys when constructing for fingerprint text):

```text
authorization_id
benchmark_case_id
discrepancy_type
expected_max_cost_usd
expected_max_input_tokens
expected_max_output_tokens
expected_max_requests
expected_max_successful_calls
idempotency_key
ledger_cost_usd
ledger_input_tokens
ledger_output_tokens
ledger_request_count
ledger_success_count
model_id
observed_attempt_count
observed_cost_usd
observed_input_tokens
observed_output_tokens
observed_success_count
operation
pilot_proposal_id
provider_id
schema_version
```

Canonical construction: `research.build_accounting_discrepancy_payload` (Appendix A.4 exact args) RETURNS jsonb. OWNER `postgres`; SECURITY DEFINER; `SET search_path = pg_catalog`; EXECUTE **NONE** to APP/N8N/GOV (callable only from elevated DEFINER bodies). Builds only the closed field set; applies numeric rules above.

Fingerprint:

```text
discrepancy_fingerprint = research.sha256_hex(canonical_payload::text)
```

### 8.1.1 Normative fingerprint example

Typed inputs (all present; no nulls):

```text
discrepancy_type = 'ledger_event_conflict'
pilot_proposal_id = 11111111-1111-1111-1111-111111111111
authorization_id = 22222222-2222-2222-2222-222222222222
provider_id = 33333333-3333-3333-3333-333333333333
model_id = 44444444-4444-4444-4444-444444444444
benchmark_case_id = 55555555-5555-5555-5555-555555555555
idempotency_key = 'idem-example-001'
operation = 'build_provider_request_envelope'
observed_attempt_count = 3
observed_success_count = 0
observed_input_tokens = 0
observed_output_tokens = 0
observed_cost_usd = 0::numeric(20,8)
expected_max_requests = 3
expected_max_successful_calls = 3
expected_max_input_tokens = 1000
expected_max_output_tokens = 1000
expected_max_cost_usd = 0::numeric(20,8)
ledger_request_count = 0
ledger_success_count = 0
ledger_input_tokens = 0
ledger_output_tokens = 0
ledger_cost_usd = 0::numeric(20,8)
schema_version = 9
```

Canonical payload `::text` (normative; keys alphabetical as produced by controlled builder):

```text
{"authorization_id": "22222222-2222-2222-2222-222222222222", "benchmark_case_id": "55555555-5555-5555-5555-555555555555", "discrepancy_type": "ledger_event_conflict", "expected_max_cost_usd": "0.00000000", "expected_max_input_tokens": 1000, "expected_max_output_tokens": 1000, "expected_max_requests": 3, "expected_max_successful_calls": 3, "idempotency_key": "idem-example-001", "ledger_cost_usd": "0.00000000", "ledger_input_tokens": 0, "ledger_output_tokens": 0, "ledger_request_count": 0, "ledger_success_count": 0, "model_id": "44444444-4444-4444-4444-444444444444", "observed_attempt_count": 3, "observed_cost_usd": "0.00000000", "observed_input_tokens": 0, "observed_output_tokens": 0, "observed_success_count": 0, "operation": "build_provider_request_envelope", "pilot_proposal_id": "11111111-1111-1111-1111-111111111111", "provider_id": "33333333-3333-3333-3333-333333333333", "schema_version": 9}
```

Expected fingerprint for tests: `research.sha256_hex(<exact canonical payload text above>)` computed under schema-9 `research_crypto`. The payload text is normative; the hex digest is whatever that function returns for that exact UTF-8 text. Tests MUST assert stability of that digest across monetary inputs `0`, `0.0`, and `0.00000000`, and MUST assert inequality when any typed field changes.

### 8.2 Table `research.accounting_discrepancies`

```text
research.accounting_discrepancies (
  id UUID PRIMARY KEY DEFAULT research_crypto.gen_random_uuid(),
  discrepancy_fingerprint CHAR(64) NOT NULL UNIQUE CHECK (discrepancy_fingerprint ~ '^[0-9a-f]{64}$'),
  pilot_proposal_id UUID NOT NULL REFERENCES research.provider_pilot_proposals(id),
  discrepancy_payload JSONB NOT NULL,
  recorded_by_role TEXT NOT NULL CHECK (recorded_by_role IN ('research_app', 'research_governance', 'postgres')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

Immutable after insert. Trigger `trg_reject_accounting_discrepancy_mutation` → `reject_accounting_discrepancy_mutation()`.

### 8.3 Typed recorder (no arbitrary JSONB from APP)

`research.record_accounting_discrepancy` accepts **typed scalar parameters only** — no open JSONB parameter.

```text
research.record_accounting_discrepancy(
  p_discrepancy_type text,
  p_pilot_proposal_id uuid,
  p_authorization_id uuid,
  p_provider_id uuid,
  p_model_id uuid,
  p_benchmark_case_id uuid,
  p_idempotency_key text,
  p_operation text,
  p_observed_attempt_count bigint,
  p_observed_success_count bigint,
  p_observed_input_tokens bigint,
  p_observed_output_tokens bigint,
  p_observed_cost_usd numeric,
  p_expected_max_requests integer,
  p_expected_max_successful_calls integer,
  p_expected_max_input_tokens integer,
  p_expected_max_output_tokens integer,
  p_expected_max_cost_usd numeric,
  p_ledger_request_count bigint,
  p_ledger_success_count bigint,
  p_ledger_input_tokens bigint,
  p_ledger_output_tokens bigint,
  p_ledger_cost_usd numeric,
  p_schema_version integer,
  p_expected_fingerprint char(64)
) RETURNS uuid
```

OWNER `postgres`; SECURITY DEFINER; `SET search_path = pg_catalog`; EXECUTE `research_app` AND `research_governance` only after cutover complete.

Inside the function:

1. Validate each scalar type and range (non-negative counts/tokens; monetary cast to `numeric(20,8)`; positive schema_version; closed `discrepancy_type` / `operation` enums).
2. Reject missing required identifiers (`pilot_proposal_id`, etc. where required by type).
3. Reject unsupported discrepancy types and operations.
4. Reconstruct canonical payload via `research.build_accounting_discrepancy_payload(...)`.
5. No open JSON parameter exists → arbitrary extra fields cannot be submitted.
6. Recompute fingerprint internally via `research.sha256_hex(payload::text)`.
7. Compare with `p_expected_fingerprint`; mismatch → reject; no insert.
8. Insert or return existing immutable row on UNIQUE fingerprint (idempotent).
9. Never accept arbitrary JSONB from `research_app`.

### 8.4 Two-transaction failure protocol

1. Preflight/builder detects accounting conflict.
2. Builds typed scalar denial result including `expected_fingerprint` (computed via DEFINER-internal payload builder). No envelope/event insert.
3. Returns structured denied result. No reservation or envelope created.
4. First transaction commits no capacity mutations.
5. Caller opens a **separate** transaction.
6. Caller invokes `record_accounting_discrepancy` with the same typed scalars + fingerprint.
7. Recorder reconstructs, recomputes, compares; mismatch fails.
8. Recording failure never permits the request; return `recording_failed`.
9. Governance resolution appends `accounting_discrepancy_acknowledged`; never mutates discrepancy rows.
10. Discrepancy inserts NEVER share the failed build transaction.

---
## 9. Envelope creation

### 9.1 Pilot path

`research.build_provider_request_envelope` — SECURITY DEFINER; OWNER `postgres`; `SET search_path = pg_catalog`; EXECUTE `research_app` only; requires authorization `pilot_proposal_id IS NOT NULL`. Direct INSERT on `live_request_envelopes` revoked from app/n8n/PUBLIC/governance.

### 9.2 Round 4 non-pilot path

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

SECURITY DEFINER; OWNER `postgres`; `SET search_path = pg_catalog`; EXECUTE `research_app` only; requires `pilot_proposal_id IS NULL`; does not write `pilot_capacity_events`. Wrong builder for pilot-linked auth fails closed.

---

## 10. Activation invariant (no GUC)

Session-GUC model (`research.allow_pilot_activation`) is **completely removed**.

Privilege rule: `research_app`, `n8n_app`, and `research_governance` have **no** direct `UPDATE` privilege on `provider_authorization_records` (SELECT only). Activation occurs only through owner-controlled:

```text
research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text)
  RETURNS research.provider_authorization_records
```

OWNER `postgres`; SECURITY DEFINER; EXECUTE `research_governance` only.

`research.trg_authorization_validity_guard()` independently recomputes and enforces every activation prerequisite even for an owner-issued direct UPDATE.

For a pilot-linked transition into `active`, the trigger MUST require all of:

1. Executing identity is the expected owner (`postgres` via DEFINER / `current_user = 'postgres'`)
2. Linked proposal terminal governance state is `pilot_approved` (not expired, fingerprint match)
3. Credential terminal state is `credential_status_confirmed` for the bound **`(proposal_id, provider_id)`** scope (not provider-only lookup)
4. Provider terminal governance state is `provider_enabled_for_proposal`
5. Model terminal governance state is `model_enabled_for_proposal`
6. Matching terminal `authorization_activation_approved` exists for `(proposal_id, authorization_id)`
7. Provider, model, proposal, role, case, authority, and fingerprint match
8. `providers.enabled` and matching model candidate `enabled` are true operationally
9. `activated_at` changes from `NULL` to exactly one timestamp
10. `expires_at = activated_at + INTERVAL '24 hours'`
11. No prior activation existed (`OLD.activated_at IS NULL`, `OLD.status` not previously active)
12. No in-place renewal

After activation:

* `activated_at` immutable; `expires_at` immutable
* active → proposed rejected
* expired → active rejected
* Direct activation with missing governance prerequisites rejected
* No GUC, caller flag, or mutable session state accepted

The controlled function remains the only supported production path. Trigger protects invariants even for owner-issued DML.

---

## 11. Helper isolation

Move all of the following from `research` to `research_test`, or DROP from `research` if already absent after move:

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

After move: `research_test.<same_name>`, OWNER `postgres`, EXECUTE only `research_test`. No APP/N8N/GOV USAGE on `research_test`. Moved helpers needing `research` access are SECURITY DEFINER with FQ `research.*` / `research_crypto.*` refs.

---

## 12. Append-only trigger functions and trigger objects

Every function below: `() RETURNS trigger`; LANGUAGE `plpgsql`; OWNER `postgres`; SECURITY INVOKER (trigger context); `SET search_path = pg_catalog`; fully qualified refs only; `REVOKE ALL … FROM PUBLIC`; EXECUTE grant to APP/N8N/GOV/TEST = **NONE**. Trigger execution does not require runtime EXECUTE grants. Enabled state: **ENABLE**.

| Trigger object | Table | Timing | Events | Function | SQLSTATE / message |
| --- | --- | --- | --- | --- | --- |
| `research.trg_reject_taha_governance_action_mutation` | `research.taha_governance_actions` | BEFORE | UPDATE OR DELETE | `research.reject_taha_governance_action_mutation()` | `P0001` / `taha_governance_actions is append-only` |
| `research.trg_reject_pilot_capacity_event_mutation` | `research.pilot_capacity_events` | BEFORE | UPDATE OR DELETE | `research.reject_pilot_capacity_event_mutation()` | `P0001` / `pilot_capacity_events is append-only` |
| `research.trg_reject_accounting_discrepancy_mutation` | `research.accounting_discrepancies` | BEFORE | UPDATE OR DELETE | `research.reject_accounting_discrepancy_mutation()` | `P0001` / `accounting_discrepancies is append-only` |
| `research.trg_reject_legacy_reservation_archive_mutation` | `research.legacy_reservation_archive` | BEFORE | UPDATE OR DELETE | `research.reject_legacy_reservation_archive_mutation()` | `P0001` / `legacy_reservation_archive is append-only` |
| `research.trg_reject_legacy_capacity_table_mutation` | `research.pilot_capacity_reservations_legacy` | BEFORE | INSERT OR UPDATE OR DELETE | `research.reject_legacy_capacity_table_mutation()` | `P0001` / `pilot_capacity_reservations_legacy is immutable audit` |

Catalog assertion: all five trigger names exist, enabled, attached to exact tables, bound to exact functions. Catalog drift in any trigger name or attachment fails validation.

---

## 13. Migration state machine (schema 8 → 9)

Schema version advances to **9** only at the designated step; EXECUTE re-grant occurs only after `cutover_complete`. The advisory lock is **not** runtime protection. Runtime is enforceably frozen by privilege revocation plus the cutover marker before the first security-sensitive DDL beyond the freeze itself.

### 13.0 Cutover marker table

```text
research.schema9_cutover_state (
  migration_id TEXT PRIMARY KEY CHECK (migration_id = 'schema_8_to_9'),
  starting_schema_version INT NOT NULL CHECK (starting_schema_version = 8),
  freeze_at TIMESTAMPTZ NOT NULL,
  state TEXT NOT NULL CHECK (state IN (
    'runtime_frozen',
    'cutover_validating',
    'cutover_complete',
    'cutover_failed'
  )),
  detail TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

Privileges: PUBLIC/APP/N8N/GOV/TEST = **NONE** (owner-only). Schema-9 elevated builders and governance writers MUST fail closed unless `state = 'cutover_complete'` (in addition to EXECUTE grants). Failure after freeze leaves `runtime_frozen` or `cutover_failed`; recovery resumes under frozen EXECUTE revokes; no broad grant during recovery.

### 13.1 Freeze inventory (exact)

At step 3 (runtime freeze), `REVOKE EXECUTE ON FUNCTION … FROM research_app, n8n_app, research_governance, PUBLIC` for every signature below. Also revoke direct mutating table privileges in §13.1.1. Any revoke/assert failure → set `cutover_failed`; version stays 8; keep runtime blocked.

**Frozen EXECUTE (lose EXECUTE from APP/N8N/GOV/PUBLIC):**

* `research.build_provider_request_envelope(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_canonical_request jsonb, p_claimed_credential_status text)`
* `research.build_non_pilot_request_envelope(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_claimed_credential_status text)` (once created; remains revoked until step 20)
* `research.live_preflight(p_provider_code text, p_model_provisional text, p_benchmark_case_id uuid, p_authorization_id uuid, p_role_code text, p_confidentiality_class text, p_claimed_credential_status text, p_projected_input_tokens integer, p_projected_output_tokens integer, p_is_retry boolean, p_fallback_provider text)`
* `research.orchestrate_research_run(p_run_id uuid)`
* `research.run_stage(p_run_id uuid, p_stage text, p_scenario_hint text)`
* `research.record_authorization_spend(p_authorization_id uuid, p_requests integer, p_tokens integer, p_cost numeric, p_note text)`
* `research.mock_adapter_invoke(p_request_id uuid)`
* `research.parse_provider_fixture_response(p_provider_code text, p_fixture jsonb)`
* `research.activate_pilot_authorization(p_authorization_id uuid, p_pilot_code text)`
* `research.append_governance_action(p_action_type text, p_proposal_id uuid, p_authorization_id uuid, p_provider_id uuid, p_model_id uuid, p_decision_value text, p_material_fingerprint char(64), p_supersedes_action_id uuid, p_issued_at timestamptz, p_expires_at timestamptz, p_payload jsonb)`
* `research.approve_pilot_proposal(p_pilot_code text)`
* `research.confirm_provider_credential_status(p_pilot_proposal_id uuid, p_provider_code text, p_n8n_credential_label text, p_governance_action_id uuid, p_note text)`
* `research.enable_provider_for_pilot(p_pilot_code text, p_provider_code text)`
* `research.enable_model_for_pilot(p_pilot_code text, p_provider_code text, p_model_id_provisional text)`
* `research.disable_provider_for_pilot(p_pilot_code text, p_provider_code text)`
* `research.disable_model_for_pilot(p_pilot_code text, p_provider_code text, p_model_id_provisional text)`
* `research.record_accounting_discrepancy` (typed Appendix A.4 signature; remains revoked until step 20)
* `research.build_accounting_discrepancy_payload` (EXECUTE NONE to runtime always; DEFINER-internal only)
* All Appendix A.4 `_r3*`, `_r4*`, `_r5a*`, `cleanup_test_fixture(p_fixture_id text)`, `record_pilot_usage_for_tests(p_authorization_id uuid, p_input_tokens integer, p_output_tokens integer, p_success boolean, p_fixture_id text, p_is_retry boolean)`

**KEEP EXECUTE during freeze (read-only inspect):** `research.gemini_pilot_5a_gate_status()`, `research.sha256_hex(p_text text)`, `research.pilot_capacity_snapshot(p_pilot_id uuid)`, `research.pilot_case_attempt_count(p_pilot_id uuid, p_benchmark_case_id uuid)`.

#### 13.1.1 Direct table privilege freeze (same boundary)

REVOKE INSERT/UPDATE/DELETE from APP/N8N/GOV/PUBLIC on at least: `live_request_envelopes`, `provider_authorization_records`, `provider_usage_ledger`, `provider_credential_status`, `providers`, `provider_model_candidates`, `provider_pilot_proposals`, `pilot_capacity_reservations` (while present), and all NEW schema-9 write tables until final allowlist.

Catalog assertion: for every frozen signature, `has_function_privilege(role, oid, 'EXECUTE') = false` for APP/N8N/GOV/PUBLIC.

### 13.2 Re-grant point

Runtime EXECUTE and exact Appendix A table grants restored **only** when all of: (1) all schema-9 objects exist; (2) legacy data reconciled; (3) unsafe functions replaced/removed; (4) privilege/ownership assertions pass; (5) provider/model remain disabled; (6) credentials unchanged; (7) no proposal/authorization activated by migration; (8) no active workflow; (9) schema version = 9; (10) cutover state = `cutover_complete`. Do **not** temporarily restore schema-8 builders. Old and new builders never simultaneously executable.

### 13.3 Numbered steps

| Step | Precondition | Object affected | Postcondition | Rerun | Failure | Recovery | Catalog assertion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Connected as `postgres`; advisory lock free | `pg_advisory_lock(hashtext('srl_schema9_cutover'))` | Lock held | Re-acquire | Abort; version 8 | Retry | Lock held |
| 2 | Lock held; max(version)=8 | Catalog vs schema-8 baseline | Expected objects present | Re-verify | Abort | Fix; restart | max(version)=8 |
| 3 | Step 2 | **Runtime freeze**: REVOKE EXECUTE on §13.1; revoke gated table writes; upsert `schema9_cutover_state` → `runtime_frozen` | Entrypoints non-executable; marker frozen | Re-REVOKE; marker upsert | `cutover_failed`; keep revoked | Keep frozen; resume 3 | Freeze EXECUTE asserts false; state=`runtime_frozen` |
| 4 | Step 3 frozen | Roles; schemas; CREATE revoke | Memberships correct; CREATE revoked | Idempotent | Keep frozen | Resume 4 | CREATE=false |
| 5 | Step 4 | PUBLIC EXECUTE; defaults; create `research_crypto` + move pgcrypto | Crypto locked | Idempotent | Keep frozen; version 8 | Fix crypto; resume 5 | Extension in `research_crypto` |
| 6 | Step 5 | Governance tables + chain indexes + decision CHECK + §12 triggers | Structures+triggers exist | IF NOT EXISTS | Keep frozen | Resume 6 | Triggers+indexes present |
| 7 | Step 6 | Capacity events, archive UNIQUE, discrepancies, typed recorder shells; marker → `cutover_validating` | Objects exist; EXECUTE still revoked for new writers | Idempotent | Keep frozen | Resume 7 | Uniques+triggers |
| 8 | Step 7 + State A/B (§13.4) | Legacy backfill / archive | Consumed capacity preserved | Skip existing keys | Keep frozen | Resume per state | Reconciliation |
| 9 | Step 8 | Ledger conflict typed discrepancy inserts (owner session) | Conflicts recorded | Idempotent fingerprints | Keep frozen | Resume 9 | No capacity restore |
| 10 | Step 9 | Create/replace governance+builder+activation+discrepancy bodies; **LEAVE EXECUTE revoked** | Bodies present; non-executable by APP/GOV | CREATE OR REPLACE | Keep frozen | Resume 10 | FQ crypto; no GUC; EXECUTE false for APP |
| 11 | Step 10 | Rewrite snapshot/case-count/envelope immutability; remove reservation deps using **State A or State B name only** | Zero unresolved production deps | Idempotent | Keep frozen | Resume 11 | Dep scan |
| 12 | Step 11 | Helper move to research_test | Helpers gone from research | DROP IF EXISTS | Keep frozen | Resume 12 | Inventory |
| 13 | Step 12 | Round 4 path readiness (still revoked) | Non-pilot builder exists; EXECUTE false | Idempotent | Keep frozen | Resume 13 | Signature |
| 14 | Step 13 + State A/B | Rename (State A only) or verify (State B); lockdown legacy; attach `trg_reject_legacy_capacity_table_mutation` | Legacy immutable; original absent | §13.4 | State C → cutover_failed | Resume per §13.4 | Original absent; legacy present |
| 15 | Step 14 | Ownership/disabled/cred/auth zero-mutation asserts | Invariants hold | Re-assert | Keep frozen | Resume 15 | gemini disabled; 0 active |
| 16 | Step 15 | Crypto+trigger inventory + freeze still held | Assert green | Re-assert | Keep frozen | Resume 16 | Five triggers; crypto OK |
| 17 | Step 16 | Final ACL dry-run vs Appendix A **without granting** | Drift report empty | Re-run | Keep frozen | Resume 17 | Zero projected drift |
| 18 | Step 17 | Insert version 9 row | max(version)=9 | Insert only if asserts green | Do not insert 9 | Fix; resume | max=9 |
| 19 | Step 18 | Marker → `cutover_complete` | Marker complete | Idempotent | If fail: keep EXECUTE revoked; cutover_failed | Owner repair | state=`cutover_complete` |
| 20 | Step 19 | **Exact Appendix A allowlist GRANT only** | Schema-9 grants exact; helpers absent | Re-GRANT exact | Revoke to freeze; cutover_failed | Fix; resume 20 | ACL=Appendix A |

### 13.4 Post-rename restart branches

#### State A — original table exists

```text
to_regclass('research.pilot_capacity_reservations') IS NOT NULL
to_regclass('research.pilot_capacity_reservations_legacy') IS NULL
```

Run dependency inventory; reconcile/backfill; rewrite dependents targeting the **original** name; assert zero unresolved production deps; RENAME to legacy; continue lockdown.

#### State B — legacy table exists

```text
to_regclass('research.pilot_capacity_reservations') IS NULL
to_regclass('research.pilot_capacity_reservations_legacy') IS NOT NULL
```

Do **not** rerun original-name rewrites. Inspect legacy + schema-9 events; verify reconciliation and archive uniqueness; verify zero production deps on legacy; recreate missing immutability trigger only if absent; continue from first incomplete **post-rename** step. **No State B step may reference the original table name.**

#### State C — both or neither

Mark `cutover_failed`; keep runtime frozen; do not advance schema version; deterministic structural error; require owner intervention.

Completion detection after rename: legacy exists; trigger present; EXECUTE still frozen until step 20; event/archive uniques. Duplicate backfill prevented by event UNIQUE keys and archive `UNIQUE(legacy_reservation_id)`.

### 13.5 Partial-cutover matrix

| Step | Runtime state | Schema version | Old builders executable | New builders executable | Recovery entrypoint |
| --- | --- | ---: | --- | --- | --- |
| 1 | locking | 8 | yes (pre-freeze) | no | step 1 |
| 2 | locking | 8 | yes (pre-freeze) | no | step 2 |
| 3 | `runtime_frozen` | 8 | **no** | **no** | step 3 |
| 4–9 | frozen / validating | 8 | **no** | **no** | same step |
| 10–17 | `cutover_validating` | 8 | **no** | **no** | same step |
| 18 | validating | 9 | **no** | **no** | step 18/19 |
| 19 | `cutover_complete` | 9 | **no** | **no** | step 20 |
| 20 | `cutover_complete` | 9 | **no** (absent) | **yes** (allowlist only) | step 20 |

Operators MUST NOT run application traffic during steps 1–2. From step 3 onward, old and new builders are never both executable; new builders become executable only at step 20.

---

## 14. Default privileges (future objects)

```text
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research
  REVOKE ALL ON TABLES FROM PUBLIC, research_app, n8n_app, research_governance;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research
  REVOKE ALL ON FUNCTIONS FROM PUBLIC, research_app, n8n_app, research_governance;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research
  REVOKE ALL ON SEQUENCES FROM PUBLIC, research_app, n8n_app, research_governance;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research_crypto
  REVOKE ALL ON TABLES FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research_crypto
  REVOKE ALL ON FUNCTIONS FROM PUBLIC, research_app, n8n_app, research_governance, research_test;
```

Future objects = NONE until an explicit allowlist migration updates Appendix A.

---

## 15. Design decisions (locked)

| Topic | Decision |
| --- | --- |
| Freeze mechanism | Step-3 EXECUTE+table WRITE revoke + `schema9_cutover_state`; advisory lock is not protection |
| Runtime re-enable point | Only after version 9 + `cutover_complete` + exact Appendix A grants |
| Credential function signature | Proposal-scoped confirm with mandatory `p_pilot_proposal_id` + `p_governance_action_id` |
| Discrepancy recorder signature | Typed scalars only; reconstructs payload; no APP JSONB |
| Monetary canonical form | `numeric(20,8)` as fixed eight-decimal JSON strings |
| Legacy restart detection | State A / B / C via `to_regclass` |
| Trigger naming | Exact `trg_reject_*` objects bound to `reject_*` functions |
| Schema-version advancement | Version 9 at step 18; EXECUTE re-grant only at step 20 |
| Action-chain parent rule | `supersedes_action_id` = immediate same-scope parent; one child per parent |
| Terminal-state rule | Enabled only if terminal action is enable + valid |

---

## Appendix A — Machine-exact object allowlist

**Rule:** Any `research` / `research_crypto` object not listed is denied (`NONE`) to runtime roles and PUBLIC unless a row grants otherwise.
**Owner:** `postgres` unless Disposition says MOVED.

Privilege tokens: `NONE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `EXECUTE`, `USAGE`, `MOVED TO research_test`, `RENAMED`, `DEPRECATED`.

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
| research.pilot_capacity_reservations_legacy | table | postgres | NONE | NONE | NONE | NONE | NONE | RENAMED from pilot_capacity_reservations; DEPRECATED; owner SELECT only |
| research.proposal_versions | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.provider_adapter_requests | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.provider_adapter_responses | table | postgres | NONE | SELECT,INSERT | SELECT | SELECT | NONE | KEEP |
| research.provider_adapter_versions | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP |
| research.provider_authorization_records | table | postgres | NONE | SELECT | SELECT | SELECT | NONE | KEEP; no runtime UPDATE |
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

DELETE = NONE for every table for every runtime role. `research.pilot_capacity_reservations` (unrenamed) MUST NOT exist after step 15.

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

None in schema `research` or `research_crypto` for application use at schema 9. Future sequences: NONE to runtime roles until allowlist migration.

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

## Appendix B — Open risks (accepted)

- Owner/`postgres` break-glass DML still possible; mitigated by append-only and activation triggers recomputing prerequisites.
- Theft of `research_governance` login equals full governance power; keep local-only.
- Round 4 adapters must call `build_non_pilot_request_envelope` after schema 9 implementation.
- Human operator error during migration windows; mitigated by advisory lock and version-8 hold until step 20.
- `ALTER EXTENSION … SET SCHEMA` requires exclusive migration window; failure blocks version advancement.
