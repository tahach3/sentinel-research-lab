# Independent review brief — Self-Improvement V2 Option A+ candidate

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
| Base (prior Codex verdict) | `e85c42ee434cf93346f14f3a890e5fb1385cb06d` — **ESCALATE** (see coverage map below) |
| Reviewed HEAD | *(paste `git rev-parse HEAD` at send)* |
| Review range | `e85c42ee434cf93346f14f3a890e5fb1385cb06d` .. *(same tip)* |
| Candidate intent | Option A+ trusted bootstrap + companion blockers for F2/F3/F5/F6 |
| Operator intent | Independent assurance before any later written authorization |
| Authorization line | After PASS, Claude may **recommend** an exact HEAD; only the **operator** issues the authorization line (supervised / manually-triggered attestation) |

A PASS here is a precondition for a later authorization decision. It is **not** authorization to run P3-C1.

---

## Prior Codex ESCALATE at `e85c42ee` (coverage map for this candidate)

Terminal verdict was **ESCALATE**. Suite under SI2 was green; novel probes blocked PASS. Findings the candidate claims to address:

| ID | Severity | Defect (verbatim sense) | Candidate claim |
|----|----------|-------------------------|-----------------|
| F1 | CRITICAL | Unauthenticated / unpinned `runtime_bridge.py`, `git_worker.py`; forged preloaded verifier accepted | Expanded closed pin + dirty/digest reject + gated verifier load |
| F2 | HIGH | `disabled=true` on authority nodes + Worker Decision Router hardcoded accept | Both validators reject disabled authority + check router selector/rules |
| F3 | HIGH | Consume omits provider/model/credential; transport unbound; `assert_provider_call_authorized` test-only | Mandatory consume identity; `/v2/provider-call-authorize`; workflow nodes |
| F4 | HIGH | Residual said R5 closes F1–3 while Option A still required impl | Residual reconciled; R5 alone ≠ close F1–3 |
| F5 | MEDIUM | Permit endpoint boolean→int coercion | Strict nonneg int; bools rejected |
| F6 | LOW | Runtime docs missing `SRL_REVIEWED_HEAD`; token substring → 401 | Docs/runtime cleanup |

**Mandatory no-env R5 passed at base** (missing-anchor self-pin rejects) and does **not** by itself cover valid-anchor dirty entrypoint/`git_worker`.

Treat the table as the coverage checklist. Do not assume claims hold — prove or refute with probes.

---

## Out-of-range test transition (settled before dispatch — do not re-spend review on arithmetic)

Exact same **32** non-SI2 tests were run at base `e85c42ee` and at candidate tip (pre-brief-commit tip `768fa7c3798cb53e63700e78ed825e6a89b4a5d1`):

| Set | Base `e85c42ee` | Candidate tip |
|-----|-----------------|---------------|
| `tests/round5a_kernel/test_validate_kernel.py` (2) | **RED** | **RED** |
| `tests/test_generate_round5a_docs.py` (26) | **RED** | **RED** |
| `tests/test_validate_round5a.py` (4 of suite) | **RED** | **RED** |
| **Total** | **32 failed** | **32 failed** (exact match) |

**Transition: RED → RED (32/32).** Not introduced by `e85c42ee..768fa7c` (candidate diff touches **no** Round5A paths).

**Error class (not “env” handwave):** Phase D / validator reports `final_status=FAIL` with code **`R5A-MANIFEST-HASH`** — registry expected digests ≠ on-disk SHA-256 of Round5A tracked artifacts (example: `docs/ROUND_5A_EVIDENCE_PROVENANCE_DECISION.md` expected `42f0f6d5…` actual `92746d72…`). Generator then fails with `R5A-GEN-SOURCE-VALIDATOR` (“Phase D validator not PASS”). Same hashes at base and tip for sampled artifacts. Scope check for SI2 may treat these as out-of-range reds with a proven RED→RED transition.

SI2 adversarial suite at candidate: green when last measured (`tests/self_improvement_v2`).

---

## System under review (defensive purpose)

Local Research Lab worker + inactive n8n design workflow intended to:

1. Refuse to treat an arbitrary checkout / self-consistent pin as trust authority.
2. Bind trusted security modules to an **externally attested** launcher identity and verifier digest.
3. Enforce one-shot provider-call permits and typed pilot budget maxima, with authorize on the live workflow path **before** the model runs.
4. Keep AI agent nodes inactive and non-authoritative for risk decisions.

Primary modules: `tools/self_improvement_v2/trusted_origin.py`, `pilot_budget.py`, `runtime_bridge.py`, `risk_authority.py`, `review_gate.py`, `workflow_validator.py`, `agent_runtime_contract.py`, pin at `specs/self_improvement/v2/trusted_origin_pin.json`, workflow `workflows/design/self_improvement_loop_v2.json`.

Design / residual: `docs/SELF_IMPROVEMENT_V2_TRUSTED_ORIGIN_DESIGN.md`, `docs/SELF_IMPROVEMENT_V2_P3C1_ACCEPTED_RESIDUAL_RISK.md`, `docs/SELF_IMPROVEMENT_V2_OPTION_A_PLUS_R0_MATRIX.md`.

---

## Verdict vocabulary (exactly one)

- **PASS** — all mandatory checks and novel probes hold; no open CRITICAL/HIGH that blocks supervised docs-only consideration under the residual-risk doc’s own terms.
- **REPAIR_REQUIRED** — name findings with severity, file/function, and a FAIL→PASS probe shape.
- **ESCALATE** — same defect class stagnated, or design-level contradiction (do not invent opportunistic in-tree patches during this review).

---

## Part A — Verification items (submit alone if filters trip)

### V1 — Authority and non-goals

Confirm: no live credentials needed; no production deploy; review is of **policy enforcement code** and adversarial probes under `tests/self_improvement_v2/`. Docs in range are in scope.

### V2 — Trusted-origin fail-closed identity (as implemented)

Confirm trust **cannot** be established from CWD / package root / pin alone. Absence of `SRL_REPOSITORY_ROOT` or `SRL_REVIEWED_HEAD` must reject. Pin must be content-digest-only (no HEAD claim). Dirty or digest-mismatched pinned modules (including entrypoint / `git_worker` / verifier) must reject under valid anchors.

### V-LAUNCH — VERIFIER AUTHENTICATION ROOT (required)

Where is the **expected digest of `trusted_origin.py`** held, and is that location **outside the repository under review**?

- If the expected verifier digest (and/or the only gate that checks it) lives **inside** the checkout, the verifier is self-authenticating and **Finding 3 / A+ launcher root is not closed** — report that **regardless of unit-test results**.
- Confirm whether `SRL_REPOSITORY_ROOT` / `SRL_REVIEWED_HEAD` have an **attested source** (out-of-repo launcher holding authorized HEAD + expected digests), not a manual shell assignment / test harness `monkeypatch.setenv`.
- Design canonical path: `%LOCALAPPDATA%\SentinelResearchLab\launch-worker.ps1` (not in checkout). Report whether that (or any equivalent external holder) exists and is what supplies the anchors.

### V3 — Mandatory R0 / R5 control

Reproduce or reason about:

`tests/self_improvement_v2/test_codex_escalate_6f4f1e2.py::test_r5_external_process_no_env_shadow_self_pin_must_reject`

and the Option A+ R0 matrix probes for dirty entrypoint / forged preload under **valid** anchors. Missing-anchor R5 alone does not close F1.

---

## Part B — Verification items (second paste if needed)

### V4 — Budget / coercion defenses

Boolean JSON must not coerce into numeric budget fields. Open-budget / permit paths reject typed booleans before durable grant state changes.

### V5 — Permit / consume atomicity

Consume requires provider, model, credential; omit/mismatch rejects **without** burning the nonce; later correct consume exactly once; concurrency one-winner preserved.

### V-TRANSPORT — live authorize path (required)

Is `/v2/provider-call-authorize` invoked on the **live workflow path**, **immediately before the model node**, on **both** roles?

- Trace the edges in `workflows/design/self_improvement_loop_v2.json` (Permit → Consume → … → Model / Agent → …).
- An endpoint with **no production call site**, or a call site **after** the model/agent has already run, is the **same defect class as prior Finding 4** under a new name — report it.
- Probe: after a **FAILED** consume (omit/mismatch), can the permit be replayed with a correct body? (Implementation claims omit does not burn the nonce — verify the failure path does not leave an incorrectly reusable *authorized* permit, and that successful consume still one-shots authorize.)

### V6 — Residual-risk and Option A+ design artifacts

Confirm residual-risk does **not** authorize a HEAD; scopes one supervised docs-only P3-C1; residual boundary (modify external launcher / forge operator auth line) is stated deliberately; R5 alone does not close F1–3.

### V7 — Five novel probes (required)

Invent **five new** integrity probes not already asserted by existing test names in this range. Prefer: external digest holder absence, verifier self-check gap, authorize-before-model edge order, consume-fail nonce reuse vs authorize-spend, workflow `disabled` / router selector. For each: expected reject/pass and why it matters defensively.

---

## Out of scope

- Running or authorizing the live P3-C1 pilot
- Implementing further repairs during this review
- Treating Cursor / implementer self-review as a substitute PASS
- Re-deriving the Round5A 32-test arithmetic (transition settled above)

---

## Split protocol

If a single paste is refused by a cybersecurity filter:

1. Submit **Part A (V1–V3 + V-LAUNCH)** only.
2. On completion, submit **Part B (V4–V7 + V-TRANSPORT)** with the same authorization context header.
3. If still refused → Trusted Access path, then lesser gate recorded as **non-Codex-equivalent** per rotation doc.
