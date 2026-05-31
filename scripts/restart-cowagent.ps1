#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$PythonCommand = "py",
    [string]$StdoutPath = "nohup.out",
    [string]$StderrPath = "nohup.err"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location -LiteralPath $ProjectRoot

$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.ProcessId -ne $PID -and
        $_.CommandLine -and
        ($_.CommandLine -match "CowAgent.*app\.py" -or $_.CommandLine -match "\bapp\.py\b")
    }

foreach ($process in $processes) {
    if ($PSCmdlet.ShouldProcess("PID $($process.ProcessId)", "Stop CowAgent process")) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped CowAgent process PID $($process.ProcessId)"
    }
}

$pidPath = Join-Path $ProjectRoot ".cow.pid"
if (Test-Path -LiteralPath $pidPath) {
    if ($PSCmdlet.ShouldProcess($pidPath, "Remove stale PID file")) {
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    }
}

$stdoutFullPath = Join-Path $ProjectRoot $StdoutPath
$stderrFullPath = Join-Path $ProjectRoot $StderrPath

if ($PSCmdlet.ShouldProcess($ProjectRoot, "Start CowAgent service")) {
    $started = Start-Process -FilePath $PythonCommand `
        -ArgumentList @("app.py") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutFullPath `
        -RedirectStandardError $stderrFullPath `
        -PassThru

    Set-Content -LiteralPath $pidPath -Value $started.Id -Encoding ASCII
    Write-Host "Started CowAgent process PID $($started.Id)"
    Write-Host "stdout: $stdoutFullPath"
    Write-Host "stderr: $stderrFullPath"
}
