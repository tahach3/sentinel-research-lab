# Architecture — Round 0B Foundation

## Containers

Exactly two services on a private Docker bridge network (`srl_net`):

| Service | Image family | Purpose |
| --- | --- | --- |
| `postgres` | `pgvector/pgvector` (PostgreSQL 16 + pgvector) | Authoritative database |
| `n8n` | `n8nio/n8n` Community Edition | Local automation UI / later workflows |

Image tags and digests are pinned in `docker-compose.yml` after pull verification.

## Why PostgreSQL + pgvector (not Qdrant)

| Criterion | pgvector in Postgres | Separate Qdrant |
| --- | --- | --- |
| Simplicity | One DB service | Extra container |
| Memory | Lower on this host (~11 GB RAM) | Higher baseline |
| Backup | Single `pg_dump` | DB + vector volume |
| n8n fit | Postgres already required | Extra integration |
| Cost | Free local | Free local |
| Migration | Can add Qdrant later if needed | Harder to collapse |

**Decision:** Round 0B uses **pgvector**. Qdrant only if later measured vector-search needs justify it.

## Schemas and roles

Database name: `sentinel_research_lab`

| Schema | Role | Purpose |
| --- | --- | --- |
| `n8n` | `n8n_app` | n8n operational tables only |
| `research` | `research_app` | Lab research data (later rounds) |

Administrator role (`postgres` from `.env`) is for init, backup, and restore only.

Cross-schema access between app roles is revoked.

## Trust boundaries

```
[Browser on localhost]
        |
        v
[n8n :127.0.0.1:5678] --private net--> [postgres]
        |
        X  no write path into ai-development-os
        X  no Equitify
        X  no Cursor/Codex triggers
        |
        v
[exports/ files] --manual Taha approval--> future SENTINEL import
```

## Local networking

- Compose network: internal bridge `srl_net`
- Host publishes:
  - `127.0.0.1:5678` → n8n
  - `127.0.0.1:5432` → postgres (localhost tools / backup only)
- No `0.0.0.0` public binds
- No tunnels / public webhooks

## Secrets

- Stored in `.env` (gitignored)
- Documented as placeholders in `.env.example`
- n8n encryption key required for credential encryption at rest inside n8n

## Volumes

| Volume | Contents |
| --- | --- |
| `srl_postgres_data` | PostgreSQL data directory |
| `srl_n8n_data` | n8n local files / settings |

## Future workflow stages (not implemented in 0B)

Planned n8n stages: research → planning → QA → review → debugging, plus approval rationale capture and quota tracking. Round 0B provides only infrastructure.
