"""T7 (additive): R17 同时行动流水线 —— 回合窗口批量结算（纯函数）。

判据 (R17):
  ① 回合窗口开启，所有玩家同时输入（可撤回）—— 复用既有 TURN_STARTED /
     ACTION_SUBMITTED / ACTION_WITHDRAWN 事件与 turn_window 状态机;
  ② 窗口关闭，服务端**批量计算**（本模块）;
  ③ 结果**不直接下发**，先进 GM 待审队列（NARRATION_PROPOSED 候选 + 投递规格）;
  ④ GM 可逐条编辑后发送（既有 POST /approvals）;
  ⑤ 只有「已发送」才到达玩家（INFO_REVEALED whisper 定向投递）。

本模块只做「计算」，不落事件、不下发 —— 因此不存在「计算即泄露」的路径。
Python 3.12 compatible.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.rules import checks

__all__ = [
    "PipelineError",
    "CHECK_VERBS",
    "candidate_id",
    "resolve_window",
    "player_order",
]

# 需要过规则层的动词（命中则跑一次 CoC 检定，结果可追溯）
CHECK_VERBS: tuple[str, ...] = (
    "搜索", "搜寻", "侦查", "观察", "查看", "撬", "听", "聆听", "潜行",
    "追踪", "攀爬", "闪避", "搏斗", "射击", "图书馆", "医学", "心理",
    "说服", "恐吓", "魅惑", "幸运",
)


class PipelineError(ValueError):
    """非法流水线请求。"""


def player_order(turn: Any) -> list[str]:
    """本回合的结算顺序：turn.order 优先，否则按 player_id 排序（确定性）。"""
    order = list(getattr(turn, "order", None) or [])
    submitted = dict(getattr(turn, "submitted", None) or {})
    if not order:
        order = sorted(submitted.keys())
    return [p for p in order if p in submitted]


def candidate_id(campaign: str, turn_no: int, player_id: str,
                 action: Any) -> str:
    """确定性候选 id（同回合同输入 -> 同 id，重复 resolve 幂等）。

    必须**不透明**：NARRATION_APPROVED/EDITED 经冻结的 ws_bridge 映射为
    public 帧，id 里嵌 turn/玩家身份会向全桌广播「谁在做什么」
    （实测 R18 泄露点）。身份保留在 pipeline_store 与 KP 通道里。
    """
    raw = json.dumps({"c": campaign, "t": turn_no, "p": player_id,
                      "a": action}, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "p:%s:%s" % (campaign, h)


def _action_text(action: Any) -> str:
    if isinstance(action, dict):
        text = action.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    if isinstance(action, str) and action.strip():
        return action.strip()
    return json.dumps(action or {}, ensure_ascii=False)


def _needs_check(text: str) -> str:
    for verb in CHECK_VERBS:
        if verb in text:
            return verb
    return ""


def _check_seed(campaign: str, turn_no: int, player_id: str) -> int:
    raw = "pipeline|%s|%s|%s" % (campaign, turn_no, player_id)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8], 16)


def resolve_window(campaign: str, turn: Any, skill: int = 50,
                   difficulty: str = "regular",
                   seed_base: int | None = None) -> list[dict[str, Any]]:
    """批量结算一个已关闭的行动窗 -> 候选列表（**不下发、不落库**）。

    每条候选: {proposal_id, player_id, turn_no, text, intention, reasoning,
              check:{...}|None}
    """
    if turn is None:
        raise PipelineError("turn required")
    turn_no = int(getattr(turn, "turn_no", 0) or 0)
    submitted = dict(getattr(turn, "submitted", None) or {})
    out: list[dict[str, Any]] = []
    for player_id in player_order(turn):
        entry = submitted.get(player_id) or {}
        action = entry.get("action") or {}
        intent = str(entry.get("intent") or "")
        act_text = _action_text(action)
        verb = _needs_check(act_text)
        check: dict[str, Any] | None = None
        if verb:
            seed = _check_seed(campaign, turn_no, player_id)
            if seed_base is not None:
                seed = int(seed_base) + seed % 1000
            chk = checks.resolve_check(skill=int(skill), difficulty=difficulty,
                                       seed=seed)
            check = {"verb": verb, "skill": chk["skill"], "rolled": chk["rolled"],
                     "level": chk["level"], "success": bool(chk["success"]),
                     "difficulty": difficulty, "seed": chk["seed"]}
        lines = ["%s 尝试：%s" % (player_id, act_text)]
        if intent:
            lines.append("（意图：%s）" % intent)
        if check:
            lines.append("检定 %s：d100=%s / 技能=%s / %s -> %s" % (
                check["verb"], check["rolled"], check["skill"],
                check["level"], "成功" if check["success"] else "失败"))
        out.append({
            "proposal_id": candidate_id(campaign, turn_no, player_id, action),
            "player_id": player_id,
            "turn_no": turn_no,
            "text": "\n".join(lines),
            "intention": intent or None,
            "reasoning": "T7 action_pipeline.resolve_window（服务端批量结算，"
                         "结果先入待审队列）",
            "check": check,
        })
    return out
