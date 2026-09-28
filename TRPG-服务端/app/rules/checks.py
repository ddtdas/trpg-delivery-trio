"""TRPG CoC7 check kernel (MIT).

Pure functions, no I/O, no global state. Python 3.12 compatible.

CoC 7th-edition conventions implemented:
- Success tiers from skill S: extreme <= floor(S/5), hard <= floor(S/2),
  regular <= S. Thresholds floor at 1 (a 1 always has a tier to beat).
- Critical success: rolled == 1 (always, even at skill 0).
- Fumble: skill >= 50 -> rolled == 100 only;
  skill < 50 -> rolled >= 96. (01 can never fumble.)
- Level order: fumble < fail < success < hard < extreme < critical.
- Difficulty gating: hard/extreme checks require the roll to beat the
  narrowed threshold (regular tier is a failure under hard+ gating).
- Opposed rolls: compare levels first, then higher skill, then lower roll.

Self-made function registry (no eval/exec):
- YAML configs may only reference ``{fn, args}`` pairs. ``resolve_derived``
  dispatches ``fn`` through the local ``REGISTRY`` dict; unknown names or
  non-dict args raise. No string expressions are ever evaluated.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from app.rules import dice as dice_mod

DIFFICULTIES = ("regular", "hard", "extreme")
LEVELS = ("fumble", "fail", "success", "hard", "extreme", "critical")
_LEVEL_RANK = {name: i for i, name in enumerate(LEVELS)}

__all__ = [
    "DIFFICULTIES",
    "LEVELS",
    "REGISTRY",
    "thresholds",
    "grade",
    "resolve_check",
    "opposed_check",
    "resolve_derived",
    "register",
]


def _check_skill(skill: Any) -> int:
    if isinstance(skill, bool) or not isinstance(skill, int):
        raise TypeError(f"skill must be int 0..100, got {type(skill).__name__}")
    if not 0 <= skill <= 100:
        raise ValueError(f"skill must be 0..100, got {skill}")
    return skill


def _check_roll(rolled: Any) -> int:
    if isinstance(rolled, bool) or not isinstance(rolled, int):
        raise TypeError(f"rolled must be int 1..100, got {type(rolled).__name__}")
    if not 1 <= rolled <= 100:
        raise ValueError(f"rolled must be 1..100, got {rolled}")
    return rolled


def thresholds(skill: int) -> dict:
    """Return {regular, hard, extreme} thresholds for a skill value."""
    s = _check_skill(skill)
    return {"regular": s, "hard": s // 2, "extreme": s // 5}


def grade(skill: int, rolled: int) -> str:
    """Grade one raw (skill, rolled) pair -> level name.

    Order of tests: critical (01) first, then fumble, then tiers.
    """
    s = _check_skill(skill)
    r = _check_roll(rolled)
    if r == 1:
        return "critical"
    if s >= 50:
        if r == 100:
            return "fumble"
    else:
        if r >= 96:
            return "fumble"
    th = thresholds(s)
    if r <= th["extreme"] and th["extreme"] >= 1:
        return "extreme"
    if r <= th["hard"] and th["hard"] >= 1:
        return "hard"
    if r <= th["regular"] and th["regular"] >= 1:
        return "success"
    # skill 0: only 01 crits (handled above); everything else fails
    # (96+ already returned fumble for skill<50).
    return "fail"


def resolve_check(
    skill: int,
    rolled: int | None = None,
    difficulty: str = "regular",
    bonus: int = 0,
    penalty: int = 0,
    seed: int | None = None,
) -> dict:
    """Resolve one CoC check deterministically.

    - ``skill``: 0..100 target value already looked up from the card.
    - ``rolled``: explicit d100 face (1..100). If None, a d100 is rolled
      with bonus/penalty dice honoured (seed-injectable).
    - ``difficulty``: regular | hard | extreme — the required tier.
    - ``bonus``/``penalty``: only used when rolling (must be >= 0 and
      not both non-zero).
    - Returns a JSON-serializable dict with roll detail, thresholds,
      level, success bool, and seed. Never raises on game outcomes —
      only on illegal inputs (TypeError/ValueError).
    """
    s = _check_skill(skill)
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"difficulty must be one of {DIFFICULTIES}, got {difficulty!r}")
    for name, val in (("bonus", bonus), ("penalty", penalty)):
        if isinstance(val, bool) or not isinstance(val, int):
            raise TypeError(f"{name} must be int, got {type(val).__name__}")
        if val < 0:
            raise ValueError(f"{name} must be >= 0, got {val}")
    if bonus > 0 and penalty > 0:
        raise ValueError("bonus and penalty must not both be non-zero")
    if rolled is not None:
        r = _check_roll(rolled)
        roll_detail: dict = {"die": "d100", "total": r, "mode": "explicit", "seed": seed}
    else:
        d = dice_mod.roll_bonus_penalty(bonus=bonus, penalty=penalty, seed=seed)
        r = d["total"]
        roll_detail = d
    level = grade(s, r)
    required = {"regular": "success", "hard": "hard", "extreme": "extreme"}[difficulty]
    success = _LEVEL_RANK[level] >= _LEVEL_RANK[required]
    return {
        "skill": s,
        "rolled": r,
        "roll": roll_detail,
        "thresholds": thresholds(s),
        "difficulty": difficulty,
        "level": level,
        "success": success,
        "bonus": bonus,
        "penalty": penalty,
        "seed": seed,
    }


def opposed_check(
    skill_a: int,
    rolled_a: int,
    skill_b: int,
    rolled_b: int,
) -> dict:
    """Resolve an opposed contest between two (skill, roll) pairs.

    Winner rule (CoC7 table convention):
    1. Higher success level wins (critical > extreme > hard > success >
       fail > fumble).
    2. Tie on level: higher skill wins.
    3. Still tied: lower roll wins; exact tie -> draw.
    Fumble vs fumble and fail vs fail still produce a winner by the same
    tie-breaks unless fully identical (then draw).
    """
    sa = _check_skill(skill_a)
    sb = _check_skill(skill_b)
    ra = _check_roll(rolled_a)
    rb = _check_roll(rolled_b)
    la = grade(sa, ra)
    lb = grade(sb, rb)
    if _LEVEL_RANK[la] != _LEVEL_RANK[lb]:
        winner = "A" if _LEVEL_RANK[la] > _LEVEL_RANK[lb] else "B"
        reason = "level"
    elif sa != sb:
        winner = "A" if sa > sb else "B"
        reason = "skill"
    elif ra != rb:
        winner = "A" if ra < rb else "B"
        reason = "roll"
    else:
        winner = "draw"
        reason = "identical"
    return {
        "a": {"skill": sa, "rolled": ra, "level": la},
        "b": {"skill": sb, "rolled": rb, "level": lb},
        "winner": winner,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Self-made derived-stat registry: YAML configures {fn, args} only.
# ---------------------------------------------------------------------------

def _fn_half(args: Mapping[str, Any], card: Mapping[str, Any]) -> int:
    base = _lookup_number(args, card, "of")
    return base // 2


def _fn_fifth(args: Mapping[str, Any], card: Mapping[str, Any]) -> int:
    base = _lookup_number(args, card, "of")
    return base // 5


def _fn_add(args: Mapping[str, Any], card: Mapping[str, Any]) -> int:
    vals = args.get("values")
    if not isinstance(vals, list) or not vals:
        raise ValueError("add.args.values must be a non-empty list")
    total = 0
    for v in vals:
        total += _resolve_operand(v, card)
    return total


def _fn_skill_threshold(args: Mapping[str, Any], card: Mapping[str, Any]) -> dict:
    skill = _lookup_number(args, card, "skill")
    return thresholds(skill)


def _lookup_number(args: Mapping[str, Any], card: Mapping[str, Any], key: str) -> int:
    if not isinstance(args, Mapping):
        raise TypeError(f"derived args must be a mapping, got {type(args).__name__}")
    if key not in args:
        raise ValueError(f"derived args missing key: {key!r}")
    return _resolve_operand(args[key], card)


def _resolve_operand(operand: Any, card: Mapping[str, Any]) -> int:
    if isinstance(operand, bool):
        raise TypeError("derived operand must be int or $ref string")
    if isinstance(operand, int):
        return operand
    if isinstance(operand, str):
        if not operand.startswith("$"):
            raise ValueError(
                f"derived operand string must be a $ref (got {operand!r}); "
                "raw expressions are forbidden"
            )
        ref = operand[1:]
        data = card.get("skills", {}) if isinstance(card, Mapping) else {}
        attrs = card.get("attrs", {}) if isinstance(card, Mapping) else {}
        merged = {**attrs, **data} if isinstance(data, dict) and isinstance(attrs, dict) else {}
        if ref not in merged:
            raise ValueError(f"derived $ref not found on card: {ref!r}")
        val = merged[ref]
        if isinstance(val, bool) or not isinstance(val, int):
            raise TypeError(f"derived $ref {ref!r} must be int, got {type(val).__name__}")
        return val
    raise TypeError(f"derived operand must be int or $ref, got {operand!r}")


REGISTRY: dict[str, Callable[..., Any]] = {
    "half": _fn_half,
    "fifth": _fn_fifth,
    "add": _fn_add,
    "skill_threshold": _fn_skill_threshold,
}


def register(name: str, fn: Callable[..., Any]) -> None:
    """Register a custom derived-stat function (code-side only, never YAML)."""
    if not isinstance(name, str) or not name:
        raise ValueError("registry name must be a non-empty string")
    if not callable(fn):
        raise TypeError("registry value must be callable")
    if name in REGISTRY:
        raise ValueError(f"registry name already registered: {name!r}")
    REGISTRY[name] = fn


def resolve_derived(spec: Mapping[str, Any], card: Mapping[str, Any]) -> Any:
    """Resolve one ``{fn, args}`` derived-stat spec against a card.

    Only names present in REGISTRY dispatch; anything else (including
    attempts to sneak in code strings) raises. ``args`` must be a mapping.
    """
    if not isinstance(spec, Mapping):
        raise TypeError(f"derived spec must be a mapping, got {type(spec).__name__}")
    if set(spec.keys()) != {"fn", "args"}:
        raise ValueError(f"derived spec must be exactly {{fn, args}}, got keys {sorted(spec.keys())}")
    fn_name = spec["fn"]
    args = spec["args"]
    if not isinstance(fn_name, str):
        raise TypeError("derived spec fn must be a string")
    if fn_name not in REGISTRY:
        raise ValueError(f"unknown derived fn: {fn_name!r}")
    if not isinstance(args, Mapping):
        raise TypeError("derived spec args must be a mapping")
    if not isinstance(card, Mapping):
        raise TypeError("card must be a mapping")
    return REGISTRY[fn_name](dict(args), card)
