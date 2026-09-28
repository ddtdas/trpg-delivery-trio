"""TRPG MCP check tools: roll_check (writes) + roll_preview (read-only) (MIT).

preview never touches the store (anti-double-dice); check goes through
the CommandBus-equivalent path: deterministic resolve + CHECK_RESOLVED
event append. Python 3.12 compatible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.domain.events import make_event
from app.mcp.auth import AuthError
from app.rules import dice as dice_mod
from app.rules.checks import grade
from app.store.event_store import EventStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int(v: Any, name: str) -> int:
    if isinstance(v, bool):
        raise ValueError("%s must be int" % name)
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError("%s must be int" % name) from None


def _seed_int(seed: Any) -> int | None:
    """Contract seed is a free string; hash it deterministically to int."""
    if seed is None:
        return None
    if isinstance(seed, bool):
        raise ValueError("seed must be int/str or None")
    if isinstance(seed, int):
        return seed
    import hashlib
    return int(hashlib.sha256(str(seed).encode("utf-8")).hexdigest()[:8], 16)


def preview_roll(skill: int, difficulty: str = "regular",
                 bonus: int = 0, penalty: int = 0,
                 seed: Any = None) -> dict[str, Any]:
    """Pure preview: roll + grade, NO store access, NO side effects."""
    if difficulty not in ("regular", "hard", "extreme"):
        raise ValueError("bad difficulty %r" % difficulty)
    d = dice_mod.roll_bonus_penalty(bonus=bonus, penalty=penalty,
                                    seed=_seed_int(seed))
    total = int(d["total"])
    level = grade(skill, total)
    required = {"regular": "success", "hard": "hard",
                "extreme": "extreme"}[difficulty]
    order = ("fumble", "fail", "success", "hard", "extreme", "critical")
    return {"total": total, "level": level, "note": "preview-only",
            "success": order.index(level) >= order.index(required),
            "rolled": [total]}


async def do_preview(args: dict[str, Any]) -> dict[str, Any]:
    skill = _as_int(args.get("difficulty", 50) if "skill" not in args
                    else args.get("skill"), "difficulty/skill")
    difficulty = str(args.get("difficulty_level", "regular")
                     if isinstance(args.get("difficulty"), int)
                     else args.get("difficulty", "regular"))
    out = preview_roll(skill=skill, difficulty=difficulty,
                       bonus=_as_int(args.get("bonus", 0), "bonus"),
                       penalty=_as_int(args.get("penalty", 0), "penalty"),
                       seed=args.get("seed"))
    return {"total": out["total"], "level": out["level"],
            "note": "preview-only"}


async def do_check(args: dict[str, Any], store: EventStore) -> dict[str, Any]:
    for f in ("campaign_id", "turn_no", "card_id", "target", "seed"):
        if f not in args:
            raise AuthError("actor_required") if f == "campaign_id" \
                else ValueError("missing param: %s" % f)
    skill = _as_int(args.get("difficulty", 50), "difficulty")
    out = preview_roll(skill=skill,
                       bonus=_as_int(args.get("bonus", 0), "bonus"),
                       penalty=_as_int(args.get("penalty", 0), "penalty"),
                       seed=args.get("seed"))
    ev = make_event(
        seq=0, campaign_id=str(args["campaign_id"]), type="CHECK_RESOLVED",
        payload={"campaign_id": str(args["campaign_id"]),
                 "turn_no": _as_int(args["turn_no"], "turn_no"),
                 "card_id": str(args["card_id"]),
                 "target": str(args["target"]), "difficulty": skill,
                 "rolled": out["rolled"], "total": out["total"],
                 "level": out["level"], "seed": str(args["seed"]),
                 "summary": "mcp roll_check"},
        actor="kp", ts=_now())
    await store.init()
    seqs = await store.append(str(args["campaign_id"]), [ev])
    return {"ok": True, "rolled": out["rolled"], "total": out["total"],
            "level": out["level"], "seed": str(args["seed"]),
            "events": [{"seq": seqs[0], "type": "CHECK_RESOLVED"}]}
