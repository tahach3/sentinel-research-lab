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
| F1 trust-set / bootstrap closure | **In scope for A+** (static-AST import closure + content-only pin; not dynamic loaders) |
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

### Closed under static AST imports (execution pin)

The content-only pin MUST equal the **static AST import closure** of
`tools.self_improvement_v2.runtime_bridge` (plus the closure calculator module itself).
Computation is defined in `tools/self_improvement_v2/import_closure.py` and is
**AST-only**: top-level and function-level `import` / `from … import` with literal
`tools.self_improvement_v2.*` names. It does **not** resolve dynamic
`importlib.import_module(...)` (including literal module-name strings),
`__import__(...)` (including literals), string-built names, or plugin loaders.
`TYPE_CHECKING`-only imports **are** included (over-inclusive / fail-safe).
A negative test must prove that adding a module to the closure breaks pin equality.

Do **not** read “closed bootstrap / execution manifest” as stronger than this
AST-only limit: an unpinned module loaded via literal-name dynamic import can
still execute inside the worker. That is the documented calculator limit, not
a missing pin entry.

Ancestor package ``__init__.py`` modules under `tools.self_improvement_v2`
**are** included (they execute on every import). Relative imports under that
prefix **are** included.

Pin = **content digests only** (per-module + combined). Pin must **not** claim reviewed HEAD.
`SRL_REVIEWED_HEAD` is the sole HEAD claim and **must equal** the live `git rev-parse HEAD`
of the install (no “pinned paths clean” drift tolerance).

Missing / malformed / mismatching / noncanonical launcher identities → fail closed. No CWD / package-root / self-pin fallback.

### Explicit trust boundary (local code execution)

**Named boundary (not a missing fourth attestation layer):**

> An attacker who can execute arbitrary code as the operator on this machine
> defeats this system. Mechanisms below that line — content pin, out-of-repo
> launcher, digests, HEAD equality — defend **misconfiguration, drift, and
> accident**, not a local adversary who already owns the operator identity.

Consequences that are **accepted under this boundary** (do not invent another
in-repo “launcher attestation” gadget for them):

- **D2-BYPASS:** starting `python -m tools.self_improvement_v2.runtime_bridge`
  with hand-set `SRL_REPOSITORY_ROOT` / `SRL_REVIEWED_HEAD` (the worker cannot
  cryptographically prove launcher provenance without moving the trust problem).
- **Anchor spoof with a self-consistent checkout:** pointing anchors at an
  attacker-controlled clone whose pin matches its own bytes (same class as
  owning the operator shell / forging the auth line).
- **N12 post-start in-process replacement:** mutating already-loaded Python
  objects after a successful byte attestation.
- **PATH-git replacement (R2-B):** after ambient `GIT_*` sanitization and
  explicit `--git-dir` / `--work-tree`, defeating git attestation requires
  replacing the `git` binary the launcher recorded. That is arbitrary code
  execution as the operator. The resolved git path is recorded in the
  out-of-repo launcher attestation for audit visibility; it is **not**
  hard-pinned (portability; an attacker who can replace `/usr/bin/git` owns
  the box).
- **Trust-root re-root (V-INSTALL adversary half):** anyone who can write
  repository files can re-run `install_launcher` from a compromised tree and
  mint a launcher whose expected verifier digest matches the backdoor. The
  artifact (out-of-repo digest gate) remains sound against post-install drift;
  the **generator** is re-rootable. Mitigation is **operator discipline**
  (refresh only in the authorization ritual from a reviewed tree) — enforced
  for accident-class cases (dirty tree, HEAD≠live, pin mismatch) but **not**
  for a local adversary who already owns the checkout.

What is **not** part of this boundary and must remain closed in code:

- Incomplete pin vs import closure (N1), including the **launcher installer**
  second manifest (`launcher_pin.json`)
- Workflow validator gaps (duplicate edges, executeOnce, port/origin, disabled
  coverage, **non-`main` attachment channels** / second `ai_languageModel`)
- `SRL_REVIEWED_HEAD != live HEAD` tolerance (N11)
- Ambient `GIT_DIR` / `GIT_WORK_TREE` defeat of N11 (R2-A — sanitized)
- Dirty-tree / drifted launcher reinstall (R3 accident half)
- `repository_root` ≠ trusted install root (R4)

An attacker who can **modify the external launcher** or **forge the operator
authorization line** also wins — same trust class as the operator shell.
Do not silently broaden the boundary.

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
