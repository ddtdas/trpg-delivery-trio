@echo off
chcp 65001 >nul
setlocal EnableExtensions
title TRPG 服务端 - 首次运行：安装运行依赖

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo ============================================================
echo   TRPG 服务端 —— 首次运行：安装运行依赖
echo   目录 : %ROOT%
echo ============================================================
echo.

rem ============================================================
rem  1) 定位一个可用的 Python 3.12+（与 scripts\start.ps1 的优先级一致）
rem     说明: 统一用 call 调用解释器 —— 若 PATH 上存在 .bat/.cmd 形式的
rem     解释器垫片，不用 call 会让本脚本被直接终止。
rem ============================================================
set "PYEXE="
set "PYARG="

call py -3.12 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 goto :use_py312
call py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 goto :use_py3
call python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
if not errorlevel 1 goto :use_python
call python -c "import sys" >nul 2>&1
if not errorlevel 1 goto :py_old
goto :py_missing

:use_py312
set "PYEXE=py"
set "PYARG=-3.12"
goto :py_ok

:use_py3
set "PYEXE=py"
set "PYARG=-3"
goto :py_ok

:use_python
set "PYEXE=python"
set "PYARG="
goto :py_ok

:py_old
echo [错误] 找到的 Python 版本低于 3.12，本服务端要求 Python 3.12 或更高。
echo        请安装 Python 3.12+（安装时务必勾选 "Add Python to PATH"）后重试。
echo        下载地址: https://www.python.org/downloads/windows/
echo.
pause
exit /b 1

:py_missing
echo [错误] 未找到 Python。
echo        请安装 Python 3.12 或更高版本，并在安装时勾选 "Add Python to PATH"。
echo        下载地址: https://www.python.org/downloads/windows/
echo        安装完成后请关闭本窗口，重新双击本文件。
echo.
pause
exit /b 1

:py_ok
echo [1/3] Python   : %PYEXE% %PYARG%
call %PYEXE% %PYARG% -c "import sys;print('                  版本: ' + sys.version.split()[0]);print('                  路径: ' + sys.executable)"
echo.

rem ============================================================
rem  2) 检查依赖；缺失则安装
rem ============================================================
call %PYEXE% %PYARG% -c "import fastapi,uvicorn,pydantic,aiosqlite,httpx,yaml" >nul 2>&1
if not errorlevel 1 goto :deps_ok

echo [2/3] 依赖     : 缺失，开始安装 ...
echo.
echo -------- 在线安装: python -m pip install -r requirements.txt --------
call %PYEXE% %PYARG% -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 goto :online_failed
goto :after_install

:online_failed
echo.
echo [提示] 在线安装失败（可能本机没有网络，或 pip 源不可达）。

if not exist "%ROOT%\wheels\*.whl" goto :offline_guide
echo -------- 改用随包内置的离线依赖: wheels\ --------
call %PYEXE% %PYARG% -m pip install --no-index --find-links "%ROOT%\wheels" -r "%ROOT%\requirements.txt"
if errorlevel 1 goto :offline_guide
goto :after_install

:offline_guide
echo.
echo ============================================================
echo   离线安装指引（中文）
echo ------------------------------------------------------------
echo   方式一（本机联网时最简单）:
echo     cd /d "%ROOT%"
echo     %PYEXE% %PYARG% -m pip install -r requirements.txt
echo.
echo   方式二（用随包内置的 wheels\ 离线安装）:
echo     cd /d "%ROOT%"
echo     %PYEXE% %PYARG% -m pip install --no-index --find-links wheels -r requirements.txt
echo.
echo   方式三（自己下载 wheel 再拷进 wheels\，适合内网机器）:
echo     在有网的机器上执行:
echo       python -m pip download -r requirements.txt -d wheels --only-binary=:all:
echo     然后把生成的 wheels\ 整个目录拷到本目录下。
echo   注意: wheel 文件名里的 cp 标签必须与目标机 Python 版本一致（cp312 / cp313）。
echo ============================================================
echo.
echo [结果] 依赖仍未安装成功，请按上面指引处理后重新双击本文件。
pause
exit /b 1

:after_install
call %PYEXE% %PYARG% -c "import fastapi,uvicorn,pydantic,aiosqlite,httpx,yaml" >nul 2>&1
if errorlevel 1 goto :verify_failed
goto :deps_ok

:verify_failed
echo.
echo [结果] 安装命令已执行，但依赖仍无法导入，请查看上面的报错信息。
echo        可手动执行下面两行排查:
echo          cd /d "%ROOT%"
echo          %PYEXE% %PYARG% -m pip install -r requirements.txt
pause
exit /b 1

:deps_ok
echo [2/3] 依赖     : OK  (fastapi / uvicorn / pydantic / aiosqlite / httpx / PyYAML 均可导入)
echo.
echo [3/3] 结论     : 依赖已就绪，现在可以双击 start.bat 启动服务端。
echo                  启动后主持端打开 http://^<本机IP^>:^<端口^>/app/
echo                  玩家端打开   http://^<本机IP^>:^<端口^>/player/
echo.
pause
exit /b 0
