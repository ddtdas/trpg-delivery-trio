@echo off
chcp 65001 >nul
setlocal EnableExtensions
title TRPG - 准备内置浏览器（把本机 Chrome 复制进包）
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "DEST=%ROOT%\browser"

echo ============================================================
echo   TRPG 服务端 —— 准备内置浏览器
echo   目标目录 : %DEST%
echo ============================================================
echo.
echo 说明：
echo   本交付包默认【不内置】浏览器。启动时会自动按以下顺序探测：
echo     browser\chrome.exe  ^>  系统 Chrome  ^>  Edge  ^>  系统默认浏览器
echo   如果目标机器没有 Chrome/Edge，或你希望完全自包含，
echo   可以现在把本机 Chrome 复制进包（约 430MB）。
echo.

if /i "%TRPG_NO_PAUSE%"=="1" goto :autoyes
choice /c YN /n /m "是否现在把本机 Chrome 复制进包？[Y=复制 / N=取消] "
if errorlevel 2 goto :cancel

:autoyes
set "SRC="
for %%c in (
  "%LOCALAPPDATA%\Google\Chrome\Application",
  "C:\Program Files\Google\Chrome\Application",
  "C:\Program Files (x86)\Google\Chrome\Application"
) do (
  if not defined SRC if exist "%%~c\chrome.exe" set "SRC=%%~c"
)
if not defined SRC (
  echo.
  echo [FAIL] 未找到本机 Chrome 安装目录。
  echo        请先安装 Chrome，或改用手工复制。
  echo        启动器仍可用系统已装的 Chrome / Edge / 默认浏览器。
  if /i not "%TRPG_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo   源   : %SRC%
echo   目标 : %DEST%
echo   正在复制（约 430MB，请稍候）...
echo.
if not exist "%DEST%" mkdir "%DEST%"
xcopy "%SRC%" "%DEST%\" /E /I /Y /Q >nul
if errorlevel 1 (
  echo [FAIL] 复制失败。
  if /i not "%TRPG_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo [OK] 已复制。校验：
if exist "%DEST%\chrome.exe" ( echo      chrome.exe 存在 ) else ( echo [FAIL] chrome.exe 缺失 & if /i not "%TRPG_NO_PAUSE%"=="1" pause & exit /b 1 )
echo.
echo 完成。之后 start.bat 会优先使用 browser\chrome.exe。
if /i not "%TRPG_NO_PAUSE%"=="1" pause
exit /b 0

:cancel
echo.
echo 已取消。启动器仍会用系统 Chrome / Edge / 默认浏览器。
if /i not "%TRPG_NO_PAUSE%"=="1" pause
exit /b 0
