# Install dependencies and register the per-user interactive scheduled task.
[CmdletBinding()]
param([string]$ConfigPath = "")
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -eq $Launcher) { throw "Python 3.12+ is required. Install Python and create .venv first." }
    & $Launcher.Source -3.12 -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Python virtual environment." }
}
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $VenvPython -m pip install -e $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Project installation failed." }
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $ProjectRoot "config/settings.json" }
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    Copy-Item (Join-Path $ProjectRoot "config/settings.example.json") $ConfigPath
    Write-Warning "Created settings file from example. Edit executable paths and verified arguments before enabling daily game execution."
}
& (Join-Path $PSScriptRoot "register-task.ps1") -ConfigPath $ConfigPath
