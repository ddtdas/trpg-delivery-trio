"""TRPG static hosting for web/dist (MIT).

Graceful 404 when the frontend bundle is absent (backend-only checkout).
Python 3.12 compatible.

T2 (additive): 新增玩家端托管 /player/ 与 /player/{path} —— 目录 APP_ROOT/player-web/
(零构建原生页面)。既有 /app 行为零变化 (路由与响应体均未改动)。
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_ROOT = Path(__file__).resolve().parent.parent.parent
DIST_DIR = APP_ROOT / "web" / "dist"
INDEX_FILE = DIST_DIR / "index.html"

# T2 (additive): 玩家端页面目录 (PC/移动浏览器版, 零构建; 由 /player/ 托管)
PLAYER_DIR = APP_ROOT / "player-web"
PLAYER_INDEX = PLAYER_DIR / "index.html"

# 缺文件统一响应 (与既有 frontend_not_built 同风格; spec §1: 不是 {ok,...} 包裹)
PLAYER_NOT_BUILT = {"error": "player_not_built",
                    "detail": "player-web/ 未部署 (缺 index.html)"}

# 玩家端静态文件 Content-Type 显式映射 (spec §1; 其它 -> application/octet-stream)
PLAYER_MEDIA_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}

# R2 cache fix (additive): 静态响应统一 no-cache。
# 无 Cache-Control 时浏览器可长期返回旧文案
# (strings.json 是运行时 fetch), 会让验收者看到旧文案而误判 FAIL。
# no-cache = 每次带 ETag 回源校验, 命中则 304, 不牺牲性能。
# 只改响应头, 不动交付物字节。
NO_CACHE = {"Cache-Control": "no-cache"}

# R2/I8d cache fix (additive): /app/assets 挂载点此前完全不发 Cache-Control
# (starlette StaticFiles 默认不加该头), 于是「无内容哈希」资产的复用期限由浏览器
# 启发式决定 —— 换包后浏览器可能继续用旧副本, 而服务端/磁盘都是新的, 现场查不出来。
# 两条分支:
#   1) 文件名含内容哈希 (Vite 产物 index-XXXXXXXX.js / vendor-XXXXXXXX.js):
#      内容一变 URL 就变, 因此可以**长缓存** (1 年 + immutable) —— 这是前端性能
#      设计的一部分, 不得降级为 no-cache;
#   2) 无内容哈希 (theme-cnmods.css: 由 web/public/ 直接拷贝、人工维护的主题覆盖层):
#      **no-cache** —— 每次带 ETag 回源校验, 命中仍 304, 既不牺牲性能也不陈旧。
# 默认走 (2) (fail-safe): 未识别的扩展名/命名一律宁可回源, 不可陈旧。
HASHED_ASSET_RE = re.compile(r"-[A-Za-z0-9_]{8}\.(?:js|css)$")
ASSET_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def asset_cache_control(name: str) -> str:
    """按「文件名是否含内容哈希」给出该资产的 Cache-Control 值。

    哈希判定只认 Vite 的 js/css 产物命名; 其余一律 no-cache (fail-safe)。
    """
    if HASHED_ASSET_RE.search(name or ""):
        return ASSET_IMMUTABLE["Cache-Control"]
    return NO_CACHE["Cache-Control"]


class _AssetStaticFiles(StaticFiles):
    """/app/assets 挂载点: 逐资产补 Cache-Control (R2/I8d)。

    只覆盖 file_response —— 命中真实文件时 (200 与条件请求 304) 的唯一出口;
    404 与目录穿越都不经过它, 因此不会给「文件不存在」加误导性的缓存头。
    304 分支 (NotModifiedResponse) 的头复制自原始响应, 同样带上这里的 Cache-Control。
    """

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = asset_cache_control(Path(full_path).name)
        return response


def mount_static(app: FastAPI) -> None:
    if (DIST_DIR / "assets").is_dir():
        app.mount("/app/assets", _AssetStaticFiles(directory=str(DIST_DIR / "assets")),
                  name="trpg-assets")

    @app.get("/app")
    def app_index() -> object:
        if INDEX_FILE.is_file():
            return FileResponse(str(INDEX_FILE), media_type="text/html", headers=NO_CACHE)
        return JSONResponse(
            status_code=404,
            content={"error": "frontend_not_built",
                     "detail": "run `npm run build` in web/ to produce web/dist"},
        )

    @app.get("/app/{path:path}")
    def app_asset(path: str) -> object:
        target = (DIST_DIR / path).resolve()
        try:
            target.relative_to(DIST_DIR.resolve())
        except ValueError:
            return JSONResponse(status_code=404, content={"error": "not_found"})
        if target.is_file():
            return FileResponse(str(target), headers=NO_CACHE)
        if INDEX_FILE.is_file():
            return FileResponse(str(INDEX_FILE), media_type="text/html", headers=NO_CACHE)
        return JSONResponse(
            status_code=404,
            content={"error": "frontend_not_built",
                     "detail": "run `npm run build` in web/ to produce web/dist"},
        )

    # ---- T2 (additive): 玩家端静态托管 /player/ --------------------------------
    # 无鉴权 (玩家端页面本身不含密钥; token 由页面内表单填写)。
    # 缺文件 -> 404 {"error":"player_not_built"}; 未知子路径不回退 index
    # (单页内视图切换, 无前端路由, 回退会掩盖拼写错误)。

    def _player_file_response(path: str) -> object:
        root = PLAYER_DIR.resolve()
        target = (PLAYER_DIR / path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            # 路径穿越 -> 同缺文件体 (spec §1: 不暴露目录结构差异)
            return JSONResponse(status_code=404, content=PLAYER_NOT_BUILT)
        if target.is_file():
            media = PLAYER_MEDIA_TYPES.get(target.suffix.lower(),
                                           "application/octet-stream")
            return FileResponse(str(target), media_type=media, headers=NO_CACHE)
        return JSONResponse(status_code=404, content=PLAYER_NOT_BUILT)

    @app.get("/player")
    def player_index_bare() -> object:
        return _player_file_response("index.html")

    @app.get("/player/")
    def player_index() -> object:
        return _player_file_response("index.html")

    @app.get("/player/{path:path}")
    def player_asset(path: str) -> object:
        return _player_file_response(path)

    # ---- T3/t8 (additive): NPC 控制台静态示例页 /npc-demo/ --------------------
    # 独立目录 APP_ROOT/npc-demo/，**不经 vite 构建**（避免与 web/dist 的单出口
    # 构建互相覆盖）；纯静态 HTML + REST 直连，不含 mock。
    demo_dir = APP_ROOT / "npc-demo"
    demo_not_built = {"error": "npc_demo_not_built",
                      "detail": "npc-demo/ 未部署 (缺 index.html)"}

    def _demo_file_response(path: str) -> object:
        root = demo_dir.resolve()
        target = (demo_dir / path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return JSONResponse(status_code=404, content=demo_not_built)
        if target.is_file():
            media = PLAYER_MEDIA_TYPES.get(target.suffix.lower(),
                                           "application/octet-stream")
            return FileResponse(str(target), media_type=media, headers=NO_CACHE)
        return JSONResponse(status_code=404, content=demo_not_built)

    @app.get("/npc-demo")
    def npc_demo_bare() -> object:
        return _demo_file_response("index.html")

    @app.get("/npc-demo/")
    def npc_demo_index() -> object:
        return _demo_file_response("index.html")

    @app.get("/npc-demo/{path:path}")
    def npc_demo_asset(path: str) -> object:
        return _demo_file_response(path)
