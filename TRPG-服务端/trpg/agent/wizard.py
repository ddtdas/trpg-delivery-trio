"""Open-game wizard — W-C1 (DESIGN §2.4 K3 + K1/K2 checklist).

New module (non-frozen): module whitelist + pre-game checklist +
house-rule template. Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any

MODULES: list[dict[str, Any]] = [
    {"id": "chaser", "name": "追书人", "level": "新手", "prep_hours": 2,
     "session_hours": 3, "why": "短经典，线索链完整，控场难度低"},
    {"id": "haunted", "name": "鬼屋", "level": "新手", "prep_hours": 1,
     "session_hours": 2, "why": "单场景，氛围教学首选"},
    {"id": "deadlight", "name": "死光", "level": "新手", "prep_hours": 2,
     "session_hours": 3, "why": "结构清晰，适合练节奏"},
    {"id": "blackwater", "name": "黑水溪", "level": "新手+", "prep_hours": 3,
     "session_hours": 4, "why": "稍长但流程完整，进阶第一车"},
]

LOCKED: list[dict[str, Any]] = [
    {"id": "poison_soup", "name": "毒汤",
     "reason": "毒汤：日系密室信息密度高，新手易漏关键链，先锁死"},
    {"id": "dark_box", "name": "常暗之箱",
     "reason": "多线并行+高难度推理，不适合首车，先锁死"},
]

CHECKLIST: list[str] = [
    "通读规则书一遍，战斗/技能/SAN页贴便签",
    "模组二遍法完成（线索链标色＋NPC名统一表）",
    "公示房规（骰法/成功等级/争议先快判后复盘）",
    "确认档期＋替补PL，准备线上保底",
    "先攻表预填，三线索保底就绪",
    "开场目标与边界声明准备好",
]

HOUSE_RULE_TEMPLATE: str = (
    "【房规公示】1）骰先于叙述；2）成功等级：大成功01＞极难＞困难＞成功＞失败＞大失败；"
    "3）争议10秒快判，记复盘项，团后对照判例库；4）KP终审，绝不替PC宣言；"
    "5）私聊信息转桌面摘要；6）超时KP有权快进。"
)


def list_modules(include_locked: bool = False) -> list[dict[str, Any]]:
    mods = list(MODULES)
    if include_locked:
        mods += [{**m, "locked": True} for m in LOCKED]
    return mods


def locked_reason(module_id: str) -> str:
    for m in LOCKED:
        if m["id"] == module_id:
            return str(m["reason"])
    raise KeyError(f"module {module_id!r} is not locked (or unknown)")


def get_checklist() -> list[str]:
    return list(CHECKLIST)


def check_offline(done: list[str]) -> dict[str, Any]:
    missing = [c for c in CHECKLIST if c not in done]
    return {"done": len(done), "total": len(CHECKLIST),
            "missing": missing, "ready": not missing}


def get_house_rule_template() -> str:
    return HOUSE_RULE_TEMPLATE


def plan_first_game(module_id: str) -> dict[str, Any]:
    mods = {m["id"]: m for m in MODULES}
    if module_id in mods:
        m = mods[module_id]
        return {"ok": True, "module": m,
                "checklist": CHECKLIST,
                "house_rules": HOUSE_RULE_TEMPLATE,
                "cheatsheet_ref": "coach.get_cheatsheet"}
    for lock in LOCKED:
        if lock["id"] == module_id:
            return {"ok": False, "locked": True,
                    "reason": lock["reason"],
                    "alternatives": [m["id"] for m in MODULES]}
    raise KeyError(f"unknown module {module_id!r}")
