# encoding:utf-8
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_NAMES = [
    "deploy-windows-server.ps1",
    "update-windows-server.ps1",
    "restart-windows-server.ps1",
]


def test_windows_deploy_scripts_exist_with_required_steps():
    for script_name in SCRIPT_NAMES:
        path = REPO_ROOT / "scripts" / script_name
        assert path.is_file(), f"missing script: {script_name}"
        text = path.read_text(encoding="utf-8")
        assert "Set-StrictMode -Version Latest" in text
        assert "COWAGENT_INVESTMENT_DATABASE_URL" in text
        assert "alembic.ini" in text
        assert "cow" in text or "app.py" in text
        assert "TODO" not in text
        assert "YOUR_" not in text


def test_windows_deploy_scripts_parse_as_powershell():
    powershell = shutil.which("powershell")
    assert powershell, "Windows PowerShell is required to parse deployment scripts"

    for script_name in SCRIPT_NAMES:
        path = REPO_ROOT / "scripts" / script_name
        escaped_path = str(path).replace("'", "''")
        parser = f"""
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}', [ref]$null, [ref]$errors) | Out-Null
if ($errors -and $errors.Count -gt 0) {{
  $errors | ForEach-Object {{ Write-Error $_.Message }}
  exit 1
}}
"""
        result = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", parser],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
