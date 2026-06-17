#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ProjectRoot = "",
    [string]$PythonPath = "",
    [string]$DatabaseUrl = "",
    [string]$StdoutPath = "nohup.out",
    [string]$StderrPath = "nohup.err",
    [switch]$Foreground,
    [switch]$NoLogs,
    [switch]$StopOnly,
    [switch]$SkipMigration
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

function Get-ConfigJson {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if (-not $raw.Trim()) {
        return $null
    }
    return $raw | ConvertFrom-Json
}

function Resolve-DatabaseUrl {
    param([string]$ExplicitUrl, [string]$Root)
    if ($ExplicitUrl) {
        return $ExplicitUrl
    }
    if ($env:COWAGENT_INVESTMENT_DATABASE_URL) {
        return $env:COWAGENT_INVESTMENT_DATABASE_URL
    }
    $config = Get-ConfigJson (Join-Path $Root "config.json")
    if ($config -and $config.PSObject.Properties["investment_database_url"] -and $config.investment_database_url) {
        return [string]$config.investment_database_url
    }
    return ""
}

function Stop-CowAgent {
    param([string]$Root)
    $pidPath = Join-Path $Root ".cow.pid"
    if (Test-Path -LiteralPath $pidPath) {
        $rawPid = (Get-Content -LiteralPath $pidPath -Raw -ErrorAction SilentlyContinue).Trim()
        if ($rawPid -match "^\d+$") {
            $pidValue = [int]$rawPid
            $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Step "Stopping CowAgent PID $pidValue."
                Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            }
        }
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    }

    $escapedRoot = [regex]::Escape($Root)
    $processes = Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine -match "app\.py" -and
            $_.CommandLine -match $escapedRoot
        }
    foreach ($process in $processes) {
        Write-Step "Stopping matching app.py process PID $($process.ProcessId)."
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$root = Resolve-ProjectRoot $ProjectRoot
Set-Location -LiteralPath $root

if (-not $PythonPath) {
    $PythonPath = Join-Path $root ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonPath)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Python runtime not found. Pass -PythonPath or create .venv first."
    }
    $PythonPath = $cmd.Source
}

$resolvedDatabaseUrl = Resolve-DatabaseUrl $DatabaseUrl $root
if ($resolvedDatabaseUrl) {
    if ($resolvedDatabaseUrl -notmatch "^postgresql(\+\w+)?://") {
        throw "Investment database URL must be a PostgreSQL SQLAlchemy URL."
    }
    $env:COWAGENT_INVESTMENT_DATABASE_URL = $resolvedDatabaseUrl
}

Stop-CowAgent $root
if ($StopOnly) {
    Write-Step "CowAgent stopped."
    exit 0
}

if (-not $SkipMigration) {
    Write-Step "Running Alembic migration: migrations/business/alembic.ini upgrade head."
    & $PythonPath -m alembic -c migrations/business/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }
}

if ($Foreground) {
    Write-Step "Starting CowAgent in foreground."
    & $PythonPath app.py
    exit $LASTEXITCODE
}

$stdoutFullPath = Join-Path $root $StdoutPath
$stderrFullPath = Join-Path $root $StderrPath
$pidPath = Join-Path $root ".cow.pid"

Write-Step "Starting CowAgent in background."
$started = Start-Process -FilePath $PythonPath `
    -ArgumentList @("app.py") `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutFullPath `
    -RedirectStandardError $stderrFullPath `
    -PassThru

Set-Content -LiteralPath $pidPath -Value $started.Id -Encoding ASCII
Write-Step "Started CowAgent PID $($started.Id)."
Write-Step "stdout: $stdoutFullPath"
Write-Step "stderr: $stderrFullPath"

if (-not $NoLogs) {
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath $stdoutFullPath) {
        Get-Content -LiteralPath $stdoutFullPath -Tail 80 -Encoding UTF8
    }
}
