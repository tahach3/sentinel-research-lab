# AGENTS.md

## Cursor Cloud specific instructions

This repo is the **SENTINEL Research Lab** — a local, loopback-only research-automation
lab. The runnable product is two Docker services (**PostgreSQL + pgvector** and
**n8n**) plus a standalone **Python 3** tooling/test suite under `tools/` and `tests/`.
The lifecycle scripts in `scripts/*.ps1` are PowerShell (Windows-targeted); on Linux run
the underlying `docker compose` / `psql` / `pytest` commands directly (see below).

### Services

| Service | Start | Endpoint | Notes |
| --- | --- | --- | --- |
| PostgreSQL + pgvector | `docker compose up -d` | `127.0.0.1:5432` | DB `sentinel_research_lab`, schemas `n8n` + `research`. First boot runs `database/init/01-initialize.sh`. |
| n8n (Community) | `docker compose up -d` | http://127.0.0.1:5678 | Depends on healthy postgres; owner account is created in the browser. |
| Self-Improvement V2 bridge (optional) | `python -m tools.self_improvement_v2.runtime_bridge` | `127.0.0.1:8765` | Loopback-only; needs env `SRL_REPOSITORY_ROOT`, `SRL_STATE_DB`, `SRL_WORKER_TOKEN`. Not required for the basic stack. |

### Docker (non-obvious startup)

- Docker engine + compose plugin are pre-installed. The **daemon is NOT started
  automatically** — start it once per session (it does not run under systemd here):
  `sudo dockerd > /tmp/dockerd.log 2>&1 &` (prefer a tmux session).
- The daemon is configured for this VM with `storage-driver=fuse-overlayfs` and
  `features.containerd-snapshotter=false` in `/etc/docker/daemon.json` (required for
  Docker 29 + fuse-overlayfs), and iptables is switched to the legacy backend. Do not
  revert these or containers will fail to start.
- Socket access: user `ubuntu` is in the `docker` group (effective in a fresh login
  session). If `docker ...` gives a permission error in the current session, either use
  `sudo docker ...` or run `sudo chmod 666 /var/run/docker.sock`.

### Environment file

`docker compose` needs a `.env` (gitignored, so it is not in the repo). If missing, copy
`.env.example` to `.env` and fill the `CHANGE_ME_*` values with any local dev secrets
(the `N8N_ENCRYPTION_KEY` must be 32+ chars). n8n data lives in the `srl_n8n_data` volume;
if you recreate `.env` with a different `N8N_ENCRYPTION_KEY`, existing n8n credentials
become unreadable.

### Database migrations

`scripts/migrate.ps1` is PowerShell. On Linux, apply the SQL files it lists (currently
`002`–`008` under `database/migrations` and `database/seeds`, in that exact order) by
piping each into the postgres container, e.g.
`cat database/migrations/002_benchmarking.sql | docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -v ON_ERROR_STOP=1`.
Verify with `SELECT version, note FROM research.schema_version ORDER BY version;`
(expect versions 1–8). Re-applying is guarded/idempotent.

### Tests / lint

- Run the Python suite from the repo root: `python3 -m pytest`.
- **Gotcha (important):** the Self-Improvement V2 validation runner spawns `python`
  subprocesses with `PYTHONNOUSERSITE=1` and a `python` executable. Test/tooling deps
  (`pytest`, `jsonschema`, `pyyaml`) must therefore be importable from **system**
  site-packages, not just the per-user site — otherwise ~30 `tests/self_improvement_v2`
  tests fail with `ModuleNotFoundError: No module named 'jsonschema'`. The startup update
  script installs them system-wide and creates the `python` -> `python3` shim.
- **Known pre-existing failures (not environment-related):** ~32 tests in
  `tests/test_generate_round5a_docs.py`, `tests/test_validate_round5a.py`, and
  `tests/round5a_kernel/test_validate_kernel.py` fail because recorded manifest SHA-256
  hashes no longer match the committed source files (content drift). These reproduce on a
  clean `master` checkout and are unrelated to setup — do not treat them as setup breakage.
