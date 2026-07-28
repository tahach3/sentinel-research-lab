# Apply pending research-schema SQL migrations (idempotent-ish; stops on error).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Import-SrlPath
Assert-SrlEnv
$root = Get-SrlRoot
Push-Location $root
try {
  $files = @(
    'database\migrations\002_benchmarking.sql',
    'database\seeds\002_benchmark_cases.sql'
  )
  foreach ($rel in $files) {
    $path = Join-Path $root $rel
    if (-not (Test-Path $path)) { throw "Missing $rel" }
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
