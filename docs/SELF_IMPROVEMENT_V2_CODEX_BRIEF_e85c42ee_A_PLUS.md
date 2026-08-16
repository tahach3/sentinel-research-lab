# Independent review brief — Self-Improvement V2 Option A+ (launcher + authorize-before-model)

**Paste target:** Codex (or equivalent independent reviewer)  
**Mode:** Read-only security assurance of **defensive integrity gates**  
**Not requested:** exploit development, unauthorized access guidance, live pilot execution, or mid-review implementation

**Dispatch rule:** Reviewed HEAD **must** equal `git rev-parse HEAD` on `research-lab-self-improvement-v2-v3-gates` at paste time. Range end is that same tip. Range start is fixed below.

---

## Authorization context (read first)

| Fact | Value |
|------|-------|
| Pilot authorization | **DOES NOT EXIST** — nothing to revoke; this review does not create it |
| Workflow | `workflows/design/self_improvement_loop_v2.json` is **inactive by design** |
| Base (prior Codex verdict) | `e85c42ee434cf93346f14f3a890e5fb1385cb06d` — **ESCALATE** |
| Reviewed HEAD | *(paste `git rev-parse HEAD` at send)* |
| Review range | `e85c42ee434cf93346f14f3a890e5fb1385cb06d` .. *(same tip)* |
| Branch push policy | Review branch **may be pushed** for PR visibility; **no merge**, **no deploy**, **no pilot**, **no authorization line** from this review |
| Operator intent | Independent assurance before any later written authorization |
| Authorization line | After PASS, Claude may **recommend** an exact HEAD; only the **operator** issues the authorization line (and refreshes the out-of-repo launcher digest in the same action) |

A PASS here is a precondition for a later authorization decision. It is **not** authorization to run P3-C1.

---

## Prior ESCALATE coverage (e85c42ee)

| ID | Severity | Defect | This candidate |
|----|----------|--------|----------------|
| F1 | CRITICAL | Unpinned entrypoint / git_worker; forged preload | Closed bootstrap pin + dirty/digest reject |
| F2 | HIGH | disabled authority + router accept | Both validators |
| F3 | HIGH | Verifier self-auth / no out-of-repo digest root | Out-of-repo launcher holds expected `trusted_origin.py` digest |
| F3/F4 transport | HIGH | Authorize missing or post-hoc | `/v2/provider-call-authorize` on main path **before** agent both roles; validators reject Agent→Authorize |
| F5 | MEDIUM | bool→int coercion | Strict ints |
| F6 | LOW | docs / status | Cleanup |

---

## Out-of-range tests (settled — do not re-spend review capacity)

Exact **32** Round5A suite failures (**RED→RED** at `e85c42ee` and SI2 tips; same count both ends), with validator error multiset `R5A-MANIFEST-HASH`×13 + provenance×3 + recreated×3. Candidate does not touch Round5A paths. Ledgered as **INV-R5A-01 known-failing** (Round 5A), not an SI2 regression.

---

## System under review

Primary: `trusted_origin.py`, `pilot_budget.py`, `runtime_bridge.py`, `workflow_validator.py`, `agent_runtime_contract.py`, `launcher/install_launcher.py`, pin, inactive workflow.

Launcher install target (outside checkout): `%LOCALAPPDATA%\SentinelResearchLab\` or `$XDG_DATA_HOME/SentinelResearchLab/`.

---

## Verdict vocabulary (exactly one)

- **PASS**
- **REPAIR_REQUIRED**
- **ESCALATE**

---

## Part A

### V1 — Authority / non-goals
No live credentials; no deploy; policy enforcement + `tests/self_improvement_v2/` probes.

### V2 — Trusted-origin fail-closed
Absent anchors reject; pin content-only; dirty/digest mismatch on pinned modules reject under valid anchors.

### V-LAUNCH — VERIFIER AUTHENTICATION ROOT (required)
Where is the expected digest of `trusted_origin.py` held? Must be **outside** the repository under review. Confirm installer refuses install-dir inside the checkout. Confirm mismatch refuses (exit non-zero). Confirm matching digest sets `SRL_REPOSITORY_ROOT` / `SRL_REVIEWED_HEAD` from the launcher (not manual shell as attested source). If expected digest only lives in-repo, Finding 3 remains open — report regardless of unit greens.

### V3 — R0 / R5
Reproduce R5 no-env reject and A+/D1/D2 matrix probes (`docs/SELF_IMPROVEMENT_V2_OPTION_A_PLUS_R0_MATRIX.md`).

---

## Part B

### V4 — Budget coercion
Booleans must not become token ceilings / grants.

### V5 — Consume atomicity
Omit identity rejects without burning nonce; correct consume once.

### V-TRANSPORT — live authorize before model (required)
Trace edges: must be `Permit → Consume → Authorize → Agent` on **both** roles. `Agent → Authorize` is FAIL. Endpoint-without-pre-model-edge is the prior Finding-4 defect under a new name.

### V6 — Residual / design
Residual does not authorize a HEAD; launcher/forged-auth-line residual boundary stated; digest refresh tied to authorization-line action.

### V7 — Five novel probes
Required. Prefer: launcher install inside repo, stale digest after verifier edit, authorize edge drift, consume-fail replay vs authorize-spend, disabled authority.

---

## Out of scope

- Live P3-C1 / authorization / merge
- Mid-review implementation
- Re-deriving Round5A **32-failure** arithmetic (known-failing; verify RED→RED identity, do not burn review budget)

## Split protocol

Part A (V1–V3 + V-LAUNCH) first if filters trip; then Part B (V4–V7 + V-TRANSPORT).
