@echo off
rem ==========================================================================
rem  TRPG client stop (wrapper). Real logic: scripts\stop.ps1 (UTF-8 + BOM).
rem
rem  Usage: stop.bat [port]
rem    port  optional. Default: read run\client.port.
rem
rem  Exit codes: 0 ok (or was not running) | 1 env error
rem ==========================================================================
setlocal
set "PORT=%~1"
set "PS1=%~dp0scripts\stop.ps1"

if not exist "%PS1%" (
  echo [FAIL] missing "%PS1%"
  exit /b 1
)

if "%PORT%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Port %PORT%
)
exit /b %ERRORLEVEL%
