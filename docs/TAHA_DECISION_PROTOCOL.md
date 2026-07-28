# Taha Decision Protocol

## Authority

Deciding authority stored as exactly `Taha`. This is an **audit field**, not an
external identity integration. Real action happens in the local authenticated
n8n owner session.

## Decision values

- `approved`
- `rejected`
- `deferred` (requires review date and/or condition text)
- `research_more` (creates reconsideration/missing-evidence conditions; question returns to `active`)
- `superseded`

## Required audit fields

- proposal version
- timestamp
- concise rationale (`decision_rationales`)
- evidence considered
- risks accepted
- conditions
- optional review/expiry date

## Queue presentation (workflow design)

The inactive Taha decision queue must show: one-sentence question, one-sentence
proposal, strongest supporting and contradictory evidence, benefit, risk, size,
prior related decisions, and exact options — never auto-decide.
