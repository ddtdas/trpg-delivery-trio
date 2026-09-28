"""TRPG campaign memory — rolling summaries in SQLite (MIT).

Async, single-writer friendly. One row per compaction step:
``memory(campaign_id, upto_seq, summary, updated_ts)`` keeps only the
latest row per campaign (append-then-trim inside one transaction).

Pure helpers (``compact_texts``) are sync and unit-testable without a DB:
keep the newest N chars worth of signal — here: join newest-first up to
``max_chars``, then prefix with the previous summary. LLM calls are the
caller's job (pass the materialized text in); this module never calls
the network.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import aiosqlite

__all__ = ["MemoryStore", "compact_texts", "MEMORY_SCHEMA"]

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    campaign_id TEXT NOT NULL,
    upto_seq INTEGER NOT NULL,
    summary TEXT NOT NULL,
    updated_ts TEXT NOT NULL,
    PRIMARY KEY (campaign_id, upto_seq)
);
""".strip()


def compact_texts(
    previous_summary: str,
    new_texts: Sequence[str],
    max_chars: int = 2000,
) -> str:
    """Fold new texts (chronological) onto the previous summary.

    Keeps the tail (newest) that fits in ``max_chars``; prefixes the
    previous summary's head when room remains. Deterministic, pure.
    """
    if not isinstance(previous_summary, str):
        raise TypeError("previous_summary must be str")
    if not isinstance(max_chars, int) or max_chars < 64:
        raise ValueError("max_chars must be int >= 64")
    texts = [t for t in new_texts if isinstance(t, str) and t.strip()]
    tail: list[str] = []
    used = 0
    for t in reversed(texts):
        t = t.strip()
        if used + len(t) + 1 > max_chars:
            break
        tail.append(t)
        used += len(t) + 1
    tail.reverse()
    out = "\n".join(tail)
    prev = previous_summary.strip()
    if prev and used + len(prev) + 12 <= max_chars:
        out = f"[前情]\n{prev}\n[新增]\n{out}" if out else prev
    return out


class MemoryStore:
    """SQLite-backed rolling summary store (one live row per campaign)."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute(MEMORY_SCHEMA)
            await db.commit()

    async def save(self, campaign_id: str, upto_seq: int, summary: str) -> None:
        if not campaign_id or not isinstance(campaign_id, str):
            raise ValueError("campaign_id must be a non-empty string")
        if not isinstance(upto_seq, int) or upto_seq < 0:
            raise ValueError("upto_seq must be int >= 0")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("summary must be a non-empty string")
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute(MEMORY_SCHEMA)
            await db.execute(
                "INSERT OR REPLACE INTO memory (campaign_id, upto_seq, summary, updated_ts)"
                " VALUES (?, ?, ?, ?)",
                (campaign_id, upto_seq, summary.strip(), ts),
            )
            # Keep only the newest row per campaign (rolling summary).
            await db.execute(
                "DELETE FROM memory WHERE campaign_id = ? AND upto_seq < ?",
                (campaign_id, upto_seq),
            )
            await db.commit()

    async def load(self, campaign_id: str) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(MEMORY_SCHEMA)
            async with db.execute(
                "SELECT campaign_id, upto_seq, summary, updated_ts FROM memory"
                " WHERE campaign_id = ? ORDER BY upto_seq DESC LIMIT 1",
                (campaign_id,),
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return {
            "campaign_id": row[0], "upto_seq": row[1],
            "summary": row[2], "updated_ts": row[3],
        }

    def save_sync(self, campaign_id: str, upto_seq: int, summary: str) -> None:
        import asyncio

        asyncio.run(self.save(campaign_id, upto_seq, summary))

    def load_sync(self, campaign_id: str) -> dict | None:
        import asyncio

        return asyncio.run(self.load(campaign_id))
