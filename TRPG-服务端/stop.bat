@echo off
rem ===========================================================
rem  TRPG server stopper - ASCII wrapper only.
rem  Real logic lives in scripts\stop.ps1 (UTF-8 with BOM).
rem
rem  Usage:
rem    stop.bat           stop the instance recorded in run\server.port
rem    stop.bat 9300      stop the instance listening on port 9300
rem ===========================================================
setlocal
set "PORT=%~1"
if "%PORT%"=="" goto autoport
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1" -Port %PORT%
exit /b %ERRORLEVEL%

:autoport
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
exit /b %ERRORLEVEL%
