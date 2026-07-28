# Round 5A — Security Boundary Test Plan (Revision 2)

**Status:** Design only. For schema ≥ 9 implementation.
**Baseline design:** `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md` (Revision 2)
**Actors:** `APP`=`research_app`, `GOV`=`research_governance`, `N8N`=`n8n_app`, `OWN`=`postgres`, `TEST`=`research_test`
**Rule:** Adversarial cases expect permission denied / execute denied / fail-closed builder errors. Governance happy paths use `BEGIN…ROLLBACK` or `research_test` fixtures that never leave production pilot active/enabled.

Production invariants after every suite:

- Gemini disabled; `gemini-2.5-flash` disabled
- 3 proposed production pilot auths; 0 active pilot auths
- 0 n8n credentials; 0 active workflows
- Pilot `awaiting_taha_credential` unless rolled back

---

## 1. Role membership and PUBLIC

| ID | Probe | Expect |
| --- | --- | --- |
| R01 | `APP` is member of `research_governance` | False |
| R02 | `N8N` is member of `research_governance` | False |
| R03 | `GOV` is member of `research_app` | False |
| R04 | As `APP`: `SET ROLE research_governance` | Fail |
| R05 | As `N8N`: `SET ROLE research_governance` | Fail |
| R06 | `GOV` has `rolinherit = false` (NOINHERIT) | True |
| R07 | Only `OWN` can `GRANT research_governance TO …` | Documented + attempted grant as APP fails |
| R08 | `PUBLIC` has EXECUTE on any governance/enable/activate/confirm/builder/capacity function | Zero |
| R09 | New function created in migration path has PUBLIC EXECUTE revoked | Assert in M-suite |
| R10 | Default privileges for `postgres` in `research` do not grant table WRITE or function EXECUTE to PUBLIC/APP beyond Appendix A | Catalog assert |

---

## 2. Allowlist completeness

| ID | Probe | Expect |
| --- | --- | --- |
| L01 | Every Appendix A table privilege for APP matches catalog | Exact match |
| L02 | Every research table/view **not** in Appendix A has no APP privileges | Denied |
| L03 | Every Appendix A.2 function with EXECUTE=Y is executable by APP | Succeeds (call smoke) |
| L04 | Every research function with EXECUTE=N for APP fails EXECUTE | Denied |
| L05 | Non-allowlisted function sample: `activate_pilot_authorization`, `enable_provider_for_pilot`, `_r4_arm_provider` | Denied for APP |
| L06 | Permission-drift CI query fails build on mismatch | Drift detected |

---

## 3. Application cannot govern or mutate gates

| ID | Attack as APP | Expect |
| --- | --- | --- |
| A01 | GUC on + `UPDATE` auth `status='active'` | UPDATE denied; row proposed |
| A02 | Direct `UPDATE` auth status/timestamps | Denied |
| A03 | `UPDATE` pilot `approved` | Denied |
| A04 | `UPDATE` credential `present` | Denied |
| A05 | `UPDATE` providers/models `enabled=true` | Denied |
| A06 | `INSERT`/`UPDATE`/`DELETE` `taha_governance_actions` | Denied |
| A07 | Call `approve_pilot_proposal` / `confirm_*` / `activate_*` / `enable_*` / `disable_*` | EXECUTE denied |
| A08 | Call any listed Round 4/5 arm/reset/fixture helper still in `research` | Absent or EXECUTE denied |
| A09 | `INSERT`/`UPDATE`/`DELETE` `pilot_capacity_events` | Denied |
| A10 | `INSERT`/`UPDATE`/`DELETE` `live_request_envelopes` | Denied |
| A11 | Change an event’s `envelope_id` | Denied / trigger reject |
| A12 | `record_authorization_spend` on pilot-linked auth | Fail closed (no pilot spend via this path) |

---

## 4. Governance happy path (rollback-safe)

Sequence under GOV inside one transaction then ROLLBACK (or disposable fixture):

| ID | Check |
| --- | --- |
| G01 | Credential confirm → present + governance action; no secrets |
| G02 | Approve → approved; fingerprint stored; provider/model still disabled |
| G03 | Enable provider without approve → fail; unchanged |
| G04 | Enable model without provider enable → fail |
| G05 | Enable provider/model after approve+credential → enabled; audit actions |
| G06 | Activate without enable → fail |
| G07 | Activate after enable → immutable 24h window; proposal unchanged |
| G08 | Altered material fingerprint invalidates prior approval for enable/activate | Fail closed |
| G09 | Duplicate / copied / stale / superseded / revoked / conflicting actions | Deterministic reject per redesign §5.2 |
| G10 | Second activate / active→proposed / expired renew in place | Reject; renewal needs new row |

---

## 5. Capacity, idempotency, concurrency, accounting

| ID | Check |
| --- | --- |
| B01 | First pilot envelope → one `attempt_consumed` + one envelope; same pre-generated id |
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
| B13 | Conflicting legacy ledger vs events → fail closed + discrepancy action (GOV reporter) |
| B14 | APP cannot insert/update/delete capacity events |

---

## 6. Round 4 compatibility

| ID | Check |
| --- | --- |
| C01 | `build_non_pilot_request_envelope` succeeds for non-pilot auth when Round 4 gates armed in rolled-back fixture |
| C02 | Same function rejects pilot-linked auth |
| C03 | `build_provider_request_envelope` rejects non-pilot auth (or requires pilot linkage — per implementation: pilot builder requires `pilot_proposal_id IS NOT NULL`) |
| C04 | Direct `INSERT` envelopes denied to APP |
| C05 | Documented Round 4 adapter entrypoint = non-pilot builder |

---

## 7. SECURITY DEFINER and ownership

| ID | Check |
| --- | --- |
| S01 | All elevated functions: `prosecdef` and `proconfig` search_path=`research, pg_temp` |
| S02 | Malicious `pg_temp` function/table shadowing names does not alter DEFINER resolution | Attack fails |
| S03 | APP cannot `CREATE OR REPLACE` / `ALTER OWNER` on research functions | Denied |
| S04 | Function owners remain `postgres` | Assert |
| S05 | Ownership replacement by APP denied | Denied |

---

## 8. Helper isolation

| ID | Check |
| --- | --- |
| H01 | Every symbol in redesign §9 absent from `research` or non-executable by APP/N8N/GOV |
| H02 | Helpers present only under `research_test` (if retained) with no APP/N8N/GOV USAGE |
| H03 | Inventory query for `%arm%|%reset%|_r4|_r5a|cleanup_test|record_pilot_usage_for_tests` in `research` = empty or classified |

---

## 9. Migration / defaults / drift

| ID | Check |
| --- | --- |
| M01 | Schema 9 re-run restart-safe |
| M02 | Partial abort leaves no APP INSERT on envelopes/events |
| M03 | Default privileges match redesign §3 |
| M04 | No `allow_pilot_activation` in catalogs |
| M05 | Gemini/model disabled; 3 proposed; 0 active; 0 credentials; 0 active workflows |
| M06 | Full catalog inventory equals Appendix A∪denied set |

---

## 10. Additional adversarial checklist (required)

1. APP cannot obtain/inherit `research_governance` — R01,R04
2. N8N cannot obtain/inherit `research_governance` — R02,R05
3. PUBLIC cannot execute elevated functions — R08
4. Default privileges do not grant future EXECUTE to PUBLIC — R09,R10,M03
5. APP only enumerated allowlist — L01–L04
6. Every non-allowlisted function denied — L04,L05
7. Provider enablement fails without matching governance path — G03
8. Model enablement fails without matching governance path — G04
9. Altered material fingerprint invalidates approval — G08
10. Duplicate/stale/copied/superseded/conflicting actions fail — G09
11. All Round 4/5 helpers inaccessible to runtime — H01–H03,A08
12. Non-pilot Round 4 matches selected path — C01–C05
13. Abandoned requests permanently consume — B11
14. No ledger/event double counting — B12
15. Conflicting legacy accounting fails closed — B13
16. Capacity events no APP write — B14,A09
17. Event envelope link immutable — A11
18. Malicious search_path ineffective — S02
19. Function replace/ownership by runtime denied — S03,S05
20. Permission drift detected — L06,M06

---

## 11. Pass criteria

Implementation `PASS` only if privilege layer (not merely triggers while WRITE remains) blocks all four original bypass classes, Appendix A matches live grants, membership/PUBLIC rules hold, enablement sequence is enforced, request counts use events only, helpers are isolated, and Round 4 uses `build_non_pilot_request_envelope`.
