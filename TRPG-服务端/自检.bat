@echo off
chcp 65001 >nul
setlocal EnableExtensions
title TRPG 服务端 - 解压后自检

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "FAIL=0"
set "PYOK=0"

echo ============================================================
echo   TRPG 服务端 —— 解压后自检
echo   目录 : %ROOT%
echo   时间 : %DATE% %TIME%
echo ============================================================
echo.

rem ============================================================
rem  1) Python（统一用 call 调用，兼容 PATH 上的 .bat/.cmd 解释器垫片）
rem ============================================================
set "PYEXE="
set "PYARG="
call py -3.12 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 goto :sc_py312
call py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 goto :sc_py3
call python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 goto :sc_python

echo [1/5] Python     : FAIL - 未找到 Python 3.12+（请安装并勾选 Add Python to PATH）
set "FAIL=1"
goto :sc_deps

:sc_py312
set "PYEXE=py"
set "PYARG=-3.12"
goto :sc_pyok

:sc_py3
set "PYEXE=py"
set "PYARG=-3"
goto :sc_pyok

:sc_python
set "PYEXE=python"
set "PYARG="

:sc_pyok
set "PYOK=1"
echo [1/5] Python     : OK
call %PYEXE% %PYARG% -c "import sys;print('                    版本: ' + sys.version.split()[0]);print('                    路径: ' + sys.executable)"

:sc_deps
echo.
rem ============================================================
rem  2) 依赖
rem ============================================================
if "%PYOK%"=="0" goto :sc_deps_skip
call %PYEXE% %PYARG% -c "import fastapi,uvicorn,pydantic,aiosqlite,httpx,yaml" >nul 2>&1
if errorlevel 1 goto :sc_deps_bad
echo [2/5] 依赖       : OK  (fastapi / uvicorn / pydantic / aiosqlite / httpx / PyYAML)
goto :sc_ports

:sc_deps_bad
echo [2/5] 依赖       : FAIL - 缺少运行依赖，请先双击  首次运行-安装依赖.bat
set "FAIL=1"
call %PYEXE% %PYARG% -c "import importlib.util as u;mods=('fastapi','uvicorn','pydantic','aiosqlite','httpx','yaml','multipart','openai');[print('                    ' + m.ljust(12) + ('OK' if u.find_spec(m) else 'MISSING')) for m in mods]"
goto :sc_ports

:sc_deps_skip
echo [2/5] 依赖       : SKIP - 无可用 Python，无法检查
set "FAIL=1"

:sc_ports
echo.
rem ============================================================
rem  3) 端口区间 9210..9230
rem ============================================================
echo [3/5] 端口区间   : 9210..9230（start.bat 会自动挑第一个空闲端口）
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ns=netstat -ano | Select-String -SimpleMatch 'LISTENING'; $busy=@(); foreach($p in 9210..9230){ foreach($l in $ns){ if($l.Line -match (':'+$p+'\s')){ $busy+=$p; break } } }; $free=21-$busy.Count; Write-Host ('                    空闲 ' + $free + ' / 21 个端口'); if($busy.Count -gt 0){ Write-Host ('                    被占用: ' + ($busy -join ', ')) }; if($free -le 0){ exit 1 }"
if errorlevel 1 goto :sc_ports_bad
echo                    结论: OK - 区间内至少有一个空闲端口
goto :sc_files

:sc_ports_bad
echo                    结论: FAIL - 9210..9230 全部被占用，请先释放端口
set "FAIL=1"

:sc_files
echo.
rem ============================================================
rem  4) 关键文件
rem ============================================================
echo [4/5] 关键文件   :
set "MISS=0"
for %%F in (
  "app\main.py"
  "trpg\__init__.py"
  "modules"
  "scripts\start.ps1"
  "scripts\stop.ps1"
  "scripts\_serve.py"
  "start.bat"
  "stop.bat"
  "requirements.txt"
  "configs\access_config.yaml"
  "configs\llm_providers.yaml"
  "configs\table_default.yaml"
  "data"
  "data\.gitkeep"
  "web\dist\index.html"
  "player-web\index.html"
  "player-web\app.css"
  "player-web\app.js"
  "player-web\strings.json"
  "player-web\tokens.json"
  "rulepacks\coc7\rulepack.yaml"
  "README.md"
  "docs\DEPLOY.md"
) do (
  if exist "%ROOT%\%%~F" (
    echo                     OK       %%~F
  ) else (
    echo                     MISSING  %%~F
    set "MISS=1"
  )
)
if "%MISS%"=="1" (echo                    结论: FAIL - 有文件缺失，压缩包可能不完整 & set "FAIL=1") else (echo                    结论: OK - 关键文件齐全)

set "WHL=0"
if exist "%ROOT%\wheels" for %%W in ("%ROOT%\wheels\*.whl") do set /a WHL+=1
echo                    说明: data\ 目录随包只带 .gitkeep，首次启动/首次建桌时
echo                          trpg.db 与 tables_registry.json 由服务端自动创建（属正常）
echo                    离线 wheel: %WHL% 个（wheels\ 目录，缺失不影响在线安装）
if "%WHL%"=="0" echo                    提示: wheels\ 为空，离线安装将不可用，请联网执行 pip install

echo.
rem ============================================================
rem  5) 结论
rem ============================================================
echo ============================================================
if "%FAIL%"=="1" (
  echo   自检结果: FAIL  —— 请按上面的提示处理后重新运行本自检
) else (
  echo   自检结果: PASS  —— 环境就绪，可以双击 start.bat 启动服务端
)
echo ============================================================
echo.
pause
if "%FAIL%"=="1" exit /b 1
exit /b 0
