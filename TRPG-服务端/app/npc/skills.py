"""R28: 按 NPC 生成一次性（团内临时）技能 —— additive 分层。

需求判据 -> 本模块实现
--------------------------------------------------------------
(1) 「有名有姓的 NPC skill 列表非空」
    -> list_skills() 返回带 name / npc_id 的记录
       (REST: GET /api/campaigns/{c}/npc/skills)。
(2) 「可调用并产生规则层效果」
    -> invoke_skill() 把技能效果（加值 / 减值 / 技能值增量）喂给**既有规则内核**
       app.rules.checks.resolve_check，返回完整检定结果（rolled/level/success）。
       同时把一次性技能挂到规则内核的派生函数派发表上（固定名
       npc_ephemeral_skill），于是 rulepack 的 derived 表也能按名引用一次性技能：
       {"fn": "npc_ephemeral_skill", "args": {"skill_id": ..., "of": "$spot_hidden"}}。
(3) 「同名技能互不干扰」
    -> 作用域键 = (campaign_id, npc_id, name)：skill_id 形如
       npc-skill:<campaign>:<npc>:<slug>。同一名字给两个 NPC 生成 -> 两条互不
       相同的记录，效果与使用计数各自独立。
(4) 「临时 / 只属该 NPC / 本次团内可用 / 不污染全局技能表」
    -> 记录只存在本模块的 SKILLS（进程内字典，服务重启即清空 —— 即「临时、
       本次团内」语义）。全局技能表（trpg.agent.registry 的 SkillManifest 注册
       表）不新增任何条目；规则内核只多出一个**固定**派发名
       npc_ephemeral_skill（常量，不随 NPC 数量增长）。

不新增事件类型 / 不新增协议帧 / 不改冻结文件。Python 3.12 compatible.
"""
from __future__ import annotations

import re
import time
from typing import Any, Mapping

from app.rules import checks as checks_mod

__all__ = [
    "EFFECT_KINDS",
    "RULES_FN_NAME",
    "SKILLS",
    "skill_id_for",
    "forge_skill",
    "list_skills",
    "get_skill",
    "drop_skill",
    "drop_campaign_skills",
    "invoke_skill",
    "registry_size",
]

# 效果类型（全部落在既有规则内核的能力范围内）
EFFECT_KINDS: tuple[str, ...] = ("check_bonus", "check_penalty", "skill_delta")

# 规则内核里代表「一次性 NPC 技能」的固定派发名（常量，不随 NPC 数量增长）
RULES_FN_NAME = "npc_ephemeral_skill"

# 一次性技能表：skill_id -> record。进程内、非持久（= 临时 / 本次团内）
SKILLS: dict[str, dict[str, Any]] = {}

_SLUG_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_MAX_EFFECT_VALUE = 5


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def _slug(name: str) -> str:
    s = _SLUG_RE.sub("-", str(name).strip()).strip("-")
    return s[:48] or "skill"


def _need(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % field)
    return value.strip()


def skill_id_for(campaign_id: str, npc_id: str, name: str) -> str:
    """作用域化 id：同名技能在不同 NPC / 不同团之间互不干扰。"""
    return "npc-skill:%s:%s:%s" % (_need(campaign_id, "campaign_id"),
                                   _need(npc_id, "npc_id"),
                                   _slug(name))


def _norm_effect(effect: Mapping[str, Any] | None) -> dict[str, Any]:
    eff = dict(effect or {})
    kind = str(eff.get("kind") or "check_bonus")
    if kind not in EFFECT_KINDS:
        raise ValueError("effect.kind must be one of %s, got %r"
                         % (list(EFFECT_KINDS), kind))
    value = eff.get("value", 1)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("effect.value must be int")
    if not 1 <= value <= _MAX_EFFECT_VALUE:
        raise ValueError("effect.value must be 1..%d, got %d"
                         % (_MAX_EFFECT_VALUE, value))
    out: dict[str, Any] = {"kind": kind, "value": value}
    if eff.get("target"):
        out["target"] = str(eff["target"]).strip()
    if eff.get("note"):
        out["note"] = str(eff["note"])
    return out


def forge_skill(campaign_id: str, npc_id: str, name: str,
                effect: Mapping[str, Any] | None = None,
                max_uses: int = 3) -> dict[str, Any]:
    """为某个 NPC 生成一次性技能（幂等：同名同 NPC 返回既有记录）。

    max_uses: 本次团内可调用次数（一次性 = 有限次、团内有效、不入全局表）。
    """
    cid = _need(campaign_id, "campaign_id")
    nid = _need(npc_id, "npc_id")
    nm = _need(name, "name")
    if isinstance(max_uses, bool) or not isinstance(max_uses, int) or max_uses < 1:
        raise ValueError("max_uses must be int >= 1")
    sid = skill_id_for(cid, nid, nm)
    existing = SKILLS.get(sid)
    if existing is not None:
        out = dict(existing)
        out["reused"] = True
        return out
    rec: dict[str, Any] = {
        "skill_id": sid,
        "name": nm,
        "npc_id": nid,
        "campaign_id": cid,
        "ephemeral": True,
        "scope": "campaign",           # 只属于本次团 / 该 NPC
        "effect": _norm_effect(effect),
        "max_uses": max_uses,
        "uses": 0,
        "created_ts": _now(),
        "reused": False,
    }
    SKILLS[sid] = rec
    return dict(rec)


def list_skills(campaign_id: str | None = None,
                npc_id: str | None = None) -> list[dict[str, Any]]:
    """列出一次性技能（可按团 / 按 NPC 过滤）。"""
    out = []
    for rec in SKILLS.values():
        if campaign_id and rec["campaign_id"] != campaign_id:
            continue
        if npc_id and rec["npc_id"] != npc_id:
            continue
        out.append(dict(rec))
    out.sort(key=lambda r: (r["campaign_id"], r["npc_id"], r["name"]))
    return out


def get_skill(skill_id: str) -> dict[str, Any] | None:
    rec = SKILLS.get(str(skill_id))
    return dict(rec) if rec is not None else None


def drop_skill(skill_id: str) -> bool:
    return SKILLS.pop(str(skill_id), None) is not None


def drop_campaign_skills(campaign_id: str) -> int:
    """团结束时清场（一次性技能随团消亡）。"""
    doomed = [k for k, v in SKILLS.items() if v["campaign_id"] == campaign_id]
    for k in doomed:
        SKILLS.pop(k, None)
    return len(doomed)


def registry_size() -> int:
    """规则内核派生函数表大小（用于证明「不随 NPC 技能数量增长」）。"""
    return len(checks_mod.REGISTRY)


def _card_value(card: Mapping[str, Any], target: str) -> int:
    """从角色卡取技能/属性值（与 app.rules.arbiter.Arbiter.skill_value 同口径）。"""
    if not isinstance(card, Mapping):
        raise TypeError("card must be a mapping")
    ref = str(target or "").lstrip("$")
    if not ref:
        raise ValueError("target must be a non-empty string")
    skills = card.get("skills") or {}
    attrs = card.get("attrs") or {}
    if isinstance(skills, Mapping) and ref in skills:
        val = skills[ref]
    elif isinstance(attrs, Mapping) and ref in attrs:
        val = attrs[ref]
    else:
        raise ValueError("unknown check target on card: %r" % ref)
    if isinstance(val, bool) or not isinstance(val, int):
        raise TypeError("card value for %r must be int" % ref)
    return val


def _apply_to_skill_value(rec: Mapping[str, Any], base: int) -> int:
    """把技能效果折算成规则内核的 (skill, bonus, penalty)。"""
    eff = rec["effect"]
    kind = eff["kind"]
    if kind == "skill_delta":
        return max(0, min(100, base + eff["value"]))
    return base


def _rules_bonus_penalty(rec: Mapping[str, Any]) -> tuple[int, int]:
    kind = rec["effect"]["kind"]
    if kind == "check_bonus":
        return rec["effect"]["value"], 0
    if kind == "check_penalty":
        return 0, rec["effect"]["value"]
    return 0, 0


def invoke_skill(skill_id: str, card: Mapping[str, Any],
                 target: str | None = None, difficulty: str = "regular",
                 rolled: int | None = None,
                 seed: int | None = None) -> dict[str, Any]:
    """调用一次性技能 -> 走既有规则内核产出规则层效果。

    返回 {skill_id, name, npc_id, effect, target, uses, max_uses, rules, ...}，
    其中 rules 即 app.rules.checks.resolve_check 的原始输出（rolled/level/success）。
    """
    rec = SKILLS.get(str(skill_id))
    if rec is None:
        raise KeyError("unknown ephemeral skill: %r" % skill_id)
    if rec["uses"] >= rec["max_uses"]:
        raise ValueError("ephemeral skill exhausted: %s (max_uses=%d)"
                         % (rec["skill_id"], rec["max_uses"]))
    tgt = str(target or rec["effect"].get("target") or "").strip()
    if not tgt:
        raise ValueError("target required (skill effect has no default target)")
    base = _card_value(card, tgt)
    skill_value = _apply_to_skill_value(rec, base)
    bonus, penalty = _rules_bonus_penalty(rec)
    rules = checks_mod.resolve_check(skill_value, rolled=rolled,
                                     difficulty=difficulty, bonus=bonus,
                                     penalty=penalty, seed=seed)
    rec["uses"] = int(rec["uses"]) + 1
    return {
        "skill_id": rec["skill_id"],
        "name": rec["name"],
        "npc_id": rec["npc_id"],
        "campaign_id": rec["campaign_id"],
        "ephemeral": True,
        "effect": dict(rec["effect"]),
        "target": tgt,
        "card_value": base,
        "skill_value_used": skill_value,
        "uses": rec["uses"],
        "max_uses": rec["max_uses"],
        "uses_left": rec["max_uses"] - rec["uses"],
        "rules_layer": "app.rules.checks.resolve_check",
        "rules": rules,
    }


# ---------------------------------------------------------------------------
# 规则内核派发入口：让 rulepack 的 derived 表能按名引用一次性 NPC 技能。
# 注意：这里注册的是**一个固定名**（RULES_FN_NAME），不随 NPC / 技能数量增长，
# 因此不构成「污染全局技能表」—— 各 NPC 的一次性技能仍只活在 SKILLS 里。
# ---------------------------------------------------------------------------

def _fn_npc_ephemeral_skill(args: Mapping[str, Any],
                            card: Mapping[str, Any]) -> int:
    """{fn: npc_ephemeral_skill, args: {skill_id, of}} -> 结算后的技能值(int)。"""
    if not isinstance(args, Mapping):
        raise TypeError("args must be a mapping")
    skill_id = args.get("skill_id")
    rec = SKILLS.get(str(skill_id))
    if rec is None:
        raise ValueError("unknown ephemeral skill: %r" % skill_id)
    of = args.get("of")
    if not isinstance(of, str) or not of:
        raise ValueError("args.of must be a non-empty $ref string")
    base = _card_value(card, of)
    return _apply_to_skill_value(rec, base)


if RULES_FN_NAME not in checks_mod.REGISTRY:
    checks_mod.register(RULES_FN_NAME, _fn_npc_ephemeral_skill)
