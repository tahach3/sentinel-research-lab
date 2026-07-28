# Round 5A â€” Security Boundary Redesign

**Status:** Design only. Not implemented.
**Baseline HEAD:** `7df838574fc9051caa6132f82f189ffd5b0a2d1e` (schema version 8)
**Scope:** Gemini pilot (`GEMINI-PILOT-5A`) approval, authorization activation, immutable capacity accounting, and request-envelope creation.
**Non-goals:** Round 5B live HTTP, credential secret storage, enabling Gemini or `gemini-2.5-flash`, workflow activation, Equitify/SENTINEL changes.

---

## 1. Threat model

### Assets

| Asset | Why it matters |
| --- | --- |
| Pilot proposal approval state | Controls whether any activation may proceed |
| Authorization `status` / `activated_at` / `expires_at` | Controls the 24-hour executable window |
| Credential-status registry (`present` / `missing`) | Confirms Tahaâ€™s manual n8n credential without storing secrets |
| Provider/model `enabled` flags | Hard kill switches for live readiness |
| Capacity consumption (requests, attempts, tokens, success, cost) | Enforces pilot bounds (3/1/8000/4000/USD 0.00) |
| `live_request_envelopes` rows | Downstream execution artifacts |

### Adversary (in scope)

`research_app` (and any client using its credentials) with full SQL access under that roleâ€™s privileges: `SELECT`/`INSERT`/`UPDATE`/`DELETE`/`EXECUTE` as granted today, plus ability to call `set_config` on custom GUCs.

Out of scope for this redesign: stolen `postgres` superuser, host filesystem compromise, physical access to Tahaâ€™s machine.

### Confirmed attack classes (must be eliminated)

1. **Session-GUC activation:** `set_config('research.allow_pilot_activation','on',true)` + `UPDATE ... status='active'`.
2. **Mutable reservation capacity:** `UPDATE`/`DELETE` on `pilot_capacity_reservations` restores limits.
3. **Callable arm/reset helpers:** `research._r5a_final_arm_gates()` / `_r5a_final_reset_defaults()` approve/enable/credential-mark.
4. **Direct envelope insert:** `INSERT INTO live_request_envelopes` without capacity consumption.

### Design principle

**Permissions remove write capability; triggers and constraints are defense in depth only.**
Do not rely on application discipline, forgeable session variables, or mutable â€œpendingâ€ rows as sole evidence of consumed capacity.

---

## 2. Trust boundaries

```text
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Boundary A â€” Migration / governance (human Taha + admin role)   â”‚
â”‚  â€¢ Owns research schema objects                                 â”‚
â”‚  â€¢ Approves pilots, records credential confirmation             â”‚
â”‚  â€¢ Activates authorizations (elevated function)                 â”‚
â”‚  â€¢ Never stores API key material                                â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                â”‚ SECURITY DEFINER functions only
                                â”‚ (fixed search_path, owner = schema owner)
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Boundary B â€” Runtime application (`research_app`)               â”‚
â”‚  â€¢ SELECT governance/capacity/envelope state                    â”‚
â”‚  â€¢ EXECUTE only: build_provider_request_envelope (+ preflight)â”‚
â”‚  â€¢ No UPDATE/DELETE on governance, auth timestamps, capacity, â”‚
â”‚    envelopes; no EXECUTE on approval/activation/arm/test helpersâ”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                â”‚ read-only
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Boundary C â€” n8n runtime (`n8n_app`)                            â”‚
â”‚  â€¢ SELECT only on research tables needed for inactive designs â”‚
â”‚  â€¢ No EXECUTE on research governance functions                  â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

Secrets stay in n8nâ€™s credential store (manual Taha entry). Postgres holds only non-secret status labels.

---

## 3. Role and permission matrix

| Role | Purpose | Typical login |
| --- | --- | --- |
| `postgres` / cluster superuser | Break-glass only | Local admin |
| `research_owner` (or existing table owner, e.g. `postgres` in lab) | Object owner of `research.*` tables/functions | Migrations |
| `research_governance` | Taha-controlled governance session | Explicit psql / governed script after human intent |
| `research_app` | Application / automation runtime | App connection string |
| `n8n_app` | n8n DB user | n8n container |
| `research_test` (optional, non-production) | Isolated test helpers | CI / local test runner only; **not** granted to app |

### Matrix (pilot-critical objects)

| Object | `research_app` | `n8n_app` | `research_governance` | Owner |
| --- | --- | --- | --- | --- |
| `provider_pilot_proposals` | SELECT | SELECT | SELECT; mutations **only** via governance functions | owner |
| `provider_authorization_records` | SELECT | SELECT | SELECT; activation **only** via function | owner |
| `provider_credential_status` | SELECT | SELECT | SELECT; status change **only** via function | owner |
| `providers` / `provider_model_candidates` | SELECT | SELECT | SELECT; enable **only** via governance (Round 5B+) | owner |
| `pilot_capacity_events` (new, append-only) | SELECT | SELECT | SELECT | owner |
| `live_request_envelopes` | SELECT | SELECT | SELECT | owner |
| `provider_usage_ledger` | SELECT (+ fixture delete path only if retained under owner functions) | SELECT | SELECT | owner |
| `approve_pilot_proposal(...)` | **REVOKE EXECUTE** | REVOKE | GRANT EXECUTE | owner, `SECURITY DEFINER` |
| `confirm_provider_credential_status(...)` | **REVOKE** | REVOKE | GRANT | owner, `SECURITY DEFINER` |
| `activate_pilot_authorization(...)` | **REVOKE** | REVOKE | GRANT | owner, `SECURITY DEFINER` |
| `build_provider_request_envelope(...)` | GRANT EXECUTE | REVOKE | GRANT (optional) | owner, `SECURITY DEFINER` |
| `live_preflight(...)` | GRANT EXECUTE | REVOKE | GRANT | owner (invoker or definer; no elevated writes) |
| `_r5a_final_arm_gates` / `_r5a_final_reset_defaults` / test helpers | **REVOKE**; prefer DROP or move to `research_test` | REVOKE | REVOKE in prod | N/A |
| Sequences used by append-only inserts | USAGE only where required by definer functions (prefer owned sequences used inside definer) | â€” | â€” | owner |

**Hard rule:** `research_app` must have **zero** `INSERT`/`UPDATE`/`DELETE` on:

- `provider_pilot_proposals`
- `provider_authorization_records`
- `provider_credential_status`
- `providers`
- `provider_model_candidates`
- `provider_budget_policies` (pilot-critical columns)
- `pilot_capacity_events` / legacy `pilot_capacity_reservations` (after migration)
- `live_request_envelopes`

Envelope creation and capacity append happen **inside** `SECURITY DEFINER` builder as owner.

---

## 4. Object ownership model

1. All `research` schema tables, indexes, triggers, and governance/builder functions are owned by the migration role (`research_owner` / current lab owner).
2. `SECURITY DEFINER` functions:
   - `OWNER` = table owner
   - `SET search_path = research, pg_temp` (fixed; never caller-controllable)
   - Perform privilege checks explicitly where needed (`current_user` / `session_user` âˆˆ allowed governance roles for approve/activate/confirm)
3. `ALTER DEFAULT PRIVILEGES` for the owner role in schema `research`:
   - **Stop** granting `INSERT, UPDATE, DELETE` on tables to `research_app` by default
   - New tables: `GRANT SELECT` only to `research_app` and `n8n_app`
   - New functions: **no** default `EXECUTE` to `research_app`; grant explicitly per function
4. Migration 009 (future implementation) must:
   - `REVOKE ALL ON ALL TABLES IN SCHEMA research FROM research_app`
   - Re-`GRANT SELECT` as needed
   - `REVOKE ALL ON ALL FUNCTIONS IN SCHEMA research FROM research_app`
   - Re-`GRANT EXECUTE` only on the allowlisted runtime functions
   - Same pattern for `n8n_app` (SELECT only; no research EXECUTE)

---

## 5. Approval and activation state machine

### 5.1 How Taha approval is represented (no secrets, not forgeable by app)

**Do not** use:

- session GUCs
- application-writable boolean columns without role checks
- â€œcredential presentâ€ alone as approval

**Do use** a two-step, governance-role-only chain:

1. **Credential confirmation (non-secret):**
   `research.confirm_provider_credential_status(provider_code, label, note)`
   - Executable **only** by `research_governance`
   - Sets `provider_credential_status.status = 'present'` and stores **label only** (e.g. `sentinel-research-lab-gemini-pilot`)
   - Appends an immutable row to `research.taha_governance_actions` (`action_type='credential_confirmed'`, `actor_role`, `at`, `payload` JSONB without secrets)

2. **Pilot approval:**
   `research.approve_pilot_proposal(pilot_code)`
   - Executable **only** by `research_governance`
   - Requires credential status already `present` for linked provider
   - Sets proposal `status='approved'`, `taha_approved_at=now()`, `expires_at=taha_approved_at + expiry_hours`
   - Appends `taha_governance_actions` (`action_type='pilot_approved'`)
   - **Never** enables provider/model
   - **Never** activates authorizations

`research_app` cannot call either function and cannot `UPDATE` those tables.

### 5.2 Authorization activation

**Single function:** `research.activate_pilot_authorization(authorization_id, pilot_code)`
**Caller:** `research_governance` only (`EXECUTE` revoked from `research_app`).

Preconditions (fail closed, leave rows unchanged on failure):

- Auth row `status='proposed'` and `activated_at IS NULL`
- `pilot_proposal_id` set; pilot `status='approved'` and not expired
- Credential status for provider is `present`
- Provider/model identities match pilot (`gemini` / `gemini-2.5-flash` for this pilot)
- Case âˆˆ pilot `benchmark_case_ids`
- `approving_authority = 'Taha'`

Effects:

- Set `status='active'`
- Set `activated_at` **once**
- Set `expires_at = activated_at + INTERVAL '24 hours'` exactly
- Append `taha_governance_actions` (`authorization_activated`)
- Do **not** mutate proposal status
- Do **not** enable provider/model

### 5.3 Rejected transitions (DB-enforced)

| Transition | Result |
| --- | --- |
| Direct `UPDATE` status/timestamps by non-owner | Permission denied (`research_app` has no UPDATE) |
| Any GUC / session variable gating | **Removed entirely**; not part of design |
| `active` â†’ `proposed` | Forbidden (constraint/trigger + no UPDATE for app) |
| `expired`/`revoked`/`exhausted` â†’ `active` | Forbidden; renewal = **new** authorization row |
| Second activation when `activated_at` already set | Forbidden |
| Changing `activated_at` / `expires_at` after first set | Forbidden (owner trigger defense in depth) |

Triggers remain for owner mistakes and break-glass sessions; they are **not** the primary controlâ€”**REVOKE UPDATE** is.

### 5.4 State machines (summary)

**Pilot proposal:**
`awaiting_taha_credential` â†’ (governance confirm credential) stays awaiting or moves per ops policy â†’ (governance approve) `approved` â†’ (`expires_at`) `expired`
App cannot write.

**Authorization:**
`proposed` â†’ (governance activate) `active` â†’ (`expires_at` or ops) `expired` | `revoked` | `exhausted`
No return to `proposed`. Renewal = insert new `proposed` row (governance/migration only).

---

## 6. Immutable capacity-accounting model

### 6.1 Replace mutable reservations

Deprecate `research.pilot_capacity_reservations` as **capacity evidence**.

Introduce append-only:

```text
research.pilot_capacity_events
  id UUID PK
  pilot_proposal_id UUID NOT NULL
  authorization_id UUID NOT NULL
  benchmark_case_id UUID NOT NULL
  event_type TEXT NOT NULL
    CHECK (event_type IN (
      'attempt_consumed',      -- first envelope prep for a case (permanent)
      'idempotency_bound'      -- optional alias; or fold into attempt_consumed
    ))
  idempotency_key TEXT NOT NULL
  projected_input_tokens INT NOT NULL CHECK (>=0)
  projected_output_tokens INT NOT NULL CHECK (>=0)
  projected_cost_usd NUMERIC NOT NULL CHECK (=0)
  envelope_id UUID NULL      -- filled in same txn after envelope insert
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  UNIQUE (pilot_proposal_id, idempotency_key)
  UNIQUE (pilot_proposal_id, benchmark_case_id)
    -- one permanent attempt per case for this pilot
```

**No `status` column that can be â€œreleasedâ€.**
**No UPDATE/DELETE grants to any runtime role.**
Owner may retain a `SECURITY DEFINER` cleanup that deletes only rows with an explicit `test_run_id` in a separate test schemaâ€”not production capacity.

### 6.2 Counting rules

| Bound | Source |
| --- | --- |
| Total requests | `COUNT(*)` of `attempt_consumed` events for pilot (+ finalized ledger request_count if still used for historical success accounting) |
| Attempts per case | uniqueness on `(pilot, case)` â€” second insert fails |
| Input/output tokens | `SUM(projected_*)` over events + finalized ledger tokens |
| Successful calls | finalized `provider_usage_ledger` where `success` only (unchanged semantics) |
| Cost | all projected and authorized costs must be `0`; any `>0` fails closed |

Pending, failed, and abandoned executions **still consume** the case attempt once `attempt_consumed` is inserted. Capacity never reopens.

### 6.3 Idempotent replay

1. Lock pilot proposal row `FOR UPDATE`.
2. Lock authorization row `FOR UPDATE`.
3. Lookup event by `(pilot_proposal_id, idempotency_key)`.
4. If found with `envelope_id` set â†’ return existing envelope; **no new event**.
5. If found without `envelope_id` â†’ fail closed (incomplete prior txn should have rolled back; orphan = operator investigation).
6. If not found â†’ validate limits â†’ `INSERT` event â†’ `INSERT` envelope â†’ `UPDATE event SET envelope_id` **only inside SECURITY DEFINER** (owner). Runtime roles cannot run that UPDATE; only the definer function can.

### 6.4 Concurrency

Transaction ordering under the builder:

1. `BEGIN` (caller or function-implicit)
2. `SELECT pilot FOR UPDATE`
3. `SELECT auth FOR UPDATE`
4. Idempotency lookup
5. Recompute aggregates including events
6. `INSERT pilot_capacity_events` (unique constraints serialize conflicting case/key)
7. `INSERT live_request_envelopes`
8. Link `envelope_id`
9. `COMMIT`

Two concurrent competitors for the last slot: one unique insert succeeds; the other hits unique or limit check and fails. No over-capacity.

### 6.5 Legacy table

After cutover: drop grants on `pilot_capacity_reservations`; migrate any durable reserved rows into events; then drop table or leave empty/read-only for audit. Mutable reservation design is **not** retained.

---

## 7. Controlled envelope-creation flow

### 7.1 Single write path

Only `research.build_provider_request_envelope(...)` (`SECURITY DEFINER`, owner) may insert into `live_request_envelopes`.

`research_app`: `EXECUTE` on this function; **no** table `INSERT`.

### 7.2 Function contract

**Inputs:** provider, model, case, authorization_id, role, confidentiality, canonical_request JSONB (must include `idempotency_key` for pilot), optional credential claim.

**Validates:** all current preflight gates (provider/model enabled, credential present, auth active & unexpired, pilot approved, bindings, retry/fallback off, confidentiality, cost 0, token/request/success caps including events).

**Writes (atomic):** capacity event + envelope + link.

**Returns:** `{ok, envelope_id, envelope, idempotent_replay}` or `{ok:false, failure_class, detail}` without leaving partial durable writes (exception â†’ rollback).

**Does not:** perform HTTP; set `executable=true`; enable providers; approve pilots; activate auths; touch secrets.

### 7.3 Envelope immutability binding

Envelope JSON must embed: `authorization_id`, `pilot_proposal_id`, `benchmark_case_id`, `idempotency_key`, projected tokens, `live_execution_allowed=false`.
Table CHECK constraints retain `executable=false` and flag consistency.
No UPDATE grants to runtime; existing immutability triggers remain defense in depth.

### 7.4 Non-pilot Round 4 path

Non-pilot envelope creation either:

- remains in the same definer function with a separate branch that does not write pilot events, still without granting table INSERT to app, or
- is frozen until a later round.

Must not re-open pilot bypasses.

---

## 8. Migration sequence from schema version 8

Future implementation round (not this commit) â€” suggested **schema version 9**:

| Step | Action | Restart-safe? |
| --- | --- | --- |
| 9.0 | Create roles if missing (`research_governance`); document password/ops | Yes |
| 9.1 | Create `taha_governance_actions`, `pilot_capacity_events` | `IF NOT EXISTS` |
| 9.2 | Create/replace SECURITY DEFINER functions with fixed `search_path` | `CREATE OR REPLACE` |
| 9.3 | Install owner-only triggers (immutability, reject unauthorized status changes even for owner mistakes) | Yes |
| 9.4 | Backfill: copy any durable reserved rows â†’ events; verify counts | Idempotent upsert by natural key |
| 9.5 | `REVOKE` broad table/function privileges from `research_app` / `n8n_app`; re-grant allowlist | Idempotent REVOKE/GRANT |
| 9.6 | Fix `ALTER DEFAULT PRIVILEGES` for owner | Yes |
| 9.7 | Drop GUC checks from triggers; delete `allow_pilot_activation` usage | Yes |
| 9.8 | `REVOKE EXECUTE` on arm/reset helpers; `DROP FUNCTION` or move to `research_test` | Yes |
| 9.9 | Drop or freeze `pilot_capacity_reservations` | After backfill verify |
| 9.10 | Insert `schema_version=9` | `ON CONFLICT DO NOTHING` |
| 9.11 | Assert: Gemini disabled; 3 proposed production auths; no active pilot auths; credential status unchanged unless governance ran | Fail closed |

Partial failure: each step is transactional where possible; version row inserted only after privilege cutover succeeds. Re-run is safe.

**Compatibility:** Existing three proposed pilot authorization shells remain `proposed` with `expires_at='-infinity'`. No automatic activation. No provider enablement.

---

## 9. Compatibility treatment for existing proposed authorizations

- Keep rows as-is (`proposed`, no `activated_at`).
- They become activatable only after governance confirms credential + approves pilot + calls activate per id.
- Test fixture rows with `test_fixture_id` remain out of production path; cleanup only via owner/test schema functions, not app-callable arm helpers.

---

## 10. Recovery and partial-failure behavior

| Failure | Behavior |
| --- | --- |
| Precondition fail in approve/activate/builder | No durable write; clear error |
| Insert event succeeds, envelope insert fails | Transaction aborts; event rolled back |
| Crash after commit | Event + envelope durable; replay by idempotency key |
| Orphan event without envelope_id | Fail closed on replay; ops inspect (should be impossible if single txn) |
| Mistaken governance approval | Append compensating governance action; revoke/expire via governance functionsâ€”not app UPDATE |
| Need renewal after expiry | Insert **new** authorization record; never reopen old timestamps |

---

## 11. Removal or isolation of test-only helpers

| Symbol | Disposition |
| --- | --- |
| `research._r5a_final_arm_gates` | DROP from `research` **or** move to `research_test` with EXECUTE only for test role |
| `research._r5a_final_reset_defaults` | Same |
| `research._r5a_insert_fixture_auth` | Same |
| `research.cleanup_test_fixture` | Owner/test-only; REVOKE from `research_app` |
| `research.simulate_envelope_insert_failure` GUC | Remove from production builder |
| Adversarial tests | Run as `research_app` expecting permission errors; separate connection as `research_governance` for happy-path governance |

Production migrations must not reinstall app-callable arm helpers.

---

## 12. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Break-glass owner still has UPDATE | Triggers + ops procedure; optional column-level revoke even from non-superuser owners |
| `SECURITY DEFINER` search_path hijack | `SET search_path = research, pg_temp` on every definer function |
| Privilege drift / default privileges re-grant DELETE | Migration asserts + CI permission tests |
| Governance role credential theft | Treat like production DB admin; local-only; no remote grant |
| Dual-count ledger vs events | Document single source of truth for attempts (events); ledger for finalized success only |
| Non-pilot Round 4 callers lose INSERT | Route through definer builder; update adapters/docs |
| Over-tight grants block legitimate Round 2â€“4 writes | Explicit allowlist of tables still writable by app (lifecycle tables unrelated to pilot gates); pilot tables locked |

---

## 13. Exact implementation scope for a later round

**In scope (schema 9):**

1. Roles + privilege cutover + default privileges
2. `taha_governance_actions` + governance functions
3. Append-only `pilot_capacity_events` + builder rewrite
4. Remove GUC activation path
5. REVOKE envelope INSERT; definer-only insert
6. Remove/isolate arm/reset helpers
7. Adversarial tests per `docs/ROUND_5A_SECURITY_BOUNDARY_TEST_PLAN.md`
8. Docs update for ops: how Taha runs governance session

**Out of scope:**

- Creating n8n credentials or API keys
- Approving/activating in the implementation PR itself (leave production pilot proposed)
- Enabling Gemini / model / workflows
- Live HTTP / Round 5B
- Equitify / `ai-development-os`

**Acceptance for implementation round:** Independent review proves all four bypass classes are impossible under `research_app` privileges, not merely â€œtrigger rejected when UPDATE is allowed.â€

---

## Design decisions (summary)

| Topic | Decision |
| --- | --- |
| Trust boundary | Owner-governed writes; app is read + single builder EXECUTE |
| Approval authority | `research_governance` only via `approve_pilot_proposal` + governance action log |
| Activation authority | `research_governance` only via `activate_pilot_authorization`; no GUC |
| Capacity model | Append-only `pilot_capacity_events`; no releasable status |
| Envelope creation | Definer-only insert; app cannot INSERT |
| Application permissions | SELECT on pilot tables; EXECUTE allowlist; no UPDATE/DELETE on gated objects |
