# Repair and Stagnation Policy

## Bounds

- Maximum repair attempts: **2**
- Debugger may recommend a bounded retry; it does not execute unlimited retries
- Same failure class twice → stop and escalate (`escalated_same_failure`)
- Max attempts exhausted → escalate (`escalated_budget` / stagnation)

## Non-repairable (fail closed)

unsupported_citation, invalid_schema, budget_blocked, timeout, rate_limited
(at non-QA stages), reviewer rejection.

## Reviewer authority

Independent reviewer rejection stands. Proposal writer cannot overwrite the
proposal to clear a rejection.
