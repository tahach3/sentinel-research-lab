# R0 matrix — parse-strictly-or-reject (link fields + shape + pin)

**Base (matrix key):** `e85c42ee434cf93346f14f3a890e5fb1385cb06d`  
**Prior tip (REPAIR_REQUIRED):** `1a1c48e6fcf1abffebfefd1001505aaf83c02cf3`  
**Mid tip (parse-strict NP-2/3/4; REPAIR_REQUIRED on link fields):** `481ac490bc17db0112dd2084c6f5d9fe96c0801b`  
**This tip:** confirm with `git rev-parse HEAD` at paste

Implementer-emitted. Reviewer verifies a **sample**; do not re-derive as primary review cost. Shares `e85c42ee` key with prior Codex columns.

## Code focus

```text
1a1c48e6fcf1abffebfefd1001505aaf83c02cf3..<rev-parse tip>
```

Primary: `workflow_validator.py`, `validation_runner.py` (static import for pin closure), `trusted_origin.py` (`TRUSTED_MODULE_NAMES`), `trusted_origin_pin.json`.

## Suite (harness)

| Tip | SI2 result |
|-----|------------|
| `481ac490…` | **289 passed** (harness; clean worktree) |
| this tip | *(fill at paste — harness SHA-256 in dispatch package)* |

## Transitions vs prior REPAIR_REQUIRED at `481ac490…`

| Probe | At 481ac490 | Tip | Class |
|-------|-------------|-----|-------|
| Design workflow both validators | PASS | PASS | GREEN→GREEN positive control |
| Legitimate unusual shapes (absent keys / empty arrays / allowed null / no parameters / empty channel) | PASS | PASS | GREEN→GREEN over-strict control |
| NP-2 structured `apiKey` dict | REFUSE | REFUSE | GREEN→GREEN |
| NP-4 non-list channel body | REFUSE | REFUSE | GREEN→GREEN |
| NP-3 rogue unconnected code node | REFUSE | REFUSE | GREEN→GREEN |
| Unknown channel `ai_widget` | REFUSE | REFUSE | GREEN→GREEN |
| `link.type={}` / `None` / `42` / `True` | **ACCEPT** | REFUSE | RED→GREEN |
| `link.index={}` / `None` / `'0'` / `True` / `0.0` | **ACCEPT** | REFUSE | RED→GREEN |
| `link.type` ≠ parent channel | **ACCEPT** | REFUSE | RED→GREEN |
| Top-level JSON array | AttributeError | structured REFUSE | RED→GREEN |
| `nodes` scalar member | AttributeError | structured REFUSE | RED→GREEN |
| `workflow_validator` in `trusted_origin_pin.json` | **ABSENT** | PRESENT + digest | RED→GREEN |
| Dirty `workflow_validator.py` under valid anchors | n/a (unpinned) | REFUSE | RED→GREEN |
| V-ROOT / V-ABSENT / V-PRESENT / V-TRANSPORT | PASS at `1a1c48e6` | REGRESSION REPLAY ONLY | do not re-investigate |

## Named status (not blocking repairs this round)

| Probe | Status |
|-------|--------|
| Credential **name-binding** (store re-point, stable reference name) | ABSENT — held Wall |
| MECHANICAL_AUTH_BINDING / LIVE_AUTH_REVOCATION | ABSENT — see residual § V-INSTALL (amended) |
| Credential **secret** independence via distinct reference names alone | **not established** (ledger) |

Reviewer must re-execute mandatory rows and the link-mutation table; treat this table as a claim to verify.
