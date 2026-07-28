# Evidence Chain of Custody

## Immutable pieces

- `sources` identity
- `source_snapshots` (fingerprint + metadata; append-only)
- `evidence_items` body immutable; corrections = new version row
- Evidence cannot be deleted (trigger); especially when cited by `taha_decisions`

## Claim linkage

`evidence_claim_links.stance`: `supports` | `contradicts` | `contextual`

## Proposal gate

A proposal may enter `ready_for_decision` only if its current
`proposal_versions.evidence_ids` is non-empty and references real evidence rows.

A question may enter `decision_required` only if such a ready proposal exists.
