# Trusted-origin root-of-trust — Option A (decided)

**Status:** DECIDED — Option A with launcher refinements.  
**Decision date:** 2026-08-15  
**Implementation:** **HELD** until independent review verdict on `6f4f1e2..7dbbfa1` returns. Do not patch mid-flight.  
**Pilot authorization:** still absent; this document does not authorize any HEAD.

## Decision

**Adopt Option A** (content-digest pin + external launcher identity). Reject B and C for this system.

### Why not B

One-commit lag only papers over Finding 2. Finding 1 (CRITICAL arbitrary-checkout self-pinning) is untouched: an attacker regenerating a pin in their checkout can write a lagged HEAD as easily as a current one. Lag removes the symptom that made the disease visible.

### Why not C

Signed out-of-repo attestation is appropriate for multi-operator / untrusted-host deployments. Here it adds key generation, storage, rotation, and a signing step per authorization while the verification key still lives outside the repo — A's trust root with extra machinery.

### Why A

Codex proved the pin cannot be the root of trust: it lives inside the artifact it authenticates. A stops pretending otherwise. The pin does the one job it can honestly do (content digests). Identity comes from the launcher.

## Normative design (refinement that closes Findings 1–3)

### 1. Launcher lives outside the repository

Canonical Windows path (this lab):

```text
%LOCALAPPDATA%\SentinelResearchLab\launch-worker.ps1
```

Not in the git checkout. The launcher:

1. Takes the **authorized HEAD** as a parameter sourced from the operator's written authorization line (when one exists).
2. Sets `SRL_REPOSITORY_ROOT` to the reviewed install root.
3. Sets `SRL_REVIEWED_HEAD` to that authorized HEAD.
4. Authenticates the verifier digest (below).
5. Execs the worker.

### 2. Worker fails closed on absence (closes Finding 1)

Either `SRL_REPOSITORY_ROOT` or `SRL_REVIEWED_HEAD` missing → **refuse**.

No CWD derivation, no package-root derivation, no self-pin path, no fallback of any kind.

### 3. Pin stops claiming a HEAD (closes Finding 2 structurally)

`specs/self_improvement/v2/trusted_origin_pin.json` carries **module content digests only** (per-module + combined; schema/version/description as needed).

Remove authoritative `reviewed_git_head` / `head_content_binding` from the pin. A file cannot name its own commit, so it must not try.

`SRL_REVIEWED_HEAD` is the sole reviewed-commit claim. Digests are checked against git blobs at that HEAD under `SRL_REPOSITORY_ROOT`.

### 4. Launcher authenticates the verifier before Python starts (closes Finding 3)

`trusted_origin.py` cannot verify itself. The launcher holds an **expected digest of the verifier module** (outside the repo), computes the on-disk digest before launch, and **refuses to launch on mismatch**.

### 5. Secrets-of-trust held by the launcher

Exactly two values, both from the operator's authorization decision:

| Secret | Role |
|--------|------|
| Authorized HEAD | Becomes `SRL_REVIEWED_HEAD` |
| Expected digest of `trusted_origin.py` | Pre-Python launch check |

Everything else chains from those.

## Residual trust boundary (deliberate)

An attacker who can **modify the launcher**, or **forge the operator's authorization line**, wins.

That is the correct boundary: the same trust placed in the operator's shell / host account. It is **accepted residual risk of Option A**, stated deliberately for the next reviewer — not an unstated hole.

Out of scope for this control (not claimed closed by A):

- Compromised operator account / `%LOCALAPPDATA%` write access
- Forged written authorization lines accepted by the human who launches

## Rejected alternatives (record)

| Option | Verdict |
|--------|---------|
| B — explicit one-commit lag | Rejected — does not close Finding 1; hides Finding 2 |
| C — signed out-of-repo attestation | Rejected for this single-operator local lab — cost without material gain over A |

## Sequencing

1. **Now:** this design is normative; dispatch independent review on `6f4f1e2..<tip>` where tip is `git rev-parse HEAD` after this design lands (do not leave reviewed HEAD lagging tip).
2. **After verdict:** implement A (Findings 2 and 3 need it regardless of Finding 1 disposition at current HEAD; verdict sizes how much of fail-closed env behavior already exists at `457608d`+).
3. **Not now:** no trusted-origin code/schema patch while the review is in flight (avoids reviewing a superseded tree).

## Related docs

- Residual risk (Findings 1–3 scoped acceptance): `docs/SELF_IMPROVEMENT_V2_P3C1_ACCEPTED_RESIDUAL_RISK.md`
- Invariant ledger: `docs/SELF_IMPROVEMENT_V2_INVARIANT_LEDGER.md`
- Review brief: `docs/SELF_IMPROVEMENT_V2_CODEX_BRIEF_6f4f1e2_7dbbfa1.md`
