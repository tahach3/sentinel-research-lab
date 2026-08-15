# Self-Improvement V2 — Local Runtime Bridge

Phase 3A provisions a **loopback-only** HTTP bridge around the reviewed Self-Improvement V2 Python worker. It does not replace n8n orchestration, does not activate workflows, and does not perform live AI calls.

## Purpose

n8n (when configured) calls this bridge for deterministic local operations:

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/health` | Non-secret readiness |
| `POST` | `/v2/validate-proposal` | Schema + policy validation, canonical hash |
| `POST` | `/v2/execute` | LOW-only detached worktree execution |
| `POST` | `/v2/finalize` | Bound review + candidate commit (no push/merge) |
| `GET` | `/v2/executions/<execution_id>` | Execution status (paths redacted) |

The bridge **wraps** existing modules under `tools/self_improvement_v2/`. It does not reimplement proposal validation, policy classification, Git worktrees, review binding, finalization, or the experience store.

## Configuration (environment)

| Variable | Required | Notes |
| --- | --- | --- |
| `SRL_REPOSITORY_ROOT` | yes | Must resolve to a `sentinel-research-lab` checkout |
| `SRL_STATE_DB` | yes | SQLite file **outside** tracked repository files |
| `SRL_WORKER_TOKEN` | yes | Bearer token; never commit or print |
| `SRL_WORKER_HOST` | no | Default `127.0.0.1` (loopback only) |
| `SRL_WORKER_PORT` | no | Default `8765` |

Start:

```powershell
$env:SRL_REPOSITORY_ROOT = (git rev-parse --show-toplevel)
$env:SRL_STATE_DB = Join-Path $env:TEMP "srl-self-improvement-v2-state.sqlite"
$env:SRL_WORKER_TOKEN = "<operator-supplied-token>"
$env:SRL_WORKER_HOST = "127.0.0.1"
$env:SRL_WORKER_PORT = "8765"
python -m tools.self_improvement_v2.runtime_bridge
```

## Bind and auth policy

- Bind address is always loopback (`127.0.0.1`). Binding `0.0.0.0` / `::` is rejected.
- `/v2/*` requires `Authorization: Bearer <SRL_WORKER_TOKEN>` with constant-time comparison.
- Maximum JSON body: 256 KB. Unknown fields and caller-supplied `repository_root` / `state_db` / `command` / `env` are rejected.
- Logs redact tokens, authorization headers, absolute worktree paths, and credential-like values.
- Health responses never include secrets, absolute paths, or environment dumps.

## n8n design binding

Inactive design workflow: `workflows/design/self_improvement_loop_v2.json` (`active: false`).

Non-secret meta references (no credential values):

- `meta.localWorkerBaseUrl` — configurable worker base URL (loopback or operator-selected Docker host mapping)
- `meta.workerHeaderAuthCredentialName` — named Header Auth credential reference for the worker bearer token
- `meta.implementerAgentCredentialReference` / `meta.reviewerAgentCredentialReference` — distinct n8n credential **names**
- `meta.implementerModel` / `meta.reviewerModel` — pinned non-secret model IDs
- `meta.agentRuntimePhase` / `meta.agentRuntimeWiringStatus` — Phase 1B inactive wiring surface (`1B` / `WORKFLOW_WIRED`; workflow remains `active: false`)

Normative agent-runtime contract: `docs/SELF_IMPROVEMENT_V2_AGENT_RUNTIME_CONTRACT.md` and `specs/self_improvement/v2/agent_runtime_contract.schema.json`.

Implementer and reviewer agent credential references must stay distinct.

## Pilot limits (recommended handoff)

| Field | Value |
| --- | --- |
| `MAXIMUM_PILOT_COST` | 5 USD |
| `MAXIMUM_AGENT_CALLS` | 6 |
| `PILOT_TIMEOUT` | 30 minutes |

Do not raise these automatically.

## Risk authority

Executable risk authority lives only in the V2 worker (`tools.self_improvement_v2.risk_authority`).

| Field | Meaning |
| --- | --- |
| `declared_risk` | Proposer-supplied assessment (may raise, never lowers) |
| `computed_risk_pre` | Worker-derived from patch text + policy (no apply) |
| `effective_risk_pre` | `stricter(declared, computed_pre)` — must be `LOW` to authorize |
| `computed_risk_post` | Worker-derived from actual applied diff |
| `effective_risk_post` | `stricter(effective_pre, computed_post)` — must stay `LOW` and equal pre |

Worker decisions returned to n8n: `AUTHORIZED` | `DECISION_REQUIRED` | `POLICY_REJECTED`.

n8n may route these decisions. n8n must not compute, override, or manufacture authorization from `proposal.risk_level`.

Policy snapshot is content-addressed (`policy_sha256`) and pinned in the execution bundle. Finalization rechecks current policy; a later policy may tighten or halt, never make an elevated run safer.

### Shared Git object property

Linked Git worktrees share the source repository object database. Rejected or halted post-application executions may leave unreferenced Git objects until normal garbage collection. This is an accepted local implementation property and is why pre-authorization classifies patch text without applying the patch or creating content objects. No automatic aggressive garbage collection is authorized.

## Explicit non-goals

- Live pilot execution
- Workflow activation
- Docker start/reconfigure
- PostgreSQL / migrations
- Push, merge, or remote publish
- Public bind or production URLs
- SENTINEL / Equitify access
