@echo off
rem ==========================================================================
rem  TRPG miniprogram client start (wrapper).
rem  Real logic: scripts\start_wechat.ps1 (UTF-8 + BOM).
rem
rem  WeChat mini-programs cannot be launched by a local script the way the
rem  Web client can: they MUST be compiled and loaded by WeChat DevTools.
rem  So this wrapper either (a) finds DevTools cli.bat and opens the project,
rem  or (b) prints clear setup instructions and exits non-zero.
rem
rem  Usage: start.bat [-Wait]
rem    -Wait   run cli.bat synchronously (default: detached, 20s cap)
rem
rem  Exit codes: 0 ok | 1 bad package | 2 DevTools/cli.bat not found | 3 cli failed
rem ==========================================================================
setlocal
set "PS1=%~dp0scripts\start_wechat.ps1"

if not exist "%PS1%" (
  echo [FAIL] missing "%PS1%"
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
exit /b %ERRORLEVEL%
