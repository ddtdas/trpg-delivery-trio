"""仓库 REST 路由 (R22 / R1 / R2 / R13 / R3) —— additive 新增文件, 不改冻结文件。

路由清单 (全部 additive, 与既有 40 条路由无冲突):
  GET    /api/repository/error_codes        R13 错误码表
  GET    /api/repository/index              两套索引 + fingerprint
  POST   /api/repository/rebuild            从磁盘重建索引 (重启自愈)

  GET    /api/modules                       列目录 (模组)
  POST   /api/modules/import                导入: 本地包 / 模组库 / 远程 URL (R1/R2)
  GET    /api/modules/{id}                  读单个
  PUT    /api/modules/{id}                  写入 (inline files / source_path)
  DELETE /api/modules/{id}                  软删 (只打标记)
  POST   /api/modules/{id}/restore          取消软删
  GET    /api/modules/{id}/prepared         导入后地图/事件/NPC/线索准备工件 (R3)

  GET    /api/rulepacks                     列目录 (规则包)
  GET    /api/rulepacks/{id}                读单个
  PUT    /api/rulepacks/{id}                写入
  DELETE /api/rulepacks/{id}                软删
  POST   /api/rulepacks/{id}/restore        取消软删
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.repository import index as repo_index
from app.repository import importer as repo_importer
from app.repository import paths as repo_paths
from app.repository import prep as repo_prep
from app.repository import rulepacks as repo_rulepacks
from app.repository.errors import RepoError, error_code_table
from app.repository.paths import safe_join, validate_entry_id
from app.repository.roots import RepoRoots

router = APIRouter()

ROOTS: RepoRoots = RepoRoots.default()


def set_roots(roots: RepoRoots) -> RepoRoots:
    """测试/多实例隔离钩子: 替换仓库根目录集合。"""
    global ROOTS
    ROOTS = roots
    return ROOTS


def get_roots() -> RepoRoots:
    return ROOTS


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportBody(StrictModel):
    source: str = "local"          # local | library | url
    path: str | None = None        # source=local
    module_id: str | None = None   # source=library
    url: str | None = None         # source=url
    sha256: str | None = None      # url 必填; local 可选(给了就校验)
    expected: dict[str, Any] | None = None   # {"scenes":N,"event_nodes":N,"npcs":N}
    overwrite: bool = False
    open_session: bool = False
    session: dict[str, Any] | None = None


class WriteBody(StrictModel):
    manifest: dict[str, Any] | None = None
    files: dict[str, str] | None = None
    module_yaml: str | None = None
    rulepack_yaml: str | None = None
    source_path: str | None = None
    overwrite: bool = False


# --------------------------------------------------------------- helpers

def _entry_or_raise(kind: str, entry_id: str, *, include_deleted: bool,
                    roots: RepoRoots | None = None) -> dict[str, Any]:
    roots = roots or ROOTS
    root = roots.modules if kind == "modules" else roots.rulepacks
    eid = validate_entry_id(entry_id, label="%s id" % kind)
    entry = repo_index.find_entry(root, kind, eid, include_deleted=True)
    if entry is None:
        code = "REPO_ENTRY_NOT_FOUND" if kind == "modules" else "RULEPACK_ENTRY_NOT_FOUND"
        raise RepoError(code, "%s 条目不存在: %s" % (kind, eid), {"id": eid, "kind": kind})
    if entry.get("deleted") and not include_deleted:
        code = "REPO_ENTRY_DELETED" if kind == "modules" else "RULEPACK_ENTRY_DELETED"
        raise RepoError(code, "%s 条目已软删: %s" % (kind, eid),
                        {"id": eid, "kind": kind, "deleted_at": entry.get("deleted_at")})
    return entry


def _list_kind(kind: str, *, include_deleted: bool, q: str, rebuild: bool) -> dict[str, Any]:
    roots = ROOTS.ensure()
    root = roots.modules if kind == "modules" else roots.rulepacks
    idx = repo_index.load_index(root, kind, rebuild=rebuild)
    entries = list(idx.get("entries", []))
    if not include_deleted:
        entries = [e for e in entries if not e.get("deleted")]
    if q:
        needle = q.lower()
        entries = [e for e in entries
                   if needle in str(e.get("id", "")).lower() or needle in str(e.get("name", "")).lower()]
    return {"ok": True, "kind": kind, "count": len(entries),
            "total": idx.get("count", len(entries)),
            "deleted_count": idx.get("deleted_count", 0),
            "fingerprint": idx.get("fingerprint"),
            "index_path": "%s/index.json" % (roots.modules if kind == "modules" else roots.rulepacks).as_posix(),
            "root": root.as_posix(),
            "entries": entries}


def _stage_inline(roots: RepoRoots, files: dict[str, str], *,
                  manifest: dict[str, Any] | None = None,
                  manifest_text: str | None = None,
                  manifest_name: str = "module.yaml",
                  staging: Path | None = None) -> Path:
    """把 inline 内容写到暂存区 (路径穿越防护逐条生效)。

    staging 由调用方先建好并持有引用, 这样中途抛异常时调用方的 finally
    仍能清掉它 —— 不留半成品/空壳目录。
    """
    staging = Path(staging) if staging is not None else Path(roots.staging) / ("put_%s" % uuid.uuid4().hex)
    staging.mkdir(parents=True, exist_ok=True)
    if manifest_text is not None:
        (staging / manifest_name).write_text(manifest_text, encoding="utf-8", newline="\n")
    elif manifest is not None:
        (staging / manifest_name).write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    for rel, content in (files or {}).items():
        target = safe_join(staging, rel, label="write files")
        if not isinstance(content, str):
            raise RepoError("REPO_WRITE_BODY_INVALID", "files[%r] 必须是字符串" % rel, {"key": rel})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    return staging


def _put_entry(kind: str, entry_id: str, body: WriteBody) -> dict[str, Any]:
    roots = ROOTS.ensure()
    root = roots.modules if kind == "modules" else roots.rulepacks
    eid = validate_entry_id(entry_id, label="%s id" % kind)
    target = safe_join(root, eid, label="%s entry" % kind)
    staging: Path | None = None
    try:
        if body.source_path:
            src = Path(body.source_path)
            if not src.is_absolute():
                src = safe_join(roots.imports, body.source_path, label="source_path")
            elif repo_paths.is_symlinkish(src):
                raise RepoError("REPO_PATH_TRAVERSAL",
                                "source_path 是符号链接/junction: %s" % src, {"path": str(src)})
            if not src.is_dir():
                raise RepoError("MODULE_PACKAGE_NOT_FOUND", "source_path 不是目录: %s" % src,
                                {"path": str(src)})
            staging = Path(roots.staging) / ("put_%s" % uuid.uuid4().hex)
            shutil.copytree(src, staging)
        else:
            manifest_name = "module.yaml" if kind == "modules" else "rulepack.yaml"
            text = body.module_yaml if kind == "modules" else body.rulepack_yaml
            if text is None and body.manifest is None and not body.files:
                raise RepoError("REPO_WRITE_BODY_INVALID",
                                "写入需要 manifest/module_yaml/rulepack_yaml/files/source_path 之一",
                                {"kind": kind, "id": eid})
            staging = Path(roots.staging) / ("put_%s" % uuid.uuid4().hex)
            _stage_inline(roots, body.files or {}, manifest=body.manifest,
                          manifest_text=text, manifest_name=manifest_name, staging=staging)

        if kind == "modules":
            checked = repo_importer.validate_package(staging, rulepacks_root=roots.rulepacks)
            if checked["module_id"] != eid:
                raise RepoError("MODULE_ID_MISSING",
                                "manifest.id=%r 与 URL id=%r 不一致" % (checked["module_id"], eid),
                                {"manifest_id": checked["module_id"], "url_id": eid})
        else:
            checked = repo_rulepacks.validate_rulepack(staging)
            if checked["rulepack_id"] != eid:
                raise RepoError("RULEPACK_ID_MISSING",
                                "manifest.id=%r 与 URL id=%r 不一致" % (checked["rulepack_id"], eid),
                                {"manifest_id": checked["rulepack_id"], "url_id": eid})

        repo_importer._commit_dir(staging, target, overwrite=body.overwrite)  # noqa: SLF001
        staging = None
        idx = repo_index.write_index(root, kind)
        entry = repo_index.find_entry(root, kind, eid, include_deleted=True) or {}
        return {"ok": True, "written": True, "kind": kind, "id": eid,
                "entry": entry, "index_fingerprint": idx.get("fingerprint"),
                "validated": checked.get("ok", True)}
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _soft_delete(kind: str, entry_id: str, reason: str) -> dict[str, Any]:
    roots = ROOTS.ensure()
    root = roots.modules if kind == "modules" else roots.rulepacks
    entry = _entry_or_raise(kind, entry_id, include_deleted=True, roots=roots)
    if entry.get("deleted"):
        return {"ok": True, "kind": kind, "id": entry["id"], "deleted": True,
                "already_deleted": True, "deleted_at": entry.get("deleted_at"),
                "physical_delete": False}
    on_disk_dir = safe_join(root, entry["dir"], label="%s entry dir" % kind)
    tomb = repo_index.mark_deleted(root, entry["dir"], reason=reason)
    idx = repo_index.write_index(root, kind)
    return {"ok": True, "kind": kind, "id": entry["id"], "deleted": True,
            "already_deleted": False, "deleted_at": tomb["deleted_at"],
            "physical_delete": False, "path": entry["path"],
            "on_disk": on_disk_dir.is_dir(),
            "index_fingerprint": idx.get("fingerprint")}


def _restore(kind: str, entry_id: str) -> dict[str, Any]:
    roots = ROOTS.ensure()
    root = roots.modules if kind == "modules" else roots.rulepacks
    entry = _entry_or_raise(kind, entry_id, include_deleted=True, roots=roots)
    changed = repo_index.unmark_deleted(root, entry["dir"])
    idx = repo_index.write_index(root, kind)
    return {"ok": True, "kind": kind, "id": entry["id"], "restored": True,
            "changed": changed, "index_fingerprint": idx.get("fingerprint")}


def _detail(kind: str, entry_id: str, include_deleted: bool) -> dict[str, Any]:
    roots = ROOTS.ensure()
    root = roots.modules if kind == "modules" else roots.rulepacks
    entry = _entry_or_raise(kind, entry_id, include_deleted=include_deleted, roots=roots)
    d = safe_join(root, entry["dir"], label="%s entry dir" % kind)
    files = [p.relative_to(d).as_posix() for p in repo_index.dir_files(d)]
    out: dict[str, Any] = {"ok": True, "kind": kind, "entry": entry, "files": files,
                           "dir": d.as_posix()}
    if kind == "modules":
        manifest, name = repo_importer.read_manifest(d)
        out["manifest"] = manifest
        out["manifest_file"] = name
        try:
            checked = repo_importer.validate_package(d, rulepacks_root=roots.rulepacks)
            out["graph_summary"] = {"nodes": checked["counts"]["event_nodes"],
                                    "edges": checked["counts"]["event_edges"],
                                    "initial_scene": checked["manifest"].get("initial_scene")}
            out["npcs"] = [{"id": n.get("id"), "name": n.get("name")} for n in checked["npcs"]]
            out["clues"] = [{"id": c.get("id"), "kind": c.get("kind")} for c in checked["clues"]]
            out["maps"] = [{"id": m.get("id"), "name": m.get("name"),
                            "rooms": len(m.get("rooms") or [])} for m in checked["maps"]]
            out["counts"] = checked["counts"]
            out["valid"] = True
        except RepoError as exc:
            out["valid"] = False
            out["validation_error"] = exc.to_dict()
    else:
        try:
            checked = repo_rulepacks.validate_rulepack(d)
            out["manifest"] = checked["manifest"]
            out["manifest_file"] = checked["manifest_name"]
            out["valid"] = True
        except RepoError as exc:
            out["valid"] = False
            out["validation_error"] = exc.to_dict()
    return out


def _prepared(entry_id: str) -> dict[str, Any]:
    roots = ROOTS.ensure()
    entry = _entry_or_raise("modules", entry_id, include_deleted=False, roots=roots)
    p = Path(roots.prep) / ("%s.json" % entry["id"])
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return {"ok": True, "module_id": entry["id"], "cached": True,
                    "prep_ref": p.as_posix(), "prepared": data}
        except Exception:
            pass
    d = safe_join(roots.modules, entry["dir"], label="modules entry dir")
    checked = repo_importer.validate_package(d, rulepacks_root=roots.rulepacks)
    prepared = repo_prep.prepare(d, manifest=checked["manifest"], graph=checked["graph"],
                                 clues=checked["clues"], npcs=checked["npcs"],
                                 maps=checked["maps"], module_sha256=entry.get("sha256", ""),
                                 npc_paths=checked["npc_paths"])
    return {"ok": True, "module_id": entry["id"], "cached": False,
            "prep_ref": None, "prepared": prepared}


# --------------------------------------------------------------- routes

@router.get("/api/repository/error_codes")
def repository_error_codes() -> dict[str, Any]:
    """R13 错误码表: 5 类坏包各自独立错误码 + 全量码表。"""
    from app.repository.errors import R13_BAD_PACKAGE_CODES

    out = error_code_table()
    out["r13_bad_package_codes"] = R13_BAD_PACKAGE_CODES
    return out


@router.get("/api/repository/index")
def repository_index(rebuild: bool = False) -> dict[str, Any]:
    roots = ROOTS.ensure()
    mod = repo_index.load_index(roots.modules, "modules", rebuild=rebuild)
    rp = repo_index.load_index(roots.rulepacks, "rulepacks", rebuild=rebuild)
    return {"ok": True, "modules": mod, "rulepacks": rp}


@router.post("/api/repository/rebuild")
def repository_rebuild() -> dict[str, Any]:
    roots = ROOTS.ensure()
    out = repo_index.rebuild_all(roots)
    return {"ok": True, "rebuilt": True,
            "modules": {"count": out["modules"]["count"],
                        "fingerprint": out["modules"]["fingerprint"],
                        "index": (roots.modules / "index.json").as_posix()},
            "rulepacks": {"count": out["rulepacks"]["count"],
                          "fingerprint": out["rulepacks"]["fingerprint"],
                          "index": (roots.rulepacks / "index.json").as_posix()}}


# ---- modules ----

@router.get("/api/modules")
def list_modules(include_deleted: bool = False, q: str = "", rebuild: bool = False) -> dict[str, Any]:
    return _list_kind("modules", include_deleted=include_deleted, q=q, rebuild=rebuild)


@router.post("/api/modules/import", status_code=201)
def import_module_route(body: ImportBody) -> dict[str, Any]:
    """R1/R2: 上传/指定包 -> 解析 manifest -> 校验 -> 落库 -> 返回开局句柄。"""
    return repo_importer.import_module(
        source=body.source, roots=ROOTS, path=body.path, module_id=body.module_id,
        url=body.url, sha256=body.sha256, expected=body.expected,
        overwrite=body.overwrite, open_session_handle=body.open_session,
        session=body.session)


@router.get("/api/modules/{module_id}")
def get_module(module_id: str, include_deleted: bool = False) -> dict[str, Any]:
    return _detail("modules", module_id, include_deleted)


@router.put("/api/modules/{module_id}")
def put_module(module_id: str, body: WriteBody) -> dict[str, Any]:
    return _put_entry("modules", module_id, body)


@router.delete("/api/modules/{module_id}")
def delete_module(module_id: str, reason: str = "") -> dict[str, Any]:
    return _soft_delete("modules", module_id, reason)


@router.post("/api/modules/{module_id}/restore")
def restore_module(module_id: str) -> dict[str, Any]:
    return _restore("modules", module_id)


@router.get("/api/modules/{module_id}/prepared")
def get_module_prepared(module_id: str) -> dict[str, Any]:
    return _prepared(module_id)


# ---- rulepacks ----

@router.get("/api/rulepacks")
def list_rulepacks(include_deleted: bool = False, q: str = "", rebuild: bool = False) -> dict[str, Any]:
    return _list_kind("rulepacks", include_deleted=include_deleted, q=q, rebuild=rebuild)


@router.get("/api/rulepacks/{rulepack_id}")
def get_rulepack(rulepack_id: str, include_deleted: bool = False) -> dict[str, Any]:
    return _detail("rulepacks", rulepack_id, include_deleted)


@router.put("/api/rulepacks/{rulepack_id}")
def put_rulepack(rulepack_id: str, body: WriteBody) -> dict[str, Any]:
    return _put_entry("rulepacks", rulepack_id, body)


@router.delete("/api/rulepacks/{rulepack_id}")
def delete_rulepack(rulepack_id: str, reason: str = "") -> dict[str, Any]:
    return _soft_delete("rulepacks", rulepack_id, reason)


@router.post("/api/rulepacks/{rulepack_id}/restore")
def restore_rulepack(rulepack_id: str) -> dict[str, Any]:
    return _restore("rulepacks", rulepack_id)


# ---- path guard middleware (R22 判据 3, 在路由之前拦掉编码绕过) ----

GUARD_PREFIXES = ("/api/modules", "/api/rulepacks", "/api/repository")


def _guard_reason(raw_path: str) -> str:
    """返回拒绝原因; 空串表示放行。只看 wire 上的原始路径 (raw_path)。"""
    s = str(raw_path or "").split("?", 1)[0]
    low = s.lower()
    if "%2f" in low or "%5c" in low:
        return "路径含编码的路径分隔符(%2f/%5c)"
    if "%2e" in low:
        return "路径含编码的点(%2e)"
    dec = repo_paths.decode_layers(s).replace("\\", "/")
    if "\x00" in dec:
        return "路径含 NUL 字节"
    if ".." in [p for p in dec.split("/")]:
        return "路径含 .. 上跳"
    return ""


class RepoPathGuard:
    """纯 ASGI 中间件: 对仓库 API 前缀做编码绕过预检 (additive, 不动既有路由)。"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            raw = scope.get("raw_path") or b""
            if isinstance(raw, bytes):
                raw_s = raw.decode("latin-1")
            else:
                raw_s = str(raw)
            path = str(scope.get("path") or "")
            if any(path.startswith(p) or raw_s.startswith(p) for p in GUARD_PREFIXES):
                reason = _guard_reason(raw_s)
                if reason:
                    err = RepoError("REPO_PATH_TRAVERSAL", reason,
                                    {"raw_path": raw_s, "path": path, "prefixes": list(GUARD_PREFIXES)})
                    resp = JSONResponse(status_code=err.http_status, content=err.to_dict())
                    await resp(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def install_repo_path_guard(app: Any) -> None:
    app.add_middleware(RepoPathGuard)


# ---- error handler ----

def install_repo_error_handler(app: Any) -> None:
    """把 RepoError 映射为明确 JSON: {error_code, message, http_status, detail}。"""

    @app.exception_handler(RepoError)
    async def _repo_error_handler(_request: Any, exc: RepoError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    # R27 (additive): 热重载路由的挂载点。
    # 为什么不直接写进 app/main.py: main.py 是多人共享文件 (t2/t3/t7 同时涉及),
    # 为不再扩大并发冲突面, 热重载路由**复用本 install 钩子**挂载 —— main.py 无需改动,
    # 我的足迹保持 +7 行不变。挂载失败只记日志, 绝不影响既有 R13 错误码契约。
    try:
        from app.web.rest_hotreload import install_hotreload

        install_hotreload(app)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("trpg.repo").exception("install_hotreload failed")
