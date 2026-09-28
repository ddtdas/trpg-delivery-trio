"""TRPG event dictionary - FROZEN (MIT).

Source: trpg_run/docs/04_event_protocol_spec.md (event dictionary full set).
Discipline: every payload JSON-serializable, no functions;
actor is a free-form id string (docs: player_id / kp_id / system);
approved_by non-empty only for approval-class events;
causal is the causal chain (loop-guard).

Adding a new type requires a contract change (merge back + broadcast).
Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EVENT_VERSION = "v1"

Scope = Literal["public", "whisper", "condition"]
CheckLevel = Literal["crit", "success", "hard", "extreme", "fail", "fumble"]
NarrationDecision = Literal["approve", "edit", "reject"]
NarrationSource = Literal["agent", "dsh"]
MapOp = Literal["move", "add_token", "set_fog", "set_status", "set_light", "set_scene"]
JobStatus = Literal["queued", "running", "done", "failed"]
TranscriptSource = Literal["cloud", "local", "import", "stt"]  # "stt" additive (EX-1, 保留既有值)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- table & campaign ----

class TableCreated(StrictModel):
    table_id: str
    campaign_id: str
    ruleset: str
    table_token: str
    config: dict[str, Any] = Field(default_factory=dict)


class TableConfigUpdated(StrictModel):
    table_id: str
    diff: dict[str, Any] = Field(default_factory=dict)


class CampaignStarted(StrictModel):
    campaign_id: str
    table_id: str
    world_intro_ref: str


class CampaignArchived(StrictModel):
    campaign_id: str
    reason: str
    summary_ref: str


# ---- character (card / portrait / world intro) ----

class CharacterCreated(StrictModel):
    card_id: str
    player_id: str
    ruleset: str
    card: dict[str, Any] = Field(default_factory=dict)


class CardReverted(StrictModel):
    card_id: str
    from_step: str
    to_step: str
    reason: str


class CardFinalized(StrictModel):
    card_id: str
    validation_report_ref: str
    portrait_ref: str | None = None


class PortraitReady(StrictModel):
    card_id: str
    image_ref: dict[str, Any] = Field(default_factory=dict)


class WorldIntroSet(StrictModel):
    campaign_id: str
    text: str
    editor: str


# ---- turn & action ----

class TurnStarted(StrictModel):
    campaign_id: str
    turn_no: int
    window_sec: int
    countdown_end_ts: str


class ActionSubmitted(StrictModel):
    campaign_id: str
    turn_no: int
    player_id: str
    action: dict[str, Any] = Field(default_factory=dict)
    intent_summary: str


class ActionWithdrawn(StrictModel):
    campaign_id: str
    turn_no: int
    player_id: str


class TurnClosed(StrictModel):
    campaign_id: str
    turn_no: int
    submit_map: dict[str, Any] = Field(default_factory=dict)
    order: list[str] = Field(default_factory=list)


class TurnCheckpoint(StrictModel):
    campaign_id: str
    turn_no: int
    cursor: str
    resolved_ids: list[str] = Field(default_factory=list)


class ActAdvanced(StrictModel):
    campaign_id: str
    act_no: int
    act_name: str


# ---- check ----

class CheckResolved(StrictModel):
    campaign_id: str
    turn_no: int
    card_id: str
    target: str
    difficulty: int
    rolled: list[int] = Field(default_factory=list)
    total: int
    level: CheckLevel
    seed: str
    summary: str


# ---- narration (approval chain) ----

class NarrationProposed(StrictModel):
    campaign_id: str
    proposal_id: str
    text: str
    intention: str | None = None
    reasoning: str
    source: NarrationSource


class NarrationApproved(StrictModel):
    proposal_id: str
    text: str


class NarrationEdited(StrictModel):
    proposal_id: str
    text: str
    diff: dict[str, Any] = Field(default_factory=dict)


class NarrationRejected(StrictModel):
    proposal_id: str
    reason: str


# ---- info distribution ----

class InfoRevealed(StrictModel):
    campaign_id: str
    info_id: str
    scope: Scope
    targets: list[str] = Field(default_factory=list)
    body_ref: str


class ClueGranted(StrictModel):
    campaign_id: str
    clue_id: str
    ref: str
    condition_met: bool


# ---- plot (event graph / branch) ----

class BranchTaken(StrictModel):
    campaign_id: str
    node_id: str
    edge_id: str
    label: str
    consequences: list[dict[str, Any]] = Field(default_factory=list)


class BranchOverridden(StrictModel):
    campaign_id: str
    node_id: str
    reason: str


class EventInjected(StrictModel):
    campaign_id: str
    node_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    dry_run_result: dict[str, Any] = Field(default_factory=dict)


# ---- transcript & session ----

class TranscriptSegment(StrictModel):
    text: str
    t0: float
    t1: float
    speaker: str | None = None


class TranscriptAppended(StrictModel):
    campaign_id: str
    seg: TranscriptSegment
    source: TranscriptSource


class TranscriptReady(StrictModel):
    campaign_id: str
    transcript_ref: str
    aligned: bool


class SessionSummarized(StrictModel):
    campaign_id: str
    summary_ref: str
    hooks: list[str] = Field(default_factory=list)
    next_preview: str


class SnapshotSaved(StrictModel):
    campaign_id: str
    snapshot_ref: str
    event_seq_at: int


class SnapshotLoaded(StrictModel):
    campaign_id: str
    snapshot_ref: str
    resume_cursor: str


# ---- murder mystery (P6) ----

class RoleAssigned(StrictModel):
    campaign_id: str
    player_id: str
    role_ref: str
    secret_ref: str


class EvidenceDealt(StrictModel):
    campaign_id: str
    act_no: int
    location: str
    clue_id: str
    scope: Scope


class VoteCast(StrictModel):
    campaign_id: str
    player_id: str
    target_player_id: str


class TruthRevealed(StrictModel):
    campaign_id: str
    truth_tree_ref: str
    timeline_ref: str


# ---- npc & map ----

class NpcActProposed(StrictModel):
    campaign_id: str
    npc_id: str
    lines: list[str] = Field(default_factory=list)
    context_ref: str


class NpcActApproved(StrictModel):
    campaign_id: str
    npc_id: str
    line: str


class MapUpdated(StrictModel):
    campaign_id: str
    map_id: str
    op: MapOp
    target: str
    delta: dict[str, Any] = Field(default_factory=dict)


class SceneUpdated(StrictModel):
    """T1 (additive): 场景推进事件 (多线叙事)。"""
    campaign_id: str
    scene_id: str
    prev_scene_id: str | None = None
    edge_id: str | None = None
    map_id: str | None = None
    reason: str = ""




# ---- M3 (additive, T6): 私聊系统 ----
# 私聊四态（主持人调控）: chat_enabled(能私聊+公共) / chat_disabled(不能私聊, 公共可) /
# public_only(能交流=公共, 不能私聊) / all_disabled(不能交流)。服务端权威门控。

ChatMode = Literal["chat_enabled", "chat_disabled", "public_only", "all_disabled"]


class ChatPolicyUpdated(StrictModel):
    """T6-3 (unified): chat policy event (renamed from ChatModeSet)."""
    campaign_id: str
    mode: ChatMode
    actor: str


# Legacy alias: pre-unification events used ChatModeSet model under the
# CHAT_MODE_SET type; keep the class name importable for compat.
ChatModeSet = ChatPolicyUpdated


class PrivateMsg(StrictModel):
    campaign_id: str
    from_player: str
    to_players: list[str] = Field(default_factory=list)
    text: str
    room_ref: str | None = None



# ---- T7 (additive): combat / tendency / snapshot / timeline / npc-info ----

class CombatStarted(StrictModel):
    campaign_id: str
    combat_id: str
    participants: list[dict[str, Any]] = Field(default_factory=list)
    start_seq: int = 0


class CombatRoundProposed(StrictModel):
    campaign_id: str
    combat_id: str
    round: int
    resolutions: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "pending_approval"


class CombatRoundApproved(StrictModel):
    campaign_id: str
    combat_id: str
    round: int
    resolutions: list[dict[str, Any]] = Field(default_factory=list)
    approved_by: str


class CombatRoundRejected(StrictModel):
    campaign_id: str
    combat_id: str
    round: int
    resolutions: list[dict[str, Any]] = Field(default_factory=list)
    reason: str = ""
    approved_by: str = ""


class CombatEnded(StrictModel):
    campaign_id: str
    combat_id: str
    end_seq: int = 0


class NpcTendencyUpdated(StrictModel):
    campaign_id: str
    npc_id: str
    tendency: dict[str, Any] = Field(default_factory=dict)
    source: str = "ai"  # "ai" | "host"


class NpcTendencyApproved(StrictModel):
    campaign_id: str
    npc_id: str
    tendency: dict[str, Any] = Field(default_factory=dict)
    approved_by: str


class SnapshotCreated(StrictModel):
    campaign_id: str
    snapshot_id: str
    kind: str = "auto"  # "auto" | "manual"
    seq: int
    label: str = ""
    reason: str = ""
    fingerprint: str = ""


class CheckpointTaken(StrictModel):
    campaign_id: str
    checkpoint_id: str
    kind: str = "auto"  # "auto" | "manual"
    seq: int
    label: str = ""
    reason: str = ""
    auto: bool = False


class TimelineRollback(StrictModel):
    campaign_id: str
    target_seq: int
    branch_mark: str = ""
    reason: str = ""
    actor: str = "kp"


class NpcInfoGenerated(StrictModel):
    campaign_id: str
    player_id: str
    npc_ids: list[str] = Field(default_factory=list)
    public_infos: list[dict[str, Any]] = Field(default_factory=list)



class PhaseUpdated(StrictModel):
    """T13 (additive): campaign phase change (lobby/configuring/running/paused/ended)."""
    campaign_id: str
    phase: str
    started_seq: int | None = None
    actor: str = "kp"
    reason: str = ""

PAYLOAD_MODELS: dict[str, type[StrictModel]] = {
    "TABLE_CREATED": TableCreated,
    "TABLE_CONFIG_UPDATED": TableConfigUpdated,
    "CAMPAIGN_STARTED": CampaignStarted,
    "CAMPAIGN_ARCHIVED": CampaignArchived,
    "CHARACTER_CREATED": CharacterCreated,
    "CARD_REVERTED": CardReverted,
    "CARD_FINALIZED": CardFinalized,
    "PORTRAIT_READY": PortraitReady,
    "WORLD_INTRO_SET": WorldIntroSet,
    "TURN_STARTED": TurnStarted,
    "ACTION_SUBMITTED": ActionSubmitted,
    "ACTION_WITHDRAWN": ActionWithdrawn,
    "TURN_CLOSED": TurnClosed,
    "TURN_CHECKPOINT": TurnCheckpoint,
    "ACT_ADVANCED": ActAdvanced,
    "CHECK_RESOLVED": CheckResolved,
    "NARRATION_PROPOSED": NarrationProposed,
    "NARRATION_APPROVED": NarrationApproved,
    "NARRATION_EDITED": NarrationEdited,
    "NARRATION_REJECTED": NarrationRejected,
    "INFO_REVEALED": InfoRevealed,
    "CLUE_GRANTED": ClueGranted,
    "BRANCH_TAKEN": BranchTaken,
    "BRANCH_OVERRIDDEN": BranchOverridden,
    "EVENT_INJECTED": EventInjected,
    "TRANSCRIPT_APPENDED": TranscriptAppended,
    "TRANSCRIPT_READY": TranscriptReady,
    "SESSION_SUMMARIZED": SessionSummarized,
    "SNAPSHOT_SAVED": SnapshotSaved,
    "SNAPSHOT_LOADED": SnapshotLoaded,
    "ROLE_ASSIGNED": RoleAssigned,
    "EVIDENCE_DEALT": EvidenceDealt,
    "VOTE_CAST": VoteCast,
    "TRUTH_REVEALED": TruthRevealed,
    "NPC_ACT_PROPOSED": NpcActProposed,
    "NPC_ACT_APPROVED": NpcActApproved,
    "MAP_UPDATED": MapUpdated,
    "SCENE_UPDATED": SceneUpdated,
    "CHAT_POLICY_UPDATED": ChatPolicyUpdated,
    "CHAT_MODE_SET": ChatPolicyUpdated,  # legacy alias (T6-3 unified)
    "PRIVATE_MSG": PrivateMsg,
    "COMBAT_STARTED": CombatStarted,
    "COMBAT_ROUND_PROPOSED": CombatRoundProposed,
    "COMBAT_ROUND_APPROVED": CombatRoundApproved,
    "COMBAT_ROUND_REJECTED": CombatRoundRejected,
    "COMBAT_ENDED": CombatEnded,
    "NPC_TENDENCY_UPDATED": NpcTendencyUpdated,
    "NPC_TENDENCY_APPROVED": NpcTendencyApproved,
    "SNAPSHOT_CREATED": SnapshotCreated,
    "CHECKPOINT_TAKEN": CheckpointTaken,
    "TIMELINE_ROLLBACK": TimelineRollback,
    "NPC_INFO_GENERATED": NpcInfoGenerated,
    "PHASE_UPDATED": PhaseUpdated,
}

EVENT_TYPES: tuple[str, ...] = tuple(sorted(PAYLOAD_MODELS.keys()))

APPROVAL_EVENT_TYPES: frozenset[str] = frozenset({
    "NARRATION_APPROVED",
    "NARRATION_EDITED",
    "NARRATION_REJECTED",
    "NPC_ACT_APPROVED",
    "CARD_FINALIZED",
    "COMBAT_ROUND_APPROVED",
    "NPC_TENDENCY_APPROVED",
})


class GameEvent(BaseModel):
    """Envelope: seq/campaign/type/payload/actor/approved_by/ts/causal."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    campaign_id: str
    type: str
    payload: dict[str, Any]
    actor: str
    approved_by: str | None = None
    ts: str
    causal: list[str] = Field(default_factory=list)
    version: str = EVENT_VERSION

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in PAYLOAD_MODELS:
            raise ValueError("unknown event type: %r" % v)
        return v

    def typed_payload(self) -> StrictModel:
        return PAYLOAD_MODELS[self.type](**self.payload)

    def model_post_init(self, _ctx: Any) -> None:
        # Validate payload shape eagerly so bad events fail fast.
        self.typed_payload()
        if self.approved_by is not None and self.type not in APPROVAL_EVENT_TYPES:
            raise ValueError("approved_by only allowed on approval-class events")


def make_event(
    seq: int,
    campaign_id: str,
    type: str,
    payload: dict[str, Any] | StrictModel,
    actor: str,
    ts: str,
    approved_by: str | None = None,
    causal: list[str] | None = None,
) -> GameEvent:
    if isinstance(payload, StrictModel):
        payload = payload.model_dump(mode="json")
    return GameEvent(
        seq=seq,
        campaign_id=campaign_id,
        type=type,
        payload=payload,
        actor=actor,
        ts=ts,
        approved_by=approved_by,
        causal=list(causal or []),
    )


def event_to_json(ev: GameEvent) -> str:
    return ev.model_dump_json()


def event_from_json(raw: str) -> GameEvent:
    return GameEvent.model_validate_json(raw)