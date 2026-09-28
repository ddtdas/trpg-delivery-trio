@echo off
chcp 65001 >nul
setlocal EnableExtensions
title TRPG Web 客户端 - 环境检查
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "FAIL=0"
set "PYEXE="
set "PYARG="
set "NEEDSETUP=0"

echo ============================================================
echo   TRPG Web 客户端 —— 环境检查
echo   目录 : %ROOT%
echo   时间 : %DATE% %TIME%
echo ============================================================
echo.

rem ---------- 1) Python ----------
call py -3.12 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 ( set "PYEXE=py" & set "PYARG=-3.12" & goto :pyok )
call py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 ( set "PYEXE=py" & set "PYARG=-3" & goto :pyok )
call python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 ( set "PYEXE=python" & set "PYARG=" & goto :pyok )
echo [1/3] Python   : FAIL  未找到 Python 3.12 或更高版本
echo         请安装 Python 3.12+（安装时勾选 Add python.exe to PATH）
set "FAIL=1"
set "NEEDSETUP=1"
goto :ports
:pyok
echo [1/3] Python   : OK
for /f "delims=" %%v in ('%PYEXE% %PYARG% -c "import sys;print(sys.version.split()[0])"') do echo          版本 %%v

rem ---------- 2) 依赖 ----------
call %PYEXE% %PYARG% -c "import fastapi,uvicorn,pydantic,aiosqlite,httpx,yaml" >nul 2>&1
if errorlevel 1 (
  echo [2/3] 依赖     : FAIL  缺少运行依赖
  set "FAIL=1"
  set "NEEDSETUP=1"
) else (
  echo [2/3] 依赖     : OK  fastapi / uvicorn / pydantic / aiosqlite / httpx / PyYAML
)

:ports
rem ---------- 3) 端口 ----------
set "PORTFREE=0"
for /l %%p in (9210,1,9230) do (
  netstat -ano | findstr ":%%p " | findstr LISTENING >nul 2>&1
  if errorlevel 1 if "%PORTFREE%"=="0" set "PORTFREE=1"
)
if "%PORTFREE%"=="1" ( echo [3/3] 端口     : OK  8080-8090 区间内有空闲端口 ) else ( echo [3/3] 端口     : FAIL  8080-8090 全被占用 & set "FAIL=1" )
echo.

rem ---------- 结论 ----------
if "%FAIL%"=="0" (
  echo ============================================================
  echo   环境就绪。可以双击 start.bat 启动客户端。
  echo ============================================================
  if /i not "%TRPG_NO_PAUSE%"=="1" pause
  exit /b 0
)

echo ============================================================
echo   检测到环境缺失（见上方 FAIL 项）。
echo ============================================================
echo.

rem ---------- 询问是否自动配置 ----------
if /i "%TRPG_AUTO_SETUP%"=="1" goto :autoyes
if /i "%1"=="/y" goto :autoyes
if /i "%1"=="-y" goto :autoyes
choice /c YN /n /m "是否现在自动配置（联网安装 Python 依赖）？[Y=自动配置 / N=退出] "
if errorlevel 2 goto :noauto
:autoyes
echo.
echo 正在自动配置 ...
echo.
set "CFGOK=0"
if "%PYEXE%"=="" goto :cfgfail

rem 优先：离线 wheels（随包，无需联网）
if exist "%ROOT%\wheels" (
  echo   [1/2] 尝试离线安装 wheels\ ...
  call %PYEXE% %PYARG% -m pip install --no-index --find-links "%ROOT%\wheels" -r "%ROOT%\requirements.txt"
  if not errorlevel 1 set "CFGOK=1"
)

if "%CFGOK%"=="0" (
  echo   [2/2] 离线不可用，尝试联网安装 ...
  call %PYEXE% %PYARG% -m pip install -r "%ROOT%\requirements.txt"
  if not errorlevel 1 set "CFGOK=1"
)

if "%CFGOK%"=="1" (
  echo.
  echo 自动配置完成。正在复检 ...
  echo.
  if /i not "%TRPG_NO_PAUSE%"=="1" pause
  call "%~f0" /y2
  exit /b %ERRORLEVEL%
)

:cfgfail
echo.
echo 自动配置失败。请手动执行：
echo   %ROOT%\首次运行-安装依赖.bat
echo 或参考 %ROOT%\使用说明.txt
if /i not "%TRPG_NO_PAUSE%"=="1" pause
exit /b 1

:noauto
echo.
echo 已跳过自动配置。启动时若仍缺依赖，服务端会报错退出。
if /i not "%TRPG_NO_PAUSE%"=="1" pause
exit /b 1
