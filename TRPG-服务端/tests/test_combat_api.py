"""T10 combat tests (P1-3: string actor normalization + validation)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from app.web.combat_api import _as_actor, _as_dict, _resolve_attack


def test_as_actor_normalizes_string():
    a = _as_actor("pc1")
    assert a["id"] == "pc1" and a["kind"] == "player"
    a2 = _as_actor({"id": "npc_x", "kind": "npc"})
    assert a2["id"] == "npc_x" and a2["kind"] == "npc"


def test_as_dict_normalizes_string_action():
    d = _as_dict("攻击")
    assert d["action"] == "攻击" and d["skill"] == "fighting_brawl"


def test_resolve_attack_with_string_actor_no_500():
    # P1-3: string actor must not crash; normalizes to {id, kind}
    r = _resolve_attack("pc1", {"action": "攻击", "skill": "fighting_brawl",
                                "target_value": 55, "seed": 42})
    assert r["actor"] == "pc1"
    assert r["status"] == "pending_approval"
    assert 1 <= r["rolled"] <= 100
    assert r["level"] in ("crit", "success", "hard", "extreme", "fail", "fumble")


def test_resolve_attack_with_dict_actor():
    r = _resolve_attack({"id": "npc_x", "kind": "npc"},
                        {"action": "反击", "target_value": 50, "seed": 7})
    assert r["actor"] == "npc_x"


def test_resolve_attack_missing_action_defaults():
    r = _resolve_attack("pc1", {"target_value": 50, "seed": 1})
    assert r["action"]  # defaults to "攻击"
    assert r["skill"] == "fighting_brawl"
