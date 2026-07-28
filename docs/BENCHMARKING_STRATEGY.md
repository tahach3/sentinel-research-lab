# SENTINEL Research Lab — Provider Benchmarking Strategy

## Why benchmark before role assignment

Providers and models change quickly. Permanent role assignment without measured
evidence creates silent quality and cost risk. Round 1 defines an evidence system
so later live benchmarking can rank candidates for:

1. Researcher
2. Planner
3. Implementation-proposal writer
4. QA checker
5. Independent reviewer
6. Debugger

No permanent provider roles are assigned in Round 1.

## Benchmark lifecycle

1. **Design** (this round): suites, cases, schema, inactive workflows, budget policy.
2. **Authorize**: Taha enables specific providers/models and any paid usage.
3. **Execute**: coordinator creates pending runs, checks quotas, routes through adapters.
4. **Score**: automatic scorers + Taha manual scores (append-only).
5. **Rank**: monthly composite ranking only when evidence thresholds are met.
6. **Assign (later round)**: Taha approves role assignments from rankings.

## Monthly reranking

Rankings are recomputed per `YYYY-MM` and stored in `research.monthly_role_rankings`.
Prior months remain as historical evidence. Model-version drift is tracked via
`models.model_version`; a new version is a distinct ranking entity.

## Evidence thresholds (minimum)

A model may appear in an official monthly ranking for a role only if all hold:

- at least **10** completed cases for that role;
- at least **2** completed adversarial cases;
- technical failure rate **&lt; 20%**;
- **zero** unresolved critical safety failures.

## Taha’s authority

Taha may:

- reject a top-ranked model;
- keep a prior assignment;
- require more cases;
- authorize or deny paid usage.

Automated rankings are advisory. Final role assignment is always human.

## Out of scope (Round 1)

- Live provider calls
- API keys / credentials
- Research-question lifecycle tables
- Permanent role binding
