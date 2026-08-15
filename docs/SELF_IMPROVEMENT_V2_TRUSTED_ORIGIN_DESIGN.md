# Trusted-origin root-of-trust — Option A+ (approved)

**Status:** APPROVED — Option A+ design delta (Claude authority, 2026-08-15).
**Supersedes:** Option A as written in the prior design (verifier-only precheck / partial eight-module pin).
**Frozen review that forced A+:** `e85c42ee434cf93346f14f3a890e5fb1385cb06d` (Codex `ESCALATE`).
**Pilot authorization:** still absent; this document does not authorize any HEAD.

## Why A+ (not another same-file pin repair)

Codex F1 proved the authenticated set was not closed: with valid `SRL_REPOSITORY_ROOT` / `SRL_REVIEWED_HEAD`, Git-dirty `runtime_bridge.py` and `git_worker.py` still executed and were accepted because neither was in the pin set. A preloaded forged `trusted_origin` could also be accepted before the real verifier loaded.

That is a **CRITICAL bootstrap/closure failure**, not a pin-metadata nit. Option A’s “precheck only `trusted_origin.py` then exec the worker” is **insufficient**.

## Disposition of Codex findings at e85c42ee

| Finding | Disposition under A+ cycle |
|---------|----------------------------|
| F1 trust-set / bootstrap closure | **In scope for A+** (expanded closed bootstrap + content-only pin) |
| F2 disabled authority / router semantics | **Companion blocker** — same candidate cycle; not “more pin repair” |
| F3 consume / transport binding | **Companion blocker** — resurfaced prior Finding 4; outside residual |
| F4 residual vs design contradiction | **Governance** — residual text reconciled; R5 alone does not close F1–3 |
| F5 permit boolean coercion | **Companion blocker** — same candidate cycle |
| F6 runtime docs / status misclassification | **Cleanup** — travels with repair |

## Normative A+ requirements

### External launcher remains root of trust

Canonical path: `%LOCALAPPDATA%\SentinelResearchLab\launch-worker.ps1` (not in the checkout).  
Installer: `python -m tools.self_improvement_v2.launcher.install_launcher` writes the populated launcher + attestation **outside** the repository (LOCALAPPDATA or XDG data home). In-repo templates/helpers are not the trust root.

Launcher supplies:

1. Authorized HEAD → `SRL_REVIEWED_HEAD`
2. Reviewed install root → `SRL_REPOSITORY_ROOT`
3. Expected digest of `trusted_origin.py` (held outside the repo); refuse if on-disk bytes ≠ expected
4. Fresh process; refuse launch on digest mismatch (fail-closed only — never accept on drift)

**Operator rule:** update the launcher’s expected verifier digest in the **same action** as issuing the authorization line for that HEAD. Both are attestations about one reviewed tip.

No repository Python module may be treated as authoritative until that external boundary succeeds.

### Closed bootstrap / execution manifest

The content-only pin MUST cover at least:

- `runtime_bridge.py` (actual worker entrypoint)
- `trusted_origin.py` (verifier)
- `git_worker.py` (Git/evidence provider used by the verifier)
- every transitive in-repo module that can change authentication, authorization, path selection, origin evidence, or provider dispatch (including `risk_authority`, `review_gate`, `pilot_budget`, `path_policy`, `workflow_validator`, `agent_runtime_contract`, `finalizer`, `patch_validator`, `runtime_config`, `schema_loader`, `canonical`, `models`)

Pin = **content digests only** (per-module + combined). Pin must **not** claim reviewed HEAD. `SRL_REVIEWED_HEAD` is the sole HEAD claim.

Missing / malformed / mismatching / noncanonical launcher identities → fail closed. No CWD / package-root / self-pin fallback.

### Verify-before-execute / anti-TOCTOU

- Digest checks for pinned modules (including `git_worker`) MUST use direct filesystem reads (and/or raw `git` subprocess) **before** trusting imported helpers that those modules provide.
- Reject Git-dirty or digest-mismatched pinned modules **before** their mutated code is relied upon.
- Reject a preloaded forged `trusted_origin` in `sys.modules` whose `__file__`/bytes do not match the pinned on-disk module (reload-from-verified-path or fail closed).
- Prefer launch from an authenticated immutable snapshot/worktree of `SRL_REVIEWED_HEAD`, or an equally strong proof that verified bytes are executed bytes.

### Explicit residual boundary (unchanged, stated)

An attacker who can **modify the external launcher** or **forge the operator authorization line** wins. That is the deliberate residual boundary (same trust as the operator shell). Do not silently broaden it.

## Companion controls (same candidate; not “pin-only”)

### Workflow authority (Codex F2)

Both `validate_workflow` and `assert_workflow_agent_wiring` MUST reject `disabled: true` (and non-boolean `disabled` where applicable) on every mandatory authority, budget, schema, review, decision, consume, and finalization node. Validate Worker Decision Router (and other security-critical routers) **selector expression and ordered routing**, not only destinations. Preserve globally inactive workflow (`active: false`).

### Permit typing + consume binding (Codex F3/F5)

- One strict integer parser at bridge and registry; JSON booleans never become token ceilings.
- Reject bool token fields **before** `calls_granted` or other durable state changes.
- Consume requires provider, model, and credential; omit/mismatch rejects **without** burning the nonce.
- Later correct request may consume exactly once; one-winner concurrency preserved.
- Do not treat self-reported identity alone as proof of transport: issue server-owned one-shot invocation evidence at consume and require a production authorize path **on the main edge immediately before the agent/model** for both roles; validators must reject Agent→Authorize post-hoc ordering.
- Bind reviewer acceptance to server-issued reviewer evidence when independence is claimed.
- Update the inactive design workflow consume bodies to pass mandatory identity fields.

## Residual-risk reconciliation (F4)

The mandatory no-env R5 probe closes **only** the no-anchor self-pin failure mode. It does **not** close:

- valid-anchor dirty entrypoint / evidence-provider execution (Codex F1 at e85c42ee)
- Option A+ bootstrap/manifest requirements
- F2/F3/F5 companion blockers

`docs/SELF_IMPROVEMENT_V2_P3C1_ACCEPTED_RESIDUAL_RISK.md` must not claim that R5 alone closes Findings 1–3 or withdraws residual on that basis.

## Implementation sequencing

1. This A+ document is authoritative.
2. One Cursor candidate commit from clean base `e85c42ee…` implementing A+ plus companion F2/F3/F5/F6.
3. No push, pilot, n8n activation, provider call, or authorization from that commit.
4. Fresh Codex review over `e85c42ee..<candidate HEAD>` before any Claude authorization.
