"""TRPG voice loop orchestration + perf_metrics ledger (MIT).

Pipeline (all steps injectable; default path is pure mock):
  uplink chunk -> AEC guard -> STT -> align/merge -> TRANSCRIPT_APPENDED
  event -> TRANSCRIPT_READY event -> draft narration (gateway text, marked
  draft) -> TTS speak (dedup) -> perf sample -> perf_metrics row.

The pipeline builds *event payload dicts* and perf rows; persistence
(EventStore append, perf_metrics insert) is the caller's job via the
returned structures — except ``record_perf``/``read_perf`` helpers which
own the tiny perf_metrics ledger (SQLite, separate from the event stream
per runtime-contract §perf).

Clock injection: pass ``clock`` (ms ms-counter) and ``clock.advance`` in
tests for deterministic voice_loop assertions. Real ``time.monotonic``
is used only when no clock is given.

Python 3.12 compatible.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import aiosqlite

from app.voice import aec_guard as AEC
from app.voice import align as ALIGN
from app.voice import browser_input as BI
from app.voice import stt_cloud as STT
from app.voice import tts_out as TTS

__all__ = [
    "VoiceLoopError",
    "run_loop",
    "record_perf",
    "read_perf",
    "summarize_perf",
    "voice_loop_of",
    "VOICE_LOOP_LIMIT_MS",
    "PERF_FIELDS",
    "PERF_SCHEMA",
]

VOICE_LOOP_LIMIT_MS = 1600
PERF_FIELDS = ("vad_ms", "stt_ms", "llm_first_token_ms", "tts_first_packet_ms", "approve_wait_ms")

PERF_SCHEMA = """
CREATE TABLE IF NOT EXISTS perf_metrics (
    event_seq INTEGER NOT NULL,
    campaign_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    vad_ms INTEGER NOT NULL,
    stt_ms INTEGER NOT NULL,
    llm_first_token_ms INTEGER NOT NULL,
    tts_first_packet_ms INTEGER NOT NULL,
    approve_wait_ms INTEGER NOT NULL
);
""".strip()


class VoiceLoopError(ValueError):
    """Illegal voice-loop input."""


class MockClock:
    """Deterministic ms clock for tests: ``now()`` + ``advance(ms)``."""

    def __init__(self) -> None:
        self.t = 0

    def now(self) -> int:
        return self.t

    def advance(self, ms: int) -> None:
        if ms < 0:
            raise ValueError("advance ms must be >= 0")
        self.t += ms


def voice_loop_of(sample: Mapping[str, Any]) -> int:
    return int(sample["vad_ms"]) + int(sample["stt_ms"]) + int(
        sample["llm_first_token_ms"]) + int(sample["tts_first_packet_ms"])


def run_loop(
    campaign_id: str,
    player_id: str,
    chunk: Mapping[str, Any] | None = None,
    transcript_text: str | None = None,
    stt: Callable[..., Any] | None = None,
    draft_narration: Callable[[str], str] | None = None,
    tts: Callable[..., Any] | None = None,
    dedup: Any | None = None,
    clock: Any | None = None,
    vad_ms: int = 110,
    approve_wait_ms: int = 0,
    broadcasting: bool = False,
    is_uplink: bool = True,
) -> dict:
    """Run one voice-loop turn. All cloud steps injectable/mockable.

    Returns {"events": [TRANSCRIPT_APPENDED, TRANSCRIPT_READY],
    "draft": str, "tts": TTSResult-ish dict, "perf": {...},
    "dropped": bool, "degraded_reasons": [...]}.
    """
    if not campaign_id or not isinstance(campaign_id, str):
        raise VoiceLoopError("campaign_id must be a non-empty string")
    if not player_id or not isinstance(player_id, str):
        raise VoiceLoopError("player_id must be a non-empty string")
    now = clock.now if clock is not None and hasattr(clock, "now") else None

    def stamp() -> int:
        if now is not None:
            return int(now())
        import time
        return int(time.monotonic() * 1000)

    t_vad0 = stamp()
    gate = AEC.aec_should_drop({"is_uplink": is_uplink}, broadcasting)
    if gate["drop"]:
        return {"events": [], "draft": "", "tts": None,
                "perf": None, "dropped": True,
                "degraded_reasons": [gate["reason"]]}
    t_vad1 = stamp()

    # STT (default: explicit mock via stt_cloud without key).
    t_stt0 = stamp()
    degraded: list[str] = []
    if transcript_text is not None:
        text, stt_degraded, stt_reason = transcript_text, False, "injected-text"
    elif stt is not None:
        res = stt()
        if isinstance(res, Mapping):
            text, stt_degraded, stt_reason = (
                str(res.get("text", "")), bool(res.get("degraded")), str(res.get("reason", "")))
        else:
            text, stt_degraded, stt_reason = str(res), False, "custom-stt"
    else:
        r = STT.transcribe({"chunks": 1})
        text, stt_degraded, stt_reason = r.text, r.degraded, r.reason
    if stt_degraded:
        degraded.append(f"stt: {stt_reason}")
    t_stt1 = stamp()

    segs = ALIGN.merge_segments([{"text": text, "t0": 0.0, "t1": 1.0, "speaker": player_id}])
    appended = {
        "campaign_id": campaign_id,
        "seg": {**segs[0]},
        "source": "voice",
    }
    ready = {"campaign_id": campaign_id, "transcript_ref": f"tr-{player_id}-{t_stt1}", "aligned": True}

    # Draft narration (LLM草稿标 — never a state write).
    t_llm0 = stamp()
    draft_fn = draft_narration or (lambda t: f"[草稿] {t[:120]}")
    draft = draft_fn(segs[0]["text"])
    t_llm1 = stamp()

    # TTS (default: mock text fallback).
    t_tts0 = stamp()
    if tts is not None:
        tts_res = tts(draft)
        if isinstance(tts_res, Mapping):
            tts_dict = dict(tts_res)
        else:
            tts_dict = {"text": getattr(tts_res, "text", draft),
                        "degraded": getattr(tts_res, "degraded", True),
                        "reason": getattr(tts_res, "reason", "custom-tts")}
    else:
        r2 = TTS.speak(draft, dedup=dedup)
        tts_dict = {"text": r2.text, "degraded": r2.degraded, "reason": r2.reason}
    if tts_dict.get("degraded"):
        degraded.append(f"tts: {tts_dict.get('reason')}")
    t_tts1 = stamp()

    perf = {
        "vad_ms": (t_vad1 - t_vad0) if now is None else vad_ms,
        "stt_ms": (t_stt1 - t_stt0),
        "llm_first_token_ms": (t_llm1 - t_llm0),
        "tts_first_packet_ms": (t_tts1 - t_tts0),
        "approve_wait_ms": approve_wait_ms,
    }
    for k in PERF_FIELDS:
        if not isinstance(perf[k], int) or perf[k] < 0:
            raise VoiceLoopError(f"perf field {k} invalid: {perf[k]!r}")
    perf["voice_loop_ms"] = voice_loop_of(perf)
    perf["within_limit"] = perf["voice_loop_ms"] <= VOICE_LOOP_LIMIT_MS
    return {
        "events": [
            {"type": "TRANSCRIPT_APPENDED", "payload": appended},
            {"type": "TRANSCRIPT_READY", "payload": ready},
        ],
        "draft": draft, "tts": tts_dict, "perf": perf,
        "dropped": False, "degraded_reasons": degraded,
    }


async def record_perf(db_path: str | Path, event_seq: int, campaign_id: str,
                      sample: Mapping[str, Any], ts: str = "") -> None:
    """Insert one perf sample into perf_metrics (never the event stream)."""
    import datetime as _dt
    for f in PERF_FIELDS:
        v = sample.get(f)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise VoiceLoopError(f"perf field {f} must be int >= 0")
    if not isinstance(event_seq, int) or event_seq < 0:
        raise VoiceLoopError("event_seq must be int >= 0")
    ts = ts or _dt.datetime.now(_dt.timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(PERF_SCHEMA)
        await db.execute(
            "INSERT INTO perf_metrics (event_seq, campaign_id, ts, vad_ms, stt_ms,"
            " llm_first_token_ms, tts_first_packet_ms, approve_wait_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_seq, campaign_id, ts, sample["vad_ms"], sample["stt_ms"],
             sample["llm_first_token_ms"], sample["tts_first_packet_ms"],
             sample["approve_wait_ms"]),
        )
        await db.commit()


async def read_perf(db_path: str | Path, campaign_id: str, n: int = 100) -> list[dict]:
    """Read the newest n perf samples (chronological)."""
    if n < 1 or n > 100:
        raise VoiceLoopError("n must be 1..100")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(PERF_SCHEMA)
        async with db.execute(
            "SELECT event_seq, campaign_id, ts, vad_ms, stt_ms, llm_first_token_ms,"
            " tts_first_packet_ms, approve_wait_ms FROM perf_metrics"
            " WHERE campaign_id = ? ORDER BY event_seq DESC LIMIT ?",
            (campaign_id, n),
        ) as cur:
            rows = await cur.fetchall()
    out = [{
        "event_seq": r[0], "campaign_id": r[1], "ts": r[2], "vad_ms": r[3],
        "stt_ms": r[4], "llm_first_token_ms": r[5],
        "tts_first_packet_ms": r[6], "approve_wait_ms": r[7],
    } for r in rows]
    out.reverse()
    return out


def summarize_perf(samples: Sequence[Mapping[str, Any]]) -> dict:
    """Mean + P95 over voice_loop + per-segment means (dashboard shape)."""
    samples = list(samples)
    if not samples:
        return {"mean": 0, "p95": 0,
                "segments": {k: 0 for k in PERF_FIELDS}, "n": 0}
    loops = sorted(voice_loop_of(s) for s in samples)
    n = len(samples)
    mean = round(sum(loops) / n)
    p95 = loops[min(n - 1, -(-n * 95 // 100) - 1)]
    segs = {k: round(sum(int(s[k]) for s in samples) / n) for k in PERF_FIELDS}
    return {"mean": mean, "p95": p95, "segments": segs, "n": n}


def _unused_import_guard() -> None:
    _ = BI.MAX_CHUNK_BYTES  # keep browser_input import live (lint-visible seam)
