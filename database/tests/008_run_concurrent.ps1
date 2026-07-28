$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\Taha\sentinel-research-lab'
$env:Path = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;" + $env:Path

Get-Content -LiteralPath 'database\tests\008_concurrent_prepare.sql' -Raw |
  docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -v ON_ERROR_STOP=1 | Out-Null

$jobA = Start-Job -ScriptBlock {
  Set-Location 'C:\Users\Taha\sentinel-research-lab'
  $env:Path = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;" + $env:Path
  Get-Content -LiteralPath 'database\tests\008_concurrent_race.sql' -Raw |
    docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -v ON_ERROR_STOP=1 -v suffix=a -tA
}
$jobB = Start-Job -ScriptBlock {
  Set-Location 'C:\Users\Taha\sentinel-research-lab'
  $env:Path = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;" + $env:Path
  Get-Content -LiteralPath 'database\tests\008_concurrent_race.sql' -Raw |
    docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -v ON_ERROR_STOP=1 -v suffix=b -tA
}

$outA = Receive-Job -Job $jobA -Wait
$outB = Receive-Job -Job $jobB -Wait
Remove-Job $jobA, $jobB -Force

Write-Output "A=$outA"
Write-Output "B=$outB"

$okCount = 0
foreach ($line in @($outA, $outB)) {
  if ($line -match '"ok": true' -or $line -match '\\"ok\\": true' -or $line -match '"ok":true') { $okCount++ }
  # psql jsonb may print without spaces
  if ($line -match 'ok.:t') { }
}
# Parse JSON ok field more reliably
$parsedOk = 0
foreach ($raw in @($outA, $outB)) {
  if (-not $raw) { continue }
  if ($raw -match '"ok"\s*:\s*true') { $parsedOk++ }
}

Write-Output "ok_count=$parsedOk"
if ($parsedOk -ne 1) {
  throw "Expected exactly one concurrent success, got $parsedOk"
}

# Cleanup concurrent fixture and restore defaults
docker compose exec -T postgres psql -U postgres -d sentinel_research_lab -v ON_ERROR_STOP=1 -c "SELECT research.cleanup_test_fixture('r5a-final-concurrent'); SELECT research._r5a_final_reset_defaults(); SELECT research._r5a_final_assert_state();" | Out-Null
Write-Output 'PASS concurrent final-slot'
