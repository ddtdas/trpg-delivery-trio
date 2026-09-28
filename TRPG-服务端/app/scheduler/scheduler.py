"""Scheduler core: serial single-writer over the event stream (MIT).

Owns: command_bus dispatch ordering, turn-window folding, crash resume
(restart replays the stream and refolds the machine). The scheduler
never invents events; it routes validated commands to the bus.
Python 3.12 compatible.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.app_core.command_bus import CommandBus
from app.app_core.query_bus import QueryBus
from app.domain.model import SessionState, new_session
from app.scheduler.branch_guard import BranchGuard
from app.scheduler.turn_window import TurnWindow, fold
from app.store.event_store import EventStore
from app.store.projector import project


class Scheduler:
    def __init__(self, store: EventStore, campaign_id: str,
                 guard: BranchGuard | None = None) -> None:
        self.store = store
        self.campaign_id = campaign_id
        self.guard = guard or BranchGuard()
        self.bus = CommandBus(store, campaign_id, self.guard)
        self.state: SessionState = new_session(campaign_id)
        self.window = TurnWindow(campaign_id=campaign_id)
        self._lock = asyncio.Lock()

    async def boot(self) -> "Scheduler":
        """Crash resume: replay full stream, refold state + window."""
        await self.store.init()
        events = await self.store.replay(self.campaign_id)
        self.state = project(events, self.campaign_id)
        self.window = fold(events, self.campaign_id)
        return self

    async def dispatch(self, name: str, params: dict[str, Any], actor: str,
                       key: str | None = None,
                       causal: list[str] | None = None) -> dict[str, Any]:
        async with self._lock:
            params = dict(params or {})
            params.setdefault("campaign_id", self.campaign_id)
            receipt = await self.bus.dispatch(name, params, actor, key=key,
                                              causal=causal)
            events = await self.store.replay(self.campaign_id)
            self.state = project(events, self.campaign_id)
            self.window = fold(events, self.campaign_id)
            return receipt

    def queries(self) -> QueryBus:
        return QueryBus(self.state)

    def status(self) -> dict[str, Any]:
        return {"campaign_id": self.campaign_id,
                "last_seq": self.state.last_seq,
                "window": self.window.snapshot()}
