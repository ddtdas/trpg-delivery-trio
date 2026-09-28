"""R23 -- rulepack multi-version + automatic ruleset binding.

Covers:
  * the three packaged rulesets load, and their field/formula tables differ
    for the right reasons (CoC7 vs CoC6 vs D&D 5e),
  * schema v2 validation and its stable error codes,
  * v1 backward compatibility (app.rules.arbiter still loads every pack),
  * manifest ruleset auto-binding, including the hard failure on an
    unknown ruleset (no silent fallback),
  * the formula registry refuses expression strings.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.rules import binding as binding_mod
from app.rules import formulas as formulas_mod
from app.rules import resolver as resolver_mod
from app.rules.rulepack_schema import (
    PACKAGED_RULESETS,
    PLANNED_RULESETS,
    RulepackSchemaError,
    catalog,
    validate_rulepack_v2,
)

ROOT = Path(__file__).resolve().parents[2]  # R2: tests/rules/ -> server root
REPO = binding_mod.RulepackRepository(ROOT / "rulepacks")

COC7_CARD = {
    "name": "Investigator A",
    "attrs": {"STR": 50, "CON": 60, "SIZ": 70, "DEX": 55, "APP": 45,
              "INT": 65, "POW": 70, "EDU": 80, "LUCK": 50},
    "skills": {"spot_hidden": 45, "library_use": 60, "dodge": 27},
}

COC6_CARD = {
    "name": "Investigator B",
    "attrs": {"STR": 50, "CON": 61, "SIZ": 70, "DEX": 55, "APP": 45,
              "INT": 65, "POW": 70, "EDU": 80, "LUCK": 50},
    "skills": {"spot_hidden": 45, "listen": 30, "dodge": 0},
}

DND_CARD = {
    "name": "Adventurer A",
    "attrs": {"STR": 16, "DEX": 14, "CON": 15, "INT": 12, "WIS": 13,
              "CHA": 10, "LEVEL": 3},
    "skills": {},
}


def rp(rid: str) -> dict:
    _, rulepack, _ = REPO.resolve(rid)
    return rulepack


# ---------------------------------------------------------------------------
# repository / index
# ---------------------------------------------------------------------------

def test_repository_indexes_the_three_new_packs():
    entries = REPO.scan()
    assert set(("coc7", "coc6", "dnd5e")).issubset(set(entries))
    for rid in ("coc7", "coc6", "dnd5e"):
        entry = entries[rid]
        assert entry["valid"] is True, entry.get("error")
        assert entry["schema"] == 2
        assert len(entry["sha256"]) == 64
        assert entry["size"] > 1000
        assert entry["resolution_model"] in (
            "coc_percentile", "coc_classic", "d20_dc")


def test_build_index_is_json_serializable_and_complete():
    index = REPO.build_index()
    assert index["count"] == len(index["items"])
    ids = {item["id"] for item in index["items"]}
    assert {"coc7", "coc6", "dnd5e"} <= ids
    for item in index["items"]:
        assert item["sha256"] and item["size"] and item["path"]


def test_catalogue_lists_packaged_and_planned_rulesets():
    cat = catalog()
    packaged = {row["id"] for row in cat["packaged"]}
    planned = {row["id"] for row in cat["planned"]}
    assert {"coc7", "coc6", "dnd5e"} <= packaged
    # the user asked for "all major editions": the schema must already
    # accommodate the rest, even before their data files land
    assert {"dnd35", "dnd4e", "pf2e", "coc5"} <= planned
    assert packaged == set(PACKAGED_RULESETS)
    assert planned == set(PLANNED_RULESETS)
    assert cat["schema_version"] == 2


# ---------------------------------------------------------------------------
# schema v2 validation + error codes
# ---------------------------------------------------------------------------

def test_v1_rulepack_still_validates():
    data = yaml.safe_load((ROOT / "rulepacks" / "custom" / "rulepack.yaml").read_text("utf-8"))
    out = validate_rulepack_v2(data)
    assert out["schema"] == 1 if "schema" in out else True


def test_schema_version_rejected():
    with pytest.raises(RulepackSchemaError) as ei:
        validate_rulepack_v2({"schema": 99, "id": "x", "version": "1"})
    assert ei.value.code == "RULEPACK_SCHEMA_UNSUPPORTED"


def test_v2_requires_combat_and_growth():
    data = rp("coc7")
    del data["combat"]
    with pytest.raises(RulepackSchemaError) as ei:
        validate_rulepack_v2(data)
    assert ei.value.code == "RULEPACK_FIELD_MISSING"
    assert "combat" in ei.value.path


def test_unknown_formula_fn_is_rejected():
    data = rp("coc7")
    data["formulas"]["bogus"] = {"fn": "definitely_not_a_fn", "args": {}}
    with pytest.raises(RulepackSchemaError) as ei:
        validate_rulepack_v2(data)
    assert ei.value.code == "RULEPACK_FORMULA_UNKNOWN"


def test_unknown_resolution_model_is_rejected():
    data = rp("coc7")
    data["ruleset"]["resolution_model"] = "roll_high_wins"
    with pytest.raises(RulepackSchemaError) as ei:
        validate_rulepack_v2(data)
    assert ei.value.code == "RULEPACK_RESOLUTION_MODEL_UNKNOWN"


def test_resolution_model_must_match_ruleset_block():
    data = rp("coc7")
    data["resolution"]["model"] = "d20_dc"
    with pytest.raises(RulepackSchemaError) as ei:
        validate_rulepack_v2(data)
    assert ei.value.code == "RULEPACK_FIELD_INVALID"


def test_every_packaged_pack_passes_v2_validation():
    for rid in ("coc7", "coc6", "dnd5e", "custom"):
        data = yaml.safe_load((ROOT / "rulepacks" / rid / "rulepack.yaml").read_text("utf-8"))
        out = validate_rulepack_v2(data)
        assert out["id"] == rid


# ---------------------------------------------------------------------------
# v1 backward compatibility
# ---------------------------------------------------------------------------

def test_v1_arbiter_still_loads_every_pack():
    from app.rules.arbiter import build_arbiter, load_rulepack
    for rid in ("coc7", "coc6", "dnd5e"):
        loaded = load_rulepack(ROOT / "rulepacks" / rid / "rulepack.yaml")
        arb = build_arbiter(loaded)
        assert arb.rulepack_id == rid


def test_v1_arbiter_resolves_coc7_derived_table():
    from app.rules.arbiter import build_arbiter, load_rulepack
    arb = build_arbiter(load_rulepack(ROOT / "rulepacks" / "coc7" / "rulepack.yaml"))
    assert arb.derived("hard_of_spot_hidden", COC7_CARD) == 22
    assert arb.derived("dodge_from_dex", COC7_CARD) == 27


# ---------------------------------------------------------------------------
# CoC 7e
# ---------------------------------------------------------------------------

def test_coc7_fields_and_formulas():
    rulepack = rp("coc7")
    fields = resolver_mod.opening_fields(rulepack, COC7_CARD)
    assert fields["ruleset"]["resolution_model"] == "coc_percentile"
    assert fields["ruleset"]["dice"] == "d100"
    assert [a["name"] for a in fields["attr_schema"]][:8] == [
        "STR", "CON", "SIZ", "DEX", "APP", "INT", "POW", "EDU"]
    assert len(fields["skill_schema"]) == 42
    assert fields["difficulties"] == ["regular", "hard", "extreme"]
    f = fields["formulas"]
    assert f["hp_max"] == 13           # (60 + 70) / 10, floored
    assert f["mp_max"] == 7            # 70 / 10 (7e official; captain adjudication 2026-09-28)
    assert f["san_start"] == 70        # CoC7 SAN starts at POW
    assert f["mov"] == 7
    assert f["build"] == 0             # STR+SIZ = 120
    assert f["damage_bonus"] == "0"
    assert f["dodge_default"] == 27    # DEX / 2
    assert f["spot_hidden_hard"] == 22
    assert f["spot_hidden_extreme"] == 9


def test_coc7_check_tiers():
    rulepack = rp("coc7")
    out = resolver_mod.resolve_check(rulepack, COC7_CARD, "spot_hidden", rolled=12)
    assert out["model"] == "coc_percentile"
    assert out["thresholds"] == {"regular": 45, "hard": 22, "extreme": 9}
    assert out["level"] == "hard" and out["success"] is True
    assert resolver_mod.resolve_check(
        rulepack, COC7_CARD, "spot_hidden", rolled=1)["level"] == "critical"
    assert resolver_mod.resolve_check(
        rulepack, COC7_CARD, "spot_hidden", rolled=100)["level"] == "fumble"
    # hard difficulty needs the narrowed tier
    assert resolver_mod.resolve_check(
        rulepack, COC7_CARD, "spot_hidden", difficulty="hard", rolled=30)["success"] is False


def test_coc7_rejects_undeclared_difficulty():
    with pytest.raises(resolver_mod.ResolutionError) as ei:
        resolver_mod.resolve_check(rp("coc7"), COC7_CARD, "spot_hidden", difficulty="medium")
    assert ei.value.code == "RULEPACK_DIFFICULTY_UNKNOWN"


# ---------------------------------------------------------------------------
# CoC 6e -- same family, different maths
# ---------------------------------------------------------------------------

def test_coc6_hp_rounds_up_where_coc7_rounds_down():
    coc7 = resolver_mod.opening_fields(rp("coc7"), COC6_CARD)["formulas"]
    coc6 = resolver_mod.opening_fields(rp("coc6"), COC6_CARD)["formulas"]
    # CON 61 + SIZ 70 = 131 -> 7e floors to 13, 6e rounds up to 14
    assert coc7["hp_max"] == 13
    assert coc6["hp_max"] == 14


def test_coc6_san_and_derived_rolls():
    f = resolver_mod.opening_fields(rp("coc6"), COC6_CARD)["formulas"]
    assert f["san_start"] == 350       # POW x 5
    assert f["idea"] == 325            # INT x 5
    assert f["luck"] == 350            # POW x 5
    assert f["know"] == 400            # EDU x 5
    assert f["dodge_start"] == 110     # DEX x 2


def test_coc6_has_no_hard_extreme_tiers():
    rulepack = rp("coc6")
    assert resolver_mod.check_difficulties(rulepack) == ("regular",)
    with pytest.raises(resolver_mod.ResolutionError) as ei:
        resolver_mod.resolve_check(rulepack, COC6_CARD, "spot_hidden", difficulty="hard")
    assert ei.value.code == "RULEPACK_DIFFICULTY_UNKNOWN"


def test_coc6_critical_special_and_fumble_bands():
    rulepack = rp("coc6")
    levels = {
        r: resolver_mod.resolve_check(rulepack, COC6_CARD, "spot_hidden", rolled=r)["level"]
        for r in (3, 9, 12, 96)
    }
    assert levels[3] == "critical"     # 01-05
    assert levels[9] == "special"      # <= 45 / 5
    assert levels[12] == "success"
    assert levels[96] == "fumble"      # 96-100 regardless of skill


def test_coc6_modifier_shifts_the_target():
    rulepack = rp("coc6")
    out = resolver_mod.resolve_check(
        rulepack, COC6_CARD, "spot_hidden", modifier=-40, rolled=12)
    assert out["target_value"] == 45 and out["effective_target"] == 5
    assert out["success"] is False


# ---------------------------------------------------------------------------
# D&D 5e
# ---------------------------------------------------------------------------

def test_dnd5e_fields_and_formulas():
    rulepack = rp("dnd5e")
    fields = resolver_mod.opening_fields(rulepack, DND_CARD)
    assert fields["ruleset"]["resolution_model"] == "d20_dc"
    assert fields["ruleset"]["dice"] == "d20"
    assert [a["name"] for a in fields["attr_schema"]] == [
        "STR", "DEX", "CON", "INT", "WIS", "CHA", "LEVEL"]
    assert len(fields["skill_schema"]) == 18
    assert len(fields["difficulties"]) == 6
    assert fields["growth"]["model"] == "level_advancement"
    f = fields["formulas"]
    assert (f["str_mod"], f["dex_mod"], f["con_mod"]) == (3, 2, 2)
    assert (f["int_mod"], f["wis_mod"], f["cha_mod"]) == (1, 1, 0)
    assert f["prof_bonus"] == 2
    assert f["hp_max"] == 24
    assert f["ac"] == 12
    assert f["initiative"] == 2
    assert f["attack"] == 5
    assert f["spell_dc"] == 11
    assert f["passive_perception"] == 13
    assert f["athletics"] == 5
    assert f["perception"] == 3


def test_dnd5e_proficiency_bonus_by_level():
    assert formulas_mod.resolve_one(
        {"fn": "dnd_prof_bonus", "args": {"level": 1}}, {}) == 2
    assert formulas_mod.resolve_one(
        {"fn": "dnd_prof_bonus", "args": {"level": 5}}, {}) == 3
    assert formulas_mod.resolve_one(
        {"fn": "dnd_prof_bonus", "args": {"level": 9}}, {}) == 4
    assert formulas_mod.resolve_one(
        {"fn": "dnd_prof_bonus", "args": {"level": 17}}, {}) == 6


def test_dnd5e_check_against_dc():
    rulepack = rp("dnd5e")
    out = resolver_mod.resolve_check(
        rulepack, DND_CARD, "perception", difficulty="medium", rolled=12)
    assert out["model"] == "d20_dc"
    assert out["target_value"] == 3
    assert out["total"] == 15 and out["dc"] == 15
    assert out["success"] is True and out["margin"] == 0


def test_dnd5e_natural_20_and_natural_1():
    rulepack = rp("dnd5e")
    crit = resolver_mod.resolve_check(
        rulepack, DND_CARD, "perception", difficulty="nearly_impossible", rolled=20)
    assert crit["critical"] is True and crit["success"] is True
    fum = resolver_mod.resolve_check(
        rulepack, DND_CARD, "perception", difficulty="very_easy", rolled=1)
    assert fum["fumble"] is True and fum["success"] is False


def test_dnd5e_advantage_keeps_the_higher_die():
    rulepack = rp("dnd5e")
    out = resolver_mod.resolve_check(
        rulepack, DND_CARD, "perception", difficulty="medium", advantage=1, seed=7)
    assert out["roll"]["mode"] == "advantage"
    assert len(out["roll"]["rolls"]) == 2
    assert out["roll"]["total"] == max(out["roll"]["rolls"])


def test_card_value_overrides_derived_formula():
    # a player who writes their own perception beats the derivation
    card = {**DND_CARD, "skills": {"perception": 9}}
    f = resolver_mod.opening_fields(rp("dnd5e"), card)["formulas"]
    assert f["perception"] == 3            # formula still reports the derivation
    out = resolver_mod.resolve_check(rp("dnd5e"), card, "perception", rolled=10)
    assert out["target_value"] == 9        # but the card wins at the table


# ---------------------------------------------------------------------------
# combat / damage / growth per ruleset
# ---------------------------------------------------------------------------

def test_apply_damage_differs_between_rulesets():
    coc7 = resolver_mod.apply_damage(rp("coc7"), current_hp=12, damage=8, armor=2)
    dnd = resolver_mod.apply_damage(rp("dnd5e"), current_hp=24, damage=8, armor=2)
    assert coc7["absorbed"] == 2 and coc7["taken"] == 6
    assert coc7["major_wound"] is True          # 6 * 2 >= 12 HP -> major wound
    assert dnd["absorbed"] == 0                 # 5e pack disables armour soak
    assert dnd["taken"] == 8
    assert "major_wound" not in dnd
    # a lighter hit is not a major wound under CoC7
    light = resolver_mod.apply_damage(rp("coc7"), current_hp=12, damage=4, armor=0)
    assert light["major_wound"] is False


def test_growth_model_differs_between_rulesets():
    coc7 = resolver_mod.growth_check(rp("coc7"), skill=45, marked=True, rolled=60, seed=1)
    assert coc7["model"] == "skill_mark_roll_over" and coc7["grew"] is True
    assert 1 <= coc7["gain"] <= 10
    dnd = resolver_mod.growth_check(rp("dnd5e"), skill=0, level=1)
    assert dnd["model"] == "level_advancement"
    assert dnd["xp_for_next"] == 300


def test_attack_loop_uses_the_declared_model():
    coc7 = resolver_mod.resolve_attack(
        rp("coc7"), COC7_CARD, COC7_CARD, rolled=10, defense_rolled=80, seed=5)
    assert coc7["model"] == "coc_percentile" and coc7["hit"] is True
    dnd = resolver_mod.resolve_attack(
        rp("dnd5e"), DND_CARD, DND_CARD, rolled=15, seed=5)
    assert dnd["model"] == "d20_dc"
    assert dnd["target_ac"] == 12


# ---------------------------------------------------------------------------
# auto-binding (R23 core)
# ---------------------------------------------------------------------------

def sample_manifest() -> dict:
    return yaml.safe_load(
        (ROOT / "modules" / "sample_coc" / "module.yaml").read_text("utf-8"))


def test_manifest_ruleset_binds_automatically():
    bound = REPO.bind_manifest(sample_manifest())
    assert bound["ok"] is True
    assert bound["requested_ruleset"] == "coc7"
    assert bound["ruleset"] == "coc7"
    assert bound["resolution_model"] == "coc_percentile"
    assert bound["alias_applied"] is None


def test_same_module_opened_as_two_rulesets_differs():
    manifest = sample_manifest()
    a = binding_mod.open_table(manifest, COC7_CARD, repo=REPO, ruleset_override="coc7")
    b = binding_mod.open_table(manifest, DND_CARD, repo=REPO, ruleset_override="dnd5e")
    fa, fb = a["opening_fields"], b["opening_fields"]
    assert a["module_id"] == b["module_id"] == "sample_coc"
    assert a["resolution_model"] != b["resolution_model"]
    assert [x["name"] for x in fa["attr_schema"]] != [x["name"] for x in fb["attr_schema"]]
    assert len(fa["skill_schema"]) != len(fb["skill_schema"])
    assert fa["difficulties"] != fb["difficulties"]
    assert set(fa["formulas"]) != set(fb["formulas"])
    assert fa["growth"]["model"] != fb["growth"]["model"]


def test_unknown_ruleset_raises_with_an_r13_code():
    with pytest.raises(binding_mod.RulesetBindingError) as ei:
        REPO.bind_manifest({**sample_manifest(), "ruleset": "gurps4e"})
    err = ei.value
    # a manifest-declared ruleset that does not exist is R13's judgement
    assert err.code == "MODULE_RULESET_UNKNOWN"
    assert err.internal_code == "RULEPACK_UNKNOWN_RULESET"
    assert err.http_status == 422
    assert err.ruleset == "gurps4e"
    payload = err.to_dict()
    assert payload["ok"] is False
    assert payload["error_code"] == "MODULE_RULESET_UNKNOWN"
    assert "coc7" in payload["available_rulesets"]
    assert payload["detail"]["catalog_known"] is False


def test_direct_ruleset_lookup_uses_the_repo_entry_code():
    with pytest.raises(binding_mod.RulesetBindingError) as ei:
        REPO.resolve("gurps4e")
    assert ei.value.code == "RULEPACK_ENTRY_NOT_FOUND"
    assert ei.value.http_status == 404


def test_every_binding_code_is_registered_in_the_r13_table():
    from app.repository.errors import ERROR_TABLE
    for code in ("MODULE_RULESET_UNKNOWN", "MODULE_RULESET_MISSING",
                 "RULEPACK_ENTRY_NOT_FOUND", "RULEPACK_MANIFEST_INVALID",
                 "MODULE_MANIFEST_INVALID", "RULEPACK_VERSION_INCOMPATIBLE"):
        assert code in ERROR_TABLE
    for manifest in ({**sample_manifest(), "ruleset": "nope"},
                     {k: v for k, v in sample_manifest().items() if k != "ruleset"}):
        with pytest.raises(binding_mod.RulesetBindingError) as ei:
            REPO.bind_manifest(manifest)
        assert ei.value.code in ERROR_TABLE
        assert ei.value.http_status == ERROR_TABLE[ei.value.code][0]


def test_unknown_ruleset_never_falls_back_to_coc7():
    for bad in ("pathfinder3", "coc9", "nope", ""):
        with pytest.raises(binding_mod.RulesetBindingError):
            REPO.resolve(bad)


def test_planned_ruleset_reports_itself_as_planned():
    with pytest.raises(binding_mod.RulesetBindingError) as ei:
        REPO.resolve("pf2e")
    assert ei.value.code == "RULEPACK_ENTRY_NOT_FOUND"
    assert ei.value.detail["planned"] is True
    assert ei.value.detail["catalog_known"] is True


def test_declared_alias_is_echoed_not_silent():
    bound = REPO.bind_manifest({**sample_manifest(), "ruleset": "dnd"})
    assert bound["requested_ruleset"] == "dnd"
    assert bound["ruleset"] == "dnd5e"
    assert bound["alias_applied"] == "dnd5e"


def test_missing_ruleset_field_is_its_own_error():
    manifest = {k: v for k, v in sample_manifest().items() if k != "ruleset"}
    with pytest.raises(binding_mod.RulesetBindingError) as ei:
        REPO.bind_manifest(manifest)
    assert ei.value.code == "MODULE_RULESET_MISSING"
    assert ei.value.internal_code == "RULEPACK_NO_RULESET_DECLARED"


def test_directory_and_declared_id_must_match(tmp_path):
    src = (ROOT / "rulepacks" / "coc7" / "rulepack.yaml").read_text("utf-8")
    (tmp_path / "misnamed").mkdir()
    (tmp_path / "misnamed" / "rulepack.yaml").write_text(src, encoding="utf-8")
    repo = binding_mod.RulepackRepository(tmp_path)
    with pytest.raises(binding_mod.RulesetBindingError) as ei:
        repo.resolve("misnamed")
    assert ei.value.code == "RULEPACK_MANIFEST_INVALID"
    assert ei.value.internal_code == "RULEPACK_INVALID"


# ---------------------------------------------------------------------------
# formula registry hygiene -- YAML never evaluates code
# ---------------------------------------------------------------------------

def test_expression_strings_are_refused():
    with pytest.raises(formulas_mod.FormulaError):
        formulas_mod.resolve_one({"fn": "half", "args": {"of": "DEX / 2"}}, {})


def test_unknown_fn_is_refused():
    with pytest.raises(formulas_mod.FormulaError):
        formulas_mod.resolve_one({"fn": "os_system", "args": {}}, {})


def test_unresolvable_ref_is_refused():
    with pytest.raises(formulas_mod.FormulaError):
        formulas_mod.resolve_one({"fn": "half", "args": {"of": "$NOPE"}}, {})


def test_spec_must_be_exactly_fn_and_args():
    with pytest.raises(formulas_mod.FormulaError):
        formulas_mod.resolve_one({"fn": "half", "args": {"of": 10}, "extra": 1}, {})


def test_bool_is_not_accepted_in_a_numeric_slot():
    with pytest.raises(formulas_mod.FormulaError):
        formulas_mod.resolve_one({"fn": "half", "args": {"of": True}}, {})


def test_formulas_resolve_in_declaration_order():
    rulepack = {
        "formulas": {
            "base": {"fn": "const", "args": {"value": 7}},
            "doubled": {"fn": "mul", "args": {"a": "$base", "b": 2}},
        }
    }
    assert formulas_mod.resolve_formulas(rulepack, {}) == {"base": 7, "doubled": 14}
