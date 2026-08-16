# Independent review brief — post-REPAIR_REQUIRED repairs (N1–N7, N11, boundary)

**Paste target:** Codex first (reframed). Fall back to Claude Code only on refusal.  
**Mode:** Read-only defensive integrity assurance  
**Not requested:** exploit development, merge, pilot, authorization line

## Authorization context

| Fact | Value |
|------|-------|
| Pilot authorization | **DOES NOT EXIST** |
| Workflow | inactive by design |
| Prior tip (REPAIR_REQUIRED) | `4ff870275c15ccc1d7e8672ac932e3d6d9f32246` |
| Prior base (ESCALATE) | `e85c42ee434cf93346f14f3a890e5fb1385cb06d` |
| Reviewed HEAD | *(paste `git rev-parse HEAD` — expect `0e56aa0f26a133742f29dc97f9c2136063999c1c`)* |
| Review range | `4ff870275c15ccc1d7e8672ac932e3d6d9f32246` .. tip **or** full `e85c42ee..tip` if re-proving cluster |
| Push | OK for repair visibility |
| Merge PR #8 | **FORBIDDEN** |
| Next-reviewer policy | **Codex first**; Claude Code only on refusal. Same-family PASS does not waive trusted-origin cluster for unsupervised runs |

## Three commits in range (order matters)

1. `63ec203…` — validator N2–N7 (multiset edges, executeOnce, port/origin, disabled/onError/retry)
2. `80e2d1c…` — trust scope N1 closure+negative, N11 HEAD equality, launcher coverage tests
3. `0e56aa0…` — docs boundary for D2-BYPASS / anchor-spoof / N12 only

## Hard rule

Existing tests passing ≠ PASS. Invent ≥5 novel probes. Return R0 matrix vs `4ff8702` (and vs `e85c42ee` for trust-cluster controls).

## Mandatory re-probes

- N3 duplicate Authorize→Agent → REJECT
- N4 executeOnce on authorize/consume → REJECT
- N2 rogue loopback port ≠ meta.localWorkerBaseUrl → REJECT
- N5/N6/N7 authorize disabled / retryOnFail / wrong onError → REJECT by **both** validators
- N1 dirty `repair_policy` / `executor` / `wall_reassert` with valid anchors → REJECT
- N1 pin == static AST closure; negative under-coverage fails
- N11 `SRL_REVIEWED_HEAD != live HEAD` → REJECT even if pinned paths clean
- Launcher path test + wrong digest / wrong HEAD
- D2-BYPASS still STARTS — confirm residual/design **name it as boundary**, not an open bug to patch with a fourth gadget
- INV-R5A-01 remains known-failing Round5A

## Gate equivalence (behavioral)

FULL only if suite independently executed, mandatory attacks verbatim, ≥5 novel probes, R0 matrix. Otherwise LESSER. Same-model-family limitation is standing and non-waivable.

## Verdict vocabulary

PASS | REPAIR_REQUIRED | BLOCKED | ESCALATE

PASS at most → supervised docs-only pilot #1 consideration under residual-risk; operator issues auth line + refreshes launcher digest in the same action.
