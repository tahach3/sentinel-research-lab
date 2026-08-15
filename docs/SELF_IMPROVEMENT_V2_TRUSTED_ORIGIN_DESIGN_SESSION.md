# Trusted-origin root-of-trust — design session (draft for approval)

**Status:** DESIGN SESSION — approaches and recommendation; **no implementation until operator picks**.  
**Why now:** No pilot authorization exists (commits free). Three consecutive origin rounds stagnated on the same structural defect. Codex Finding 2 showed a pin cannot name the commit it lives in.

## Problem statement (narrow)

Who supplies `SRL_REPOSITORY_ROOT` and `SRL_REVIEWED_HEAD`, what authenticates **that** supplier, and what happens when identity is absent (**fail closed, no fallback**)?

Secondary: the pin file today still carries `reviewed_git_head`, which collides with “pin lives inside the artifact it authenticates.”

## Non-negotiables (already evidenced)

1. Absent launcher anchors ⇒ REJECT (no CWD/package-root authority).
2. Verifier module is in the trust set.
3. Content digests of trusted modules must match pin + git blobs at a named reviewed content tip.
4. Do not ship a fifth opportunistic patch without choosing a model below.

## Approaches

### A — Content-digest attestation only (recommended)

**Pin becomes:** module digests + combined + optional description. **Remove** `reviewed_git_head` / `head_content_binding` from the pin (or demote to non-authoritative metadata).

**Identity:** `SRL_REVIEWED_HEAD` is the sole reviewed-commit claim, supplied by the launcher. Digests are checked against `git show ${SRL_REVIEWED_HEAD}:path` and working tree under `SRL_REPOSITORY_ROOT`.

**Supplier of anchors:** the **operator-controlled launcher** (systemd unit, signed wrapper, or n8n credential-injected env on the trusted host). The launcher is outside the worker package. Authentication of the supplier = host OS ACL + how the operator starts the worker (not reinvented inside Python).

**Absent identity:** fail closed (current behavior). No self-pin path.

**Pros:** Ends the self-reference paradox; pin no longer claims HEAD. Matches Codex’s structural critique.  
**Cons:** Requires pin schema + bind-rule rewrite; successor-tip special case may shrink or vanish.

### B — Explicit one-commit lag (pin names parent)

**Pin keeps** `reviewed_git_head`, defined as: “content tip of trusted modules,” which is **always** a parent (or ancestor) of the commit that updates the pin metadata. By construction the pin never names the commit that edits the pin.

**Launcher:** `SRL_REVIEWED_HEAD` must equal that content tip **or** a successor whose trusted-module tree matches the tip (today’s successor rule), documented as intentional lag.

**Pros:** Smaller code delta; preserves current tests’ primary bind form.  
**Cons:** Easy to re-hit by accident (operators will keep trying to set pin HEAD == candidate tip). Lag must be taught and enforced in tooling that regenerates the pin.

### C — Dual-file external attestation (heavier)

Keep in-repo digests; store reviewed HEAD in an **out-of-repo** attestation file or OS keyring entry written only by the launcher. Worker refuses if attestation missing.

**Pros:** Strong separation.  
**Cons:** Operational complexity; more moving parts for a docs-only pilot host.

## Recommendation

**Choose A** for the durable design. Keep today’s fail-closed env requirement. Treat B only as a transitional documentation of current behavior if A cannot land before the supervised P3-C1 under residual risk.

## Decision needed from operator

Reply with **A**, **B**, or **C** (or a hybrid). After pick: write the normative design to `docs/superpowers/specs/` (or `docs/SELF_IMPROVEMENT_V2_TRUSTED_ORIGIN_DESIGN.md`) and only then plan implementation — no fifth blind patch.

## Explicitly deferred

- Implementation patches
- Pilot authorization
- Changing residual-risk acceptance (still valid under Option A until withdrawn by R5 evidence or expiry)
