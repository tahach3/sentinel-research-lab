# Accepted Residual Risk — One Supervised Docs-Only P3-C1

**Status:** Decision artifact. Predates the pilot it governs. Reconciled after Codex `ESCALATE` on `e85c42ee434cf93346f14f3a890e5fb1385cb06d`, and after the independent Claude Code assurance round on `4ff8702…` (REPAIR_REQUIRED) whose code repairs and this boundary statement supersede the prior “Findings 1–3 open indefinitely” framing.

**Authority:** Operator decision (Option A trust bar), amended by Option A+ design approval and the local-code-execution boundary below.

**Authorization:** WITHHELD until independent review PASS on a HEAD later named in an authorization line. This file does **not** authorize a HEAD and must not be read as naming an authorized commit.

## Source findings

Raised by independent Codex review of range:

```text
21f0e844bbfe5faa907b9568c0f30670566b55bc..6f4f1e26ec7785d2f2bd954e086e9843b6691f61
```

and re-opened / expanded by Codex review of:

```text
6f4f1e26ec7785d2f2bd954e086e9843b6691f61..e85c42ee434cf93346f14f3a890e5fb1385cb06d
```

and re-probed by Claude Code assurance of:

```text
e85c42ee434cf93346f14f3a890e5fb1385cb06d..4ff870275c15ccc1d7e8672ac932e3d6d9f32246
```

| # | Severity | Cluster | Summary | Disposition after A+ repairs + this doc |
|---|----------|---------|---------|----------------------------------------|
| 1 | CRITICAL | trusted-origin | Arbitrary-checkout self-pin when external identity is absent / spoofable | **No-anchor** path: fail-closed. **With-anchor spoof / D2-BYPASS:** accepted as **local-code-execution boundary** (below), not a fourth attestation gadget |
| 2 | HIGH | trusted-origin | Pin must not claim HEAD | **Closed in code** (content-only pin; `SRL_REVIEWED_HEAD` sole HEAD claim; live HEAD must equal reviewed HEAD) |
| 3 | HIGH | trusted-origin | Bootstrap set not closed | **Closed in code** for static import closure of `runtime_bridge` (N1) and launcher-installer closure (`launcher_pin.json`). Launcher digest **artifact** remains out-of-repo. **Adversary re-root:** the trust root is re-rootable by anyone who can write repository files and re-run the installer; mitigation is operator discipline (unenforced against that adversary) — see named boundary `V-INSTALL` |

Findings that were **outside** the original residual and required code (not boundary prose):

- Workflow `disabled:true` / router / transport ordering / duplicate-edge / executeOnce / port-origin (N2–N7, D1-WINDOW)
- Consume identity + authorize path
- Permit boolean coercion

## Named trust boundary (what remains accepted)

**Statement:**

> An attacker who can execute arbitrary code as the operator on this machine
> defeats this system. The pin, out-of-repo launcher, digests, and HEAD
> equality defend misconfiguration, drift, and accident — not a local
> adversary who already owns the operator identity (same class as the
> operator shell, git config, credentials, and n8n instance).

**Accepted under that boundary only:**

| ID | Shape | Why not another code layer |
|----|-------|----------------------------|
| D2-BYPASS | Direct `runtime_bridge` start with hand-set env anchors | No in-repo secret/token/ancestry check distinguishes launcher without moving the trust problem |
| Anchor spoof | Anchors point at attacker checkout with self-consistent pin | Same as forging operator-supplied identity |
| N12 | Post-start in-process object replacement after byte attestation | Expected limit of byte-level attestation |
| PATH-git (R2-B) | Replace the `git` binary recorded in the launcher attestation | Arbitrary code execution as the operator; ambient `GIT_*` is closed in code (R2-A) |
| V-INSTALL re-root | Re-run `install_launcher` from a compromised tree to mint a matching digest | Requires write access to the checkout (conceded adversary); dirty/HEAD/pin accident cases are closed in code |

**Not accepted as residual / must stay closed in code:** incomplete pin vs closure (N1 + launcher pin), N11 HEAD drift tolerance, ambient `GIT_*` rebinding, dirty/drifted reinstall accidents, `repository_root` divergence (R4), validator multi-dispatch / port / disabled / **non-`main` attachment** gaps (N2–N7, R1), transport omit/burn bugs.

OS-level privilege separation (service account the operator shell cannot impersonate) remains **Option B** — a real boundary if ever needed; not required for supervised docs-only pilot #1.

## Exact scope (expires on use)

Accepted **only** for:

- **Exactly one** supervised, manually-triggered, docs-only **P3-C1** pilot
- At whichever repository HEAD is **later authorized in writing** after independent review PASS
- Not “documentation pilots in general,” not a class of runs, and not precedent for any later pilot

After that one run completes (success or failure), this acceptance **expires**. Any subsequent run requires a **new written decision**.

Same-model-family assurance (Claude reviewing Claude-implemented code) carries correlated blindness for **build-review independence** (INV-AUTH-02). It is at most evidence toward this supervised docs-only pilot #1, not toward unsupervised or code-touching runs.

## Two independence claims (do not collapse)

| Claim | What it protects | Pilot #1 status |
|-------|------------------|-----------------|
| **Loop independence** | Gemini implements / Groq reviews inside the pilot; different providers/families; content-hash bound | Intact — what pilot #1 is designed to test |
| **Build-review independence** (INV-AUTH-02) | Who reviewed the code that *implements* the loop | Not discharged by same-family Claude rounds; Codex/Trusted Access preferred |

Waiving build-review independence for one scoped run does **not** waive loop independence. Correlated blindness of the build reviewer is a real theoretical concern; the empirical record of three same-family rounds (manufactured PASS, D2-BYPASS, anchor spoof, unpinned closures, port swap, duplicate edges, executeOnce, HEAD drift, `ai_*` gadgets, ambient `GIT_*`, installer re-root, config-root divergence, blank-env loader gate, …) is not the signature of a reviewer sharing the implementer's blind spots — but that does not *discharge* INV-AUTH-02.

**Built-in safety net:** NC-1 is blocking. If the review path is broken in a way three reviews missed, NC-1 fails to reject a known-bad package and the pilot stops before Zone B.

## Same-family build-review residual (pilot #1 only) — INV-RES-02

**Status:** Operator decision artifact (same structure as trusted-origin residual above). This section does **not** authorize a HEAD and does not convert an `ESCALATE` into a reviewer `PASS`.

Pursue Codex / Trusted Access when available. Do **not** hold the supervised docs-only pilot indefinitely on an uncertain Trusted Access timeline.

If the next review at the tip returns technical merits that would be `PASS` but escalates solely for same-family / INV-AUTH-02, the operator **may** authorize under this residual:

Accepted **only** for:

- **Exactly one** supervised, manually-triggered, docs-only **P3-C1** pilot
- At whichever repository HEAD is **later authorized in writing**
- Not “documentation pilots in general,” not a class of runs, and not precedent for any later pilot

After that one run completes (success or failure), this acceptance **expires**. Any subsequent run requires a **new written decision**.

Hard gate before unsupervised / code-touching / operator-absent runs: this residual alone is insufficient; prefer a cross-family independent PASS to discharge INV-AUTH-02 cleanly.

## What the mandatory no-env R5 probe does and does not close

The mandatory no-environment external-process R5 attack (arbitrary-name shadow checkout; CWD=shadow; both `SRL_REPOSITORY_ROOT` and `SRL_REVIEWED_HEAD` absent; mutated `risk_authority` + recomputed self-pin) tests **only** the missing-launcher-anchor self-pin failure mode.

**If that probe REJECTS**, it is evidence that the no-anchor self-pin path fails closed. It does **not**, by itself, defeat D2-BYPASS or with-anchor spoof — those are the named boundary above.

## Conditions that make residual acceptance interpretable

1. **Written record in the repository** — this file; boundary and source ranges named here; build-review residual (INV-RES-02) scoped here.
2. **Scoped to one run** — candidate P3-C1, docs-only, supervised, one authorized HEAD; expires on use.
3. **Re-decided in writing** for any subsequent run — no silent extension.
4. **Hard gate before escalation** — code-closed items (closure pin, HEAD equality, transport/validator repairs, blank-env loader refuse) must remain PASS; unsupervised / code-touching / operator-absent runs require a **new** written decision (and preferably a non-Claude-family reviewer discharging INV-AUTH-02).

## Reasoning (supervised docs-only measurement)

The remaining accepted trusted-origin shapes require a local adversary with code execution who already owns the operator identity. Pilot #1 has no such adversary: manually triggered, inactive loopback workflow, docs-only, operator-supervised, no auto-merge.

What P3-C1 is meant to prove (end-to-end loop execution, reviewer behavior, promotion boundary) does **not** depend on defeating that local adversary — and does **not** depend on discharging build-review independence via Codex, provided the operator accepts INV-RES-02 in writing for that one HEAD. A residual trusted-origin *boundary* and a residual same-family *build review* weaken what an *unsupervised* or *code-touching* pilot would prove; they do not invalidate the supervised docs-only measurement — **provided** the code-closed HIGH items remain closed and NC-1 stays blocking.

## Hard gate (normative)

Do **not** proceed to unsupervised pilots, code-touching pilots, or operator-absent runs while relying on INV-RES-01 / INV-RES-02 alone.

Closing those run classes—or a new written acceptance with its own scope—is a hard precondition.
