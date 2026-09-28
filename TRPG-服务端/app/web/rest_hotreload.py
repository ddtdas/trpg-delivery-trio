"""R27 热重载 + R24 一键下载 —— additive APIRouter。

新增路由 (全部 additive, 不动既有路由形状):
  GET  /api/hotreload/status            监听器与绑定状态
  POST /api/hotreload/bind              绑定 campaign -> 模块保存文件 (mtime+sha256)
  POST /api/hotreload/unbind            解绑
  POST /api/hotreload/tick              立即轮询一次 (确定性测试用)
  POST /api/hotreload/apply             手动应用当前保存文件 / 直接应用给定状态
  POST /api/hotreload/rollback          回滚到上一个已应用状态 (旧状态可回滚)
  GET  /api/hotreload/state             当前已应用状态摘要 + 历史深度
  GET  /api/modules/{module_id}/download   一键下载 .modpkg (下载后可直接 import)
  GET  /api/modules/{module_id}/package    产物摘要 (R35-2: 下载前即可拿到该按什么校验)

契约:
  * 帧复用: 本模块**不** import hub / ws_bridge, 不 publish; 变更只经 EventStore.append
    落库, 由既有单一收口 (EventStore.on_append) 广播冻结的 8 帧。
  * 错误: 统一走既有 RepoError 形状 {ok:false, error_code, message, http_status, detail}。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

from app.hotreload import compiled as hc
from app.hotreload import watcher as hrw
from app.hotreload.spec import SAVE_RELPATH, CompiledError
from app.repository import paths as repo_paths
from app.repository.errors import RepoError
from app.repository.pkg import pack_module
from app.repository.roots import RepoRoots

router = APIRouter()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BindBody(StrictModel):
    campaign_id: str
    module_id: str = ""
    table_id: str = ""
    save_path: str = ""


class ApplyBody(StrictModel):
    campaign_id: str
    state: dict[str, Any] | None = None


class RollbackBody(StrictModel):
    campaign_id: str
    steps: int = 1


def _roots() -> RepoRoots:
    try:
        from app.web import rest_repo
        return rest_repo.get_roots()
    except Exception:  # noqa: BLE001
        return RepoRoots.default()


def _err(exc: CompiledError) -> JSONResponse:
    return JSONResponse(status_code=exc.to_dict()["http_status"], content=exc.to_dict())


def install_hotreload(app: Any) -> None:
    """把热重载路由挂到既有 app 上 (幂等)。

    由 app.web.rest_repo.install_repo_error_handler 调用 —— 见该函数内注释:
    这样 app/main.py 不需要新增任何行 (共享文件并发纪律)。

    启动方式 (F-9, 依 captain 裁决: 不接受"惰性"作为终态):
      app/main.py 用了自定义 lifespan, Starlette 在自定义 lifespan 下**不会**执行
      add_event_handler("startup", ...) 的处理器 —— 所以全局 startup 钩子拿不到。
      这里**包一层** app.router.lifespan_context: 原 lifespan 照常进入, 进入后
      (此时已在运行中的事件循环里) 调用 hrw.hunger_start() 回灌绑定表并拉起轮询任务。
      于是语义上等价于「进程起来就监听所有已绑定局」, 且 **app/main.py 零足迹**。

    同时保留路由内的 ensure_watcher() 作为兜底 (TestClient 不走 lifespan 的场景)。
    """
    if getattr(app.state, "_hotreload_installed", False):
        return
    app.include_router(router)
    _install_startup_hook(app)
    app.state._hotreload_installed = True


def _install_startup_hook(app: Any) -> None:
    """把 hunger_start 挂到既有 lifespan 上 (幂等; 不改 app/main.py)。"""
    import logging
    from contextlib import asynccontextmanager

    log = logging.getLogger("trpg.hotreload")
    orig = getattr(app.router, "lifespan_context", None)
    if orig is None or getattr(orig, "_hotreload_wrapped", False):
        return

    @asynccontextmanager
    async def _wrapped(scope_app: Any):
        async with orig(scope_app) as state:
            try:
                info = hrw.hunger_start()
                log.info("hotreload hunger-start: %s", info)
            except Exception as exc:  # noqa: BLE001 — 启动失败不得拖垮应用
                log.warning("hotreload hunger-start failed: %s", exc)
            yield state

    _wrapped._hotreload_wrapped = True
    app.router.lifespan_context = _wrapped


@router.get("/api/hotreload/status")
async def hotreload_status() -> dict[str, Any]:
    return hrw.get_watcher().status()


@router.post("/api/hotreload/bind", status_code=201)
async def hotreload_bind(body: BindBody) -> Any:
    """把 campaign 绑到一个模块的保存文件 (R26 ②「导入后保存文件」) 上。"""
    w = hrw.ensure_watcher()
    roots = _roots()
    mid = body.module_id.strip()
    raw = body.save_path.strip()
    try:
        if raw:
            # R13 路径防线: 相对路径走 safe_join (拒 ../ / URL 编码 / 绝对盘符 / 符号链接);
            # 绝对路径必须字面位于仓库根之内, 且路径组件不得含链接。
            save = (repo_paths.assert_within(roots.modules.parent, Path(raw), label="save_path")
                    if Path(raw).is_absolute()
                    else repo_paths.safe_join(roots.modules, raw, label="save_path"))
        elif mid:
            save = repo_paths.safe_join(
                roots.modules,
                "%s/%s" % (repo_paths.validate_entry_id(mid), hrw.SAVE_RELPATH),
                label="module save_path")
        else:
            return _err(CompiledError("HOTRELOAD_BIND_INVALID",
                                      "必须给出 module_id 或 save_path", {}))
    except RepoError as exc:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    initial = None
    if save.is_file():
        try:
            initial = hc.load_compiled(save)
        except CompiledError as exc:
            return _err(exc)
    b = w.bind(body.campaign_id, mid, save, table_id=body.table_id, initial=initial)
    return {"ok": True, "bound": b.snapshot(), "save_exists": save.is_file(),
            "relpath": SAVE_RELPATH}


@router.post("/api/hotreload/unbind")
async def hotreload_unbind(body: BindBody) -> dict[str, Any]:
    return {"ok": True, "removed": hrw.get_watcher().unbind(body.campaign_id)}


@router.post("/api/hotreload/tick")
async def hotreload_tick() -> dict[str, Any]:
    """立即轮询一次 (确定性测试 / 取证用; 后台任务也在按 interval 轮询)。"""
    hrw.ensure_watcher()
    return await hrw.get_watcher().poll_once()


@router.post("/api/hotreload/apply")
async def hotreload_apply(body: ApplyBody) -> Any:
    hrw.ensure_watcher()
    w = hrw.get_watcher()
    try:
        if body.state is not None:
            return await w.apply_state(body.campaign_id, body.state, source="inline")
        return await w.apply_file(body.campaign_id, source="manual")
    except CompiledError as exc:
        return _err(exc)


@router.post("/api/hotreload/rollback")
async def hotreload_rollback(body: RollbackBody) -> Any:
    hrw.ensure_watcher()
    try:
        return await hrw.get_watcher().rollback(body.campaign_id, body.steps)
    except CompiledError as exc:
        return _err(exc)


@router.get("/api/hotreload/state")
async def hotreload_state(campaign_id: str) -> Any:
    b = hrw.get_watcher().get(campaign_id)
    if b is None:
        # 热重载层的错误码自成一套 (HOTRELOAD_*), 不进 app/repository/errors.ERROR_TABLE ——
        # ERROR_TABLE 是 R13 已验收的错误码表 (36 码), 不得为 t5 扩表而改动其内容。
        return _err(CompiledError("HOTRELOAD_NOT_BOUND",
                                  "campaign 未绑定热重载: %s" % campaign_id,
                                  {"campaign_id": campaign_id}))
    return {"ok": True, "binding": b.snapshot(),
            "counts": (hc.validate_compiled({"module_id": b.module_id, **b.applied_norm})["counts"]
                       if b.applied_norm else None)}


def _module_artifact(module_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """按模组 id 现构建可下载产物 (.modpkg) -> (路径, 产物摘要, 目录摘要)。

    R35-2 的语义澄清（**两个不同的量，不要相互比对**）:
      * 索引条目里的 sha256 / size / files **是解包后目录摘要**
        —— sha256_dir(modules/<id>)，即"每行 <相对路径> + NUL + 该文件 sha256 + 换行"
        拼接后的 sha256、目录内文件大小之和、文件个数（见 app/repository/index.py）。
        队级不变量 I2 明确断言这一等式（entry.sha256 == sha256_dir(dir)），
        因此索引 sha256 **不是**可下载产物的 sha256，也不应被改成产物摘要。
      * 可下载产物的 sha256 是 .modpkg 这个 zip 容器的**字节**摘要 —— 本函数返回的
        artifact。打包走 deterministic=True（固定 packed_at / 固定 zip 条目 mtime），
        所以"同输入必得同字节"：这里算出的 artifact.sha256 与随后 GET /download
        返回的字节 sha256 恒等，可由调用方独立复算（R26 确定性）。
    """
    roots = _roots()
    from app.repository import index as repo_index

    eid = repo_paths.validate_entry_id(module_id)
    src = repo_paths.safe_join(roots.modules, eid, label="modules")
    if not src.is_dir():
        raise RepoError("MODULE_ENTRY_NOT_FOUND", "模组不存在: %s" % eid, {"module_id": eid})
    out = roots.staging / ("dl_%s.modpkg" % eid)
    packed = pack_module(src, out, deterministic=True)
    entry = repo_index.find_entry(roots.modules, "modules", eid,
                                  include_deleted=True) or {}
    dl = "/api/modules/%s/download" % eid
    artifact = {
        "sha256": packed["sha256"], "size": packed["size"], "files": packed["files"],
        "filename": "%s.modpkg" % eid, "path": dl,
        "meaning": "可下载产物 .modpkg 的字节 sha256 —— 校验对象是 GET %s 的响应字节" % dl}
    content = {
        "sha256": entry.get("sha256", ""), "size": entry.get("size"),
        "files": entry.get("files"), "index_ref": "GET /api/modules -> entries[].sha256",
        "meaning": "解包后目录摘要 sha256_dir(modules/%s)：索引条目 sha256/size/files 即此值" % eid}
    return out, artifact, content


@router.get("/api/modules/{module_id}/package")
async def module_package_meta(module_id: str) -> Any:
    """R35-2: 产物摘要（只读，不下载）—— "按模组 id 下载并校验 sha256" 的校验基准。

    契约（写清"索引的 sha256 指什么"）:
      * content.sha256  = 索引条目 sha256 = 模组**目录**摘要（16 文件那个数）；
      * artifact.sha256 = GET /api/modules/{id}/download 响应**字节**的 sha256。
    两者不是同一个量；校验下载物必须用 artifact.sha256。
    """
    _, artifact, content = _module_artifact(module_id)
    return {"ok": True, "module_id": module_id,
            "artifact": artifact, "content": content,
            "download_path": artifact["path"],
            "verify": "sha256(GET %s 的响应字节) == artifact.sha256" % artifact["path"],
            "note": "索引条目 sha256/size/files 是解包后目录摘要(content)，"
                    "与下载产物 digest 不是同一个量；两者都在此显式给出。"}


@router.get("/api/modules/{module_id}/download")
async def module_download(module_id: str) -> Any:
    """R24 一键下载: 把已导入的模组目录打成单文件 .modpkg (下载后可直接 import)。

    R35-2: 响应头同时给出**两个量**，调用方不必再靠猜:
      X-Artifact-Sha256 / X-Artifact-Size -> 本次响应字节(.modpkg)的 sha256 / 大小
      X-Content-Sha256  / X-Content-Size  -> 索引条目里的目录摘要 / 目录文件大小之和
    """
    out, artifact, content = _module_artifact(module_id)
    headers = {
        "X-Artifact-Sha256": str(artifact["sha256"]),
        "X-Artifact-Size": str(artifact["size"]),
        "X-Content-Sha256": str(content["sha256"]),
        "X-Content-Size": str(content["size"]),
        "X-Content-Files": str(content["files"]),
    }
    return FileResponse(str(out), media_type="application/zip",
                        filename=artifact["filename"], headers=headers)
