# SENTINEL Research Lab

Isolated local research-automation lab. **Not** part of PROJECT SENTINEL (`ai-development-os`).

## What this is

Local Docker foundation for:

- collecting and organizing research evidence;
- later multi-stage research / planning / QA / review workflows in n8n;
- exporting proposals for **manual** Taha-approved import into SENTINEL.

It does **not** modify software projects, trigger coding agents, or write into SENTINEL.

## Stack (Round 0B–4)

| Service | Role |
| --- | --- |
| PostgreSQL + pgvector | Authoritative storage (`n8n` + `research` schemas) |
| n8n Community Edition | Local automation UI (HTTP on loopback only) |

Round 1 adds **benchmarking design + schema only** (no live AI calls). See `docs/BENCHMARKING_STRATEGY.md`.

Round 2 adds the **governed research question and decision lifecycle** (still no AI calls). See `docs/RESEARCH_QUESTION_LIFECYCLE.md`.

Round 3 adds a **simulated multi-model research pipeline** with mock adapters only. See `docs/RESEARCH_ORCHESTRATION.md`.

Round 4 prepares **gated live-provider readiness** (all disabled; zero live calls). See `docs/PROVIDER_PREFLIGHT.md`.

Qdrant is **not** included. See `docs/ARCHITECTURE.md`.

## Prerequisites

- Docker Desktop with WSL2 Linux containers
- Ports `5678` (and optionally `5432`) free on localhost

## Quick start

```powershell
cd C:\Users\Taha\sentinel-research-lab
Copy-Item .env.example .env   # first time only; then fill secrets
# Or use the generated .env from Round 0B setup
.\scripts\start.ps1
.\scripts\status.ps1
```

Open n8n: http://127.0.0.1:5678

Create the owner account yourself in the browser. Do not share that password in Git or chat logs.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/start.ps1` | `docker compose up -d` |
| `scripts/stop.ps1` | `docker compose down` |
| `scripts/status.ps1` | Container / health / port snapshot |
| `scripts/backup.ps1` | Timestamped Postgres dump under `backups/` |
| `scripts/restore-test.ps1` | Restore dump into a throwaway DB, verify, drop |

## Boundaries

Read `docs/PROJECT_BOUNDARIES.md` before adding workflows or credentials.

## Operations

See `docs/OPERATIONS.md`.
