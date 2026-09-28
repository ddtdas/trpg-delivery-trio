"""R29: NPC 记忆 —— additive 分层（SQLite，与 EventStore 同库不同表）。

需求判据 -> 本模块实现
--------------------------------------------------------------
(1) 「记住见过谁 / 发生过什么 / 玩家做过什么」
    -> npc_memory 表：kind ∈ {met, event, player_action, gm_note}，
       ref 记「谁/哪件事」，text 记「发生了什么」。
       既支持 GM/系统显式 remember()，也支持 ingest_events() 从事件流
       自动归纳（玩家行动、检定、别的 NPC 说过的话）。
(2) 「影响后续反应与对话」
    -> digest() 把记忆压成生成器可用的结构化摘要
       {met, events, player_actions, attitude, hostile, friendly, recall[]}；
       app/npc/director.py 生成台词时按 attitude 决定语气与是否隐瞒，
       并把命中的记忆写回 proposal.memory_refs（可追溯）。
(3) 「GM 可查看 / 编辑 / 清空且即时生效」
    -> recall() / update_memory() / forget()；生成器每次现读库（无缓存），
       故编辑与清空在下一次生成立即生效。

不新增事件类型 / 不新增协议帧。Python 3.12 compatible.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import aiosqlite

from app.config import APP_ROOT

__all__ = [
    "DB_PATH",
    "NPC_SCHEMA",
    "MEMORY_KINDS",
    "init",
    "remember",
    "recall",
    "update_memory",
    "forget",
    "digest",
    "ingest_events",
    "ATTITUDES",
]

DB_PATH = APP_ROOT / "data" / "trpg.db"

MEMORY_KINDS: tuple[str, ...] = ("met", "event", "player_action", "gm_note")

# 记忆 -> 态度：生成器据此选语气（确定性、可测试）
_HOSTILE_KW = ("攻击", "威胁", "殴打", "开枪", "拔枪", "欺骗", "偷", "拷问", "逼迫", "砸")
_FRIENDLY_KW = ("安抚", "帮助", "治疗", "说服", "赠送", "救", "道歉", "保护", "安慰")

ATTITUDES: tuple[str, ...] = ("戒备", "疏离", "中立", "配合", "亲近")

NPC_SCHEMA = """
CREATE TABLE IF NOT EXISTS npc_memory (
    mem_id      TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    npc_id      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    ref         TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'system',
    ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_npc_memory_scope
    ON npc_memory (campaign_id, npc_id, ts);

CREATE TABLE IF NOT EXISTS npc_proposal (
    proposal_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    npc_id      TEXT NOT NULL,
    line        TEXT NOT NULL,
    tone        TEXT NOT NULL DEFAULT '',
    intent      TEXT NOT NULL DEFAULT '',
    conceal     INTEGER NOT NULL DEFAULT 0,
    memory_refs TEXT NOT NULL DEFAULT '[]',
    source      TEXT NOT NULL DEFAULT 'auto',
    status      TEXT NOT NULL DEFAULT 'pending',
    final_line  TEXT NOT NULL DEFAULT '',
    edit_from   TEXT NOT NULL DEFAULT '',
    created_ts  TEXT NOT NULL,
    decided_ts  TEXT NOT NULL DEFAULT '',
    decided_by  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_npc_proposal_scope
    ON npc_proposal (campaign_id, npc_id, status);

CREATE TABLE IF NOT EXISTS npc_setting (
    campaign_id TEXT NOT NULL,
    npc_id      TEXT NOT NULL DEFAULT '*',
    auto        INTEGER NOT NULL DEFAULT 1,
    takeover    INTEGER NOT NULL DEFAULT 0,
    updated_ts  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (campaign_id, npc_id)
);
""".strip()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:12])


async def _connect() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


async def init() -> None:
    """建表（幂等）。与 EventStore 共用 data/trpg.db，WAL 模式下安全。"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.executescript(NPC_SCHEMA)
        await db.commit()


def _row_to_memory(row: sqlite3.Row) -> dict[str, Any]:
    return {"mem_id": row["mem_id"], "campaign_id": row["campaign_id"],
            "npc_id": row["npc_id"], "kind": row["kind"], "ref": row["ref"],
            "text": row["text"], "source": row["source"], "ts": row["ts"]}


async def remember(campaign_id: str, npc_id: str, kind: str, text: str,
                   ref: str = "", source: str = "system") -> dict[str, Any]:
    """写入一条记忆（见过谁 / 发生过什么 / 玩家做过什么）。"""
    if not campaign_id or not npc_id:
        raise ValueError("campaign_id / npc_id required")
    if kind not in MEMORY_KINDS:
        raise ValueError("kind must be one of %s" % (list(MEMORY_KINDS),))
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    await init()
    mem = {"mem_id": _new_id("mem"), "campaign_id": campaign_id,
           "npc_id": npc_id, "kind": kind, "ref": str(ref or ""),
           "text": text.strip(), "source": str(source or "system"),
           "ts": _utcnow()}
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO npc_memory (mem_id, campaign_id, npc_id, kind, ref,"
            " text, source, ts) VALUES (?,?,?,?,?,?,?,?)",
            (mem["mem_id"], mem["campaign_id"], mem["npc_id"], mem["kind"],
             mem["ref"], mem["text"], mem["source"], mem["ts"]))
        await db.commit()
    return mem


async def recall(campaign_id: str, npc_id: str,
                 limit: int = 200) -> list[dict[str, Any]]:
    """按时间顺序读回记忆（GM 查看）。"""
    await init()
    n = max(1, min(int(limit or 200), 1000))
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        async with db.execute(
            "SELECT * FROM npc_memory WHERE campaign_id=? AND npc_id=?"
            " ORDER BY ts ASC, rowid ASC LIMIT ?",
            (campaign_id, npc_id, n)) as cur:
            rows = await cur.fetchall()
    return [_row_to_memory(r) for r in rows]


async def update_memory(mem_id: str, text: str | None = None,
                        kind: str | None = None,
                        ref: str | None = None) -> bool:
    """GM 编辑记忆（即时生效：生成器每次现读库）。"""
    sets: list[str] = []
    args: list[Any] = []
    if text is not None:
        if not str(text).strip():
            raise ValueError("text must be a non-empty string")
        sets.append("text=?")
        args.append(str(text).strip())
    if kind is not None:
        if kind not in MEMORY_KINDS:
            raise ValueError("kind must be one of %s" % (list(MEMORY_KINDS),))
        sets.append("kind=?")
        args.append(kind)
    if ref is not None:
        sets.append("ref=?")
        args.append(str(ref))
    if not sets:
        raise ValueError("nothing to update")
    await init()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "UPDATE npc_memory SET %s WHERE mem_id=?" % ", ".join(sets),
            (*args, mem_id))
        await db.commit()
        return cur.rowcount > 0


async def forget(campaign_id: str, npc_id: str,
                 mem_id: str | None = None) -> int:
    """GM 清空记忆（单条或整只 NPC）。"""
    await init()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        if mem_id:
            cur = await db.execute(
                "DELETE FROM npc_memory WHERE mem_id=? AND campaign_id=?"
                " AND npc_id=?", (mem_id, campaign_id, npc_id))
        else:
            cur = await db.execute(
                "DELETE FROM npc_memory WHERE campaign_id=? AND npc_id=?",
                (campaign_id, npc_id))
        await db.commit()
        return int(cur.rowcount or 0)


def _attitude(hostile: int, friendly: int) -> str:
    score = friendly - hostile
    if score <= -2:
        return "戒备"
    if score == -1:
        return "疏离"
    if score == 0:
        return "中立"
    if score == 1:
        return "配合"
    return "亲近"


async def digest(campaign_id: str, npc_id: str,
                 limit: int = 200) -> dict[str, Any]:
    """把记忆压成生成器可用的结构化摘要（同时给出被引用的记忆 id）。"""
    mems = await recall(campaign_id, npc_id, limit=limit)
    met: list[str] = []
    events: list[str] = []
    actions: list[str] = []
    hostile = friendly = 0
    for m in mems:
        if m["kind"] == "met" and m["ref"] and m["ref"] not in met:
            met.append(m["ref"])
        elif m["kind"] == "player_action":
            actions.append(m["text"])
            if any(k in m["text"] for k in _HOSTILE_KW):
                hostile += 1
            if any(k in m["text"] for k in _FRIENDLY_KW):
                friendly += 1
        else:
            events.append(m["text"])
    attitude = _attitude(hostile, friendly)
    recall_ids = [m["mem_id"] for m in mems[-5:]]
    return {"npc_id": npc_id, "campaign_id": campaign_id,
            "count": len(mems), "met": met, "events": events,
            "player_actions": actions, "hostile": hostile,
            "friendly": friendly, "attitude": attitude,
            "memory_refs": recall_ids,
            "recent": [m["text"] for m in mems[-3:]]}


# ---------------------------------------------------------------------------
# 从事件流自动归纳记忆（additive：只读事件，不写事件）
# ---------------------------------------------------------------------------

def _event_action_text(payload: Mapping[str, Any]) -> str:
    action = payload.get("action") or {}
    if isinstance(action, Mapping) and action.get("text"):
        return str(action["text"])
    return json.dumps(action, ensure_ascii=False)


async def ingest_events(campaign_id: str, npc_id: str,
                        events: Iterable[Any],
                        known_players: Iterable[str] = ()) -> int:
    """把事件流里「玩家做过什么 / 发生过什么」记进 NPC 记忆。

    只归纳与 NPC 交互相关、且对 NPC 可观察的事件类型；不产生任何新事件。
    幂等性由调用方控制（同一批事件重复 ingest 会重复计数）。
    """
    players = {str(p) for p in known_players if p}
    written = 0
    for ev in events:
        etype = str(getattr(ev, "type", "") or "")
        payload = dict(getattr(ev, "payload", None) or {})
        actor = str(getattr(ev, "actor", "") or "")
        if etype == "ACTION_SUBMITTED":
            pid = str(payload.get("player_id") or actor or "?")
            text = "玩家 %s 做了：%s" % (pid, _event_action_text(payload))
            await remember(campaign_id, npc_id, "player_action", text,
                           ref=pid, source="event:ACTION_SUBMITTED")
            written += 1
        elif etype == "CHECK_RESOLVED":
            pid = str(payload.get("card_id") or actor or "?")
            text = "检定 %s 目标 %s 结果 %s" % (
                pid, payload.get("target", ""), payload.get("level", ""))
            await remember(campaign_id, npc_id, "event", text,
                           ref=pid, source="event:CHECK_RESOLVED")
            written += 1
        elif etype == "NPC_ACT_APPROVED":
            other = str(payload.get("npc_id") or "")
            if other and other != npc_id:
                await remember(campaign_id, npc_id, "event",
                               "另一个角色（%s）说了：%s" % (other, payload.get("line", "")),
                               ref=other, source="event:NPC_ACT_APPROVED")
                written += 1
    return written
