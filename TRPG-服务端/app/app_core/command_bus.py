"""Command bus: the ONLY write path (MIT).

Commands are registered by name; dispatch() validates, runs the guard,
emits frozen GameEvents, and appends them in one store transaction.
Idempotency keys make retries safe. dispatch() is serialized per campaign
(_dispatch_lock) so the idempotency check and the append are atomic, and the
store assigns seqs inside one BEGIN IMMEDIATE transaction -- no caller-side
read-then-write. Anything that bypasses this bus and writes events directly
is a bug (tests assert single-writer usage).
Python 3.12 compatible.
"""
from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timezone
from typing import Any, Callable

from app.domain.events import GameEvent, make_event
from app.scheduler.branch_guard import (
    BranchGuard,
    BranchViolation,
    ConflictError,
    DuplicateCommand,
)
from app.store.event_store import EventStore, SeqConflictError

__all__ = [
    "CommandError",
    "CommandBus",
    "COMMANDS",
    "BranchViolation",
    "ConflictError",
    "DuplicateCommand",
    "SeqConflictError",
]


class CommandError(ValueError):
    """Validation / execution failure of a command."""


def _canon(params: dict[str, Any]) -> dict[str, Any]:
    """Canonical signature: JSON round-trip (sorted keys), so key order,
    aliasing, or later caller mutation can never fork the identity."""
    return json.loads(json.dumps(params, sort_keys=True, ensure_ascii=False))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# R8 并发 (P0): 按 campaign 分片的派发锁, **跨 CommandBus 实例共享**。
# 每个请求都会新建 CommandBus (access.py:690 / access.py:1597 /
# pipeline_api.py:185), 所以实例级锁毫无作用; 与 access._GUARDS 一样做成
# 进程内单例注册表。作用域 = check_key -> handler -> append -> record_key,
# 让幂等键的「查重 -> 落库 -> 登记」真正原子。
_DISPATCH_LOCKS: dict[str, asyncio.Lock] = {}


def _dispatch_lock(campaign_id: str) -> asyncio.Lock:
    lock = _DISPATCH_LOCKS.get(campaign_id)
    if lock is None:
        lock = asyncio.Lock()
        _DISPATCH_LOCKS[campaign_id] = lock
    return lock


Handler = Callable[[dict[str, Any]], list[dict[str, Any]]]
# handler input: {"params":..., "actor":..., "key":..., "causal":...}
# handler output: list of {"type":..., "payload":...} event specs


class CommandBus:
    def __init__(self, store: EventStore, campaign_id: str,
                 guard: BranchGuard | None = None) -> None:
        self.store = store
        self.campaign_id = campaign_id
        self.guard = guard or BranchGuard()
        self._handlers: dict[str, Handler] = {}
        for name, fn in COMMANDS.items():
            self._handlers[name] = fn

    def register(self, name: str, fn: Handler) -> None:
        if name in self._handlers:
            raise CommandError("command already registered: %r" % name)
        self._handlers[name] = fn

    async def dispatch(self, name: str, params: dict[str, Any], actor: str,
                       key: str | None = None,
                       causal: list[str] | None = None) -> dict[str, Any]:
        if name not in self._handlers:
            raise CommandError("unknown command: %r" % name)
        if not actor:
            raise CommandError("actor required")
        causal = list(causal or [])
        payload_sig = {"name": name, "params": _canon(dict(params)),
                       "actor": actor}
        # R8 并发 (P0): 幂等键的 check_key -> append -> record_key 必须原子。
        # 否则同 req_id 的并发提交会**同时**通过 check_key, 各自落一条
        # ACTION_SUBMITTED —— 幂等键形同虚设 (实测 8 并发落 8 条)。
        async with _dispatch_lock(self.campaign_id):
            if key is not None:
                try:
                    self.guard.check_key(key, payload_sig)
                except DuplicateCommand:
                    receipt = self.guard.receipt_for(key) or {}
                    receipt = dict(receipt)
                    receipt["status"] = "duplicate"
                    return receipt
            node = params.get("node_id") if isinstance(params, dict) else None
            self.guard.check_causal(causal, node if isinstance(node, str) else None)
            try:
                specs = self._handlers[name]({"params": params, "actor": actor,
                                              "key": key, "causal": causal})
            except (CommandError, BranchViolation, ConflictError):
                raise
            except ValueError as exc:
                raise CommandError(str(exc))
            events = [make_event(seq=0, campaign_id=self.campaign_id,
                                 type=s["type"], payload=s["payload"],
                                 actor=actor, ts=_now(),
                                 approved_by=s.get("approved_by"),
                                 causal=causal) for s in specs]
            # R8 并发 (P0): **不得**在这里自己读 tip 再回传 expected_seq。
            # 那是 read-then-write 的 TOCTOU: N 个并发请求都读到同一个 tip,
            # 先落库者把 tip 推到 +1, 后到者即抛 SeqConflictError, 调用方
            # (access.mobile_action) 只 catch ConflictError/CommandError/
            # BranchViolation => 直接 HTTP 500, 且这几条行动**整条丢失**
            # (实测 8 并发: 1 成功 + 7 个 SeqConflictError, 只落 1 条)。
            # expected_seq 的语义是「调用方持有旧视图, 要求 CAS 失败」; 本处
            # 根本没有旧视图, 它唯一的效果就是把良性的并发写变成 500。
            # 落库顺序由 EventStore.append 内的 BEGIN IMMEDIATE 串行化
            # (原子分配全局 seq); 全仓其余 20 余处 append 调用同样不传它。
            seqs = await self.store.append(self.campaign_id, events)
            receipt: dict[str, Any] = {"status": "ok", "seqs": seqs,
                                       "events": len(seqs), "key": key}
            if key is not None:
                self.guard.record_key(key, payload_sig, receipt)
            return receipt


# ---- built-in command handlers (pure validation -> event specs) ----

def _req(params: dict, *fields: str) -> None:
    missing = [f for f in fields if f not in params]
    if missing:
        raise CommandError("missing params: %s" % missing)


def _cmd_start_turn(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "turn_no", "window_sec", "countdown_end_ts")
    return [{"type": "TURN_STARTED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "turn_no": p["turn_no"], "window_sec": p["window_sec"],
                         "countdown_end_ts": p["countdown_end_ts"]}}]


def _cmd_submit_action(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "turn_no", "player_id", "action")
    return [{"type": "ACTION_SUBMITTED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "turn_no": p["turn_no"], "player_id": p["player_id"],
                         "action": p["action"],
                         "intent_summary": p.get("intent_summary", "")}}]


def _cmd_withdraw_action(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "turn_no", "player_id")
    return [{"type": "ACTION_WITHDRAWN",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "turn_no": p["turn_no"],
                         "player_id": p["player_id"]}}]


def _cmd_close_window(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "turn_no")
    return [{"type": "TURN_CLOSED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "turn_no": p["turn_no"],
                         "submit_map": p.get("submit_map", {}),
                         "order": p.get("order", [])}}]


def _cmd_checkpoint(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "turn_no", "cursor")
    return [{"type": "TURN_CHECKPOINT",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "turn_no": p["turn_no"], "cursor": p["cursor"],
                         "resolved_ids": p.get("resolved_ids", [])}}]


def _cmd_advance_act(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "act_no", "act_name")
    return [{"type": "ACT_ADVANCED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "act_no": p["act_no"],
                         "act_name": p["act_name"]}}]


def _cmd_resolve_check(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "turn_no", "card_id", "target", "difficulty", "total", "level",
         "seed")
    if p["level"] not in ("crit", "success", "hard", "extreme", "fail",
                          "fumble"):
        raise CommandError("bad level %r" % p["level"])
    return [{"type": "CHECK_RESOLVED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "turn_no": p["turn_no"], "card_id": p["card_id"],
                         "target": p["target"], "difficulty": p["difficulty"],
                         "rolled": p.get("rolled", []), "total": p["total"],
                         "level": p["level"], "seed": p["seed"],
                         "summary": p.get("summary", "")}}]


def _cmd_propose_narration(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "proposal_id", "text", "reasoning")
    return [{"type": "NARRATION_PROPOSED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "proposal_id": p["proposal_id"], "text": p["text"],
                         "intention": p.get("intention"),
                         "reasoning": p["reasoning"],
                         "source": p.get("source", "agent")}}]


def _cmd_approve_narration(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "proposal_id", "decision")
    if p["decision"] not in ("approve", "edit", "reject"):
        raise CommandError("bad decision %r" % p["decision"])
    actor = ctx["actor"]
    if p["decision"] == "approve":
        return [{"type": "NARRATION_APPROVED",
                 "payload": {"proposal_id": p["proposal_id"],
                             "text": p.get("text", "")},
                 "approved_by": actor}]
    if p["decision"] == "edit":
        return [{"type": "NARRATION_EDITED",
                 "payload": {"proposal_id": p["proposal_id"],
                             "text": p.get("text", ""),
                             "diff": p.get("diff", {})},
                 "approved_by": actor}]
    return [{"type": "NARRATION_REJECTED",
             "payload": {"proposal_id": p["proposal_id"],
                         "reason": p.get("reason", "")},
             "approved_by": actor}]


def _cmd_distribute_info(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "info_id", "scope", "body_ref")
    if p["scope"] not in ("public", "whisper", "condition"):
        raise CommandError("bad scope %r" % p["scope"])
    if p["scope"] == "whisper" and not p.get("targets"):
        raise CommandError("whisper requires targets")
    return [{"type": "INFO_REVEALED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "info_id": p["info_id"], "scope": p["scope"],
                         "targets": p.get("targets", []),
                         "body_ref": p["body_ref"]}}]


def _cmd_take_branch(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "node_id", "edge_id", "label")
    return [{"type": "BRANCH_TAKEN",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "node_id": p["node_id"], "edge_id": p["edge_id"],
                         "label": p["label"],
                         "consequences": p.get("consequences", [])}}]


def _cmd_advance_scene(ctx: dict) -> list[dict]:
    """T1 (additive): advance to a scene -> SCENE_UPDATED (+ MAP_UPDATED set_scene)."""
    p = ctx["params"]
    _req(p, "to_scene_id")
    scene_id = str(p["to_scene_id"]).strip()
    if not scene_id:
        raise CommandError("to_scene_id required")
    specs: list[dict[str, Any]] = [{
        "type": "SCENE_UPDATED",
        "payload": {"campaign_id": p.get("campaign_id", ""),
                    "scene_id": scene_id,
                    "prev_scene_id": p.get("prev_scene_id"),
                    "edge_id": p.get("edge_id"),
                    "map_id": p.get("map_id"),
                    "reason": p.get("reason", "")},
    }]
    map_id = p.get("map_id")
    if map_id:
        specs.append({
            "type": "MAP_UPDATED",
            "payload": {"campaign_id": p.get("campaign_id", ""),
                        "map_id": str(map_id), "op": "set_scene",
                        "target": scene_id,
                        "delta": {"room_ref": p.get("room_ref", "")}},
        })
    return specs


def _cmd_map_update(ctx: dict) -> list[dict]:
    p = ctx["params"]
    _req(p, "map_id", "op", "target")
    if p["op"] not in ("move", "add_token", "set_fog", "set_status",
                       "set_light", "set_scene"):
        raise CommandError("bad op %r" % p["op"])
    return [{"type": "MAP_UPDATED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "map_id": p["map_id"], "op": p["op"],
                         "target": p["target"], "delta": p.get("delta", {})}}]


COMMANDS: dict[str, Handler] = {
    "start_turn": _cmd_start_turn,
    "submit_action": _cmd_submit_action,
    "withdraw_action": _cmd_withdraw_action,
    "close_window": _cmd_close_window,
    "checkpoint": _cmd_checkpoint,
    "advance_act": _cmd_advance_act,
    "resolve_check": _cmd_resolve_check,
    "propose_narration": _cmd_propose_narration,
    "approve_narration": _cmd_approve_narration,
    "distribute_info": _cmd_distribute_info,
    "take_branch": _cmd_take_branch,
    "map_update": _cmd_map_update,
    "advance_scene": _cmd_advance_scene,
}

GameEventUnused = GameEvent  # re-export for convenience
