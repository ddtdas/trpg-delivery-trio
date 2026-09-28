"""Table manager: create table / seat players / bind cards (MIT).

Thin facade over the command bus + projector state; owns no separate
storage. Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any

from app.app_core.command_bus import CommandBus
from app.domain.character import CharacterCard, validate_card


class TableError(ValueError):
    pass


class TableManager:
    def __init__(self, bus: CommandBus, table_id: str = "tbl_demo",
                 ruleset: str = "coc7") -> None:
        self.bus = bus
        self.table_id = table_id
        self.ruleset = ruleset
        self.seats: dict[str, str] = {}  # player_id -> card_id
        self.created = False

    async def create_table(self, campaign_id: str, actor: str = "kp",
                           window_sec: int = 120) -> dict:
        # T26: table creation is registry-only (no TURN_STARTED) so the
        # first real start_turn opens COLLECTING from IDLE exactly once.
        # The explicit TABLE_CREATED event lands in T15 with MCP wiring.
        self.created = True
        return {"table_id": self.table_id, "campaign_id": campaign_id,
                "ruleset": self.ruleset, "window_sec": window_sec}

    def seat(self, player_id: str, card: CharacterCard | dict) -> dict:
        if isinstance(card, dict):
            card = CharacterCard(**card)
        report = validate_card(card)
        if not report.ok:
            raise TableError("illegal card: %s" % report.errors)
        self.seats[player_id] = card.card_id
        return {"player_id": player_id, "card_id": card.card_id}

    def binding(self, player_id: str) -> str | None:
        return self.seats.get(player_id)

    def roster(self) -> dict[str, str]:
        return dict(self.seats)

    async def bind_and_announce(self, campaign_id: str, player_id: str,
                                card: CharacterCard | dict,
                                actor: str = "kp") -> dict[str, Any]:
        seat = self.seat(player_id, card)
        # Binding itself is local (seat map); announcement goes through the
        # bus as a public info reveal so every client sees the same roster.
        data = card.model_dump(mode="json") if isinstance(card, CharacterCard) \
            else dict(card)
        receipt = await self.bus.dispatch(
            "distribute_info",
            {"campaign_id": campaign_id, "info_id": "seat:%s" % player_id,
             "scope": "public",
             "body_ref": "card:%s" % data.get("card_id", seat["card_id"])},
            actor=actor, key="bind:%s:%s" % (campaign_id, player_id))
        return {"seat": seat, "receipt": receipt}
