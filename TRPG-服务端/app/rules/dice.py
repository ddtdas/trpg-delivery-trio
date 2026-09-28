"""TRPG dice kernel (MIT).

Pure functions, explicit seed injection, no global state.

Conventions:
- ``seed``: optional int/explicit value passed by the caller. When given,
  results are fully reproducible (same seed -> same output). When None,
  randomness comes from ``random.Random()`` (OS-seeded entropy).
- ``rng``: optional ``random.Random``-compatible object the caller may inject
  (used mostly by tests). ``seed`` takes precedence over ``rng``.
  ``rng`` must expose ``randint(a, b)``.
- All results are plain dicts of JSON-serializable values.

CoC7 d100 conventions:
- d100 rolls a uniform integer in [1, 100], modelled as two d10 dice
  (tens in 0..90 + ones in 1..10, with 00+0 read as 100). We expose the
  raw ``tens``/``ones`` components for auditability, plus the ``total``.
- Bonus/penalty dice: roll 1 + n extra tens dice, keep the best (bonus:
  lowest tens, penalty: highest tens). Result includes every tens die so
  the outcome is auditable.
"""
from __future__ import annotations

import random
from typing import Any, Mapping, Sequence


def _make_rng(seed: int | None, rng: Any | None) -> random.Random | Any:
    if seed is not None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(f"seed must be int or None, got {type(seed).__name__}")
        return random.Random(seed)
    if rng is not None:
        if not hasattr(rng, "randint"):
            raise TypeError("rng must expose randint(a, b)")
        return rng
    return random.Random()


def _check_die(sides: int) -> None:
    if isinstance(sides, bool) or not isinstance(sides, int):
        raise TypeError(f"sides must be int, got {type(sides).__name__}")
    if not 2 <= sides <= 1000:
        raise ValueError(f"sides must be 2..1000, got {sides}")


def _check_count(count: int) -> None:
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(f"count must be int, got {type(count).__name__}")
    if not 1 <= count <= 100:
        raise ValueError(f"count must be 1..100, got {count}")


def roll_die(sides: int, seed: int | None = None, rng: Any | None = None) -> dict:
    """Roll one die with ``sides`` faces -> value in [1, sides]."""
    _check_die(sides)
    r = _make_rng(seed, rng)
    value = r.randint(1, sides)
    return {"sides": sides, "total": value, "rolls": [value], "seed": seed}


def roll_dice(
    count: int,
    sides: int,
    seed: int | None = None,
    rng: Any | None = None,
    modifier: int = 0,
) -> dict:
    """Roll ``count`` d``sides`` plus an integer modifier."""
    _check_count(count)
    _check_die(sides)
    if isinstance(modifier, bool) or not isinstance(modifier, int):
        raise TypeError(f"modifier must be int, got {type(modifier).__name__}")
    r = _make_rng(seed, rng)
    rolls = [r.randint(1, sides) for _ in range(count)]
    return {
        "count": count,
        "sides": sides,
        "rolls": rolls,
        "modifier": modifier,
        "total": sum(rolls) + modifier,
        "seed": seed,
    }


def roll_d100(seed: int | None = None, rng: Any | None = None) -> dict:
    """Roll d100 -> total in [1, 100] with tens/ones audit components."""
    r = _make_rng(seed, rng)
    tens = r.randint(0, 9) * 10  # 0, 10, ..., 90
    ones = r.randint(1, 10)  # 1..10, where 10 on the ones die reads as 0
    total = tens + ones
    if total > 100:  # tens=90 + ones=10 -> 100 by construction; guard anyway
        total = 100
    # Canonical CoC reading: 00 + 0 == 100.
    if tens == 0 and ones == 10:
        total = 100
    return {"die": "d100", "tens": tens, "ones": ones, "total": total, "seed": seed}


def roll_d20(seed: int | None = None, rng: Any | None = None) -> dict:
    """Roll d20 -> total in [1, 20]."""
    out = roll_die(20, seed=seed, rng=rng)
    return {"die": "d20", "total": out["total"], "rolls": out["rolls"], "seed": seed}


def roll_3d6(seed: int | None = None, rng: Any | None = None) -> dict:
    """Roll 3d6 -> total in [3, 18] (characteristic generation)."""
    out = roll_dice(3, 6, seed=seed, rng=rng)
    return {"die": "3d6", "rolls": out["rolls"], "total": out["total"], "seed": seed}


def roll_bonus_penalty(
    bonus: int = 0,
    penalty: int = 0,
    seed: int | None = None,
    rng: Any | None = None,
) -> dict:
    """CoC7 bonus/penalty d100.

    - ``bonus`` / ``penalty``: non-negative counts of extra tens dice.
      They must not both be non-zero (they cancel in table play; the
      caller must net them first).
    - Bonus keeps the lowest tens die; penalty keeps the highest.
    - Returns every tens die + the ones die + chosen total.
    """
    for name, val in (("bonus", bonus), ("penalty", penalty)):
        if isinstance(val, bool) or not isinstance(val, int):
            raise TypeError(f"{name} must be int, got {type(val).__name__}")
        if val < 0:
            raise ValueError(f"{name} must be >= 0, got {val}")
    if bonus > 0 and penalty > 0:
        raise ValueError("bonus and penalty must not both be non-zero (net them first)")
    r = _make_rng(seed, rng)
    ones = r.randint(1, 10)
    tens_dice = [r.randint(0, 9) * 10 for _ in range(1 + bonus + penalty)]
    if bonus > 0:
        chosen_tens = min(tens_dice)
    elif penalty > 0:
        chosen_tens = max(tens_dice)
    else:
        chosen_tens = tens_dice[0]
    total = chosen_tens + ones
    if total > 100:
        total = 100
    if chosen_tens == 0 and ones == 10:
        total = 100
    return {
        "die": "d100",
        "mode": "bonus" if bonus else ("penalty" if penalty else "normal"),
        "bonus": bonus,
        "penalty": penalty,
        "tens_dice": tens_dice,
        "chosen_tens": chosen_tens,
        "ones": ones,
        "total": total,
        "seed": seed,
    }


def roll_formula(
    formula: str, seed: int | None = None, rng: Any | None = None
) -> dict:
    """Roll a small NdM(+K) formula, e.g. '1d6', '2d8+3', 'd20', '3d6-1'.

    Allowed grammar (nothing else — no DSL interpreter):
    ``[count] 'd' sides [ ('+'|'-') modifier ]`` with
    1 <= count <= 100, 2 <= sides <= 1000, |modifier| <= 10000.
    Plain integers like '5' are treated as fixed constants.
    Whitespace is ignored. Anything else raises ValueError.
    """
    if not isinstance(formula, str):
        raise TypeError(f"formula must be str, got {type(formula).__name__}")
    import re

    text = formula.strip().replace(" ", "")
    if re.fullmatch(r"[+-]?\d+", text or ""):
        return {
            "formula": formula,
            "rolls": [],
            "modifier": int(text),
            "total": int(text),
            "seed": seed,
        }
    m = re.fullmatch(r"(\d*)[dD](\d+)([+-]\d+)?", text or "")
    if not m:
        raise ValueError(f"invalid dice formula: {formula!r}")
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    modifier = int(m.group(3)) if m.group(3) else 0
    if not 1 <= count <= 100:
        raise ValueError(f"count out of range 1..100: {count}")
    if not 2 <= sides <= 1000:
        raise ValueError(f"sides out of range 2..1000: {sides}")
    if abs(modifier) > 10000:
        raise ValueError(f"modifier out of range: {modifier}")
    out = roll_dice(count, sides, seed=seed, rng=rng, modifier=modifier)
    out["formula"] = formula
    return out


def roll_many(
    specs: Sequence[Mapping[str, Any]],
    seed: int | None = None,
    rng: Any | None = None,
) -> list[dict]:
    """Roll several specs deterministically from one stream.

    Each spec: ``{"sides": int}`` or ``{"count","sides","modifier?"}`` or
    ``{"formula": str}``. With an explicit ``seed``, child rolls derive
    sub-seeds ``seed+i`` so the batch is reproducible AND order-stable.
    Without a seed, all rolls share the one injected/auto RNG stream.
    """
    if not isinstance(specs, (list, tuple)):
        raise TypeError("specs must be a list/tuple of mappings")
    results: list[dict] = []
    shared = None if seed is not None else _make_rng(None, rng)
    for i, spec in enumerate(specs):
        if not isinstance(spec, Mapping):
            raise TypeError(f"spec[{i}] must be a mapping")
        if "formula" in spec:
            results.append(roll_formula(spec["formula"], seed=(seed + i) if seed is not None else None, rng=shared))
        elif "sides" in spec and "count" not in spec:
            results.append(roll_die(spec["sides"], seed=(seed + i) if seed is not None else None, rng=shared))
        elif "sides" in spec:
            results.append(
                roll_dice(
                    spec.get("count", 1),
                    spec["sides"],
                    seed=(seed + i) if seed is not None else None,
                    rng=shared,
                    modifier=spec.get("modifier", 0),
                )
            )
        else:
            raise ValueError(f"spec[{i}] needs 'formula' or 'sides': {dict(spec)!r}")
    return results
