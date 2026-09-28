"""TRPG WS frame codec - FROZEN (MIT).

Source: docs/contracts/runtime-contract.md v1.0 (t4 frozen).
Discipline: Server->Client 8 kinds, Client->Server 6 kinds, exact fields -
no additions, no removals. PING is the heartbeat frame (§4), outside the 8+6.
Any change requires a contract change (merge back + broadcast).
Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = "v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProtocolError(ValueError):
    """Raised when a WS frame has an unknown kind or bad fields."""


# ---- Server -> Client (8 kinds; all carry seq/campaign_id/scope/ts) ----

ServerKind = Literal[
    "STATE_DELTA",
    "TURN_UPDATED",
    "NARRATION_PENDING",
    "NARRATION_APPROVED",
    "WHISPER",
    "INFO_REVEALED",
    "BRANCH_TAKEN",
    "JOB_STATUS",
]

SERVER_KINDS: tuple[str, ...] = (
    "STATE_DELTA",
    "TURN_UPDATED",
    "NARRATION_PENDING",
    "NARRATION_APPROVED",
    "WHISPER",
    "INFO_REVEALED",
    "BRANCH_TAKEN",
    "JOB_STATUS",
)

TurnState = Literal["COLLECTING", "CLOSING", "RESOLVING", "DISTRIBUTED", "ADVANCED"]
JobStatus = Literal["queued", "running", "done", "failed"]

REQUIRED_SCOPE: dict[str, str] = {
    "NARRATION_PENDING": "kp",
    "NARRATION_APPROVED": "public",
    "WHISPER": "whisper",
    "INFO_REVEALED": "condition",
    "BRANCH_TAKEN": "public",
    "JOB_STATUS": "actor",
}


class SubmittedEntry(StrictModel):
    player_id: str
    intent: str | None = None


class TurnInfo(StrictModel):
    state: TurnState
    submitted: list[SubmittedEntry] = Field(default_factory=list)
    total: int
    countdown_end_ts: int


class ProposalInfo(StrictModel):
    id: str
    text: str
    intention: str | None = None
    source: str | None = None


class NarrationInfo(StrictModel):
    id: str
    text: str


class PacketInfo(StrictModel):
    info_id: str
    body: str


class BranchInfo(StrictModel):
    node_id: str
    label: str
    consequences: list[Any] = Field(default_factory=list)


class JobInfo(StrictModel):
    job_id: str
    status: JobStatus
    result_ref: str | None = None


class ServerFrame(StrictModel):
    kind: ServerKind
    seq: int = Field(ge=0)
    campaign_id: str
    scope: str
    ts: int
    delta: dict[str, Any] | None = None
    turn: TurnInfo | None = None
    proposal: ProposalInfo | None = None
    narration: NarrationInfo | None = None
    targets: list[str] | None = None
    packet: PacketInfo | None = None
    branch: BranchInfo | None = None
    actor_id: str | None = None
    job: JobInfo | None = None

    def model_post_init(self, _ctx: Any) -> None:
        required = REQUIRED_SCOPE.get(self.kind)
        if required is not None and self.scope != required:
            raise ValueError(
                "scope for %s must be %r, got %r" % (self.kind, required, self.scope))
        need: dict[str, tuple[str, ...]] = {
            "STATE_DELTA": ("delta",),
            "TURN_UPDATED": ("turn",),
            "NARRATION_PENDING": ("proposal",),
            "NARRATION_APPROVED": ("narration",),
            "WHISPER": ("targets", "packet"),
            "INFO_REVEALED": ("packet",),
            "BRANCH_TAKEN": ("branch",),
            "JOB_STATUS": ("actor_id", "job"),
        }
        for field in need[self.kind]:
            if getattr(self, field) is None:
                raise ValueError("%s requires field %r" % (self.kind, field))


class PingFrame(StrictModel):
    """Heartbeat: server every 15s PING{ts} (contract §4)."""

    kind: Literal["PING"] = "PING"
    ts: int


# ---- Client -> Server (6 kinds; all carry campaign/actor/req_id) ----

ClientKind = Literal[
    "SUBMIT_ACTION",
    "START_TURN",
    "CLOSE_WINDOW",
    "APPROVE_NARRATION",
    "COMMAND",
    "AUDIO_CHUNK",
]

CLIENT_KINDS: tuple[str, ...] = (
    "SUBMIT_ACTION",
    "START_TURN",
    "CLOSE_WINDOW",
    "APPROVE_NARRATION",
    "COMMAND",
    "AUDIO_CHUNK",
)

NarrationDecision = Literal["approve", "edit", "reject"]
CommandType = Literal["roll_check", "map", "quick"]


class ActorRef(StrictModel):
    id: str
    token: str | None = None


class CommandBody(StrictModel):
    type: CommandType
    payload: dict[str, Any] = Field(default_factory=dict)


class ClientFrame(StrictModel):
    kind: ClientKind
    campaign: str
    actor: ActorRef
    req_id: str
    action: Any | None = None
    intent: str | None = None
    window_sec: int | None = None
    proposal_id: str | None = None
    decision: NarrationDecision | None = None
    edited_text: str | None = None
    cmd: CommandBody | None = None
    player_id: str | None = None
    mime: Literal["audio/opus"] | None = None
    chunk_base64: str | None = None
    seq: int | None = None

    def model_post_init(self, _ctx: Any) -> None:
        need: dict[str, tuple[str, ...]] = {
            "SUBMIT_ACTION": ("action",),
            "START_TURN": ("window_sec",),
            "CLOSE_WINDOW": (),
            "APPROVE_NARRATION": ("proposal_id", "decision"),
            "COMMAND": ("cmd",),
            "AUDIO_CHUNK": ("player_id", "mime", "chunk_base64", "seq"),
        }
        for field in need[self.kind]:
            if getattr(self, field) is None:
                raise ValueError("%s requires field %r" % (self.kind, field))
        if self.kind == "APPROVE_NARRATION" and self.decision == "edit" \
                and not self.edited_text:
            raise ValueError("APPROVE_NARRATION decision=edit requires edited_text")


def encode_server(frame: ServerFrame) -> dict[str, Any]:
    return frame.model_dump(mode="json", exclude_none=True)


def decode_server(raw: dict[str, Any]) -> ServerFrame:
    try:
        return ServerFrame(**raw)
    except Exception as exc:
        raise ProtocolError("bad server frame: %s" % exc) from exc


def encode_client(frame: ClientFrame) -> dict[str, Any]:
    return frame.model_dump(mode="json", exclude_none=True)


def decode_client(raw: dict[str, Any]) -> ClientFrame:
    if not isinstance(raw, dict) or raw.get("kind") not in CLIENT_KINDS:
        raise ProtocolError("unknown client kind: %r" % (
            raw.get("kind") if isinstance(raw, dict) else raw))
    try:
        return ClientFrame(**raw)
    except Exception as exc:
        raise ProtocolError("bad client frame: %s" % exc) from exc


def decode_ping(raw: dict[str, Any]) -> PingFrame:
    try:
        return PingFrame(**raw)
    except Exception as exc:
        raise ProtocolError("bad PING frame: %s" % exc) from exc
