# Provider Adapter Contract

## Scope

Round 3 defines a **provider-neutral adapter contract** with **mock adapters only**.
No live HTTP provider adapters. No API keys. No AI calls.

## Stages

1. researcher
2. planner
3. implementation_proposal_writer
4. qa_checker
5. independent_reviewer
6. debugger

QA uses `mock-provider-qa`. Reviewer uses `mock-provider-reviewer` (must differ).

## Request fields

`run_id`, `question_id`, `stage`, `model identifier`, `prompt version`,
`normalized evidence bundle`, `allowed source IDs`, `token ceiling`, `cost ceiling`,
`timeout`, `required output schema`, `confidentiality class`, `input fingerprint`.

## Response fields

`provider`, `model`, `model version`, `stage`, `structured output`, `cited evidence IDs`,
`latency`, `input/output tokens`, `estimated cost`, `finish reason`, `retry count`,
`output fingerprint`, `failure classification`.

## Failure classes

`quota_exhausted`, `budget_blocked`, `timeout`, `rate_limited`, `invalid_schema`,
`unsupported_citation`, `provider_unavailable`, `unsafe_output`, `mock_failure`.

## Deterministic mock scenarios

success, invalid_schema, timeout, rate_limit, contradictory_finding, QA rejection,
reviewer rejection, debugger recovery recommendation, budget_exhaustion,
unsupported_claim.
