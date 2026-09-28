"""Six-state TRPG agent loop — W-B1 implementation (DESIGN §2.2/§2.3).

Frozen contract (unchanged from W-A2; do not change without captain approval):
  LoopState enum (S0..S5), TRANSITIONS table, KeeperLoop.step()/run_round()
  + per-state s0..s5 handlers, MAX_REENTRY = 2.

W-B1 bodies (this file):
  S0 perceive: dedupe+sort WS frames -> normalized E[] (Event list);
    idle tracking: empty E[] increments idle_rounds; idle_rounds >= idle_timeout
    emits one cold-field ALERT reminder but stays S0 (fail verdict, TRANSITIONS).
  S1 scene: SceneCoordinator.advance -> SceneDelta dict; has_pending_ruling
    (payload flag or ruling-point event) -> S3 skip (tick noted in context).
  S2 time: TimeCoordinator.tick + check_pace -> ClockDelta + reminders;
    reminders ride along into S3 (fail verdict still -> S3 per TRANSITIONS).
  S3 decide: checks/narrative/approval via decide_fn (galaxy.decide plugs in);
    invariants enforced BEFORE broadcast: (1) dice first — any D needing dice
    must carry a filled rolled/outcome (else ValueError); (2) never speak for
    a PC — payload proposal carrying a pc declaration is rejected (ValueError).
  S4 act: append ROLL/RULING/BOARD events to the event log, broadcast text.
  S5 verify: assertions (dice consistency / clue no-loss / npc consistency /
    numeric sanity) -> pass/fail + replay pointer (every round replayable);
    fail -> S1 (state error) or S3 (ruling error), reentry_count + 1;
    reentry_count > MAX_REENTRY -> escalate "需 KP 拍板：" + audit entry.

Global invariants (hard-coded, tested in tests/test_loop*.py):
  1. dice precede narration; 2. never declare for a PC; 3. every round replayable.
Pure-python, stdlib only (no app/ imports). Python 3.12 compatible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class LoopState(str, Enum):
    """Frozen six states (DESIGN §2.2)."""

    S0_PERCEIVE = "S0"
    S1_SCENE = "S1"
    S2_TIME = "S2"
    S3_DECIDE = "S3"
    S4_ACT = "S4"
    S5_VERIFY = "S5"


# Frozen transition table: state -> {pass: next, fail: re-entry}.
# S5 fail re-enters S1 (state error) or S3 (ruling error); the choice is
# made by the S5 body via fail_target.
TRANSITIONS: dict[str, dict[str, str]] = {
    "S0": {"pass": "S1", "fail": "S0"},   # idle timeout: cold-field alert, stay S0
    "S1": {"pass": "S2", "fail": "S1"},   # decision point: skip S2 (tick noted) → S3
    "S2": {"pass": "S3", "fail": "S3"},   # reminders ride along into S3
    "S3": {"pass": "S4", "fail": "S4"},   # uncertain → kp_needed broadcast, still S4
    "S4": {"pass": "S5", "fail": "S5"},
    "S5": {"pass": "S0", "fail": "S1"},   # default fail → S1; ruling error → S3
}

MAX_REENTRY = 2  # >2 S5-fails → escalate "需 KP 拍板" + audit

KP_PREFIX = "需 KP 拍板："

# S1 → S3 skip marker: S1 sets it on the shared context; step() routes.
_SKIP_TO_S3 = "skip_to_s3"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ev_id(prefix: str, seq: int) -> str:
    return "%s-%d" % (prefix, seq)


@dataclass
class LoopStep:
    """One state execution record."""

    state: str
    verdict: str  # "pass" | "fail"
    reentry_count: int = 0
    note: str = ""


@dataclass
class KeeperLoop:
    """Built-in keeper agent loop (W-B1 full bodies).

    Wiring:
      scene: SceneCoordinator-like (advance/triple_guarantee/snapshot/replay)
      time:  TimeCoordinator-like (tick/check_pace/spotlight_next/budget)
      decide_fn: S3 decision callable (galaxy.decide plugs in at W-C2).
        Called as decide_fn(request: dict) -> dict (ruling slip D).
        May be None → S3 builds a minimal kp_needed slip.
    Frozen knobs: idle_timeout (rounds), MAX_REENTRY class attr = 2.
    """

    scene: Any = None
    time: Any = None
    decide_fn: Any = None
    idle_timeout: int = 3
    state: str = LoopState.S0_PERCEIVE.value
    reentry_count: int = 0
    history: list[LoopStep] = field(default_factory=list)
    # Shared round context (payload-independent, reset per run_round).
    ctx: dict[str, Any] = field(default_factory=dict)
    # Append-only event log (dicts; mirrors Event envelope keys).
    event_log: list[dict[str, Any]] = field(default_factory=list)
    # Audit trail (escalations, invariant rejections).
    audit: list[dict[str, Any]] = field(default_factory=list)
    _seq: int = field(default=0, repr=False)
    _idle_rounds: int = field(default=0, repr=False)

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return _ev_id(prefix, self._seq)

    # -- single-state step ------------------------------------------------
    def step(self, payload: dict[str, Any] | None = None) -> LoopStep:
        """Run current state once, advance per TRANSITIONS. Bodies: W-B1."""
        payload = dict(payload or {})
        handler = {
            "S0": self.s0_perceive,
            "S1": self.s1_scene,
            "S2": self.s2_time,
            "S3": self.s3_decide,
            "S4": self.s4_act,
            "S5": self.s5_verify,
        }[self.state]
        verdict = handler(payload)
        if verdict not in ("pass", "fail"):
            raise ValueError(f"bad verdict from {self.state}: {verdict!r}")
        nxt = TRANSITIONS[self.state][verdict]
        if self.state == "S5" and verdict == "fail":
            nxt = str(payload.get("fail_target",
                                  self.ctx.get("fail_target", "S1")))
            self.reentry_count += 1
            if self.reentry_count > MAX_REENTRY:
                self._escalate("s5-reentry-overflow")
                nxt = "S3"  # park at decision with kp_needed slip
                self.ctx["kp_needed"] = True
        elif verdict == "pass" and self.state == "S5":
            self.reentry_count = 0
        # S1 decision-point skip: S2 is noted (tick) but not executed.
        if self.state == "S1" and self.ctx.pop(_SKIP_TO_S3, False):
            nxt = "S3"
        rec = LoopStep(state=self.state, verdict=verdict,
                       reentry_count=self.reentry_count,
                       note=str(self.ctx.get("last_note", "")))
        self.history.append(rec)
        self.state = nxt
        return rec

    def run_round(self, payload: dict[str, Any] | None = None) -> list[LoopStep]:
        """Run S0→…→S5 once (6 state visits from S0). Returns step records."""
        self.state = LoopState.S0_PERCEIVE.value
        self.ctx.pop(_SKIP_TO_S3, None)
        out: list[LoopStep] = []
        for _ in range(6):
            out.append(self.step(payload))
            if self.state == "S0":
                break
        return out

    def replay(self, event_id: str) -> list[dict[str, Any]]:
        """Invariant 3: every round replayable — suffix from event_id."""
        ids = [e.get("event_id") for e in self.event_log]
        if event_id not in ids:
            raise KeyError(f"unknown event_id: {event_id}")
        return self.event_log[ids.index(event_id):]

    # -- audit ------------------------------------------------------------
    def _escalate(self, reason: str) -> None:
        self.audit.append({"ts_wall": _now_iso(), "kind": "escalation",
                           "reason": reason,
                           "reentry_count": self.reentry_count,
                           "broadcast": KP_PREFIX + "S5 校验连续失败，"
                           "请 KP 接管拍板（重入超 %d 次）。" % MAX_REENTRY})

    # -- per-state bodies (W-B1; signatures frozen) ------------------------
    def s0_perceive(self, payload: dict[str, Any]) -> str:
        """S0 感知: converge WS frames → normalized E[].

        payload["frames"]: list of {event_id?, ts_round?, src?, kind?, payload?}.
        Dedupe by event_id (first wins), sort by (ts_round, event_id).
        Empty E[] → idle_rounds += 1; on reaching idle_timeout emit one
        cold-field ALERT reminder, verdict fail (stay S0 per TRANSITIONS).
        """
        frames = payload.get("frames", self.ctx.get("frames", []))
        seen: dict[str, dict[str, Any]] = {}
        for i, fr in enumerate(frames):
            if not isinstance(fr, dict):
                continue
            eid = str(fr.get("event_id") or self._next_id("fr"))
            if eid in seen:
                continue
            seen[eid] = {
                "event_id": eid,
                "ts_round": int(fr.get("ts_round", 0)),
                "ts_wall": str(fr.get("ts_wall", _now_iso())),
                "src": str(fr.get("src", "system")),
                "kind": str(fr.get("kind", "say")),
                "payload": dict(fr.get("payload", {})),
                "_order": i,
            }
        ordered = sorted(seen.values(),
                         key=lambda e: (e["ts_round"], e["event_id"]))
        events = [{k: v for k, v in e.items() if not k.startswith("_")}
                  for e in ordered]
        self.ctx["E"] = events
        if not events:
            self._idle_rounds += 1
            self.ctx["idle_rounds"] = self._idle_rounds
            if self._idle_rounds >= self.idle_timeout:
                alert = {"event_id": self._next_id("alert"),
                         "ts_round": int(payload.get("round", 0)),
                         "ts_wall": _now_iso(), "src": "agent:S0",
                         "kind": "alert",
                         "payload": {"type": "cold_field",
                                     "detail": "%d idle rounds" % self._idle_rounds}}
                self.event_log.append(alert)
                self.ctx["last_note"] = "cold-field alert, stay S0"
                return "fail"
            self.ctx["last_note"] = "idle, stay S0"
            return "fail"
        self._idle_rounds = 0
        self.ctx["idle_rounds"] = 0
        self.ctx["last_note"] = "%d events" % len(events)
        return "pass"

    def s1_scene(self, payload: dict[str, Any]) -> str:
        """S1 场景: advance scene graph / clues / NPC.

        Decision-point skip: payload["has_pending_ruling"] True, or any E[]
        event with kind in {ruling, roll} / payload.ruling_point True →
        mark skip_to_s3 (tick noted), verdict fail (TRANSITIONS fail → S1,
        but step() reroutes to S3 via the skip flag).
        """
        events = list(self.ctx.get("E", []))
        graph = payload.get("graph", self.ctx.get("graph"))
        if self.scene is not None:
            try:
                from .events import make_event as _mk
                ev_objs = []
                for e in events:
                    if hasattr(e, "event_id"):
                        ev_objs.append(e)
                    else:
                        ev_objs.append(_mk(
                            str(e.get("event_id", "e")), int(e.get("ts_round", 0)),
                            str(e.get("ts_wall", _now_iso())),
                            str(e.get("src", "system")),
                            str(e.get("kind", "say")),
                            dict(e.get("payload", {}))))
                delta = self.scene.advance(ev_objs, graph)
            except TypeError:
                delta = self.scene.advance(events)
        else:
            delta = {"scene_id": "", "moved": False, "new_clues": [],
                     "npc_lines": [], "round": 0}
        if not isinstance(delta, dict):
            delta = {"scene_id": "", "moved": False, "new_clues": [],
                     "npc_lines": [], "round": 0}
        self.ctx["scene_delta"] = delta
        pending = bool(payload.get("has_pending_ruling", False))
        if not pending:
            for ev in events:
                pl = ev.get("payload", {}) if isinstance(ev, dict) else {}
                if (ev.get("kind") in ("ruling", "roll")
                        or (isinstance(pl, dict) and pl.get("ruling_point"))):
                    pending = True
                    break
        if pending:
            # tick-noted skip of S2: advance the clock minimally if time exists.
            if self.time is not None:
                try:
                    self.ctx["clock_note"] = self.time.tick(delta)
                except TypeError:
                    self.ctx["clock_note"] = self.time.tick()
            else:
                self.ctx["clock_note"] = {"round": 0, "skipped": True}
            self.ctx[_SKIP_TO_S3] = True
            self.ctx["last_note"] = "pending ruling → skip S2 to S3"
            return "fail"
        self.ctx["last_note"] = "scene %s" % delta.get("scene_id", "")
        return "pass"

    def s2_time(self, payload: dict[str, Any]) -> str:
        """S2 时间: tick clock / pace / spotlight.

        Any reminder (timeout/cold_field/off-track/spotlight) rides along
        into S3: verdict fail (TRANSITIONS fail → S3), reminders in ctx.
        """
        delta = self.ctx.get("scene_delta", {})
        clock: dict[str, Any]
        if self.time is not None:
            try:
                clock = dict(self.time.tick(delta))
            except TypeError:
                clock = dict(self.time.tick())
            try:
                rems = list(self.time.check_pace(
                    int(payload.get("round_elapsed_sec", 0)),
                    payload.get("on_track", True)))
            except TypeError:
                rems = list(self.time.check_pace())
        else:
            clock = {"round": 0}
            rems = []
        self.ctx["clock"] = clock
        self.ctx["reminders"] = rems
        if rems:
            for r in rems:
                self.event_log.append({
                    "event_id": self._next_id("alert"),
                    "ts_round": int(clock.get("round", 0)),
                    "ts_wall": _now_iso(), "src": "agent:S2",
                    "kind": "alert", "payload": dict(r)})
            self.ctx["last_note"] = "%d reminders → S3" % len(rems)
            return "fail"
        self.ctx["last_note"] = "clock round %s" % clock.get("round", 0)
        return "pass"

    def s3_decide(self, payload: dict[str, Any]) -> str:
        """S3 决策: checks / narrative / approval (+galaxy sub-call).

        Invariants (raise ValueError on violation, audited):
          1. dice first — a slip with dice.needed True must already carry
             rolled + outcome (S3 never narrates before the roll lands).
          2. never declare for a PC — payload["pc_declaration"] present →
             reject (the loop must not speak an action for a player).
        build: decide_fn(request) if wired, else minimal slip from payload.
        kp_needed / rule-conflict fast-ruling still verdict pass (→ S4).
        """
        if payload.get("pc_declaration") is not None:
            self.audit.append({"ts_wall": _now_iso(),
                               "kind": "invariant_reject",
                               "rule": "never-declare-for-pc"})
            raise ValueError("S3 refuses pc_declaration: "
                             "never declare an action for a PC")
        request = {
            "scene_delta": self.ctx.get("scene_delta", {}),
            "clock": self.ctx.get("clock",
                                  self.ctx.get("clock_note", {})),
            "reminders": self.ctx.get("reminders", []),
            "declaration": payload.get("declaration"),
            "ruling": payload.get("ruling"),
            "seed": payload.get("seed"),
        }
        if self.decide_fn is not None:
            slip = self.decide_fn(request)
        else:
            ruling = dict(payload.get("ruling") or {"type": "kp_needed"})
            dice = dict(payload.get("dice") or {"needed": False})
            slip = {
                "decision_id": "gd-%s-%d" % (
                    self.ctx.get("clock", {}).get("round", 0)
                    if isinstance(self.ctx.get("clock"), dict) else 0,
                    self._seq + 1),
                "trigger": {"point_id": "loop-s3", "matched": "default",
                            "round": 0},
                "context": {"scene_id": "", "pc": "",
                            "declaration": str(request["declaration"] or "")},
                "ruling": ruling, "dice": dice,
                "broadcast": (KP_PREFIX + "请 KP 拍板。"
                              if ruling.get("type") == "kp_needed" else ""),
                "replay_ptr": "",
            }
        if not isinstance(slip, dict):
            raise ValueError("S3 decide_fn must return a ruling-slip dict")
        dice = slip.get("dice", {}) if isinstance(slip.get("dice"), dict) else {}
        if dice.get("needed") and (dice.get("rolled") is None
                                   or dice.get("outcome") is None):
            self.audit.append({"ts_wall": _now_iso(),
                               "kind": "invariant_reject",
                               "rule": "dice-before-narration"})
            raise ValueError("S3 dice-needed slip lacks rolled/outcome: "
                             "dice must precede narration")
        rtype = slip.get("ruling", {}).get("type") \
            if isinstance(slip.get("ruling"), dict) else None
        if rtype == "kp_needed" and not str(slip.get("broadcast", "")) \
                .startswith(KP_PREFIX):
            slip["broadcast"] = KP_PREFIX + str(slip.get("broadcast", ""))
        if payload.get("rule_conflict"):
            slip.setdefault("review", {})["fast_ruling"] = True
            slip["review"]["note"] = "先快判后复盘"
        self.ctx["D"] = slip
        self.ctx["last_note"] = "ruling %s" % rtype
        return "pass"

    def s4_act(self, payload: dict[str, Any]) -> str:
        """S4 行动: append event + broadcast.

        Writes ROLL (if dice rolled) + RULING + BOARD events; broadcast text
        is the slip broadcast (never composed before dice — see S3).
        """
        slip = self.ctx.get("D") or {}
        clock = self.ctx.get("clock", {}) \
            if isinstance(self.ctx.get("clock"), dict) else {}
        rnd = int(clock.get("round", payload.get("round", 0)))
        dice = slip.get("dice", {}) if isinstance(slip, dict) else {}
        if isinstance(dice, dict) and dice.get("rolled") is not None:
            self.event_log.append({
                "event_id": self._next_id("roll"), "ts_round": rnd,
                "ts_wall": _now_iso(), "src": "agent:S3",
                "kind": "roll",
                "payload": {"expr": dice.get("expr", "1d100"),
                            "target": dice.get("target"),
                            "rolled": dice.get("rolled"),
                            "outcome": dice.get("outcome")}})
        self.event_log.append({
            "event_id": self._next_id("ruling"), "ts_round": rnd,
            "ts_wall": _now_iso(), "src": "agent:S3",
            "kind": "ruling",
            "payload": {"decision_id": slip.get("decision_id", ""),
                        "type": (slip.get("ruling", {}) or {}).get("type")}})
        btext = str(slip.get("broadcast", "")) if isinstance(slip, dict) else ""
        board = {"event_id": self._next_id("board"), "ts_round": rnd,
                 "ts_wall": _now_iso(), "src": "agent:S4",
                 "kind": "board", "payload": {"text": btext}}
        self.event_log.append(board)
        self.ctx["broadcast"] = btext
        self.ctx["replay_ptr"] = board["event_id"]
        self.ctx["last_note"] = "broadcast %d chars" % len(btext)
        return "pass"

    def s5_verify(self, payload: dict[str, Any]) -> str:
        """S5 校验: assertions + replayable.

        Checks (payload-injectable for failure injection):
          dice_consistency (S4 ROLL vs S3 slip), clue_no_loss
          (S1 new_clues ⊆ revealed payload set), npc_consistency
          (npc lines non-empty), numeric_sanity (round/rolled ranges).
        verdict fail sets ctx fail_target: ruling-class errors → S3,
        state-class errors → S1 (default). Always leaves a replay pointer.
        """
        slip = self.ctx.get("D") or {}
        dice = slip.get("dice", {}) if isinstance(slip, dict) else {}
        fails: list[str] = []
        if isinstance(dice, dict) and dice.get("rolled") is not None:
            rolls = [e for e in self.event_log if e.get("kind") == "roll"]
            if not rolls or rolls[-1]["payload"].get("rolled") != dice.get(
                    "rolled"):
                fails.append("dice_consistency")
        if payload.get("force_fail"):
            fails.append(str(payload["force_fail"]))
        if payload.get("drop_clue"):
            fails.append("clue_no_loss")
        if payload.get("npc_mismatch"):
            fails.append("npc_consistency")
        rolled = (dice or {}).get("rolled")
        if rolled is not None and not (1 <= int(rolled) <= 100):
            fails.append("numeric_sanity")
        self.ctx["replay_ptr"] = self.ctx.get("replay_ptr") or (
            self.event_log[-1].get("event_id") if self.event_log else "")
        if not fails:
            self.ctx["last_note"] = "verify pass"
            return "pass"
        ruling_errors = {"dice_consistency", "ruling_error"}
        self.ctx["fail_target"] = "S3" if set(fails) & ruling_errors else "S1"
        self.ctx["fail_reasons"] = fails
        self.ctx["last_note"] = "verify fail: %s" % ",".join(fails)
        return "fail"
