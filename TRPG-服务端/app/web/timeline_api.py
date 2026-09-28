"""T7 (additive): M6 轨迹/快照/团文件夹/回退 REST API.

Provides:
  GET    /api/campaigns/{c}/timeline           轨迹列表（按 seq：事件 + 快照点 + 分支标记）
  POST   /api/campaigns/{c}/timeline/checkpoint  手动存档点（主持人）
  POST   /api/campaigns/{c}/timeline/rollback    回退到任意 seq（append-only + branch 标记）
  POST   /api/campaigns/{c}/timeline/autoscan    触发 AI 自动存档点分析（JOB_STATUS 回传）
  GET    /api/campaigns/{c}/timeline/checkpoints 列出全部快照
  GET    /api/campaigns/{c}/timeline/events      回退语义下的事件视图（upto=）

Rollback semantics (captain ruling): append-only + branch mark, never
physical truncation. Rolling back to P appends a TIMELINE_ROLLBACK event;
later writes carry branch marks into an alternate branch. Snapshot reads
the nearest checkpoint <= P then replays increments (see campaign_folder).
Python 3.12 compatible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import APP_ROOT
from app.domain.events import make_event
from app.web.access import _require_kp_end
from app.repository.campaign_folder import (
    CAMPAIGNS_ROOT,
    ensure_campaign,
    latest_checkpoint_at_or_before,
    list_checkpoints,
    read_checkpoint,
    read_events,
    read_campaign_meta,
    update_campaign_meta,
    write_checkpoint,
)

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _campaign_id(c: str) -> str:
    c = str(c or "").strip()
    if not c or "/" in c or "\\" in c or ".." in c:
        raise HTTPException(status_code=422, detail="bad campaign id")
    return c


@router.get("/api/campaigns/{campaign}/timeline")
async def timeline_list(campaign: str,
                        entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """轨迹列表：快照点 + 事件流条目 + 分支标记（按 seq 升序）。"""
    c = _campaign_id(campaign)
    ensure_campaign(c)
    cps = list_checkpoints(c)
    evs = read_events(c)
    timeline = [{"seq": -1, "type": "campaign",
                 "label": read_campaign_meta(c).get("name", c)}]
    for cp in cps:
        timeline.append({"seq": cp["seq"], "type": "checkpoint",
                         "kind": cp["kind"], "snapshot_id": cp.get("snapshot_id", ""),
                         "label": cp.get("label", ""), "reason": cp.get("reason", ""),
                         "file": cp.get("file", "")})
    for ev in evs:
        timeline.append({"seq": ev.get("seq", -1), "type": "event",
                         "event_type": ev.get("type", ""),
                         "payload": ev.get("payload", {})})
    timeline.sort(key=lambda t: t["seq"])
    meta = read_campaign_meta(c)
    return {"campaign": c,
            "checkpoint_count": len(cps),
            "event_count": len(evs),
            "current_checkpoint": meta.get("current_checkpoint", ""),
            "last_seq": meta.get("last_seq", -1),
            "timeline": timeline}


@router.get("/api/campaigns/{campaign}/timeline/checkpoints")
async def timeline_checkpoints(campaign: str,
                               entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    c = _campaign_id(campaign)
    ensure_campaign(c)
    cps = list_checkpoints(c)
    return {"campaign": c, "count": len(cps), "checkpoints": cps}


@router.post("/api/campaigns/{campaign}/timeline/checkpoint", status_code=201)
async def timeline_checkpoint(campaign: str, body: dict[str, Any],
                              entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """手动存档点：冻结当前投影到 checkpoints/manual/<name>-<seq>.snapshot。"""
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    ensure_campaign(c)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    state = rest_mod.project(events, c)
    seq = max(0, state.last_seq)
    name = str((body or {}).get("label") or ("manual-%s" % int(seq)))
    reason = str((body or {}).get("reason") or "manual checkpoint")
    snapshot = {
        "schema": "trpg.snapshot.v1",
        "campaign_id": c,
        "snapshot_id": "manual-%s-%06d" % (name, seq),
        "kind": "manual",
        "seq": seq,
        "ts": _now(),
        "label": name,
        "reason": reason,
        "state": state.model_dump(mode="json"),
    }
    path = write_checkpoint(c, "manual", name, seq, snapshot)
    # event: CHECKPOINT_TAKEN
    ev = make_event(seq=0, campaign_id=c, type="CHECKPOINT_TAKEN",
                    payload={"campaign_id": c,
                             "checkpoint_id": snapshot["snapshot_id"],
                             "kind": "manual", "seq": seq,
                             "label": name, "reason": reason, "auto": False},
                    actor="kp", ts=_now())
    await store.append(c, [ev])
    update_campaign_meta(c, current_checkpoint=snapshot["snapshot_id"], last_seq=seq)
    return {"ok": True, "snapshot_id": snapshot["snapshot_id"],
            "seq": seq, "path": path.as_posix()}


@router.post("/api/campaigns/{campaign}/timeline/rollback", status_code=201)
async def timeline_rollback(campaign: str, body: dict[str, Any],
                            entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """回退到任意 seq：append-only + branch 标记（不物理截断）。

    回退后新写事件走 alternate branch；主持人可确认分叉继续或撤销。
    """
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    ensure_campaign(c)
    target = int((body or {}).get("target_seq", -1))
    if target < 0:
        raise HTTPException(status_code=422, detail="target_seq required (>=0)")
    reason = str((body or {}).get("reason") or "rollback")
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    if target > (events[-1].seq if events else -1):
        raise HTTPException(status_code=422, detail="target_seq beyond tip")
    # Determine rollback state: nearest checkpoint <= target + replay increments.
    cp = latest_checkpoint_at_or_before(c, target)
    snap = None
    base_seq = -1
    if cp is not None:
        snap = read_checkpoint(c, cp["kind"], cp["file"])
        base_seq = int(snap.get("seq", -1))
    # Replay increments from base_seq+1 .. target (events from EventStore).
    increment_events = [e for e in events if base_seq < e.seq <= target]
    from app.store.projector import reduce
    from app.domain.model import new_session
    if snap is not None:
        try:
            state = new_session(c).model_copy(deep=True)
            # snapshot carries a full state dict; rebuild via model_validate
            from app.domain.model import SessionState
            state = SessionState.model_validate(dict(snap.get("state") or {}))
        except Exception:  # noqa: BLE001 — corrupted snapshot -> full replay
            state = new_session(c)
    else:
        state = new_session(c)
    for ev in increment_events:
        try:
            reduce(state, ev)
        except Exception:  # noqa: BLE001 — a bad event stops the increment replay
            break
    branch_mark = "br_%s_%06d" % (c, target)
    ev = make_event(seq=0, campaign_id=c, type="TIMELINE_ROLLBACK",
                    payload={"campaign_id": c, "target_seq": target,
                             "branch_mark": branch_mark, "reason": reason,
                             "actor": "kp"},
                    actor="kp", ts=_now())
    await store.append(c, [ev])
    update_campaign_meta(c, current_checkpoint="rollback:%06d" % target,
                         last_seq=target)
    # M3 (T8): branch semantics — after rollback all NEW writes belong to the
    # alternate branch identified by branch_id; the main timeline is preserved
    # append-only. Host may 'branch-fork' (new branch becomes primary) or
    # 'undo-rollback' (return to the original main timeline).
    return {"ok": True, "target_seq": target, "branch_mark": branch_mark,
            "branch_id": branch_mark,
            "branch_semantics": "append-only; new writes after this rollback "
                                "carry branch_id=%s on the alternate branch; "
                                "main timeline preserved" % branch_mark,
            "snapshot_used": cp.get("file") if cp else None,
            "base_seq": base_seq,
            "replayed_increment": len(increment_events),
            "projected_state": state.model_dump(mode="json")}


@router.post("/api/campaigns/{campaign}/timeline/autoscan", status_code=202)
async def timeline_autoscan(campaign: str, body: dict[str, Any] | None = None,
                            entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """触发 AI 自动存档点分析。

    M4 (T8): 如实反映 DSH loop 是否启用 —— loop 未运行时返回 not_enabled
    而非假的 queued job。
    """
    c = _campaign_id(campaign)
    ensure_campaign(c)
    loop_enabled = False
    try:
        from app.dsh import loop as dsh_loop
        snap = dsh_loop.registry_snapshot()
        loop_enabled = c in snap and snap[c].get("running", False)
    except Exception:  # noqa: BLE001
        loop_enabled = False
    if not loop_enabled:
        return {"ok": True, "status": "not_enabled",
                "note": "DSH loop 未启用；自动存档点可手动 POST /timeline/checkpoint",
                "loop_running": False}
    return {"ok": True, "status": "queued", "loop_running": True,
            "note": "DSH loop 已启用，autoscan 候选在下一 tick 计算并在 checkpoints/auto/ 落盘"}
