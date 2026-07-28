# Round 5A — Security Boundary Test Plan (Revision 5)

**Status:** Design only. For schema ≥ 9 implementation.
**Baseline design:** `docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md` (Revision 5)
**Actors:** `APP`=`research_app`, `GOV`=`research_governance`, `N8N`=`n8n_app`, `OWN`=`postgres`, `TEST`=`research_test`
**Rule:** Adversarial cases expect permission denied / execute denied / fail-closed builder errors. Governance happy paths use `BEGIN…ROLLBACK` or disposable fixtures that never leave production pilot active/enabled.

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
| R01–R13 | As Revision 4 plus `research_crypto` CREATE/USAGE denial | Exact |

---

## 2. Allowlist / trigger inventory (L)

| ID | Probe | Expect |
| --- | --- | --- |
| L01–L10 | As Revision 4 | Exact |
| L11 | All five exact trigger names exist | Exact |
| L12 | Each trigger attached to exact expected table | Exact |
| L13 | Each trigger uses exact expected trigger function | Exact |
| L14 | Trigger enablement = ENABLE | Exact |
| L15 | Catalog drift in any trigger name/attachment fails validation | Fail |

---

## 3. Application gate attacks (A)

| ID | Attack as APP | Expect |
| --- | --- | --- |
| A01–A16 | As Revision 4 | Exact |

---

## 4. Governance chain and credential scope (G)

| ID | Check |
| --- | --- |
| G01–G19 | As Revision 4 chain semantics | Exact |
| G20 | Credential confirmation without proposal ID fails | Reject |
| G21 | Credential confirmation for proposal A does not affect proposal B | Isolated chains |
| G22 | Provider-only ambiguous lookup fails (no proposal id path) | Absent / reject |
| G23 | Wrong proposal/provider binding fails | Reject |
| G24 | Wrong governance action scope fails | Reject |
| G25 | Expired or superseded credential action fails | Reject |
| G26 | Credential confirmation stores no secret material | Catalog/payload assert |
| G27 | Cross-scope supersession rejected | Reject |
| G28 | Child proposal identifier mismatch rejected | Reject |
| G29 | Child provider identifier mismatch rejected | Reject |
| G30 | Child model identifier mismatch rejected | Reject |
| G31 | Concurrent child creation cannot branch a chain | Unique / reject |

---

## 5. Capacity / accounting (B)

| ID | Check |
| --- | --- |
| B01–B17 | As Revision 4 | Exact |
| B18 | Arbitrary extra JSON fields cannot be submitted to recorder | No JSONB param / reject |
| B19 | Recorder reconstructs payload from typed inputs | Exact |
| B20 | Invalid scalar types fail | Reject |
| B21 | Negative count or token values fail | Reject |
| B22 | Monetary precision overflow fails | Reject |
| B23 | `0`, `0.0`, `0.00000000` produce same fingerprint | Match |
| B24 | Different monetary values produce different fingerprints | Differ |
| B25 | Canonical example payload text hashes via `sha256_hex` stably | Match redesign §8.1.1 |
| B26 | Caller-supplied matching hash for non-canonical payload rejected | Reconstruct mismatch |
| B27 | Duplicate canonical report idempotent | Same id |
| B28 | Recorder failure leaves request blocked | Exact |

---

## 6–8. Round 4 / SECURITY DEFINER / helpers (C, S, H)

As Revision 4, plus:

| ID | Check |
| --- | --- |
| S11 | Failure to move pgcrypto keeps schema version 8 and runtime frozen | Exact |
| S12 | Wrong pgcrypto schema keeps runtime frozen | Exact |
| S13 | Missing `research_crypto.digest` keeps runtime frozen | Exact |
| S14 | Unqualified crypto reference detection fails migration assertions | Exact |

---

## 9. Migration freeze and restart (M)

| ID | Check |
| --- | --- |
| M01 | Schema 9 re-run restart-safe at every step boundary 1–20 | Exact |
| M02 | Schema-8 pilot builder denied immediately after freeze (step 3) | EXECUTE denied |
| M03 | Schema-8 / non-pilot builder denied immediately after freeze | Denied |
| M04 | `live_preflight` denied immediately after freeze | Denied |
| M05 | Orchestration entrypoint cannot reach provider logic during cutover | Denied / no provider path |
| M06 | Direct envelope insertion remains denied | Denied |
| M07 | Runtime remains blocked after failure at every migration step | Frozen |
| M08 | New builders remain denied before final schema-9 assertions | Denied until step 20 |
| M09 | Old and new builders never executable simultaneously | Matrix assert |
| M10 | Advisory-lock absence does not permit runtime execution once frozen | Marker+REVOKE hold |
| M11 | Exact schema-9 allowlist granted only after `cutover_complete` | Step 20 only |
| M12 | Restart from State A succeeds deterministically | Exact |
| M13 | Restart from State B succeeds deterministically | Exact |
| M14 | Both original and legacy tables present fails closed | State C |
| M15 | Neither table present fails closed | State C |
| M16 | No duplicate events after State B restart | Exact |
| M17 | No duplicate archive rows after State B restart | Exact |
| M18 | No post-rename State B step references original table name | Static/catalog assert |
| M19 | Version remains 8 for every failed restart branch before step 18 | Exact |
| M20 | Default privileges / no GUC / disabled gemini / zero activations | As prior M03–M05 |

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

## 11. Required adversarial index (X01–X70 retained + X71–X140)

Retain Revision 4 X01–X70 meanings where still valid. Add:

| ID | Probe | Expect |
| --- | --- | --- |
| X71 | Schema-8 pilot builder denied immediately after freeze | Denied |
| X72 | Non-pilot builder denied immediately after freeze | Denied |
| X73 | `live_preflight` denied immediately after freeze | Denied |
| X74 | Orchestration cannot reach provider logic during cutover | Denied |
| X75 | Direct envelope insert denied during cutover | Denied |
| X76 | Runtime blocked after failure at every step | Frozen |
| X77 | New builders denied before final assertions | Denied |
| X78 | Old+new builders never both executable | Exact |
| X79 | Advisory lock alone does not permit runtime once frozen | Exact |
| X80 | Allowlist grant only after `cutover_complete` | Exact |
| X81–X87 | Credential scope probes G20–G26 | Exact |
| X88–X92 | Chain scope probes G27–G31 | Exact |
| X93–X106 | Activation prerequisite probes V01–V14 | Exact |
| X107–X113 | Activation mutation probes V16–V22 | Exact |
| X114–X117 | Crypto placement probes S11–S14 | Exact |
| X118–X128 | Discrepancy canonicalization B18–B28 | Exact |
| X129–X136 | Post-rename restart M12–M19 | Exact |
| X137–X140 | Trigger inventory L11–L15 | Exact |

---

## 12. Pass criteria

Implementation `PASS` only if Revision 5 redesign requirements hold and:

1. Runtime is privilege-blocked from step 3 through step 19
2. Exact schema-9 grants occur only at step 20 after `cutover_complete`
3. Credential confirmation is proposal-scoped
4. Discrepancy recorder accepts typed scalars only and reconstructs payloads
5. Monetary canonicalization matches §8.1
6. State A/B/C restart branches are enforced
7. All five exact trigger objects exist and attach correctly
8. Each activation prerequisite has an independent failing probe
9. X71–X140 and retained X01–X70 pass
10. Zero HTTP/model calls; gemini remains disabled; no production activation
