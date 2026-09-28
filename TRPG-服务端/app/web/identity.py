"""服务端实例身份端点 (SPEC-SERVER-IDENTITY v1.0, additive).

GET /__trpg_server__ —— 「**是本部署**」的判据，与 /api/health 的「**活着**」严格分开。

背景（见 evidence/LAN-TEST/REPORT-T2.md 的 P1 缺陷）
--------------------------------------------------
/api/health 的响应在不同部署/版本之间**逐字节同构**（`{"status":"ok","version":"0.1.0-t12","ts":...}`），
不含任何部署标识；客户端有对等端点 /__trpg_client__，服务端此前没有。
后果：服务端启动器把「端口上有健康实例」误当成「是本部署已在运行」→ L13 谎称幂等并把
run/server.json 覆写成他人实例；L15 自适应落回他人端口。

契约边界
--------
本模块**只新增**一个 additive 端点：不触碰冻结 6 项，不改变任何既有端点的签名与行为
（/api/health 响应逐字节不变）。响应只含部署身份信息，**不含任何密钥/令牌**，故不带鉴权。
本端点的响应头显式声明 `charset=utf-8`（见 Utf8JSONResponse）—— 同样只影响本新增端点。

Python 3.12 compatible.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.config import APP_ROOT, get_version

router = APIRouter()

SERVICE = "trpg-server"


class Utf8JSONResponse(JSONResponse):
    """显式声明 `charset=utf-8` 的 JSON 响应（F1 修复）。

    Starlette 的 `JSONResponse` 默认 `media_type = "application/json"`（**不带 charset**）。
    按 HTTP/1.1 的历史默认，**Windows PowerShell 5.1** 的 `Invoke-WebRequest` 在
    `Content-Type` 无 `charset` 时按 **ISO-8859-1** 解码响应体 —— 于是本端点
    `install_dir` 里的非 ASCII（中文）路径被解成乱码，`start.ps1`/`stop.ps1` 的
    `install_dir` 判据在中文安装路径下恒为 False（SPEC §三 2) 的并集退化为仅
    `deployment_id` 一支；一旦 `run/deployment.id` 丢失/竞态，唯一兜底失效，
    会把**本部署**误判为「别的部署」（假冲突 exit 2 / 拒绝停止 exit 1）。

    响应体本就由 `json.dumps(..., ensure_ascii=False)` 编码为 UTF-8，这里只是把
    事实写进响应头。属 additive：只影响本新增端点。
    """

    media_type = "application/json; charset=utf-8"


# 部署根 = trpg-server 仓库根（app/config.py 的 APP_ROOT = app/ 的上一级）。
# 与 scripts/start.ps1 的 $root（Split-Path -Parent $PSScriptRoot）指向同一目录。
DEPLOYMENT_ROOT = Path(APP_ROOT).resolve()

_RUN_DIR = DEPLOYMENT_ROOT / "run"
_DEPLOYMENT_ID_FILE = _RUN_DIR / "deployment.id"


def path_digest() -> str:
    """部署根绝对路径的稳定摘要（SHA256 前 16 位，小写十六进制）。

    仅在 run/deployment.id 不可读且不可写时作为兜底 —— 保证本端点在任何情况下
    都返回一个**稳定**的 deployment_id，不抛异常。
    Windows 路径大小写不敏感，故先做「正斜杠归一 + 小写」再摘要。
    """
    canon = str(DEPLOYMENT_ROOT).replace("\\", "/").rstrip("/").lower()
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def ensure_deployment_id() -> str:
    """读 run/deployment.id；不存在则生成 UUID v4 落盘，之后每次启动复用。

    scripts/start.ps1 也会在启动前生成同一个文件（两侧同源）；若服务端被直接以
    uvicorn 拉起（不经 start.ps1），这里补生成，保证端点始终可用。
    落盘失败（只读部署等）-> 退化为部署根路径摘要。
    """
    try:
        if _DEPLOYMENT_ID_FILE.is_file():
            v = _DEPLOYMENT_ID_FILE.read_text(encoding="utf-8").strip()
            if v:
                return v
        _RUN_DIR.mkdir(parents=True, exist_ok=True)
        v = str(uuid.uuid4())
        # 显式不带 BOM，方便 PowerShell / 其它语言直接读取
        _DEPLOYMENT_ID_FILE.write_text(v, encoding="utf-8")
        return v
    except (OSError, ValueError):
        # ValueError 覆盖 UnicodeDecodeError：run/deployment.id 若被写入非 UTF-8 字节，
        # read_text(encoding='utf-8') 会抛 UnicodeDecodeError（P3/F4）。若不捕获，
        # 本端点会 500，调用方（start/stop.ps1）将把**本部署**误判为「非 TRPG 服务端」
        # → start.bat 假冲突 exit 2。退化到路径摘要即可（与下方 resolve_port 同风格）。
        return path_digest()


def resolve_port(request: Request) -> int:
    """当前实例真实监听端口。

    首选 ASGI scope 的 server 元组 —— uvicorn 用监听套接字的 getsockname() 填充，
    即**真实绑定端口**，不受 Host 头 / 反向代理影响；
    回退 start.ps1 落盘的 run/server.port；再回退 0（无法确定）。
    """
    srv = request.scope.get("server")
    if isinstance(srv, (tuple, list)) and len(srv) == 2:
        try:
            p = int(srv[1])
            if 1 <= p <= 65535:
                return p
        except (TypeError, ValueError):
            pass
    try:
        p = int((_RUN_DIR / "server.port").read_text(encoding="utf-8").strip())
        if 1 <= p <= 65535:
            return p
    except (OSError, ValueError):
        pass
    return 0


@router.get("/__trpg_server__", response_class=Utf8JSONResponse)
def server_identity(request: Request) -> dict:
    """部署身份（无鉴权；只暴露部署身份信息，不含任何密钥/令牌）。"""
    return {
        "service": SERVICE,
        "ok": True,
        "pid": os.getpid(),
        "port": resolve_port(request),
        "deployment_id": ensure_deployment_id(),
        "install_dir": str(DEPLOYMENT_ROOT),
        "version": get_version(),
    }
