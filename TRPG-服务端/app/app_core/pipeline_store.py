"""T7 (additive): 待审候选的「投递规格」登记表 (R11/R17/R18/R19)。

为什么需要它:
  * **候选正文绝不能进事件流/公开帧** —— 否则玩家在 GM 发送前就能通过
    REST 事件流（R9 未裁剪时）或 /review DTO 读到结果，R17 的负例
    「发送前玩家收不到任何结果」与 R18 的「A 未察觉则不含 B 信息」必然失败。
    因此 NARRATION_PROPOSED 只带**脱敏标签**，真实正文存在本表，
    只有 KP token 能通过 GET /api/campaigns/{c}/approvals 读到。
  * 本表**不是第二套审批机制**: 它不做任何审批决定，只登记「这条候选
    由谁收、正文是什么、批准后要落什么效果事件」。所有决定仍走既有
    POST /api/campaigns/{c}/approvals。
Python 3.12 compatible.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import APP_ROOT

__all__ = [
    "STORE_DIR",
    "PENDING", "DELIVERED", "REJECTED",
    "register", "get", "set_status", "pending", "for_actor", "all_items",
    "load", "save", "reset",
]

STORE_DIR = APP_ROOT / "data" / "pipeline"

PENDING = "pending"
DELIVERED = "delivered"
REJECTED = "rejected"

_CACHE: dict[str, dict[str, dict[str, Any]]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", str(name or ""))[:128] or "campaign"


def _path(campaign: str) -> Path:
    return STORE_DIR / ("%s.json" % _safe(campaign))


def load(campaign: str) -> dict[str, dict[str, Any]]:
    """读一个团的登记表（进程内缓存 + 磁盘回退；重启后可恢复）。"""
    key = str(campaign)
    if key in _CACHE:
        return _CACHE[key]
    data: dict[str, dict[str, Any]] = {}
    p = _path(campaign)
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("items"), dict):
                data = {str(k): dict(v) for k, v in raw["items"].items()
                        if isinstance(v, dict)}
        except (OSError, ValueError):
            data = {}
    _CACHE[key] = data
    return data


def save(campaign: str) -> None:
    """原子落盘（临时文件 + replace），失败不抛出（best-effort）。"""
    data = _CACHE.get(str(campaign))
    if data is None:
        return
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        p = _path(campaign)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"campaign": campaign, "items": data},
                                  ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def register(campaign: str, proposal_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """登记/覆盖一条投递规格（同 proposal_id 幂等）。"""
    if not proposal_id:
        raise ValueError("proposal_id required")
    data = load(campaign)
    item = dict(data.get(proposal_id) or {})
    item.update(dict(spec or {}))
    item["proposal_id"] = proposal_id
    item["campaign"] = campaign
    item.setdefault("status", PENDING)
    item.setdefault("created_ts", _now())
    data[proposal_id] = item
    save(campaign)
    return item


def get(campaign: str, proposal_id: str) -> dict[str, Any] | None:
    return load(campaign).get(str(proposal_id))


def set_status(campaign: str, proposal_id: str, status: str,
               **extra: Any) -> dict[str, Any] | None:
    data = load(campaign)
    item = data.get(str(proposal_id))
    if item is None:
        return None
    item["status"] = status
    item["decided_ts"] = _now()
    item.update(extra)
    save(campaign)
    return item


def all_items(campaign: str) -> list[dict[str, Any]]:
    data = load(campaign)
    return [dict(v) for v in data.values()]


def pending(campaign: str) -> list[dict[str, Any]]:
    return [dict(v) for v in load(campaign).values()
            if v.get("status") == PENDING]


def for_actor(campaign: str, actor: str) -> list[dict[str, Any]]:
    """某个玩家自己的条目（用于「已上报待主持人」状态回显，不含他人数据）。"""
    out = []
    for v in load(campaign).values():
        targets = list(v.get("targets") or [])
        if v.get("actor") == actor or actor in targets:
            out.append(dict(v))
    return out


def reset(campaign: str | None = None) -> None:
    """测试隔离用。"""
    if campaign is None:
        _CACHE.clear()
        return
    _CACHE.pop(str(campaign), None)
