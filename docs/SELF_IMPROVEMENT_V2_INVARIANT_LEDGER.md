# Self-Improvement V2 — Invariant Ledger (draft)

**Status:** DRAFT — capture of properties established by independent Codex reviews and in-tree adversarial probes.  
**Not authorization.** This ledger does not authorize any HEAD or pilot.  
**HEAD context:** tip of `research-lab-self-improvement-v2-v3-gates` (see `git rev-parse HEAD`).  
**Design:** Option A+ (`docs/SELF_IMPROVEMENT_V2_TRUSTED_ORIGIN_DESIGN.md`).

## How to read

| Column | Meaning |
|--------|---------|
| ID | Stable invariant id |
| Property | Normative claim |
| Evidence | Review finding and/or test |
| Status | `established` / `accepted-residual` / `open` / `known-failing` / `withdrawn-if` |

---

## Established properties (Codex + probes)

| ID | Property | Evidence | Status |
|----|----------|----------|--------|
| INV-TO-01 | Launcher anchors are mandatory: absent `SRL_REPOSITORY_ROOT` or `SRL_REVIEWED_HEAD` ⇒ trusted-origin **REJECT** | Codex Finding 1; R5 no-env probe; `_require_launcher_anchors` | established |
| INV-TO-02 | CWD / package root / self-consistent pin inside an alternate checkout are **not** trust authority | Codex Finding 1 | established |
| INV-TO-03 | Expected digest of `trusted_origin.py` is held **outside** the checkout by the launcher; mismatch ⇒ refuse (fail-closed). Launcher defends drift/misconfig; D2-BYPASS is a **documented local-code-execution boundary**, not a missing gadget | Option A+; `install_launcher`; residual-risk boundary | established + boundary stated |
| INV-TO-05 | Pin is content-digest only; must not claim HEAD; `SRL_REVIEWED_HEAD` is sole HEAD claim and **must equal** live HEAD | Option A+; N11 repair | established |
| INV-TO-06 | Pin set **equals** static AST import closure of `runtime_bridge` (**AST-only** limit stated; not a full closed bootstrap against dynamic importlib/`__import__`; negative under-coverage test required) | N1 repair; `import_closure.py` | established |
| INV-TO-07 | Launcher installer has a **second** content pin (`launcher_pin.json`) equal to its own static import closure; negative under-coverage required; pin file digest recorded in out-of-repo attestation | R3 repair | established |
| INV-TO-08 | `load_runtime_config` refuses `repository_root` ≠ `SRL_REPOSITORY_ROOT` (guard lives in the loader, not only `main`); blank/whitespace `SRL_REPOSITORY_ROOT` ≡ absent (structured refuse, same as missing) | R4 / V-R4 | established |
| INV-WF-01 | Absolute loopback origin pin is `http://127.0.0.1:8765` — **rigidity is the control**; making the port/host configurable reopens N2 | absolute-origin repair | established |
| INV-WF-02 | Agent attachments: exactly one `ai_languageModel` per agent; `ai_tool` / `ai_memory` / unknown channels **deny-by-default** — **rigidity is the control**; making attachments configurable reopens R1 / P1d cost-bound bypass | R1 repair | established |
| INV-BUD-01 | Boolean JSON must not coerce into pilot budget numeric fields | Codex Finding 5 | established |
| INV-BUD-02 | Boolean `maxIterations` must not satisfy `maxIterations==1` via `int(True)` | Codex Finding 6 | established |
| INV-BUD-03 | Provider-call consume validates role-bound provider/model/credential atomically; omit does not burn nonce | Codex Finding 3/4 | established |
| INV-BUD-04 | `/v2/provider-call-authorize` sits on the main path **immediately before** each role’s agent (model invocation); Agent→Authorize post-hoc is rejected by validators | V-TRANSPORT repair; `test_d1_*` | established |
| INV-AUTH-01 | Risk authority is sole authorizer; agent nodes are inactive-by-design and non-authoritative | agent-runtime contract + workflow inactive flag | established (process) |
| INV-AUTH-02 | **Build-review independence:** cross-family independent review required to *discharge* before written pilot authorization. Cursor cannot restore revoked auth via self-review; operator issues the auth line. Distinct from **loop independence** (Gemini/Groq). **Discharged** for the Codex-reviewed range ending `1a1c48e6fcf1abffebfefd1001505aaf83c02cf3` (verdict `REPAIR_REQUIRED` — independence yes; technical PASS still open on repaired tip). Same-family residual (INV-RES-02) is **unnecessary while Codex is working** | residual-risk doc; Codex wide review `2026-08-16` | established (process); discharged for that range |
| INV-RES-01 | Residual acceptance of Findings 1–3 (trusted-origin boundary) is one-run, docs-only, supervised, expires on use; withdraws if mandatory no-env R5 REJECTS at reviewed HEAD | `docs/SELF_IMPROVEMENT_V2_P3C1_ACCEPTED_RESIDUAL_RISK.md` | decision artifact |
| INV-RES-02 | Residual acceptance of **same-family build review** for pilot #1 only — **dormant / unnecessary while non-family reviewer is working.** Do not authorize under this residual when Codex (or equivalent) is dispatchable. Re-activation requires a new written operator decision if cross-family review becomes unavailable | residual-risk doc § build-review residual | dormant (Codex path active) |

## Known-failing (out of SI2 scope)

| ID | Property | Evidence | Status |
|----|----------|----------|--------|
| INV-R5A-01 | Round 5A Phase D manifest integrity: on-disk Round5A artifact digests must match registry expectations | Settled RED→RED at `e85c42ee` and SI2 candidate tips. Validator error-class multiset (identical at both ends): `R5A-MANIFEST-HASH`×13 + `R5A-PROV-SOURCE-PROVENANCE-HASH`×3 + `R5A-PROV-SOURCE-RECREATED-HASH`×3 (19 errors). Across Round5A suites (`test_generate_round5a_docs.py` + `test_validate_round5a.py` + `tests/round5a_kernel`) **32 tests fail** (identical at base and tip). Narrow `test_validate_round5a.py` alone is 4 fail / 34 pass of 38 collected — do not cite that slice as the integrity claim. SI2 candidate diffs do not touch Round5A paths | **known-failing** (Round 5A round; do not treat as SI2 regression) |

## Withdrawal hooks

- If mandatory no-env external R5 **REJECTS** at the HEAD under review ⇒ Findings 1–3 **closed by evidence**; INV-RES-01 acceptance **withdrawn**.
- If trusted-origin design session picks a new root-of-trust model ⇒ re-derive INV-TO-*; do not patch under the old model without that decision.

## Explicitly not established

- Codex **technical PASS** on the post-repair tip (parse-strictly-or-reject at `1c8e2b9536861fff8b42dc2228c32c23cdd3549a` or later) — **open** until the next Codex round returns clean. Prior Codex at `1a1c48e6fcf1abffebfefd1001505aaf83c02cf3` was `REPAIR_REQUIRED` (validator class) with V-ROOT / V-ABSENT / V-PRESENT / V-TRANSPORT PASS.
- Any P3-C1 authorization line — **absent**.
- Unsupervised / code-touching pilots while assurance is open — **forbidden** (hard gate).
- Launcher attestation HEAD equality / hash stability and n8n credential **name-binding** (store re-point with stable reference name) — **held** for a later brief; not claimed closed by the NP-2 embedded-value fix.
