"""TRPG rulepack schema v2 -- formula registry (MIT, additive layer).

The v1 kernel (app/rules/checks.py) hard-codes CoC 7th-edition semantics
and exposes a four-function REGISTRY (half/fifth/add/skill_threshold).
Rulepack schema v2 needs *per-ruleset* formulas (CoC 6e/7e, D&D 5e, ...),
so this module adds a SEPARATE namespaced registry used by
app.rules.resolver.

Same discipline as v1 -- YAML may only name a function and hand it
literal or $ref arguments:

* no expression strings are ever evaluated (no eval/exec/getattr/import
  from YAML),
* every function is pure: (args, ns) -> JSON-serializable value,
* an unknown fn name is rejected, never silently ignored.

$ref operands resolve against a *namespace* built from the card's
attrs + skills + every formula already resolved (declaration order
matters, exactly like spreadsheet column order).
"""
from __future__ import annotations

from typing import Any, Mapping

__all__ = [
    "FormulaError",
    "FORMULA_REGISTRY",
    "formula_names",
    "resolve_one",
    "resolve_formulas",
]


class FormulaError(ValueError):
    """Raised for illegal formula specs: bad fn, bad args, bad $ref."""


# --------------------------------------------------------------------------
# argument plumbing
# --------------------------------------------------------------------------

def _as_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FormulaError("%s must be int, got %s" % (name, type(value).__name__))
    return value


def _args_of(args: Any) -> Mapping[str, Any]:
    if not isinstance(args, Mapping):
        raise FormulaError("formula args must be a mapping, got %s" % type(args).__name__)
    return args


def _operand(args: Mapping[str, Any], ns: Mapping[str, Any], key: str) -> Any:
    """Resolve one argument slot: literal, $ref, or nested list/mapping."""
    if not isinstance(args, Mapping):
        raise FormulaError("formula args must be a mapping, got %s" % type(args).__name__)
    if key not in args:
        raise FormulaError("formula args missing key: %r" % (key,))
    return _value(args[key], ns)


def _value(raw: Any, ns: Mapping[str, Any]) -> Any:
    # A bool LITERAL is allowed (e.g. dnd_passive args {proficient: true});
    # numeric slots still reject bools through _as_int, so True never
    # silently becomes 1.
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw
    if isinstance(raw, str):
        if not raw.startswith("$"):
            raise FormulaError(
                "formula operand string must be a $ref (got %r); "
                "raw expressions are forbidden" % (raw,)
            )
        ref = raw[1:]
        if ref not in ns:
            raise FormulaError("formula $ref not resolvable: %r" % (ref,))
        return ns[ref]
    if isinstance(raw, (list, tuple)):
        return [_value(v, ns) for v in raw]
    if isinstance(raw, Mapping):
        return {k: _value(v, ns) for k, v in raw.items()}
    raise FormulaError("formula operand type not supported: %s" % type(raw).__name__)


def _num(args: Mapping[str, Any], ns: Mapping[str, Any], key: str) -> int:
    return _as_int(key, _operand(args, ns, key))


# --------------------------------------------------------------------------
# generic functions
# --------------------------------------------------------------------------

def _fn_const(args, ns):
    return _operand(args, ns, "value")


def _fn_add(args, ns):
    vals = _operand(args, ns, "values")
    if not isinstance(vals, list) or not vals:
        raise FormulaError("add.values must be a non-empty list")
    return sum(_as_int("add.values[]", v) for v in vals)


def _fn_sub(args, ns):
    return _num(args, ns, "a") - _num(args, ns, "b")


def _fn_mul(args, ns):
    return _num(args, ns, "a") * _num(args, ns, "b")


def _fn_div_floor(args, ns):
    b = _num(args, ns, "b")
    if b == 0:
        raise FormulaError("div_floor.b must not be 0")
    return _num(args, ns, "a") // b


def _fn_div_ceil(args, ns):
    b = _num(args, ns, "b")
    if b == 0:
        raise FormulaError("div_ceil.b must not be 0")
    a = _num(args, ns, "a")
    return -((-a) // b)


def _fn_half(args, ns):
    return _num(args, ns, "of") // 2


def _fn_fifth(args, ns):
    return _num(args, ns, "of") // 5


def _fn_min(args, ns):
    vals = _operand(args, ns, "values")
    if not isinstance(vals, list) or not vals:
        raise FormulaError("min.values must be a non-empty list")
    return min(_as_int("min.values[]", v) for v in vals)


def _fn_max(args, ns):
    vals = _operand(args, ns, "values")
    if not isinstance(vals, list) or not vals:
        raise FormulaError("max.values must be a non-empty list")
    return max(_as_int("max.values[]", v) for v in vals)


def _fn_clamp(args, ns):
    v = _num(args, ns, "value")
    return max(_num(args, ns, "lo"), min(_num(args, ns, "hi"), v))


def _fn_lookup(args, ns):
    """Table lookup: the result of the first band whose max >= value."""
    v = _num(args, ns, "value")
    bands = _operand(args, ns, "bands")
    if not isinstance(bands, list) or not bands:
        raise FormulaError("lookup.bands must be a non-empty list")
    for band in bands:
        if not isinstance(band, Mapping):
            raise FormulaError("lookup.bands[] must be mappings")
        hi = band.get("max")
        if hi is None:
            return band.get("result")
        if v <= _as_int("lookup.bands[].max", hi):
            return band.get("result")
    return bands[-1].get("result")


# --------------------------------------------------------------------------
# Call of Cthulhu family
# --------------------------------------------------------------------------

def _fn_coc_hp_max(args, ns):
    """CoC 7e: HP = (CON + SIZ) / 10, rounded down."""
    return (_num(args, ns, "con") + _num(args, ns, "siz")) // 10


def _fn_coc_hp_max_ceil(args, ns):
    """CoC 6e: HP = (CON + SIZ) / 10, rounded up."""
    total = _num(args, ns, "con") + _num(args, ns, "siz")
    return -((-total) // 10)


def _fn_coc_mp_max(args, ns):
    """CoC MP (legacy / 6e): POW / 5, rounded down.

    【队长裁决 2026-09-28】官方 7e = POW/10，本函数保留 POW/5 供 coc6 与
    legacy 回退；7e 走 coc_mp_max_7e。ruleset_version 兼容见 wizard_config。
    """
    return _num(args, ns, "pow") // 5


def _fn_coc_mp_max_7e(args, ns):
    """CoC 7e official: MP = POW / 10, rounded down (Keeper Rulebook 7e)."""
    return _num(args, ns, "pow") // 10


def _fn_coc_san_start(args, ns):
    """CoC 7e: starting SAN equals POW."""
    return _num(args, ns, "pow")


def _fn_coc_san_start_classic(args, ns):
    """CoC 6e: starting SAN equals POW x 5."""
    return _num(args, ns, "pow") * 5


def _fn_coc_mov(args, ns):
    """CoC 7e MOV: 7 / 8 / 9 from the STR-DEX-SIZ comparison."""
    s = _num(args, ns, "str")
    d = _num(args, ns, "dex")
    z = _num(args, ns, "siz")
    if d < z and s < z:
        return 7
    if s > z and d > z:
        return 9
    return 8


def _fn_coc_build(args, ns):
    """CoC 7e Build from STR + SIZ."""
    total = _num(args, ns, "str") + _num(args, ns, "siz")
    if total <= 64:
        return -2
    if total <= 84:
        return -1
    if total <= 124:
        return 0
    if total <= 164:
        return 1
    if total <= 204:
        return 2
    return 3


def _fn_coc_damage_bonus(args, ns):
    """CoC 7e damage bonus string from STR + SIZ."""
    total = _num(args, ns, "str") + _num(args, ns, "siz")
    if total <= 64:
        return "-2"
    if total <= 84:
        return "-1"
    if total <= 124:
        return "0"
    if total <= 164:
        return "+1d4"
    if total <= 204:
        return "+1d6"
    return "+2d6"


# --------------------------------------------------------------------------
# d20 family (D&D 3.5 / 4e / 5e / Pathfinder share these)
# --------------------------------------------------------------------------

def _fn_dnd_ability_mod(args, ns):
    """d20 ability modifier = floor((score - 10) / 2)."""
    return (_num(args, ns, "score") - 10) // 2


def _fn_dnd_prof_bonus(args, ns):
    """D&D 5e proficiency bonus = 2 + floor((level - 1) / 4)."""
    lvl = _num(args, ns, "level")
    if lvl < 1:
        raise FormulaError("dnd_prof_bonus.level must be >= 1")
    return 2 + (lvl - 1) // 4


def _fn_dnd_hp_max(args, ns):
    """D&D 5e HP = hit_die + CON mod at level 1, then average per level."""
    hit_die = _num(args, ns, "hit_die")
    con_mod = _num(args, ns, "con_mod")
    level = _num(args, ns, "level") if "level" in _args_of(args) else 1
    if level < 1:
        raise FormulaError("dnd_hp_max.level must be >= 1")
    per_level = hit_die // 2 + 1 + con_mod
    return max(1, hit_die + con_mod + per_level * (level - 1))


def _fn_dnd_ac(args, ns):
    """D&D 5e AC = base + DEX mod, optionally capped (medium armour)."""
    base = _num(args, ns, "base")
    dex_mod = _num(args, ns, "dex_mod")
    if "cap" in _args_of(args):
        return base + min(_num(args, ns, "cap"), dex_mod)
    return base + dex_mod


def _fn_dnd_passive(args, ns):
    """D&D 5e passive score = 10 + ability mod + proficiency when proficient."""
    total = _num(args, ns, "base") + _num(args, ns, "mod")
    if bool(_operand(args, ns, "proficient")):
        total += _num(args, ns, "prof")
    return total


def _fn_dnd_spell_dc(args, ns):
    """D&D 5e spell save DC = 8 + proficiency + casting-ability mod."""
    return 8 + _num(args, ns, "prof") + _num(args, ns, "mod")


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

FORMULA_REGISTRY: dict[str, Any] = {
    # generic
    "const": _fn_const,
    "add": _fn_add,
    "sub": _fn_sub,
    "mul": _fn_mul,
    "div_floor": _fn_div_floor,
    "div_ceil": _fn_div_ceil,
    "half": _fn_half,
    "fifth": _fn_fifth,
    "min": _fn_min,
    "max": _fn_max,
    "clamp": _fn_clamp,
    "lookup": _fn_lookup,
    # Call of Cthulhu family
    "coc_hp_max": _fn_coc_hp_max,
    "coc_hp_max_ceil": _fn_coc_hp_max_ceil,
    "coc_mp_max": _fn_coc_mp_max,
    "coc_mp_max_7e": _fn_coc_mp_max_7e,
    "coc_san_start": _fn_coc_san_start,
    "coc_san_start_classic": _fn_coc_san_start_classic,
    "coc_mov": _fn_coc_mov,
    "coc_build": _fn_coc_build,
    "coc_damage_bonus": _fn_coc_damage_bonus,
    # d20 family
    "dnd_ability_mod": _fn_dnd_ability_mod,
    "dnd_prof_bonus": _fn_dnd_prof_bonus,
    "dnd_hp_max": _fn_dnd_hp_max,
    "dnd_ac": _fn_dnd_ac,
    "dnd_passive": _fn_dnd_passive,
    "dnd_spell_dc": _fn_dnd_spell_dc,
}


def formula_names() -> tuple[str, ...]:
    """Sorted names of every registered formula function."""
    return tuple(sorted(FORMULA_REGISTRY))


def _namespace(card: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> dict:
    if not isinstance(card, Mapping):
        raise FormulaError("card must be a mapping, got %s" % type(card).__name__)
    ns: dict[str, Any] = {}
    for key in ("attrs", "skills"):
        block = card.get(key)
        if isinstance(block, Mapping):
            for k, v in block.items():
                if k in ns and ns[k] != v:
                    raise FormulaError("ambiguous card field %r in attrs and skills" % (k,))
                ns[str(k)] = v
    if extra:
        ns.update(extra)
    return ns


def resolve_one(spec: Mapping[str, Any], ns: Mapping[str, Any]) -> Any:
    """Resolve one {fn, args} spec against an already-built namespace."""
    if not isinstance(spec, Mapping):
        raise FormulaError("formula spec must be a mapping, got %s" % type(spec).__name__)
    if set(spec.keys()) != {"fn", "args"}:
        raise FormulaError(
            "formula spec must be exactly {fn, args}, got keys %s" % (sorted(spec.keys()),)
        )
    fn_name = spec["fn"]
    if not isinstance(fn_name, str):
        raise FormulaError("formula spec fn must be a string")
    fn = FORMULA_REGISTRY.get(fn_name)
    if fn is None:
        raise FormulaError(
            "unknown formula fn: %r (known: %s)" % (fn_name, ", ".join(formula_names()))
        )
    return fn(_args_of(spec["args"]), ns)


def resolve_formulas(rulepack: Mapping[str, Any], card: Mapping[str, Any]) -> dict:
    """Resolve every formula of rulepack against card.

    Declaration order is significant: a later formula may $ref an earlier
    one (e.g. hp_max referencing con_mod). The returned mapping is
    JSON-serializable and ordered like the YAML.
    """
    if not isinstance(rulepack, Mapping):
        raise FormulaError("rulepack must be a mapping, got %s" % type(rulepack).__name__)
    table = rulepack.get("formulas") or {}
    if not isinstance(table, Mapping):
        raise FormulaError("rulepack.formulas must be a mapping")
    ns = _namespace(card)
    out: dict[str, Any] = {}
    for name, spec in table.items():
        value = resolve_one(spec, {**ns, **out})
        out[str(name)] = value
    return out
