# Apply research-schema SQL migrations/seeds listed below (stop on error).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Import-SrlPath
Assert-SrlEnv
$root = Get-SrlRoot
Push-Location $root
try {
  $files = @(
    'database\migrations\002_benchmarking.sql',
    'database\seeds\002_benchmark_cases.sql',
    'database\migrations\003_research_lifecycle.sql',
    'database\migrations\003a_status_history_after_insert.sql',
    'database\seeds\003_lifecycle_scenarios.sql',
    'database\migrations\004_research_orchestration.sql',
    'database\seeds\004_round3_pilot.sql',
    'database\migrations\005_provider_live_gates.sql'
  )
  foreach ($rel in $files) {
    $path = Join-Path $root $rel
    if (-not (Test-Path $path)) { throw "Missing $rel" }
    # Skip already-applied numbered migrations when schema_version present
    if ($rel -match 'migrations\\002_' ) {
      $has = docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT 1 FROM research.schema_version WHERE version=2;"
      if ("$has".Trim() -eq '1') { Write-Output "SKIP $rel (schema_version 2 present)"; continue }
    }
    if ($rel -match 'seeds\\002_' ) {
      $has = docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT 1 FROM research.benchmark_cases LIMIT 1;"
      if ("$has".Trim() -eq '1') { Write-Output "SKIP $rel (benchmark cases present)"; continue }
    }
    if ($rel -match 'migrations\\003_research_lifecycle' ) {
      $has = docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT 1 FROM research.schema_version WHERE version=3;"
      if ("$has".Trim() -eq '1') { Write-Output "SKIP $rel (schema_version 3 present)"; continue }
    }
    if ($rel -match 'migrations\\003a_' ) {
      $has = docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT 1 FROM pg_trigger WHERE tgname='research_questions_status_history';"
      if ("$has".Trim() -eq '1') { Write-Output "SKIP $rel (status history AFTER trigger present)"; continue }
    }
    if ($rel -match 'seeds\\003_' ) {
      $has = docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT 1 FROM research.research_questions WHERE question_id='RQ-2026-001';"
      if ("$has".Trim() -eq '1') { Write-Output "SKIP $rel (lifecycle seeds present)"; continue }
    }
    if ($rel -match 'migrations\\004_' ) {
      $has = docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT 1 FROM research.schema_version WHERE version=4;"
      if ("$has".Trim() -eq '1') { Write-Output "SKIP $rel (schema_version 4 present)"; continue }
    }
    if ($rel -match 'seeds\\004_' ) {
      $has = docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT 1 FROM research.research_questions WHERE question_id='RQ-2026-R3-001';"
      if ("$has".Trim() -eq '1') { Write-Output "SKIP $rel (round3 pilot present)"; continue }
    }
    if ($rel -match 'migrations\\005_' ) {
      $has = docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT 1 FROM research.schema_version WHERE version=5;"
      if ("$has".Trim() -eq '1') { Write-Output "SKIP $rel (schema_version 5 present)"; continue }
    }
    Write-Output "Applying $rel ..."
    Get-Content -LiteralPath $path -Raw | docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw "Failed applying $rel (exit $LASTEXITCODE)" }
    Write-Output "OK $rel"
  }
  docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -tA -c "SELECT version, note FROM research.schema_version ORDER BY version;"
}
finally {
  Pop-Location
}
