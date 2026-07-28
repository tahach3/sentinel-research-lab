# Status snapshot for SENTINEL Research Lab (no secrets printed).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Import-SrlPath
Assert-SrlEnv
$root = Get-SrlRoot
Push-Location $root
try {
  Write-Output '=== compose ps ==='
  docker compose ps
  Write-Output '=== volumes ==='
  docker volume ls --filter 'name=sentinel-research-lab' --filter 'name=srl_'
  Write-Output '=== port listeners ==='
  foreach ($p in 5678, 5432, 6333) {
    $listeners = @(Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) {
      Write-Output "port ${p}: none"
    }
    else {
      foreach ($l in $listeners) {
        Write-Output "port ${p}: $($l.LocalAddress) pid=$($l.OwningProcess)"
      }
    }
  }
  Write-Output '=== n8n HTTP probe ==='
  try {
    $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:5678' -UseBasicParsing -TimeoutSec 5
    Write-Output "n8n HTTP status: $($resp.StatusCode)"
  }
  catch {
    Write-Output "n8n HTTP probe: $($_.Exception.Message)"
  }
}
finally {
  Pop-Location
}
