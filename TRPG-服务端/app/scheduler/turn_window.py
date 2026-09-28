"""Turn window state machine (MIT).

Event-driven migration over the frozen event stream:
  IDLE -> COLLECTING (TURN_STARTED)
  COLLECTING -> CLOSED (TURN_CLOSED) | -> LATE on late submit path
  COLLECTING -> COLLECTING (ACTION_SUBMITTED / ACTION_WITHDRAWN)
  CLOSED -> RESOLVING (TURN_CHECKPOINT) | -> COLLECTING (reopen edge)
  RESOLVING -> ADVANCED (ACT_ADVANCED) | -> IDLE (next TURN_STARTED resets)
  * -> PENDING_APPROVAL when a NARRATION_PROPOSED is open (orthogonal flag)

Illegal migration raises StateMachineViolation. Deterministic: the same
event stream always derives the same machine state (see scheduler resume).
Python 3.12 compatible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.events import GameEvent

IDLE = "IDLE"
COLLECTING = "COLLECTING"
CLOSED = "CLOSED"
RESOLVING = "RESOLVING"
LATE = "LATE"
PENDING_APPROVAL = "PENDING_APPROVAL"
ADVANCED = "ADVANCED"

TERMINAL_OK = (ADVANCED,)


class StateMachineViolation(ValueError):
    """Raised on any illegal turn-window migration."""


@dataclass
class TurnWindow:
    campaign_id: str
    turn_no: int = 0
    state: str = IDLE
    submitted: dict[str, dict[str, Any]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    cursor: str = ""
    countdown_end_ts: str = ""
    pending_approvals: int = 0
    late_players: list[str] = field(default_factory=list)

    # -- explicit command-style transitions (used by scheduler) --

    def start(self, turn_no: int, countdown_end_ts: str = "") -> None:
        if self.state in (COLLECTING, CLOSED, RESOLVING):
            raise StateMachineViolation(
                "cannot start turn %d from %s (window still open)" % (turn_no, self.state))
        self.turn_no = turn_no
        self.state = COLLECTING
        self.submitted = {}
        self.order = []
        self.countdown_end_ts = countdown_end_ts
        self.cursor = "turn:%d:collecting" % turn_no
        self.late_players = []

    def submit(self, player_id: str, action: dict | None = None,
               intent: str = "", late: bool = False) -> None:
        if self.state == COLLECTING:
            self.submitted[player_id] = {"action": action or {}, "intent": intent}
        elif self.state == CLOSED and late:
            if player_id not in self.late_players:
                self.late_players.append(player_id)
            self.submitted[player_id] = {"action": action or {}, "intent": intent,
                                         "late": True}
            self.state = LATE
        else:
            raise StateMachineViolation(
                "cannot submit in %s (late=%s)" % (self.state, late))

    def withdraw(self, player_id: str) -> None:
        if self.state != COLLECTING:
            raise StateMachineViolation("cannot withdraw in %s" % self.state)
        self.submitted.pop(player_id, None)

    def close(self, order: list[str] | None = None) -> None:
        if self.state not in (COLLECTING, LATE):
            raise StateMachineViolation("cannot close from %s" % self.state)
        self.state = CLOSED
        if order is not None:
            self.order = list(order)
        else:
            self.order = sorted(self.submitted.keys())

    def checkpoint(self, cursor: str) -> None:
        if self.state not in (CLOSED, LATE, RESOLVING):
            raise StateMachineViolation("cannot checkpoint from %s" % self.state)
        self.state = RESOLVING
        self.cursor = cursor

    def advance(self) -> None:
        if self.state != RESOLVING:
            raise StateMachineViolation("cannot advance from %s" % self.state)
        self.state = ADVANCED

    # -- event-driven folding (derive machine from event stream) --

    def apply(self, ev: GameEvent) -> "TurnWindow":
        t = ev.type
        p = ev.payload
        if t == "TURN_STARTED":
            self.start(p["turn_no"], p.get("countdown_end_ts", ""))
        elif t == "ACTION_SUBMITTED":
            late = self.state == CLOSED
            self.submit(p["player_id"], p.get("action"), p.get("intent_summary", ""),
                        late=late)
        elif t == "ACTION_WITHDRAWN":
            self.withdraw(p["player_id"])
        elif t == "TURN_CLOSED":
            self.close(list(p.get("order", [])))
        elif t == "TURN_CHECKPOINT":
            self.checkpoint(p.get("cursor", ""))
        elif t == "ACT_ADVANCED":
            if self.state == RESOLVING:
                self.advance()
        elif t == "NARRATION_PROPOSED":
            self.pending_approvals += 1
        elif t in ("NARRATION_APPROVED", "NARRATION_EDITED", "NARRATION_REJECTED"):
            self.pending_approvals = max(0, self.pending_approvals - 1)
        return self

    @property
    def approval_flag(self) -> str | None:
        return PENDING_APPROVAL if self.pending_approvals > 0 else None

    def snapshot(self) -> dict[str, Any]:
        return {"campaign_id": self.campaign_id, "turn_no": self.turn_no,
                "state": self.state, "submitted": dict(self.submitted),
                "order": list(self.order), "cursor": self.cursor,
                "countdown_end_ts": self.countdown_end_ts,
                "pending_approvals": self.pending_approvals,
                "late_players": list(self.late_players)}


def fold(events: list[GameEvent], campaign_id: str) -> TurnWindow:
    tw = TurnWindow(campaign_id=campaign_id)
    for ev in events:
        tw.apply(ev)
    return tw
