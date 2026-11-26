# Remove the GameDailyAutomation scheduled task.
[CmdletBinding()]
param([string]$TaskName = "GameDailyAutomation")
$ErrorActionPreference = "Stop"
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $Existing) {
    Write-Host "Scheduled task '$TaskName' is not registered."
    exit 0
}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Unregistered task '$TaskName'."
