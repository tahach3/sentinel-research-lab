# Stop SENTINEL Research Lab stack (volumes retained).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Write-Output 'Stopping Research Lab stack (volumes kept)...'
Invoke-SrlCompose -ComposeArgs @('down')
Write-Output 'Stopped.'
