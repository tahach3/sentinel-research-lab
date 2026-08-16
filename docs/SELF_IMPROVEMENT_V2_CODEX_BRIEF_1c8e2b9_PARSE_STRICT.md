# Independent review brief — parse-strictly-or-reject + re-verify A+ (post Codex REPAIR_REQUIRED)

**Paste target:** Codex (non-Claude-family; preferred)  
**Mode:** Read-only security assurance of **defensive integrity gates**  
**Not requested:** exploit development, unauthorized access guidance, live pilot execution, or mid-review implementation

**Dispatch rule:** Reviewed HEAD **must** equal `git rev-parse HEAD` on `research-lab-self-improvement-v2-v3-gates` at paste time. Do **not** trust a tip SHA pasted from a prior chat message — run `git rev-parse HEAD` and use that value as range end. Range start is fixed below.

**Sandbox requirement (operator):** Prefer an environment where the full SI2 suite and R0 matrix can run: **writable + exec-capable temp**, **loopback sockets permitted**. Prior Codex round correctly declined to treat a partial suite (22 loopback errors; `/dev/shm` noexec) as PASS evidence. Probe-only evidence is weaker than suite+probe.

---

## Authorization context (read first)

| Fact | Value |
|------|-------|
| Pilot authorization | **DOES NOT EXIST** — nothing to revoke; this review does not create it |
| Workflow | `workflows/design/self_improvement_loop_v2.json` is **inactive by design** |
| Prior Codex tip | `1a1c48e6fcf1abffebfefd1001505aaf83c02cf3` — **REPAIR_REQUIRED** (validator parse-skip class: NP-2/3/4) |
| Prior Codex PASS probes | V-ROOT, V-ABSENT, V-PRESENT, V-TRANSPORT |
| INV-AUTH-02 | **Discharged** for the prior Codex-reviewed range by that non-family dispatch; do **not** escalate solely for same-family / INV-RES-02 |
| INV-RES-02 | **Unnecessary** while this Codex path is live — do not authorize under same-family residual |
| Reviewed HEAD | *(paste `git rev-parse HEAD` at send)* |
| Review range | `1a1c48e6fcf1abffebfefd1001505aaf83c02cf3` .. *(same tip from rev-parse)* — or from matrix base `e85c42ee434cf93346f14f3a890e5fb1385cb06d` if re-checking A+ wholesale |
| Branch push policy | Review branch **may be pushed** for PR visibility; **no merge**, **no deploy**, **no pilot**, **no authorization line** from this review |

A PASS here is a precondition for a later authorization decision with **no same-family residual**. It is **not** authorization to run P3-C1.

---

## What the prior round found (one defect class)

All in `tools/self_improvement_v2/workflow_validator.py`; same root cause: **anything the validator cannot fully interpret became a skip, not a rejection.**

| Probe | Mechanism | Required property |
|-------|-----------|-------------------|
| NP-2 | Credential walk discarded dict keys → `{"apiKey":"sk-…"}` invisible | Sensitive **keys** and values scanned; uninterpretable JSON types reject |
| NP-4 | Channel enumerator skipped non-list bodies → malformed `ai_tool` object vanished | Channel body type enumeration: list required; `str`/`dict`/`int`/`None`/`bool` → reject |
| NP-3 | Required nodes checked; node set not closed → rogue unconnected `code` node PASS | Node-set closure (deny-by-default extras), matching edge closure |

**Cluster rule to verify:** parse strictly or reject — applied at every workflow JSON walk point — plus typed negative tests per branch (including “not the type I expected”).

**Process note (for this review):** Prefer class-boundary checks over probe-shape-only. When walking JSON, for each value ask: what types can this be, and what happens for each?

---

## Out-of-range tests (settled — do not re-spend review capacity)

Exact **32** Round5A suite failures (**RED→RED**); ledgered as **INV-R5A-01 known-failing**. Candidate does not touch Round5A paths.

---

## System under review

Primary delta: `workflow_validator.py` + `tests/self_improvement_v2/test_workflow_validator.py`.

Re-confirm (already PASS at prior tip): `trusted_origin.py`, transport authorize-before-model, pin/closure, inactive workflow.

Accepted residual (do not re-open as MUST-FIX unless newly worsened): V-INSTALL re-root — `MECHANICAL_AUTH_BINDING=ABSENT` / `LIVE_AUTH_REVOCATION=ABSENT` (named in residual-risk doc).

---

## Verdict vocabulary (exactly one)

- **PASS**
- **REPAIR_REQUIRED**
- **ESCALATE**

Do **not** return ESCALATE solely for INV-AUTH-02 / same-family — that invariant is discharged for the prior Codex range; this round is technical.

---

## Part A — Prior PASS re-spot (cheap)

Confirm V-ROOT / V-ABSENT / V-PRESENT / V-TRANSPORT still hold at the new tip. No need to re-derive the full A+ matrix unless suite sandbox is healthy and cheap.

---

## Part B — Parse-strict cluster (required)

1. **NP-2 style:** Workflow JSON with sensitive material only under a dict key (e.g. `parameters.apiKey`) must **FAIL** validation.
2. **NP-4 style:** `ai_tool` (or other channel) body as object / string / int / null / bool must **FAIL**, not disappear. Unknown channel **name** `ai_widget` must still **FAIL**.
3. **NP-3 style:** Extra unconnected executable node (e.g. `code`) must **FAIL** node-set closure.
4. **Class boundary:** Spot-check other walk points for silent skips on wrong JSON types (connections shape, outputs arrays, link objects). Prefer evidence that negatives exist for unexpected types, not only the demonstrated probe shapes.
5. **Design workflow:** Unmutated `workflows/design/self_improvement_loop_v2.json` must still **PASS**.

---

## Part C — Suite evidence (required if sandbox allows)

Run `tests/self_improvement_v2/` (full). If environment blocks loopback or exec-on-temp, report that limitation explicitly and do **not** claim a candidate total as PASS evidence — fall back to targeted probes and state the gap.

Reproduce R0 / A+ matrix probes from `docs/SELF_IMPROVEMENT_V2_OPTION_A_PLUS_R0_MATRIX.md` when sockets work.

---

## Part D — Named not-previously-reviewed probes (report status; do not invent fixes)

These are **held** for Wall / later briefs if ABSENT; they are in-scope to **name and classify**, not to expand into a repair campaign in this turn:

| Probe | Question |
|-------|----------|
| **Credential name-binding** | Can the n8n credential **store** contents be re-pointed while the workflow’s credential **reference name** stays identical? (Distinct from NP-2 embedded JSON values.) |
| **Reinstall-revocation** | Confirm still `MECHANICAL_AUTH_BINDING=ABSENT` and `LIVE_AUTH_REVOCATION=ABSENT` for installer re-root after compromised tree write — accepted residual boundary, not a silent close. |

**Out of this round’s repair scope (hold):** launcher attestation HEAD equality / hash stability; three credential-store field binding designs — operator holds Wall additions until after a clean technical PASS.

---

## Out of scope

- Live P3-C1 / authorization / merge / deploy
- Same-family residual authorization (INV-RES-02)
- Round5A RED→RED re-litigation
- Inventing new attestation gadgets for V-INSTALL / D2-BYPASS

---

## Evidence rules

- Prefer commands and file citations over narrative.
- If suite cannot run cleanly, say so; do not launder a partial total into PASS.
- One verdict word at the end.
