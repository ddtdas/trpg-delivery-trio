"""T7 (additive): M8 DSH 全程 Loop (MIT).

Background asyncio loops, one per campaign, with a global resident cap
(default 3, configurable). Idle campaigns HOLD (no token spend); decision
points park in WAIT_HOST (no automatic writes).

Lifecycle per campaign:
    IDLE -> OBSERVE -> COMPUTE -> PROPOSE -> WAIT_HOST -> APPLY -> OBSERVE

Loop state persists to campaigns/<id>/.dsh/loop_state.json so the board
and dashboard can read phase/decision without touching the loop process.

Resource rules (captain ruling 2026-09-28):
  * one task per campaign; global resident cap (default 3); excess queues;
  * HOLD when idle: no LLM calls, no token spend;
  * WAIT_HOST stops all computation until the host responds;
  * failures never write events on their own (gateway degradation is
    read-only and the deterministic fallback is pure computation).
Python 3.12 compatible.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import APP_ROOT


def _max_resident() -> int:
    """Resident loop cap (default 3); wizard_config may override."""
    try:
        from app.app_core.coc7_rules import load_wizard_config
        cfg = load_wizard_config().get("dsh_loop")
        if isinstance(cfg, dict) and cfg.get("max_resident"):
            return max(1, int(cfg["max_resident"]))
    except Exception:  # noqa: BLE001
        pass
    return 3


_REGISTRY: dict[str, "DSHLoop"] = {}
_LOOP_LOCK: asyncio.Lock | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DSHLoop:
    """One campaign background loop (phase machine + persistence)."""

    def __init__(self, campaign_id: str) -> None:
        self.campaign_id = campaign_id
        self.phase = "IDLE"
        self.decision: dict[str, Any] = {}
        self.running = False
        self.next_step = ""
        self.confidence = 0.0
        self.rationale = ""
        self.needs_host = False
        self._task: asyncio.Task | None = None
        self._wake: asyncio.Event = asyncio.Event()

    def _persist(self) -> None:
        try:
            p = APP_ROOT / "campaigns" / self.campaign_id / ".dsh" / "loop_state.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({
                "campaign_id": self.campaign_id,
                "phase": self.phase,
                "decision": self.decision,
                "next_step": self.next_step,
                "confidence": self.confidence,
                "rationale": self.rationale,
                "needs_host": self.needs_host,
                "updated_at": _now(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001 — persistence is best-effort
            pass

    def poke(self) -> bool:
        """Wake the loop so it recomputes on the next tick."""
        self._wake.set()
        return self.running

    async def _observe(self) -> list[Any]:
        try:
            from app.web import rest as rest_mod
            store = rest_mod._store()
            await store.init()
            return await store.replay(self.campaign_id)
        except Exception:  # noqa: BLE001
            return []

    async def _compute(self, events: list[Any]) -> None:
        """Deterministic COMPUTE (no LLM): derive next step + decision point."""
        state = None
        try:
            from app.web import rest as rest_mod
            state = rest_mod.project(events, self.campaign_id)
        except Exception:  # noqa: BLE001
            pass
        if state is None:
            self.phase = "HOLD"
            self._persist()
            return
        scene = getattr(state, "current_scene", "") or ""
        combat = getattr(state, "combat", {}) or {}
        self.needs_host = False
        self.decision = {}
        if combat and combat.get("pending_resolutions"):
            self.phase = "WAIT_HOST"
            self.needs_host = True
            self.decision = {"kind": "combat_approval",
                             "round": combat.get("round"),
                             "prompt": "战斗第 %s 轮结算待主持人批准" % combat.get("round")}
        else:
            pending = []
            for nid, tend in (getattr(state, "npc_tendencies", {}) or {}).items():
                if (tend or {}).get("status") == "pending":
                    pending.append(nid)
            if pending:
                self.phase = "WAIT_HOST"
                self.needs_host = True
                self.decision = {"kind": "npc_tendency",
                                 "npc_ids": pending,
                                 "prompt": "NPC 倾向待主持人批准: %s" % ", ".join(pending)}
            else:
                self.phase = "HOLD" if not events else "OBSERVE"
                self.next_step = ("当前场景 %s：建议推进下一分支或勘察未探索地区" % scene)
                self.confidence = 0.5 if events else 0.0
                self.rationale = "基于事件流投影的确定性建议（未调用 LLM）"
        self._persist()

    async def _run(self) -> None:
        while True:
            self.running = True
            try:
                events = await self._observe()
                await self._compute(events)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                self.phase = "HOLD"
                self._persist()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
            finally:
                self._wake.clear()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="dsh-loop")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.running = False


def _lock() -> asyncio.Lock:
    global _LOOP_LOCK
    if _LOOP_LOCK is None:
        _LOOP_LOCK = asyncio.Lock()
    return _LOOP_LOCK


async def ensure_loop(campaign_id: str) -> DSHLoop:
    """Start (or reuse) the loop for a campaign, honouring the resident cap."""
    async with _lock():
        loop = _REGISTRY.get(campaign_id)
        if loop is not None:
            return loop
        loop = DSHLoop(campaign_id)
        _REGISTRY[campaign_id] = loop
        if len(_REGISTRY) <= _max_resident():
            await loop.start()
        return loop


def poke(campaign_id: str) -> bool:
    loop = _REGISTRY.get(campaign_id)
    if loop is not None:
        return loop.poke()
    return False


def registry_snapshot() -> dict[str, Any]:
    return {cid: {"phase": lp.phase, "running": lp.running}
            for cid, lp in _REGISTRY.items()}
