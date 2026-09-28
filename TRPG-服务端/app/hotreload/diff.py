"""两份编译产物的**确定性**差异 -> 既有域事件类型的变更规格 —— additive (R27)。

铁律: 只使用 app.domain.events.EVENT_TYPES 中**已存在**的类型, 不新增事件类型,
不新增 WS 帧。变更最终由 EventStore.append 落库, 交给既有单一收口广播。

映射 (既有类型 -> 用途):
  MAP_UPDATED          房间/锚点/可交互物的增删改 (op 取既有 MAP_OPS 之一)
  EVENT_INJECTED       事件图节点/边新增
  CLUE_GRANTED         线索新增
  TABLE_CONFIG_UPDATED NPC / 元信息变更 (通用配置差异)
  SNAPSHOT_LOADED      回滚到旧状态
  SNAPSHOT_SAVED       状态落盘
"""
from __future__ import annotations

from typing import Any

from app.hotreload.spec import MAX_CHANGES_PER_APPLY

#: 既有 MAP_OPS (app/web/rest.py) —— 不得自造 op
MAP_OP_ADD = "add_token"
MAP_OP_MOVE = "move"
MAP_OP_STATUS = "set_status"


def _inter_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in state.get("maps") or []:
        for it in m.get("interactables") or []:
            d = dict(it)
            d["_map"] = m.get("id")
            out[d["id"]] = d
    return out


def _room_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in state.get("maps") or []:
        for r in m.get("rooms") or []:
            out[r["id"]] = r
    return out


def diff_states(old: dict[str, Any] | None, new: dict[str, Any]) -> list[dict[str, Any]]:
    """确定性差异 -> 变更规格列表 (有序: 房间 -> 可交互物 -> 图 -> 线索 -> NPC)。

    old 为 None 表示首次导入: 视为「从空到全量」, 仍只产出既有类型的事件。
    两份**规范化后相同**的产物 -> 返回 [] (这就是「二次导入 diff 为空」的判据)。
    """
    old = old or {}
    changes: list[dict[str, Any]] = []

    old_rooms, new_rooms = _room_index(old), _room_index(new)
    for rid in sorted(new_rooms):
        nr = new_rooms[rid]
        orr = old_rooms.get(rid)
        if orr is None:
            changes.append({"type": "MAP_UPDATED", "map_id": nr.get("_map", ""),
                            "op": MAP_OP_STATUS, "target": rid,
                            "delta": {"kind": "room", "change": "added",
                                      "name": nr.get("name"), "rect": nr.get("rect")}})
        elif orr.get("rect") != nr.get("rect") or orr.get("name") != nr.get("name"):
            changes.append({"type": "MAP_UPDATED", "map_id": nr.get("_map", ""),
                            "op": MAP_OP_MOVE, "target": rid,
                            "delta": {"kind": "room", "change": "updated",
                                      "from": {"name": orr.get("name"), "rect": orr.get("rect")},
                                      "to": {"name": nr.get("name"), "rect": nr.get("rect")}}})
    for rid in sorted(set(old_rooms) - set(new_rooms)):
        changes.append({"type": "MAP_UPDATED", "map_id": old_rooms[rid].get("_map", ""),
                        "op": MAP_OP_STATUS, "target": rid,
                        "delta": {"kind": "room", "change": "removed"}})

    old_it, new_it = _inter_index(old), _inter_index(new)
    for iid in sorted(new_it):
        ni = new_it[iid]
        oi = old_it.get(iid)
        if oi is None:
            changes.append({"type": "MAP_UPDATED", "map_id": ni.get("_map", ""),
                            "op": MAP_OP_ADD, "target": iid,
                            "delta": {"kind": "interactable", "change": "added",
                                      "room": ni.get("room"), "anchor": ni.get("anchor"),
                                      "x": ni.get("x"), "y": ni.get("y"),
                                      "actions": list(ni.get("actions") or [])}})
        else:
            moved = (float(oi.get("x", 0)) != float(ni.get("x", 0))
                     or float(oi.get("y", 0)) != float(ni.get("y", 0)))
            if moved:
                changes.append({"type": "MAP_UPDATED", "map_id": ni.get("_map", ""),
                                "op": MAP_OP_MOVE, "target": iid,
                                "delta": {"kind": "interactable", "change": "moved",
                                          "from": {"x": oi.get("x"), "y": oi.get("y")},
                                          "to": {"x": ni.get("x"), "y": ni.get("y")},
                                          "room": ni.get("room"), "anchor": ni.get("anchor")}})
            if sorted(oi.get("actions") or []) != sorted(ni.get("actions") or []):
                changes.append({"type": "MAP_UPDATED", "map_id": ni.get("_map", ""),
                                "op": MAP_OP_STATUS, "target": iid,
                                "delta": {"kind": "interactable", "change": "actions",
                                          "from": sorted(oi.get("actions") or []),
                                          "to": sorted(ni.get("actions") or [])}})
            if (oi.get("room") != ni.get("room") or oi.get("anchor") != ni.get("anchor")
                    or oi.get("name") != ni.get("name")):
                changes.append({"type": "MAP_UPDATED", "map_id": ni.get("_map", ""),
                                "op": MAP_OP_STATUS, "target": iid,
                                "delta": {"kind": "interactable", "change": "retargeted",
                                          "room": ni.get("room"), "anchor": ni.get("anchor"),
                                          "name": ni.get("name")}})
    for iid in sorted(set(old_it) - set(new_it)):
        changes.append({"type": "MAP_UPDATED", "map_id": old_it[iid].get("_map", ""),
                        "op": MAP_OP_STATUS, "target": iid,
                        "delta": {"kind": "interactable", "change": "removed"}})

    og = (old.get("event_graph") or {})
    ng = (new.get("event_graph") or {})
    onodes = {n["id"]: n for n in (og.get("nodes") or [])}
    for n in sorted((ng.get("nodes") or []), key=lambda n: n["id"]):
        if n["id"] not in onodes:
            changes.append({"type": "EVENT_INJECTED", "node_id": n["id"],
                            "payload": {"label": n.get("label"), "source": "hot_reload"},
                            "dry_run_result": {"ok": True}})
    oedges = {(e["from"], e["to"], e["id"]) for e in (og.get("edges") or [])}
    for e in sorted((ng.get("edges") or []), key=lambda e: (e["from"], e["to"], e["id"])):
        if (e["from"], e["to"], e["id"]) not in oedges:
            changes.append({"type": "EVENT_INJECTED", "node_id": e["from"],
                            "payload": {"edge": {"from": e["from"], "to": e["to"],
                                                 "id": e["id"]},
                                        "source": "hot_reload"},
                            "dry_run_result": {"ok": True}})

    oclues = {c["id"]: c for c in (old.get("clues") or [])}
    for c in sorted((new.get("clues") or []), key=lambda c: c["id"]):
        if c["id"] not in oclues:
            changes.append({"type": "CLUE_GRANTED", "clue_id": c["id"],
                            "ref": "compiled/clues/%s" % c["id"], "condition_met": True})
    onpcs = {n["id"]: n for n in (old.get("npcs") or [])}
    for n in sorted((new.get("npcs") or []), key=lambda n: n["id"]):
        if n["id"] not in onpcs:
            changes.append({"type": "TABLE_CONFIG_UPDATED",
                            "diff": {"npc_added": n["id"], "name": n.get("name")}})
        elif onpcs[n["id"]].get("name") != n.get("name"):
            changes.append({"type": "TABLE_CONFIG_UPDATED",
                            "diff": {"npc_renamed": n["id"],
                                     "from": onpcs[n["id"]].get("name"),
                                     "to": n.get("name")}})

    return changes[:MAX_CHANGES_PER_APPLY]


def changes_digest(changes: list[dict[str, Any]]) -> str:
    """变更列表的确定性摘要 (用于「二次导入 diff 为空」的机器判据)。"""
    import hashlib
    import json
    canon = json.dumps(changes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
