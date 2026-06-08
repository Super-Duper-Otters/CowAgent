#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$DatabaseUrl = "",
    [switch]$SkipGitPull,
    [switch]$InstallOptional,
    [switch]$SkipMigration,
    [switch]$SkipStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$DatabaseUrlEnvironmentName = "COWAGENT_INVESTMENT_DATABASE_URL"
$AlembicConfigPath = "migrations/investment/alembic.ini"

function Write-Step {
    param([string]$Message)
    Write-Host "[CowAgent] $Message" -ForegroundColor Cyan
}

function Resolve-ProjectRoot {
    param([string]$Value)
    if ($Value) {
        return (Resolve-Path -LiteralPath $Value).Path
    }
    $scriptDir = Split-Path -Parent $MyInvocation.ScriptName
    $candidate = Split-Path -Parent $scriptDir
    if (Test-Path -LiteralPath (Join-Path $candidate "app.py")) {
        return $candidate
    }
    if (Test-Path -LiteralPath (Join-Path $PWD.Path "app.py")) {
        return $PWD.Path
    }
    throw "Cannot find CowAgent project root. Pass -ProjectRoot."
}

$root = Resolve-ProjectRoot $ProjectRoot
Set-Location -LiteralPath $root

Write-Step "Stopping current CowAgent process if it is running."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts\restart-windows-server.ps1") `
    -ProjectRoot $root `
    -StopOnly `
    -SkipMigration
if ($LASTEXITCODE -ne 0) { throw "Stop step failed." }

if (-not $SkipGitPull) {
    if (Test-Path -LiteralPath (Join-Path $root ".git")) {
        Write-Step "Pulling latest code."
        git pull
        if ($LASTEXITCODE -ne 0) { throw "git pull failed." }
    } else {
        Write-Step "No .git directory found. Skipping git pull."
    }
}

$deployArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $root "scripts\deploy-windows-server.ps1"),
    "-ProjectRoot", $root,
    "-PersistEnvironmentScope", "None"
)
if ($DatabaseUrl) {
    $env:COWAGENT_INVESTMENT_DATABASE_URL = $DatabaseUrl
    $deployArgs += @("-DatabaseUrl", $DatabaseUrl)
} elseif ($env:COWAGENT_INVESTMENT_DATABASE_URL) {
    Write-Step "Using $DatabaseUrlEnvironmentName from the current environment."
}
if ($InstallOptional) {
    $deployArgs += "-InstallOptional"
}
if ($SkipMigration) {
    $deployArgs += "-SkipMigration"
}
if ($SkipStart) {
    $deployArgs += "-SkipStart"
}

Write-Step "Installing dependencies, applying migrations, and restarting if enabled."
& powershell.exe @deployArgs
if ($LASTEXITCODE -ne 0) { throw "Update deployment step failed." }

Write-Step "Update script finished."
