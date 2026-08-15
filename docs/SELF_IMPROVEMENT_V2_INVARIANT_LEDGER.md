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
| INV-TO-03 | Expected digest of `trusted_origin.py` is held **outside** the checkout by the launcher; mismatch ⇒ refuse (fail-closed) | Option A+; `install_launcher`; `test_d2_*` | established (re-prove on assurance review) |
| INV-TO-05 | Pin is content-digest only; must not claim HEAD; `SRL_REVIEWED_HEAD` is sole HEAD claim | Option A+ | established |
| INV-BUD-01 | Boolean JSON must not coerce into pilot budget numeric fields | Codex Finding 5 | established |
| INV-BUD-02 | Boolean `maxIterations` must not satisfy `maxIterations==1` via `int(True)` | Codex Finding 6 | established |
| INV-BUD-03 | Provider-call consume validates role-bound provider/model/credential atomically; omit does not burn nonce | Codex Finding 3/4 | established |
| INV-BUD-04 | `/v2/provider-call-authorize` sits on the main path **immediately before** each role’s agent (model invocation); Agent→Authorize post-hoc is rejected by validators | V-TRANSPORT repair; `test_d1_*` | established |
| INV-AUTH-01 | Risk authority is sole authorizer; agent nodes are inactive-by-design and non-authoritative | agent-runtime contract + workflow inactive flag | established (process) |
| INV-AUTH-02 | Independent external PASS is required before written pilot authorization; Cursor cannot restore revoked auth via self-review; operator issues the auth line | residual-risk doc | established (process) |
| INV-RES-01 | Residual acceptance of Findings 1–3 is one-run, docs-only, supervised, expires on use; withdraws if mandatory no-env R5 REJECTS at reviewed HEAD | `docs/SELF_IMPROVEMENT_V2_P3C1_ACCEPTED_RESIDUAL_RISK.md` | decision artifact |

## Known-failing (out of SI2 scope)

| ID | Property | Evidence | Status |
|----|----------|----------|--------|
| INV-R5A-01 | Round 5A Phase D manifest integrity (`R5A-MANIFEST-HASH`): registry expected digests match on-disk Round5A artifact SHA-256 | Settled RED→RED (32/32) at `e85c42ee` and SI2 candidate tips; error class `R5A-MANIFEST-HASH`; SI2 candidate diffs do not touch Round5A paths | **known-failing** (Round 5A round; do not treat as SI2 regression) |

## Withdrawal hooks

- If mandatory no-env external R5 **REJECTS** at the HEAD under review ⇒ Findings 1–3 **closed by evidence**; INV-RES-01 acceptance **withdrawn**.
- If trusted-origin design session picks a new root-of-trust model ⇒ re-derive INV-TO-*; do not patch under the old model without that decision.

## Explicitly not established

- Codex **PASS** on the current A+ range — **open** until independent review returns.
- Any P3-C1 authorization line — **absent**.
- Unsupervised / code-touching pilots while assurance is open — **forbidden** (hard gate).
