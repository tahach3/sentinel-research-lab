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
| `POST` | `/v2/budget/open` | Open a pilot budget session (cost-by-construction assert) |
| `POST` | `/v2/provider-call-permit` | Grant one provider-call permit (refuses 7th call / wall-clock) |
| `POST` | `/v2/provider-call-consume` | Consume permit with mandatory provider/model/credential identity |
| `POST` | `/v2/provider-call-authorize` | One-shot authorize bound to server-issued invocation evidence |
| `POST` | `/v2/wall/capture` | Capture tracked-tree / index / worktree-list fingerprints |
| `POST` | `/v2/wall/assert` | Reassert Wall fingerprints unchanged |

The bridge **wraps** existing modules under `tools/self_improvement_v2/`. It does not reimplement proposal validation, policy classification, Git worktrees, review binding, finalization, or the experience store.

## Pilot budget enforcement (executable)

Callers (n8n) must open a budget session and request a **provider-call permit** before each provider invocation:

1. `POST /v2/budget/open` — asserts worst-case cost `(max_input+max_output)×price×MAX_CALLS < 5 USD` before any call.
2. `POST /v2/provider-call-permit` — decrements the call counter, checks the 30-minute wall clock, requires `max_output_tokens`, refuses the 7th call.

Repair-attempt limits remain in the worker (`repair_policy`); risk authorization remains solely in `risk_authority`.

Trusted security modules must load from the worker install. Worktree-derived `sys.path` entries are rejected (`trusted_origin`).

## Configuration (environment)

| Variable | Required | Notes |
| --- | --- | --- |
| `SRL_REPOSITORY_ROOT` | yes | Absolute path to the reviewed git checkout (**launcher-supplied**) |
| `SRL_REVIEWED_HEAD` | yes | Full commit SHA for this launch (**launcher-supplied**; pin does not claim HEAD) |
| `SRL_STATE_DB` | yes | SQLite file **outside** tracked repository files |
| `SRL_WORKER_TOKEN` | yes | Bearer token; never commit or print |
| `SRL_WORKER_HOST` | no | Default `127.0.0.1` (loopback only) |
| `SRL_WORKER_PORT` | no | Default `8765` |

### Launcher (authentication root — outside the checkout)

Canonical Windows path: `%LOCALAPPDATA%\SentinelResearchLab\launch-worker.ps1`  
Linux/mac fallback used by the installer: `$XDG_DATA_HOME/SentinelResearchLab/launch-worker.sh` (or `~/.local/share/...`).

The launcher is **unversioned and unreviewed by design** — it must live outside the artifact to be a root. It holds:

1. Authorized / reviewed HEAD  
2. Expected SHA-256 of `tools/self_improvement_v2/trusted_origin.py`

It computes the actual verifier digest, **refuses on mismatch** (fail-closed only), sets `SRL_REPOSITORY_ROOT` / `SRL_REVIEWED_HEAD`, then execs the worker.

Install / refresh (same operator action as issuing the authorization line for that HEAD):

```powershell
python -m tools.self_improvement_v2.launcher.install_launcher `
  --repository-root <absolute-reviewed-checkout> `
  --reviewed-head <40-char-sha>
& "$env:LOCALAPPDATA\SentinelResearchLab\launch-worker.ps1"
```

Manual shell assignment of `SRL_REPOSITORY_ROOT` / `SRL_REVIEWED_HEAD` is **not** an attested source and must not be used for supervised pilot runs.

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

## Pilot limits (enforced)

| Field | Value | Enforcer |
| --- | --- | --- |
| `MAXIMUM_PILOT_COST` | 5 USD | `pilot_budget.assert_cost_by_construction` / permit path |
| `MAXIMUM_AGENT_CALLS` | 6 | `pilot_budget.PilotBudgetRegistry.request_call_permit` |
| `PILOT_TIMEOUT` | 30 minutes | same permit path (wall clock) |
| max repair attempts | 1 (second refused) | `repair_policy.assert_repair_attempt_allowed` |

Do not raise these automatically. Cost is **by construction** (pre-call token ceilings × prices), not an after-the-fact estimate.

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

## Zone P probe harness (offline)

`tools/self_improvement_v2/zone_p_harness.py` builds synthetic negative-control packages that are path/patch valid and correctly hash-bound so they reach the Independent Reviewer boundary. Records must use throwaway state DBs (`%TEMP%\srl-zone-p-<id>.sqlite`) and tag `synthetic_control` / `probe_id`. Live Gemini/Groq resolution uses `model_resolution_probe` with an injected transport (no secrets in-repo).

Workflow material comparison (A14): `workflow_normalizer` with explicit `MATERIAL_FIELDS` / `IGNORED_FIELDS` (unknown → fail).

## Explicit non-goals

- Live pilot execution
- Workflow activation
- Docker start/reconfigure
- PostgreSQL / migrations
- Push, merge, or remote publish
- Public bind or production URLs
- SENTINEL / Equitify access


## Trusted-origin launcher anchors (mandatory)

The worker fails closed unless both are set by the external launcher:

- `SRL_REPOSITORY_ROOT` — absolute path to the reviewed git checkout
- `SRL_REVIEWED_HEAD` — full commit SHA authorized for this launch

Do not derive either from CWD or package root. See `docs/SELF_IMPROVEMENT_V2_TRUSTED_ORIGIN_DESIGN.md` (Option A+).
