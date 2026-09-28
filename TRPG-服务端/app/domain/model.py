"""TRPG aggregate roots / entities / value objects (MIT).

Pure in-memory state shaped by projector.reduce(); persistence lives in
app.store (event_store / snapshot). Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Table(Strict):
    table_id: str
    campaign_id: str
    ruleset: str
    config: dict[str, Any] = Field(default_factory=dict)


class TurnWindowState(Strict):
    campaign_id: str
    turn_no: int = 0
    state: str = "IDLE"
    submitted: dict[str, dict[str, Any]] = Field(default_factory=dict)
    order: list[str] = Field(default_factory=list)
    cursor: str = ""
    countdown_end_ts: str = ""


class ApprovalItem(Strict):
    proposal_id: str
    campaign_id: str
    text: str
    intention: str | None = None
    source: str = "agent"
    status: str = "pending"  # pending|approved|edited|rejected


class SessionState(Strict):
    campaign_id: str
    table_id: str = ""
    world_intro: str = ""
    characters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    finalized_cards: list[str] = Field(default_factory=list)
    turn: TurnWindowState | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list)
    narrations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    approvals: dict[str, ApprovalItem] = Field(default_factory=dict)
    infos: dict[str, dict[str, Any]] = Field(default_factory=dict)
    clues: dict[str, dict[str, Any]] = Field(default_factory=dict)
    branches: list[dict[str, Any]] = Field(default_factory=list)
    transcripts: list[dict[str, Any]] = Field(default_factory=list)
    transcript_ready: bool = False
    summaries: list[dict[str, Any]] = Field(default_factory=list)
    roles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    votes: list[dict[str, Any]] = Field(default_factory=list)
    truth: dict[str, Any] = Field(default_factory=dict)
    npc_lines: dict[str, str] = Field(default_factory=dict)
    maps: dict[str, dict[str, Any]] = Field(default_factory=dict)
    current_scene: str = ""
    scene_trace: list[dict[str, Any]] = Field(default_factory=list)
    # ---- M3 (additive, T6): 私聊系统状态 ----
    # chat_mode: 主持人调控四态（服务端权威）；chats: 私聊消息历史（append-only）。
    chat_mode: str = "chat_enabled"
    chats: list[dict[str, Any]] = Field(default_factory=list)
    # ---- T7 (additive): M4/M5/M6/M7/M8 状态（全部带默认值，向后兼容） ----
    npc_tendencies: dict[str, dict[str, Any]] = Field(default_factory=dict)
    combat: dict[str, Any] = Field(default_factory=dict)
    checkpoints: dict[str, dict[str, Any]] = Field(default_factory=dict)
    timeline_branches: list[dict[str, Any]] = Field(default_factory=list)
    npc_public_infos: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    dsh_loop: dict[str, Any] = Field(default_factory=dict)
    # T13 (additive): campaign phase machine (lobby/configuring/running/paused/ended)
    phase: str = "lobby"
    started_seq: int | None = None
    act_no: int = 0
    archived: bool = False
    last_seq: int = -1

    def ensure_turn(self, campaign_id: str) -> TurnWindowState:
        if self.turn is None:
            self.turn = TurnWindowState(campaign_id=campaign_id)
        return self.turn


def new_session(campaign_id: str) -> SessionState:
    return SessionState(campaign_id=campaign_id)