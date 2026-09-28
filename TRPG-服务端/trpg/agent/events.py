"""Agent event dictionary — frozen minimal set (DESIGN §2.3, W-A3).

Frozen contract: Event{event_id, ts_round, ts_wall, src, kind, payload}.
kind is a 10-member frozen enum. Changes require captain approval.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EventKind(str, Enum):
    """Frozen 10-kind enum (DESIGN §2.3)."""

    SAY = "say"          # PC/KP speech or declaration
    ACT = "act"          # PC action declaration
    ROLL = "roll"        # dice result (dice always precedes narration)
    CLUE = "clue"        # clue granted / revealed
    NPC = "npc"          # NPC reaction line
    SCENE = "scene"      # scene-graph delta
    CLOCK = "clock"      # time/clock ruling
    RULING = "ruling"    # KP ruling / galaxy-decision裁决单 ref
    ALERT = "alert"      # timeout/cold-field/off-track/spotlight reminder
    BOARD = "board"      # public board broadcast snapshot


FROZEN_KINDS: tuple[str, ...] = tuple(k.value for k in EventKind)


class Event(BaseModel):
    """Frozen event envelope."""

    event_id: str = Field(min_length=1)
    ts_round: int = Field(ge=0)
    ts_wall: datetime
    src: str = Field(min_length=1)  # kp | pc:<id> | agent:<state> | system
    kind: EventKind
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "src", mode="before")
    @classmethod
    def _strip_nonempty(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
        return v


def make_event(
    event_id: str,
    ts_round: int,
    ts_wall: datetime | str,
    src: str,
    kind: EventKind | str,
    payload: dict[str, Any] | None = None,
) -> Event:
    """Convenience constructor (accepts ISO-8601 string for ts_wall)."""
    if isinstance(ts_wall, str):
        ts_wall = datetime.fromisoformat(ts_wall)
    return Event(
        event_id=event_id,
        ts_round=ts_round,
        ts_wall=ts_wall,
        src=src,
        kind=EventKind(kind),
        payload=dict(payload or {}),
    )


def event_to_json(ev: Event) -> str:
    return ev.model_dump_json()


def event_from_json(raw: str) -> Event:
    return Event.model_validate_json(raw)
