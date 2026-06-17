#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$PythonCommand = "py",
    [string]$PythonVersion = "3.12",
    [string]$DatabaseUrl = "",
    [ValidateSet("None", "User", "Machine")]
    [string]$PersistEnvironmentScope = "User",
    [switch]$InstallOptional,
    [switch]$MigrateSqlite,
    [string]$SqlitePath = "",
    [switch]$SkipMigration,
    [switch]$SkipStart,
    [switch]$WriteDatabaseUrlToConfig,
    [string]$WebHost = "",
    [int]$WebPort = 0,
    [AllowEmptyString()]
    [string]$WebPassword = $null
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

function Test-PyLauncher {
    param([string]$Command)
    $leaf = Split-Path -Leaf $Command
    return $leaf -eq "py" -or $leaf -eq "py.exe"
}

function Invoke-BasePython {
    param([string[]]$Arguments)
    $prefix = @()
    if (Test-PyLauncher $script:PythonCommandResolved) {
        $prefix = @("-$script:PythonVersion")
    }
    & $script:PythonCommandResolved @prefix @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($Arguments -join ' ')"
    }
}

function Get-ConfigJson {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [ordered]@{}
    }
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if (-not $raw.Trim()) {
        return [ordered]@{}
    }
    return $raw | ConvertFrom-Json
}

function Set-JsonProperty {
    param(
        [object]$Config,
        [string]$Name,
        [object]$Value
    )
    if ($null -eq $Config.PSObject.Properties[$Name]) {
        $Config | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    } else {
        $Config.$Name = $Value
    }
}

function Save-ConfigJson {
    param([object]$Config, [string]$Path)
    $json = $Config | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($Path, $json, [System.Text.UTF8Encoding]::new($false))
}

function Resolve-DatabaseUrl {
    param([string]$ExplicitUrl, [object]$Config)
    if ($ExplicitUrl) {
        return $ExplicitUrl
    }
    if ($env:COWAGENT_INVESTMENT_DATABASE_URL) {
        return $env:COWAGENT_INVESTMENT_DATABASE_URL
    }
    if ($Config -and $Config.PSObject.Properties["investment_database_url"] -and $Config.investment_database_url) {
        return [string]$Config.investment_database_url
    }
    throw "Missing PostgreSQL URL. Pass -DatabaseUrl or set COWAGENT_INVESTMENT_DATABASE_URL."
}

function Persist-DatabaseUrl {
    param([string]$Url, [string]$Scope)
    $env:COWAGENT_INVESTMENT_DATABASE_URL = $Url
    if ($Scope -ne "None") {
        [Environment]::SetEnvironmentVariable("COWAGENT_INVESTMENT_DATABASE_URL", $Url, $Scope)
        Write-Step "Saved COWAGENT_INVESTMENT_DATABASE_URL to $Scope environment."
    }
}

function Ensure-Config {
    param([string]$Root, [string]$Url, [bool]$WriteUrl)
    $configPath = Join-Path $Root "config.json"
    if (-not (Test-Path -LiteralPath $configPath)) {
        $template = Join-Path $Root "config-template.json"
        if (-not (Test-Path -LiteralPath $template)) {
            throw "config-template.json not found."
        }
        Copy-Item -LiteralPath $template -Destination $configPath
        Write-Step "Created config.json from config-template.json."
    }

    $config = Get-ConfigJson $configPath
    if ($WriteUrl) {
        Set-JsonProperty $config "investment_database_url" $Url
    }
    if ($WebHost) {
        Set-JsonProperty $config "web_host" $WebHost
    }
    if ($WebPort -gt 0) {
        Set-JsonProperty $config "web_port" $WebPort
    }
    if ($null -ne $WebPassword) {
        Set-JsonProperty $config "web_password" $WebPassword
    }
    Save-ConfigJson $config $configPath
    return $config
}

$script:ProjectRootResolved = Resolve-ProjectRoot $ProjectRoot
Set-Location -LiteralPath $script:ProjectRootResolved

$script:PythonCommandResolved = $PythonCommand
$pythonCmd = Get-Command $script:PythonCommandResolved -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    throw "Python command not found: $script:PythonCommandResolved"
}
$script:PythonCommandResolved = $pythonCmd.Source

Write-Step "Project root: $script:ProjectRootResolved"
Write-Step "Creating or reusing virtual environment."
$venvPython = Join-Path $script:ProjectRootResolved ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-BasePython @("-m", "venv", ".venv")
}

Write-Step "Installing dependencies."
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed." }
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "requirements.txt install failed." }
if ($InstallOptional) {
    & $venvPython -m pip install -r requirements-optional.txt
    if ($LASTEXITCODE -ne 0) { throw "requirements-optional.txt install failed." }
}
& $venvPython -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw "editable install failed." }

$existingConfig = Get-ConfigJson (Join-Path $script:ProjectRootResolved "config.json")
$resolvedDatabaseUrl = Resolve-DatabaseUrl $DatabaseUrl $existingConfig
if ($resolvedDatabaseUrl -notmatch "^postgresql(\+\w+)?://") {
    throw "Investment database URL must be a PostgreSQL SQLAlchemy URL."
}
Persist-DatabaseUrl $resolvedDatabaseUrl $PersistEnvironmentScope
$null = Ensure-Config $script:ProjectRootResolved $resolvedDatabaseUrl ([bool]$WriteDatabaseUrlToConfig)

if (-not $SkipMigration) {
    Write-Step "Running Alembic migration: migrations/investment/alembic.ini upgrade head."
    & $venvPython -m alembic -c migrations/investment/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }
}

if ($MigrateSqlite) {
    $sourceSqlite = $SqlitePath
    if (-not $sourceSqlite) {
        $sourceSqlite = Join-Path $script:ProjectRootResolved "business_storage\investment.db"
    }
    if (-not (Test-Path -LiteralPath $sourceSqlite)) {
        throw "SQLite source database not found: $sourceSqlite"
    }
    Write-Step "Migrating investment SQLite data to PostgreSQL."
    & $venvPython scripts/migrate_investment_sqlite_to_pg.py --sqlite $sourceSqlite --pg $resolvedDatabaseUrl
    if ($LASTEXITCODE -ne 0) { throw "SQLite to PostgreSQL migration failed." }
}

if (-not $SkipStart) {
    Write-Step "Starting CowAgent through restart-windows-server.ps1."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $script:ProjectRootResolved "scripts\restart-windows-server.ps1") `
        -ProjectRoot $script:ProjectRootResolved `
        -PythonPath $venvPython `
        -DatabaseUrl $resolvedDatabaseUrl
    if ($LASTEXITCODE -ne 0) { throw "CowAgent restart failed." }
}

Write-Step "Deployment script finished."
