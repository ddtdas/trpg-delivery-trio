"""TRPG rulepack schema v2 -- declarative validation (MIT, additive layer).

Rulepack schema v1 (the three YAML files shipped before this round) only
carried attrs / skills / checks / card_rules and was implicitly CoC7
shaped: nothing in the file said *which* resolution model to use, and the
loader (app/rules/arbiter.py) delegated every check to the CoC7 kernel.

Schema v2 adds the missing declaration so that one engine can host
several rulesets:

    schema: 2
    ruleset: {family: coc, edition: "7", dice: d100,
              resolution_model: coc_percentile}
    resolution: {model: coc_percentile, ...}
    formulas: {hp_max: {fn: coc_hp_max, args: {con: $CON, siz: $SIZ}}}

A v2 file is still a valid v1 file: every v1 key keeps its v1 shape, so
app.rules.arbiter.validate_rulepack keeps accepting it unchanged. That
backward-compatibility property is asserted by the test suite.

Every rejection carries a stable machine-readable code so the R13 error
table can route on it (no more single opaque error for every bad pack).
"""
from __future__ import annotations

import copy
from typing import Any, Mapping

from app.rules.formulas import FORMULA_REGISTRY

__all__ = [
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "RESOLUTION_MODELS",
    "RULESET_CATALOG",
    "RULESET_ALIASES",
    "PACKAGED_RULESETS",
    "PLANNED_RULESETS",
    "RulepackSchemaError",
    "schema_version_of",
    "validate_rulepack_v2",
    "catalog",
]

#: Schema version written by the rulepacks shipped in this round.
SCHEMA_VERSION = 2

#: Schema versions this validator accepts (v1 files keep loading).
SUPPORTED_SCHEMA_VERSIONS = (1, 2)

#: Resolution models the engine can execute (see app.rules.resolver).
RESOLUTION_MODELS = ("coc_percentile", "coc_classic", "d20_dc")

#: ruleset id -> catalogue entry. status=packaged means the YAML ships in
#: rulepacks/<id>/rulepack.yaml; status=planned means the schema already
#: accommodates it and only the data file is missing.
RULESET_CATALOG: dict[str, dict[str, Any]] = {
    "coc7": {"family": "coc", "edition": "7", "dice": "d100",
             "resolution_model": "coc_percentile", "status": "packaged",
             "display_name": "Call of Cthulhu 7th Edition"},
    "coc6": {"family": "coc", "edition": "6", "dice": "d100",
             "resolution_model": "coc_classic", "status": "packaged",
             "display_name": "Call of Cthulhu 6th Edition"},
    "dnd5e": {"family": "dnd", "edition": "5e", "dice": "d20",
              "resolution_model": "d20_dc", "status": "packaged",
              "display_name": "Dungeons & Dragons 5th Edition (SRD)"},
    "custom": {"family": "custom", "edition": "-", "dice": "d100",
               "resolution_model": "coc_percentile", "status": "packaged",
               "display_name": "Custom homebrew"},
    # ---- schema-ready, data file pending (documented in docs/RULEPACKS.md) ----
    "coc5": {"family": "coc", "edition": "5", "dice": "d100",
             "resolution_model": "coc_classic", "status": "planned",
             "display_name": "Call of Cthulhu 5th Edition"},
    "dnd35": {"family": "dnd", "edition": "3.5", "dice": "d20",
              "resolution_model": "d20_dc", "status": "planned",
              "display_name": "Dungeons & Dragons 3.5"},
    "dnd4e": {"family": "dnd", "edition": "4e", "dice": "d20",
              "resolution_model": "d20_dc", "status": "planned",
              "display_name": "Dungeons & Dragons 4th Edition"},
    "pf2e": {"family": "pathfinder", "edition": "2e", "dice": "d20",
             "resolution_model": "d20_dc", "status": "planned",
             "display_name": "Pathfinder 2nd Edition"},
    "pf1e": {"family": "pathfinder", "edition": "1e", "dice": "d20",
             "resolution_model": "d20_dc", "status": "planned",
             "display_name": "Pathfinder 1st Edition"},
}

#: Declared shorthand -> canonical id. Aliases are never silent: the
#: binding result echoes both the requested string and the resolved id.
RULESET_ALIASES: dict[str, str] = {
    "dnd": "dnd5e",
    "dnd5": "dnd5e",
    "5e": "dnd5e",
    "coc": "coc7",
    "coc7e": "coc7",
    "coc6e": "coc6",
    "dnd3.5": "dnd35",
    "d&d5e": "dnd5e",
}

PACKAGED_RULESETS: tuple[str, ...] = tuple(
    sorted(k for k, v in RULESET_CATALOG.items() if v["status"] == "packaged")
)
PLANNED_RULESETS: tuple[str, ...] = tuple(
    sorted(k for k, v in RULESET_CATALOG.items() if v["status"] == "planned")
)


class RulepackSchemaError(ValueError):
    """A rulepack file violates schema v1/v2.

    Attributes
    ----------
    code:
        Stable machine-readable code, e.g. RULEPACK_FIELD_MISSING. The R13
        error table routes on this, never on the human message.
    path:
        Dotted location of the offending node inside the rulepack.
    """

    def __init__(self, code: str, message: str, path: str = "") -> None:
        self.code = code
        self.path = path
        super().__init__("%s: %s%s" % (code, message, (" [at %s]" % path) if path else ""))

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "path": self.path}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def schema_version_of(data: Mapping[str, Any]) -> int:
    """Return the declared schema version (v1 files declare nothing)."""
    if not isinstance(data, Mapping):
        raise RulepackSchemaError("RULEPACK_ROOT_INVALID", "rulepack must be a mapping")
    raw = data.get("schema", 1)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise RulepackSchemaError(
            "RULEPACK_SCHEMA_UNSUPPORTED",
            "schema must be an integer, got %r" % (raw,),
            "schema",
        )
    if raw not in SUPPORTED_SCHEMA_VERSIONS:
        raise RulepackSchemaError(
            "RULEPACK_SCHEMA_UNSUPPORTED",
            "schema %r not supported (supported: %s)"
            % (raw, ", ".join(str(v) for v in SUPPORTED_SCHEMA_VERSIONS)),
            "schema",
        )
    return raw


def _need(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise RulepackSchemaError("RULEPACK_FIELD_MISSING", "required key missing", "%s.%s" % (path, key))
    return data[key]


def _need_mapping(data: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    value = _need(data, key, path)
    if not isinstance(value, Mapping):
        raise RulepackSchemaError(
            "RULEPACK_FIELD_INVALID", "must be a mapping", "%s.%s" % (path, key)
        )
    return value


def _validate_formula_table(data: Mapping[str, Any], path: str = "formulas") -> None:
    table = data.get("formulas")
    if table is None:
        return
    if not isinstance(table, Mapping):
        raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a mapping", path)
    for name, spec in table.items():
        where = "%s.%s" % (path, name)
        if not isinstance(spec, Mapping):
            raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a mapping", where)
        if set(spec.keys()) != {"fn", "args"}:
            raise RulepackSchemaError(
                "RULEPACK_FIELD_INVALID",
                "must be exactly {fn, args}, got keys %s" % (sorted(spec.keys()),),
                where,
            )
        if spec["fn"] not in FORMULA_REGISTRY:
            raise RulepackSchemaError(
                "RULEPACK_FORMULA_UNKNOWN",
                "unknown formula fn %r" % (spec["fn"],),
                "%s.fn" % where,
            )
        if not isinstance(spec["args"], Mapping):
            raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "args must be a mapping", "%s.args" % where)


def _validate_attrs(data: Mapping[str, Any]) -> None:
    attrs = _need(data, "attrs", "")
    if not isinstance(attrs, (list, tuple)) or not attrs:
        raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a non-empty list", "attrs")
    seen: set[str] = set()
    for i, attr in enumerate(attrs):
        where = "attrs[%d]" % i
        if not isinstance(attr, Mapping) or "name" not in attr:
            raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a mapping with name", where)
        name = attr["name"]
        if not isinstance(name, str) or not name:
            raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "name must be a non-empty string", where)
        if name in seen:
            raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "duplicate attribute %r" % (name,), where)
        seen.add(name)
        lo, hi = attr.get("min", 1), attr.get("max", 100)
        for label, val in (("min", lo), ("max", hi)):
            if isinstance(val, bool) or not isinstance(val, int):
                raise RulepackSchemaError(
                    "RULEPACK_FIELD_INVALID", "%s must be an int" % label, "%s.%s" % (where, label)
                )
        if lo > hi:
            raise RulepackSchemaError(
                "RULEPACK_FIELD_INVALID", "min %d > max %d" % (lo, hi), where
            )


def _validate_skills(data: Mapping[str, Any]) -> None:
    skills = _need(data, "skills", "")
    if not isinstance(skills, Mapping) or not skills:
        raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a non-empty mapping", "skills")
    for name, base in skills.items():
        if isinstance(base, bool) or not isinstance(base, int) or not 0 <= base <= 100:
            raise RulepackSchemaError(
                "RULEPACK_FIELD_INVALID",
                "base must be an int 0..100 (v2 keeps the v1 int shape)",
                "skills.%s" % name,
            )
    meta = data.get("skill_meta")
    if meta is None:
        return
    if not isinstance(meta, Mapping):
        raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a mapping", "skill_meta")
    for name, entry in meta.items():
        where = "skill_meta.%s" % name
        if not isinstance(entry, Mapping):
            raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a mapping", where)
        if "attr" in entry and not isinstance(entry["attr"], str):
            raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "attr must be a string", "%s.attr" % where)
        if "category" in entry and not isinstance(entry["category"], str):
            raise RulepackSchemaError(
                "RULEPACK_FIELD_INVALID", "category must be a string", "%s.category" % where
            )


def _validate_ruleset_block(data: Mapping[str, Any], version: int) -> str | None:
    """Validate the v2 ruleset + resolution declaration. Returns the model."""
    block = _need_mapping(data, "ruleset", "")
    for key in ("family", "edition", "dice", "resolution_model"):
        if key not in block:
            raise RulepackSchemaError(
                "RULEPACK_FIELD_MISSING", "required key missing", "ruleset.%s" % key
            )
        if not isinstance(block[key], str) or not block[key]:
            raise RulepackSchemaError(
                "RULEPACK_FIELD_INVALID", "must be a non-empty string", "ruleset.%s" % key
            )
    model = block["resolution_model"]
    if model not in RESOLUTION_MODELS:
        raise RulepackSchemaError(
            "RULEPACK_RESOLUTION_MODEL_UNKNOWN",
            "unknown resolution_model %r (known: %s)" % (model, ", ".join(RESOLUTION_MODELS)),
            "ruleset.resolution_model",
        )
    resolution = _need_mapping(data, "resolution", "")
    declared = resolution.get("model")
    if declared != model:
        raise RulepackSchemaError(
            "RULEPACK_FIELD_INVALID",
            "resolution.model %r must match ruleset.resolution_model %r" % (declared, model),
            "resolution.model",
        )
    return model


def _validate_combat(data: Mapping[str, Any], version: int) -> None:
    combat = data.get("combat")
    if combat is None:
        if version >= 2:
            raise RulepackSchemaError("RULEPACK_FIELD_MISSING", "required key missing", ".combat")
        return
    if not isinstance(combat, Mapping):
        raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a mapping", "combat")
    initiative = combat.get("initiative")
    if initiative is not None:
        if not isinstance(initiative, Mapping) or "order_by" not in initiative:
            raise RulepackSchemaError(
                "RULEPACK_FIELD_INVALID", "must be a mapping with order_by", "combat.initiative"
            )
    dmg = combat.get("damage_default")
    if dmg is not None and not isinstance(dmg, str):
        raise RulepackSchemaError(
            "RULEPACK_FIELD_INVALID", "must be a dice formula string", "combat.damage_default"
        )


def _validate_growth(data: Mapping[str, Any], version: int) -> None:
    growth = data.get("growth")
    if growth is None:
        if version >= 2:
            raise RulepackSchemaError("RULEPACK_FIELD_MISSING", "required key missing", ".growth")
        return
    if not isinstance(growth, Mapping):
        raise RulepackSchemaError("RULEPACK_FIELD_INVALID", "must be a mapping", "growth")
    if "model" in growth and growth["model"] not in ("skill_mark_roll_over", "level_advancement", "none"):
        raise RulepackSchemaError(
            "RULEPACK_FIELD_INVALID", "unknown growth model %r" % (growth["model"],), "growth.model"
        )


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def validate_rulepack_v2(data: Mapping[str, Any]) -> dict:
    """Validate a v1 or v2 rulepack. Returns a deep copy; never mutates input.

    Raises RulepackSchemaError (with a stable .code) on the first problem.
    """
    if not isinstance(data, Mapping):
        raise RulepackSchemaError("RULEPACK_ROOT_INVALID", "rulepack must be a mapping")
    version = schema_version_of(data)

    if not isinstance(data.get("id"), str) or not data.get("id"):
        raise RulepackSchemaError("RULEPACK_FIELD_MISSING", "id must be a non-empty string", "id")
    if not isinstance(data.get("version"), str) or not data.get("version"):
        raise RulepackSchemaError(
            "RULEPACK_FIELD_MISSING", "version must be a non-empty string", "version"
        )
    _validate_attrs(data)
    _validate_skills(data)
    _need_mapping(data, "checks", "")
    _need_mapping(data, "card_rules", "")
    _validate_combat(data, version)
    _validate_growth(data, version)
    _validate_formula_table(data)
    if version >= 2:
        _validate_ruleset_block(data, version)
    return copy.deepcopy(dict(data))


def catalog() -> dict:
    """Public catalogue of packaged + planned rulesets (for /api/rules/*)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "supported_schema_versions": list(SUPPORTED_SCHEMA_VERSIONS),
        "resolution_models": list(RESOLUTION_MODELS),
        "aliases": dict(RULESET_ALIASES),
        "packaged": [
            {"id": k, **v} for k, v in sorted(RULESET_CATALOG.items()) if v["status"] == "packaged"
        ],
        "planned": [
            {"id": k, **v} for k, v in sorted(RULESET_CATALOG.items()) if v["status"] == "planned"
        ],
    }
