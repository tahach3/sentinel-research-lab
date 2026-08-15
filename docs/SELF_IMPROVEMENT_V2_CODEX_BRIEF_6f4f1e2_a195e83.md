# Independent review brief — Self-Improvement V2 (defensive assurance)

**Paste target:** Codex (or equivalent independent reviewer)  
**Mode:** Read-only security assurance of **defensive integrity gates**  
**Not requested:** exploit development, unauthorized access guidance, or live pilot execution

---

## Authorization context (read first)

| Fact | Value |
|------|-------|
| Pilot authorization | **DOES NOT EXIST** — nothing to revoke; this review does not create it |
| Workflow | `workflows/design/self_improvement_loop_v2.json` is **inactive by design** |
| Candidate HEAD | `a195e8329d9b8c3cae6310b4b6c3f19a5367ed07` |
| Review range | `6f4f1e26ec7785d2f2bd954e086e9843b6691f61` .. `a195e8329d9b8c3cae6310b4b6c3f19a5367ed07` |
| Prior escalate (handled) | `21f0e84..6f4f1e2` repaired through `457608d`; residual-risk doc at tip records Option A for Findings 1–3 only |
| Operator intent | Verify fail-closed **trust and budget gates** before any future written authorization |

A PASS here is a precondition for a later authorization decision. It is **not** authorization to run P3-C1.

---

## System under review (defensive purpose)

Local Research Lab worker + inactive n8n design workflow intended to:

1. Refuse to treat an arbitrary checkout / self-consistent pin as trust authority.
2. Bind trusted security modules to externally supplied launcher identity.
3. Enforce one-shot provider-call permits and typed pilot budget maxima.
4. Keep AI agent nodes inactive and non-authoritative for risk decisions.

Primary modules: `tools/self_improvement_v2/trusted_origin.py`, `pilot_budget.py`, `runtime_bridge.py`, `risk_authority.py`, `review_gate.py`, pin at `specs/self_improvement/v2/trusted_origin_pin.json`.

---

## Verdict vocabulary (exactly one)

- **PASS** — all mandatory checks and novel probes hold; no open CRITICAL/HIGH that blocks supervised docs-only consideration under the residual-risk doc’s own terms.
- **REPAIR_REQUIRED** — name findings with severity, file/function, and a FAIL→PASS probe shape.
- **ESCALATE** — same defect class stagnated, or design-level contradiction (do not propose a fifth trusted-origin patch without a design session).

---

## Part A — Verification items V1–V3 (submit alone if filters trip)

### V1 — Authority and non-goals

Confirm the reviewer understands: no live credentials needed; no production deploy; review is of **policy enforcement code** and its adversarial unit probes already in-tree under `tests/self_improvement_v2/`.

### V2 — Trusted-origin fail-closed identity

Confirm that trust **cannot** be established from CWD / package root / pin alone. Required external anchors: `SRL_REPOSITORY_ROOT` and `SRL_REVIEWED_HEAD`. Absence of either must reject.

### V3 — Mandatory R0 / R5 control (weight highest)

Reproduce or reason about the in-tree probe:

`tests/self_improvement_v2/test_codex_escalate_6f4f1e2.py::test_r5_external_process_no_env_shadow_self_pin_must_reject`

Shape (integrity check, not an attack playbook): an alternate checkout with mutated `risk_authority` and a recomputed self-pin, run with **both** launcher env vars absent, must **REJECT** (non-zero / exception). Acceptance of that configuration is a CRITICAL fail.

Also confirm `tools.self_improvement_v2.trusted_origin` is itself in `TRUSTED_MODULE_NAMES`.

---

## Part B — Verification items V4–V7 (second paste if Part A alone is needed)

### V4 — Budget / coercion defenses

Boolean JSON values must not coerce into numeric budget fields or `maxIterations==1` (see escalate tests F5/F6). Open-budget path rejects typed booleans.

### V5 — Permit / consume atomicity

Provider-call consume must bind role ↔ provider ↔ model ↔ credential; mismatched identity rejects; consumed permits are one-shot.

### V6 — Residual-risk decision artifact

Read `docs/SELF_IMPROVEMENT_V2_P3C1_ACCEPTED_RESIDUAL_RISK.md`. Confirm it:

- does **not** authorize a HEAD,
- scopes acceptance to **one** supervised docs-only P3-C1 after a later written auth,
- withdraws if the mandatory no-env R5 REJECTS at the reviewed HEAD.

### V7 — Five novel probes (required)

Invent **five new** integrity probes not already asserted by existing test names in this range. Prefer: pin/env disagreement, verifier exclusion, transport/consume races, workflow graph edges, inactive-node authority. For each: expected reject/pass and why it matters defensively.

---

## Out of scope

- Running or authorizing the live P3-C1 pilot
- Patching trusted-origin without a design decision on pin vs external HEAD identity
- Treating Cursor / implementer self-review as a substitute PASS

---

## Split protocol

If a single paste is refused by a cybersecurity filter:

1. Submit **Part A (V1–V3)** only.
2. On completion, submit **Part B (V4–V7)** with the same authorization context header.
3. If still refused → Trusted Access path, then lesser gate (Claude Code) recorded as **non-Codex-equivalent**.
