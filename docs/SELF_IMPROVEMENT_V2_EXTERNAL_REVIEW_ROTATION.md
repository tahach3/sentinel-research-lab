# External review rotation — Self-Improvement gates

**Status:** Process decision draft (durable fix for single-reviewer SPOF).  
**Problem:** The gate required exactly one independent reviewer (Codex). Failure modes include both rubber-stamp and **refusal to run**. Same structural weakness.

## Policy

1. Maintain a **roster of at least two** qualified independent reviewers.
2. Use them in **rotation** for successive assurance rounds — not only as fallback after refusal.
3. Record which reviewer produced which verdict; a lesser gate must be labeled as such.

## Proposed roster (initial)

| Role | Reviewer | Equivalence | When to use |
|------|----------|-------------|-------------|
| Primary A | **Codex** (ChatGPT Codex / OpenAI independent review) | Full gate | Default rotation slot |
| Primary B | **Claude Code** (Anthropic Claude in a fresh session, read-only brief) | Full gate **only if** operator marks it Codex-equivalent for that round; otherwise **lesser gate** | Alternate rotation slot; also Trusted Access / filter-refusal ladder step 4 |
| Escalation | Human operator (Taha) + written decision protocol | Not a substitute PASS for code assurance; decides residual risk / auth | Residual acceptance, auth lines, design-session outcomes |

Operator may add a third tool (e.g. another frontier model with tool-using review) later; roster size ≥ 2 is the hard minimum.

## Rotation rules

- Odd assurance rounds → Primary A; even → Primary B (or explicit operator override recorded in the brief header).
- Same defect class across **two** rounds with the **same** reviewer → switch reviewer before a third attempt (fresh angles).
- Filter refusal by A → try reframed brief → split brief → Trusted Access → B as lesser gate if still blocked; do not invent a PASS.
- Self-review by the implementer agent (Cursor) is **never** a roster member.

## Brief requirements (every reviewer)

- Authorization context **first** (auth absent / withheld; inactive workflow; range; non-goals).
- Defensive framing (integrity gates, fail-closed checks).
- Mandatory R0/R5 control + novel probes.
- Verdict vocabulary: PASS / REPAIR_REQUIRED / ESCALATE only.
