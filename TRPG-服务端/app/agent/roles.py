"""R20: agent 职责角色注册表 —— 多角色可单独启停 + 单角色降级不影响他人 + 降级可见。

设计约束：
  * **不改冻结件** `app/domain/events.py` 的 EVENT_TYPES —— 其中没有"agent 职责角色开关"事件
    （`ROLE_ASSIGNED` 是**局内身份分配**，语义不同，不能挪用）。
    故角色开关与健康态持久化到 `data/agent_roles.json`（与 `load_persisted_tables` 同为进程外持久化）。
  * 降级口径**复用** `app/agent/gateway.py` 的 `ok | degraded | fault`（不另造第二套语义）。
  * 铁律：单角色失败**不得**影响其他角色 —— `run_role()` 捕获异常并返回 fallback，
    调用方永远拿到可用结果，同时把降级事实登记到健康表供 UI 显示。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import APP_ROOT

_STATE_FILE = APP_ROOT / "data" / "agent_roles.json"
_LOCK = threading.RLock()

#: R20 要求 ≥4 个职责角色；此处给出 6 个（覆盖 TASKBOOK 列举的全部职责面）。
ROLE_DEFS: tuple[tuple[str, str, str], ...] = (
    ("narrative", "叙事", "生成与润色叙事文本、旁白"),
    ("rules", "规则裁决", "判定检定成败与后果裁定"),
    ("map", "地图与空间", "棋子移动、迷雾、光照与空间校验"),
    ("compliance", "审核与合规", "内容合规与安全审核"),
    ("npc", "NPC 扮演", "NPC 台词、动机与记忆"),
    ("pace", "节奏与调度", "回合窗口、场景推进与调度"),
)
ROLE_IDS: tuple[str, ...] = tuple(r[0] for r in ROLE_DEFS)
_DEF_BY_ID = {r[0]: r for r in ROLE_DEFS}

#: 连续失败达到该阈值即判定降级 / 故障（与 gateway 的 ok|degraded|fault 对齐）。
DEGRADED_AT = 3
FAULT_AT = 5

#: 状态：{campaign: {"enabled": {rid: bool}, "health": {rid: {...}}}}
_STATE: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blank(campaign: str) -> dict[str, Any]:
    return {
        "campaign_id": campaign,
        "enabled": {rid: True for rid in ROLE_IDS},
        "health": {rid: {"status": "ok", "fails": 0, "calls": 0,
                         "last_error": "", "last_ts": ""} for rid in ROLE_IDS},
    }


def _load_file() -> None:
    try:
        raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    if isinstance(raw, dict):
        for campaign, val in raw.items():
            if isinstance(val, dict):
                base = _blank(campaign)
                base["enabled"].update({k: bool(v) for k, v in (val.get("enabled") or {}).items()
                                        if k in _DEF_BY_ID})
                for rid, h in (val.get("health") or {}).items():
                    if rid in _DEF_BY_ID and isinstance(h, dict):
                        base["health"][rid].update(h)
                _STATE[campaign] = base


def _save_file() -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(_STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # 持久化失败不影响在线服务（内存态仍权威）


_load_file()


def _state(campaign: str) -> dict[str, Any]:
    with _LOCK:
        if campaign not in _STATE:
            _STATE[campaign] = _blank(campaign)
        return _STATE[campaign]


def list_roles(campaign: str) -> list[dict[str, Any]]:
    """全部角色 + 启停 + 健康态（UI 直接渲染）。"""
    st = _state(campaign)
    out: list[dict[str, Any]] = []
    for rid, name, duty in ROLE_DEFS:
        h = st["health"][rid]
        out.append({
            "role_id": rid, "name": name, "duty": duty,
            "enabled": bool(st["enabled"][rid]),
            "status": h.get("status", "ok"),
            "fails": int(h.get("fails", 0)), "calls": int(h.get("calls", 0)),
            "last_error": h.get("last_error", ""), "last_ts": h.get("last_ts", ""),
        })
    return out


def role_summary(campaign: str) -> dict[str, Any]:
    rs = list_roles(campaign)
    return {
        "campaign_id": campaign,
        "count": len(rs),
        "enabled_count": sum(1 for r in rs if r["enabled"]),
        "degraded": [r["role_id"] for r in rs if r["status"] != "ok"],
        "roles": rs,
    }


def set_enabled(campaign: str, role_id: str, enabled: bool) -> dict[str, Any]:
    if role_id not in _DEF_BY_ID:
        raise KeyError(role_id)
    with _LOCK:
        st = _state(campaign)
        st["enabled"][role_id] = bool(enabled)
        # 重新启用即视为恢复：清空失败计数（否则会一直显示降级）。
        if enabled:
            st["health"][role_id] = {"status": "ok", "fails": 0,
                                     "calls": int(st["health"][role_id].get("calls", 0)),
                                     "last_error": "", "last_ts": _now()}
        _save_file()
    return {"role_id": role_id, "enabled": bool(enabled)}


def is_enabled(campaign: str, role_id: str) -> bool:
    return bool(_state(campaign)["enabled"].get(role_id, True))


def record_outcome(campaign: str, role_id: str, ok: bool, error: str = "") -> dict[str, Any]:
    """登记一次调用结果，并按连续失败数推导 ok/degraded/fault。"""
    if role_id not in _DEF_BY_ID:
        raise KeyError(role_id)
    with _LOCK:
        h = _state(campaign)["health"][role_id]
        h["calls"] = int(h.get("calls", 0)) + 1
        if ok:
            h["fails"] = 0
            h["status"] = "ok"
            h["last_error"] = ""
        else:
            h["fails"] = int(h.get("fails", 0)) + 1
            h["status"] = ("fault" if h["fails"] >= FAULT_AT
                           else "degraded" if h["fails"] >= DEGRADED_AT else "ok")
            h["last_error"] = str(error)[:300]
        h["last_ts"] = _now()
        _save_file()
        return dict(h)


def run_role(campaign: str, role_id: str,
             fn: Callable[[], Any], fallback: Any = None) -> tuple[Any, bool]:
    """执行某角色的一次工作。

    返回 (结果, 是否降级)。**任何异常都被吞掉并转为 fallback**，
    因此单角色失败不会中断其他角色 —— 这是 R20 的核心判据。
    角色被禁用时直接走 fallback 并记为一次降级（"已停用"）。
    """
    if role_id not in _DEF_BY_ID:
        raise KeyError(role_id)
    if not is_enabled(campaign, role_id):
        record_outcome(campaign, role_id, False, "role disabled")
        return fallback, True
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 —— 故意兜住一切，保证隔离
        record_outcome(campaign, role_id, False, f"{type(exc).__name__}: {exc}")
        return fallback, True
    record_outcome(campaign, role_id, True)
    return result, False


def reset_roles(campaign: str | None = None) -> None:
    """测试用：清空内存态（不动磁盘）。"""
    with _LOCK:
        if campaign is None:
            _STATE.clear()
        else:
            _STATE.pop(campaign, None)
