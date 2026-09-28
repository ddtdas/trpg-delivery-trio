"""TRPG append-only event store: SQLite WAL + aiosqlite (MIT).

Single writer. seq is GLOBALLY unique and monotonically increasing across
all campaigns (T23 fix: previously per-campaign numbering collided on the
global PRIMARY KEY, so any second campaign failed with UNIQUE constraint).
Per-campaign ordering is preserved (global seqs restricted to one campaign
are strictly increasing); replay/projector/snapshot filter by campaign_id
exactly as before. Optimistic locking uses per-campaign expected_seq
(max seq of THIS campaign the caller saw, -1 when empty) so concurrent
writers on the same campaign still conflict while other campaigns never
cause false conflicts.
Python 3.12 compatible.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Awaitable, Callable, ClassVar

import aiosqlite

from app.domain.events import GameEvent, event_from_json, event_to_json

logger = logging.getLogger("trpg.event_store")

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload TEXT NOT NULL,
  actor TEXT NOT NULL,
  approved_by TEXT,
  ts TEXT NOT NULL,
  causal TEXT NOT NULL DEFAULT '[]',
  version TEXT NOT NULL DEFAULT 'v1'
);
CREATE INDEX IF NOT EXISTS idx_events_campaign_seq ON events (campaign_id, seq);
CREATE TABLE IF NOT EXISTS perf_metrics (
  event_seq INTEGER NOT NULL,
  campaign_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  vad_ms REAL DEFAULT 0,
  stt_ms REAL DEFAULT 0,
  llm_first_token_ms REAL DEFAULT 0,
  tts_first_packet_ms REAL DEFAULT 0,
  approve_wait_ms REAL DEFAULT 0
);
"""


class SeqConflictError(ValueError):
    """Raised when expected_seq does not match the current max seq."""


class EventStore:
    # T2 (additive, ENDPOINT-SPEC-NEW §8): 事件落库后的可选发布回调。
    # 默认 None -> 纯 store 用法 (脚本 / 既有测试) 行为**完全不变**。
    # 由 app/main.py 的 lifespan 注入: EventStore.on_append = ws_bridge.publish_events
    #
    # 为什么是**类属性**而不是实例属性: rest._store() 每次调用都新建
    # EventStore(path) 实例 (app/web/rest.py:90), 实例属性无法跨请求生效。
    # 类属性既保留「默认 None + 可注入」的语义, 又对所有实例生效。
    on_append: ClassVar[Callable[[str, list[GameEvent]], Awaitable[None]] | None] = None

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def max_seq(self, campaign_id: str | None = None) -> int:
        """Max seq. With campaign_id: tip of THIS campaign (-1 when empty,
        used for optimistic locking + resume cursors). Without: global tip
        across all campaigns (used for seq assignment)."""
        sql = "SELECT MAX(seq) FROM events"
        args: tuple = ()
        if campaign_id is not None:
            sql += " WHERE campaign_id = ?"
            args = (campaign_id,)
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(sql, args)
            row = await cur.fetchone()
            return int(row[0]) if row and row[0] is not None else -1

    async def campaign_tip(self, campaign_id: str) -> int:
        """Alias kept explicit for the optimistic-lock read path."""
        return await self.max_seq(campaign_id)

    async def append(
        self,
        campaign_id: str,
        events: list[GameEvent],
        expected_seq: int | None = None,
    ) -> list[int]:
        """Single-transaction batch append with optimistic lock.

        expected_seq: max seq of THIS campaign the caller saw (-1 when empty).
        Assigned seqs are globally unique and monotonically increasing
        (global tip + 1 ...), hence NOT contiguous within one campaign when
        other campaigns interleave; stored seq wins over caller-supplied seq.
        """
        current = await self.campaign_tip(campaign_id)
        if expected_seq is not None and expected_seq != current:
            raise SeqConflictError(
                "seq conflict for %s: expected %d, have %d"
                % (campaign_id, expected_seq, current))
        seqs: list[int] = []
        async with aiosqlite.connect(self.path) as db:
            try:
                # Serialize writers: BEGIN IMMEDIATE takes the write lock so
                # the global-tip read and the inserts are atomic. Without it,
                # two concurrent appends could read the same MAX(seq) and
                # collide on the PRIMARY KEY.
                await db.execute("BEGIN IMMEDIATE")
                cur = await db.execute("SELECT MAX(seq) FROM events")
                row = await cur.fetchone()
                nxt = int(row[0]) + 1 if row and row[0] is not None else 0
                cur2 = await db.execute(
                    "SELECT MAX(seq) FROM events WHERE campaign_id = ?",
                    (campaign_id,))
                row2 = await cur2.fetchone()
                tip = int(row2[0]) if row2 and row2[0] is not None else -1
                if expected_seq is not None and expected_seq != tip:
                    raise SeqConflictError(
                        "seq conflict for %s: expected %d, have %d"
                        % (campaign_id, expected_seq, tip))
                for ev in events:
                    if ev.campaign_id != campaign_id:
                        raise ValueError("campaign mismatch: %s" % ev.campaign_id)
                    ev.seq = nxt
                    await db.execute(
                        "INSERT INTO events (seq, campaign_id, type, payload, actor,"
                        " approved_by, ts, causal, version)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (nxt, ev.campaign_id, ev.type,
                         json.dumps(ev.payload, ensure_ascii=False),
                         ev.actor, ev.approved_by, ev.ts,
                         json.dumps(ev.causal, ensure_ascii=False), ev.version),
                    )
                    seqs.append(nxt)
                    nxt += 1
                await db.commit()
            except sqlite3.IntegrityError as exc:
                raise SeqConflictError(
                    "seq conflict for %s at seq %d: %s" % (campaign_id, nxt, exc))
        # T2 (additive, ENDPOINT-SPEC-NEW §8): 事件落库后的 best-effort 广播。
        # **唯一收口** —— 全仓库只有这里触发发布 (禁止业务分支散点 publish)。
        # 回调由 app/main.py lifespan 注入; 未注入 (None) 则完全跳过。
        # 发布失败只记日志, 绝不影响落库与 HTTP 响应。
        # 注意: 必须避免描述符绑定 —— 若把普通函数赋给类属性, self.on_append 会
        # 变成 bound method 并把 self 当作第一个参数传入。故实例属性优先,
        # 其次从类上取 (访问类属性不会绑定)。
        callback = self.__dict__.get("on_append")
        if callback is None:
            callback = type(self).on_append
        if callback is not None:
            try:
                await callback(campaign_id, events)
            except Exception:  # noqa: BLE001 — best-effort: 绝不向调用方抛出
                logger.warning("EventStore.on_append callback failed",
                               exc_info=True)
        return seqs

    async def replay(self, campaign_id: str, upto: int | None = None) -> list[GameEvent]:
        sql = ("SELECT seq, campaign_id, type, payload, actor, approved_by,"
               " ts, causal, version FROM events WHERE campaign_id = ?")
        args: list = [campaign_id]
        if upto is not None:
            sql += " AND seq <= ?"
            args.append(upto)
        sql += " ORDER BY seq ASC"
        out: list[GameEvent] = []
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(sql, args) as cur:
                async for row in cur:
                    raw = {
                        "seq": row[0], "campaign_id": row[1], "type": row[2],
                        "payload": json.loads(row[3]), "actor": row[4],
                        "approved_by": row[5], "ts": row[6],
                        "causal": json.loads(row[7]), "version": row[8],
                    }
                    out.append(GameEvent(**raw))
        return out

    async def one(self, seq: int) -> GameEvent | None:
        """R9 (additive): 按主键取单个事件 (O(1), seq 是全局 PRIMARY KEY)。

        供 WS 实时路径做逐帧可见性判定时**免去全量重放**（原来每次
        INFO_REVEALED 广播都要 replay+project 整条流，延迟随事件数线性增长）。
        """
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT seq, campaign_id, type, payload, actor, approved_by,"
                " ts, causal, version FROM events WHERE seq = ?", (int(seq),)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return GameEvent(**{
            "seq": row[0], "campaign_id": row[1], "type": row[2],
            "payload": json.loads(row[3]), "actor": row[4],
            "approved_by": row[5], "ts": row[6],
            "causal": json.loads(row[7]), "version": row[8],
        })

    def replay_sync(self, campaign_id: str, upto: int | None = None) -> list[GameEvent]:
        import asyncio

        return asyncio.get_event_loop().run_until_complete(self.replay(campaign_id, upto))


def events_roundtrip(events: list[GameEvent]) -> list[GameEvent]:
    """JSON round-trip helper used by replay_check-style assertions."""
    return [event_from_json(event_to_json(ev)) for ev in events]
