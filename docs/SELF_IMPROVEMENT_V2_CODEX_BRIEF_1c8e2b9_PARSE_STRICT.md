# Independent review brief — parse-strictly-or-reject (post Codex REPAIR_REQUIRED)

**Paste target:** Codex (non-Claude-family)  
**Mode:** Read-only security assurance of **defensive integrity gates**  
**Not requested:** exploit development, unauthorized access guidance, live pilot execution, or mid-review implementation

**Dispatch rule:** Reviewed HEAD **must** equal `git rev-parse HEAD` on `research-lab-self-improvement-v2-v3-gates` at paste time. Do **not** trust a tip SHA from a prior chat message.

---

## Authorization context (read first)

| Fact | Value |
|------|-------|
| Pilot authorization | **DOES NOT EXIST** |
| Workflow | `workflows/design/self_improvement_loop_v2.json` is **inactive by design** |
| Prior Codex tip | `1a1c48e6fcf1abffebfefd1001505aaf83c02cf3` — **REPAIR_REQUIRED** (validator parse-skip class NP-2/3/4) |
| Prior Codex PASS (do not re-investigate) | V-ROOT, V-ABSENT, V-PRESENT, V-TRANSPORT |
| INV-AUTH-02 | **Discharged** for the prior Codex-reviewed range; do **not** escalate solely for same-family / INV-RES-02 |
| INV-RES-02 | **Unnecessary / dormant** while this Codex path is live |
| Reviewed HEAD | *(substituted from `git rev-parse HEAD` at send)* |
| Branch push policy | **no merge**, **no deploy**, **no pilot**, **no authorization line** |

A PASS here is a precondition for later authorization **with no same-family residual**. It is **not** authorization to run P3-C1.

---

## Range discipline (matrix-comparable; attention on the change)

```text
Range:        e85c42ee434cf93346f14f3a890e5fb1385cb06d..<rev-parse tip>
Code focus:   1a1c48e6fcf1abffebfefd1001505aaf83c02cf3..<rev-parse tip>
```

- **Wide range** keeps the three Codex columns matrix-comparable with prior rounds.
- **Code focus** is the only span to *read deeply* — the parse-strict repair and tests.
- `1a1c48e6…` is **not** an approved floor (it returned REPAIR_REQUIRED). It is the prior tip where V-ROOT / V-ABSENT / V-PRESENT / V-TRANSPORT already PASSed.

### Trusted-origin cluster — REGRESSION REPLAY ONLY

Codex PASSed V-ROOT / V-ABSENT / V-PRESENT / V-TRANSPORT at `1a1c48e6…`. **Re-run those probes to confirm no regression; do not re-investigate the mechanism.**

`workflow_validator.py` is outside the `runtime_bridge` AST content-pin set today; if the tip still omits it from `trusted_origin_pin.json`, report that accurately (ABSENT for TO dirty-refuse of this file) and do **not** expand into reopening V-ROOT. If it *is* pinned at the tip, confirm the pin regenerated with the parse-strict change and that a dirty `workflow_validator.py` still REFUSES. That is the only trusted-origin surface this code-focus range could touch.

---

## What prior round found (one defect class)

All in `tools/self_improvement_v2/workflow_validator.py`: **anything the validator could not fully interpret became a skip, not a rejection.**

| Probe | Mechanism |
|-------|-----------|
| NP-2 | Credential walk discarded dict keys → `{"apiKey":"sk-…"}` invisible |
| NP-4 | Channel enumerator skipped non-list bodies → malformed `ai_tool` object vanished |
| NP-3 | Required nodes checked; node set not closed → rogue unconnected `code` node PASS |

**Property to verify:** parse strictly or reject — at every workflow JSON walk point — plus node-set closure matching edge closure. Prefer class-boundary checks (full input-type space at each walk point), not probe-shape-only.

---

## POSITIVE CONTROL (blocking — a PASS without this is not a PASS)

You just rewrote a file with a history of silent skips into one that rejects anything it cannot parse. That is exactly where an **over-strict regression** appears. An over-strict validator is worse than a permissive one: the first time it blocks a legitimate workflow someone loosens it under pressure and the class reopens.

**Mandatory (equal weight to fail-open findings):**

1. The reviewed design workflow at this tip must **PASS both validators**, unchanged, with **zero errors**:
   - `tools.self_improvement_v2.workflow_validator.validate_workflow`
   - `tools.self_improvement_v2.agent_runtime_contract.assert_workflow_agent_wiring`
2. Then probe **legitimate-but-unusual shapes that must still PASS**:
   - optional keys absent
   - empty arrays
   - nulls where the schema allows them
   - a node with no `parameters` object
   - a channel present but empty (`[]`)
3. **Any legitimate shape rejected is a finding of equal weight to a fail-open.**

---

## Part B — Parse-strict cluster (required)

1. NP-2 style: sensitive material only under a dict key must **FAIL**.
2. NP-4 style: channel body as object / string / int / null / bool must **FAIL**, not disappear. Unknown channel name `ai_widget` must still **FAIL**.
3. NP-3 style: extra unconnected executable node must **FAIL** node-set closure.
4. Class boundary: other walk points must not silently skip wrong JSON types.
5. Node closure is a **deliberately rigid control** (INV-WF-03): the closed allow-list **is** the control; making it open reopens NP-3 — same sentence class as absolute port pin and `ai_tool`/`ai_memory` ban.

---

## Suite evidence (R0 pattern — harness emits, Codex spot-checks)

Harness (Cursor) ran the full `tests/self_improvement_v2/` suite at this tip and shipped totals + artifact hashes in the dispatch package. **Do not fight a broken sandbox for a second full-suite attempt.**

Your job:

1. Read the harness suite artifact (totals + SHA-256 of the log).
2. **Spot-check by targeted execution** a sample of tests (prefer the parse-strict / positive-control / design-PASS tests). Report N/N.
3. If your sandbox *can* run the full suite cleanly, do so and compare to the harness total — but a clean spot-check against a hashed harness total is sufficient evidence for this round.

Reproduce R0 / A+ matrix probes only as **regression replay** for the four already-PASS trusted-origin / transport items above — not a fresh investigation.

---

## Part D — Named not-previously-reviewed probes (status only; no repair campaign)

| Probe | Question |
|-------|----------|
| **Credential name-binding** | Can the n8n credential **store** be re-pointed while the workflow’s credential **reference name** stays identical? (Distinct from NP-2 embedded JSON values.) |
| **Reinstall-revocation** | Confirm still `MECHANICAL_AUTH_BINDING=ABSENT` / `LIVE_AUTH_REVOCATION=ABSENT` for installer re-root — accepted residual, not a silent close. |

**Held (out of repair scope):** launcher attestation HEAD equality / hash stability; credential-store field binding designs.

---

## Out of scope

- Live P3-C1 / authorization / merge / deploy
- INV-RES-02 / same-family residual authorization
- Round5A RED→RED re-litigation
- Re-deriving V-ROOT / V-ABSENT / V-PRESENT / V-TRANSPORT mechanisms
- Inventing new attestation gadgets for V-INSTALL / D2-BYPASS

---

## Verdict vocabulary (exactly one)

- **PASS**
- **REPAIR_REQUIRED**
- **ESCALATE**

Do **not** return ESCALATE solely for INV-AUTH-02. A PASS without the positive control is not a PASS.

## Evidence rules

- Prefer commands and file citations.
- One verdict word at the end.
