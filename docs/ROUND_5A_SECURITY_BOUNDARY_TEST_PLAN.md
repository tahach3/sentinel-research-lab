# Round 5A — Security Boundary Test Plan (Revision 7)

**Status:** Design only. For schema ≥ 9 implementation.
**Baseline design:** `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md` (Revision 7)
**Actors:** `APP`=`research_app`, `GOV`=`research_governance`, `N8N`=`n8n_app`, `OWN`=`postgres`, `TEST`=`research_test`
**Rule:** Adversarial cases expect permission denied / execute denied / fail-closed builder errors. Governance happy paths use `BEGIN…ROLLBACK` or disposable fixtures that never leave production pilot active/enabled. This plan is **self-contained** — no prior-revision-only references.

Production invariants after every suite:

- Gemini disabled; `gemini-2.5-flash` disabled
- 3 proposed production pilot auths; 0 active pilot auths
- 0 n8n credentials; 0 active workflows
- Pilot `awaiting_taha_credential` unless rolled back
- Zero HTTP or model calls
- USD 0.00 paid usage

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
| R07 | Only `OWN` can `GRANT research_governance TO …` | Documented + APP grant fails |
| R08 | `PUBLIC` has EXECUTE on any governance/enable/activate/confirm/builder/capacity/discrepancy function | Zero |
| R09 | New function created in cutover path has PUBLIC EXECUTE revoked | Assert in M-suite |
| R10 | Default privileges for `postgres` in `research` grant NONE on future TABLES/FUNCTIONS/SEQUENCES to PUBLIC/APP/N8N/GOV | Catalog assert |
| R11 | `APP`/`N8N`/`GOV`/`TEST`/`PUBLIC` hold CREATE on schema `research` | False for each |
| R12 | `TEST` holds USAGE+CREATE on schema `research_test` only; NO USAGE and NO CREATE on schema `research` | Exact |
| R13 | `APP`/`N8N`/`GOV`/`TEST`/`PUBLIC` hold CREATE or USAGE on schema `research_crypto` | False for each |

---

## 2. Allowlist / trigger inventory (L)

| ID | Probe | Expect |
| --- | --- | --- |
| L01 | Every Appendix A table privilege for APP matches catalog | Exact match |
| L02 | Every research table/view **not** in Appendix A has no APP privileges | Denied |
| L03 | Every Appendix A.4 function with research_app EXECUTE=Y is executable by APP after `complete` | Succeeds |
| L04 | Every research function with research_app EXECUTE=N fails EXECUTE for APP | Denied |
| L05 | Non-allowlisted sample: `activate_pilot_authorization`, `enable_provider_for_pilot`, `_r4_arm_provider` as APP | Denied |
| L06 | Permission-drift CI query fails build on mismatch | Drift detected |
| L07 | Sequence inventory: zero sequences in `research`; future sequence ACL = NONE | Exact |
| L08 | Every function overload signature in Appendix A.4 present with exact identity arguments | Exact |
| L09 | Views match Appendix A.2 | Exact |
| L10 | `schema9_cutover_state` and `schema9_cutover_checkpoints` privileges = NONE for APP/N8N/GOV/TEST/PUBLIC | Exact |
| L11 | All five exact trigger names exist | Exact |
| L12 | Each trigger attached to exact expected table | Exact |
| L13 | Each trigger uses exact expected trigger function | Exact |
| L14 | Trigger enablement = ENABLE | Exact |
| L15 | Catalog drift in any trigger name/attachment fails validation | Fail |
| L16 | Every §13.3 function row matches catalog identity | Exact |
| L17 | Every §13.4 table-role cell matches catalog ACL | Exact |

---

## 3. Application gate attacks (A)

| ID | Attack as APP | Expect |
| --- | --- | --- |
| A01 | GUC on + `UPDATE` auth `status='active'` | UPDATE denied; row proposed |
| A02 | Direct `UPDATE` auth status/timestamps | Denied |
| A03 | `UPDATE` pilot `approved` | Denied |
| A04 | `UPDATE` credential `present` | Denied |
| A05 | `UPDATE` providers/models `enabled=true` | Denied |
| A06 | `INSERT`/`UPDATE`/`DELETE` `taha_governance_actions` | Denied |
| A07 | Call `approve_pilot_proposal` / `confirm_*` / `activate_*` / `enable_*` / `disable_*` / `append_governance_action` | EXECUTE denied |
| A08 | Call Round 4/5 arm/reset/fixture helper still in `research` | Absent or EXECUTE denied |
| A09 | `INSERT`/`UPDATE`/`DELETE` `pilot_capacity_events` | Denied |
| A10 | `INSERT`/`UPDATE`/`DELETE` `live_request_envelopes` | Denied |
| A11 | Change an event's `envelope_id` | Denied / trigger reject |
| A12 | `record_authorization_spend` on pilot-linked auth | Fail closed |
| A13 | `INSERT`/`UPDATE`/`DELETE` `accounting_discrepancies` | Denied |
| A14 | `CREATE TABLE` / `CREATE FUNCTION` in schema `research` | Denied |
| A15 | Direct write on freeze-matrix governed table during cutover | Denied |
| A16 | Call frozen builders while cutover state ≠ `complete` | EXECUTE denied or entrypoint gate deny |

---

## 4. Governance chain and credential scope (G)

| ID | Check | Expect |
| --- | --- | --- |
| G01 | Credential confirm → present + governance action; no secrets | Exact |
| G02 | Approve → approved; fingerprint stored; provider/model still disabled until enable | Exact |
| G03 | Enable provider without approve → fail; unchanged | Reject |
| G04 | Enable model without provider enable → fail | Reject |
| G05 | Enable provider/model after approve+credential → enabled; audit actions | Exact |
| G06 | Activate without enable → fail | Reject |
| G07 | Activate after enable → immutable 24h window | Exact |
| G08 | Altered material fingerprint invalidates prior approval | Fail closed |
| G09 | Duplicate / copied / stale / superseded / revoked / conflicting actions | Deterministic reject |
| G10 | Second activate / active→proposed / expired renew in place | Reject |
| G11 | Disable provider/model → new preflight/envelope denied; capacity unchanged | Exact |
| G12 | Credential confirmation without proposal ID fails | Reject |
| G13 | Credential confirmation for proposal A does not affect proposal B | Isolated |
| G14 | Provider-only ambiguous lookup fails | Absent / reject |
| G15 | Wrong proposal/provider binding fails | Reject |
| G16 | Wrong governance action scope fails | Reject |
| G17 | Expired or superseded credential action fails | Reject |
| G18 | Credential confirmation stores no secret material | Assert |
| G19 | Concurrent child creation cannot branch a chain | Unique / reject |

### 4.1 Explicit governance transition tests

| ID | Check | Expect |
| --- | --- | --- |
| GT01 | enable → enable rejection | Reject; no row |
| GT02 | disable → disable rejection | Reject; no row |
| GT03 | valid enable → disable → enable | Accept each legal transition |
| GT04 | terminal-only enabled-state detection | Only terminal enable counts |
| GT05 | historical enable does not override terminal disable | Disabled |
| GT06 | branching child rejection | Reject |
| GT07 | cross-scope supersession rejection | Reject |
| GT08 | child proposal mismatch | Reject |
| GT09 | child provider mismatch | Reject |
| GT10 | child model mismatch | Reject |

---

## 5. Capacity / accounting (B)

| ID | Check | Expect |
| --- | --- | --- |
| B01 | First pilot envelope → one `attempt_consumed` normal + envelope | Exact |
| B02 | Idempotent replay → same envelope; event count unchanged | Exact |
| B03 | Alternate idempotency key same case → blocked | Exact |
| B04 | Fourth total request blocked (events only) | Exact |
| B05 | Token limits from event projected sums only | Exact |
| B06 | Success cap from non-fixture ledger `success` only | Exact |
| B07 | Cost > 0 blocked | Exact |
| B08 | Retry/fallback/confidential blocked; no event | Exact |
| B09 | Mid-txn failure rolls back event+envelope | Exact |
| B10 | Concurrent final slot → 1 ok / 1 blocked | Exact |
| B11 | Abandoned path: event committed, no success → attempt consumed | Exact |
| B12 | Enforcement never uses `COUNT(events)+SUM(ledger.request_count)` | Unit assert |
| B13 | Conflicting legacy ledger vs events → fail closed + discrepancy | Exact |
| B14 | APP cannot insert/update/delete capacity events | Denied |
| B15 | Legacy null-envelope reserved/finalized → `legacy_orphan` | Exact |
| B16 | Released legacy → archive only | Exact |
| B17 | Post-rename builders independent of original table name | Exact |
| B18 | Arbitrary extra JSON fields cannot be submitted to recorder | Reject |
| B19 | Recorder reconstructs payload from typed inputs | Exact |
| B20 | Invalid scalar types fail | Reject |
| B21 | Negative count or token values fail | Reject |
| B22 | Monetary precision overflow fails | Reject |
| B23 | `0`, `0.0`, `0.00000000` produce same fingerprint | Match literal |
| B24 | Different monetary values produce different fingerprints | Differ |
| B25 | Canonical payload hashes to `c79c93716d543b36954e599c5e1d1a6e5cf74b9d6215f25319cb2296833dc957` via independent digest (not production function under test) | Match literal |
| B26 | Caller-supplied matching hash for non-canonical payload rejected | Reject |
| B27 | Duplicate canonical report idempotent | Same id |
| B28 | Recorder failure leaves request blocked | Exact |

---

## 6. Round 4 compatibility (C)

| ID | Check | Expect |
| --- | --- | --- |
| C01 | `build_non_pilot_request_envelope` succeeds for non-pilot auth in rolled-back fixture | Exact |
| C02 | Same function rejects pilot-linked auth | Reject |
| C03 | `build_provider_request_envelope` requires `pilot_proposal_id IS NOT NULL` | Exact |
| C04 | Direct `INSERT` envelopes denied to APP | Denied |
| C05 | Documented Round 4 adapter entrypoint = non-pilot builder | Exact |
| C06 | Both builders share exact same argument signature | Catalog match |

---

## 7. SECURITY DEFINER / crypto placement (S)

| ID | Check | Expect |
| --- | --- | --- |
| S01 | Elevated functions: `prosecdef` and `search_path=pg_catalog` | Exact |
| S02 | Malicious `pg_temp` shadowing does not alter DEFINER resolution | Attack fails |
| S03 | APP cannot `CREATE OR REPLACE` / `ALTER OWNER` on research functions | Denied |
| S04 | Function owners remain `postgres` | Assert |
| S05 | Ownership replacement by APP denied | Denied |
| S06 | Unqualified reference detection in every elevated function body | Zero |
| S07 | Shadow table in `research` created by APP | CREATE denied |
| S08 | Missing `research_crypto.digest(...)` | Fail; version 8; runtime frozen |
| S09 | Missing `research_crypto.gen_random_uuid()` | Fail; version 8; runtime frozen |
| S10 | pgcrypto installed in the wrong schema | Fail; v8; frozen |
| S11 | Elevated function resolving a crypto symbol from `public` | Fail; v8; frozen |
| S12 | Elevated function resolving a crypto symbol from `pg_temp` | Fail; v8; frozen |
| S13 | Any unqualified crypto call in schema-9 elevated-function definitions | Fail; v8; frozen |
| S14 | After each of S08–S13, `max(schema_version)=8` and freeze ACLs remain revoked | Exact |

---

## 8. Helper isolation (H)

| ID | Check | Expect |
| --- | --- | --- |
| H01 | Moved helpers absent from `research` or non-executable by APP/N8N/GOV | Exact |
| H02 | Helpers only under `research_test` with no APP/N8N/GOV USAGE | Exact |
| H03 | Inventory `%arm%|%reset%|_r3|_r4|_r5a|cleanup_test|record_pilot_usage_for_tests` in `research` = empty or MOVED | Exact |

---

## 9. Multi-transaction cutover controller (M)

| ID | Setup | Action | Expect |
| --- | --- | --- | --- |
| M01 | Fresh v8 | Run preflight | No DML/DDL; no cutover row written |
| M02 | Instrument preflight SQL | Assert absence of INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/GRANT/REVOKE on cutover/ACL objects | Exact |
| M03 | Optional cutover-state upsert | Static/design assert | Absent from preflight |
| M04 | Extra LOGIN role | Preflight | Block |
| M05 | Extra executable function for APP | Preflight | Block |
| M06 | Wrong function owner | Preflight | Block |
| M07 | Unexpected function caller role | Preflight | Block |
| M08 | Extra base table | Preflight | Block |
| M09 | Unexpected writable role | Preflight | Block |
| M10 | Effective inherited WRITE via membership | Preflight | Block |
| M11 | Column-level UPDATE grant mismatch | Preflight | Block |
| M12 | Freeze txn failure | Abort mid-freeze | Rollback; no `runtime_frozen`; no transform |
| M13 | Freeze commit | New session verify | ACL frozen before transform |
| M14 | After freeze | Call pilot builder / live_preflight / orchestrate | Denied |
| M15 | During transform | Old+new builders | Both non-executable |
| M16 | Each §13.8 checkpoint | Complete subphase | Checkpoint row + matching `catalog_digest` |
| M17 | Checkpoint flag without matching catalog | Validate | Fail → `failed_frozen` |
| M18 | Catalog state without matching checkpoint | Restart classify | Fail / do not advance |
| M19 | Each §13.9 category | Inject fixture row | Exact predicate outcome |
| M20 | Full reservation set | Classify | Every source row in exactly one category |
| M21 | State B | Recompute digests without trusting checkpoint presence | Completeness proof |
| M22 | Persisted vs recomputed digest mismatch | Reconcile verify | `failed_frozen` |
| M23 | Validation pass under freeze | Version txn | Version becomes 9; ACLs still revoked |
| M24 | v9 + `version_advanced` | Restore txn A | Grants applied; state=`runtime_restoring`; entrypoints still deny |
| M25 | After txn A | Call schema-9 builder | Denied by state gate |
| M26 | Partial grants + verify fail | Separate fail-revoke txn | Revoke A grants; `failed_frozen` |
| M27 | Aborted grant txn | Attempt same-txn recovery | Forbidden; harness asserts new txn used |
| M28 | Fail-revoke txn fails | Controller result | `BLOCKED_OWNER_RECOVERY` |
| M29 | Restart `runtime_restoring` no grants | Classify | Selects grant installation (txn A) |
| M30 | Restart `runtime_restoring` partial grants | Classify | Re-freeze revoke first (§13.5 8b) |
| M31 | `complete` with ACL mismatch | Verify | Re-enter `failed_frozen` |
| M32 | Throughout restoration | Schema-8 builders | Unavailable |
| M33 | Before `complete` commit | Schema-9 builders usable? | No |
| M34 | After `complete` | Schema-9 allowlist builders | Usable per Appendix A |
| M35 | Advisory lock absent after freeze | Runtime call | Still denied (ACL+state) |
| M36 | State A path | Rename readiness | Equality §13.10 then rename |
| M37 | State C | Both/neither tables | `failed_frozen` |
| M38 | Every restart class §13.5 | Drive fixture | Exactly one recovery phase |

---

## 10. Activation prerequisites (V)

Each of V01–V14: activation fails; `activated_at` null; status remains proposed.

| ID | Missing / corrupted prerequisite |
| --- | --- |
| V01 | proposal not approved |
| V02 | credential not confirmed for proposal scope |
| V03 | provider terminal state disabled |
| V04 | model terminal state disabled |
| V05 | missing activation-approval action |
| V06 | altered activation fingerprint |
| V07 | wrong authority |
| V08 | wrong proposal |
| V09 | wrong provider |
| V10 | wrong model |
| V11 | wrong role |
| V12 | wrong case |
| V13 | provider operational flag disabled |
| V14 | model operational flag disabled |
| V15 | Activation with all prerequisites succeeds (rollback-safe) | Then ROLLBACK |
| V16 | Moving `activated_at` after activation fails |
| V17 | Clearing `activated_at` fails |
| V18 | Moving `expires_at` fails |
| V19 | Clearing `expires_at` fails |
| V20 | active→proposed fails |
| V21 | expired→active fails |
| V22 | Exact `expires_at = activated_at + 24 hours` on success |
| V23 | No GUC path can authorize activation |

---

## 11. Required adversarial index (X01–X174)

Every retained probe is restated here (no prior-revision-only references).

| ID | Probe | Expect |
| --- | --- | --- |
| X01 | Runtime schema `CREATE` denial as APP/N8N/GOV/TEST/PUBLIC on `research` | Denied |
| X02 | Shadow table attack: create `research.<elevated_target_name>` as APP | CREATE denied |
| X03 | Shadow function attack in `research` as APP | CREATE denied |
| X04 | `pg_temp` name-resolution attack against DEFINER functions | Ineffective |
| X05 | Unqualified reference detection in every elevated function | Zero unqualified refs |
| X06 | `PUBLIC EXECUTE` denial for every elevated signature in Appendix A.4 | Zero PUBLIC EXECUTE |
| X07 | Exact sequence privilege assertions | No research sequences; future = NONE |
| X08 | Every function overload signature in the allowlist | Exact identity match |
| X09 | Future table default privilege remains `NONE` | APP has no privileges on probe table |
| X10 | Future function default `PUBLIC EXECUTE` remains revoked | Absent until explicit GRANT |
| X11 | Invalid governance `action_type` via `append_governance_action` | Reject; no row |
| X12 | Missing required type-dependent foreign keys | Reject; no row |
| X13 | Forbidden foreign keys for an action type | Reject; no row |
| X14 | Invalid fingerprint length or characters | Reject; no row |
| X15 | Duplicate action `(action_type, proposal_id, material_fingerprint)` | Reject / unique |
| X16 | Copied action for altered proposal | Enable/activate fail closed |
| X17 | Stale action (`expires_at < now()`) | Cannot authorize |
| X18 | Superseded action | Cannot authorize |
| X19 | Conflicting governance action | Reject |
| X20 | Governance-action mutation/deletion as APP/GOV | Denied |
| X21 | Legacy reserved null envelope → `legacy_orphan` | Capacity consumed |
| X22 | Legacy finalized null envelope → `legacy_orphan` | Same |
| X23 | Released legacy → archive only | Archive present; event absent |
| X24 | Ledger/event conflict blocks the pilot | Fail-closed; no envelope |
| X25 | Discrepancy evidence survives failed request workflow | Persists after build txn ends |
| X26 | Discrepancy insertion failure still leaves request blocked | Exact |
| X27 | Provider disable blocks new envelopes immediately | Denied |
| X28 | Model disable blocks new envelopes immediately | Denied |
| X29 | Disable does not restore capacity | Counts unchanged |
| X30 | Re-enable requires a new governance action | Old enable insufficient |
| X31 | Prepared envelopes after disablement | Idempotent JSON ok; executable false |
| X32 | Failure/restart after every cutover phase boundary | Resume idempotent; version rules hold |
| X33 | No schema-version advancement after partial failure before validate | `max(version)=8` |
| X34 | No duplicated capacity events after rerun | Unique + skip |
| X35 | No temporary broad grant at any partial-cutover checkpoint | ACL probes |
| X36 | Round 4 non-pilot builder compatibility | C01–C06 pass |
| X37 | Provider/model remain disabled after cutover | `enabled=false` |
| X38 | Credential status remains unchanged | Baseline unchanged |
| X39 | Zero proposal approvals or authorization activations caused by cutover | Exact |
| X40 | Zero HTTP or model calls | Exact |
| X41 | APP cannot INSERT governance actions | Denied |
| X42 | APP cannot UPDATE providers.enabled | Denied |
| X43 | APP cannot UPDATE models/candidates enabled | Denied |
| X44 | APP cannot UPDATE credential_status | Denied |
| X45 | APP cannot UPDATE authorization activated_at | Denied |
| X46 | N8N cannot EXECUTE builders | Denied |
| X47 | N8N cannot INSERT envelopes | Denied |
| X48 | PUBLIC cannot EXECUTE elevated functions | Denied |
| X49 | GOV cannot SET ROLE research_app | Fail |
| X50 | Terminal enable detection ignores non-terminal history | Exact |
| X51 | Branching governance child rejected | Reject |
| X52 | Cross-scope supersession rejected | Reject |
| X53 | Child proposal mismatch rejected | Reject |
| X54 | Child provider mismatch rejected | Reject |
| X55 | Child model mismatch rejected | Reject |
| X56 | enable→enable rejected | Reject |
| X57 | disable→disable rejected | Reject |
| X58 | enable→disable→enable accepted | Accept |
| X59 | Activation missing any V01–V14 prerequisite | Fail; no activation |
| X60 | Activation success then ROLLBACK leaves production inactive | Exact |
| X61 | Post-activation timestamp mutation denied | Denied |
| X62 | No GUC authorization path | Absent/denied |
| X63 | Helper arm/reset still in research after isolation | Absent or denied |
| X64 | research_crypto USAGE denied to APP | Denied |
| X65 | Unqualified crypto in elevated body | Validation fail |
| X66 | State A rename without completeness equality | Blocked |
| X67 | State B step referencing original table name | Static fail |
| X68 | State C both tables | `failed_frozen` |
| X69 | State C neither table | `failed_frozen` |
| X70 | USD paid usage remains 0.00 through cutover suites | Exact |
| X71 | Schema-8 pilot builder denied after durable freeze | Denied |
| X72 | Non-pilot builder denied after durable freeze | Denied |
| X73 | `live_preflight` denied after durable freeze | Denied |
| X74 | Orchestration cannot reach provider logic during cutover | Denied |
| X75 | Direct envelope insert denied during cutover | Denied |
| X76 | Runtime blocked after failure at every phase | Frozen |
| X77 | New builders denied before `complete` | Denied |
| X78 | Old+new builders never both executable | Exact |
| X79 | Advisory lock alone does not permit runtime once frozen | Exact |
| X80 | Allowlist grant only after version 9 in restore txn A | Exact |
| X81 | G12 credential without proposal id | Reject |
| X82 | G13 proposal A vs B isolation | Isolated |
| X83 | G14 provider-only ambiguous lookup | Reject |
| X84 | G15 wrong binding | Reject |
| X85 | G16 wrong scope | Reject |
| X86 | G17 expired/superseded credential | Reject |
| X87 | G18 no secret material | Assert |
| X88 | GT06 branching | Reject |
| X89 | GT07 cross-scope | Reject |
| X90 | GT08 child proposal mismatch | Reject |
| X91 | GT09 child provider mismatch | Reject |
| X92 | GT10 child model mismatch | Reject |
| X93–X106 | V01–V14 activation prerequisites | Fail closed |
| X107–X113 | V16–V22 activation mutations / window | Exact |
| X114 | S08 missing digest | Fail; v8; frozen |
| X115 | S09 missing gen_random_uuid | Fail; v8; frozen |
| X116 | S10 wrong pgcrypto schema | Fail; v8; frozen |
| X117 | S11 public crypto resolve | Fail; v8; frozen |
| X118 | S12 pg_temp crypto resolve | Fail; v8; frozen |
| X119 | S13 unqualified crypto | Fail; v8; frozen |
| X120–X128 | B18–B28 discrepancy/fingerprint | Exact incl. literal B25 |
| X129 | M21 State B independent completeness | Exact |
| X130 | M22 digest mismatch → failed_frozen | Exact |
| X131 | M36 State A equality | Exact |
| X132 | M37 State C | failed_frozen |
| X133 | M38 unique recovery phase | Exact |
| X134 | L11–L15 trigger inventory | Exact |
| X135 | L16 function inventory closed-world | Exact |
| X136 | L17 table-role matrix closed-world | Exact |
| X137 | M01 preflight no mutation | Exact |
| X138 | M03 no preflight upsert | Absent |
| X139 | M04 unexpected role blocks | Block |
| X140 | M05 unexpected executable function blocks | Block |
| X141 | M06 unexpected function owner blocks | Block |
| X142 | M07 unexpected caller role blocks | Block |
| X143 | M08 unexpected writable table blocks | Block |
| X144 | M09 unexpected writable role blocks | Block |
| X145 | M10 inherited write blocks | Block |
| X146 | M11 column-level write mismatch blocks | Block |
| X147 | M16 every transform checkpoint has catalog evidence | Exact |
| X148 | M17 checkpoint flag without catalog evidence fails | Fail |
| X149 | M18 catalog without checkpoint fails | Fail |
| X150 | M19 each reconciliation category predicate | Exact |
| X151 | M20 every source row one category | Exact |
| X152 | M24 restore txn A commits while entrypoints blocked | Exact |
| X153 | M26 partial grant verify failure → separate re-revoke | Exact |
| X154 | M27 aborted grant txn no same-txn recovery | Exact |
| X155 | M28 fail-revoke failure → BLOCKED_OWNER_RECOVERY | Exact |
| X156 | M29 runtime_restoring no grants → txn A | Exact |
| X157 | M30 runtime_restoring partial grants → re-freeze first | Exact |
| X158 | M31 complete ACL mismatch → failed_frozen | Exact |
| X159 | M32 old builders unavailable throughout restoration | Exact |
| X160 | M33/M34 new builders only after complete | Exact |
| X161 | GT01 | Reject |
| X162 | GT02 | Reject |
| X163 | GT03 | Accept |
| X164 | GT04 | Exact |
| X165 | GT05 | Disabled |
| X166 | Freeze rollback no false marker (M12) | Exact |
| X167 | Frozen v9 recovery (M23/M24) | Exact |
| X168 | Entrypoint gate denies when state=`runtime_restoring` | Denied |
| X169 | PUBLIC never receives elevated grants during restore | Exact |
| X170 | GRANT ALL never used in restore scripts | Static assert |
| X171 | Schema-8 builder EXECUTE never restored | Exact |
| X172 | Reconciliation algorithm version pinned `schema9_reconcile_v1` | Exact |
| X173 | All 18 checkpoint ids present before reconcile | Exact |
| X174 | paid usage USD 0.00 after restore suites | Exact |

---

## 12. Pass criteria

Implementation `PASS` only if Revision 7 redesign requirements hold and:

1. Preflight performs no durable mutation and writes no cutover row
2. Closed-world function and table-role inventories match catalog or block
3. Durable freeze commits before any transform; independently verified
4. All 18 transform checkpoints have matching `catalog_digest` evidence
5. Every reconciliation category has one predicate; State B independently recomputes completeness
6. Version remains 8 until validate-under-freeze; frozen v9 recoverable
7. Restoration uses txn A → verify → txn B; failure uses a **new** revoke txn
8. Entrypoints deny until `complete`
9. Crypto S08–S14 and GT01–GT10 pass
10. X01–X174 pass; zero HTTP/model calls; gemini disabled; USD 0.00 paid usage
