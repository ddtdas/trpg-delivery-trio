"""TRPG rules arbiter — rulepack binding + card validation (MIT).

Pure functions, no I/O inside the arbiter object itself (YAML file
loading is the single explicit boundary helper ``load_rulepack``).
The arbiter never mutates caller state: cards/rulepacks are only read.

Python 3.12 compatible.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from app.rules import checks as checks_mod

__all__ = [
    "RulepackError",
    "CardError",
    "load_rulepack",
    "validate_rulepack",
    "validate_card",
    "build_arbiter",
    "Arbiter",
]


class RulepackError(ValueError):
    """Raised when a rulepack config is missing keys or malformed."""


class CardError(ValueError):
    """Raised by ``Arbiter.resolve_check`` on illegal inputs.

    ``validate_card`` itself never raises for game-content problems — it
    returns a report dict with ``errors``. Type-level misuse (non-mapping
    card) raises TypeError instead.
    """


_REQUIRED_RULEPACK_KEYS = ("id", "version", "attrs", "skills", "checks", "card_rules")


def load_rulepack(path: str | Path) -> dict:
    """Load + validate a rulepack YAML file. Raises on any problem."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise RulepackError(f"cannot read rulepack file: {p}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulepackError(f"invalid YAML in {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise RulepackError(f"rulepack root must be a mapping in {p}")
    return validate_rulepack(data)


def validate_rulepack(data: Mapping[str, Any]) -> dict:
    """Validate an already-parsed rulepack mapping. Returns deep copy."""
    if not isinstance(data, Mapping):
        raise RulepackError("rulepack must be a mapping")
    missing = [k for k in _REQUIRED_RULEPACK_KEYS if k not in data]
    if missing:
        raise RulepackError(f"rulepack missing keys: {missing}")
    if not isinstance(data["id"], str) or not data["id"]:
        raise RulepackError("rulepack.id must be a non-empty string")
    if not isinstance(data["attrs"], (list, tuple)) or not data["attrs"]:
        raise RulepackError("rulepack.attrs must be a non-empty list")
    for i, a in enumerate(data["attrs"]):
        if not isinstance(a, Mapping) or "name" not in a:
            raise RulepackError(f"rulepack.attrs[{i}] must be a mapping with 'name'")
    if not isinstance(data["skills"], Mapping) or not data["skills"]:
        raise RulepackError("rulepack.skills must be a non-empty mapping")
    for name, base in data["skills"].items():
        if isinstance(base, bool) or not isinstance(base, int) or not 0 <= base <= 100:
            raise RulepackError(f"rulepack.skills[{name!r}] base must be int 0..100")
    if not isinstance(data["checks"], Mapping):
        raise RulepackError("rulepack.checks must be a mapping")
    if not isinstance(data["card_rules"], Mapping):
        raise RulepackError("rulepack.card_rules must be a mapping")
    if "derived" in data and not isinstance(data["derived"], Mapping):
        raise RulepackError("rulepack.derived must be a mapping when present")
    for dname, spec in (data.get("derived") or {}).items():
        if not isinstance(spec, Mapping) or set(spec.keys()) != {"fn", "args"}:
            raise RulepackError(f"rulepack.derived[{dname!r}] must be exactly {{fn, args}}")
        if spec["fn"] not in checks_mod.REGISTRY:
            raise RulepackError(f"rulepack.derived[{dname!r}] unknown fn: {spec['fn']!r}")
        if not isinstance(spec["args"], Mapping):
            raise RulepackError(f"rulepack.derived[{dname!r}].args must be a mapping")
    return copy.deepcopy(dict(data))


def _is_json_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _check_jsonable(value: Any, path: str, errors: list[str]) -> None:
    if _is_json_scalar(value):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            errors.append(f"{path}: non-finite float not JSON-serializable")
        return
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _check_jsonable(v, f"{path}[{i}]", errors)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                errors.append(f"{path}: non-string key {k!r} not JSON-serializable")
            _check_jsonable(v, f"{path}.{k}", errors)
        return
    errors.append(f"{path}: type {type(value).__name__} not JSON-serializable")


def validate_card(card: Mapping[str, Any], rulepack: Mapping[str, Any]) -> dict:
    """Validate a character card against a rulepack.

    Never raises for content problems — returns
    ``{"ok": bool, "errors": [str, ...]}`` with one specific message per
    violation. Raises TypeError only when ``card``/``rulepack`` are not
    mappings at all.
    """
    if not isinstance(card, Mapping):
        raise TypeError(f"card must be a mapping, got {type(card).__name__}")
    if not isinstance(rulepack, Mapping):
        raise TypeError(f"rulepack must be a mapping, got {type(rulepack).__name__}")
    errors: list[str] = []
    _check_jsonable(dict(card), "card", errors)

    rp_attrs = rulepack.get("attrs", [])
    attr_names = [a["name"] for a in rp_attrs if isinstance(a, Mapping) and "name" in a]
    attr_min = {a["name"]: a.get("min", 1) for a in rp_attrs if isinstance(a, Mapping) and "name" in a}
    attr_max = {a["name"]: a.get("max", 100) for a in rp_attrs if isinstance(a, Mapping) and "name" in a}
    rp_skills: Mapping[str, Any] = rulepack.get("skills", {})
    cr: Mapping[str, Any] = rulepack.get("card_rules", {})
    skill_lo = cr.get("skill_min", 0)
    skill_hi = cr.get("skill_max", 100)

    # --- attrs block ---
    attrs = card.get("attrs")
    if not isinstance(attrs, Mapping):
        errors.append("card.attrs: missing or not a mapping")
    else:
        required = cr.get("required_attrs", attr_names)
        for name in required:
            if name not in attrs:
                errors.append(f"card.attrs.{name}: missing required attribute")
        for name, val in attrs.items():
            if name not in attr_names:
                errors.append(f"card.attrs.{name}: unknown attribute (rulepack has no such attr)")
                continue
            if isinstance(val, bool) or not isinstance(val, int):
                errors.append(f"card.attrs.{name}: must be int, got {type(val).__name__}")
                continue
            lo, hi = attr_min.get(name, 1), attr_max.get(name, 100)
            if not lo <= val <= hi:
                errors.append(f"card.attrs.{name}: {val} out of range {lo}..{hi}")

    # --- skills block ---
    skills = card.get("skills")
    if not isinstance(skills, Mapping):
        errors.append("card.skills: missing or not a mapping")
    else:
        if not skills:
            errors.append("card.skills: empty (at least one skill required)")
        allow_custom = bool(cr.get("allow_custom_skills", False))
        for name, val in skills.items():
            if name not in rp_skills and not allow_custom:
                errors.append(f"card.skills.{name}: unknown skill (not in rulepack skill table)")
                continue
            if isinstance(val, bool) or not isinstance(val, int):
                errors.append(f"card.skills.{name}: must be int, got {type(val).__name__}")
                continue
            if not skill_lo <= val <= skill_hi:
                errors.append(f"card.skills.{name}: {val} out of range {skill_lo}..{skill_hi}")
        max_total = cr.get("max_skill_total")
        if isinstance(max_total, int) and isinstance(skills, Mapping):
            ints = [v for v in skills.values() if isinstance(v, int) and not isinstance(v, bool)]
            if sum(ints) > max_total:
                errors.append(f"card.skills: total {sum(ints)} exceeds max_skill_total {max_total}")

    # --- name / identity ---
    if "name" in card and (not isinstance(card["name"], str) or not card["name"].strip()):
        errors.append("card.name: must be a non-empty string when present")

    return {"ok": not errors, "errors": errors}


class Arbiter:
    """Rule-pack-bound deterministic adjudicator. Stateless, read-only."""

    def __init__(self, rulepack: Mapping[str, Any]) -> None:
        self._rp = validate_rulepack(rulepack)

    @property
    def rulepack_id(self) -> str:
        return self._rp["id"]

    @property
    def rulepack(self) -> dict:
        return copy.deepcopy(self._rp)

    def skill_value(self, card: Mapping[str, Any], target: str) -> int:
        """Look up ``target`` skill/attr value on a card. Raises CardError."""
        if not isinstance(card, Mapping):
            raise CardError(f"card must be a mapping, got {type(card).__name__}")
        if not isinstance(target, str) or not target:
            raise CardError(f"target must be a non-empty string, got {target!r}")
        skills = card.get("skills", {})
        attrs = card.get("attrs", {})
        if isinstance(skills, Mapping) and target in skills:
            val = skills[target]
        elif isinstance(attrs, Mapping) and target in attrs:
            val = attrs[target]
        else:
            raise CardError(f"unknown check target: {target!r}")
        if isinstance(val, bool) or not isinstance(val, int):
            raise CardError(f"target {target!r} value must be int, got {type(val).__name__}")
        if not 0 <= val <= 100:
            raise CardError(f"target {target!r} value {val} out of range 0..100")
        return val

    def validate_card(self, card: Mapping[str, Any]) -> dict:
        return validate_card(card, self._rp)

    def resolve_check(
        self,
        card: Mapping[str, Any],
        target: str,
        difficulty: str = "regular",
        bonus: int = 0,
        penalty: int = 0,
        seed: int | None = None,
        rolled: int | None = None,
    ) -> dict:
        """Resolve a check for ``target`` on ``card``.

        Illegal inputs raise (CardError/TypeError/ValueError); game
        outcomes are data. Caller state is never mutated.
        """
        if not isinstance(card, Mapping):
            raise CardError(f"card must be a mapping, got {type(card).__name__}")
        if difficulty not in checks_mod.DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {checks_mod.DIFFICULTIES}, got {difficulty!r}")
        for name, val in (("bonus", bonus), ("penalty", penalty)):
            if isinstance(val, bool) or not isinstance(val, int):
                raise TypeError(f"{name} must be int, got {type(val).__name__}")
            if val < 0:
                raise ValueError(f"{name} must be >= 0, got {val}")
        if bonus > 0 and penalty > 0:
            raise ValueError("bonus and penalty must not both be non-zero")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise TypeError(f"seed must be int or None, got {type(seed).__name__}")
        before = copy.deepcopy(dict(card))
        skill = self.skill_value(card, target)
        out = checks_mod.resolve_check(
            skill, rolled=rolled, difficulty=difficulty,
            bonus=bonus, penalty=penalty, seed=seed,
        )
        out = {"target": target, **out}
        if dict(card) != before:
            raise AssertionError("arbiter mutated the input card")
        return out

    def derived(self, name: str, card: Mapping[str, Any]) -> Any:
        """Resolve a named derived stat from the rulepack's {fn, args} table."""
        derived_table = self._rp.get("derived") or {}
        if name not in derived_table:
            raise CardError(f"unknown derived stat: {name!r}")
        return checks_mod.resolve_derived(derived_table[name], card)


def build_arbiter(rulepack: Mapping[str, Any] | str | Path) -> Arbiter:
    """Build an Arbiter from a rulepack mapping or a YAML file path."""
    if isinstance(rulepack, (str, Path)) and Path(str(rulepack)).suffix in (".yaml", ".yml"):
        return Arbiter(load_rulepack(rulepack))
    if isinstance(rulepack, Mapping):
        return Arbiter(rulepack)
    # Heuristic: a Mapping without rulepack keys but passed as path-like str
    # that is not a yaml path is a user error.
    raise RulepackError(f"cannot build arbiter from {type(rulepack).__name__}")
