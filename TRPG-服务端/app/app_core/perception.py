"""T7 (additive): 感知回显字幕 + 检定驱动的通知 (R18/R19) —— 领域层。

铁律 (D4):
  * 不新增事件类型: 感知通知走既有 INFO_REVEALED(scope=whisper, targets=[X])，
    由 ws_bridge 映射为冻结 WHISPER 帧，Hub.viewer_may_see 按 targets 服务端权威定向;
  * 不新增协议帧; 不写库（写路径由 command_bus 唯一收口）。

R18 语义: 玩家 B 进入房间时，B 的**定向**字幕可以看到房内 A 正在做什么；
          A 只有在自己的感知检定成功后才收到中性通知（**不含 B 的身份**）。
Python 3.12 compatible.
"""
from __future__ import annotations

import hashlib
from typing import Any

from app.rules import checks

__all__ = [
    "PerceptionError",
    "MOVE_KEYS",
    "movement_target",
    "token_positions",
    "positions_from_state",
    "room_name",
    "occupants",
    "mover_subtitle",
    "occupant_notice",
    "perception_seed",
    "resolve_perception",
    "DIFFICULTY_CODES",
]


class PerceptionError(ValueError):
    """非法感知请求。"""


MOVE_KEYS: tuple[str, ...] = ("room", "room_id", "to", "move", "target_room")

# checks.resolve_check 的难度字面量 -> 冻结 CheckResolved.difficulty(int) 编码
DIFFICULTY_CODES: dict[str, int] = {"regular": 1, "hard": 2, "extreme": 3}


def movement_target(action: Any) -> str:
    """从玩家行动里取「移动到哪个房间」（无 -> ""）。"""
    if not isinstance(action, dict):
        return ""
    for key in MOVE_KEYS:
        val = action.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def token_positions(events: list[Any]) -> dict[str, str]:
    """折叠 MAP_UPDATED 的 move/add_token -> {token: room_id}（确定性）。"""
    pos: dict[str, str] = {}
    for ev in events:
        if getattr(ev, "type", "") != "MAP_UPDATED":
            continue
        p = getattr(ev, "payload", None) or {}
        if p.get("op") not in ("move", "add_token"):
            continue
        token = str(p.get("target") or "")
        delta = p.get("delta") if isinstance(p.get("delta"), dict) else {}
        room = ""
        for key in MOVE_KEYS:
            val = delta.get(key)
            if isinstance(val, str) and val.strip():
                room = val.strip()
                break
        if token and room:
            pos[token] = room
    return pos


def positions_from_state(state: Any) -> dict[str, str]:
    """从投影态取 {token: room}（复用 state.maps 的 ops 历史）。"""
    pos: dict[str, str] = {}
    maps = getattr(state, "maps", None) or {}
    for _map_id, entry in maps.items():
        for op in (entry or {}).get("ops", []) or []:
            if op.get("op") not in ("move", "add_token"):
                continue
            token = str(op.get("target") or "")
            delta = op.get("delta") if isinstance(op.get("delta"), dict) else {}
            room = ""
            for key in MOVE_KEYS:
                val = delta.get(key)
                if isinstance(val, str) and val.strip():
                    room = val.strip()
                    break
            if token and room:
                pos[token] = room
    return pos


def room_name(rooms: list[dict[str, Any]], room_id: str) -> str:
    for r in rooms or []:
        if str(r.get("id")) == str(room_id):
            return str(r.get("name") or r.get("id") or room_id)
    return str(room_id)


def occupants(positions: dict[str, str], room_id: str,
              exclude: str = "") -> list[str]:
    """房间内的 token（按 token 名排序，确定性；exclude 排除自己）。"""
    out = [tok for tok, rid in positions.items()
           if rid == room_id and tok != exclude]
    return sorted(out)


def _label(token: str, names: dict[str, str] | None = None) -> str:
    if names and token in names and names[token]:
        return str(names[token])
    return str(token)


def mover_subtitle(mover: str, room_label: str,
                   others: list[dict[str, Any]],
                   names: dict[str, str] | None = None) -> str:
    """R18: 进入者自己的定向字幕（可以看到房内其他人在做什么）。"""
    who = _label(mover, names)
    if not others:
        return "你进入了%s，房间里空无一人。" % room_label
    parts = []
    for o in others:
        label = _label(str(o.get("token") or ""), names)
        act = str(o.get("action_text") or "").strip()
        parts.append("%s 正在%s" % (label, act) if act else "%s 也在房里" % label)
    return "你进入了%s，看到了 %s。" % (room_label, "；".join(parts))


def occupant_notice(room_label: str) -> str:
    """R19: 感知检定成功的通知 —— **中性文案，不含进入者身份**。"""
    return "你感觉你的房间多进来了一个人。"


def perception_seed(campaign: str, player_id: str, room_id: str,
                    salt: Any = 0) -> int:
    raw = "%s|%s|%s|%s" % (campaign, player_id, room_id, salt)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8], 16)


def resolve_perception(skill: int = 50, difficulty: str = "regular",
                       seed: int | None = None) -> dict[str, Any]:
    """感知/侦察检定（复用 app.rules.checks.resolve_check，可复现）。"""
    if difficulty not in DIFFICULTY_CODES:
        raise PerceptionError("difficulty must be one of %s" % sorted(DIFFICULTY_CODES))
    chk = checks.resolve_check(skill=int(skill), difficulty=difficulty, seed=seed)
    return {"skill": chk["skill"], "rolled": chk["rolled"], "level": chk["level"],
            "success": bool(chk["success"]), "difficulty": difficulty,
            "difficulty_code": DIFFICULTY_CODES[difficulty],
            "thresholds": chk["thresholds"], "seed": chk["seed"]}
