# Ranking formula (rank-v1)

Used by the monthly role-ranking design. Not executed live in Round 1.

## Eligibility gate

Skip ranking a model for a role unless:

- completed_cases ≥ 10
- completed_adversarial ≥ 2
- technical_failure_rate &lt; 0.20
- unresolved_critical_safety_count = 0

## Composite score (0–100)

Weights (sum = 1.0):

| Dimension | Weight |
| --- | --- |
| factual_accuracy | 0.18 |
| evidence_quality | 0.12 |
| instruction_compliance | 0.14 |
| reasoning_completeness | 0.08 |
| output_structure | 0.08 |
| citation_correctness | 0.10 |
| hallucination_rate (quality score) | 0.10 |
| agreement_with_taha | 0.12 |
| latency (normalized) | 0.03 |
| token_use (normalized) | 0.025 |
| cost (normalized; free-preferred) | 0.025 |

`schema_valid_response_rate`, `retry_rate`, and `rate_limit_failures` act as
multipliers:

- schema_valid_response_rate &lt; 0.95 → composite × 0.9
- any silent paid retry detected → composite = 0 (disqualify)
- rate_limit_failures high (&gt;10% of runs) → composite × 0.95

## Tie-break order

1. Higher `agreement_with_taha`
2. Lower median latency
3. Lower average cost
4. Higher adversarial-case average
5. Lexicographic `provider_code` + `model_code` (stable)

## Output

Rows inserted into `research.monthly_role_rankings` with `formula_version = 'rank-v1'`
only when the evidence gate passes (enforced by table CHECK).
