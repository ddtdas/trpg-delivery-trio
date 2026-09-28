"""COC7 full character-creation rules layer (MIT, additive).

T1: the delivery-package rulepack (rulepacks/coc7/rulepack.yaml) covers the
resolution kernel (attrs roll strings, 42 skill base values, derived sheet
formulas, card_rules). It has **no** occupation table, age-modifier table,
point-buy option, background random tables or sanity mechanism details --
those live here as pure-data side files:
    configs/wizard_config.yaml      (point-buy / age / caps / san switches)
    rulepacks/coc7/occupations.yaml (occupation table)
    rulepacks/coc7/background_tables.yaml (optional random background tables)

Principles:
  * authority: rulepack formulas where they exist; this module only fills
    the gaps the rulepack does not declare.
  * no eval: occupations/background tables are plain YAML data; every
    computation is an explicit pure function.
  * deterministic: derived recompute is idempotent; dice rolls accept a
    seed for reproducibility.
Python 3.12 compatible.
"""
from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from app.config import APP_ROOT

RULEDATA_DIR = Path(__file__).resolve().parent.parent.parent / "rulepacks" / "coc7"
CONFIGS_DIR = APP_ROOT / "configs"

# ---- config ---------------------------------------------------------------

_DEFAULT_WIZARD_CONFIG: dict[str, Any] = {
    "point_buy": {
        "enabled": True,
        "total": 460,
        "min": 15,
        "max": 90,
        "per_attr_cost": "linear",
        "exclude": ["LUCK"],
    },
    "age_rule": {
        "apply": True,
        "min_investigator_age": 15,
        "int_mod_variant": False,
        # M6 (T8): age_mods single source = wizard_config.yaml (7e official,
        # INT/EDU only). This default mirrors the yaml exactly so behavior is
        # identical with or without the config file present.
        "age_mods": [
            {"min": 15, "max": 19, "int": 0, "edu": -5},
            {"min": 20, "max": 39, "int": 0, "edu": 0},
            {"min": 40, "max": 49, "int": 1, "edu": 1},
            {"min": 50, "max": 59, "int": 1, "edu": 2},
            {"min": 60, "max": 69, "int": 2, "edu": 3},
            {"min": 70, "max": 79, "int": 3, "edu": 4},
            {"min": 80, "max": 999, "int": 4, "edu": 5},
        ],
    },
    "skill_creation_cap75": True,
    "max_skill_total": 4000,
    "cm_san_cap": False,
    "random_background_enabled": False,
}


def load_wizard_config() -> dict[str, Any]:
    """wizard_config.yaml (additive) merged over defaults; never raises."""
    cfg = dict(_DEFAULT_WIZARD_CONFIG)
    try:
        p = CONFIGS_DIR / "wizard_config.yaml"
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                        merged = dict(cfg[k])
                        merged.update(v)
                        cfg[k] = merged
                    else:
                        cfg[k] = v
    except Exception:  # noqa: BLE001 — config failure degrades to defaults
        pass
    return cfg


# ---- dice expression parsing (roll strings like "3d6x5" / "2d6p6x5") -------

_ROLL_RE = re.compile(r"^(\d*)d(\d+)([pkh]?)(\d*)x?(\d*)$")


def parse_roll_string(spec: str) -> dict[str, Any]:
    """rulepack roll string -> {count, sides, keep, times, mult} spec.

    Grammar used by rulepacks/coc7/rulepack.yaml:
      "3d6x5"    -> 3d6, result times 5
      "2d6p6x5"  -> 2d6 keep the best 6 (take-6), times 5
    Unknown shapes fall back to plain 1d100 (never raise at parse time).
    """
    m = _ROLL_RE.match(str(spec or "").strip())
    if not m:
        return {"count": 1, "sides": 100, "keep": None, "mult": 1, "raw": spec}
    count = int(m.group(1) or 1) or 1
    sides = int(m.group(2) or 6)
    keep_flag = (m.group(3) or "").lower()
    keep = None
    if keep_flag == "p":
        keep = int(m.group(4)) if m.group(4) else sides
    mult = int(m.group(5)) if m.group(5) else 1
    return {"count": count, "sides": sides, "keep": keep, "mult": mult,
            "raw": spec}


def roll_attrs(roll_specs: Mapping[str, str], seed: int | None = None) -> dict[str, int]:
    """Roll each attr from its rulepack roll string, deterministically.

    keep="p6" semantics: roll `count` dice, keep the highest `keep` (take-6).
    Result values are already scaled by the x5 multiplier (CoC 1..100 attrs).
    """
    rng = random.Random(seed) if seed is not None else random.Random()
    out: dict[str, int] = {}
    for attr, spec in roll_specs.items():
        p = parse_roll_string(spec)
        rolls = [rng.randint(1, p["sides"]) for _ in range(p["count"])]
        if p["keep"] is not None and p["keep"] < len(rolls):
            rolls = sorted(rolls, reverse=True)[: p["keep"]]
        total = sum(rolls) * p["mult"]
        out[attr] = int(total)
    return out


# ---- heuristics (sanity mechanism data, section 2.8 of T1) -----------------

SAN_MIN, SAN_MAX = 0, 99


def san_current_for(attrs: Mapping[str, int]) -> int:
    """Starting SAN = POW (7e: POW is already 0..100; engine coc_san_start)."""
    return max(SAN_MIN, min(SAN_MAX, int(attrs.get("POW", 0))))


# ---- derived sheets (uses the engine formula registry where possible) -------

def recompute_derived(attrs: Mapping[str, int], *,
                      luck_enabled: bool = False,
                      luck: int | None = None,
                      ruleset_version: str = "7e") -> dict[str, int]:
    """Idempotent derived-sheet computation using canonical 7e formulas.

    Mirrors app.rules.formulas (coc_hp_max / coc_mp_max / coc_san_start /
    coc_mov / coc_build / coc_damage_bonus) so the wizard sheet matches the
    runtime resolver without importing it (no cross-layer coupling).
    """
    d: dict[str, int] = {}
    con = int(attrs.get("CON", 0))
    siz = int(attrs.get("SIZ", 0))
    pow_ = int(attrs.get("POW", 0))
    dex = int(attrs.get("DEX", 0))
    str_ = int(attrs.get("STR", 0))
    int_ = int(attrs.get("INT", 0))

    d["hp_max"] = (con + siz) // 10
    # 【队长裁决 2026-09-28】MP = POW/10 (官方 7e)。默认 7e；旧逻辑 POW/5 可经
    # ruleset_version="6e"/"legacy" 回退 (tester 回归旧卡不崩)。
    if ruleset_version in ("6e", "legacy", "classic"):
        d["mp_max"] = pow_ // 5
    else:
        d["mp_max"] = pow_ // 10
    d["san_start"] = max(SAN_MIN, min(SAN_MAX, pow_))
    d["dodge"] = dex // 2
    d["idea"] = int_ * 5
    d["knowledge"] = int(attrs.get("EDU", 0)) * 5  # Know (7e 官方)
    if dex < siz and str_ < siz:
        d["mov"] = 7
    elif str_ > siz and dex > siz:
        d["mov"] = 9
    else:
        d["mov"] = 8
    total = str_ + siz
    if total <= 64:
        d["build"] = -2
        d["damage_bonus"] = "-2"
    elif total <= 84:
        d["build"] = -1
        d["damage_bonus"] = "-1"
    elif total <= 124:
        d["build"] = 0
        d["damage_bonus"] = "0"
    elif total <= 164:
        d["build"] = 1
        d["damage_bonus"] = "+1d4"
    elif total <= 204:
        d["build"] = 2
        d["damage_bonus"] = "+1d6"
    else:
        d["build"] = 3
        d["damage_bonus"] = "+2d6"

    if luck_enabled and luck is not None:
        d["luck"] = int(luck) * 5
    return d


# ---- occupations -----------------------------------------------------------

_OCCUPATIONS_CACHE: dict[str, dict[str, Any]] = {}


def load_occupations(ruleset: str = "coc7") -> dict[str, Any]:
    """occupations.yaml -> {id: {..}} (plain data; empty table if absent)."""
    ruleset = str(ruleset or "coc7")
    if ruleset in _OCCUPATIONS_CACHE:
        return _OCCUPATIONS_CACHE[ruleset]
    data: dict[str, Any] = {}
    try:
        p = RULEDATA_DIR / "occupations.yaml"
        if p.is_file():
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                occs = doc.get("occupations") or []
                data = {str(o.get("id")): o for o in occs if isinstance(o, dict) and o.get("id")}
    except Exception:  # noqa: BLE001
        data = {}
    _OCCUPATIONS_CACHE[ruleset] = data
    return data


def occupation_points(occupation: Mapping[str, Any], edu: int) -> int:
    """Occupational skill points (7e official, 【队长裁决 2026-09-28】):
    EDU<=75 用 EDU*4; EDU>75 用 EDU*2+2。
    occupations.yaml 里的 points 字段仅为展示参考, 实算以 7e 官方动态规则为准。
    """
    pts = str(occupation.get("points") or "edu_x4")
    edu_v = int(edu)
    if pts == "edu_x2_p2" and edu_v <= 75:
        # 部分职业官方固定 edu_x2+2 (艺术家/军人/流浪汉等)；EDU>75 仍按官方动态规则。
        return edu_v * 2 + 2
    if edu_v > 75:
        return edu_v * 2 + 2
    return edu_v * 4


def interest_points(int_: int) -> int:
    """Interest skill points = INT x 2 (7e Investigator Handbook)."""
    return int(int_) * 2


# ---- background random tables ----------------------------------------------

_BG_TABLES_CACHE: dict[str, dict[str, Any]] = {}


def load_background_tables(ruleset: str = "coc7") -> dict[str, Any]:
    """background_tables.yaml -> {field: [options]}; empty if absent."""
    ruleset = str(ruleset or "coc7")
    if ruleset in _BG_TABLES_CACHE:
        return _BG_TABLES_CACHE[ruleset]
    data: dict[str, Any] = {}
    try:
        p = RULEDATA_DIR / "background_tables.yaml"
        if p.is_file():
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                data = doc.get("tables") or {}
    except Exception:  # noqa: BLE001
        data = {}
    _BG_TABLES_CACHE[ruleset] = data
    return data


def roll_background(ruleset: str = "coc7", seed: int | None = None,
                    tables: Mapping[str, Any] | None = None) -> tuple[dict[str, str], str]:
    """Roll one option per background field; returns (details, ref)."""
    tables = dict(tables or load_background_tables(ruleset))
    rng = random.Random(seed) if seed is not None else random.Random()
    details: dict[str, str] = {}
    refs: list[str] = []
    for field, options in tables.items():
        opts = list(options) if isinstance(options, (list, tuple)) else []
        if not opts:
            continue
        pick = opts[rng.randrange(len(opts))]
        if isinstance(pick, dict):
            text = str(pick.get("text") or pick.get("value") or "")
            ref = str(pick.get("ref") or "")
        else:
            text, ref = str(pick), ""
        if text:
            details[str(field)] = text
        if ref:
            refs.append(ref)
    return details, ";".join(refs)


# ---- sanitized skill table (from rulepack) ---------------------------------

_SKILL_BASE_CACHE: dict[str, dict[str, int]] = {}


def load_skill_base(ruleset: str = "coc7") -> dict[str, int]:
    """CoC7 skill base table -- 【队长裁决 2026-09-28】单一事实数据源 = skills_7e.yaml.

    skills_7e.yaml (官方 7e 技能清单, 约 60 项 + 默认值) 优先；若缺失则回退
    rulepack.yaml 的 42 项 (向后兼容)。引擎校验与 UI 展示都读本函数。
    """
    ruleset = str(ruleset or "coc7")
    if ruleset in _SKILL_BASE_CACHE:
        return _SKILL_BASE_CACHE[ruleset]
    data: dict[str, int] = {}
    # 1) skills_7e.yaml (additive, 单一事实)
    try:
        p7 = RULEDATA_DIR / "skills_7e.yaml"
        if p7.is_file():
            doc = yaml.safe_load(p7.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("skills"), dict):
                for k, v in doc["skills"].items():
                    if isinstance(v, dict) and "base" in v:
                        data[str(k)] = int(v["base"])
                    elif isinstance(v, (int, float)) and not isinstance(v, bool):
                        data[str(k)] = int(v)
    except Exception:  # noqa: BLE001
        pass
    # 2) fallback / merge: rulepack 已有技能照旧 (只补缺失, 不覆盖 skills_7e)
    try:
        p = RULEDATA_DIR / "rulepack.yaml"
        if p.is_file():
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("skills"), dict):
                for k, v in doc["skills"].items():
                    if k not in data and isinstance(v, (int, float)) and not isinstance(v, bool):
                        data[str(k)] = int(v)
    except Exception:  # noqa: BLE001
        pass
    _SKILL_BASE_CACHE[ruleset] = data
    return data
