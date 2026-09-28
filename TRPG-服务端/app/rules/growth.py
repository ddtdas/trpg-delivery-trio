"""TRPG interlude (幕间) growth checks (MIT).

Pure functions: given a skill's current value and a d100 growth roll,
decide whether the skill improves and by how much. No I/O, no globals.
Python 3.12 compatible.

CoC7 growth convention:
- During play, mark skills used with a notable success (caller tracks).
- At interlude, for each marked skill roll d100: if rolled > skill,
  the investigator learns from experience -> skill += 1d10 (capped at 99
  for growth; 100 is reachable only via other means ... here cap 99).
  Unmarked skills do not roll (reported as ineligible).
- Extreme edge: skill >= 99 cannot grow further (already at cap).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.rules import dice as dice_mod

GROWTH_CAP = 99

__all__ = ["growth_check", "growth_batch", "GROWTH_CAP"]


def _check_skill(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"skill must be int 0..100, got {type(value).__name__}")
    if not 0 <= value <= 100:
        raise ValueError(f"skill must be 0..100, got {value}")
    return value


def growth_check(
    skill: int,
    marked: bool = True,
    rolled: int | None = None,
    seed: int | None = None,
) -> dict:
    """Resolve one skill's growth.

    - ``marked`` False -> ineligible, no roll.
    - ``rolled`` explicit 1..100, else seeded d100.
    - Success (rolled > skill and skill < cap) -> gain = 1d10.
    Returns detail dict (JSON-serializable).
    """
    s = _check_skill(skill)
    if not isinstance(marked, bool):
        raise TypeError(f"marked must be bool, got {type(marked).__name__}")
    if rolled is not None:
        if isinstance(rolled, bool) or not isinstance(rolled, int):
            raise TypeError(f"rolled must be int 1..100, got {type(rolled).__name__}")
        if not 1 <= rolled <= 100:
            raise ValueError(f"rolled must be 1..100, got {rolled}")
        roll_detail: dict = {"die": "d100", "total": rolled, "mode": "explicit", "seed": seed}
        r = rolled
    else:
        d = dice_mod.roll_d100(seed=seed)
        r = d["total"]
        roll_detail = d
    if not marked:
        return {
            "skill_before": s, "marked": False, "eligible": False,
            "rolled": r, "roll": roll_detail, "grew": False,
            "gain": 0, "skill_after": s, "seed": seed,
        }
    if s >= GROWTH_CAP:
        return {
            "skill_before": s, "marked": True, "eligible": False,
            "rolled": r, "roll": roll_detail, "grew": False,
            "gain": 0, "skill_after": s, "seed": seed,
            "reason": "at_cap",
        }
    grew = r > s
    gain = 0
    if grew:
        gain_seed = (seed + 1) if seed is not None else None
        gain = dice_mod.roll_die(10, seed=gain_seed)["total"]
    after = min(GROWTH_CAP, s + gain)
    return {
        "skill_before": s, "marked": True, "eligible": True,
        "rolled": r, "roll": roll_detail, "grew": grew,
        "gain": gain, "skill_after": after, "seed": seed,
    }


def growth_batch(
    entries: Sequence[Mapping[str, Any]],
    seed: int | None = None,
) -> list[dict]:
    """Resolve many growth entries with stable seed derivation (seed+i)."""
    if not isinstance(entries, (list, tuple)):
        raise TypeError("entries must be a list/tuple")
    out: list[dict] = []
    for i, e in enumerate(entries):
        if not isinstance(e, Mapping):
            raise TypeError(f"entries[{i}] must be a mapping")
        if "skill" not in e:
            raise ValueError(f"entries[{i}] missing 'skill'")
        out.append(
            growth_check(
                e["skill"],
                marked=e.get("marked", True),
                rolled=e.get("rolled"),
                seed=(seed + i) if seed is not None else None,
            )
        )
    return out
