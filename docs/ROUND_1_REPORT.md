# Round 1 Report — Provider Benchmarking Design

## Status

Design and schema complete. No live provider calls. No API keys.

## Starting commit

`3abf826fcd05ff7551cceae4ceabf4640f908ad9`

## Delivered

- Benchmark strategy, scoring, ranking, and budget policy docs
- 6 roles × 3 cases (normal / ambiguous / adversarial) seeded
- PostgreSQL research-schema migration v2 + views + constraints
- Four inactive n8n workflow design JSON files under `workflows/design/`
- Migration script `scripts/migrate.ps1`

## Ranking formula

See `docs/BENCHMARK_RANKING.md` (`rank-v1`).

## Evidence threshold

- ≥10 completed cases / role
- ≥2 adversarial completed
- &lt;20% technical failure rate
- 0 unresolved critical safety failures

## Explicit non-goals completed as non-work

- No permanent role assignment
- No 30-day live benchmark start
- No research-question lifecycle tables
- No SENTINEL / Equitify connectivity
