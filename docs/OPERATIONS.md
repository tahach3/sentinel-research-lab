# Operations

All commands assume:

```powershell
cd C:\Users\Taha\sentinel-research-lab
$env:Path = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;" + $env:Path
```

## Start

```powershell
.\scripts\start.ps1
```

## Stop

```powershell
.\scripts\stop.ps1
```

## Status

```powershell
.\scripts\status.ps1
```

## Backup

```powershell
.\scripts\backup.ps1
```

Creates a timestamped dump under `backups/` (gitignored).

## Restore test

```powershell
.\scripts\restore-test.ps1
```

Restores the newest (or specified) dump into a temporary database, verifies schemas / pgvector / `schema_version`, then drops the temporary database.

## Password rotation

1. `.\scripts\stop.ps1`
2. Update secrets in `.env` (never commit).
3. For role passwords already applied to a live volume, connect as admin and `ALTER ROLE ... PASSWORD ...`, **or** recreate the postgres volume (destructive).
4. If `N8N_ENCRYPTION_KEY` changes, existing n8n encrypted credentials become unreadable — rotate only with a planned re-entry of credentials.
5. `.\scripts\start.ps1` and verify login / DB connectivity.

## n8n upgrade procedure

1. Backup: `.\scripts\backup.ps1`
2. Note current image digest in `docker-compose.yml`
3. Pull the new **pinned** `n8nio/n8n:<version>` tag from Docker Hub
4. Update compose tag **and** digest
5. `docker compose up -d`
6. Verify http://127.0.0.1:5678 and `research.schema_version`
7. Run restore-test against the pre-upgrade backup if anything looks wrong

## PostgreSQL / pgvector upgrade procedure

1. Backup and restore-test successfully
2. Pull new pinned `pgvector/pgvector:` tag
3. Update compose tag and digest
4. Follow PostgreSQL major-upgrade guidance (dump/restore for major versions)
5. Confirm `CREATE EXTENSION vector` still present
6. Confirm n8n still connects (`n8n` schema tables intact)

## Docker DNS note

This host’s router DNS can fail for Docker Hub / registry lookups. Docker Desktop was configured with daemon DNS `8.8.8.8` and `1.1.1.1` during prerequisite install. Do **not** change that configuration unless pulls fail again; if they do, restore those DNS entries in Docker Desktop / `~\.docker\daemon.json` and restart Docker Desktop.

## Local recovery steps

1. `.\scripts\status.ps1` — identify unhealthy service
2. `docker compose logs postgres` / `docker compose logs n8n` (avoid pasting secrets)
3. Confirm ports: only `127.0.0.1:5678` and `127.0.0.1:5432`
4. If database corrupt: stop stack, restore from `backups/` into a fresh volume (documented case-by-case)
5. If n8n UI unreachable but DB healthy: restart `n8n` service only
6. Never point recovery tooling at `ai-development-os` or Equitify
