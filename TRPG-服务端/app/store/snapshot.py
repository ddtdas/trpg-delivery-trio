"""TRPG snapshot + resume (MIT).

Snapshot = serialized SessionState + event_seq_at cursor.
Resume = load snapshot, replay only the tail, continue from cursor.
Python 3.12 compatible.
"""
from __future__ import annotations

import json  # noqa: F401  (snapshot files are JSON; kept explicit)
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.domain.model import SessionState
from app.store.event_store import EventStore
from app.store.projector import project


class SnapshotRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    event_seq_at: int
    cursor: str
    state: dict


_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _safe_campaign_id(campaign_id: str) -> str:
    """campaign_id -> 目录名安全片段 (防路径穿越; 与 access._safe_file_id 同语义)。

    t5 fix (reviewer P1-2): /api/campaigns/{campaign}/save|resume|snapshots 的
    campaign 直接拼进目录路径, 恶意值 (如 ..\\..\\x) 可穿越 data/snapshots 写文件;
    落盘前统一净化, 使读写侧 (save/resume/list) 行为一致。
    """
    name = _SAFE_ID_RE.sub("_", str(campaign_id or ""))
    return name or "campaign"


def snapshot_dir(base: str | Path, campaign_id: str) -> Path:
    d = Path(base) / _safe_campaign_id(campaign_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_snapshot(base: str | Path, state: SessionState) -> Path:
    """Persist state; filename encodes the event seq cursor."""
    d = snapshot_dir(base, state.campaign_id)
    cursor = ""
    if state.turn is not None:
        cursor = state.turn.cursor
    rec = SnapshotRecord(
        campaign_id=state.campaign_id,
        event_seq_at=state.last_seq,
        cursor=cursor,
        state=state.model_dump(mode="json"),
    )
    p = d / ("snapshot_%06d.json" % state.last_seq)
    p.write_text(rec.model_dump_json(), encoding="utf-8")
    return p


def load_snapshot(path: str | Path) -> tuple[SessionState, SnapshotRecord]:
    rec = SnapshotRecord.model_validate_json(Path(path).read_text(encoding="utf-8"))
    return SessionState(**rec.state), rec


def latest_snapshot(base: str | Path, campaign_id: str) -> Path | None:
    d = Path(base) / campaign_id
    if not d.exists():
        return None
    cands = sorted(d.glob("snapshot_*.json"))
    return cands[-1] if cands else None


async def resume(
    store: EventStore,
    base: str | Path,
    campaign_id: str,
) -> SessionState:
    """Crash resume: snapshot + tail replay. No snapshot -> full replay."""
    snap_path = latest_snapshot(base, campaign_id)
    if snap_path is None:
        events = await store.replay(campaign_id)
        return project(events, campaign_id)
    state, rec = load_snapshot(snap_path)
    tail = await store.replay(campaign_id)
    tail = [ev for ev in tail if ev.seq > rec.event_seq_at]
    from app.store.projector import reduce

    for ev in tail:
        reduce(state, ev)
    return state


def snapshot_index(base: str | Path, campaign_id: str) -> list[dict]:
    d = Path(base) / campaign_id
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("snapshot_*.json")):
        rec = SnapshotRecord.model_validate_json(p.read_text(encoding="utf-8"))
        out.append({"file": p.name, "event_seq_at": rec.event_seq_at,
                    "cursor": rec.cursor})
    return out
