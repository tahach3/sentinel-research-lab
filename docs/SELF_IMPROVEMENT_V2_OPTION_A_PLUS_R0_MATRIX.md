# R0 matrix — SI2 repairs after `4ff8702` REPAIR_REQUIRED

**Base (matrix key):** `e85c42ee434cf93346f14f3a890e5fb1385cb06d`  
**Prior rejected tip:** `4ff870275c15ccc1d7e8672ac932e3d6d9f32246`  
**This tip:** `05ecf407276d9fc40e8d40fe4fe310f71508d281`  

Implementer-emitted. Reviewer verifies; do not re-derive arithmetic as the primary review cost.

## Repair commits (code reading focus: `4ff8702..tip`)

| SHA | Content |
|-----|---------|
| `63ec203` | N2–N7 validators |
| `80e2d1c` | N1 closure + N11 HEAD + launcher tests |
| `0e56aa0` | Docs boundary D2-BYPASS / spoof / N12 |
| `b184871` | Codex-first brief |
| *(later)* | Absolute meta origin pin + this matrix + brief refresh |

## Suite

| Tip | SI2 result |
|-----|------------|
| `4ff8702` | 231 passed (context) |
| post-repair tips | 248+ passed — **not** PASS evidence |

## Transitions vs `e85c42ee` (comparable to prior review matrix)

| Probe | Base e85c42ee | Tip | Class |
|-------|---------------|-----|-------|
| D2-BYPASS hand-set env | ACCEPT | ACCEPT | **RED→RED** — documented boundary |
| Anchor spoof + self-pin | ACCEPT | ACCEPT | **RED→RED** — documented boundary |
| N12 post-start mutate | ACCEPT | ACCEPT | **RED→RED** — documented boundary |
| A1 dirty runtime_bridge | ACCEPT | REFUSE | RED→GREEN |
| A2 dirty git_worker | ACCEPT | REFUSE | RED→GREEN |
| N1a dirty repair_policy | ACCEPT | REFUSE | RED→GREEN |
| N1b dirty executor | ACCEPT | REFUSE | RED→GREEN |
| N1c dirty wall_reassert | ACCEPT | REFUSE | RED→GREEN |
| N1 pin==AST closure | n/a | HOLD + negative under-cover fails | established |
| N11 HEAD≠live (clean pin paths) | ACCEPT | REFUSE | RED→GREEN |
| D1-WINDOW insert Set/Wait/NoOp | n/a→ACCEPT at 4ff8702 | REFUSE | RED→GREEN |
| N3 duplicate Authorize→Agent | ACCEPT | REFUSE | RED→GREEN |
| N4 executeOnce authorize/consume | ACCEPT | REFUSE | RED→GREEN |
| N2 rogue node port (meta fixed) | ACCEPT | REFUSE | RED→GREEN |
| N2 meta+nodes rogue port agree | ACCEPT | REFUSE | RED→GREEN (absolute pin) |
| N5 authorize disabled both validators | 1-of-2 | both REFUSE | RED→GREEN |
| N6 authorize retryOnFail | ACCEPT | REFUSE | RED→GREEN |
| N7 authorize onError wrong | 1-of-2 | both REFUSE | RED→GREEN |
| Launcher wrong digest | n/a | REFUSE | RED→GREEN |
| Launcher wrong HEAD | n/a | REFUSE | RED→GREEN |
| Launcher install inside repo | n/a | REFUSE | RED→GREEN |
| R5 no-env shadow | REFUSE | REFUSE | GREEN→GREEN control |
| INV-R5A-01 R5A-MANIFEST-HASH | FAIL | FAIL | RED→RED known-failing Round5A |

Reviewer must re-execute mandatory rows and ≥5 novel probes; treat this table as a claim to verify, not a substitute for PASS.
