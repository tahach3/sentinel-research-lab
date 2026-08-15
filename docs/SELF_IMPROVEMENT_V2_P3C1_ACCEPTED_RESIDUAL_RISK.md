# Accepted Residual Risk — One Supervised Docs-Only P3-C1

**Status:** Decision artifact. Predates the pilot it governs. Reconciled after Codex `ESCALATE` on `e85c42ee434cf93346f14f3a890e5fb1385cb06d`.

**Authority:** Operator decision (Option A trust bar), amended by Option A+ design approval.

**Authorization:** WITHHELD until independent Codex PASS on a HEAD later named in an authorization line. This file does **not** authorize a HEAD and must not be read as naming an authorized commit.

## Source findings

Raised by independent Codex review of range:

```text
21f0e844bbfe5faa907b9568c0f30670566b55bc..6f4f1e26ec7785d2f2bd954e086e9843b6691f61
```

and re-opened / expanded by Codex review of:

```text
6f4f1e26ec7785d2f2bd954e086e9843b6691f61..e85c42ee434cf93346f14f3a890e5fb1385cb06d
```

| # | Severity | Cluster | Summary |
|---|----------|---------|---------|
| 1 | CRITICAL | trusted-origin | Arbitrary-checkout self-pinning bypass when external identity is absent |
| 2 | HIGH | trusted-origin | Pin / candidate external-anchor disagreement (structural: pin must not claim HEAD) |
| 3 | HIGH | trusted-origin | Trust verifier / bootstrap set not closed (entrypoint + Git evidence provider) |

Findings from the e85c42ee review that are **outside** this residual (blocking on their own):

- Workflow `disabled:true` authority bypass (HIGH)
- Consume not bound to provider transport / omitted identity (HIGH; prior transport Finding 4)
- Permit boolean coercion on token fields (MEDIUM)

## Exact scope (expires on use)

Accepted **only** for:

- **Exactly one** supervised, manually-triggered, docs-only **P3-C1** pilot
- At whichever repository HEAD is **later authorized in writing** after Codex PASS
- Not “documentation pilots in general,” not a class of runs, and not precedent for any later pilot

After that one run completes (success or failure), this acceptance **expires**. Any subsequent run requires a **new written decision**.

## What the mandatory no-env R5 probe does and does not close

The mandatory no-environment external-process R5 attack (arbitrary-name shadow checkout; CWD=shadow; both `SRL_REPOSITORY_ROOT` and `SRL_REVIEWED_HEAD` absent; mutated `risk_authority` + recomputed self-pin) tests **only** the missing-launcher-anchor self-pin failure mode.

**If that probe REJECTS**, it is evidence that the no-anchor self-pin path fails closed. It does **not**, by itself:

- close valid-anchor dirty-entrypoint / dirty-`git_worker` execution gaps
- close Option A+ closed-bootstrap / content-only-pin requirements
- withdraw this residual for Findings 1–3 as a complete set
- authorize any HEAD or pilot

Closure of the trusted-origin cluster for authorization purposes requires Codex PASS on a HEAD that implements **Option A+** (see `docs/SELF_IMPROVEMENT_V2_TRUSTED_ORIGIN_DESIGN.md`), including the expanded bootstrap/execution manifest — not R5 alone.

## Conditions that make residual acceptance interpretable

1. **Written record in the repository** — this file; Findings 1–3, source review ranges, and reasoning are named here (not only in chat).
2. **Scoped to one run** — candidate P3-C1, docs-only, supervised, one authorized HEAD; expires on use.
3. **Re-decided in writing** for any subsequent run — no silent extension, no drift by habit.
4. **Hard gate before escalation** — trusted-origin Findings 1–3 under Option A+, plus out-of-residual HIGH blockers (workflow disabled-authority, transport/consume binding), must be **closed by PASS** (or separately re-accepted under a new written decision) before any unsupervised run, any pilot that touches code, or any run without the operator present.

## Reasoning (supervised docs-only measurement)

Findings 1–3 (and the e85c42ee closure gaps) require a local adversary with code execution who can create a shadow checkout or mutate worker bytes. Pilot #1 has no such adversary: it is manually triggered, inactive loopback workflow, docs-only, operator-supervised, no auto-merge.

What P3-C1 is meant to prove (end-to-end loop execution, reviewer behavior, promotion boundary) does **not** depend on defeating a code-exec shadow-checkout or dirty-entrypoint attack against `trusted_origin`. A residual trusted-origin defect weakens what an *unsupervised* or *code-touching* pilot would prove; it does not invalidate the supervised docs-only measurement — **provided** out-of-residual HIGH blockers that affect the pilot’s own authority/budget path are closed or separately accepted.

## Hard gate (normative)

Do **not** proceed to unsupervised pilots, code-touching pilots, or operator-absent runs while:

- Option A+ trusted-origin closure remains open, or
- out-of-residual HIGH findings (disabled authority nodes, consume/transport binding) remain open under this (or any later) residual

Closing those findings—or a new written acceptance with its own scope—is a hard precondition for those run classes.
