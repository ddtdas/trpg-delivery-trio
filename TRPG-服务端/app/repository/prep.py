"""导入后「地图/事件准备」编排 (R3) —— additive。

导入成功后立即产出 prep 工件:
  * 地图: 房间/区域矩形 + **家具锚点** (显式 furniture 优先, 否则按房间面积确定性自动布点) + 门;
  * 事件图: 节点/边/邻接表/终局节点/拓扑序, **悬挂边必须为 0**;
  * NPC 卡: id/name/role/lines/traits;
  * 线索: id/kind/location/points_to/scope;
  * checks: 逐项布尔判据, 全 True 才 ready=True。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ANCHOR_KINDS = ("furniture", "container", "fixture")
ANCHOR_MIN, ANCHOR_MAX = 2, 6
ANCHOR_AREA_STEP = 20000.0  # 每 20000 px^2 增加一个锚点


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def anchors_for_room(room: dict[str, Any]) -> list[dict[str, Any]]:
    """确定性家具锚点: 同输入必得同输出 (不依赖随机/时间)。"""
    rid = str(room.get("id") or "room")
    declared = room.get("furniture") or room.get("anchors") or room.get("props")
    if isinstance(declared, list) and declared:
        out: list[dict[str, Any]] = []
        for i, item in enumerate(declared):
            if isinstance(item, dict):
                out.append({"id": str(item.get("id") or "anchor_%s_%d" % (rid, i + 1)),
                            "kind": str(item.get("kind") or "furniture"),
                            "room": rid,
                            "name": item.get("name"),
                            "x": item.get("x"), "y": item.get("y"),
                            "source": "declared"})
            else:
                out.append({"id": "anchor_%s_%d" % (rid, i + 1), "kind": "furniture",
                            "room": rid, "name": str(item), "x": None, "y": None,
                            "source": "declared"})
        return out

    try:
        x, y = float(room.get("x", 0) or 0), float(room.get("y", 0) or 0)
        w, h = float(room.get("w", 0) or 0), float(room.get("h", 0) or 0)
    except (TypeError, ValueError):
        x = y = w = h = 0.0
    count = ANCHOR_MIN + int(max(0.0, w * h) // ANCHOR_AREA_STEP)
    count = max(ANCHOR_MIN, min(ANCHOR_MAX, count))
    out = []
    for i in range(count):
        frac = (i + 1) / (count + 1)
        out.append({"id": "anchor_%s_%d" % (rid, i + 1),
                    "kind": ANCHOR_KINDS[i % len(ANCHOR_KINDS)],
                    "room": rid,
                    "name": None,
                    "x": round(x + w * frac, 2),
                    "y": round(y + h * 0.5, 2),
                    "source": "auto"})
    return out


def _topology(node_ids: list[str], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Kahn 拓扑排序 (确定性); 有环时报告环内节点, 不抛异常。"""
    indeg = {n: 0 for n in node_ids}
    adj: dict[str, list[str]] = {n: [] for n in node_ids}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in indeg and b in indeg:
            adj[a].append(b)
            indeg[b] += 1
    for k in adj:
        adj[k] = sorted(set(adj[k]))
    ready = sorted([n for n, d in indeg.items() if d == 0])
    order: list[str] = []
    deg = dict(indeg)
    while ready:
        cur = ready.pop(0)
        order.append(cur)
        for nxt in adj[cur]:
            deg[nxt] -= 1
            if deg[nxt] == 0:
                ready.append(nxt)
                ready.sort()
    cyclic = sorted(set(node_ids) - set(order))
    terminals = sorted([n for n in node_ids if not adj[n]])
    return {"acyclic": not cyclic, "topological_order": order,
            "cycle_nodes": cyclic, "adjacency": adj,
            "terminal_nodes": terminals, "indegree": indeg}


def prepare(module_dir: Path, *, manifest: dict[str, Any], graph: dict[str, Any],
            clues: list[dict[str, Any]], npcs: list[dict[str, Any]],
            maps: list[dict[str, Any]], module_sha256: str = "",
            npc_paths: dict[str, str] | None = None) -> dict[str, Any]:
    """产出 ModulePrep v1 工件 (纯函数, 确定)。"""
    node_list = [n for n in (graph.get("nodes") or []) if isinstance(n, dict)]
    node_ids = sorted(str(n["id"]) for n in node_list if n.get("id"))
    node_set = set(node_ids)
    edges = [e for e in (graph.get("edges") or []) if isinstance(e, dict)]
    dangling = [e for e in edges if e.get("from") not in node_set or e.get("to") not in node_set]

    maps_out: list[dict[str, Any]] = []
    anchors_total = 0
    rooms_total = 0
    for m in maps:
        rooms_out = []
        for room in (m.get("rooms") or []):
            if not isinstance(room, dict):
                continue
            anchors = anchors_for_room(room)
            anchors_total += len(anchors)
            rooms_total += 1
            rooms_out.append({
                "id": str(room.get("id") or ""),
                "name": str(room.get("name") or ""),
                "rect": {"x": room.get("x"), "y": room.get("y"),
                         "w": room.get("w"), "h": room.get("h")},
                "anchors": anchors,
            })
        maps_out.append({
            "id": str(m.get("id") or ""),
            "name": str(m.get("name") or ""),
            "rooms": rooms_out,
            "doors": [d for d in (m.get("doors") or []) if isinstance(d, dict)],
            "tokens_start": [t for t in (m.get("tokens_start") or []) if isinstance(t, dict)],
            "anchors_total": sum(len(r["anchors"]) for r in rooms_out),
        })

    npc_paths = npc_paths or {}
    npcs_out = [{"id": str(n.get("id") or ""),
                 "name": str(n.get("name") or ""),
                 "role": str(n.get("role") or ""),
                 "lines": len(n.get("lines") or []),
                 "traits": n.get("traits") or {},
                 "visibility": str(n.get("visibility") or ""),
                 "card_path": npc_paths.get(str(n.get("id") or ""), "")}
                for n in npcs if isinstance(n, dict)]

    clues_out = [{"id": str(c.get("id") or ""),
                  "kind": str(c.get("kind") or ""),
                  "location": str(c.get("location") or ""),
                  "points_to": str(c.get("points_to") or ""),
                  "scope": str(c.get("scope") or "")}
                 for c in clues if isinstance(c, dict)]

    topo = _topology(node_ids, edges)
    checks = {
        "dangling_edges": len(dangling),
        "dangling_edges_zero": len(dangling) == 0,
        "initial_scene_valid": bool(manifest.get("initial_scene")) and manifest["initial_scene"] in node_set,
        "all_rooms_have_anchors": all(r["anchors"] for m in maps_out for r in m["rooms"]),
        "npcs_present": len(npcs_out) > 0,
        "clues_present": len(clues_out) > 0,
        "maps_present": len(maps_out) > 0,
        "graph_connected_from_start": None,
    }
    start = manifest.get("initial_scene")
    if start in node_set:
        seen = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in topo["adjacency"].get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        checks["graph_connected_from_start"] = sorted(seen) == node_ids
        checks["reachable_nodes"] = sorted(seen)
    checks["ready"] = all(bool(checks[k]) for k in (
        "dangling_edges_zero", "initial_scene_valid", "all_rooms_have_anchors",
        "npcs_present", "clues_present", "maps_present", "graph_connected_from_start"))

    return {
        "schema": "ModulePrep v1",
        "module_id": str(manifest.get("id") or ""),
        "module_sha256": module_sha256,
        "name": str(manifest.get("name") or ""),
        "version": str(manifest.get("version") or ""),
        "ruleset": str(manifest.get("ruleset") or ""),
        "prepared_at": _now(),
        "ready": bool(checks["ready"]),
        "counts": {
            "areas": len(maps_out),
            "rooms": rooms_total,
            "scenes": rooms_total,
            "anchors": anchors_total,
            "event_nodes": len(node_ids),
            "event_edges": len(edges),
            "npcs": len(npcs_out),
            "clues": len(clues_out),
        },
        "maps": maps_out,
        "event_graph": {
            "initial_scene": start,
            "node_ids": node_ids,
            "node_count": len(node_ids),
            "edge_count": len(edges),
            "dangling_edges": dangling,
            "acyclic": topo["acyclic"],
            "cycle_nodes": topo["cycle_nodes"],
            "topological_order": topo["topological_order"],
            "terminal_nodes": topo["terminal_nodes"],
            "adjacency": topo["adjacency"],
            "indegree": topo["indegree"],
        },
        "npcs": npcs_out,
        "clues": clues_out,
        "checks": checks,
    }
