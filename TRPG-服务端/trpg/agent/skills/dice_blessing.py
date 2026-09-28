"""Sample skill: dice blessing (W-B3).

Subscribes to ``roll`` events; appends one blessing line to the broadcast
without touching the dice value. Pure function — no allow permissions needed.
"""
from __future__ import annotations

from typing import Any

BLESSINGS: tuple[str, ...] = (
    "骰运亨通，克总保佑调查员！",
    "骰子落地，故事继续——祝大成功！",
    "愿你的 d100 永远远离大失败！",
)

SKILL_ID = "dice-blessing"
SKILL_NAME = "骰子祝福语"
SKILL_VERSION = "1.0.0"


def bless_roll(event: Any) -> Any:
    """Handle a roll event: return a copy with one blessing appended to broadcast.

    Never mutates the input event and never changes rolled/outcome values.
    """
    if isinstance(event, dict):
        payload = dict(event.get("payload", {}))
    else:
        payload = dict(getattr(event, "payload", {}) or {})
    rolled = payload.get("rolled")
    idx = (int(rolled) % len(BLESSINGS)) if isinstance(rolled, int) else 0
    text = str(payload.get("broadcast", ""))
    suffix = BLESSINGS[idx]
    payload = dict(payload)
    payload["broadcast"] = (text + "\n" + suffix) if text else suffix
    payload["blessing"] = suffix
    if isinstance(event, dict):
        out = dict(event)
        out["payload"] = payload
        return out
    # pydantic Event / namespace object: shallow copy then replace payload
    try:
        out = event.model_copy(update={"payload": payload})
        return out
    except AttributeError:
        import copy as _copy
        out = _copy.copy(event)
        out.payload = payload
        return out


# Manifest dict — entry is a "module:attr" hot-load path.
SKILL_MANIFEST: dict[str, Any] = {
    "skill_id": SKILL_ID,
    "name": SKILL_NAME,
    "version": SKILL_VERSION,
    "entry": "trpg.agent.skills.dice_blessing:bless_roll",
    "events_subscribed": ("roll",),
    "needs_allow": (),
}
