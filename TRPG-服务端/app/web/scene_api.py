"""T1 (additive): 场景栏目 REST + 模组文字生成地图 API.

Provides:
  GET    /api/campaigns/{campaign}/scenes          场景列表 + current_scene
  GET    /api/campaigns/{campaign}/scenes/{sid}    场景详情 (map_refs)
  POST   /api/campaigns/{campaign}/scenes/advance  推进场景 (SCENE_UPDATED + MAP_UPDATED)
  POST   /api/campaigns/{campaign}/scenes          (KP) 手工建场景
  PUT    /api/campaigns/{campaign}/scenes/{sid}    (KP) 改 branches
  DELETE /api/campaigns/{campaign}/scenes/{sid}    (KP) 删场景
  GET    /api/modules/{module}/maps               地图列表 (map-index)
  GET    /api/modules/{module}/maps/{map_id}      单张 MapDefinition
  GET    /api/modules/{module}/scene-graph        event_graph (nodes/edges/initial_scene)
  POST   /api/modules/{module}/generate-map       模组文字 -> MapDefinition (rule 即时)

Scene definitions are derived from the module event_graph; runtime current
scene is projected from SCENE_UPDATED events (SessionState.current_scene).
All event writes go through the command bus (single-writer discipline).
Python 3.12 compatible.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.config import APP_ROOT
from app.web.access import _require_kp_end
from app.repository import index as repo_index
from app.repository.errors import RepoError
from app.repository.paths import safe_join, validate_entry_id
from app.repository.roots import RepoRoots

router = APIRouter()

MODULES_DIR = APP_ROOT / "modules"


def _module_dir(module_id: str) -> Path:
    eid = validate_entry_id(str(module_id or ""), label="module id")
    root = RepoRoots.default().modules
    entry = repo_index.find_entry(root, "modules", eid, include_deleted=True)
    if entry is None or entry.get("deleted"):
        raise HTTPException(status_code=404, detail="module not found: %s" % eid)
    d = safe_join(root, entry["dir"], label="module entry dir")
    if not d.is_dir():
        raise HTTPException(status_code=404, detail="module dir missing")
    return d


def _load_graph(module_dir: Path) -> dict[str, Any]:
    p = module_dir / "event_graph.yaml"
    if not p.is_file():
        return {"nodes": [], "edges": [], "initial_scene": ""}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _load_maps(module_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    maps_dir = module_dir / "maps"
    if not maps_dir.is_dir():
        return out
    for f in sorted(maps_dir.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out


def _scene_from_node(node: dict[str, Any], edges: list[dict[str, Any]],
                     initial_scene: str, module_id: str,
                     campaign: str) -> dict[str, Any]:
    """Node -> Scene (T1 §4.1). Branches derived from outgoing edges."""
    nid = str(node.get("id") or "")
    branches = []
    for e in edges:
        if str(e.get("from")) == nid:
            branches.append({
                "to_scene_id": str(e.get("to") or ""),
                "edge_id": str(e.get("id") or ""),
                "label": str(e.get("label") or e.get("id") or ""),
                "condition": "",
                "locked": False,
            })
    return {
        "scene_id": nid,
        "campaign_id": campaign,
        "module_id": module_id,
        "title": str(node.get("label") or nid),
        "summary": str(node.get("summary") or node.get("label") or ""),
        "map_refs": [str(node["map_ref"])] if node.get("map_ref") else [],
        "current_map": str(node.get("map_ref") or ""),
        "room_ref": str(node.get("room_ref") or ""),
        "clue_refs": list(node.get("clue_refs") or []),
        "npc_refs": list(node.get("npc_refs") or []),
        "branches": branches,
        "is_initial": nid == initial_scene,
    }


def _scenes_for(campaign: str, module_id: str) -> list[dict[str, Any]]:
    mdir = _module_dir(module_id)
    graph = _load_graph(mdir)
    nodes = [n for n in (graph.get("nodes") or []) if isinstance(n, dict)]
    edges = [e for e in (graph.get("edges") or []) if isinstance(e, dict)]
    init = str(graph.get("initial_scene") or "")
    return [_scene_from_node(n, edges, init, module_id, campaign)
            for n in nodes if n.get("id")]


def _resolve_module(campaign: str, module_id: str = "") -> str:
    """campaign -> module id (显式参数 > 桌配置 > 默认 dead_light)。"""
    mid = str(module_id or "").strip()
    if not mid:
        try:
            from app.web import access as access_mod
            from app.web import rest as rest_mod
            tid = access_mod._table_entry_by_campaign(campaign)
            cfg = (rest_mod.TABLES.get(tid) or {}).get("config") or {}
            mid = str(cfg.get("module") or cfg.get("module_id") or "dead_light").strip()
        except Exception:  # noqa: BLE001
            mid = "dead_light"
    return mid or "dead_light"


async def _current_scene(campaign: str) -> str:
    """Project SCENE_UPDATED events -> current scene id (async, read-only)."""
    try:
        from app.web import rest as rest_mod
        from app.domain.rollback import project_with_rollback
        store = rest_mod._store()
        await store.init()
        events = await store.replay(campaign)
        state = project_with_rollback(events, campaign)  # P1-4
        return str(getattr(state, "current_scene", "") or "")
    except Exception:  # noqa: BLE001
        return ""


# ---- scenes CRUD + advance ----

@router.get("/api/campaigns/{campaign}/scenes")
async def list_scenes(campaign: str, module_id: str = "",
                      authorization: str | None = Header(default=None),
                      token: str | None = Query(default=None)) -> dict[str, Any]:
    """场景列表 + 当前场景。module_id 缺省取桌配置/默认模组。T4: 任意启用端 token 可读。"""
    from app.web.access import _require_any_end
    _require_any_end(authorization=authorization, token=token)
    mid = _resolve_module(campaign, module_id)
    scenes = _scenes_for(campaign, mid)
    # P1b: merge persistent custom scenes (they win on id collision)
    try:
        from app.repository import campaign_folder as cf
        cf.ensure_campaign(campaign)
        customs = cf.read_custom_scenes(campaign)
        ids = {s["scene_id"] for s in scenes}
        for sid, c in customs.items():
            if sid in ids:
                scenes = [s for s in scenes if s["scene_id"] != sid]
            scenes.append(c)
    except Exception:  # noqa: BLE001 — persistence failure degrades to graph-only
        pass
    current = await _current_scene(campaign)
    return {
        "campaign": campaign,
        "module_id": mid,
        "current_scene": current,
        "scene_count": len(scenes),
        "scenes": scenes,
    }


@router.get("/api/campaigns/{campaign}/scenes/{scene_id}")
async def get_scene(campaign: str, scene_id: str,
                    module_id: str = "",
                    authorization: str | None = Header(default=None),
                    token: str | None = Query(default=None)) -> dict[str, Any]:
    """T4: 任意启用端 token 可读。P1b: 也查自定义场景。"""
    from app.web.access import _require_any_end
    _require_any_end(authorization=authorization, token=token)
    mid = _resolve_module(campaign, module_id)
    for s in _scenes_for(campaign, mid):
        if s["scene_id"] == scene_id:
            mdir = _module_dir(mid)
            s["maps"] = _load_maps(mdir)
            return s
    # P1b: custom scenes persisted in campaign folder
    try:
        from app.repository import campaign_folder as cf
        cf.ensure_campaign(campaign)
        custom = cf.read_custom_scenes(campaign)
        c = custom.get(scene_id)
        if c:
            return dict(c)
    except Exception:  # noqa: BLE001
        pass
    raise HTTPException(status_code=404, detail="scene not found: %s" % scene_id)


@router.post("/api/campaigns/{campaign}/scenes/advance", status_code=201)
async def advance_scene(campaign: str, body: dict[str, Any],
                        entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """推进场景: to_scene_id (必填), 可选 edge_id/reason。T4: 主持人专属 + 目标存在性校验。"""
    to_scene_id = str((body or {}).get("to_scene_id") or "").strip()
    if not to_scene_id:
        raise HTTPException(status_code=422, detail="to_scene_id required")
    from app.app_core.command_bus import CommandBus
    from app.web import access as access_mod
    from app.web import rest as rest_mod
    store = rest_mod._store()
    await store.init()
    module_id = _resolve_module(campaign, str((body or {}).get("module_id") or ""))
    # T4 (mandatory): validate target scene EXISTS before advancing, so a bad
    # to_scene_id can never pollute the event stream.
    found = None
    try:
        for s in _scenes_for(campaign, module_id):
            if s["scene_id"] == to_scene_id:
                found = s
                break
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - resolution failure is a 422, not a silent pass
        found = None
    if found is None:
        raise HTTPException(status_code=422,
                            detail="to_scene_id %r not found in module scenes" % to_scene_id)
    map_id = str(found.get("current_map") or "")
    room_ref = str(found.get("room_ref") or "")
    bus = CommandBus(store, campaign, guard=access_mod._guard_for(campaign))
    receipt = await bus.dispatch(
        "advance_scene",
        {"campaign_id": campaign, "to_scene_id": to_scene_id,
         "edge_id": (body or {}).get("edge_id"),
         "map_id": map_id or None, "room_ref": room_ref,
         "reason": (body or {}).get("reason", "")},
        actor=str((body or {}).get("actor") or "kp"),
        key=(body or {}).get("req_id") or None)
    return {"ok": True, "receipt": receipt,
            "scene_id": to_scene_id, "map_id": map_id, "room_ref": room_ref}


@router.post("/api/campaigns/{campaign}/scenes", status_code=201)
def create_scene(campaign: str, body: dict[str, Any],
                 entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """(主持人) 手工建自定义场景 —— P1b: 真持久化到 campaign folder。"""
    from app.repository import campaign_folder as cf
    scene_id = str((body or {}).get("scene_id") or "").strip()
    if not scene_id:
        raise HTTPException(status_code=422, detail="scene_id required")
    cf.ensure_campaign(campaign)
    custom = cf.read_custom_scenes(campaign)
    if scene_id in custom:
        raise HTTPException(status_code=409, detail="scene already exists: %s" % scene_id)
    scene = {
        "scene_id": scene_id,
        "campaign_id": campaign,
        "title": str((body or {}).get("title") or scene_id),
        "summary": str((body or {}).get("summary") or ""),
        "map_refs": list((body or {}).get("map_refs") or []),
        "current_map": str((body or {}).get("current_map") or ""),
        "room_ref": str((body or {}).get("room_ref") or ""),
        "branches": list((body or {}).get("branches") or []),
        "is_initial": bool((body or {}).get("is_initial", False)),
        "custom": True,
    }
    cf.write_custom_scene(campaign, scene)
    return {"ok": True, "scene_id": scene_id, "persisted": True, "scene": scene}


@router.put("/api/campaigns/{campaign}/scenes/{scene_id}")
def update_scene(campaign: str, scene_id: str, body: dict[str, Any],
                 entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """(主持人) 修改分支 label/condition —— P1b: 持久化到 campaign folder。"""
    from app.repository import campaign_folder as cf
    cf.ensure_campaign(campaign)
    custom = cf.read_custom_scenes(campaign)
    if scene_id not in custom:
        raise HTTPException(status_code=404, detail="scene not found: %s" % scene_id)
    cur = dict(custom[scene_id])
    for k in ("title", "summary", "map_refs", "current_map", "room_ref", "branches"):
        if k in (body or {}):
            cur[k] = (body or {}).get(k)
    cf.write_custom_scene(campaign, cur)
    return {"ok": True, "scene_id": scene_id, "updated": True, "scene": cur}


@router.delete("/api/campaigns/{campaign}/scenes/{scene_id}")
def delete_scene(campaign: str, scene_id: str,
                 entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """(主持人) 删除自定义场景 (graph 派生场景不可删)。P1b: 真删除。"""
    from app.repository import campaign_folder as cf
    cf.ensure_campaign(campaign)
    removed = cf.delete_custom_scene(campaign, scene_id)
    if not removed:
        raise HTTPException(status_code=404, detail="scene not found: %s" % scene_id)
    return {"ok": True, "scene_id": scene_id, "deleted": True}


# ---- module map / scene-graph / generate-map ----

@router.get("/api/modules/{module}/maps")
def module_maps(module: str,
                authorization: str | None = Header(default=None),
                token: str | None = Query(default=None)) -> dict[str, Any]:
    """T4: 任意启用端 token 可读。"""
    from app.web.access import _require_any_end
    _require_any_end(authorization=authorization, token=token)
    mdir = _module_dir(module)
    maps = _load_maps(mdir)
    out = [{"map_id": str(m.get("id") or ""), "title": str(m.get("name") or ""),
            "rooms": len(m.get("rooms") or [])} for m in maps]
    return {"ok": True, "module_id": module, "count": len(out), "maps": out}


@router.get("/api/modules/{module}/maps/{map_id}")
def module_map_detail(module: str, map_id: str,
                      authorization: str | None = Header(default=None),
                      token: str | None = Query(default=None)) -> dict[str, Any]:
    """T4: 任意启用端 token 可读。"""
    from app.web.access import _require_any_end
    _require_any_end(authorization=authorization, token=token)
    mdir = _module_dir(module)
    maps = _load_maps(mdir)
    for m in maps:
        if str(m.get("id") or "") == map_id:
            return {"ok": True, "module_id": module, "map": m}
    raise HTTPException(status_code=404, detail="map not found: %s" % map_id)


@router.get("/api/modules/{module}/scene-graph")
def module_scene_graph(module: str,
                       authorization: str | None = Header(default=None),
                       token: str | None = Query(default=None)) -> dict[str, Any]:
    """T4: 任意启用端 token 可读。"""
    from app.web.access import _require_any_end
    _require_any_end(authorization=authorization, token=token)
    mdir = _module_dir(module)
    graph = _load_graph(mdir)
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    return {"ok": True, "module_id": module,
            "initial_scene": str(graph.get("initial_scene") or ""),
            "node_count": len(nodes), "edge_count": len(edges),
            "nodes": nodes, "edges": edges}


GENERATE_MAP_MAX_TEXT = 200_000  # T4 suggestion: input cap (chars)


@router.post("/api/modules/{module}/generate-map", status_code=201)
def generate_map(module: str, body: dict[str, Any],
                 entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """模组文字 -> MapDefinition (rule 即时; 不落库, 返回 draft)。

    body: {"text": "...", "map_id": "m_gen", "title": "..."}
    硬门: 悬空边 / initial_scene 必须合法 (与 importer 同构)。
    T4: 主持人专属 + 输入上限。
    """
    text = str((body or {}).get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text required")
    if len(text) > GENERATE_MAP_MAX_TEXT:
        raise HTTPException(status_code=422,
                            detail="text too large (max %d chars)" % GENERATE_MAP_MAX_TEXT)
    from app.repository import mapgen as mapgen_mod
    map_id = str((body or {}).get("map_id") or ("m_%s" % module))
    title = str((body or {}).get("title") or "生成地图")
    try:
        result = mapgen_mod.parse_module_text(
            text, module_id=module, map_id=map_id, map_title=title)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="mapgen: %s" % exc) from exc
    node_ids = {str(n["id"]) for n in (result["event_graph"]["nodes"] or [])}
    edges = result["event_graph"]["edges"] or []
    dangling = [e for e in edges
                if str(e.get("from")) not in node_ids or str(e.get("to")) not in node_ids]
    init = str(result["event_graph"].get("initial_scene") or "")
    if dangling:
        raise HTTPException(status_code=422,
                            detail="mapgen: %d dangling edges" % len(dangling))
    if init not in node_ids:
        raise HTTPException(status_code=422,
                            detail="mapgen: initial_scene %r not a node" % init)
    return {"ok": True, "status": "draft", "result": result}
