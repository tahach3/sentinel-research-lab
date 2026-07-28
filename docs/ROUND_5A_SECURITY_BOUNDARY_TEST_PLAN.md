# Round 5A — Security Boundary Test Plan (Revision 3)

**Status:** Design only. For schema ≥ 9 implementation.
**Baseline design:** `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md` (Revision 3)
**Actors:** `APP`=`research_app`, `GOV`=`research_governance`, `N8N`=`n8n_app`, `OWN`=`postgres`, `TEST`=`research_test`
**Rule:** Adversarial cases expect permission denied / execute denied / fail-closed builder errors. Governance happy paths use `BEGIN…ROLLBACK` or `research_test` fixtures that never leave production pilot active/enabled.

Production invariants after every suite:

- Gemini disabled; `gemini-2.5-flash` disabled
- 3 proposed production pilot auths; 0 active pilot auths
- 0 n8n credentials; 0 active workflows
- Pilot `awaiting_taha_credential` unless rolled back
- Zero HTTP or model calls

---

## 1. Role membership and PUBLIC (R)

| ID | Probe | Expect |
| --- | --- | --- |
| R01 | `APP` is member of `research_governance` | False |
| R02 | `N8N` is member of `research_governance` | False |
| R03 | `GOV` is member of `research_app` | False |
| R04 | As `APP`: `SET ROLE research_governance` | Fail |
| R05 | As `N8N`: `SET ROLE research_governance` | Fail |
| R06 | `GOV` has `rolinherit = false` (NOINHERIT) | True |
| R07 | Only `OWN` can `GRANT research_governance TO …` | Documented + attempted grant as APP fails |
| R08 | `PUBLIC` has EXECUTE on any governance/enable/activate/confirm/builder/capacity/discrepancy function | Zero |
| R09 | New function created in migration path has PUBLIC EXECUTE revoked | Assert in M-suite |
| R10 | Default privileges for `postgres` in `research` grant NONE on future TABLES/FUNCTIONS/SEQUENCES to PUBLIC/APP/N8N/GOV | Catalog assert |
| R11 | `APP`/`N8N`/`GOV`/`TEST`/`PUBLIC` hold CREATE on schema `research` | False for each |
| R12 | `TEST` holds USAGE+CREATE on schema `research_test` only; NO USAGE and NO CREATE on schema `research` | CREATE research=false; research USAGE=false; research_test USAGE+CREATE=true |

---

## 2. Allowlist completeness (L)

| ID | Probe | Expect |
| --- | --- | --- |
| L01 | Every Appendix A table privilege for APP matches catalog | Exact match |
| L02 | Every research table/view **not** in Appendix A has no APP privileges | Denied |
| L03 | Every Appendix A.4 function with research_app EXECUTE=Y is executable by APP | Succeeds (call smoke) |
| L04 | Every research function with research_app EXECUTE=N fails EXECUTE for APP | Denied |
| L05 | Non-allowlisted sample: `activate_pilot_authorization`, `enable_provider_for_pilot`, `_r4_arm_provider` | Denied for APP |
| L06 | Permission-drift CI query fails build on mismatch | Drift detected |
| L07 | Sequence inventory: zero sequences in `research` at schema 8/9 baseline; any future sequence ACL = NONE for APP/N8N/GOV/PUBLIC | Exact |
| L08 | Every function overload signature in Appendix A.4 present with exact identity arguments | Exact match |

---

## 3. Application cannot govern or mutate gates (A)

| ID | Attack as APP | Expect |
| --- | --- | --- |
| A01 | GUC on + `UPDATE` auth `status='active'` | UPDATE denied; row proposed |
| A02 | Direct `UPDATE` auth status/timestamps | Denied |
| A03 | `UPDATE` pilot `approved` | Denied |
| A04 | `UPDATE` credential `present` | Denied |
| A05 | `UPDATE` providers/models `enabled=true` | Denied |
| A06 | `INSERT`/`UPDATE`/`DELETE` `taha_governance_actions` | Denied |
| A07 | Call `approve_pilot_proposal` / `confirm_*` / `activate_*` / `enable_*` / `disable_*` / `append_governance_action` | EXECUTE denied |
| A08 | Call any listed Round 4/5 arm/reset/fixture helper still in `research` | Absent or EXECUTE denied |
| A09 | `INSERT`/`UPDATE`/`DELETE` `pilot_capacity_events` | Denied |
| A10 | `INSERT`/`UPDATE`/`DELETE` `live_request_envelopes` | Denied |
| A11 | Change an event’s `envelope_id` | Denied / trigger reject |
| A12 | `record_authorization_spend` on pilot-linked auth | Fail closed (no pilot spend via this path) |
| A13 | `INSERT`/`UPDATE`/`DELETE` `accounting_discrepancies` | Denied (INSERT only via DEFINER) |
| A14 | `CREATE TABLE` / `CREATE FUNCTION` in schema `research` | Denied |

---

## 4. Governance happy path (G)

Sequence under GOV inside one transaction then ROLLBACK (or disposable fixture):

| ID | Check |
| --- | --- |
| G01 | Credential confirm → present + governance action; no secrets |
| G02 | Approve → approved; fingerprint stored; provider/model still disabled until enable |
| G03 | Enable provider without approve → fail; unchanged |
| G04 | Enable model without provider enable → fail |
| G05 | Enable provider/model after approve+credential → enabled; audit actions |
| G06 | Activate without enable → fail |
| G07 | Activate after enable → immutable 24h window; proposal unchanged |
| G08 | Altered material fingerprint invalidates prior approval for enable/activate | Fail closed |
| G09 | Duplicate / copied / stale / superseded / revoked / conflicting actions | Deterministic reject per redesign §6.3 |
| G10 | Second activate / active→proposed / expired renew in place | Reject; renewal needs new row |
| G11 | Disable provider/model → new preflight/envelope denied; capacity unchanged | Exact |

---

## 5. Capacity, idempotency, concurrency, accounting (B)

| ID | Check |
| --- | --- |
| B01 | First pilot envelope → one `attempt_consumed` normal + one envelope; same pre-generated id |
| B02 | Idempotent replay → same envelope; event count unchanged |
| B03 | Alternate idempotency key same case → blocked |
| B04 | Fourth total request blocked (events only) |
| B05 | Token limits from event projected sums only |
| B06 | Success cap from non-fixture ledger `success` only |
| B07 | Cost > 0 blocked |
| B08 | Retry/fallback/confidential blocked; no event |
| B09 | Mid-txn failure rolls back event+envelope |
| B10 | Concurrent final slot → 1 ok / 1 blocked |
| B11 | Abandoned path: event committed, no later “success” → attempt still consumed; new key same case blocked |
| B12 | Enforcement never uses `COUNT(events)+SUM(ledger.request_count)` | Unit assert on snapshot function |
| B13 | Conflicting legacy ledger vs events → fail closed + discrepancy fingerprint returned; APP records via separate txn |
| B14 | APP cannot insert/update/delete capacity events |
| B15 | Legacy null-envelope reserved/finalized → `legacy_orphan` consumption; no executable envelope |

---

## 6. Round 4 compatibility (C)

| ID | Check |
| --- | --- |
| C01 | `build_non_pilot_request_envelope` succeeds for non-pilot auth when Round 4 gates armed in rolled-back fixture |
| C02 | Same function rejects pilot-linked auth |
| C03 | `build_provider_request_envelope` requires `pilot_proposal_id IS NOT NULL` |
| C04 | Direct `INSERT` envelopes denied to APP |
| C05 | Documented Round 4 adapter entrypoint = non-pilot builder |
| C06 | Both builders share exact same argument signature | Catalog identity match |

---

## 7. SECURITY DEFINER and ownership (S)

| ID | Check |
| --- | --- |
| S01 | All elevated functions: `prosecdef` and `proconfig` search_path=`pg_catalog` |
| S02 | Malicious `pg_temp` function/table shadowing names does not alter DEFINER resolution | Attack fails |
| S03 | APP cannot `CREATE OR REPLACE` / `ALTER OWNER` on research functions | Denied |
| S04 | Function owners remain `postgres` | Assert |
| S05 | Ownership replacement by APP denied | Denied |
| S06 | Unqualified reference detection in every elevated function body | Zero unqualified research object refs |
| S07 | Shadow table in `research` created by APP | CREATE denied (R11/A14) |

---

## 8. Helper isolation (H)

| ID | Check |
| --- | --- |
| H01 | Every symbol in redesign §10 absent from `research` or non-executable by APP/N8N/GOV |
| H02 | Helpers present only under `research_test` with no APP/N8N/GOV USAGE |
| H03 | Inventory query for `%arm%|%reset%|_r4|_r5a|cleanup_test|record_pilot_usage_for_tests` in `research` = empty or classified MOVED |

---

## 9. Migration / defaults / drift (M)

| ID | Check |
| --- | --- |
| M01 | Schema 9 re-run restart-safe at every step boundary 1–20 |
| M02 | Partial abort leaves no APP INSERT on envelopes/events; builders blocked until step 16 |
| M03 | Default privileges match redesign §12 |
| M04 | No `allow_pilot_activation` in catalogs |
| M05 | Gemini/model disabled; 3 proposed; 0 active; 0 credentials; 0 active workflows |
| M06 | Full catalog inventory equals Appendix A ∪ denied set |
| M07 | Schema version remains 8 after any partial failure before step 20 |
| M08 | No duplicated capacity events after migration rerun |
| M09 | No temporary broad grant at any partial-cutover checkpoint |

---

## 10. Required adversarial tests (X01–X40)

Exact additions required by Deliverable 3. Each maps to redesign Revision 3.

| ID | Probe | Expect |
| --- | --- | --- |
| X01 | Runtime schema `CREATE` denial as APP/N8N/GOV/TEST/PUBLIC on `research` | Denied |
| X02 | Shadow table attack: attempt to create `research.<elevated_target_name>` as APP | CREATE denied; DEFINER still resolves owner objects |
| X03 | Shadow function attack: attempt to create competing function in `research` as APP | CREATE denied |
| X04 | `pg_temp` name-resolution attack against DEFINER functions | Attack ineffective; search_path=`pg_catalog` + qualified refs |
| X05 | Unqualified reference detection in every elevated function | Zero unqualified refs |
| X06 | `PUBLIC EXECUTE` denial for every elevated signature in Appendix A.4 | Zero PUBLIC EXECUTE |
| X07 | Exact sequence privilege assertions | No research sequences; future = NONE |
| X08 | Every function overload signature in the allowlist | Exact identity-argument match |
| X09 | Future table default privilege remains `NONE` | Create probe table as OWN; APP has no privileges |
| X10 | Future function default `PUBLIC EXECUTE` remains revoked | Create probe function as OWN; PUBLIC/APP EXECUTE absent until explicit GRANT |
| X11 | Invalid governance `action_type` via `append_governance_action` | Reject; no row |
| X12 | Missing required type-dependent foreign keys | Reject; no row |
| X13 | Forbidden foreign keys for an action type | Reject; no row |
| X14 | Invalid fingerprint length or characters | Reject; no row |
| X15 | Duplicate action `(action_type, proposal_id, material_fingerprint)` | Reject / unique violation |
| X16 | Copied action for altered proposal (fingerprint mismatch vs live material) | Enable/activate fail closed |
| X17 | Stale action (`expires_at < now()`) | Cannot authorize enable/activate |
| X18 | Superseded action (`governance_revoked` / supersede row points to it) | Cannot authorize |
| X19 | Conflicting governance action (second active different fingerprint same type+proposal) | Reject |
| X20 | Attempted governance-action mutation or deletion as APP/GOV | Denied |
| X21 | Legacy reserved row with null envelope remains consumed as `legacy_orphan` | Capacity consumed; no executable envelope |
| X22 | Legacy finalized row with null envelope remains consumed as `legacy_orphan` | Same |
| X23 | Released legacy row → `legacy_reservation_archive` only; zero `attempt_consumed` | Archive present; event absent |
| X24 | Ledger/event conflict blocks the pilot | Builder returns fail-closed; no envelope |
| X25 | Discrepancy evidence survives the failed request workflow | Separate txn insert persists after build txn ends |
| X26 | Discrepancy insertion failure still leaves request blocked | `recording_failed`; next call re-detects conflict |
| X27 | Provider disable blocks new envelopes immediately | New build denied |
| X28 | Model disable blocks new envelopes immediately | New build denied |
| X29 | Disable does not restore capacity | Event counts unchanged |
| X30 | Re-enable requires a new governance action | Old enable insufficient after disable supersede |
| X31 | Previously prepared envelopes after disablement | Idempotent JSON retrieval ok; `execution_denied=true`; executable false |
| X32 | Failure and restart after every migration boundary 1–20 | Resume idempotent; version 8 until step 20 |
| X33 | No schema-version advancement after partial failure | `max(version)=8` |
| X34 | No duplicated capacity events after rerun | Unique constraints + skip logic |
| X35 | No temporary broad grant exists at any partial-cutover checkpoint | ACL probes at each step |
| X36 | Round 4 non-pilot builder compatibility | C01–C06 pass |
| X37 | Provider/model remain disabled after migration | Gemini + model `enabled=false` |
| X38 | Credential status remains unchanged | Gemini credential `missing` |
| X39 | Zero proposal approvals or authorization activations caused by migration | No migration-authored approve/activate actions; 0 active auths |
| X40 | Zero HTTP or model calls | No live network; no provider HTTP during suites |

---

## 11. Pass criteria

Implementation `PASS` only if:

1. Privilege layer (not merely triggers while WRITE remains) blocks all original bypass classes plus shadow-object CREATE
2. Appendix A matches live grants exactly (tables, views, sequences, function signatures)
3. Membership/PUBLIC/CREATE rules hold
4. Enablement sequence and disablement effects are enforced as specified
5. Request counts use events only; legacy null-envelope and released treatments match §7.4
6. Discrepancy recording uses separate-commit architecture and survives failed builds
7. Helpers are isolated under `research_test`
8. Round 4 uses `build_non_pilot_request_envelope`
9. Migration state machine is restart-safe; version 9 only after step 20
10. Adversarial tests X01–X40 all pass
