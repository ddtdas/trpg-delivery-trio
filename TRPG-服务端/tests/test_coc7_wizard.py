"""COC7 character wizard tests (T4 mandatory: committed to delivery tests/).

Covers: 8-step full flow, legacy 6-step compatibility, point-buy, the 3
captain adjudications (MP=POW/10, skills_7e single source, occupation
points EDU<=75 x4 / EDU>75 x2+2), age mods (INT/EDU only), validate_card.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from app.app_core.char_wizard import CharWizard
from app.app_core.coc7_rules import (
    interest_points,
    load_occupations,
    load_skill_base,
    load_wizard_config,
    occupation_points,
    parse_roll_string,
    recompute_derived,
    roll_attrs,
    san_current_for,
)
from app.domain.character import CharacterCard, validate_card


class FakeStore:
    def __init__(self):
        self.appends = []

    async def append(self, campaign, events):
        self.appends.append((campaign, events))
        return [i for i in range(len(events))]


def _run(coro):
    return asyncio.run(coro)


# ---- rules layer ----

def test_rules_cfg():
    cfg = load_wizard_config()
    assert cfg["point_buy"]["total"] == 460
    assert cfg["age_rule"]["min_investigator_age"] == 15
    assert cfg.get("ruleset_version") == "7e"


def test_roll_string_parse():
    p = parse_roll_string("3d6x5")
    assert p["count"] == 3 and p["sides"] == 6 and p["mult"] == 5
    p2 = parse_roll_string("2d6p6x5")
    assert p2["keep"] == 6
    rolls = roll_attrs({"STR": "3d6x5", "INT": "2d6p6x5"}, seed=42)
    assert 1 <= rolls["STR"] <= 100 and 1 <= rolls["INT"] <= 100


def test_skill_base_is_7e_single_source():
    base = load_skill_base("coc7")
    assert base.get("spot_hidden") == 25
    assert len(base) >= 60  # skills_7e.yaml (73) is the single source
    assert "astronomy" in base  # 7e-only skill present


def test_mp_is_pow_10():
    # Captain adjudication: 7e MP = POW/10
    d = recompute_derived({"CON": 50, "SIZ": 50, "POW": 55, "DEX": 50,
                           "STR": 50, "INT": 50, "EDU": 50})
    assert d["mp_max"] == 5  # 55 // 10
    assert d["knowledge"] == 250  # EDU*5
    # legacy fallback POW/5
    d2 = recompute_derived({"POW": 55}, ruleset_version="6e")
    assert d2["mp_max"] == 11


def test_occupation_points_7e():
    occs = load_occupations("coc7")
    occ = occs["doctor"]
    assert occupation_points(occ, 71) == 284   # EDU<=75 -> x4
    assert occupation_points(occ, 80) == 162   # EDU>75 -> x2+2
    assert interest_points(66) == 132


def test_san_current():
    assert san_current_for({"POW": 55}) == 55


# ---- wizard flows ----

def test_legacy_flow_compat():
    wiz = CharWizard(FakeStore(), "c1")
    sess = wiz.start("pl1")
    wiz.fill(sess.card_id, "basics", {"name": "Legacy Bob"})
    wiz.fill(sess.card_id, "attrs", {"STR": 50, "CON": 50, "POW": 50, "DEX": 50,
                                     "APP": 50, "SIZ": 50, "INT": 50, "EDU": 50})
    wiz.fill(sess.card_id, "skills", {"skills": {"spot_hidden": 60, "library_use": 50}})
    wiz.fill(sess.card_id, "background", {"background": "legacy demo"})
    card = _run(wiz.finalize(sess.card_id))
    assert card.name == "Legacy Bob"
    assert validate_card(card).ok
    assert card.schema_version == "coc7-full-1.0"


def test_full_flow_8_step():
    wiz = CharWizard(FakeStore(), "c1")
    sess = wiz.start("pl2")
    wiz.fill(sess.card_id, "basics", {"name": "Dr. Wu", "age": 45})
    wiz.fill(sess.card_id, "attrs", {
        "method": "dice",
        "rolls": {"STR": 50, "CON": 60, "POW": 70, "DEX": 45,
                  "APP": 55, "SIZ": 55, "INT": 65, "EDU": 70},
        "luck_enabled": True, "luck": 40, "seed": 7,
    })
    wiz.fill(sess.card_id, "derived", {"age": 45})
    # 7e age table: 45 -> EDU+1, INT+1, SIZ unchanged
    assert sess.attrs["EDU"] == 71
    assert sess.attrs["INT"] == 66
    assert sess.attrs["SIZ"] == 55
    assert sess.derived["mp_max"] == 7
    wiz.fill(sess.card_id, "occupation", {"occupation": "doctor", "credit_rating": 50})
    assert sess.occupation_points == 284
    assert sess.interest_points == 132
    occ_pool = {"medicine": 60, "first_aid": 45, "psychology": 40, "science": 30,
                "library_use": 50, "listen": 30, "persuade": 20}
    int_pool = {"spot_hidden": 45, "stealth": 40, "art_craft": 30}
    wiz.fill(sess.card_id, "skills", {"occupation": occ_pool, "interest": int_pool})
    wiz.fill(sess.card_id, "background", {
        "background_details": {"personal_desc": "calm", "phobias_manias": "claustrophobia"},
        "background": "story",
    })
    card = _run(wiz.finalize(sess.card_id))
    assert card.occupation == "doctor"
    assert card.occupation_credit == "50"
    assert card.age == 45
    assert card.luck == 40
    assert card.derived["hp_max"] == 11
    assert card.derived["mp_max"] == 7
    assert card.derived["knowledge"] == 355
    assert card.san_current == 70
    assert card.background_details["personal_desc"] == "calm"
    assert validate_card(card).ok


def test_point_buy_flow():
    wiz = CharWizard(FakeStore(), "c1")
    sess = wiz.start("pl3")
    wiz.fill(sess.card_id, "basics", {"name": "PB Guy"})
    wiz.fill(sess.card_id, "attrs", {
        "method": "point_buy",
        "allocation": {"STR": 50, "CON": 50, "POW": 50, "DEX": 50,
                       "APP": 50, "SIZ": 50, "INT": 50, "EDU": 50},
    })
    wiz.fill(sess.card_id, "derived", {})
    wiz.fill(sess.card_id, "occupation", {"occupation": "criminal", "credit_rating": 20})
    occ_pool = {"stealth": 30, "fast_talk": 30, "locksmith": 30, "sleight_of_hand": 30,
                "disguise": 20, "firearms_handgun": 20, "intimidate": 20, "drive_auto": 10}
    wiz.fill(sess.card_id, "skills", {"occupation": occ_pool, "interest": {}})
    card = _run(wiz.finalize(sess.card_id))
    assert card.attrs_method == "point_buy"
    assert validate_card(card).ok


def test_validate_card_rejects_missing_attr():
    card = CharacterCard(card_id="c", player_id="p", ruleset="coc7", name="X",
                         attrs={"STR": 50})  # missing CON etc.
    rep = validate_card(card)
    assert not rep.ok
