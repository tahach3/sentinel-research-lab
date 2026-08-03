# Round 5A Evidence Provenance Decision

Architecture reset name: **Round 5A Architecture Reset**

This decision record binds hash-matched Phase 1 evidence query artifacts to the current repository and defines alias, path-portability, and resolution rules for evidence identifiers.

It does **not** rewrite `docs/ROUND_5A_REVISION_8_NORMATIVE_DECISION_RECORD.md`.

---

## Historical claim status

```text
CLAIMED HISTORICAL COMMIT: 8d592bf
HISTORICAL GIT AUTHENTICATION: UNVERIFIED
CURRENT GIT BINDING: established by this repair commit
```

Hash equality of offline bytes is not authentication of git origin.

---

## ND-PROV-001 — Hash-matched offline archived copy

The hash-matched offline archived SQL/spec copy is accepted as a new,
git-bound current provenance artifact at the repair commit.

It is not evidence that the bytes were retrieved from commit 8d592bf.
Historical source authentication remains UNVERIFIED.

Committed producers:

```text
evidence/round5a/archived_phase1/SRL_Phase1_catalog_snapshot.sql
evidence/round5a/archived_phase1/SRL_Phase1_evidence_spec.md
evidence/round5a/archived_phase1/PROVENANCE.json
```

---

## ND-PROV-002 — Explicit evidence identifier mappings

Archived and recreated EV identifiers must be connected through explicit
typed alias, split, merge, replacement, or retirement records.

Normative machine-readable owner:

```text
specs/round5a/evidence_aliases.yaml
```

Name similarity alone is never sufficient. A mapping typed
`CONFLICTING_MEANING` is blocking and must not be accepted.

---

## ND-PROV-003 — Portable normative paths

Normative manifests may contain repository-relative paths, logical external
artifact identifiers, and cryptographic hashes, but no absolute user,
TEMP, drive-specific, or machine-specific paths.

Reconstructed-reference schema-8 evidence remains a runtime-supplied
external artifact identified logically as
`ROUND5A-RECONSTRUCTED-REFERENCE-SCHEMA8`.

---

## ND-PROV-004 — Current EV reference resolution

Every EV reference used by a current marker, checkpoint, rule, fixture, or
generated document must resolve to:

- a committed evidence producer;
- an explicit evidence mapping;
- or an explicit live/runtime unknown gate.

Live/preflight and runtime-revalidation markers remain unknown until their
declared gates execute. Reconstructed evidence must never be reclassified as
`LIVE_CATALOG` by this repair.
