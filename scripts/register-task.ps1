# Register the current user's interactive task scheduler.
[CmdletBinding()]
param(
    [string]$TaskName = "GameDailyAutomation",
    [string]$ConfigPath = ""
)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $ProjectRoot "config/settings.json"
}
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Settings file not found: $ConfigPath. Copy config/settings.example.json to config/settings.json and edit it first."
}
$Settings = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ScheduleTime = "17:00"
if ($null -ne $Settings.schedule -and -not [string]::IsNullOrWhiteSpace([string]$Settings.schedule.time)) {
    $ScheduleTime = [string]$Settings.schedule.time
}
if ($ScheduleTime -notmatch '^(?:[01]\d|2[0-3]):[0-5]\d$') { throw "Invalid schedule.time in $ConfigPath: $ScheduleTime" }
$TimeParts = $ScheduleTime.Split(":")
$Start = (Get-Date).Date.AddHours([int]$TimeParts[0]).AddMinutes([int]$TimeParts[1])
if ($Start -le (Get-Date)) { $Start = $Start.AddDays(1) }
$Python = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { $Python = (Get-Command python.exe -ErrorAction Stop).Source }
$Python = [System.IO.Path]::GetFullPath($Python)
$UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$Escape = { param([string]$Value) [System.Security.SecurityElement]::Escape($Value) }
$PythonXml = & $Escape $Python
$ConfigXml = & $Escape $ConfigPath
$RootXml = & $Escape $ProjectRoot
$SidXml = & $Escape $UserSid
$StartBoundary = $Start.ToString("yyyy-MM-dd'T'HH:mm:ss")
$TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Runs GameDailyAutomation only in the logged-in user's unlocked interactive desktop.</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$StartBoundary</StartBoundary><Enabled>true</Enabled>
      <Repetition><Interval>PT5M</Interval><Duration>P1D</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
    <LogonTrigger><Enabled>true</Enabled><UserId>$SidXml</UserId></LogonTrigger>
    <SessionStateChangeTrigger><Enabled>true</Enabled><StateChange>SessionUnlock</StateChange><UserId>$SidXml</UserId></SessionStateChangeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>$SidXml</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Enabled>true</Enabled><Hidden>false</Hidden><WakeToRun>true</WakeToRun>
  </Settings>
  <Actions Context="Author"><Exec><Command>$PythonXml</Command><Arguments>-m game_daily_automation --config &quot;$ConfigXml&quot;</Arguments><WorkingDirectory>$RootXml</WorkingDirectory></Exec></Actions>
</Task>
"@
Register-ScheduledTask -TaskName $TaskName -Xml $TaskXml -Force | Out-Null
Write-Host "Registered task '$TaskName' for user $env:USERNAME at $ScheduleTime."
