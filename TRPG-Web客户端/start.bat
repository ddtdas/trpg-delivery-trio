@echo off
rem ==========================================================================
rem  TRPG client start (wrapper). Real logic: scripts\start.ps1 (UTF-8 + BOM).
rem
rem  Usage: start.bat [port] [server-url] [bind-host]
rem    bind-host   optional. Default 0.0.0.0 (LAN reachable).
rem                Use 127.0.0.1 to restrict to loopback only.
rem    port        optional. Default: auto-select first free port 8080..8090.
rem                If the given port is busy the script fails (exit 2).
rem    server-url  optional. Default: auto-detect from ..\trpg-server\run\server.json.
rem
rem  Exit codes: 0 ok (or already running) | 1 env error | 2 port conflict | 3 timeout
rem ==========================================================================
setlocal
set "PORT=%~1"
set "SURL=%~2"
set "BHOST=%~3"
set "PS1=%~dp0scripts\start.ps1"

if not exist "%PS1%" (
  echo [FAIL] missing "%PS1%"
  exit /b 1
)

if "%PORT%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
) else if "%SURL%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Port %PORT%
) else if "%BHOST%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Port %PORT% -ServerUrl "%SURL%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Port %PORT% -ServerUrl "%SURL%" -BindHost "%BHOST%"
)
exit /b %ERRORLEVEL%
