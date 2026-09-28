"""TRPG context builder (MIT).

Events -> prompt messages with a token budget. Pure functions.

Budget model (documented estimate, no tokenizer dependency):
``estimate_tokens(text) = max(1, len(text) // 4)`` (CJK-friendly rough
count: ~1 token per CJK char, ~4 chars per English token).
``build_prompt`` keeps: system head + rolling summary (if any) + the
newest events that fit, oldest-first within the kept window. Overflow
is reported (dropped count) so callers can surface it.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = [
    "estimate_tokens",
    "event_to_text",
    "build_prompt",
    "DEFAULT_BUDGET",
    "SYSTEM_HEAD",
]

DEFAULT_BUDGET = 4000
SYSTEM_HEAD = (
    "你是 TRPG 主持人助手。你只能起草叙事提案，绝不直接修改游戏状态。"
    "输出为一段中文旁白候选，等待主持人批准。"
)


def estimate_tokens(text: str) -> int:
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    return max(1, len(text) // 4)


def event_to_text(ev: Mapping[str, Any]) -> str:
    """Render one event mapping (or GameEvent-like) to one prompt line."""
    if not isinstance(ev, Mapping):
        raise TypeError("event must be a mapping")
    etype = str(ev.get("type", "?"))
    payload = ev.get("payload", {})
    if isinstance(payload, Mapping):
        bits = []
        for key in ("text", "intent_summary", "label", "summary", "reason"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                bits.append(f"{key}={val.strip()[:120]}")
        detail = " ".join(bits)
    else:
        detail = str(payload)[:120]
    actor = ev.get("actor", "?")
    return f"[{ev.get('seq', '?')}] {etype} by {actor}" + (f" :: {detail}" if detail else "")


def build_prompt(
    events: Sequence[Mapping[str, Any]],
    summary: str = "",
    budget: int = DEFAULT_BUDGET,
    task: str = "",
) -> dict:
    """Build chat messages inside ``budget`` tokens.

    Returns {"messages": [...], "usage": {...}} where usage reports
    estimated tokens, kept/dropped event counts. Messages: system head,
    optional summary, then kept event lines as one user message, then
    the task instruction (user). The task line is always kept; events
    yield oldest-first when over budget.
    """
    if not isinstance(budget, int) or budget < 64:
        raise ValueError(f"budget must be int >= 64, got {budget!r}")
    if not isinstance(summary, str):
        raise TypeError("summary must be str")
    if not isinstance(task, str):
        raise TypeError("task must be str")
    ev_list = list(events)
    for i, ev in enumerate(ev_list):
        if not isinstance(ev, Mapping):
            raise TypeError(f"events[{i}] must be a mapping")

    head_cost = estimate_tokens(SYSTEM_HEAD)
    summary_cost = estimate_tokens(summary) if summary.strip() else 0
    task_text = task.strip() or "请根据上述事件与摘要，起草下一段中文旁白（150字内）。"
    task_cost = estimate_tokens(task_text)

    fixed = head_cost + summary_cost + task_cost + 32  # framing slack
    room = budget - fixed
    lines = [event_to_text(ev) for ev in ev_list]
    costs = [estimate_tokens(line) for line in lines]

    kept: list[str] = []
    dropped = 0
    # Walk newest-first to fill the budget, then restore chrono order.
    for line, cost in reversed(list(zip(lines, costs))):
        if sum_kept(kept) + cost <= room:
            kept.append(line)
        else:
            dropped += 1
    kept.reverse()
    # If even the newest single event does not fit, keep it anyway and
    # report over_budget (caller decides: raise budget or compress).
    over_budget = False
    if not kept and lines:
        kept = [lines[-1]]
        dropped = len(lines) - 1
        over_budget = True

    messages = [{"role": "system", "content": SYSTEM_HEAD}]
    if summary.strip():
        messages.append({"role": "user", "content": f"[历史摘要]\n{summary.strip()}"})
    if kept:
        messages.append({"role": "user", "content": "[最近事件]\n" + "\n".join(kept)})
    messages.append({"role": "user", "content": task_text})
    used = fixed + sum(estimate_tokens(line) for line in kept) - 32
    return {
        "messages": messages,
        "usage": {
            "budget": budget,
            "estimated_tokens": used,
            "events_total": len(ev_list),
            "events_kept": len(kept),
            "events_dropped": dropped,
            "over_budget": over_budget,
        },
    }


def sum_kept(kept: list[str]) -> int:
    return sum(estimate_tokens(line) for line in kept)