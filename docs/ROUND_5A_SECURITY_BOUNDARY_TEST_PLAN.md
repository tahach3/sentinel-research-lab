# Round 5A — Security Boundary Test Plan (Revision 4)

**Status:** Design only. For schema ≥ 9 implementation.
**Baseline design:** `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md` (Revision 4)
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
| R10 | Default privileges for `postgres` in `research`/`research_crypto` grant NONE on future objects to PUBLIC/APP/N8N/GOV | Catalog assert |
| R11 | `APP`/`N8N`/`GOV`/`TEST`/`PUBLIC` hold CREATE on schema `research` or `research_crypto` | False for each |
| R12 | `TEST` holds USAGE+CREATE on schema `research_test` only; NO USAGE/CREATE on `research` or `research_crypto` | Exact |
| R13 | Runtime roles hold USAGE on `research_crypto` | False for each |

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
| L07 | Sequence inventory: zero application sequences; future = NONE | Exact |
| L08 | Every function overload signature in Appendix A.4 present with exact identity arguments | Exact match |
| L09 | Five `reject_*` trigger functions installed, attached, PUBLIC/APP/GOV EXECUTE=NONE | Exact |
| L10 | `research_crypto.digest` / `gen_random_uuid` exist; runtime EXECUTE=NONE | Exact |

---

## 3. Application cannot govern or mutate gates (A)

| ID | Attack as APP | Expect |
| --- | --- | --- |
| A01 | GUC on + `UPDATE` auth `status='active'` | UPDATE denied; no GUC accepted |
| A02 | Direct `UPDATE` auth status/timestamps | Denied |
| A03 | `UPDATE` pilot `approved` | Denied |
| A04 | `UPDATE` credential `present` | Denied |
| A05 | `UPDATE` providers/models `enabled=true` | Denied |
| A06 | `INSERT`/`UPDATE`/`DELETE` `taha_governance_actions` | Denied / trigger reject |
| A07 | Call `approve_pilot_proposal` / `confirm_*` / `activate_*` / `enable_*` / `disable_*` / `append_governance_action` | EXECUTE denied |
| A08 | Call any listed Round 4/5 arm/reset/fixture helper still in `research` | Absent or EXECUTE denied |
| A09 | `INSERT`/`UPDATE`/`DELETE` `pilot_capacity_events` | Denied / trigger reject |
| A10 | `INSERT`/`UPDATE`/`DELETE` `live_request_envelopes` | Denied |
| A11 | Change an event’s `envelope_id` | Denied / trigger reject |
| A12 | `record_authorization_spend` on pilot-linked auth | Fail closed |
| A13 | `INSERT`/`UPDATE`/`DELETE` `accounting_discrepancies` | Denied (INSERT only via DEFINER) |
| A14 | `CREATE TABLE` / `CREATE FUNCTION` in schema `research` or `research_crypto` | Denied |
| A15 | Call `reject_*` trigger functions directly | EXECUTE denied |
| A16 | Mutate `pilot_capacity_reservations_legacy` | Denied / trigger reject |

---

## 4. Governance happy path and chain semantics (G)

Sequence under GOV inside one transaction then ROLLBACK (or disposable fixture):

| ID | Check |
| --- | --- |
| G01 | Credential confirm → present + governance action; no secrets |
| G02 | Approve → approved; fingerprint stored; provider/model still disabled until enable |
| G03 | Enable provider without approve → fail; unchanged |
| G04 | Enable model without provider enable → fail |
| G05 | Enable provider/model after approve+credential → enabled; audit actions; first enable parent NULL |
| G06 | Activate without enable → fail |
| G07 | Activate after enable → immutable 24h window; proposal unchanged |
| G08 | Altered material fingerprint invalidates prior approval for enable/activate | Fail closed |
| G09 | Duplicate / copied / stale / superseded / revoked / conflicting / branched actions | Deterministic reject per redesign §6 |
| G10 | Second activate / active→proposed / expired renew in place | Reject; renewal needs new row |
| G11 | Disable provider/model → new preflight/envelope denied; capacity unchanged | Exact |
| G12 | Disable references the active (terminal) enable action as `supersedes_action_id` | Exact parent |
| G13 | Re-enable references the terminal disable action | Exact parent |
| G14 | Governance chains cannot branch (second child of same parent) | Unique violation / reject |
| G15 | Enable→enable and disable→disable transitions fail | Reject |
| G16 | Valid enable→disable→enable chain succeeds | Three rows; terminal=enable |
| G17 | Active detection uses only the terminal action | Historical enable does not keep disabled provider active |
| G18 | Exact decision-value mappings enforced | Wrong `decision_value` rejected |
| G19 | Re-enable does not reactivate expired authorizations | New auth required after expiry |

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
| B16 | Released archive UNIQUE(`legacy_reservation_id`) prevents duplicate rerun entries |
| B17 | Snapshot/case-count functions have zero dependency on `pilot_capacity_reservations_legacy` |

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

## 7. SECURITY DEFINER, crypto, and ownership (S)

| ID | Check |
| --- | --- |
| S01 | All elevated functions: `prosecdef` and `proconfig` search_path=`pg_catalog` |
| S02 | Malicious `pg_temp` function/table shadowing names does not alter DEFINER resolution | Attack fails |
| S03 | APP cannot `CREATE OR REPLACE` / `ALTER OWNER` on research functions | Denied |
| S04 | Function owners remain `postgres` | Assert |
| S05 | Ownership replacement by APP denied | Denied |
| S06 | Unqualified reference detection in every elevated function body | Zero unqualified research/crypto refs |
| S07 | Shadow table in `research` created by APP | CREATE denied |
| S08 | Unqualified `digest` / `gen_random_uuid` calls do not exist in elevated functions | Zero matches |
| S09 | Extension functions resolve only from `research_crypto` | Catalog assert |
| S10 | Runtime roles cannot create objects in `research_crypto` | Denied |

---

## 8. Helper isolation (H)

| ID | Check |
| --- | --- |
| H01 | Every symbol in redesign §11 absent from `research` or non-executable by APP/N8N/GOV |
| H02 | Helpers present only under `research_test` with no APP/N8N/GOV USAGE |
| H03 | Inventory query for `%arm%|%reset%|_r4|_r5a|cleanup_test|record_pilot_usage_for_tests` in `research` = empty or classified MOVED |

---

## 9. Migration / defaults / drift (M)

| ID | Check |
| --- | --- |
| M01 | Schema 9 re-run restart-safe at every step boundary 1–20 |
| M02 | Partial abort leaves no APP INSERT on envelopes/events; builders blocked until ACL step |
| M03 | Default privileges match redesign §14 |
| M04 | No `allow_pilot_activation` in catalogs |
| M05 | Gemini/model disabled; 3 proposed; 0 active; 0 credentials; 0 active workflows |
| M06 | Full catalog inventory equals Appendix A ∪ denied set |
| M07 | Schema version remains 8 after any partial failure before step 20 |
| M08 | No duplicated capacity events after migration rerun |
| M09 | No temporary broad grant at any partial-cutover checkpoint |
| M10 | Partial failure before legacy rename is restart-safe |
| M11 | Partial failure after rename is restart-safe; original name absent |
| M12 | Version remains 8 when any legacy-dependency assertion fails |
| M13 | Every legacy-table dependency rewritten or removed before rename |
| M14 | Production symbols have zero dependency on `pilot_capacity_reservations_legacy` |

---

## 10. Activation without GUC (V)

| ID | Probe | Expect |
| --- | --- | --- |
| V01 | Activation without all governance prerequisites | Fail |
| V02 | Owner direct UPDATE to active missing prerequisites | Trigger reject |
| V03 | Activation with exact prerequisites succeeds in rollback-safe test | Active 24h; then ROLLBACK |
| V04 | No GUC path can authorize activation | Absent / ineffective |

---

## 11. Discrepancy identity (D)

| ID | Probe | Expect |
| --- | --- | --- |
| D01 | Discrepancy payloads are canonical and closed (exact key set) | Exact |
| D02 | Equivalent observed state produces the same fingerprint | Exact match |
| D03 | Altered state produces a different fingerprint | Differ |
| D04 | Fingerprint mismatch rejected by `record_accounting_discrepancy` | Reject; no insert |
| D05 | Duplicate discrepancy reports are idempotent | Same id; no mutation |
| D06 | Discrepancy-recording failure leaves the request blocked | `recording_failed` |

---

## 12. Required adversarial tests (X01–X40) + chain/crypto/legacy additions (X41–X70)

| ID | Probe | Expect |
| --- | --- | --- |
| X01 | Runtime schema `CREATE` denial as APP/N8N/GOV/TEST/PUBLIC on `research` | Denied |
| X02 | Shadow table attack in `research` as APP | CREATE denied |
| X03 | Shadow function attack in `research` as APP | CREATE denied |
| X04 | `pg_temp` name-resolution attack against DEFINER functions | Ineffective |
| X05 | Unqualified reference detection in every elevated function | Zero unqualified refs |
| X06 | `PUBLIC EXECUTE` denial for every elevated signature in Appendix A.4 | Zero PUBLIC EXECUTE |
| X07 | Exact sequence privilege assertions | NONE |
| X08 | Every function overload signature in the allowlist | Exact match |
| X09 | Future table default privilege remains `NONE` | Exact |
| X10 | Future function default `PUBLIC EXECUTE` remains revoked | Exact |
| X11 | Invalid governance `action_type` | Reject; no row |
| X12 | Missing required type-dependent foreign keys | Reject; no row |
| X13 | Forbidden foreign keys for an action type | Reject; no row |
| X14 | Invalid fingerprint length or characters | Reject; no row |
| X15 | Duplicate identical transition+parent | Reject / unique violation |
| X16 | Copied action for altered proposal | Enable/activate fail closed |
| X17 | Stale action (`expires_at < now()`) | Cannot authorize |
| X18 | Superseded terminal (child exists) | Cannot authorize as terminal |
| X19 | Conflicting concurrent child / branch attempt | Reject |
| X20 | Attempted governance-action mutation or deletion as APP/GOV | Denied / trigger |
| X21 | Legacy reserved null envelope → `legacy_orphan` | Consumed; no executable envelope |
| X22 | Legacy finalized null envelope → `legacy_orphan` | Same |
| X23 | Released → archive only; zero `attempt_consumed` | Exact |
| X24 | Ledger/event conflict blocks the pilot | No envelope |
| X25 | Discrepancy evidence survives failed request workflow | Separate txn persists |
| X26 | Discrepancy insertion failure still leaves request blocked | Exact |
| X27 | Provider disable blocks new envelopes immediately | Denied |
| X28 | Model disable blocks new envelopes immediately | Denied |
| X29 | Disable does not restore capacity | Counts unchanged |
| X30 | Re-enable requires new enable whose parent is terminal disable; prior enable insufficient | Chain semantics per §6.3 |
| X31 | Prepared envelopes after disablement | Lookup ok; `execution_denied=true`; executable false |
| X32 | Failure and restart after every migration boundary 1–20 | Resume idempotent; version 8 until step 20 |
| X33 | No schema-version advancement after partial failure | `max(version)=8` |
| X34 | No duplicated capacity events after rerun | Exact |
| X35 | No temporary broad grant at partial-cutover checkpoints | Exact |
| X36 | Round 4 non-pilot builder compatibility | C01–C06 pass |
| X37 | Provider/model remain disabled after migration | `enabled=false` |
| X38 | Credential status remains unchanged | Gemini `missing` |
| X39 | Zero proposal approvals or authorization activations caused by migration | Exact |
| X40 | Zero HTTP or model calls | Exact |
| X41 | Disable references the active enable action | Parent match |
| X42 | Re-enable references the terminal disable action | Parent match |
| X43 | Governance chains cannot branch | Reject |
| X44 | Enable→enable and disable→disable fail | Reject |
| X45 | Valid enable→disable→enable succeeds | Terminal=enable |
| X46 | Active detection uses only terminal action | Exact |
| X47 | Historical enable does not keep disabled provider active | Exact |
| X48 | Exact decision-value mappings enforced | Reject invalid |
| X49 | Unqualified `digest`/`gen_random_uuid` absent from elevated functions | Zero |
| X50 | Runtime roles cannot create objects in `research_crypto` | Denied |
| X51 | Extension functions resolve only from `research_crypto` | Exact |
| X52 | Activation without all governance prerequisites fails | Fail |
| X53 | Owner direct activation missing prerequisites fails | Trigger reject |
| X54 | Activation with exact prerequisites succeeds (rollback-safe) | Then ROLLBACK |
| X55 | Discrepancy payloads canonical and closed | Exact keys |
| X56 | Equivalent observed state → same discrepancy fingerprint | Match |
| X57 | Altered state → different fingerprint | Differ |
| X58 | Fingerprint mismatch rejected by recorder | Reject |
| X59 | Duplicate discrepancy reports idempotent | Same id |
| X60 | Discrepancy-recording failure leaves request blocked | Exact |
| X61 | Every legacy-table dependency rewritten or removed | Zero production refs before/at rename |
| X62 | Schema-9 production symbols have zero dependency on `pilot_capacity_reservations_legacy` | Exact |
| X63 | Legacy table mutation rejected | Trigger / privilege |
| X64 | Released archive uniqueness prevents duplicate rerun entries | Exact |
| X65 | All five append-only trigger functions installed and attached | Exact |
| X66 | Runtime roles cannot invoke or replace append-only trigger functions | Denied |
| X67 | Partial failure before legacy rename is restart-safe | Exact |
| X68 | Partial failure after rename is restart-safe | Exact |
| X69 | Version remains 8 when any dependency assertion fails | Exact |
| X70 | X30 matches finalized disable/re-enable chain semantics | Exact |

---

## 13. Pass criteria

Implementation `PASS` only if:

1. Privilege layer blocks original bypass classes plus shadow-object CREATE and crypto-schema CREATE
2. Appendix A matches live grants exactly (tables, views, sequences, function signatures, triggers, crypto)
3. Membership/PUBLIC/CREATE rules hold
4. Linear governance chains, terminal-state detection, and closed decision values are enforced
5. Request counts use events only; legacy null-envelope/released/rename treatments match §7.4
6. Discrepancy recording uses closed payload, recomputed fingerprint, and separate-commit architecture
7. Activation has no GUC; trigger enforces all prerequisites including against owner direct UPDATE
8. Helpers are isolated under `research_test`
9. Round 4 uses `build_non_pilot_request_envelope`
10. Migration state machine is restart-safe; version 9 only after step 20
11. Adversarial tests X01–X70 all pass
