# Self-Improvement V2 — Invariant Ledger (draft)

**Status:** DRAFT — capture of properties established by independent Codex reviews and in-tree adversarial probes.  
**Not authorization.** This ledger does not authorize any HEAD or pilot.  
**HEAD context when drafted:** `a195e8329d9b8c3cae6310b4b6c3f19a5367ed07`  
**Source ranges:** `21f0e84..6f4f1e2` (escalate; repaired through `457608d`); open assurance range `6f4f1e2..a195e83` (no PASS yet).

## How to read

| Column | Meaning |
|--------|---------|
| ID | Stable invariant id |
| Property | Normative claim |
| Evidence | Review finding and/or test |
| Status | `established` / `accepted-residual` / `open` / `withdrawn-if` |

---

## Established properties (Codex + probes)

| ID | Property | Evidence | Status |
|----|----------|----------|--------|
| INV-TO-01 | Launcher anchors are mandatory: absent `SRL_REPOSITORY_ROOT` or `SRL_REVIEWED_HEAD` ⇒ trusted-origin **REJECT** | Codex Finding 1 (CRITICAL); `test_r5_external_process_no_env_shadow_self_pin_must_reject`; `_require_launcher_anchors` | **established** at repair tip; **re-prove** on every assurance review |
| INV-TO-02 | CWD / package root / self-consistent pin inside an alternate checkout are **not** trust authority | Codex Finding 1; fail-closed redesign at `28eb33f` | established (pending Codex PASS on `6f4f1e2..a195e83`) |
| INV-TO-03 | `trusted_origin` verifier module must be in its own pin set (`TRUSTED_MODULE_NAMES`) | Codex Finding 3 (HIGH); `test_r5_trusted_origin_module_is_pinned` | established |
| INV-TO-04 | Pin `reviewed_git_head` and launcher `SRL_REVIEWED_HEAD` must agree under the documented bind rules (primary bind or trusted-module-unchanged successor tip) | Codex Finding 2 (HIGH); `assert_trusted_code_origin` bind branch | **accepted-residual** for one supervised docs-only P3-C1 under `docs/SELF_IMPROVEMENT_V2_P3C1_ACCEPTED_RESIDUAL_RISK.md`; design session required for durable close |
| INV-TO-05 | A pin file **cannot** truthfully name the commit that first introduces that pin byte-for-byte (self-reference / one-commit lag) | Codex Finding 2 evidence (pin named `77def2a…` while candidate was `6f4f1e2…`; naming exact candidate rejected) | **design-open** — see trusted-origin design session |
| INV-BUD-01 | Boolean JSON must not coerce into pilot budget numeric fields | Codex Finding 5; `test_f5_boolean_budget_fields_rejected_via_runtime_bridge` | established |
| INV-BUD-02 | Boolean `maxIterations` must not satisfy `maxIterations==1` via `int(True)` | Codex Finding 6; `test_f6_max_iterations_boolean_true_rejected` | established |
| INV-BUD-03 | Provider-call consume validates role-bound provider/model/credential atomically | Codex Finding 4; `test_f4_consume_validates_provider_model_credential_binding` | established |
| INV-BUD-04 | Consumed permits are one-shot; second assert after consume fails | `test_r2_consumed_permit_second_assert_one_shot` | established |
| INV-AUTH-01 | Risk authority is sole authorizer; agent nodes are inactive-by-design and non-authoritative | agent-runtime contract + workflow inactive flag | established (process) |
| INV-AUTH-02 | Independent external PASS is required before written pilot authorization; Cursor cannot restore revoked auth via self-review | operator process; residual-risk doc Authorization line | established (process) |
| INV-RES-01 | Residual acceptance of Findings 1–3 is one-run, docs-only, supervised, expires on use; withdraws if mandatory no-env R5 REJECTS at reviewed HEAD | `docs/SELF_IMPROVEMENT_V2_P3C1_ACCEPTED_RESIDUAL_RISK.md` | decision artifact |

## Withdrawal hooks

- If mandatory no-env external R5 **REJECTS** at the HEAD under review ⇒ Findings 1–3 **closed by evidence**; INV-RES-01 acceptance **withdrawn**.
- If trusted-origin design session picks a new root-of-trust model ⇒ re-derive INV-TO-01..05; do not patch a fifth time under the old model without that decision.

## Explicitly not established

- Codex **PASS** on `6f4f1e2..a195e83` — **open** (filter refusal is a process failure, not a PASS).
- Any P3-C1 authorization line naming `a195e83` — **absent**.
- Unsupervised / code-touching pilots while Findings 1–3 remain open under residual — **forbidden** (hard gate).
