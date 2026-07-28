# Restore-test: load a dump into a temporary database, verify, drop. Keep dump file.
param(
  [string]$DumpPath = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Import-SrlPath
Assert-SrlEnv
$root = Get-SrlRoot
$backupDir = Join-Path $root 'backups'

if (-not $DumpPath) {
  $latest = Get-ChildItem -Path $backupDir -Filter 'sentinel_research_lab_*.sql' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if (-not $latest) { throw "No dumps found in $backupDir" }
  $DumpPath = $latest.FullName
}
if (-not (Test-Path $DumpPath)) { throw "Dump not found: $DumpPath" }

$tmpDb = 'srl_restore_test_' + (Get-Date -Format 'yyyyMMddHHmmss')
Write-Output "Restore-test using dump: backups\$(Split-Path $DumpPath -Leaf)"
Write-Output "Temporary database: $tmpDb"

Push-Location $root
try {
  docker compose exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $tmpDb;"
  if ($LASTEXITCODE -ne 0) { throw 'CREATE DATABASE failed' }

  Get-Content -LiteralPath $DumpPath -Raw | docker compose exec -T postgres psql -U postgres -d $tmpDb -v ON_ERROR_STOP=1
  if ($LASTEXITCODE -ne 0) { throw 'Restore psql failed' }

  $verifySql = @"
SELECT nspname FROM pg_namespace WHERE nspname IN ('n8n','research') ORDER BY 1;
SELECT extname FROM pg_extension WHERE extname = 'vector';
SELECT version, note FROM research.schema_version ORDER BY version;
"@
  $verifyOut = $verifySql | docker compose exec -T postgres psql -U postgres -d $tmpDb -v ON_ERROR_STOP=1 -tA
  if ($LASTEXITCODE -ne 0) { throw 'Verification queries failed' }

  $text = ($verifyOut | Out-String)
  if ($text -notmatch 'n8n') { throw 'Verify failed: n8n schema missing after restore' }
  if ($text -notmatch 'research') { throw 'Verify failed: research schema missing after restore' }
  if ($text -notmatch 'vector') { throw 'Verify failed: pgvector extension missing after restore' }
  if ($text -notmatch 'Round 0B') { throw 'Verify failed: schema_version note missing after restore' }

  Write-Output 'Restore verification OK (schemas, pgvector, schema_version).'
}
finally {
  docker compose exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $tmpDb WITH (FORCE);" | Out-Null
  Write-Output "Temporary database dropped: $tmpDb"
  Pop-Location
}
