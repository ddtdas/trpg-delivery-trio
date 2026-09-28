"""TRPG CoC7 combat kernel (MIT).

Pure functions only: initiative ordering, attack/dodge/counterattack
resolution, damage application. No I/O, no global state.
Python 3.12 compatible.

All inputs are plain ints validated at the boundary; illegal values raise
TypeError/ValueError. Outcomes never raise — they are data.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.rules import checks as checks_mod
from app.rules import dice as dice_mod

__all__ = [
    "roll_initiative",
    "resolve_attack",
    "apply_damage",
    "resolve_counterattack",
]


def _check_pct(name: str, value: Any, lo: int = 0, hi: int = 100) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int {lo}..{hi}, got {type(value).__name__}")
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be {lo}..{hi}, got {value}")
    return value


def _check_nonneg(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int >= 0, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def roll_initiative(
    combatants: Sequence[Mapping[str, Any]],
    seed: int | None = None,
) -> list[dict]:
    """Order combatants by DEX desc, tie-broken by seeded d100.

    Each combatant: ``{"id": str, "dex": int 1..100}``. Ties on DEX roll
    one d100 each from a derived stream (``seed+i``) so an explicit seed
    reproduces the full order. Higher tie-roll acts first; residual ties
    break by id ascending (fully deterministic).
    """
    if not isinstance(combatants, (list, tuple)) or not combatants:
        raise ValueError("combatants must be a non-empty list")
    rows: list[dict] = []
    for i, c in enumerate(combatants):
        if not isinstance(c, Mapping):
            raise TypeError(f"combatant[{i}] must be a mapping")
        cid = c.get("id")
        if not isinstance(cid, str) or not cid:
            raise ValueError(f"combatant[{i}].id must be a non-empty string")
        dex = c.get("dex")
        _check_pct(f"combatant[{i}].dex", dex, 1, 100)
        tie_seed = (seed + i) if seed is not None else None
        tie = dice_mod.roll_d100(seed=tie_seed)["total"]
        rows.append({"id": cid, "dex": dex, "tie_roll": tie})
    rows.sort(key=lambda r: (-r["dex"], -r["tie_roll"], r["id"]))
    return [{"order": n + 1, **r} for n, r in enumerate(rows)]


def resolve_attack(
    attack_skill: int,
    attack_roll: int | None = None,
    dodge_skill: int | None = None,
    dodge_roll: int | None = None,
    damage_formula: str = "1d6",
    difficulty: str = "regular",
    seed: int | None = None,
) -> dict:
    """Resolve one attack vs optional dodge.

    Steps:
    1. Attack check via :func:`checks.resolve_check`.
    2. If dodge given: opposed contest decides hit/miss. Attacker wins
       ties-or-better on level (needs level >= defender level AND attack
       itself successful); defender winning the contest dodges.
       Fumbled attacks always miss; fumbled dodges never avoid a
       successful attack.
    3. On hit: roll ``damage_formula`` (seed derived +1 from attack seed
       for reproducibility); on miss/clean-dodge: no damage.
    Returns a JSON-serializable dict.
    """
    atk = checks_mod.resolve_check(attack_skill, rolled=attack_roll, difficulty=difficulty, seed=seed)
    atk_level = atk["level"]
    atk_ok = bool(atk["success"])
    dodge_detail: dict | None = None
    if dodge_skill is not None or dodge_roll is not None:
        if dodge_skill is None or dodge_roll is None:
            raise ValueError("dodge_skill and dodge_roll must be given together")
        _check_pct("dodge_skill", dodge_skill)
        dodge_detail = checks_mod.resolve_check(dodge_skill, rolled=dodge_roll, seed=seed)
    if atk_level == "fumble":
        hit, outcome = False, "fumble"
    elif not atk_ok:
        hit, outcome = False, "miss"
    elif dodge_detail is not None:
        contest = checks_mod.opposed_check(attack_skill, atk["rolled"], dodge_skill, dodge_detail["rolled"])
        d_level = dodge_detail["level"]
        if d_level == "fumble":
            hit, outcome = True, "hit"  # defender fumbled the dodge
        elif contest["winner"] == "B" and d_level not in ("fail", "fumble"):
            hit, outcome = False, "dodged"
        elif contest["winner"] == "draw":
            # Identical contests: a successful attack still lands
            # unless the dodge itself succeeded at equal level.
            hit = d_level in ("fail", "fumble")
            outcome = "hit" if hit else "dodged"
        else:
            # Attacker wins contest (or wins/keeps ties with success)
            hit = contest["winner"] == "A" or (
                _rank(atk_level) >= _rank(d_level) and atk_ok and d_level in ("fail", "fumble")
            )
            outcome = "hit" if hit else "dodged"
    else:
        hit, outcome = True, "hit"
    damage: dict | None = None
    if hit:
        dmg_seed = (seed + 1) if seed is not None else None
        damage = dice_mod.roll_formula(damage_formula, seed=dmg_seed)
    return {
        "attack": atk,
        "dodge": dodge_detail,
        "hit": hit,
        "outcome": outcome,
        "damage": damage,
    }


def _rank(level: str) -> int:
    return {"fumble": 0, "fail": 1, "success": 2, "hard": 3, "extreme": 4, "critical": 5}[level]


def apply_damage(current_hp: int, damage: int, armor: int = 0) -> dict:
    """Apply armor then HP loss. HP floors at 0; returns detail dict."""
    _check_nonneg("current_hp", current_hp)
    _check_nonneg("damage", damage)
    _check_nonneg("armor", armor)
    absorbed = min(armor, damage)
    taken = damage - absorbed
    remaining = max(0, current_hp - taken)
    return {
        "current_hp": current_hp,
        "damage": damage,
        "armor": armor,
        "absorbed": absorbed,
        "taken": taken,
        "remaining_hp": remaining,
        "down": remaining == 0,
        "major_wound": taken * 2 >= max(1, current_hp),
    }


def resolve_counterattack(
    first_skill: int,
    first_roll: int,
    second_skill: int,
    second_roll: int,
    first_damage: str = "1d6",
    second_damage: str = "1d6",
    seed: int | None = None,
) -> dict:
    """Fighting-back / counterattack: opposed contest, winner deals damage.

    Draws deal no damage. Damage seeds derive from ``seed`` (+1/+2) so a
    seeded counterattack is fully reproducible.
    """
    _check_pct("first_skill", first_skill)
    _check_pct("second_skill", second_skill)
    contest = checks_mod.opposed_check(first_skill, first_roll, second_skill, second_roll)
    result: dict = {"contest": contest, "winner": contest["winner"], "damage": None}
    if contest["winner"] == "A":
        result["damage"] = dice_mod.roll_formula(
            first_damage, seed=(seed + 1) if seed is not None else None
        )
    elif contest["winner"] == "B":
        result["damage"] = dice_mod.roll_formula(
            second_damage, seed=(seed + 2) if seed is not None else None
        )
    return result
