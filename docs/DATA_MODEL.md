# Data Model

## Implemented

### Round 0B

- schemas `n8n` / `research`, roles, `vector`, `schema_version`

### Round 1

Benchmarking tables/views (providers, models, suites, cases, runs, scores, rankings).

### Round 2

Lifecycle tables and decision/evidence custody (see Round 2 docs).

### Round 3

Orchestration tables:

- `research_runs` (shared orchestration state)
- `research_run_stages`
- `provider_adapter_requests`
- `provider_adapter_responses`
- `repair_attempts`
- `orchestration_failures`

View: `v_simulated_decision_cards`

Functions: `mock_adapter_invoke`, `run_stage`, `orchestrate_research_run`,
`materialize_proposal_from_run`, `build_decision_card`, `cancel_research_run`.

## Planned later

Live provider adapters, SENTINEL export packages (not Round 3).
