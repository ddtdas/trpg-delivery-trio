"""TRPG ruleset-aware resolution engine (MIT, additive layer).

app/rules/checks.py is the CoC 7th-edition kernel: one ruleset, one
resolution model, hard-coded. R23 needs one engine that can host several
rulesets, so this module dispatches on the model the rulepack declares:

    coc_percentile  CoC 7e -- d100 <= target, hard/extreme tiers,
                             crit on 01, fumble 100 / 96+
    coc_classic     CoC 6e -- d100 <= target, special <= target/5,
                             crit on 01-05, fumble 96-100, no tiers
                             (the Keeper applies a flat modifier instead)
    d20_dc          D&D 5e -- d20 + skill bonus vs DC, nat 20 crit,
                             nat 1 fumble, advantage/disadvantage

The three models deliberately emit DIFFERENT field sets: that is what
makes "same module opened as coc7 vs dnd5e" observable at runtime
instead of a cosmetic label swap.

Nothing here mutates the card or the rulepack. Illegal input raises
ResolutionError with a stable .code; game outcomes are data.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.rules import dice as dice_mod
from app.rules.formulas import resolve_formulas
from app.rules.rulepack_schema import RESOLUTION_MODELS

__all__ = [
    "ResolutionError",
    "resolution_model",
    "check_difficulties",
    "resolve_check",
    "resolve_attack",
    "apply_damage",
    "growth_check",
    "opening_fields",
]


class ResolutionError(ValueError):
    """Illegal resolution input. Carries a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__("%s: %s" % (code, message))

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self)}


# --------------------------------------------------------------------------
# shared lookups
# --------------------------------------------------------------------------

def _rp(rulepack: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(rulepack, Mapping):
        raise ResolutionError(
            "RULEPACK_ROOT_INVALID", "rulepack must be a mapping, got %s" % type(rulepack).__name__
        )
    return rulepack


def resolution_model(rulepack: Mapping[str, Any]) -> str:
    """Return the declared resolution model (v1 files default to coc_percentile)."""
    rp = _rp(rulepack)
    block = rp.get("ruleset") or {}
    model = block.get("resolution_model") if isinstance(block, Mapping) else None
    if model is None:
        model = (rp.get("resolution") or {}).get("model") if isinstance(rp.get("resolution"), Mapping) else None
    if model is None:
        # v1 rulepacks predate the declaration; they are CoC7 by construction.
        return "coc_percentile"
    if model not in RESOLUTION_MODELS:
        raise ResolutionError(
            "RULEPACK_RESOLUTION_MODEL_UNKNOWN",
            "unknown resolution model %r (known: %s)" % (model, ", ".join(RESOLUTION_MODELS)),
        )
    return str(model)


def _resolution(rulepack: Mapping[str, Any]) -> Mapping[str, Any]:
    block = _rp(rulepack).get("resolution")
    if not isinstance(block, Mapping):
        raise ResolutionError("RULEPACK_FIELD_MISSING", "rulepack.resolution must be a mapping")
    return block


def check_difficulties(rulepack: Mapping[str, Any]) -> tuple[str, ...]:
    """Difficulty labels this ruleset accepts."""
    block = _resolution(rulepack)
    names = block.get("difficulties")
    if isinstance(names, (list, tuple)) and names:
        return tuple(str(n) for n in names)
    checks = _rp(rulepack).get("checks") or {}
    names = checks.get("difficulties") if isinstance(checks, Mapping) else None
    if isinstance(names, (list, tuple)) and names:
        return tuple(str(n) for n in names)
    return ("regular",)


def resolved_card(rulepack: Mapping[str, Any], card: Mapping[str, Any]) -> dict:
    """Card view = attrs + skills + every rulepack formula resolved.

    Formulas act as derived sheet fields, so a d20 ruleset can expose
    str_mod / prof_bonus / hp_max even though the player only entered the
    raw ability scores.
    """
    if not isinstance(card, Mapping):
        raise ResolutionError("RULEPACK_CARD_INVALID", "card must be a mapping, got %s" % type(card).__name__)
    attrs = card.get("attrs") if isinstance(card.get("attrs"), Mapping) else {}
    skills = card.get("skills") if isinstance(card.get("skills"), Mapping) else {}
    # Precedence: a rulepack formula is a DERIVED DEFAULT; anything the
    # player actually put on the card wins. (CoC6 derives dodge = DEX x 2,
    # but a card that spent points on dodge keeps its own number.)
    view: dict[str, Any] = dict(resolve_formulas(rulepack, card))
    view.update(attrs)
    view.update(skills)
    return view


def _target_value(rulepack: Mapping[str, Any], card: Mapping[str, Any], target: str) -> int:
    if not isinstance(target, str) or not target:
        raise ResolutionError("RULEPACK_TARGET_INVALID", "target must be a non-empty string")
    view = resolved_card(rulepack, card)
    if target in view:
        value = view[target]
    else:
        # A character sheet omits skills it never put points into; the
        # rulepack's own skill table supplies the base value for those.
        base_table = rulepack.get("skills")
        if isinstance(base_table, Mapping) and target in base_table:
            value = base_table[target]
        else:
            raise ResolutionError(
                "RULEPACK_TARGET_UNKNOWN",
                "target %r is not on the card nor derived by the rulepack (known: %s)"
                % (target, ", ".join(sorted(str(k) for k in view)[:24])),
            )
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResolutionError(
            "RULEPACK_TARGET_INVALID",
            "target %r must resolve to int, got %s" % (target, type(value).__name__),
        )
    return value


def _difficulty(rulepack: Mapping[str, Any], difficulty: str | None) -> str:
    allowed = check_difficulties(rulepack)
    if difficulty is None:
        return allowed[0]
    if difficulty not in allowed:
        raise ResolutionError(
            "RULEPACK_DIFFICULTY_UNKNOWN",
            "difficulty %r not declared by this ruleset (declared: %s)"
            % (difficulty, ", ".join(allowed)),
        )
    return difficulty


def _roll_d100(rolled: int | None, seed: int | None, mode: str) -> dict:
    if rolled is not None:
        if isinstance(rolled, bool) or not isinstance(rolled, int) or not 1 <= rolled <= 100:
            raise ResolutionError("RULEPACK_ROLL_INVALID", "rolled must be int 1..100, got %r" % (rolled,))
        return {"die": "d100", "total": rolled, "mode": mode, "seed": seed}
    out = dice_mod.roll_d100(seed=seed)
    out["mode"] = mode
    return out


def _roll_d20(rolled: int | None, seed: int | None, advantage: int, disadvantage: int) -> dict:
    if advantage and disadvantage:
        raise ResolutionError(
            "RULEPACK_ROLL_INVALID", "advantage and disadvantage cancel; pass only one"
        )
    if rolled is not None:
        if isinstance(rolled, bool) or not isinstance(rolled, int) or not 1 <= rolled <= 20:
            raise ResolutionError("RULEPACK_ROLL_INVALID", "rolled must be int 1..20, got %r" % (rolled,))
        return {"die": "d20", "rolls": [rolled], "total": rolled, "mode": "explicit", "seed": seed}
    if advantage or disadvantage:
        count = 2 + max(advantage, disadvantage) - 1
        rolls = [dice_mod.roll_die(20, seed=(seed + i) if seed is not None else None)["total"] for i in range(count)]
        keep = max(rolls) if advantage else min(rolls)
        return {
            "die": "d20",
            "rolls": rolls,
            "kept": keep,
            "total": keep,
            "mode": "advantage" if advantage else "disadvantage",
            "seed": seed,
        }
    out = dice_mod.roll_d20(seed=seed)
    out["mode"] = "normal"
    return out


# --------------------------------------------------------------------------
# per-model check resolution
# --------------------------------------------------------------------------

def _check_coc7(rulepack, card, target, difficulty, rolled, seed) -> dict:
    block = _resolution(rulepack)
    diff = _difficulty(rulepack, difficulty)
    skill = _target_value(rulepack, card, target)
    if not 0 <= skill <= 100:
        raise ResolutionError(
            "RULEPACK_TARGET_INVALID", "target %r value %d out of 0..100" % (target, skill)
        )
    roll = _roll_d100(rolled, seed, diff)
    r = roll["total"]
    thresholds = {"regular": skill, "hard": skill // 2, "extreme": skill // 5}
    crit_rule = str(block.get("critical", "roll_eq_1"))
    skilled_threshold = int(block.get("fumble_skilled_threshold", 50))
    if r == 1:
        level = "critical"
    elif (skill >= skilled_threshold and r == 100) or (skill < skilled_threshold and r >= 96):
        level = "fumble"
    elif r <= thresholds["extreme"] and thresholds["extreme"] >= 1:
        level = "extreme"
    elif r <= thresholds["hard"] and thresholds["hard"] >= 1:
        level = "hard"
    elif r <= thresholds["regular"] and thresholds["regular"] >= 1:
        level = "success"
    else:
        level = "fail"
    rank = {"fumble": 0, "fail": 1, "success": 2, "hard": 3, "extreme": 4, "critical": 5}
    required = {"regular": "success", "hard": "hard", "extreme": "extreme"}[diff]
    return {
        "model": "coc_percentile",
        "target": target,
        "target_value": skill,
        "rolled": r,
        "roll": roll,
        "thresholds": thresholds,
        "difficulty": diff,
        "level": level,
        "success": rank[level] >= rank[required],
        "critical_rule": crit_rule,
    }


def _check_coc6(rulepack, card, target, difficulty, modifier, rolled, seed) -> dict:
    block = _resolution(rulepack)
    diff = _difficulty(rulepack, difficulty)
    base = _target_value(rulepack, card, target)
    effective = max(0, min(99, base + modifier))
    roll = _roll_d100(rolled, seed, diff)
    r = roll["total"]
    special_div = int(block.get("special_divisor", 5))
    crit_max = int(block.get("critical_max", 5))
    fumble_min = int(block.get("fumble_min", 96))
    if r <= crit_max:
        level = "critical"
    elif r >= fumble_min:
        level = "fumble"
    elif r <= effective // special_div and effective >= special_div:
        level = "special"
    elif r <= effective and effective >= 1:
        level = "success"
    else:
        level = "fail"
    return {
        "model": "coc_classic",
        "target": target,
        "target_value": base,
        "effective_target": effective,
        "modifier": modifier,
        "rolled": r,
        "roll": roll,
        "special_threshold": effective // special_div,
        "critical_max": crit_max,
        "fumble_min": fumble_min,
        "difficulty": diff,
        "level": level,
        "success": level in ("success", "special", "critical"),
    }


def _check_d20(rulepack, card, target, difficulty, advantage, disadvantage, rolled, seed) -> dict:
    block = _resolution(rulepack)
    diff = _difficulty(rulepack, difficulty)
    dc_table = block.get("dc_table") or {}
    if not isinstance(dc_table, Mapping) or diff not in dc_table:
        raise ResolutionError(
            "RULEPACK_DIFFICULTY_UNKNOWN", "no DC declared for difficulty %r" % (diff,)
        )
    dc = int(dc_table[diff])
    bonus = _target_value(rulepack, card, target)
    roll = _roll_d20(rolled, seed, advantage, disadvantage)
    natural = roll["total"]
    total = natural + bonus
    crit_min = int(block.get("critical_natural", 20))
    fumble_max = int(block.get("fumble_natural", 1))
    critical = natural >= crit_min
    fumble = natural <= fumble_max
    success = critical or (not fumble and total >= dc)
    return {
        "model": "d20_dc",
        "target": target,
        "target_value": bonus,
        "roll": roll,
        "natural": natural,
        "total": total,
        "dc": dc,
        "difficulty": diff,
        "success": success,
        "critical": critical,
        "fumble": fumble,
        "margin": total - dc,
    }


def resolve_check(
    rulepack: Mapping[str, Any],
    card: Mapping[str, Any],
    target: str,
    difficulty: str | None = None,
    modifier: int = 0,
    advantage: int = 0,
    disadvantage: int = 0,
    rolled: int | None = None,
    seed: int | None = None,
) -> dict:
    """Resolve one check under the rulepack's declared model."""
    model = resolution_model(rulepack)
    if model == "coc_percentile":
        return _check_coc7(rulepack, card, target, difficulty, rolled, seed)
    if model == "coc_classic":
        return _check_coc6(rulepack, card, target, difficulty, modifier, rolled, seed)
    if model == "d20_dc":
        return _check_d20(rulepack, card, target, difficulty, advantage, disadvantage, rolled, seed)
    raise ResolutionError("RULEPACK_RESOLUTION_MODEL_UNKNOWN", "unhandled model %r" % (model,))


# --------------------------------------------------------------------------
# combat
# --------------------------------------------------------------------------

def resolve_attack(
    rulepack: Mapping[str, Any],
    attacker: Mapping[str, Any],
    defender: Mapping[str, Any] | None = None,
    attack_target: str | None = None,
    defense_target: str | None = None,
    damage_formula: str | None = None,
    rolled: int | None = None,
    defense_rolled: int | None = None,
    seed: int | None = None,
) -> dict:
    """Minimal attack loop for the declared ruleset.

    Percentile rulesets: opposed contest against dodge, damage formula
    plus the ruleset's damage bonus. d20 rulesets: attack total against
    the defender's AC, damage dice plus ability modifier.
    """
    rp = _rp(rulepack)
    model = resolution_model(rp)
    combat = rp.get("combat") or {}
    if not isinstance(combat, Mapping):
        raise ResolutionError("RULEPACK_FIELD_INVALID", "combat must be a mapping")
    formula = damage_formula or str(combat.get("damage_default") or "1d6")

    if model in ("coc_percentile", "coc_classic"):
        atk_name = attack_target or str(combat.get("attack_default") or "fighting_brawl")
        dodge_name = defense_target or str(combat.get("defense_default") or "dodge")
        attack = resolve_check(rp, attacker, atk_name, rolled=rolled, seed=seed)
        dodge = None
        if defender is not None:
            try:
                dodge = resolve_check(rp, defender, dodge_name, rolled=defense_rolled, seed=seed)
            except ResolutionError as exc:
                if exc.code != "RULEPACK_TARGET_UNKNOWN":
                    raise
        hit = bool(attack["success"]) and attack["level"] != "fumble"
        if dodge is not None:
            if dodge["level"] == "fumble":
                hit = hit and True
            elif dodge["success"]:
                hit = False
        damage = None
        if hit:
            dmg_seed = (seed + 1) if seed is not None else None
            damage = dice_mod.roll_formula(formula, seed=dmg_seed)
            bonus = None
            try:
                bonus = resolve_formulas(rp, attacker).get("damage_bonus")
            except Exception:  # noqa: BLE001 -- bonus is optional flavour
                bonus = None
            if bonus and str(bonus) not in ("0", ""):
                damage["damage_bonus"] = bonus
        return {
            "model": model,
            "attack": attack,
            "dodge": dodge,
            "hit": hit,
            "outcome": "hit" if hit else ("fumble" if attack["level"] == "fumble" else "miss"),
            "damage": damage,
        }

    if model == "d20_dc":
        atk_name = attack_target or str(combat.get("attack_default") or "attack")
        attack = resolve_check(rp, attacker, atk_name, difficulty="medium", rolled=rolled, seed=seed)
        ac = None
        if defender is not None:
            ac = resolved_card(rp, defender).get("ac")
            if not isinstance(ac, int):
                raise ResolutionError(
                    "RULEPACK_TARGET_UNKNOWN", "defender has no derivable 'ac' for d20 combat"
                )
        hit = bool(attack["success"])
        if ac is not None:
            hit = attack["critical"] or (not attack["fumble"] and attack["total"] >= ac)
        damage = None
        if hit:
            dmg_seed = (seed + 1) if seed is not None else None
            damage = dice_mod.roll_formula(formula, seed=dmg_seed)
            if attack["critical"]:
                damage["critical"] = True
                damage["total"] = damage["total"] * 2
        return {
            "model": model,
            "attack": attack,
            "target_ac": ac,
            "hit": hit,
            "outcome": "critical" if (hit and attack["critical"]) else ("hit" if hit else "miss"),
            "damage": damage,
        }

    raise ResolutionError("RULEPACK_RESOLUTION_MODEL_UNKNOWN", "unhandled model %r" % (model,))


def apply_damage(rulepack: Mapping[str, Any], current_hp: int, damage: int, armor: int = 0) -> dict:
    """Apply armor then HP loss under the ruleset's combat options."""
    rp = _rp(rulepack)
    for name, value in (("current_hp", current_hp), ("damage", damage), ("armor", armor)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ResolutionError("RULEPACK_FIELD_INVALID", "%s must be int" % name)
        if value < 0:
            raise ResolutionError("RULEPACK_FIELD_INVALID", "%s must be >= 0" % name)
    combat = rp.get("combat") or {}
    armor_block = combat.get("armor") if isinstance(combat, Mapping) else None
    armor_on = True
    if isinstance(armor_block, Mapping):
        armor_on = bool(armor_block.get("enabled", True))
    absorbed = min(armor, damage) if armor_on else 0
    taken = damage - absorbed
    remaining = max(0, current_hp - taken)
    out = {
        "current_hp": current_hp,
        "damage": damage,
        "armor": armor if armor_on else 0,
        "absorbed": absorbed,
        "taken": taken,
        "remaining_hp": remaining,
        "down": remaining == 0,
    }
    major = combat.get("major_wound") if isinstance(combat, Mapping) else None
    if isinstance(major, Mapping) and major.get("enabled"):
        threshold = int(major.get("threshold_divisor", 2))
        out["major_wound"] = taken * threshold >= max(1, current_hp)
    return out


# --------------------------------------------------------------------------
# growth
# --------------------------------------------------------------------------

def growth_check(
    rulepack: Mapping[str, Any],
    skill: int,
    marked: bool = True,
    rolled: int | None = None,
    seed: int | None = None,
    level: int | None = None,
) -> dict:
    """Interlude / advancement step under the rulepack's growth model."""
    rp = _rp(rulepack)
    growth = rp.get("growth")
    if not isinstance(growth, Mapping):
        raise ResolutionError("RULEPACK_FIELD_MISSING", "rulepack.growth must be a mapping")
    model = str(growth.get("model") or "skill_mark_roll_over")

    if isinstance(skill, bool) or not isinstance(skill, int) or not 0 <= skill <= 100:
        raise ResolutionError("RULEPACK_FIELD_INVALID", "skill must be int 0..100")

    if model == "skill_mark_roll_over":
        cap = int(growth.get("cap", 99))
        gain_formula = str(growth.get("gain", "1d10"))
        if not marked:
            return {"model": model, "skill_before": skill, "marked": False,
                    "eligible": False, "grew": False, "gain": 0, "skill_after": skill}
        if skill >= cap:
            return {"model": model, "skill_before": skill, "marked": True,
                    "eligible": False, "reason": "at_cap", "grew": False,
                    "gain": 0, "skill_after": skill}
        r = rolled if rolled is not None else dice_mod.roll_d100(seed=seed)["total"]
        if isinstance(r, bool) or not isinstance(r, int) or not 1 <= r <= 100:
            raise ResolutionError("RULEPACK_ROLL_INVALID", "rolled must be int 1..100")
        grew = r > skill
        gain = dice_mod.roll_formula(gain_formula, seed=(seed + 1) if seed is not None else None)["total"] if grew else 0
        return {"model": model, "skill_before": skill, "marked": True, "eligible": True,
                "rolled": r, "grew": grew, "gain": gain,
                "skill_after": min(cap, skill + gain)}

    if model == "level_advancement":
        if level is None:
            raise ResolutionError("RULEPACK_FIELD_INVALID", "level_advancement needs level")
        per_level = growth.get("xp_per_level") or []
        if not isinstance(per_level, (list, tuple)) or len(per_level) < 2:
            raise ResolutionError("RULEPACK_FIELD_INVALID", "growth.xp_per_level must be a table")
        next_level = level + 1
        if next_level - 2 >= len(per_level):
            return {"model": model, "level": level, "eligible": False,
                    "reason": "max_level", "advanced": False, "level_after": level}
        return {"model": model, "level": level, "eligible": True, "advanced": False,
                "xp_for_next": per_level[next_level - 2], "level_after": level,
                "note": "xp threshold for level %d" % next_level}

    if model == "none":
        return {"model": model, "skill_before": skill, "eligible": False,
                "reason": "ruleset has no growth step", "grew": False, "gain": 0,
                "skill_after": skill}

    raise ResolutionError("RULEPACK_FIELD_INVALID", "unknown growth model %r" % (model,))


# --------------------------------------------------------------------------
# opening payload -- the "same module, two rulesets" comparison surface
# --------------------------------------------------------------------------

def opening_fields(rulepack: Mapping[str, Any], card: Mapping[str, Any]) -> dict:
    """Everything a fresh table gets from the bound rulepack.

    This is the payload the acceptance evidence compares between coc7 and
    dnd5e: field names, ranges and computed formulas all differ because
    they come from the rulepack, not from the engine.
    """
    rp = _rp(rulepack)
    block = rp.get("ruleset") or {}
    formulas = resolve_formulas(rp, card)
    return {
        "rulepack_id": rp.get("id"),
        "rulepack_version": rp.get("version"),
        "schema": rp.get("schema", 1),
        "ruleset": {
            "family": block.get("family") if isinstance(block, Mapping) else None,
            "edition": block.get("edition") if isinstance(block, Mapping) else None,
            "dice": block.get("dice") if isinstance(block, Mapping) else None,
            "resolution_model": resolution_model(rp),
        },
        "attr_schema": [
            {"name": a["name"], "min": a.get("min", 1), "max": a.get("max", 100),
             **({"abbr": a["abbr"]} if "abbr" in a else {}),
             **({"roll": a["roll"]} if "roll" in a else {})}
            for a in rp.get("attrs", [])
            if isinstance(a, Mapping) and "name" in a
        ],
        "skill_schema": dict(rp.get("skills") or {}),
        "card_rules": dict(rp.get("card_rules") or {}),
        "difficulties": list(check_difficulties(rp)),
        "combat": dict(rp.get("combat") or {}),
        "growth": dict(rp.get("growth") or {}),
        "attrs": dict(card.get("attrs") or {}),
        "skills": dict(card.get("skills") or {}),
        "formulas": formulas,
    }
