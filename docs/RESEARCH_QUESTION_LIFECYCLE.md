# Research Question Lifecycle

## Purpose

Govern creation, prioritization, deduplication, status tracking, closure, and
audit of Research Lab questions without autonomous AI decisions.

## Statuses

`proposed` → `triage_required` → `approved_for_research` → `active` →
`evidence_review` → `decision_required` → `accepted` | `rejected` | `deferred`
→ `closed`

Also: `superseded` (replacement identified). `research_more` decisions return a
question to `active` with explicit missing-evidence conditions.

## Rules

- No undocumented transition skipping (enforced in DB).
- Every transition appends immutable `research_status_history`.
- Closed questions cannot silently reopen; reopen requires a new version + rationale path.
- Duplicates link via `canonical_question_id` / `duplicate_of` relationships.
- Confidentiality defaults to `public_or_synthetic` in Round 2.

## Intake sources (Round 2)

- Manual local form
- Synthetic metric-gap fixture
- Synthetic incident fixture
- Local PostgreSQL seed data

No AI-generated questions in this round.
