# Shared helpers for Research Lab scripts. Dot-source only; do not execute alone.
$ErrorActionPreference = 'Stop'

function Get-SrlRoot {
  return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Import-SrlPath {
  $dockerBin = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'
  if (Test-Path $dockerBin) {
    $env:Path = "$dockerBin;" + $env:Path
  }
}

function Assert-SrlEnv {
  $root = Get-SrlRoot
  $envFile = Join-Path $root '.env'
  if (-not (Test-Path $envFile)) {
    throw ".env missing at $envFile - copy .env.example and set secrets first."
  }
}

function Invoke-SrlCompose {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$ComposeArgs
  )
  Import-SrlPath
  Assert-SrlEnv
  $root = Get-SrlRoot
  Push-Location $root
  try {
    & docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
      throw "docker compose failed (exit $LASTEXITCODE): $($ComposeArgs -join ' ')"
    }
  }
  finally {
    Pop-Location
  }
}
