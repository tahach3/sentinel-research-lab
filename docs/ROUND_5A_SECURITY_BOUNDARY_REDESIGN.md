# Round 5A — Security Boundary Redesign (Revision 2)

**Status:** Design only. Not implemented.
**Baseline HEAD:** `3d4464299f2385cd9c813bb8a5d57f46e7ff45b5` (docs) / schema version 8 runtime
**Supersedes:** prior content of this file at that commit
**Scope:** Enforceable privilege, governance, capacity, and envelope boundaries for Gemini pilot + Round 1–4 runtime compatibility.
**Non-goals:** Implementing SQL in this round; storing API keys; Round 5B live HTTP; Equitify/SENTINEL changes.

---

## 1. Threat model (unchanged classes)

Must eliminate at the **privilege and ownership** layer:

1. Session-GUC activation
2. Mutable/deletable capacity evidence
3. Application-callable approval/arm helpers
4. Direct envelope insertion

Adversary: `research_app` / `n8n_app` with any SQL allowed by their grants, including `set_config`, `SET ROLE` attempts, and `PUBLIC` defaults.

---

## 2. Roles and Taha authority

| Role | Kind | Purpose |
| --- | --- | --- |
| `postgres` (lab DB owner / migration role) | Login, object owner | Migrations; owns all `research` objects; sole granter of governance membership |
| `research_governance` | Login, `NOINHERIT` | Taha-controlled governance session only |
| `research_app` | Login | Application / automation runtime |
| `n8n_app` | Login | n8n runtime (read research; own n8n schema) |
| `research_test` | Login, optional, non-prod | Owns `research_test` schema helpers; never granted to app/n8n |
| **Taha** | Human | Sole approval authority; operates as `research_governance` after intentional local login |

Object owner for all security-sensitive `research` tables, views, sequences, triggers, and elevated functions: **`postgres`** (migration/database owner). Do not transfer ownership to `research_app` or `research_governance`.

---

## 3. Role-membership and PUBLIC rules (normative)

1. `research_app` **MUST NOT** be a member of `research_governance`.
2. `n8n_app` **MUST NOT** be a member of `research_governance`.
3. `research_governance` **MUST NOT** be a member of `research_app` or `n8n_app`.
4. Application roles **MUST NOT** be able to `SET ROLE research_governance` (no membership ⇒ denied).
5. Only `postgres` (migration/owner) may `GRANT research_governance TO …`.
6. `research_governance` is created with **`NOINHERIT`**. Membership, if ever granted to a human login role distinct from the governance login, does not auto-activate; operator must `SET ROLE` after intentional switch. Preferred model: humans log in **as** `research_governance` directly; no other role holds membership.
7. Least privilege on all new roles: no superuser, no `CREATEDB`/`CREATEROLE` unless owner.
8. **`PUBLIC` receives no `EXECUTE`** on: governance, activation, credential-confirmation, enablement/disablement, capacity-event writers, or envelope builders.
9. Every newly created function: `REVOKE ALL ON FUNCTION … FROM PUBLIC;` then grant explicitly.
10. `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA research`:
    - Tables: `GRANT SELECT` only to `research_app`, `n8n_app` (no INSERT/UPDATE/DELETE by default)
    - Functions: **revoke** default `EXECUTE` from `PUBLIC` and from `research_app`; no default function grants to app
    - Existing bad default (`research_app=arwdDxt` on tables) **must be dropped** in schema 9 and replaced with the above

Catalog assertion (migration + CI): zero rows where `research_app`/`n8n_app`/`PUBLIC` hold elevated EXECUTE or write on gated objects outside Appendix A.

---

## 4. Provider/model enablement (selected design)

### 4.1 Functions (schema `research`, owner `postgres`, `SECURITY DEFINER`, `SET search_path = research, pg_temp`)

| Function | EXECUTE |
| --- | --- |
| `research.confirm_provider_credential_status(provider_code, n8n_label, note)` | `research_governance` only |
| `research.approve_pilot_proposal(pilot_code)` | `research_governance` only |
| `research.enable_provider_for_pilot(pilot_code, provider_code)` | `research_governance` only |
| `research.enable_model_for_pilot(pilot_code, provider_code, model_id_provisional)` | `research_governance` only |
| `research.disable_provider_for_pilot(pilot_code, provider_code)` | `research_governance` only |
| `research.disable_model_for_pilot(pilot_code, provider_code, model_id_provisional)` | `research_governance` only |
| `research.activate_pilot_authorization(authorization_id, pilot_code)` | `research_governance` only |

`research_governance` has **SELECT only** on `providers`, `provider_model_candidates`, `provider_credential_status`, `provider_pilot_proposals`, `provider_authorization_records`. **No** direct `UPDATE`/`INSERT`/`DELETE` on those tables.

### 4.2 Enablement sequence (chosen — not optional)

```text
1) confirm_provider_credential_status
2) approve_pilot_proposal
3) enable_provider_for_pilot
4) enable_model_for_pilot
5) activate_pilot_authorization  (per authorization row)
6) research_app may call build_provider_request_envelope
```

Provider/model enablement happens **before** authorization activation, never atomically inside activation.

### 4.3 Preconditions for `enable_provider_for_pilot` / `enable_model_for_pilot`

Fail closed; no table mutation on failure:

- Pilot exists; `status = 'approved'`; not expired
- Credential status for provider = `present`
- Provider/model identity matches pilot row exactly
- Matching append-only governance action already recorded for this step **or** the function itself appends the authorizing action in the same transaction (required: function appends `action_type` `provider_enabled_for_pilot` / `model_enabled_for_pilot` with full material fingerprint)
- Pilot cost = 0; retries false; fallback false; confidentiality = `public_or_synthetic`
- Validity: enablement authorization expires at `min(pilot.expires_at, now() + pilot.expiry_hours_after_approval)` recorded on the governance action

Effects: set `providers.enabled` / `provider_model_candidates.enabled` (+ verification fields as specified in function contract) **only** for the bound IDs; append governance action; never activate authorizations; never create credentials; never set paid flags.

Disable functions clear `enabled=false` and append `provider_disabled_for_pilot` / `model_disabled_for_pilot`.

---

## 5. `taha_governance_actions` schema (normative)

```text
research.taha_governance_actions (
  governance_action_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  action_type            TEXT NOT NULL,
  proposal_id            UUID NULL REFERENCES research.provider_pilot_proposals(id),
  authorization_id       UUID NULL REFERENCES research.provider_authorization_records(id),
  provider_id            UUID NULL REFERENCES research.providers(id),
  model_id               UUID NULL REFERENCES research.provider_model_candidates(id),
  decision_value         TEXT NOT NULL,
  authority_identifier   TEXT NOT NULL CHECK (authority_identifier = 'Taha'),
  material_fingerprint   TEXT NOT NULL CHECK (length(material_fingerprint) = 64),
  previous_action_id     UUID NULL REFERENCES research.taha_governance_actions(governance_action_id),
  issued_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at             TIMESTAMPTZ NULL,
  status                 TEXT NOT NULL CHECK (status IN (
                           'active','superseded','revoked','expired','rejected'
                         )),
  recorded_by_role       TEXT NOT NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload                JSONB NOT NULL DEFAULT '{}'::jsonb
)
```

**Allowed `action_type` values (closed set):**
`credential_confirmed`, `pilot_approved`, `pilot_approval_revoked`, `provider_enabled_for_pilot`, `provider_disabled_for_pilot`, `model_enabled_for_pilot`, `model_disabled_for_pilot`, `authorization_activated`, `accounting_discrepancy`, `governance_rejected`.

### 5.1 Material fingerprint

`material_fingerprint = sha256_hex(canonical_json)` over exactly these fields (sorted keys, no secrets):

- `pilot_code`, `proposal_id`, `provider_code`, `model_id_provisional`
- `benchmark_case_ids` (ordered), `benchmark_case_codes` (ordered)
- `max_successful_calls`, `max_attempts_per_case`, `max_total_requests`
- `max_total_input_tokens`, `max_total_output_tokens`, `max_authorized_cost_usd`
- `retries_allowed`, `fallback_provider_allowed`, `confidentiality_class`
- `expiry_hours_after_approval`, `authority_identifier`
- `action_type`, `decision_value`

Altered proposal content, provider/model binding, limits, policies, or validity ⇒ different fingerprint ⇒ prior `active` approval **does not** authorize the new material.

### 5.2 Uniqueness and validation rules

| Situation | Rule |
| --- | --- |
| Duplicate identical approval | Second insert with same `(action_type, proposal_id, material_fingerprint)` while first `status='active'` → reject |
| Copied approval (same fingerprint, new id) | Reject if active row with same fingerprint+action_type+proposal exists |
| Stale approval | `expires_at < now()` → treat as `expired`; cannot authorize enable/activate |
| Altered proposal after approval | New fingerprint required; old active approval must be `superseded` or `revoked` before new approve |
| Altered model/provider binding | Fingerprint mismatch → enable/activate fail closed |
| Superseded | New approve sets prior active approve for same proposal to `superseded` and sets `previous_action_id` |
| Revoked | `pilot_approval_revoked` sets prior approve to `revoked`; enable/activate forbidden |
| Expired | Time-based; enable/activate forbidden |
| Conflicting decisions | Cannot have two `active` rows for same `(proposal_id, action_type)` with different fingerprints |

Privileges: `research_app` / `n8n_app` / `PUBLIC` → **SELECT only** (or none for payload if desired; SELECT allowed for audit). **No INSERT/UPDATE/DELETE.** Writes only inside owner `SECURITY DEFINER` governance functions.

No GUC, mutable boolean, free-text name match, or application-supplied authority string is proof of approval.

---

## 6. Activation (normative)

`research.activate_pilot_authorization` — governance-only, `SECURITY DEFINER`, fixed `search_path`.

Requires, else no mutation:

- Auth `proposed`, `activated_at IS NULL`
- Pilot `approved`, not expired, fingerprint-consistent with active `pilot_approved` action
- Credential `present`
- Provider and model **already enabled** via prior governance enable actions still `active`
- Exact provider/model/case/authority bindings
- No GUC involved (GUC path removed from triggers entirely)

Sets immutable `activated_at`, `expires_at = activated_at + 24 hours`, status `active`; appends `authorization_activated`.
Rejects in-place renewal; renewal = **new** authorization row inserted only by owner/migration or a future governance `propose_pilot_authorization` (out of schema-9 minimum: migration seeds only; app cannot INSERT auth rows).

---

## 7. Capacity accounting — one source of truth each

### 7.1 Table `research.pilot_capacity_events` (append-only)

```text
id UUID PK
pilot_proposal_id UUID NOT NULL
authorization_id UUID NOT NULL
benchmark_case_id UUID NOT NULL
event_type TEXT NOT NULL CHECK (event_type = 'attempt_consumed')
idempotency_key TEXT NOT NULL
projected_input_tokens INT NOT NULL CHECK (>=0)
projected_output_tokens INT NOT NULL CHECK (>=0)
projected_cost_usd NUMERIC NOT NULL CHECK (=0)
envelope_id UUID NOT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE (pilot_proposal_id, idempotency_key)
UNIQUE (pilot_proposal_id, benchmark_case_id)
```

**Single event type:** `attempt_consumed` only. No `idempotency_bound`.

### 7.2 Metric authorities (exclusive — never add two sources)

| Metric | Authoritative source | Rule |
| --- | --- | --- |
| Total requests | `COUNT(*)` of `attempt_consumed` for pilot | One event = one request slot |
| Attempts per case | Unique `(pilot, case)` on events | Second insert fails |
| Input tokens (limits) | `SUM(projected_input_tokens)` of events | Ledger tokens not added |
| Output tokens (limits) | `SUM(projected_output_tokens)` of events | Ledger tokens not added |
| Cost (limits) | Events require `projected_cost_usd=0`; proposal/auth max cost = 0 | Any ledger `estimated_cost_usd > 0` for pilot → fail closed + `accounting_discrepancy` action |
| Successful calls | `COUNT(*)` of `provider_usage_ledger` rows where `pilot_proposal_id` set AND `success IS TRUE` AND `test_fixture_id IS NULL` | **Ledger is authoritative for success only**; events never count as success |

`provider_usage_ledger.request_count` for pilot-linked rows is **reporting-only**. Aggregate request enforcement **MUST NEVER** compute `events + ledger.request_count`.

### 7.3 Permanent consumption

Failed, abandoned, rejected-after-reservation, and completed attempts remain consumed once `attempt_consumed` exists. Capacity never reopens.

### 7.4 Insert ordering (no post-insert UPDATE)

Preferred and required:

1. Lock pilot `FOR UPDATE`; lock auth `FOR UPDATE`
2. Idempotency lookup
3. Validate limits using events (+ success from ledger)
4. `envelope_id := gen_random_uuid()`
5. `INSERT pilot_capacity_events (…, envelope_id)` with final id
6. `INSERT live_request_envelopes (id := envelope_id, …)`
7. Commit

No `envelope_id` NULL→value update path.

Defense in depth: `BEFORE UPDATE OR DELETE` on `pilot_capacity_events` ⇒ always raise (even for owner mistakes except migration under explicit session). Owner break-glass documented separately.

### 7.5 Legacy reconciliation

On builder/preflight, if for a pilot:

- `SUM(ledger.request_count) WHERE pilot_proposal_id = P` > `COUNT(events)` for P, **or**
- ledger shows success count > events count, **or**
- ledger token sums exceed event projected sums without matching events

⇒ fail closed; append `accounting_discrepancy` via governance-only reporter function `research.record_accounting_discrepancy` (EXECUTE: governance + owner); do not create envelopes.

Backfill (migration 9): convert each durable `pilot_capacity_reservations` row with `status IN ('reserved','finalized')` and non-null `envelope_id` into one `attempt_consumed` event; then freeze/drop reservations table.

---

## 8. Envelope creation

### 8.1 Pilot path

`research.build_provider_request_envelope` — `SECURITY DEFINER`, owner `postgres`, fixed `search_path`, `EXECUTE` to `research_app` (and optionally governance).
Revoke direct `INSERT` on `live_request_envelopes` from app/n8n/PUBLIC.

### 8.2 Round 4 compatibility (chosen — not optional)

**Route non-pilot callers through a separate controlled builder:**

`research.build_non_pilot_request_envelope(...)`
— same argument list as the pilot builder
— `SECURITY DEFINER`, fixed `search_path`
— `EXECUTE`: `research_app`
— Requires authorization `pilot_proposal_id IS NULL`
— Does **not** write `pilot_capacity_events`
— Still enforces Round 4 live_preflight gates
— Direct table `INSERT` remains revoked

Existing Round 4 flows continue by calling this function (adapters/docs updated in implementation round). Pilot-linked auths must use `build_provider_request_envelope` only; wrong function fails closed.

---

## 9. Helper isolation (complete inventory)

| Symbol | Classification |
| --- | --- |
| `_r4_arm_provider` | Move to `research_test`; DROP from `research` |
| `_r4_reset_defaults` | Move to `research_test`; DROP from `research` |
| `_r4_case_id` | Move to `research_test`; DROP from `research` |
| `_r4_make_auth` | Move to `research_test`; DROP from `research` |
| `_r5a_arm_for_pilot_tests` | Move to `research_test`; DROP from `research` |
| `_r5a_repair_reset_defaults` | Move to `research_test`; DROP from `research` |
| `_r5a_final_arm_gates` | Move to `research_test`; DROP from `research` |
| `_r5a_final_reset_defaults` | Move to `research_test`; DROP from `research` |
| `_r5a_final_assert_state` | Move to `research_test`; DROP from `research` |
| `_r5a_assert_final_pilot_state` | Move to `research_test`; DROP from `research` |
| `_r5a_insert_fixture_auth` | Move to `research_test`; DROP from `research` |
| `_r3_clone_question` | Move to `research_test`; DROP from `research` |
| `_r3_new_run` | Move to `research_test`; DROP from `research` |
| `cleanup_test_fixture` | Move to `research_test`; DROP from `research` |
| `record_pilot_usage_for_tests` | Move to `research_test`; DROP from `research` |
| `simulate_envelope_insert_failure` GUC usage | Remove from production builders |

`research_test` schema: owned by `research_test` role; **no** `USAGE`/`EXECUTE` for `research_app`, `n8n_app`, or `research_governance`.

---

## 10. Migration 8 → 9 (summary)

1. Create `research_governance` (`NOINHERIT`), optional `research_test`
2. Create `taha_governance_actions`, `pilot_capacity_events`
3. Create/replace governance + builder DEFINER functions; `REVOKE FROM PUBLIC`
4. Drop GUC from authorization trigger
5. Backfill reservations → events; freeze/drop `pilot_capacity_reservations`
6. Move helpers to `research_test` / DROP from `research`
7. `REVOKE ALL` on gated tables/functions from app/n8n/PUBLIC; apply **Appendix A** grants exactly
8. Replace `ALTER DEFAULT PRIVILEGES` for `postgres` in `research`
9. Assert membership matrix, Gemini disabled, 3 proposed pilot auths, version 9
10. Restart-safe / idempotent; version row only after privilege cutover succeeds

No accidental approve/activate/enable/credential in migration.

---

## 11. Design decisions (locked)

| Topic | Decision |
| --- | --- |
| Enablement sequence | Credential → approve → enable provider → enable model → activate → build |
| Total request authority | `pilot_capacity_events` count only |
| Successful-call authority | Finalized non-fixture `provider_usage_ledger.success` |
| Token authority | Event projected sums only |
| Cost authority | Event projected cost must be 0 (+ proposal/auth max 0); ledger cost >0 fails closed |
| Non-pilot envelope path | `build_non_pilot_request_envelope` SECURITY DEFINER |
| Append-only link | Pre-generate `envelope_id`; no post-insert UPDATE |

---

## Appendix A — Machine-exact `research_app` allowlist

**Owner column:** `postgres` for all objects below.
**Rule:** Any `research` object not listed is **denied** to `research_app` (no privilege).
**n8n_app:** SELECT on the same tables/views listed with SELECT=Y; no INSERT/UPDATE/DELETE/EXECUTE on research elevated functions (see Appendix B).

### A.1 Tables and views

| Object | Type | Owner | SELECT | INSERT | UPDATE | DELETE | EXECUTE | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| automatic_scores | table | postgres | Y | Y | Y | N | — | Round 1 scoring writes |
| benchmark_cases | table | postgres | Y | N | N | N | — | Read cases |
| benchmark_runs | table | postgres | Y | Y | Y | N | — | Round 1 runs |
| benchmark_suites | table | postgres | Y | N | N | N | — | Read suites |
| decision_rationales | table | postgres | Y | Y | N | N | — | Append rationales |
| evidence_claim_links | table | postgres | Y | Y | N | N | — | Lifecycle links |
| evidence_items | table | postgres | Y | Y | N | N | — | Append evidence |
| gemini_pilot_request_builder_specs | table | postgres | Y | N | N | N | — | Read-only specs |
| improvement_proposals | table | postgres | Y | Y | Y | N | — | Lifecycle proposals |
| live_request_envelopes | table | postgres | Y | N | N | N | — | Read only; insert via DEFINER |
| model_outputs | table | postgres | Y | Y | N | N | — | Orchestration outputs |
| models | table | postgres | Y | N | N | N | — | Read registry |
| monthly_role_rankings | table | postgres | Y | Y | N | N | — | Rankings |
| orchestration_failures | table | postgres | Y | Y | N | N | — | Orchestration |
| pilot_capacity_reservations | table | postgres | N | N | N | N | — | Deprecated; freeze then drop |
| pilot_capacity_events | table | postgres | Y | N | N | N | — | Read quotas; write via DEFINER |
| proposal_versions | table | postgres | Y | Y | N | N | — | Version append |
| provider_adapter_requests | table | postgres | Y | Y | N | N | — | Mock/live prep |
| provider_adapter_responses | table | postgres | Y | Y | N | N | — | Fixture responses |
| provider_adapter_versions | table | postgres | Y | N | N | N | — | Read |
| provider_authorization_records | table | postgres | Y | N | N | N | — | Gated |
| provider_budget_policies | table | postgres | Y | N | N | N | — | Gated |
| provider_capabilities | table | postgres | Y | N | N | N | — | Read |
| provider_credential_status | table | postgres | Y | N | N | N | — | Gated |
| provider_health_checks | table | postgres | Y | Y | N | N | — | Registry health rows |
| provider_model_candidates | table | postgres | Y | N | N | N | — | Gated |
| provider_pilot_proposals | table | postgres | Y | N | N | N | — | Gated |
| provider_policy_verifications | table | postgres | Y | N | N | N | — | Read |
| provider_rate_limit_policies | table | postgres | Y | N | N | N | — | Read |
| provider_usage_ledger | table | postgres | Y | N | N | N | — | Read; insert via DEFINER spend/success paths |
| providers | table | postgres | Y | N | N | N | — | Gated |
| question_status_transitions | table | postgres | Y | N | N | N | — | Read transition rules |
| reconsideration_conditions | table | postgres | Y | Y | Y | N | — | Lifecycle |
| repair_attempts | table | postgres | Y | Y | N | N | — | Repair log |
| research_closure_records | table | postgres | Y | Y | N | N | — | Closures |
| research_findings | table | postgres | Y | Y | N | N | — | Findings |
| research_priorities | table | postgres | Y | Y | Y | N | — | Priorities |
| research_question_relationships | table | postgres | Y | Y | N | N | — | Relationships |
| research_question_versions | table | postgres | Y | Y | N | N | — | Versions |
| research_questions | table | postgres | Y | Y | Y | N | — | Lifecycle core |
| research_run_stages | table | postgres | Y | Y | Y | N | — | Orchestration |
| research_runs | table | postgres | Y | Y | Y | N | — | Orchestration |
| research_status_history | table | postgres | Y | Y | N | N | — | History append |
| run_failures | table | postgres | Y | Y | N | N | — | Failures |
| schema_version | table | postgres | Y | N | N | N | — | Read |
| source_snapshots | table | postgres | Y | Y | N | N | — | Snapshots |
| sources | table | postgres | Y | Y | N | N | — | Sources |
| taha_decisions | table | postgres | Y | Y | N | N | — | Decisions |
| taha_governance_actions | table | postgres | Y | N | N | N | — | Audit read |
| taha_scores | table | postgres | Y | Y | N | N | — | Scores |
| v_active_research_queue | view | postgres | Y | — | — | — | — | Reporting |
| v_cost_per_successful_run | view | postgres | Y | — | — | — | — | Reporting |
| v_decision_history_by_topic | view | postgres | Y | — | — | — | — | Reporting |
| v_duplicate_question_warnings | view | postgres | Y | — | — | — | — | Reporting |
| v_enabled_provider_readiness | view | postgres | Y | — | — | — | — | Reporting |
| v_failure_rate | view | postgres | Y | — | — | — | — | Reporting |
| v_gemini_pilot_5a | view | postgres | Y | — | — | — | — | Reporting |
| v_highest_priority_unanswered | view | postgres | Y | — | — | — | — | Reporting |
| v_insufficient_evidence_warning | view | postgres | Y | — | — | — | — | Reporting |
| v_latency_percentile_summary | view | postgres | Y | — | — | — | — | Reporting |
| v_latest_monthly_ranking | view | postgres | Y | — | — | — | — | Reporting |
| v_missing_credentials | view | postgres | Y | — | — | — | — | Reporting |
| v_models_awaiting_verification | view | postgres | Y | — | — | — | — | Reporting |
| v_proposals_awaiting_taha | view | postgres | Y | — | — | — | — | Reporting |
| v_provider_health_summary | view | postgres | Y | — | — | — | — | Reporting |
| v_provider_performance_by_role | view | postgres | Y | — | — | — | — | Reporting |
| v_questions_blocked_missing_evidence | view | postgres | Y | — | — | — | — | Reporting |
| v_rejected_eligible_reconsideration | view | postgres | Y | — | — | — | — | Reporting |
| v_remaining_daily_quota | view | postgres | Y | — | — | — | — | Reporting |
| v_remaining_monthly_budget | view | postgres | Y | — | — | — | — | Reporting |
| v_settled_questions | view | postgres | Y | — | — | — | — | Reporting |
| v_simulated_decision_cards | view | postgres | Y | — | — | — | — | Reporting |
| v_unauthorized_call_warnings | view | postgres | Y | — | — | — | — | Reporting |

Sequences: grant `USAGE, SELECT` on sequences owned by tables with INSERT=Y above; no sequence grants for gated tables.

Schema: `GRANT USAGE ON SCHEMA research TO research_app, n8n_app, research_governance`.

### A.2 Functions — classification and `research_app` EXECUTE

| Object | Classification | research_app EXECUTE | Reason |
| --- | --- | --- | --- |
| `_allowed_source_ids(uuid)` | runtime allowlisted | Y | Orchestration helper |
| `_append_completed_stage(uuid,text)` | runtime allowlisted | Y | Orchestration helper |
| `_evidence_bundle_for_question(uuid)` | runtime allowlisted | Y | Orchestration helper |
| `_record_failure(uuid,text,text,text)` | runtime allowlisted | Y | Orchestration helper |
| `_r3_clone_question` | test-only | N | Moved to research_test |
| `_r3_new_run` | test-only | N | Moved to research_test |
| `_r4_arm_provider` | test-only | N | Moved to research_test |
| `_r4_case_id` | test-only | N | Moved to research_test |
| `_r4_make_auth` | test-only | N | Moved to research_test |
| `_r4_reset_defaults` | test-only | N | Moved to research_test |
| `_r5a_arm_for_pilot_tests` | test-only | N | Moved to research_test |
| `_r5a_assert_final_pilot_state` | test-only | N | Moved to research_test |
| `_r5a_final_arm_gates` | test-only | N | Moved to research_test |
| `_r5a_final_assert_state` | test-only | N | Moved to research_test |
| `_r5a_final_reset_defaults` | test-only | N | Moved to research_test |
| `_r5a_insert_fixture_auth` | test-only | N | Moved to research_test |
| `_r5a_repair_reset_defaults` | test-only | N | Moved to research_test |
| `activate_pilot_authorization` | governance-only | N | Taha activation |
| `approve_pilot_proposal` | governance-only | N | New; Taha approval |
| `build_decision_card(uuid)` | runtime allowlisted | Y | Round 3 |
| `build_provider_request_envelope(...)` | runtime allowlisted DEFINER | Y | Pilot envelopes |
| `build_non_pilot_request_envelope(...)` | runtime allowlisted DEFINER | Y | Round 4 path |
| `cancel_research_run(uuid,text)` | runtime allowlisted | Y | Round 3 |
| `cleanup_test_fixture` | test-only | N | research_test |
| `compute_priority_v1(...)` | runtime allowlisted | Y | Priority |
| `confirm_provider_credential_status(...)` | governance-only | N | Credential confirm |
| `disable_model_for_pilot(...)` | governance-only | N | Enablement pair |
| `disable_provider_for_pilot(...)` | governance-only | N | Enablement pair |
| `enable_model_for_pilot(...)` | governance-only | N | Enablement |
| `enable_provider_for_pilot(...)` | governance-only | N | Enablement |
| `enforce_completed_run_evidence()` | owner/migration-only (trigger) | N | Trigger fn |
| `estimate_provider_cost_usd(...)` | runtime allowlisted | Y | Cost estimate read |
| `forbid_mutation()` | owner/migration-only (trigger) | N | Trigger fn |
| `forbid_terminal_run_wipe()` | owner/migration-only (trigger) | N | Trigger fn |
| `gemini_pilot_5a_gate_status()` | read-only reporting | Y | Status report |
| `live_preflight(...)` | runtime allowlisted | Y | Gates |
| `materialize_proposal_from_run(uuid)` | runtime allowlisted | Y | Round 3 |
| `mock_adapter_invoke(uuid)` | runtime allowlisted | Y | Round 3 mock |
| `mock_model_for_stage(text)` | runtime allowlisted | Y | Round 3 mock |
| `mock_provider_for_stage(text)` | runtime allowlisted | Y | Round 3 mock |
| `orchestrate_research_run(uuid)` | runtime allowlisted | Y | Round 3 |
| `parse_provider_fixture_response(text,jsonb)` | runtime allowlisted | Y | Round 4 fixtures |
| `pilot_capacity_snapshot(uuid)` | read-only reporting | Y | Quota read |
| `pilot_case_attempt_count(uuid,uuid)` | read-only reporting | Y | Attempt read |
| `proposal_has_evidence(uuid[])` | runtime allowlisted | Y | Lifecycle |
| `record_accounting_discrepancy(...)` | governance-only | N | Fail-closed audit |
| `record_authorization_spend(...)` | runtime allowlisted DEFINER | Y | Round 4 non-pilot spend only; **rejects pilot_proposal_id IS NOT NULL** |
| `record_pilot_usage_for_tests(...)` | test-only | N | research_test |
| `run_stage(...)` | runtime allowlisted | Y | Round 3 |
| `sha256_hex(text)` | runtime allowlisted | Y | Hashing |
| `trg_authorization_validity_guard()` | owner/migration-only | N | Trigger |
| `trg_block_evidence_delete_after_decision()` | owner/migration-only | N | Trigger |
| `trg_envelope_immutability()` | owner/migration-only | N | Trigger |
| `trg_evidence_immutable_body()` | owner/migration-only | N | Trigger |
| `trg_proposal_ready_requires_evidence()` | owner/migration-only | N | Trigger |
| `trg_question_decision_requires_supported_proposal()` | owner/migration-only | N | Trigger |
| `trg_question_status_change()` | owner/migration-only | N | Trigger |
| `trg_question_status_history()` | owner/migration-only | N | Trigger |
| `trg_question_status_validate()` | owner/migration-only | N | Trigger |
| `trg_run_stage_immutable()` | owner/migration-only | N | Trigger |
| `trg_set_priority_scores()` | owner/migration-only | N | Trigger |
| `trg_sync_question_priority()` | owner/migration-only | N | Trigger |
| `trg_usage_ledger_immutability()` | owner/migration-only | N | Trigger |
| `try_enter_decision_from_partial(uuid)` | runtime allowlisted | Y | Round 3 |

`PUBLIC EXECUTE`: **N** for every function in this appendix.

---

## Appendix B — `n8n_app` and `research_governance` grants

| Role | Tables/views | Functions |
| --- | --- | --- |
| `n8n_app` | SELECT where Appendix A SELECT=Y | **No** EXECUTE on any research function listed above |
| `research_governance` | SELECT on all research tables/views needed for ops (same SELECT set as app + gated tables) | EXECUTE only governance-only + read-only reporting functions; **not** arm/test helpers; **not** `build_*` required (optional GRANT for diagnostics) |

---

## Appendix C — Open risks (accepted)

- Owner/`postgres` break-glass UPDATE still possible; mitigated by immutability triggers + ops procedure.
- Human theft of `research_governance` login equals full governance power; keep local-only.
- Round 4 adapters must be pointed at `build_non_pilot_request_envelope` in the implementation round.
