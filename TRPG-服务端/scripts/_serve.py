#!/usr/bin/env python3
"""TRPG 服务端后台启动器（仅供 scripts/start.ps1 调用，不面向使用者）。

为什么需要这个文件
------------------
PowerShell 的 `Start-Process` 在创建子进程时会打开句柄继承，被拉起的常驻服务进程
会**继承调用方的 stdout 管道句柄并一直持有它**。后果是：只要调用方用管道捕获
start.bat 的输出（例如 `$out = & cmd /c start.bat | Out-String`，或任何 CI 包装），
在服务端停止之前调用方永远读不到 EOF，表现为**卡死**（实测阻塞 >30s，杀掉服务端后
立刻返回）。

改用 WMI(Win32_Process.Create) 拉起本脚本后，服务端与调用方完全解耦（新进程不继承
调用方句柄），同时 stdout/stderr 仍然完整合并写入 run/server.log。

用法
----
    python scripts/_serve.py <port>
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: _serve.py <port>\n")
        return 2
    try:
        port = int(sys.argv[1])
    except (TypeError, ValueError):
        sys.stderr.write("invalid port: %r\n" % (sys.argv[1],))
        return 2

    # scripts/_serve.py -> 上一级即仓库根。不写死任何绝对路径。
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rundir = os.path.join(root, "run")
    os.makedirs(rundir, exist_ok=True)

    # stdout 与 stderr 合并写入 run/server.log
    log = open(os.path.join(rundir, "server.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log

    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        import uvicorn
    except Exception as exc:
        sys.stderr.write("failed to import uvicorn: %s\n" % (exc,))
        return 1

    try:
        uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        sys.stderr.write("uvicorn exited with error: %s\n" % (exc,))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
