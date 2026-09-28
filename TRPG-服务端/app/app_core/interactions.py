"""T7 (additive): 地点交互动作集 (R10/R11) —— 领域层。

铁律 (D4):
  * **不新增事件类型**: 交互结果走既有 EVENT_INJECTED / INFO_REVEALED;
  * **不动 MAP_OPS / events.MapOp**（冻结字面量）: 「搜索/撬锁/查看/取走」是
    **对象动作集**（per-object actions），不是地图 op —— 因此既不扩展
    MAP_OPS，也不需要新增事件类型来承载它;
  * 纯函数 + 只读磁盘: 本模块不写库、不发事件；写路径由 command_bus 唯一收口。

顺带覆盖 R14（可交互物品模糊化 + 自动分配位置）:
  模组未显式声明家具时，按房间名称做**语义抽取**（柜/抽屉/桌/架/保险箱/门…），
  并把家具**自动分配**到房间矩形内的确定性锚点。
Python 3.12 compatible.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from app.config import APP_ROOT
from app.rules import checks

__all__ = [
    "InteractionError",
    "ACTIONS",
    "ACTION_LABELS",
    "SENSITIVE_ACTIONS",
    "KIND_ACTIONS",
    "guess_kind",
    "actions_for",
    "is_sensitive",
    "load_rooms",
    "resolve_module_dir",
    "objects_for_room",
    "load_interactives",
    "find_object",
    "resolve_action",
    "seed_for",
]


class InteractionError(ValueError):
    """非法交互请求（未知动作 / 未知对象 / 参数缺失）。"""


ACTIONS: tuple[str, ...] = ("look", "search", "pick_lock", "take")
ACTION_LABELS: dict[str, str] = {
    "look": "查看",
    "search": "搜索",
    "pick_lock": "撬锁",
    "take": "取走",
}

# R11: 敏感动作 -> 必须先进主持人待审队列，批准后才下发。
SENSITIVE_ACTIONS: frozenset[str] = frozenset({"pick_lock", "take"})

# 家具类型 -> 默认动作集（可被模组声明覆盖）
KIND_ACTIONS: dict[str, tuple[str, ...]] = {
    "cabinet": ("look", "search", "pick_lock"),
    "drawer": ("look", "search", "pick_lock"),
    "desk": ("look", "search", "take"),
    "shelf": ("look", "search"),
    "safe": ("look", "pick_lock"),
    "door": ("look", "pick_lock"),
    "bed": ("look", "search"),
    "generic": ("look", "search"),
}

# 房间名/家具名 -> 家具类型（R14 语义抽取，顺序敏感：先长后短）
_KIND_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("safe", ("保险", "金库", "铁闸")),
    ("drawer", ("抽屉", "屉")),
    ("shelf", ("书架", "货架", "架")),
    ("cabinet", ("柜", "箱", "橱", "匣")),
    ("desk", ("书桌", "桌", "台", "案")),
    ("door", ("门", "闸")),
    ("bed", ("床",)),
)

_KIND_LABELS: dict[str, str] = {
    "cabinet": "柜子",
    "drawer": "抽屉",
    "desk": "书桌",
    "shelf": "书架",
    "safe": "保险箱",
    "door": "门",
    "bed": "床",
    "generic": "杂物堆",
}


def guess_kind(name: str) -> str:
    """家具名/房间名 -> 家具类型（关键词语义抽取，未知 -> generic）。"""
    text = str(name or "")
    for kind, keys in _KIND_KEYWORDS:
        for key in keys:
            if key in text:
                return kind
    return "generic"


def actions_for(kind: str, override: Any = None) -> list[str]:
    """某类家具的动作集（override 为模组声明，非法值被忽略）。"""
    if isinstance(override, (list, tuple)) and override:
        out = [a for a in override if a in ACTIONS]
        if out:
            return out
    return list(KIND_ACTIONS.get(str(kind), KIND_ACTIONS["generic"]))


def is_sensitive(obj: dict[str, Any], action: str) -> bool:
    """R11 判据: 敏感动作 -> 必须过主持人。模组可显式声明 sensitive 列表。"""
    if action not in ACTIONS:
        raise InteractionError("bad action %r" % action)
    declared = obj.get("sensitive") if isinstance(obj, dict) else None
    if isinstance(declared, (list, tuple)) and len(declared) > 0:
        # 模组显式声明了敏感动作集合 -> 以声明为准
        return action in declared
    return action in SENSITIVE_ACTIONS


# ---- 模组家具来源 ---------------------------------------------------------

def _read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _norm_room(raw: Any) -> dict[str, Any]:
    r = dict(raw) if isinstance(raw, dict) else {}
    return {
        "id": str(r.get("id") or r.get("room_id") or ""),
        "name": str(r.get("name") or r.get("id") or ""),
        "x": int(r.get("x") or 0),
        "y": int(r.get("y") or 0),
        "w": int(r.get("w") or r.get("width") or 400),
        "h": int(r.get("h") or r.get("height") or 300),
        "objects": list(r.get("objects") or r.get("furniture") or []),
    }


def resolve_module_dir(module_dir: str | Path) -> Path:
    """模组目录解析：接受绝对路径 / 相对路径 / **裸模组 id**。

    'sample_coc' -> APP_ROOT/modules/sample_coc（避免调用方依赖 cwd）。
    """
    root = Path(module_dir)
    if root.is_absolute() or root.exists():
        return root
    for cand in (APP_ROOT / root, APP_ROOT / "modules" / root):
        if cand.exists():
            return cand
    return root


def load_rooms(module_dir: str | Path) -> list[dict[str, Any]]:
    """读房间表: ① compiled/rooms.json（T5 单文件容器的导入用保存文件）
    ② maps/*.json（既有 MapAsset v1）③ 空。"""
    root = resolve_module_dir(module_dir)
    compiled = root / "compiled" / "rooms.json"
    if compiled.is_file():
        data = _read_json(compiled)
        rooms = data.get("rooms") if isinstance(data, dict) else data
        if isinstance(rooms, list) and rooms:
            return [_norm_room(r) for r in rooms]
    maps_dir = root / "maps"
    if maps_dir.is_dir():
        for f in sorted(maps_dir.glob("*.json")):
            try:
                data = _read_json(f)
            except (OSError, ValueError):
                continue
            rooms = data.get("rooms") if isinstance(data, dict) else None
            if isinstance(rooms, list) and rooms:
                return [_norm_room(r) for r in rooms]
    return []


def _anchor(room: dict[str, Any], idx: int) -> dict[str, int]:
    """R14: 家具锚点自动分配 —— 落在房间边界内的确定性坐标（不随机）。"""
    x, y, w, h = room["x"], room["y"], room["w"], room["h"]
    col = idx % 3
    row = idx // 3
    return {"x": int(x + w * (0.2 + 0.3 * col)),
            "y": int(y + h * (0.25 + 0.25 * min(row, 2)))}


def _norm_object(raw: Any, room: dict[str, Any], idx: int) -> dict[str, Any]:
    o = dict(raw) if isinstance(raw, dict) else {"name": str(raw)}
    name = str(o.get("name") or o.get("id") or "")
    kind = str(o.get("kind") or guess_kind(name))
    if kind not in KIND_ACTIONS:
        kind = guess_kind(name)
    oid = str(o.get("id") or ("%s_%s" % (room["id"], kind)))
    anchor = o.get("anchor") if isinstance(o.get("anchor"), dict) else _anchor(room, idx)
    return {
        "id": oid,
        "name": name or oid,
        "kind": kind,
        "room": str(o.get("room") or room["id"]),
        "anchor": {"x": int(anchor.get("x") or 0), "y": int(anchor.get("y") or 0)},
        "actions": actions_for(kind, o.get("actions")),
        "sensitive": list(o.get("sensitive") or []),
        "description": str(o.get("description") or ""),
        "search_skill": int(o.get("search_skill") or 50),
        "clue_ref": o.get("clue_ref"),
    }


def _default_objects(room: dict[str, Any]) -> list[dict[str, Any]]:
    """R14: 模组没给家具时，按房间名语义抽取 + 自动分配位置。

    房间名含「柜/桌/架/保险箱…」时优先该类家具；再补两类通用容器，
    保证「点开柜子出现『搜索』」在任何房间都成立。
    """
    kinds: list[str] = []
    hinted = guess_kind(room.get("name") or "")
    if hinted != "generic":
        kinds.append(hinted)
    for kind in ("cabinet", "desk", "drawer"):
        if kind not in kinds:
            kinds.append(kind)
    out: list[dict[str, Any]] = []
    for idx, kind in enumerate(kinds[:3]):
        oid = "%s_%s" % (room["id"], kind)
        label = _KIND_LABELS.get(kind, kind)
        out.append(_norm_object(
            {"id": oid, "name": "%s的%s" % (room.get("name") or room["id"], label),
             "kind": kind,
             "description": "看上去被人动过，表面落着一层薄灰。"},
            room, idx))
    return out


def objects_for_room(room: dict[str, Any]) -> list[dict[str, Any]]:
    """房间内可交互物: 显式声明优先，否则 R14 语义抽取 + 自动分配锚点。"""
    raw = room.get("objects") or []
    if isinstance(raw, list) and raw:
        return [_norm_object(o, room, i) for i, o in enumerate(raw)]
    return _default_objects(room)


def _load_module_yaml_interactives(module_dir: Path) -> dict[str, Any]:
    """可选 additive 文件 interactions.yaml: {rooms: {room_id: {objects: [...]}}}"""
    p = module_dir / "interactions.yaml"
    if not p.is_file():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def load_interactives(module_dir: str | Path) -> dict[str, Any]:
    """汇总一个模组的可交互物: {rooms:[{...}], objects:[{...}], source: str}。"""
    root = resolve_module_dir(module_dir)
    rooms = load_rooms(root)
    declared = _load_module_yaml_interactives(root)
    declared_rooms = declared.get("rooms") if isinstance(declared.get("rooms"), dict) else {}
    out_rooms: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    for room in rooms:
        extra = declared_rooms.get(room["id"]) if isinstance(declared_rooms, dict) else None
        if isinstance(extra, dict) and isinstance(extra.get("objects"), list):
            room = dict(room)
            room["objects"] = list(extra["objects"])
        objs = objects_for_room(room)
        out_rooms.append({"id": room["id"], "name": room["name"],
                          "x": room["x"], "y": room["y"],
                          "w": room["w"], "h": room["h"],
                          "objects": [o["id"] for o in objs]})
        objects.extend(objs)
    return {"module": root.name, "rooms": out_rooms, "objects": objects,
            "source": "compiled/rooms.json" if (root / "compiled" / "rooms.json").is_file()
                      else ("maps/*.json" if rooms else "none")}


def find_object(module_dir: str | Path, object_id: str,
                room: str | None = None) -> dict[str, Any]:
    """按 id 取家具（可限定房间）。找不到 -> InteractionError。"""
    data = load_interactives(module_dir)
    for obj in data["objects"]:
        if obj["id"] == object_id and (not room or obj["room"] == room):
            return obj
    raise InteractionError("unknown object: %r" % object_id)


def seed_for(campaign: str, object_id: str, action: str, salt: Any = 0) -> int:
    """确定性种子: 同一 (团/家具/动作/盐) 永远得到同一结果（可复现验收）。"""
    raw = "%s|%s|%s|%s" % (campaign, object_id, action, salt)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8], 16)


def resolve_action(campaign: str, obj: dict[str, Any], action: str,
                   seed: int | None = None) -> dict[str, Any]:
    """执行一次交互 -> 可判定结果（纯函数，不落库）。

    返回 {level, rolled, success, found, clue_ref, text, ...}；
    检定复用 app/rules/checks.resolve_check（与 R19 同一规则层）。
    """
    if action not in ACTIONS:
        raise InteractionError("bad action %r" % action)
    if not isinstance(obj, dict) or not obj.get("id"):
        raise InteractionError("object required")
    kind = str(obj.get("kind") or "generic")
    name = str(obj.get("name") or obj["id"])
    s = int(seed) if seed is not None else seed_for(campaign, str(obj["id"]), action)
    out: dict[str, Any] = {
        "object_id": obj["id"], "room": obj.get("room"), "kind": kind,
        "action": action, "action_label": ACTION_LABELS[action],
        "sensitive": is_sensitive(obj, action), "seed": s,
    }
    if action == "look":
        out.update({"level": "auto", "rolled": None, "success": True,
                    "found": False, "clue_ref": None, "skill": None,
                    "text": "你查看了%s：%s" % (
                        name, obj.get("description") or "看不出更多名堂。")})
        return out
    skill = int(obj.get("search_skill") or 50)
    chk = checks.resolve_check(skill=skill, difficulty="regular", seed=s)
    found = bool(chk["success"])
    clue_ref = obj.get("clue_ref") if found else None
    if action == "search":
        text = "你翻找%s，%s" % (name, "在夹层里摸到了东西。" if found else "除了一手灰，什么也没找到。")
    elif action == "pick_lock":
        text = "你摆弄%s的锁，%s" % (name, "锁簧「咔」地一声弹开了。" if found else "锁纹丝不动，还发出刺耳的声响。")
    else:  # take
        text = "你伸手去拿%s里的东西，%s" % (name, "顺利取到了手。" if found else "却扑了个空。")
    out.update({"level": chk["level"], "rolled": chk["rolled"], "success": found,
                "found": found, "clue_ref": clue_ref, "skill": skill, "text": text})
    return out
