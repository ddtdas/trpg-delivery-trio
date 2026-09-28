@echo off
rem ===========================================================
rem  TRPG server launcher - ASCII wrapper only.
rem  Real logic lives in scripts\start.ps1 (UTF-8 with BOM).
rem
rem  Usage:
rem    start.bat          auto-select port (probes 9210..9230)
rem    start.bat 9300     use port 9300 (exit 2 if already busy)
rem
rem  Exit codes: 0=ok/already-running 1=env-or-dep-error
rem              2=port-conflict      3=health-check-timeout
rem ===========================================================
setlocal
set "PORT=%~1"
if "%PORT%"=="" goto autoport
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -Port %PORT% -Explicit
exit /b %ERRORLEVEL%

:autoport
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
exit /b %ERRORLEVEL%
