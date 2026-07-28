# Data Model

## Implemented

### Round 0B

- schemas `n8n` / `research`, roles, `vector`, `schema_version`

### Round 1

Benchmarking tables/views (providers, models, suites, cases, runs, scores, rankings).

### Round 2

Lifecycle tables:

- `question_status_transitions`
- `research_questions`, `research_question_versions`, `research_question_relationships`
- `research_priorities`, `research_status_history`, `research_closure_records`
- `sources`, `source_snapshots`, `evidence_items`, `evidence_claim_links`, `research_findings`
- `improvement_proposals`, `proposal_versions`
- `taha_decisions`, `decision_rationales`, `reconsideration_conditions`

Views:

- `v_active_research_queue`
- `v_highest_priority_unanswered`
- `v_questions_blocked_missing_evidence`
- `v_proposals_awaiting_taha`
- `v_rejected_eligible_reconsideration`
- `v_settled_questions`
- `v_duplicate_question_warnings`
- `v_decision_history_by_topic`

## Planned later

SENTINEL export packages, live provider adapters, AI-generated intake (not Round 2).
