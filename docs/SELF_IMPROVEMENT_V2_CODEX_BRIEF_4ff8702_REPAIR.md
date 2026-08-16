# Independent review brief — wide range `e85c42ee..tip` (Codex first)

**Paste target:** Codex first (reframed). Claude Code only on refusal.  
**Mode:** Read-only defensive integrity assurance  
**Not requested:** exploit development, merge, pilot, authorization line, mid-review rubber-stamp

---

## Authorization context

| Fact | Value |
|------|-------|
| Pilot authorization | **DOES NOT EXIST** |
| Workflow | inactive by design |
| Matrix base (comparability) | `e85c42ee434cf93346f14f3a890e5fb1385cb06d` |
| Prior REPAIR_REQUIRED tip | `4ff870275c15ccc1d7e8672ac932e3d6d9f32246` — **not** an approved floor |
| Reviewed HEAD | *(paste `git rev-parse HEAD` at send)* |
| Review range | `e85c42ee434cf93346f14f3a890e5fb1385cb06d` .. *(same tip)* |
| Code-reading focus | `4ff870275c15ccc1d7e8672ac932e3d6d9f32246` .. tip |
| Earlier segment `e85c42ee..4ff8702` | **probe-replay only** (do not re-read as primary code review) |
| Push | OK for repair visibility |
| Merge PR #8 | **FORBIDDEN** |
| Implementer R0 matrix | `docs/SELF_IMPROVEMENT_V2_OPTION_A_PLUS_R0_MATRIX.md` — **verify**, do not re-derive as primary cost |

A PASS is at most evidence toward **supervised docs-only pilot #1** under the residual-risk record.

---

## Step 0

```bash
git rev-parse HEAD
```

Must equal the tip named at paste. Mismatch → **BLOCKED**.

---

## Why wide range

`4ff8702` returned REPAIR_REQUIRED — not a known-good floor. The prior R0 matrix is keyed to `e85c42ee`, so every RED→RED / RED→GREEN row is directly comparable this round. Focus code reading on `4ff8702..tip`; treat `e85c42ee..4ff8702` as probe-replay for matrix continuity.

---

## Hard rule

```text
Existing tests passing != review PASS.
≥5 self-invented novel probes mandatory.
Listed-only review cannot PASS.
FULL gate only if: independent suite execution, mandatory attacks verbatim,
≥5 novel probes, R0 matrix verified (not merely re-invented).
Same-model-family correlated blindness is a standing non-waivable limitation.
```

---

## Mandatory repair probes (each new trusted component needs a negative)

### Absolute origin pin (N2 follow-on)

Requiring node URL origin == `meta.localWorkerBaseUrl` moves trust onto meta.
**Probe:** set meta **and** all worker HTTP nodes to the same rogue port (e.g. `:59999`).
Required: **REJECT** — absolute constraint `http://127.0.0.1:8765`, not self-consistency.
Also reject `localhost:8765` if absolute pin is `127.0.0.1:8765`.

### Multiset edges (N3)

- Triplicate Authorize→Agent (not just duplicate) → REJECT  
- Reverse: a legitimately single required edge elsewhere must still PASS (check not over-strict)

### Closure calculator (N1)

- **Run** (do not only read) the negative under-coverage test  
- Probe the stated AST-only limit: add a **function-level** `import` of a security module and confirm it is correctly in/out of closure per the documented rules — not silently included or missed without statement

### Boundary document (commit 3)

Scope must be **exactly** D2-BYPASS, anchor-spoof, N12.
If the text claims “trust is anchored by the launcher” as if the launcher were attestable against a local adversary, that **overclaims** — report it.
Allowed statement class: *an attacker who can execute arbitrary code as the operator defeats this system; pin/launcher/digests defend misconfiguration/drift/accident.*

---

## Interaction bet — strict HEAD × detached execution worktree

`SRL_REVIEWED_HEAD == live HEAD` resolves live HEAD via `git rev-parse HEAD` at `SRL_REPOSITORY_ROOT`.
The executor creates a detached worktree at baseline+patch; in a linked worktree `git rev-parse HEAD` returns that worktree’s HEAD.

```text
Probe: run the full execute path with a detached worktree present.
Confirm which HEAD strict equality resolves, and that the assertion is
evaluated against the INSTALL root (SRL_REPOSITORY_ROOT), never a
worktree-derived path or cwd.
```

Both failure shapes are bad: fail-closed that breaks execution, or equality against the wrong HEAD.

---

## Other mandatory re-probes (matrix verify)

Use `docs/SELF_IMPROVEMENT_V2_OPTION_A_PLUS_R0_MATRIX.md`. Re-execute at least:

- N1 dirty repair_policy/executor/wall_reassert → REFUSE  
- N11 HEAD≠live → REFUSE  
- N3/N4/N5/N6/N7 → REFUSE as claimed  
- D2-BYPASS still STARTS → boundary, not open bug to patch with a fourth gadget  
- INV-R5A-01 remains known-failing Round5A  

---

## Launcher discipline (docs check)

Confirm runtime doc states: update launcher HEAD + verifier digest **only** at authorization-line time, **never during development**. Strict equality makes every commit stop the worker until refresh — that must remain a control, not an annoyance people disable.

---

## Verdict vocabulary

PASS | REPAIR_REQUIRED | BLOCKED | ESCALATE

## Required return

1. `git rev-parse HEAD`  
2. Exact reviewed HEAD  
3. Gate FULL|LESSER + same-family limitation  
4. Absolute-origin / multiset / closure-negative / boundary-scope results  
5. Worktree×HEAD interaction result  
6. ≥5 novel probes + outcomes  
7. Verified R0 matrix (confirm or dispute implementer table)  
8. PR #8 unmerged?  
9. One terminal verdict  

Do **not** merge PR #8. Any repair commit → new tip; do not transfer approval.
