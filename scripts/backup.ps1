# Backup PostgreSQL to backups/ (gitignored). Does not print secrets.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Import-SrlPath
Assert-SrlEnv
$root = Get-SrlRoot
$backupDir = Join-Path $root 'backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMddTHHmmssZ'
# Use local time stamp label; filename only
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outFile = Join-Path $backupDir "sentinel_research_lab_$stamp.sql"

Push-Location $root
try {
  $leaf = Split-Path $outFile -Leaf
  Write-Output "Creating backup at backups\$leaf ..."
  $remote = "/tmp/$leaf"
  docker compose exec -T postgres pg_dump -U postgres -d sentinel_research_lab --no-owner --no-acl -f $remote
  if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit $LASTEXITCODE" }
  docker compose cp "postgres:$remote" $outFile
  if ($LASTEXITCODE -ne 0) { throw "docker compose cp failed with exit $LASTEXITCODE" }
  docker compose exec -T postgres rm -f $remote | Out-Null
  $item = Get-Item $outFile
  if ($item.Length -lt 100) { throw "Backup file unexpectedly small ($($item.Length) bytes)" }
  Write-Output "Backup OK: size_bytes=$($item.Length) path=backups\$($item.Name)"
}
finally {
  Pop-Location
}
