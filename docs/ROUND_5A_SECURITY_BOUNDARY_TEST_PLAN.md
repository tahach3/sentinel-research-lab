# Round 5A â€” Security Boundary Test Plan

**Status:** Design only. Tests are specified for a future implementation round (schema â‰¥ 9).
**Baseline:** redesign in `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md` against HEAD `7df8385â€¦` / schema 8.
**Rule:** Adversarial cases run as role `research_app` (and `n8n_app` where noted). Happy-path governance runs as `research_governance` inside rollback-safe transactions unless explicitly testing durable migration asserts.
**Forbidden during testing:** live HTTP, real Gemini calls, creating n8n credential secrets, enabling production Gemini permanently, pushing, touching Equitify/SENTINEL.

---

## 1. Roles and fixtures

| Actor | Connection |
| --- | --- |
| `APP` | `SET ROLE research_app` (or login as `research_app`) |
| `GOV` | `SET ROLE research_governance` |
| `OWN` | migration owner / `postgres` (permission drift checks only) |
| `N8N` | `n8n_app` |

**Fixtures (transaction-local where possible):**

- Use dedicated `test_run_id` / rows in `research_test` if present.
- Do not leave production `GEMINI-PILOT-5A` authorizations active after tests.
- Prefer `BEGIN â€¦ ROLLBACK` for governance happy paths that would otherwise approve/activate.

**Production invariants to re-assert after every suite:**

- Gemini `enabled=false`
- `gemini-2.5-flash` `enabled=false`
- Exactly 3 production proposed pilot auths (`test_fixture_id IS NULL`)
- 0 active pilot-linked auths
- `n8n.credentials_entity` count = 0
- 0 active workflows
- Pilot status remains `awaiting_taha_credential` unless a documented governance test rolled back

---

## 2. Adversarial matrix â€” `research_app` must fail

Each case: expect **permission denied** and/or **function execute privilege** error, or builder `ok=false` without durable bypass. No capacity restore, no activation, no approval.

| ID | Attack | Expect |
| --- | --- | --- |
| A01 | `SELECT set_config('research.allow_pilot_activation','on',true);` then `UPDATE provider_authorization_records SET status='active'` on pilot-linked proposed row | UPDATE fails (no privilege) and/or GUC path absent; row stays `proposed` |
| A02 | Direct `UPDATE ... SET status='active'` without GUC | Permission denied |
| A03 | `UPDATE ... SET activated_at` / `expires_at` on any auth | Permission denied |
| A04 | `UPDATE provider_pilot_proposals SET status='approved'` | Permission denied |
| A05 | `UPDATE provider_credential_status SET status='present'` | Permission denied |
| A06 | `UPDATE providers SET enabled=true WHERE code='gemini'` | Permission denied |
| A07 | `UPDATE provider_model_candidates SET enabled=true` for `gemini-2.5-flash` | Permission denied |
| A08 | `SELECT research._r5a_final_arm_gates()` | Execute privilege revoked / function absent from `research` |
| A09 | `SELECT research._r5a_final_reset_defaults()` | Same as A08 |
| A10 | `SELECT research.approve_pilot_proposal('GEMINI-PILOT-5A')` | Execute denied |
| A11 | `SELECT research.activate_pilot_authorization(<id>,'GEMINI-PILOT-5A')` | Execute denied |
| A12 | `SELECT research.confirm_provider_credential_status(...)` | Execute denied |
| A13 | `UPDATE pilot_capacity_events` (or legacy reservations) SET tokens/status | Permission denied / table gone |
| A14 | `DELETE FROM pilot_capacity_events` (or legacy reservations) | Permission denied |
| A15 | Attempt to â€œreleaseâ€ capacity via any status column | Impossible (no status) or denied |
| A16 | `INSERT INTO live_request_envelopes (...)` | Permission denied |
| A17 | `UPDATE` / `DELETE` on `live_request_envelopes` | Permission denied |
| A18 | After GOV creates an `attempt_consumed` event in a setup txn, APP tries to delete/update it then call builder with new idempotency key for same case | Mutation denied; second attempt still blocked |
| A19 | Call any remaining `research.cleanup_test_fixture` / fixture insert helpers | Execute denied for APP |
| A20 | `INSERT INTO taha_governance_actions` | Permission denied |

---

## 3. Governance happy path (rollback-safe)

Run as `GOV` inside `BEGIN` â€¦ `ROLLBACK` (or ephemeral pilot clone if required):

| ID | Check |
| --- | --- |
| G01 | Confirm credential status â†’ `present` + governance action row; no secret fields |
| G02 | Approve pilot â†’ `approved`; proposal-only change; provider/model still disabled |
| G03 | Activate one fixture/proposed auth â†’ immutable `activated_at`; `expires_at = activated_at + 24 hours` |
| G04 | Activation does not change proposal status |
| G05 | Second activate on same row fails |
| G06 | `active`â†’`proposed` fails |
| G07 | Expired/revoked â†’ `active` fails; renewal requires new row |
| G08 | Activate while proposal not approved fails; rows unchanged |
| G09 | Activate while credential not `present` fails; rows unchanged |

---

## 4. Builder, capacity, concurrency, idempotency

Setup: GOV prepares approved pilot + active fixture auth + enabled flags **only inside rolled-back or disposable fixture**, OR use `research_test` harness that never touches production shells.

| ID | Check |
| --- | --- |
| B01 | First `build_provider_request_envelope` inserts one `attempt_consumed` + one envelope atomically |
| B02 | Replay same `idempotency_key` returns same `envelope_id`; event count unchanged |
| B03 | Different key, same case â†’ blocked (unique / quota) |
| B04 | Fourth total request blocked |
| B05 | Aggregate input 8000 / output 4000 include events |
| B06 | Success-call cap from finalized ledger only |
| B07 | `projected_cost_usd > 0` blocked; no event/envelope |
| B08 | Retry / fallback / confidential input blocked; no event/envelope |
| B09 | Simulated mid-function failure after event insert rolls back both event and envelope |
| B10 | Two concurrent APP sessions competing for last slot â†’ exactly one success, one failure, no over-capacity |
| B11 | APP cannot create envelope when auth proposed / provider disabled |
| B12 | Malformed/null projected tokens / missing idempotency key fail closed |

---

## 5. Migration, privileges, definer safety

| ID | Check |
| --- | --- |
| M01 | Migration 009 re-run is restart-safe (version 9 present â†’ skip or no-op) |
| M02 | Abort mid-migration (savepoint/simulated) leaves either pre-9 or consistent post-9; no half-open GRANT to APP for INSERT on envelopes |
| M03 | Permission drift query: APP lacks INSERT/UPDATE/DELETE on gated tables |
| M04 | `ALTER DEFAULT PRIVILEGES` for owner no longer grants table WRITE to `research_app` |
| M05 | All `SECURITY DEFINER` pilot functions show `prosecdef` and `proconfig` contains `search_path=research, pg_temp` (or equivalent) |
| M06 | Function owners are migration owner, not `research_app` |
| M07 | REVOKE/GRANT regression snapshot matches allowlist file committed with implementation |
| M08 | No `research.allow_pilot_activation` references in `pg_proc` source |
| M09 | Arm/reset helpers absent from `research` or non-executable by APP/N8N |
| M10 | Append-only: even OWN trigger rejects `UPDATE`/`DELETE` on non-test capacity events (defense in depth) |
| M11 | Immutable activation timestamps under OWN attempted slide â†’ rejected |
| M12 | Exact 24-hour expiry equality check |
| M13 | Zero-cost constraints on events and pilot proposal |
| M14 | Confidential-input blocking still in preflight/builder |
| M15 | After full suite: provider/model disabled; 3 proposed; 0 active pilot; 0 credentials; 0 active workflows |

---

## 6. n8n role checks

| ID | Check |
| --- | --- |
| N01 | `n8n_app` SELECT works on needed research tables |
| N02 | `n8n_app` cannot EXECUTE governance or builder functions |
| N03 | `n8n_app` cannot INSERT envelopes or capacity events |

---

## 7. Evidence standard

Treat automated tests as **evidence**, not proof. Each implementation PR must also include:

1. SQL privilege dump (`information_schema.role_table_grants` / `role_routine_grants`) for gated objects.
2. One manual transcript of A01â€“A02 as `research_app`.
3. Concurrent B10 output showing 1 ok / 1 blocked.
4. Post-condition invariant query results.

---

## 8. Pass criteria for implementation round

`PASS` only if:

- All four original bypass classes fail under `research_app` **because of missing privileges** (and definer allowlist), not solely because a trigger raised while UPDATE remained granted.
- Capacity cannot be restored by APP mutation or delete.
- No session-GUC activation path exists in code or catalogs.
- Arm/reset helpers are not APP-callable.
- Direct envelope INSERT is denied to APP.
- Production Gemini remains disabled; no live calls; no paid usage; no credential objects created by tests.

---

## 9. Mapping to Codex defects

| Codex defect | Tests |
| --- | --- |
| GUC activation | A01, M08, G03â€“G09 |
| Mutable reservation capacity | A13â€“A15, A18, B01â€“B10, M10 |
| Arm/reset helpers | A08â€“A09, M09 |
| Direct envelope insert | A16â€“A17, B01, N03 |
