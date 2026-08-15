# Accepted Residual Risk — One Supervised Docs-Only P3-C1

**Status:** Decision artifact. Predates the pilot it governs.

**Authority:** Operator decision (Option A trust bar).

**Authorization:** WITHHELD until independent Codex PASS on the HEAD later named in an authorization line. This file does **not** authorize a HEAD and must not be read as naming an authorized commit.

## Source findings

Raised by independent Codex review of range:

```text
21f0e844bbfe5faa907b9568c0f30670566b55bc..6f4f1e26ec7785d2f2bd954e086e9843b6691f61
```

| # | Severity | Cluster | Summary |
|---|----------|---------|---------|
| 1 | CRITICAL | trusted-origin | Arbitrary-checkout self-pinning bypass when external identity is absent |
| 2 | HIGH | trusted-origin | Pin / candidate external-anchor disagreement |
| 3 | HIGH | trusted-origin | Trust verifier excluded from its own trust set |

Findings **4** (transport atomicity), **5** (boolean budget coercion), and **6** (boolean `maxIterations`) are **not** covered by this residual. They are outside the trusted-origin cluster and remain blocking if still open at the reviewed HEAD.

## Exact scope (expires on use)

Accepted **only** for:

- **Exactly one** supervised, manually-triggered, docs-only **P3-C1** pilot
- At whichever repository HEAD is **later authorized in writing** after Codex PASS
- Not “documentation pilots in general,” not a class of runs, and not precedent for any later pilot

After that one run completes (success or failure), this acceptance **expires**. Any subsequent run requires a **new written decision**.

## Conditions that make acceptance safe

1. **Written record in the repository** — this file; Findings 1–3, source review range, and reasoning are named here (not only in chat).
2. **Scoped to one run** — candidate P3-C1, docs-only, supervised, one authorized HEAD; expires on use.
3. **Re-decided in writing** for any subsequent run — no silent extension, no drift by habit.
4. **Hard gate before escalation** — Findings 1–3 must be **closed** (or separately re-accepted under a new written decision) before any unsupervised run, any pilot that touches code, or any run without the operator present.

## Reasoning

Findings 1–3 require a local adversary with code execution who can create a shadow checkout and attempt to defeat the trust pin. Pilot #1 has no such adversary: it is manually triggered, inactive loopback workflow, docs-only, operator-supervised, no auto-merge.

What P3-C1 is meant to prove (end-to-end loop execution, reviewer behavior, promotion boundary) does **not** depend on defeating a code-exec shadow-checkout attack against `trusted_origin`. A residual trusted-origin defect weakens what an *unsupervised* or *code-touching* pilot would prove; it does not invalidate the supervised docs-only measurement.

## Withdrawal if the attack is closed

If, at the HEAD under Codex review, the **mandatory no-environment external-process R5 attack** (arbitrary-name shadow checkout; CWD=shadow; both `SRL_REPOSITORY_ROOT` and `SRL_REVIEWED_HEAD` absent; mutated `risk_authority` + recomputed self-pin) **REJECTS**, then Findings 1–3 are **closed by evidence**, not deferred. In that case this residual-risk acceptance is **withdrawn** and must not be treated as standing residual risk.

## Hard gate (normative)

Do **not** proceed to unsupervised pilots, code-touching pilots, or operator-absent runs while Findings 1–3 remain open under this (or any later) residual. Closing those findings—or a new written acceptance with its own scope—is a hard precondition for those run classes.
