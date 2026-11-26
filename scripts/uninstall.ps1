# Unregister the task; application data and configuration are intentionally preserved.
[CmdletBinding()]
param([string]$TaskName = "GameDailyAutomation")
$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "unregister-task.ps1") -TaskName $TaskName
Write-Host "Application files, settings, database and logs were preserved."
