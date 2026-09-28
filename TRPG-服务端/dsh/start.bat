@echo off
rem ===========================================================
rem  TRPG DSH assistant launcher - ASCII wrapper only.
rem  Real logic lives in scripts\dsh_start.ps1 (UTF-8 with BOM).
rem  Exit codes: 0=ok  1=server-not-healthy
rem ===========================================================
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dsh_start.ps1"
exit /b %ERRORLEVEL%
