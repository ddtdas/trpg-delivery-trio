"""TRPG character card model + validation (MIT).

Shared interface with the T7 rule validator: validate_card() is the single
hard gate used by CARD_FINALIZED flows and rulepacks.
Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CharacterCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str
    player_id: str
    ruleset: str
    name: str = ""
    attrs: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)
    background: str = ""
    secret_ref: str | None = None
    finalized: bool = False

    # ---- T1 (additive): COC7 full-rules fields. All optional with defaults,
    # ---- so legacy cards deserialize unchanged and validate_card hard gate
    # ---- (name + 8 attrs + skills 0..100) is untouched.
    schema_version: str = "coc7-full-1.0"
    age: int | None = None
    age_mod_applied: bool = False
    luck: int | None = None
    derived: dict[str, int] = Field(default_factory=dict)
    occupation: str = ""
    occupation_credit: str = ""
    occupation_points: int | None = None
    interest_points: int | None = None
    skill_points: dict[str, dict[str, int]] = Field(default_factory=dict)
    background_details: dict[str, str] = Field(default_factory=dict)
    idea: int | None = None
    san_current: int | None = None
    random_background_ref: str | None = None
    attrs_method: str = "dice"


class CardValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    errors: list[str] = Field(default_factory=list)


REQUIRED_ATTRS = ("STR", "CON", "POW", "DEX", "APP", "SIZ", "INT", "EDU")


def validate_card(card: CharacterCard | dict[str, Any]) -> CardValidationReport:
    """Hard gate: required attrs present + in range, name non-empty."""
    if isinstance(card, dict):
        try:
            card = CharacterCard(**card)
        except Exception as exc:  # noqa: BLE001 - report as validation error
            return CardValidationReport(ok=False, errors=["schema: %s" % exc])
    errors: list[str] = []
    if not card.name.strip():
        errors.append("name: required")
    for attr in REQUIRED_ATTRS:
        if attr not in card.attrs:
            errors.append("attrs.%s: missing" % attr)
        else:
            try:
                v = int(card.attrs[attr])
            except (TypeError, ValueError):
                errors.append("attrs.%s: not an int" % attr)
                continue
            if not 1 <= v <= 100:
                errors.append("attrs.%s: out of range 1..100" % attr)
    for skill, v in card.skills.items():
        try:
            iv = int(v)
        except (TypeError, ValueError):
            errors.append("skills.%s: not an int" % skill)
            continue
        if not 0 <= iv <= 100:
            errors.append("skills.%s: out of range 0..100" % skill)
    return CardValidationReport(ok=not errors, errors=errors)


def sample_card(
    card_id: str = "card_demo",
    player_id: str = "pl1",
    ruleset: str = "coc7",
) -> CharacterCard:
    return CharacterCard(
        card_id=card_id,
        player_id=player_id,
        ruleset=ruleset,
        name="Demo Investigator",
        attrs={k: 50 for k in REQUIRED_ATTRS},
        skills={"spot_hidden": 60, "library_use": 50},
        background="demo",
    )
