# Research Priority Policy (`priority-v1`)

## Components (0–100)

| Component | Weight |
| --- | --- |
| constitutional_impact | 0.18 |
| measured_performance_gap | 0.16 |
| safety_impact | 0.16 |
| expected_value | 0.14 |
| urgency | 0.12 |
| evidence_availability | 0.10 |
| implementation_cost (inverted) | 0.08 |
| duplication_penalty (subtract) | 0.06 |

`calculated_score = Σ(weight_i * component_i)` with cost inverted as
`(100 - implementation_cost) * 0.08` and penalty subtracted.

## Effective score

`effective_score = override_score` if set, else `calculated_score`.

Overrides **require** non-empty `override_rationale` and sync onto
`research_questions.priority_score`.
