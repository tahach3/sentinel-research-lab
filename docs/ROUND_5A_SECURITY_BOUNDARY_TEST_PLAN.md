# Round 5A — Security Boundary Test Plan (Revision 6)

**Status:** Design only. For schema ≥ 9 implementation.
**Baseline design:** `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md` (Revision 6)
**Actors:** `APP`=`research_app`, `GOV`=`research_governance`, `N8N`=`n8n_app`, `OWN`=`postgres`, `TEST`=`research_test`
**Rule:** Adversarial cases expect permission denied / execute denied / fail-closed builder errors. Governance happy paths use `BEGIN…ROLLBACK` or disposable fixtures that never leave production pilot active/enabled.

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
| R07 | Only `OWN` can `GRANT research_governance TO …` | Documented + attempted grant as APP fails |
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
| L03 | Every Appendix A.4 function with research_app EXECUTE=Y is executable by APP | Succeeds (call smoke) |
| L04 | Every research function with research_app EXECUTE=N fails EXECUTE for APP | Denied |
| L05 | Non-allowlisted sample: `activate_pilot_authorization`, `enable_provider_for_pilot`, `_r4_arm_provider` | Denied for APP |
| L06 | Permission-drift CI query fails build on mismatch | Drift detected |
| L07 | Sequence inventory: zero sequences in `research` at schema 8/9 baseline; any future sequence ACL = NONE for APP/N8N/GOV/PUBLIC | Exact |
| L08 | Every function overload signature in Appendix A.4 present with exact identity arguments | Exact match |
| L09 | Views match Appendix A.2 | Exact |
| L10 | `schema9_cutover_state` and `schema9_cutover_checkpoints` privileges = NONE for APP/N8N/GOV/TEST/PUBLIC | Exact |
| L11 | All five exact trigger names exist | Exact |
| L12 | Each trigger attached to exact expected table | Exact |
| L13 | Each trigger uses exact expected trigger function | Exact |
| L14 | Trigger enablement = ENABLE | Exact |
| L15 | Catalog drift in any trigger name/attachment fails validation | Fail |

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
| A08 | Call any listed Round 4/5 arm/reset/fixture helper still in `research` | Absent or EXECUTE denied |
| A09 | `INSERT`/`UPDATE`/`DELETE` `pilot_capacity_events` | Denied |
| A10 | `INSERT`/`UPDATE`/`DELETE` `live_request_envelopes` | Denied |
| A11 | Change an event's `envelope_id` | Denied / trigger reject |
| A12 | `record_authorization_spend` on pilot-linked auth | Fail closed |
| A13 | `INSERT`/`UPDATE`/`DELETE` `accounting_discrepancies` | Denied (INSERT only via DEFINER) |
| A14 | `CREATE TABLE` / `CREATE FUNCTION` in schema `research` | Denied |
| A15 | Direct write on any freeze-matrix governed table during cutover | Denied |
| A16 | Call frozen schema-8 builders while cutover state ≠ `complete` | EXECUTE denied |

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
| G07 | Activate after enable → immutable 24h window; proposal unchanged | Exact |
| G08 | Altered material fingerprint invalidates prior approval for enable/activate | Fail closed |
| G09 | Duplicate / copied / stale / superseded / revoked / conflicting actions | Deterministic reject |
| G10 | Second activate / active→proposed / expired renew in place | Reject; renewal needs new row |
| G11 | Disable provider/model → new preflight/envelope denied; capacity unchanged | Exact |
| G12 | Credential confirmation without proposal ID fails | Reject |
| G13 | Credential confirmation for proposal A does not affect proposal B | Isolated chains |
| G14 | Provider-only ambiguous lookup fails (no proposal id path) | Absent / reject |
| G15 | Wrong proposal/provider binding fails | Reject |
| G16 | Wrong governance action scope fails | Reject |
| G17 | Expired or superseded credential action fails | Reject |
| G18 | Credential confirmation stores no secret material | Catalog/payload assert |
| G19 | Concurrent child creation cannot branch a chain | Unique / reject |

### 4.1 Explicit governance transition tests (Revision 6)

| ID | Check | Expect |
| --- | --- | --- |
| GT01 | enable → enable rejection (second enable without intervening disable) | Reject; no row |
| GT02 | disable → disable rejection (second disable without intervening enable) | Reject; no row |
| GT03 | valid enable → disable → enable | Accept each legal transition |
| GT04 | terminal-only enabled-state detection | Only terminal enable counts as enabled |
| GT05 | historical enable does not override terminal disable | Disabled while terminal is disable |
| GT06 | branching child rejection | Reject second child of same parent |
| GT07 | cross-scope supersession rejection | Reject |
| GT08 | child proposal mismatch | Reject |
| GT09 | child provider mismatch | Reject |
| GT10 | child model mismatch | Reject |

---

## 5. Capacity / accounting (B)

| ID | Check | Expect |
| --- | --- | --- |
| B01 | First pilot envelope → one `attempt_consumed` normal + one envelope; same pre-generated id | Exact |
| B02 | Idempotent replay → same envelope; event count unchanged | Exact |
| B03 | Alternate idempotency key same case → blocked | Exact |
| B04 | Fourth total request blocked (events only) | Exact |
| B05 | Token limits from event projected sums only | Exact |
| B06 | Success cap from non-fixture ledger `success` only | Exact |
| B07 | Cost > 0 blocked | Exact |
| B08 | Retry/fallback/confidential blocked; no event | Exact |
| B09 | Mid-txn failure rolls back event+envelope | Exact |
| B10 | Concurrent final slot → 1 ok / 1 blocked | Exact |
| B11 | Abandoned path: event committed, no later success → attempt still consumed | Exact |
| B12 | Enforcement never uses `COUNT(events)+SUM(ledger.request_count)` | Unit assert |
| B13 | Conflicting legacy ledger vs events → fail closed + discrepancy fingerprint | Exact |
| B14 | APP cannot insert/update/delete capacity events | Denied |
| B15 | Legacy null-envelope reserved/finalized → `legacy_orphan` consumption | Exact |
| B16 | Released legacy → archive only; zero attempt_consumed | Exact |
| B17 | Post-rename builders independent of original table name | Exact |
| B18 | Arbitrary extra JSON fields cannot be submitted to recorder | No JSONB param / reject |
| B19 | Recorder reconstructs payload from typed inputs | Exact |
| B20 | Invalid scalar types fail | Reject |
| B21 | Negative count or token values fail | Reject |
| B22 | Monetary precision overflow fails | Reject |
| B23 | `0`, `0.0`, `0.00000000` produce same fingerprint | Match literal |
| B24 | Different monetary values produce different fingerprints | Differ |
| B25 | Canonical example payload text hashes to literal normative fingerprint | Match `c79c93716d543b36954e599c5e1d1a6e5cf74b9d6215f25319cb2296833dc957` via independent digest (not the production function under test) |
| B26 | Caller-supplied matching hash for non-canonical payload rejected | Reconstruct mismatch |
| B27 | Duplicate canonical report idempotent | Same id |
| B28 | Recorder failure leaves request blocked | Exact |

---

## 6. Round 4 compatibility (C)

| ID | Check | Expect |
| --- | --- | --- |
| C01 | `build_non_pilot_request_envelope` succeeds for non-pilot auth when Round 4 gates armed in rolled-back fixture | Exact |
| C02 | Same function rejects pilot-linked auth | Reject |
| C03 | `build_provider_request_envelope` requires `pilot_proposal_id IS NOT NULL` | Exact |
| C04 | Direct `INSERT` envelopes denied to APP | Denied |
| C05 | Documented Round 4 adapter entrypoint = non-pilot builder | Exact |
| C06 | Both builders share exact same argument signature | Catalog identity match |

---

## 7. SECURITY DEFINER / crypto placement (S)

| ID | Check | Expect |
| --- | --- | --- |
| S01 | All elevated functions: `prosecdef` and `proconfig` search_path=`pg_catalog` | Exact |
| S02 | Malicious `pg_temp` function/table shadowing names does not alter DEFINER resolution | Attack fails |
| S03 | APP cannot `CREATE OR REPLACE` / `ALTER OWNER` on research functions | Denied |
| S04 | Function owners remain `postgres` | Assert |
| S05 | Ownership replacement by APP denied | Denied |
| S06 | Unqualified reference detection in every elevated function body | Zero unqualified research object refs |
| S07 | Shadow table in `research` created by APP | CREATE denied |
| S08 | Missing `research_crypto.digest(...)` | Transform/validate fails; version remains 8; runtime remains frozen |
| S09 | Missing `research_crypto.gen_random_uuid()` | Transform/validate fails; version remains 8; runtime remains frozen |
| S10 | pgcrypto installed in the wrong schema | Fail; version 8; runtime frozen |
| S11 | Elevated function resolving a crypto symbol from `public` | Fail assert; version 8; runtime frozen |
| S12 | Elevated function resolving a crypto symbol from `pg_temp` | Fail assert; version 8; runtime frozen |
| S13 | Any unqualified crypto call in schema-9 elevated-function definitions | Fail assert; version 8; runtime frozen |
| S14 | After each of S08–S13, `max(schema_version)=8` and cutover ACLs remain revoked | Exact |

---

## 8. Helper isolation (H)

| ID | Check | Expect |
| --- | --- | --- |
| H01 | Every moved helper identity absent from `research` or non-executable by APP/N8N/GOV | Exact |
| H02 | Helpers present only under `research_test` with no APP/N8N/GOV USAGE | Exact |
| H03 | Inventory query for `%arm%|%reset%|_r3|_r4|_r5a|cleanup_test|record_pilot_usage_for_tests` in `research` = empty or classified MOVED | Exact |

---

## 9. Multi-transaction cutover controller (M)

Controller under test (design): `scripts/schema9-cutover.ps1` + separately committed phase SQL. No single all-or-nothing migration assumption. Advisory lock is not runtime protection.

| ID | Check | Expect |
| --- | --- | --- |
| M01 | Fresh v8, no freeze marker → recovery selects `preflight` then `runtime_freezing` | Classification #1 |
| M02 | Freeze transaction failure rolls back; no `runtime_frozen` marker; no transform begins | Exact |
| M03 | Freeze commit then independent verify session re-reads ACLs before transform | Exact |
| M04 | Schema-8 pilot builder denied immediately after durable freeze | EXECUTE denied |
| M05 | Non-pilot / schema-8 builders denied after durable freeze | Denied |
| M06 | `live_preflight` denied after durable freeze | Denied |
| M07 | `orchestrate_research_run` / `run_stage` cannot reach provider logic during cutover | Denied |
| M08 | Direct envelope insertion remains denied | Denied |
| M09 | Runtime remains blocked after failure at every phase/checkpoint | `failed_frozen` or frozen ACLs |
| M10 | New builders remain non-executable until `complete` | Denied until restore asserts pass |
| M11 | Old and new builders never executable simultaneously | Matrix §13.7 |
| M12 | Advisory-lock absence does not permit runtime once frozen | Marker+REVOKE hold |
| M13 | Exact schema-9 allowlist granted only in `runtime_restoring` after version 9 | Exact |
| M14 | Version remains 8 through freeze, transform, reconcile, validate | Exact |
| M15 | Version advances to 9 only after validation under durable freeze | Separate commit |
| M16 | Restart with `schema_version=9`, state `version_advanced`, ACLs revoked → `runtime_restoring` | Classification #7 |
| M17 | Restart with restore incomplete → retry exact grants or `failed_frozen`; never schema-8 restore | Classification #8 |
| M18 | Restart from `complete` is catalog-verify no-op success | Classification #9 |
| M19 | Contradictory state/catalog → `failed_frozen` + owner intervention | Classification #10 |
| M20 | State A predicates all true before rename; restart resumes A path | Exact |
| M21 | State B predicates all true; no recovery step references original table name | Exact |
| M22 | State C (both or neither reservation names) → `failed_frozen`; no version advance | Exact |
| M23 | No duplicate capacity events after State B restart | Exact |
| M24 | No duplicate archive rows after State B restart | Exact |
| M25 | Final grant assert failure re-revokes schema-9 runtime grants and sets `failed_frozen` | Exact |
| M26 | Every phase leaves committed evidence (state and/or checkpoint row) | Exact |
| M27 | Every restart classification maps to exactly one recovery phase | §13.5 |
| M28 | Default privileges / no GUC / disabled gemini / zero activations after cutover | Exact |
| M29 | Every function in §13.3 freeze inventory has EXECUTE revoked after freeze commit | Exact |
| M30 | Every table in §13.4 matrix has write privileges revoked after freeze commit | Exact |

---

## 10. Activation prerequisites — independent probes (V)

Each of V01–V14: activation fails; `activated_at` remains null; `expires_at` unchanged; status remains proposed.

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

## 11. Required adversarial index (X01–X140)

Retain X01–X70 meanings from prior design revisions where still valid. Add / remap:

| ID | Probe | Expect |
| --- | --- | --- |
| X71 | Schema-8 pilot builder denied immediately after durable freeze | Denied |
| X72 | Non-pilot builder denied immediately after durable freeze | Denied |
| X73 | `live_preflight` denied immediately after durable freeze | Denied |
| X74 | Orchestration cannot reach provider logic during cutover | Denied |
| X75 | Direct envelope insert denied during cutover | Denied |
| X76 | Runtime blocked after failure at every phase | Frozen |
| X77 | New builders denied before `complete` | Denied |
| X78 | Old+new builders never both executable | Exact |
| X79 | Advisory lock alone does not permit runtime once frozen | Exact |
| X80 | Allowlist grant only after version 9 in `runtime_restoring` | Exact |
| X81–X87 | Credential scope probes G12–G18 | Exact |
| X88–X92 | Chain scope probes GT06–GT10 / G19 | Exact |
| X93–X106 | Activation prerequisite probes V01–V14 | Exact |
| X107–X113 | Activation mutation probes V16–V22 | Exact |
| X114 | Missing `research_crypto.digest` (S08) | Fail; v8; frozen |
| X115 | Missing `research_crypto.gen_random_uuid` (S09) | Fail; v8; frozen |
| X116 | Wrong pgcrypto schema (S10) | Fail; v8; frozen |
| X117 | Crypto resolve from `public` (S11) | Fail; v8; frozen |
| X118 | Crypto resolve from `pg_temp` (S12) | Fail; v8; frozen |
| X119 | Unqualified crypto in elevated defs (S13) | Fail; v8; frozen |
| X120–X128 | Discrepancy canonicalization B18–B28 including literal fingerprint B25 | Exact |
| X129–X136 | Restart classifications M16–M24 / State A/B/C | Exact |
| X137–X140 | Trigger inventory L11–L15 | Exact |
| X141 | GT01 enable→enable rejection | Reject |
| X142 | GT02 disable→disable rejection | Reject |
| X143 | GT03 enable→disable→enable | Accept |
| X144 | GT04 terminal-only enabled detection | Exact |
| X145 | GT05 historical enable vs terminal disable | Disabled |
| X146 | Freeze txn rollback leaves no false freeze marker (M02) | Exact |
| X147 | Frozen version-9 recovery path (M16) | Exact |
| X148 | Final grant failure re-revokes (M25) | Exact |

---

## 12. Pass criteria

Implementation `PASS` only if Revision 6 redesign requirements hold and:

1. Durable freeze commits in its own transaction before any transform
2. Freeze is independently verified in a new session before transform
3. Version remains 8 through freeze/transform/reconcile/validate
4. Version 9 with runtime still frozen is a valid recoverable state
5. Exact schema-9 grants occur only in `runtime_restoring` after version 9; assert failure re-revokes
6. Credential confirmation is proposal-scoped
7. Discrepancy recorder accepts typed scalars only; B25 compares to the literal normative fingerprint without using the production function under test for the expected value
8. State A/B/C restart branches and §13.5 classifications are enforced
9. Crypto placement probes S08–S14 pass
10. Explicit governance transition tests GT01–GT10 pass
11. All five exact trigger objects exist and attach correctly
12. Each activation prerequisite has an independent failing probe
13. X71–X148 and retained X01–X70 pass
14. Zero HTTP/model calls; gemini remains disabled; no production activation; USD 0.00 paid usage
