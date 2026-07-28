# Start SENTINEL Research Lab stack (local only).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Write-Output 'Starting Research Lab stack...'
Invoke-SrlCompose -ComposeArgs @('up', '-d')
Write-Output 'Requested up -d. Run .\scripts\status.ps1 to verify health.'
Write-Output 'n8n URL: http://127.0.0.1:5678'
