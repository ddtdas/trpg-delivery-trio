"""编译产物 (自建等价结构) 的读取 / 校验 / 确定性摘要 —— additive (R26/R27)。

R26 的「原版本体文档」按 captain 裁决 D-05 只放**公开可溯源元数据 + 摘要 + 出处**
(不复制受版权保护的模组正文); 「导入后保存文件」与「自建等价结构」都落在 compiled/。

本模块只做纯函数式处理: 读 -> 校验 -> 规范化 -> 摘要。不做任何 IO 副作用。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.hotreload.spec import (ALLOWED_ACTIONS, COMPILED_SCHEMA, CompiledError)


def _require(cond: bool, code: str, msg: str, detail: dict[str, Any] | None = None) -> None:
    if not cond:
        raise CompiledError(code, msg, detail)


def _rect_contains(rect: dict[str, Any], x: float, y: float) -> bool:
    return (float(rect.get("x", 0)) <= x <= float(rect.get("x", 0)) + float(rect.get("w", 0))
            and float(rect.get("y", 0)) <= y <= float(rect.get("y", 0)) + float(rect.get("h", 0)))


def load_compiled(path: str | Path) -> dict[str, Any]:
    """读一个编译产物 JSON 文件。文件缺失/JSON 非法 -> CompiledError。"""
    p = Path(path)
    if not p.is_file():
        raise CompiledError("COMPILED_FILE_MISSING", "编译产物文件不存在: %s" % p, {"path": str(p)})
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CompiledError("COMPILED_INVALID_JSON", "编译产物不是合法 JSON: %s" % exc,
                            {"path": str(p)}) from exc
    _require(isinstance(data, dict), "COMPILED_INVALID_JSON", "编译产物根必须是对象")
    return data


def validate_compiled(data: dict[str, Any]) -> dict[str, Any]:
    """结构校验 + **可交互物契约**校验。返回规范化摘要 (不含时间戳, 完全确定)。

    可交互物契约 (captain 硬要求): 每个可交互物必须给出 {房间, 锚点, 动作集},
    且其坐标必须落在所属房间矩形边界内。
    """
    _require(isinstance(data, dict), "COMPILED_INVALID_JSON", "编译产物根必须是对象")
    _require(bool(str(data.get("module_id") or "")), "COMPILED_MODULE_ID_MISSING",
             "编译产物缺少 module_id")
    maps = data.get("maps")
    _require(isinstance(maps, list) and maps, "COMPILED_MAPS_MISSING",
             "编译产物缺少 maps (至少一张地图)")

    n_rooms = n_inter = 0
    seen_inter_ids: set[str] = set()
    for mi, m in enumerate(maps):
        _require(isinstance(m, dict), "COMPILED_MAP_INVALID", "maps[%d] 不是对象" % mi)
        mid = str(m.get("id") or "")
        _require(bool(mid), "COMPILED_MAP_INVALID", "maps[%d] 缺少 id" % mi)
        rooms = m.get("rooms")
        _require(isinstance(rooms, list) and rooms, "COMPILED_ROOMS_MISSING",
                 "地图 %s 缺少 rooms" % mid, {"map_id": mid})
        by_id: dict[str, dict[str, Any]] = {}
        for ri, room in enumerate(rooms):
            _require(isinstance(room, dict), "COMPILED_ROOM_INVALID",
                     "地图 %s rooms[%d] 不是对象" % (mid, ri))
            rid = str(room.get("id") or "")
            _require(bool(rid), "COMPILED_ROOM_INVALID", "地图 %s rooms[%d] 缺少 id" % (mid, ri))
            rect = room.get("rect")
            _require(isinstance(rect, dict), "COMPILED_ROOM_INVALID",
                     "房间 %s 缺少 rect" % rid, {"room": rid})
            for k in ("x", "y", "w", "h"):
                _require(isinstance(rect.get(k), (int, float)), "COMPILED_ROOM_INVALID",
                         "房间 %s 的 rect.%s 必须是数字" % (rid, k), {"room": rid, "key": k})
            by_id[rid] = room
            n_rooms += 1

        for ii, it in enumerate(m.get("interactables") or []):
            _require(isinstance(it, dict), "COMPILED_INTERACTABLE_INVALID",
                     "地图 %s interactables[%d] 不是对象" % (mid, ii))
            iid = str(it.get("id") or "")
            _require(bool(iid), "COMPILED_INTERACTABLE_INVALID",
                     "地图 %s interactables[%d] 缺少 id" % (mid, ii))
            _require(iid not in seen_inter_ids, "COMPILED_INTERACTABLE_DUPLICATE",
                     "可交互物 id 重复: %s" % iid, {"id": iid})
            seen_inter_ids.add(iid)
            rid = str(it.get("room") or "")
            _require(rid in by_id, "COMPILED_INTERACTABLE_ROOM_UNKNOWN",
                     "可交互物 %s 的房间不存在: %r" % (iid, rid), {"id": iid, "room": rid})
            anchor = str(it.get("anchor") or "")
            _require(bool(anchor), "COMPILED_INTERACTABLE_ANCHOR_MISSING",
                     "可交互物 %s 缺少锚点" % iid, {"id": iid})
            actions = it.get("actions")
            _require(isinstance(actions, list) and actions, "COMPILED_INTERACTABLE_ACTIONS_MISSING",
                     "可交互物 %s 缺少动作集" % iid, {"id": iid})
            bad = [a for a in actions if a not in ALLOWED_ACTIONS]
            _require(not bad, "COMPILED_INTERACTABLE_ACTION_UNKNOWN",
                     "可交互物 %s 含未声明动作: %s" % (iid, bad), {"id": iid, "bad": bad})
            x, y = it.get("x"), it.get("y")
            _require(isinstance(x, (int, float)) and isinstance(y, (int, float)),
                     "COMPILED_INTERACTABLE_POS_MISSING",
                     "可交互物 %s 缺少坐标" % iid, {"id": iid})
            rect = by_id[rid]["rect"]
            _require(_rect_contains(rect, float(x), float(y)),
                     "COMPILED_INTERACTABLE_OUT_OF_ROOM",
                     "可交互物 %s 位置 (%s,%s) 落在房间 %s 边界之外" % (iid, x, y, rid),
                     {"id": iid, "room": rid, "x": x, "y": y, "rect": rect})
            n_inter += 1

    graph = data.get("event_graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    _require(isinstance(nodes, list) and nodes, "COMPILED_GRAPH_MISSING",
             "编译产物缺少 event_graph.nodes")
    node_ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
    dangling = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        if str(e.get("from") or "") not in node_ids or str(e.get("to") or "") not in node_ids:
            dangling.append({"from": e.get("from"), "to": e.get("to")})
    _require(not dangling, "COMPILED_GRAPH_DANGLING_EDGE",
             "事件图存在 %d 条悬挂边" % len(dangling), {"dangling": dangling})
    initial = str(graph.get("initial_scene") or "")
    _require(initial in node_ids, "COMPILED_GRAPH_INITIAL_INVALID",
             "initial_scene=%r 不在节点集内" % initial, {"initial_scene": initial})

    npcs = data.get("npcs") or []
    clues = data.get("clues") or []
    _require(isinstance(npcs, list) and npcs, "COMPILED_NPCS_MISSING", "编译产物缺少 npcs")
    _require(isinstance(clues, list) and clues, "COMPILED_CLUES_MISSING", "编译产物缺少 clues")

    return {
        "schema": COMPILED_SCHEMA,
        "module_id": str(data["module_id"]),
        "counts": {"maps": len(maps), "rooms": n_rooms, "interactables": n_inter,
                   "event_nodes": len(nodes), "event_edges": len(edges),
                   "npcs": len(npcs), "clues": len(clues)},
        "valid": True,
    }


def canonical_digest(data: dict[str, Any]) -> str:
    """编译产物的**确定性**摘要 (键排序 + 紧凑分隔符, 不含时间戳)。"""
    canon = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    """规范化: 只保留参与差异比较的键, 顺序稳定 (保证「二次导入 diff 为空」)。"""
    maps = []
    for m in data.get("maps") or []:
        maps.append({
            "id": str(m.get("id") or ""),
            "rooms": sorted(({"id": str(r.get("id") or ""),
                              "name": str(r.get("name") or ""),
                              "rect": {k: float((r.get("rect") or {}).get(k, 0))
                                       for k in ("x", "y", "w", "h")}}
                             for r in (m.get("rooms") or [])), key=lambda r: r["id"]),
            "interactables": sorted(({"id": str(i.get("id") or ""),
                                      "name": str(i.get("name") or ""),
                                      "room": str(i.get("room") or ""),
                                      "anchor": str(i.get("anchor") or ""),
                                      "x": float(i.get("x", 0)), "y": float(i.get("y", 0)),
                                      "actions": sorted(str(a) for a in (i.get("actions") or []))}
                                     for i in (m.get("interactables") or [])),
                                    key=lambda i: i["id"]),
        })
    graph = data.get("event_graph") or {}
    return {
        "module_id": str(data.get("module_id") or ""),
        "maps": sorted(maps, key=lambda m: m["id"]),
        "event_graph": {
            "initial_scene": str(graph.get("initial_scene") or ""),
            "nodes": sorted(({"id": str(n.get("id") or ""),
                              "label": str(n.get("label") or "")}
                             for n in (graph.get("nodes") or [])), key=lambda n: n["id"]),
            "edges": sorted(({"from": str(e.get("from") or ""), "to": str(e.get("to") or ""),
                              "id": str(e.get("id") or "%s->%s" % (e.get("from"), e.get("to")))}
                             for e in (graph.get("edges") or [])),
                            key=lambda e: (e["from"], e["to"], e["id"])),
        },
        "npcs": sorted(({"id": str(n.get("id") or ""), "name": str(n.get("name") or "")}
                        for n in (data.get("npcs") or [])), key=lambda n: n["id"]),
        "clues": sorted(({"id": str(c.get("id") or ""), "kind": str(c.get("kind") or "")}
                         for c in (data.get("clues") or [])), key=lambda c: c["id"]),
    }
