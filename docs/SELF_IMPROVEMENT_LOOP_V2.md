# Self-Improvement Loop V2

V1 status (historical): **ESCALATE — SELF-IMPROVEMENT V1 ARCHITECTURE FAILED**.

V2 supersedes V1 for all future autonomous implementation work. V2 guarantees:

```text
The exact proposal bytes reviewed
=
the exact proposal bytes executed
=
the exact diff reviewed
=
the exact diff committed
```

## Business and architectural decisions

| Decision | Value |
| --- | --- |
| Business objective | Content-addressed, immutable execution and review for Research Lab self-improvement |
| Primary user | Taha |
| Initial target repository | `sentinel-research-lab` only |
| Production orchestration | n8n (design-only in this phase; `active: false`) |
| Repository execution | Local Python worker under `tools/self_improvement_v2/` |
| Persistent experience | SQLite through an explicitly supplied runtime database path |
| Connectivity | Offline in Phase S2 |
| Promotion boundary | Local candidate commit only after independent review PASS |

The local Python worker is an **authorized development automation tool**. It is not a new application runtime package and must not replace the repository’s SQL-and-n8n production architecture.

## Normative decisions

### SI2-ND-001 — Immutable proposal snapshot

Once an execution begins, its proposal is immutable.

The execution must reference a content-addressed snapshot:

```text
proposal_sha256
proposal_schema_version
baseline_sha
policy_sha256
```

The experience store must never overwrite this snapshot. A later proposal revision receives a new proposal ID and a new hash.

### SI2-ND-002 — Immutable execution bundle

Every successful execution produces an immutable execution bundle containing:

```text
execution_id
proposal_id
proposal_sha256
policy_sha256
baseline_sha
worktree_tree_sha
actual_diff_sha256
changed_paths_sha256
validation_profile_sha256
validation_results_sha256
execution_result_sha256
```

The bundle is serialized canonically and stored append-only.

### SI2-ND-003 — Review content binding

A review is valid only when it binds to all of:

```text
proposal_sha256
execution_id
execution_result_sha256
actual_diff_sha256
worktree_tree_sha
validation_results_sha256
```

A matching `proposal_id` alone is never sufficient. PASS requires empty `security_findings` and empty `architecture_findings`.

### SI2-ND-004 — Finalization without recomputation from mutable proposal data

Finalization must not reload patch content from a mutable proposal row and reapply it.

Finalization must use the already executed, frozen worktree and immutable execution bundle.

Before committing, it must recompute:

```text
worktree_tree_sha
actual_diff_sha256
changed_paths_sha256
```

and compare them with the execution bundle and review binding.

Any mismatch returns:

```text
CONTENT_BINDING_MISMATCH
→ FAILED_FROZEN
```

### SI2-ND-005 — Detached worktree before approval

Execution uses a detached temporary worktree at the exact approved baseline.

No candidate branch is created before independent review PASS.

After review PASS:

1. revalidate immutable bindings;
2. create the local candidate commit in the detached worktree;
3. create the candidate branch ref pointing to that exact commit;
4. record the commit hash;
5. remove the temporary worktree.

Candidate branch format:

```text
self-improvement-v2/<sanitized-candidate-id>/<execution-short-id>
```

### SI2-ND-006 — Segment-aware protected paths

Protected filenames and directory segments are denied at every depth.

Examples that must always be denied:

```text
.env
.env.local
docs/.env
tests/fixtures/.env.production
.git/config
docs/.git/config
tests/fixtures/.git/HEAD
credentials/token.json
docs/secrets/key.txt
```

A broad allowed prefix never overrides a protected segment. **DENY beats ALLOW**.

### SI2-ND-007 — Append-only state transitions

Candidates, proposals, executions, reviews, finalizations, and learning records use immutable event records.

Updates that change content after execution begins are prohibited.

State progression is recorded through append-only events rather than mutable replacement.

### SI2-ND-008 — Independent system validation

The system validator must execute real adversarial probes.

Source-text presence, function-name checks, and declared counts are not proof of:

* path policy;
* review binding;
* immutable storage;
* finalization safety;
* worktree isolation;
* workflow risk routing.

## State machine

Happy path:

```text
CANDIDATE_RECEIVED
→ RESEARCH_VALIDATED
→ PROPOSAL_VALIDATED
→ PROPOSAL_FROZEN
→ RISK_CLASSIFIED
→ AUTO_AUTHORIZED
→ DETACHED_WORKTREE_PREPARED
→ PATCH_APPLIED
→ EXECUTION_BUNDLE_FROZEN
→ VALIDATING
→ REVIEW_PENDING
→ REVIEW_BOUND
→ FINALIZATION_REVALIDATED
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
CONTENT_BINDING_MISMATCH
IMMUTABILITY_VIOLATION
REPAIR_LIMIT_REACHED
FAILED_FROZEN
```

### Transition catalog

#### CANDIDATE_RECEIVED → RESEARCH_VALIDATED

| Field | Value |
| --- | --- |
| Required immutable inputs | `improvement_candidate` JSON |
| Hashes verified | candidate schema only |
| State written | candidate snapshot insert-only |
| Next allowed operations | propose |
| Failure state | `POLICY_REJECTED` |
| Retry behavior | revise candidate offline |

#### RESEARCH_VALIDATED → PROPOSAL_VALIDATED

| Field | Value |
| --- | --- |
| Required immutable inputs | candidate; proposal JSON |
| Hashes verified | proposal schema; candidate_id match |
| State written | proposal validated event |
| Next allowed operations | freeze |
| Failure state | `POLICY_REJECTED` |
| Retry behavior | revise proposal offline |

#### PROPOSAL_VALIDATED → PROPOSAL_FROZEN

| Field | Value |
| --- | --- |
| Required immutable inputs | validated proposal |
| Hashes verified | `proposal_sha256` (canonical); `policy_sha256` |
| State written | `proposal_snapshots` insert-only |
| Next allowed operations | risk classify / execute |
| Failure state | `IMMUTABILITY_VIOLATION` |
| Retry behavior | new proposal_id required for content change |

#### PROPOSAL_FROZEN → RISK_CLASSIFIED

| Field | Value |
| --- | --- |
| Required immutable inputs | frozen proposal; policy |
| Hashes verified | policy hash; path policy |
| State written | risk classification event |
| Next allowed operations | authorize |
| Failure state | `POLICY_REJECTED` or `DECISION_REQUIRED` |
| Retry behavior | none autonomous for MEDIUM/HIGH/PROHIBITED |

#### RISK_CLASSIFIED → AUTO_AUTHORIZED

| Field | Value |
| --- | --- |
| Required immutable inputs | risk `LOW`; frozen proposal |
| Hashes verified | risk level; repair anti-broadening |
| State written | authorization event |
| Next allowed operations | prepare detached worktree |
| Failure state | `DECISION_REQUIRED` / `POLICY_REJECTED` / `REPAIR_LIMIT_REACHED` |
| Retry behavior | one repair max |

#### AUTO_AUTHORIZED → DETACHED_WORKTREE_PREPARED

| Field | Value |
| --- | --- |
| Required immutable inputs | baseline SHA; clean source |
| Hashes verified | `baseline_sha` exact |
| State written | worktree prepared event; no branch/commit |
| Next allowed operations | apply patches |
| Failure state | `BASELINE_MISMATCH` |
| Retry behavior | none |

#### DETACHED_WORKTREE_PREPARED → PATCH_APPLIED

| Field | Value |
| --- | --- |
| Required immutable inputs | frozen patches; path policy |
| Hashes verified | preimage/postimage; structural patch parse |
| State written | patch applied event |
| Next allowed operations | compute actual diff / validate |
| Failure state | `PATCH_REJECTED` |
| Retry behavior | none autonomous |

#### PATCH_APPLIED → EXECUTION_BUNDLE_FROZEN

| Field | Value |
| --- | --- |
| Required immutable inputs | staged tree; actual diff; changed paths |
| Hashes verified | `worktree_tree_sha`; `actual_diff_sha256`; `changed_paths_sha256` |
| State written | `execution_bundles` insert-only (after validation) |
| Next allowed operations | validating |
| Failure state | `FAILED_FROZEN` |
| Retry behavior | none |

#### EXECUTION_BUNDLE_FROZEN / VALIDATING → REVIEW_PENDING

| Field | Value |
| --- | --- |
| Required immutable inputs | frozen execution bundle |
| Hashes verified | `validation_results_sha256`; `execution_result_sha256` |
| State written | review pending event |
| Next allowed operations | independent review |
| Failure state | `VALIDATION_FAILED` |
| Retry behavior | finite repair once |

#### REVIEW_PENDING → REVIEW_BOUND

| Field | Value |
| --- | --- |
| Required immutable inputs | review binding all content hashes |
| Hashes verified | proposal/execution/diff/tree/validation hashes |
| State written | `review_snapshots` insert-only |
| Next allowed operations | finalize |
| Failure state | `REVIEW_FAILED` |
| Retry behavior | none for PASS path; one finite repair |

#### REVIEW_BOUND → FINALIZATION_REVALIDATED

| Field | Value |
| --- | --- |
| Required immutable inputs | execution_id; review_id; frozen worktree |
| Hashes verified | recomputed tree/diff/paths vs bundle+review |
| State written | revalidation event |
| Next allowed operations | commit |
| Failure state | `CONTENT_BINDING_MISMATCH` → `FAILED_FROZEN` |
| Retry behavior | none |

#### FINALIZATION_REVALIDATED → CANDIDATE_COMMITTED

| Field | Value |
| --- | --- |
| Required immutable inputs | frozen staged tree |
| Hashes verified | committed tree equals reviewed tree |
| State written | commit then branch; finalization insert-only |
| Next allowed operations | learning |
| Failure state | `FAILED_FROZEN` |
| Retry behavior | idempotent finalize only |

#### CANDIDATE_COMMITTED → LEARNING_RECORDED → READY_FOR_HUMAN_PROMOTION

| Field | Value |
| --- | --- |
| Required immutable inputs | finalization; review; execution |
| Hashes verified | learning binds proposal/execution hashes |
| State written | learning insert-only; worktree removed |
| Next allowed operations | human promotion only |
| Failure state | `FAILED_FROZEN` |
| Retry behavior | none |

## n8n design workflow routing

`workflows/design/self_improvement_loop_v2.json` remains `active: false`.

Failure and risk routing must be real graph edges (node IDs, types, connections, output indexes, `onError` behavior). Comments, sticky notes, and `jsCode` marker strings are not routes.

Required structural routes include invalid candidate/proposal, MEDIUM/HIGH decision terminals, PROHIBITED policy rejection, worker/validation/review/finalization failure edges into `Failure Router`, and Failure Router outputs to terminal failure states including `CONTENT_BINDING_MISMATCH` → `FAILED_FROZEN`. Only LOW may reach `Detached Worker Execute`.

## Namespace

```text
specs/self_improvement/v2/
tools/self_improvement_v2/
tests/self_improvement_v2/
workflows/design/self_improvement_loop_v2.json
```

V2 must not import V1 promotion or policy enforcement as authoritative logic.

## Security gates

* no arbitrary commands;
* no `shell=True`;
* no `eval`;
* no dynamic imports from proposal data;
* no `os.environ.copy()` in validation;
* no path escape / symlink escape;
* no credential reads / environment credential inheritance;
* no network / PostgreSQL / Docker / migrations;
* no push / merge;
* no SENTINEL or Equitify access.
