@echo off
chcp 65001 >nul
rem ==========================================================================
rem  TRPG Web client self-check. Real logic: scripts\selfcheck.ps1 (UTF-8 + BOM).
rem  Prints a single verdict line:  PASS or FAIL .
rem  Exit codes: 0 = PASS | 1 = FAIL
rem ==========================================================================
setlocal
set "PS1=%~dp0scripts\selfcheck.ps1"

if not exist "%PS1%" (
  echo [FAIL] missing "%PS1%"
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
exit /b %ERRORLEVEL%
