# Data Model

## Implemented

### Round 0B

- schemas `n8n` and `research`
- roles `n8n_app` and `research_app`
- extension `vector`
- table `research.schema_version`

### Round 1 (benchmarking only)

Tables in `research`:

- `providers`, `models`, `provider_budget_policies`
- `benchmark_suites`, `benchmark_cases`
- `benchmark_runs`, `model_outputs`, `run_failures`
- `automatic_scores`, `taha_scores` (append-only)
- `monthly_role_rankings` (evidence-threshold CHECKs)

Views:

- `v_provider_performance_by_role`
- `v_cost_per_successful_run`
- `v_failure_rate`
- `v_latency_percentile_summary`
- `v_latest_monthly_ranking`
- `v_insufficient_evidence_warning`

No research-question lifecycle tables yet.

## Planned later domains

### 1. Research questions

- Question text, priority, status, tags
- Origin (manual vs generated)
- Links to related evidence and proposals

### 2. Sources

- Official / trusted source identity
- URL or citation
- Trust class and retrieval timestamp

### 3. Evidence

- Normalized excerpts or facts
- Source linkage
- Optional embedding reference (pgvector later)

### 4. Model runs (general)

Benchmark runs exist; broader research lifecycle model-runs come later.

### 5. Proposals

- Structured proposal body
- Linked questions and evidence
- Export package reference

### 6. Taha decisions

- Approve / reject / defer beyond scoring dimensions
- Rationale text for SENTINEL import

### 7. Provider budgets

Policy table exists; live metering adapters later.

### 8. SENTINEL export packages

- Files under `exports/`
- Manifest checksum / version
- Import status after Taha approval
