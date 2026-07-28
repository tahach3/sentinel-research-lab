# Research Orchestration

## Flow

approved_for_research → active → researcher → evidence validation → planner →
proposal writer → QA → independent review → evidence_review → decision_required →
Taha decision queue (card only; no auto-decision).

## Run statuses

pending, running, awaiting_qa, awaiting_review, repair_required, decision_ready,
failed, blocked, cancelled.

## Rules

- Immutable stage records after success/fail
- Output references input fingerprint
- Unsupported claims fail before proposal materialization
- No silent provider switching or paid fallback
- Quota/budget checked before each stage
- Partial results cannot enter decision_required
- Failed runs preserve evidence and failure history
- Resume skips completed stages (no duplicates)
