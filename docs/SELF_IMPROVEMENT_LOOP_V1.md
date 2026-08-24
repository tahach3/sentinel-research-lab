# Self-Improvement Loop V1

## Business and architectural decisions

| Decision | Value |
| --- | --- |
| Business objective | Allow Research Lab agents to improve Research Lab through bounded, independently verified repository changes. |
| Primary user | Taha |
| Initial target repository | `sentinel-research-lab` only |
| Future target | Selected low-risk SENTINEL improvements after three successful Research Lab pilot cycles |
| Production orchestration | n8n |
| Repository execution | Local Python worker under `tools/self_improvement/` |
| Persistent experience | SQLite through an explicitly supplied runtime database path |
| Connectivity | Offline in Phase S1 |
| Promotion boundary | Local candidate commit only |

The local Python worker is an **authorized development automation tool**. It is not a new application runtime package and must not replace the repository’s SQL-and-n8n production architecture.

## Discovery summary

| Concern | Existing convention | V1 decision |
| --- | --- | --- |
| Workflow JSON | Inactive `workflows/design/*.json` with `settings`, `name`, `active:false`, `meta`, `nodes`, `connections` | Same format; new design workflow remains inactive |
| Webhooks / subworkflows | Design mocks; no public webhooks | Interface contract only; no live endpoint in S1 |
| Agent nodes | Mock structured `n8n-nodes-base.code` steps + sticky notes | Stage nodes encode intake→research→implement→review→finalize |
| Structured output | JSON objects from code nodes / SQL bindings | Draft 2020-12 schemas under `specs/self_improvement/v1/` |
| Local-tool CLI | `python -m tools.*` argparse CLIs | `python -m tools.self_improvement.cli` |
| Logging / reports | Deterministic JSON reports without timestamps | `validate_system` and execution results follow same rule |
| Testing | pytest + temp paths | `tests/self_improvement/` with temp repos and SQLite |
| Safe validation | Offline kernel/docs validators | Allowlisted validation profiles only |

## State machine

Happy path:

```text
CANDIDATE_RECEIVED
→ RESEARCH_VALIDATED
→ PROPOSAL_VALIDATED
→ RISK_CLASSIFIED
→ AUTO_AUTHORIZED
→ WORKTREE_PREPARED
→ PATCH_VALIDATED
→ PATCH_APPLIED
→ VALIDATING
→ INDEPENDENT_REVIEW
→ CANDIDATE_COMMITTED
→ LEARNING_RECORDED
→ READY_FOR_HUMAN_PROMOTION
```

Failure states:

```text
DECISION_REQUIRED
BASELINE_MISMATCH
POLICY_REJECTED
PATCH_REJECTED
VALIDATION_FAILED
REVIEW_FAILED
REPAIR_LIMIT_REACHED
FAILED_FROZEN
```

### Transition catalog

#### CANDIDATE_RECEIVED → RESEARCH_VALIDATED

| Field | Value |
| --- | --- |
| Required inputs | `improvement_candidate` JSON |
| Validation | Schema `improvement_candidate.schema.json`; repository=`sentinel-research-lab` |
| Output | Validated candidate record |
| Audit event | `candidate.validated` |
| Failure state | `POLICY_REJECTED` |
| Retry policy | None autonomous; revise candidate offline |

#### RESEARCH_VALIDATED → PROPOSAL_VALIDATED

| Field | Value |
| --- | --- |
| Required inputs | Validated candidate; `implementation_proposal` JSON |
| Validation | Schema `implementation_proposal.schema.json`; candidate_id match; patches present |
| Output | Validated proposal |
| Audit event | `proposal.validated` |
| Failure state | `POLICY_REJECTED` |
| Retry policy | None autonomous; revise proposal |

#### PROPOSAL_VALIDATED → RISK_CLASSIFIED

| Field | Value |
| --- | --- |
| Required inputs | Validated proposal; `policy.json` |
| Validation | Risk level enum; forbidden-path / migration / credential indicators |
| Output | Classified risk (`LOW`/`MEDIUM`/`HIGH`/`PROHIBITED`) |
| Audit event | `risk.classified` |
| Failure state | `POLICY_REJECTED` or `DECISION_REQUIRED` |
| Retry policy | None |

#### RISK_CLASSIFIED → AUTO_AUTHORIZED

| Field | Value |
| --- | --- |
| Required inputs | Risk=`LOW`; `human_approval_required=false` |
| Validation | Only `LOW` auto-authorized; MEDIUM/HIGH/PROHIBITED blocked |
| Output | Authorization token for worker execute |
| Audit event | `risk.auto_authorized` |
| Failure state | `DECISION_REQUIRED` (MEDIUM/HIGH) or `POLICY_REJECTED` (PROHIBITED) |
| Retry policy | Human decision only |

#### AUTO_AUTHORIZED → WORKTREE_PREPARED

| Field | Value |
| --- | --- |
| Required inputs | Clean source tree; exact `baseline_sha` |
| Validation | Root verified; clean worktree; HEAD/`baseline_sha` match |
| Output | Temporary worktree; branch `self-improvement/<candidate-id>/<short-run-id>` |
| Audit event | `worktree.prepared` |
| Failure state | `BASELINE_MISMATCH` |
| Retry policy | None until baseline corrected |

#### WORKTREE_PREPARED → PATCH_VALIDATED

| Field | Value |
| --- | --- |
| Required inputs | Proposal patches; policy limits |
| Validation | Path confinement; no traversal/absolute/binary/symlink/delete; preimage hashes; `git apply --check`; size/file limits |
| Output | Patch validation report |
| Audit event | `patch.validated` |
| Failure state | `PATCH_REJECTED` |
| Retry policy | `FINITE_REPAIR` path only (max 1) |

#### PATCH_VALIDATED → PATCH_APPLIED

| Field | Value |
| --- | --- |
| Required inputs | Checked patches |
| Validation | Apply in temp worktree only; re-verify paths, diff size, postimage hashes |
| Output | Changed paths; diff summary |
| Audit event | `patch.applied` |
| Failure state | `PATCH_REJECTED` |
| Retry policy | Finite repair only |

#### PATCH_APPLIED → VALIDATING

| Field | Value |
| --- | --- |
| Required inputs | `validation_profile` name |
| Validation | Profile must be allowlisted; execute fixed argv arrays via subprocess (no shell) |
| Output | Validation results |
| Audit event | `validation.completed` |
| Failure state | `VALIDATION_FAILED` |
| Retry policy | Finite repair only |

#### VALIDATING → INDEPENDENT_REVIEW

| Field | Value |
| --- | --- |
| Required inputs | Passing validation; separately produced `review_result` |
| Validation | Worker must not generate PASS; require independent reviewer |
| Output | Review gate pending/accepted |
| Audit event | `review.requested` |
| Failure state | `REVIEW_FAILED` |
| Retry policy | See repair policy |

#### INDEPENDENT_REVIEW → CANDIDATE_COMMITTED

| Field | Value |
| --- | --- |
| Required inputs | Review PASS with empty security findings and path/acceptance PASS |
| Validation | `independent_from_implementer=true`; implementer ≠ reviewer |
| Output | Local commit `Self-improvement: <objective>` |
| Audit event | `commit.created` |
| Failure state | `REVIEW_FAILED` |
| Retry policy | No commit without PASS |

#### CANDIDATE_COMMITTED → LEARNING_RECORDED

| Field | Value |
| --- | --- |
| Required inputs | Execution result; review result; explicit SQLite path |
| Validation | Learning-record schema; no secrets/absolute paths |
| Output | Persisted learning record |
| Audit event | `learning.recorded` |
| Failure state | `FAILED_FROZEN` |
| Retry policy | None autonomous |

#### LEARNING_RECORDED → READY_FOR_HUMAN_PROMOTION

| Field | Value |
| --- | --- |
| Required inputs | Learning record; cleaned worktree metadata |
| Validation | Temp worktree removed; no push/merge performed |
| Output | Promotion-ready candidate commit SHA (local only) |
| Audit event | `promotion.ready` |
| Failure state | `FAILED_FROZEN` |
| Retry policy | Human promotion only |

### Failure and repair transitions

| From | To | Trigger |
| --- | --- | --- |
| Any pre-commit state | `DECISION_REQUIRED` | Risk MEDIUM/HIGH or human_approval_required |
| WORKTREE_PREPARED prep | `BASELINE_MISMATCH` | Dirty tree or SHA mismatch |
| Policy/schema checks | `POLICY_REJECTED` | Path/profile/risk violations |
| Patch checks/apply | `PATCH_REJECTED` | Unsafe or mismatched patch |
| Validation profiles | `VALIDATION_FAILED` | Non-zero exit, timeout, acceptance fail |
| Review gate | `REVIEW_FAILED` | Missing/self/non-PASS review |
| `FINITE_REPAIR` after 1 attempt | `REPAIR_LIMIT_REACHED` | Second repair requested |
| `REPAIR_LIMIT_REACHED` | `FAILED_FROZEN` | Terminal freeze |

Repair policy:

1. Independent review may return `FINITE_REPAIR` once.
2. One revised proposal may be executed.
3. A second repair attempt transitions to `REPAIR_LIMIT_REACHED` then `FAILED_FROZEN`.

## Autonomous-lane policy

Allowed paths: `docs/**`, `tests/**`, `tools/self_improvement/**`, `specs/self_improvement/**`, `workflows/design/**`.

Forbidden paths include migrations, credentials, `.env*`, `.git/**`, active workflows, Round 5A/kernel authority artifacts.

Limits: ≤8 files, ≤500 added+removed lines, ≤200 KB patch, ≤1 autonomous repair, deletions/binary/symlinks/push/merge/DB/network/credentials forbidden.

Only risk level `LOW` may be auto-authorized.

## Worker responsibilities

1. Verify repository root, clean source tree, exact baseline SHA.
2. Create temporary Git worktree and unique local branch.
3. Validate and apply patches only inside that worktree.
4. Enforce allowed/forbidden paths before and after patching.
5. Run allowlisted validation profiles with confined subprocesses.
6. Accept an independent review result; never self-PASS.
7. Create a local candidate commit only after review PASS.
8. Record learning in SQLite at an explicit path; remove the temp worktree.
9. Never push, merge, rebase protected branches, modify git config, or broad-clean.

## Independent review boundary

The worker must not generate its own PASS review. Finalize requires a separately produced `review_result.json` with:

- `independent_from_implementer: true`
- `verdict: PASS`
- `contract_alignment: PASS`
- `allowed_path_compliance: PASS`
- `acceptance_results: PASS`
- `security_findings: []`

## Experience store

Python `sqlite3`, explicit runtime path, never committed. Tables: `improvement_candidates`, `implementation_proposals`, `execution_runs`, `validation_results`, `review_results`, `learning_records`, `state_transitions`. Store structured JSON, schema version, content SHA-256, state, error codes, and parent identifiers. Do not store credentials, environment dumps, absolute repository paths, or unbounded command output.

## n8n design workflow

`workflows/design/self_improvement_loop_v1.json` remains `active: false` with placeholder credential references only. Local-worker dispatch interface:

Request: `proposal`, `operation`, `correlation_id`  
Response: `status`, `execution_result`, `error`

## Security requirements

No `shell=True`, `eval`, dynamic imports from proposal data, arbitrary commands, path/symlink escape, environment dumps, credential reads, network, database server, Docker, migration execution, push/merge, or SENTINEL/Equitify access.

## Promotion boundary

V1 stops at a local candidate commit and learning record. Human (Taha) promotion is required before any merge or broader use.
