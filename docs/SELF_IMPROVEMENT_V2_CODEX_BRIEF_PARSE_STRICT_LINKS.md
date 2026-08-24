# Independent review brief — link-field parse-strict + pinned workflow_validator

**Paste target:** Codex (non-Claude-family)  
**Mode:** Read-only security assurance of **defensive integrity gates**  
**Not requested:** exploit development, unauthorized access guidance, live pilot execution, mid-review implementation

**Dispatch rule:** Reviewed HEAD **must** equal `git rev-parse HEAD` at paste time.

---

## Authorization context

| Fact | Value |
|------|-------|
| Pilot authorization | **DOES NOT EXIST** |
| Workflow | inactive by design |
| Prior Codex tip | `481ac490bc17db0112dd2084c6f5d9fe96c0801b` — **REPAIR_REQUIRED** (unparsed `link.type`/`link.index`; unpinned `workflow_validator`) |
| Prior PASS probes | V-ROOT / V-ABSENT / V-PRESENT / V-TRANSPORT at `1a1c48e6…` — **REGRESSION REPLAY ONLY** |
| INV-AUTH-02 | Discharged for prior Codex range; do **not** escalate solely for INV-RES-02 |
| INV-RES-02 | Dormant while Codex path is live |
| Reviewed HEAD | *(substituted from `git rev-parse HEAD` at send)* |

---

## Range discipline

```text
Range:        e85c42ee434cf93346f14f3a890e5fb1385cb06d..<rev-parse tip>
Code focus:   1a1c48e6fcf1abffebfefd1001505aaf83c02cf3..<rev-parse tip>
```

Trusted-origin: REGRESSION REPLAY ONLY for V-ROOT/ABSENT/PRESENT/TRANSPORT. Additionally confirm `workflow_validator` is **in** `trusted_origin_pin.json` and dirty refuse holds.

R0 claim table: `docs/SELF_IMPROVEMENT_V2_R0_MATRIX_PARSE_STRICT.md` — verify a sample, including the link-mutation table.

---

## POSITIVE CONTROL (blocking)

Design workflow must PASS both `validate_workflow` and `assert_workflow_agent_wiring` with zero errors. Legitimate-but-unusual shapes (absent optional keys, empty arrays, allowed nulls, no `parameters`, empty channel `[]`) must still PASS. Over-strict rejection = finding equal to fail-open.

---

## Required class (this tip)

1. `link.type` / `link.index` parsed strictly — reject non-string type, non-int index (incl. bool), `None`, and `type` ≠ parent channel.
2. Top-level non-object → structured FAIL (no AttributeError).
3. `nodes` scalar member → structured FAIL (no AttributeError).
4. `workflow_validator` pinned + dirty refuse.

NP-2/3/4 prior repairs must still hold.

---

## Suite / V-MATRIX

Harness embeds totals + SHA-256 in the dispatch package. Spot-check; do not fight sandbox for a second full suite. If sandbox cannot run R0 matrix probes that need sockets/git mutability, say so explicitly — do not silently drop V-MATRIX.

---

## Named status (report; no repair campaign)

| Probe | Expectation |
|-------|-------------|
| Credential name-binding | ABSENT / held Wall |
| V-INSTALL MECHANICAL_AUTH_BINDING / LIVE_AUTH_REVOCATION | ABSENT — **documented** in residual § V-INSTALL (amended deliberately; same one-run scope) |
| Secret independence from distinct credential **names** alone | **not established** (ledger) |

---

## Verdict vocabulary

PASS / REPAIR_REQUIRED / ESCALATE — one word at end. PASS without positive control is not a PASS.
