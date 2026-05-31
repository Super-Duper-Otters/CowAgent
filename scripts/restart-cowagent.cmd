@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-cowagent.ps1" %*
