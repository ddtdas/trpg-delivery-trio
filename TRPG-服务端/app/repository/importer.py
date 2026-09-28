"""模组导入编排 (R1 / R2 / R13 / R3) —— additive。

一次导入的固定顺序 (错误码按此顺序产生, 便于验收):
  1. 取包 (local 目录 / local zip|modpkg / 模组库 / 远程 URL) -> 暂存区
  2. sha256 校验 (URL 必填; local 若给了也必须一致)          -> MODULE_PACKAGE_SHA256_*
  3. 解析 manifest                                            -> MODULE_MANIFEST_MISSING
  4. id 校验                                                  -> MODULE_ID_MISSING
  5. schema/引擎版本                                          -> MODULE_VERSION_INCOMPATIBLE
  6. ruleset 存在性                                           -> MODULE_RULESET_*
  7. 引用文件齐全                                             -> MODULE_FILE_MISSING
  8. 事件图非空 / 悬挂边                                      -> MODULE_GRAPH_* / MODULE_GRAPH_DANGLING_EDGE
  9. initial_scene                                            -> MODULE_INITIAL_SCENE_INVALID
 10. 内部引用一致性                                           -> MODULE_REF_INTEGRITY
 11. 声明计数比对 (调用方 expected / manifest.counts)          -> MODULE_COUNT_MISMATCH
 12. 提交 (目录 move 到仓库根) + 索引重建 + prep 工件 + 导入日志 + 开局句柄

原子性: 一切写入先落 <staging>/imp_<uuid>/, 全部成功后才 os.replace 提交;
任何一步失败 -> finally 里 shutil.rmtree 暂存区, 仓库不留半成品。
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from app.repository import index as repo_index
from app.repository import paths as repo_paths
from app.repository import prep as repo_prep
from app.repository.errors import RepoError
from app.repository.paths import safe_join, validate_entry_id
from app.repository.pkg import extract_modpkg, is_zipfile, sha256_file
from app.repository.roots import RepoRoots
from app.repository.spec import (MAX_PACKAGE_BYTES, REPO_ENGINE_VERSION,
                                 SUPPORTED_MODULE_SCHEMA_VERSIONS,
                                 normalize_schema_version, version_lt)

MANIFEST_NAMES = ("module.yaml", "module.yml", "manifest.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- manifest IO

def read_manifest(root: Path) -> tuple[dict[str, Any], str]:
    """读模组 manifest; 找不到 -> MODULE_MANIFEST_MISSING (R13 坏包 1)。"""
    root = Path(root)
    for name in MANIFEST_NAMES:
        p = root / name
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RepoError("MODULE_MANIFEST_INVALID",
                                "manifest 解析失败(%s): %s" % (name, exc),
                                {"file": name}) from exc
            if not isinstance(data, dict):
                raise RepoError("MODULE_MANIFEST_INVALID",
                                "manifest 不是映射(%s)" % name, {"file": name})
            return data, name
    raise RepoError("MODULE_MANIFEST_MISSING",
                    "包内未找到 module.yaml/module.yml/manifest.json",
                    {"root": str(root), "looked_for": list(MANIFEST_NAMES)})


def _read_yaml_map(path: Path, code: str, msg: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RepoError(code, msg, {"path": str(path)}) from exc
    except Exception as exc:
        raise RepoError(code, "%s: %s" % (msg, exc), {"path": str(path)}) from exc
    if not isinstance(data, dict):
        raise RepoError(code, msg, {"path": str(path)})
    return data


def _read_json_map(path: Path, code: str, msg: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RepoError(code, msg, {"path": str(path)}) from exc
    except Exception as exc:
        raise RepoError(code, "%s: %s" % (msg, exc), {"path": str(path)}) from exc
    if not isinstance(data, dict):
        raise RepoError(code, msg, {"path": str(path)})
    return data


# ------------------------------------------------------------ package validate

def validate_package(root: Path, *, rulepacks_root: Path | None = None) -> dict[str, Any]:
    """R13 校验闸门: 返回规范化后的包内容; 任一不合规抛对应 RepoError。"""
    root = Path(root)
    if not root.is_dir():
        raise RepoError("MODULE_PACKAGE_NOT_FOUND", "包目录不存在: %s" % root, {"path": str(root)})

    # (3) manifest
    manifest, manifest_name = read_manifest(root)

    # (4) id
    raw_id = manifest.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise RepoError("MODULE_ID_MISSING", "module.yaml: id required",
                        {"manifest": manifest_name})
    module_id = validate_entry_id(raw_id.strip(), label="manifest.id")

    # (5) 版本兼容
    sv = normalize_schema_version(manifest.get("schema_version"))
    if sv not in SUPPORTED_MODULE_SCHEMA_VERSIONS:
        raise RepoError("MODULE_VERSION_INCOMPATIBLE",
                        "schema_version=%r 不受支持(支持 %s)" % (sv, list(SUPPORTED_MODULE_SCHEMA_VERSIONS)),
                        {"schema_version": sv, "supported": list(SUPPORTED_MODULE_SCHEMA_VERSIONS),
                         "engine_version": REPO_ENGINE_VERSION})
    min_engine = manifest.get("min_engine_version")
    if min_engine and version_lt(REPO_ENGINE_VERSION, str(min_engine)):
        raise RepoError("MODULE_VERSION_INCOMPATIBLE",
                        "min_engine_version=%s 高于当前引擎 %s" % (min_engine, REPO_ENGINE_VERSION),
                        {"min_engine_version": str(min_engine), "engine_version": REPO_ENGINE_VERSION})

    # (6) ruleset
    ruleset = manifest.get("ruleset")
    if not isinstance(ruleset, str) or not ruleset.strip():
        raise RepoError("MODULE_RULESET_MISSING", "module.yaml: ruleset required", {"manifest": manifest_name})
    ruleset = ruleset.strip()
    if rulepacks_root is not None:
        rp = Path(rulepacks_root) / ruleset
        if not rp.is_dir() or not any((rp / n).is_file() for n in ("rulepack.yaml", "rulepack.yml", "manifest.json")):
            raise RepoError("MODULE_RULESET_UNKNOWN",
                            "ruleset=%r 在规则仓库中不存在" % ruleset,
                            {"ruleset": ruleset, "rulepacks_root": str(rulepacks_root)})

    # (7) 引用文件
    files = manifest.get("files") or {}
    if not isinstance(files, dict):
        raise RepoError("MODULE_MANIFEST_INVALID", "manifest.files 必须是映射", {"manifest": manifest_name})
    graph_rel = str(files.get("event_graph") or "event_graph.yaml")
    missing: list[str] = []
    graph_path = safe_join(root, graph_rel, label="manifest.files.event_graph")
    if not graph_path.is_file():
        raise RepoError("MODULE_FILE_MISSING",
                        "事件图文件缺失: %s" % graph_rel,
                        {"module_id": module_id, "missing": [graph_rel]})
    npc_rels = [str(x) for x in (files.get("npcs") or [])]
    map_rels = [str(x) for x in (files.get("maps") or [])]
    clues_rel = str(files.get("clues") or "clues.yaml")
    for rel in npc_rels + map_rels + [clues_rel]:
        if not rel:
            continue
        try:
            ok = safe_join(root, rel, label="manifest.files").is_file()
        except RepoError:
            raise
        if not ok:
            missing.append(rel)
    if missing:
        raise RepoError("MODULE_FILE_MISSING",
                        "manifest 引用的文件在包内不存在: %s" % ", ".join(missing),
                        {"module_id": module_id, "missing": sorted(missing)})

    # (8) 事件图
    graph = _read_yaml_map(graph_path, "MODULE_GRAPH_MISSING", "事件图文件不是 YAML 映射")
    nodes_raw = graph.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise RepoError("MODULE_GRAPH_EMPTY", "event_graph: nodes[] required", {"path": str(graph_path)})
    node_ids: list[str] = []
    for n in nodes_raw:
        if not isinstance(n, dict) or not n.get("id"):
            raise RepoError("MODULE_GRAPH_EMPTY", "event_graph: 存在缺少 id 的节点",
                            {"path": str(graph_path)})
        node_ids.append(str(n["id"]))
    node_set = set(node_ids)
    edges = [e for e in (graph.get("edges") or []) if isinstance(e, dict)]
    dangling = [e for e in edges if e.get("from") not in node_set or e.get("to") not in node_set]
    if dangling:
        raise RepoError("MODULE_GRAPH_DANGLING_EDGE",
                        "事件图存在 %d 条悬挂边" % len(dangling),
                        {"module_id": module_id, "dangling_edges": dangling[:10],
                         "dangling_count": len(dangling), "node_count": len(node_ids)})

    # (9) initial_scene
    init = manifest.get("initial_scene")
    if not isinstance(init, str) or init not in node_set:
        raise RepoError("MODULE_INITIAL_SCENE_INVALID",
                        "initial_scene=%r 不在事件图 nodes 中" % (init,),
                        {"module_id": module_id, "initial_scene": init,
                         "node_ids": sorted(node_set)[:50]})

    # (10) 载入 clues / npcs / maps + 引用一致性
    clues_doc = _read_yaml_map(safe_join(root, clues_rel, label="manifest.files.clues"),
                               "MODULE_FILE_MISSING", "线索文件不是 YAML 映射")
    clue_list = [c for c in (clues_doc.get("clues") or []) if isinstance(c, dict)]
    clue_ids = {str(c.get("id")) for c in clue_list if c.get("id")}

    npcs: list[dict[str, Any]] = []
    npc_paths: dict[str, str] = {}
    npc_ids: set[str] = set()
    for rel in npc_rels:
        doc = _read_yaml_map(safe_join(root, rel, label="manifest.files.npcs"),
                             "MODULE_FILE_MISSING", "NPC 卡不是 YAML 映射")
        npcs.append(doc)
        if doc.get("id"):
            npc_ids.add(str(doc["id"]))
            npc_paths[str(doc["id"])] = rel

    maps: list[dict[str, Any]] = []
    map_ids: set[str] = set()
    for rel in map_rels:
        doc = _read_json_map(safe_join(root, rel, label="manifest.files.maps"),
                             "MODULE_FILE_MISSING", "地图资产不是 JSON 映射")
        maps.append(doc)
        if doc.get("id"):
            map_ids.add(str(doc["id"]))

    problems: dict[str, list[str]] = {}
    for n in nodes_raw:
        for ref in (n.get("clue_refs") or []):
            if str(ref) not in clue_ids:
                problems.setdefault("node_clue_refs_missing", []).append(str(ref))
        for ref in (n.get("npc_refs") or []):
            if str(ref) not in npc_ids:
                problems.setdefault("node_npc_refs_missing", []).append(str(ref))
        mref = n.get("map_ref")
        if mref and str(mref) not in map_ids:
            problems.setdefault("node_map_refs_missing", []).append(str(mref))
    for c in clue_list:
        loc = c.get("location")
        if loc and str(loc) not in node_set:
            problems.setdefault("clue_location_not_node", []).append(str(c.get("id")))
        pt = c.get("points_to")
        if pt and str(pt) not in node_set:
            problems.setdefault("clue_points_to_not_node", []).append(str(c.get("id")))
    if problems:
        raise RepoError("MODULE_REF_INTEGRITY",
                        "模组内部引用悬空: %s" % ", ".join("%s=%s" % (k, v) for k, v in sorted(problems.items())),
                        {"module_id": module_id, "problems": {k: sorted(set(v)) for k, v in problems.items()}})

    counts = {
        "areas": len(maps),
        "rooms": sum(len(m.get("rooms") or []) for m in maps),
        "scenes": sum(len(m.get("rooms") or []) for m in maps),
        "event_nodes": len(node_ids),
        "event_edges": len(edges),
        "npcs": len(npcs),
        "clues": len(clue_list),
    }
    return {"root": root, "manifest": manifest, "manifest_name": manifest_name,
            "module_id": module_id, "ruleset": ruleset,
            "graph": graph, "nodes": nodes_raw, "edges": edges,
            "clues": clue_list, "npcs": npcs, "npc_paths": npc_paths,
            "maps": maps, "counts": counts,
            "declared": manifest.get("counts") if isinstance(manifest.get("counts"), dict) else None}


# ------------------------------------------------------------------ materialize

def _download(url: str, dest: Path, *, max_bytes: int = MAX_PACKAGE_BYTES,
              timeout: float = 30.0) -> int:
    import urllib.error
    import urllib.request

    scheme = (urlparse(url).scheme or "").lower()
    if scheme not in ("http", "https"):
        raise RepoError("MODULE_DOWNLOAD_SCHEME_REJECTED",
                        "仅允许 http/https 下载, 收到 scheme=%r" % scheme, {"url": url})
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "trpg-repo/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise RepoError("MODULE_PACKAGE_CORRUPT",
                                    "下载体积超过上限 %d" % max_bytes, {"url": url})
                fh.write(chunk)
    except RepoError:
        raise
    except urllib.error.HTTPError as exc:
        raise RepoError("MODULE_DOWNLOAD_FAILED", "HTTP %s" % exc.code, {"url": url}) from exc
    except Exception as exc:
        raise RepoError("MODULE_DOWNLOAD_FAILED", "%s: %s" % (type(exc).__name__, exc),
                        {"url": url}) from exc
    return total


def _copy_dir(src: Path, dst: Path) -> None:
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(Path(src).rglob("*")):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _materialize(source: str, *, staging: Path, roots: RepoRoots,
                 path: str | None, module_id: str | None, url: str | None,
                 sha256: str | None) -> dict[str, Any]:
    """把各种来源的包统一落到 staging/src, 并做 sha256 校验。"""
    src_dir = Path(staging) / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    if source == "url":
        if not url:
            raise RepoError("MODULE_PACKAGE_NOT_FOUND", "source=url 必须提供 url")
        if not sha256:
            raise RepoError("MODULE_PACKAGE_SHA256_REQUIRED",
                            "从远程 URL 导入必须提供 sha256 供下载后校验", {"url": url})
        dl = Path(staging) / "download.bin"
        size = _download(url, dl)
        actual = sha256_file(dl)
        if actual.lower() != str(sha256).strip().lower():
            raise RepoError("MODULE_PACKAGE_SHA256_MISMATCH",
                            "下载后 sha256 不一致",
                            {"url": url, "expected": str(sha256).strip().lower(),
                             "actual": actual, "size": size})
        if not is_zipfile(dl):
            raise RepoError("MODULE_PACKAGE_CORRUPT", "下载内容不是 zip/modpkg", {"url": url})
        extract_modpkg(dl, src_dir)
        return {"src_dir": src_dir, "ref": url, "sha256": actual, "size": size,
                "transport": "url"}

    if source == "library":
        if not module_id:
            raise RepoError("MODULE_PACKAGE_NOT_FOUND", "source=library 必须提供 module_id")
        mid = validate_entry_id(module_id, label="module_id")
        entry = repo_index.find_entry(roots.modules, "modules", mid, include_deleted=False)
        if entry is None:
            raise RepoError("MODULE_PACKAGE_NOT_FOUND",
                            "模组库中不存在(或已软删): %s" % mid, {"module_id": mid})
        lib_dir = Path(roots.modules) / entry["dir"]
        pkg_dir = Path(roots.modules) / "_pkg"
        pkg_file = pkg_dir / (mid + ".modpkg")
        if pkg_file.is_file():
            extract_modpkg(pkg_file, src_dir)
            actual = sha256_file(pkg_file)
            ref = "%s/_pkg/%s.modpkg" % (roots.modules.as_posix(), mid)
            size = pkg_file.stat().st_size
        elif lib_dir.is_dir():
            _copy_dir(lib_dir, src_dir)
            actual, size, _n = repo_index.sha256_dir(lib_dir)
            ref = "%s/%s" % (roots.modules.as_posix(), entry["dir"])
        else:
            raise RepoError("MODULE_PACKAGE_NOT_FOUND",
                            "模组库条目没有对应实体: %s" % mid, {"module_id": mid})
        return {"src_dir": src_dir, "ref": ref, "sha256": actual, "size": size,
                "transport": "library", "library_sha256": entry["sha256"]}

    if source != "local":
        raise RepoError("REPO_WRITE_BODY_INVALID", "source 必须是 local|library|url", {"source": source})

    if not path:
        raise RepoError("MODULE_PACKAGE_NOT_FOUND", "source=local 必须提供 path")
    p = Path(path)
    if not p.is_absolute():
        # 相对路径一律相对「离线收件箱」解析, 走完整路径穿越/符号链接防护
        p = safe_join(roots.imports, path, label="import path")
    else:
        p = Path(os.path.abspath(str(p)))
        if repo_paths.is_symlinkish(p):
            raise RepoError("REPO_PATH_TRAVERSAL",
                            "本地包路径是符号链接/junction: %s" % p, {"path": str(p)})
    if not p.exists():
        raise RepoError("MODULE_PACKAGE_NOT_FOUND", "本地包不存在: %s" % p, {"path": str(p)})
    if p.is_dir():
        _copy_dir(p, src_dir)
        actual, size, _n = repo_index.sha256_dir(p)
        ref = str(p)
    elif p.is_file():
        if not is_zipfile(p):
            raise RepoError("MODULE_PACKAGE_CORRUPT",
                            "本地文件既不是目录也不是 zip/modpkg: %s" % p, {"path": str(p)})
        extract_modpkg(p, src_dir)
        actual = sha256_file(p)
        size = p.stat().st_size
        ref = str(p)
    else:
        raise RepoError("MODULE_PACKAGE_NOT_FOUND", "路径类型不支持: %s" % p, {"path": str(p)})

    if sha256 and actual.lower() != str(sha256).strip().lower():
        raise RepoError("MODULE_PACKAGE_SHA256_MISMATCH", "本地包 sha256 与声明不一致",
                        {"path": str(p), "expected": str(sha256).strip().lower(), "actual": actual})
    return {"src_dir": src_dir, "ref": ref, "sha256": actual, "size": size,
            "transport": "local"}


# ---------------------------------------------------------------------- commit

def _commit_dir(src: Path, target: Path, *, overwrite: bool) -> None:
    """把暂存目录原子提交到仓库根 (目录级 rename, 失败回滚)。"""
    src, target = Path(src), Path(target)
    if target.exists():
        if not overwrite:
            raise RepoError("REPO_ENTRY_EXISTS",
                            "仓库条目已存在: %s (需 overwrite=true)" % target.name,
                            {"entry": target.name})
        old = target.parent / (".old_%s_%s" % (target.name, uuid.uuid4().hex[:8]))
        os.replace(str(target), str(old))
        try:
            os.replace(str(src), str(target))
        except Exception:
            os.replace(str(old), str(target))
            raise
        shutil.rmtree(old, ignore_errors=True)
    else:
        os.replace(str(src), str(target))


def _write_prep(roots: RepoRoots, module_id: str, payload: dict[str, Any]) -> Path:
    out = Path(roots.prep) / ("%s.json" % module_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp-%d" % os.getpid())
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, out)
    return out


def _append_import_log(roots: RepoRoots, record: dict[str, Any]) -> None:
    p = Path(roots.log)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def open_session(module_id: str, ruleset: str, prepared: dict[str, Any],
                 *, session: dict[str, Any] | None = None,
                 prep_ref: str = "", persist_tables: bool = True) -> dict[str, Any]:
    """复用既有 TABLES 注册表 (不新建第二套机制) 产出开局句柄。"""
    from app.web import rest as rest_mod

    session = dict(session or {})
    stamp = "%d%s" % (int(time.time()), uuid.uuid4().hex[:6])
    campaign_id = str(session.get("campaign_id") or "c_%s_%s" % (module_id, stamp))
    table_id = str(session.get("table_id") or "t_%s_%s" % (module_id, stamp))
    if table_id in rest_mod.TABLES:
        raise RepoError("REPO_SESSION_EXISTS", "table_id 已存在: %s" % table_id, {"table_id": table_id})
    entry = {"table_id": table_id, "campaign_id": campaign_id, "ruleset": ruleset,
             "config": {"module_id": module_id,
                        "initial_scene": prepared["event_graph"]["initial_scene"],
                        "prep_ref": prep_ref,
                        "prepared_ready": bool(prepared.get("ready"))}}
    rest_mod.TABLES[table_id] = entry
    if persist_tables:
        try:
            from app.web import access as access_mod
            access_mod.persist_tables()
        except Exception:
            pass
    return {"table_id": table_id, "campaign_id": campaign_id, "ruleset": ruleset,
            "module_id": module_id,
            "initial_scene": prepared["event_graph"]["initial_scene"],
            "prepared_ready": bool(prepared.get("ready")),
            "prep_ref": prep_ref,
            "table_url": "/api/tables/%s" % table_id,
            "resume_url": "/api/campaigns/%s/resume" % campaign_id,
            "ws_url": "/ws?table=%s&viewer=kp&role=kp" % table_id,
            "player_url": "/player/?table=%s&campaign=%s" % (table_id, campaign_id)}


def import_module(*, source: str, roots: RepoRoots, path: str | None = None,
                  module_id: str | None = None, url: str | None = None,
                  sha256: str | None = None, expected: dict[str, Any] | None = None,
                  overwrite: bool = False, open_session_handle: bool = False,
                  session: dict[str, Any] | None = None) -> dict[str, Any]:
    """R1/R2 主入口: 取包 -> 校验 -> 落库 -> 准备 -> (可选)开局句柄。"""
    roots = roots.ensure()
    staging = Path(roots.staging) / ("imp_%s" % uuid.uuid4().hex)
    staging.mkdir(parents=True, exist_ok=True)
    target: Path | None = None
    committed = False
    try:
        got = _materialize(source, staging=staging, roots=roots, path=path,
                           module_id=module_id, url=url, sha256=sha256)
        src_dir: Path = got["src_dir"]

        checked = validate_package(src_dir, rulepacks_root=roots.rulepacks)
        mid = checked["module_id"]

        # (11) 计数比对
        counts = dict(checked["counts"])
        declared = checked["declared"]
        declared_verified = None
        if declared:
            declared_verified = all(int(declared.get(k, counts.get(k))) == counts.get(k)
                                    for k in declared if k in counts)
        if expected:
            bad = {k: {"expected": v, "actual": counts.get(k)} for k, v in expected.items()
                   if k in counts and int(v) != counts[k]}
            unknown = sorted(k for k in expected if k not in counts)
            if bad or unknown:
                raise RepoError("MODULE_COUNT_MISMATCH",
                                "实际计数与声明不一致: %s" % json.dumps(bad, ensure_ascii=False),
                                {"mismatch": bad, "unknown_keys": unknown, "actual": counts})

        # (12) 提交
        target = Path(roots.modules) / mid
        _commit_dir(src_dir, target, overwrite=overwrite)
        committed = True

        try:
            idx = repo_index.write_index(roots.modules, "modules")
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            committed = False
            repo_index.write_index(roots.modules, "modules")
            raise

        entry = repo_index.find_entry(roots.modules, "modules", mid, include_deleted=True) or {}
        prepared = repo_prep.prepare(target, manifest=checked["manifest"], graph=checked["graph"],
                                     clues=checked["clues"], npcs=checked["npcs"],
                                     maps=checked["maps"], module_sha256=entry.get("sha256", ""),
                                     npc_paths=checked["npc_paths"])
        prep_path = _write_prep(roots, mid, prepared)

        handle = None
        if open_session_handle:
            handle = open_session(mid, checked["ruleset"], prepared, session=session,
                                  prep_ref="%s/%s.json" % (roots.prep.as_posix(), mid),
                                  persist_tables=(Path(roots.modules) == RepoRoots.default().modules))

        record = {"ts": _now(), "module_id": mid, "source": source, "source_ref": got["ref"],
                  "sha256": got["sha256"], "size": got["size"],
                  "index_fingerprint": idx.get("fingerprint"),
                  "counts": counts, "session": handle}
        _append_import_log(roots, record)

        return {
            "ok": True,
            "imported": True,
            "source": source,
            "source_ref": got["ref"],
            "transport": got.get("transport"),
            "sha256": got["sha256"],
            "package_sha256": got["sha256"],
            "content_sha256": entry.get("sha256", ""),
            "size": got["size"],
            "module_id": mid,
            "name": str(checked["manifest"].get("name") or mid),
            "version": str(checked["manifest"].get("version") or ""),
            "ruleset": checked["ruleset"],
            "counts": counts,
            "declared": declared,
            "declared_verified": declared_verified,
            "expected_verified": bool(expected),
            "index": {"kind": "modules", "count": idx.get("count"),
                      "fingerprint": idx.get("fingerprint")},
            "prepared": prepared,
            "prep_ref": "%s/%s.json" % (roots.prep.as_posix(), mid),
            "session": handle,
        }
    except RepoError:
        raise
    except Exception as exc:
        raise RepoError("REPO_IMPORT_FAILED", "%s: %s" % (type(exc).__name__, exc),
                        {"module_id": module_id, "source": source}) from exc
    finally:
        if not committed and target is not None:
            shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
