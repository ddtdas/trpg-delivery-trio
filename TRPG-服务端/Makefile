# ===========================================================================
#  TRPG 服务端 —— Makefile
#
#  Windows 上若无 GNU make，请直接使用仓库根目录的 start.bat / stop.bat。
# ===========================================================================

PYTHON ?= python

.PHONY: help install start stop test clean

help:
	@echo TRPG 服务端 —— 可用目标：
	@echo   make install   安装运行依赖 (pip install -r requirements.txt)
	@echo   make start     启动服务（默认 9210 起，占用则自适应 9211..9230）
	@echo   make stop      停止服务并释放端口
	@echo   make test      运行 pytest
	@echo   make clean     清理运行期数据与 Python 缓存

install:
	$(PYTHON) -m pip install -r requirements.txt

start:
	start.bat

stop:
	stop.bat

test:
	$(PYTHON) -m pytest tests/ -q

clean:
	-@if exist run rmdir /s /q run
	-@if exist var rmdir /s /q var
	-@for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	-@if exist .pytest_cache rmdir /s /q .pytest_cache
	-@if exist .hypothesis rmdir /s /q .hypothesis
