"""T13 (additive): 大厅/场次管理 REST API (launcher).

Campaign phase machine: lobby -> configuring -> running -> paused/ended.
PHASE_UPDATED is the independent phase-change event (S1 ruling); resume
(read from checkpoint) is separate from rollback (S2 ruling).

  GET    /api/campaigns                    团列表（phase/path/last_checkpoint/players/maps）
  POST   /api/campaigns                    新建团 {name, ruleset, module_ref?, campaign_id?}
  GET    /api/campaigns/{id}/lobby         开始页聚合（campaign.json+players+scenes+checkpoints+phase）
  POST   /api/campaigns/{id}/start         phase -> running（记 started_seq + 自动存档点）
  POST   /api/campaigns/{id}/pause|end     phase 切换（可选自动存档）
  POST   /api/campaigns/{id}/resume        从 checkpoint 恢复（读档；不落 TIMELINE_ROLLBACK）
  GET    /api/campaigns/{id}/checkpoints   存档点列表（复用 timeline_api）
Python 3.12 compatible.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.config import APP_ROOT
from app.domain.events import make_event
from app.web.access import _require_any_end, _require_kp_end
from app.repository.campaign_folder import (
    CAMPAIGNS_ROOT,
    ensure_campaign,
    list_active_campaigns,
    list_checkpoints,
    list_players,
    latest_checkpoint_at_or_before,
    read_campaign_meta,
    update_campaign_meta,
    write_campaign_meta,
)

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _campaign_id(c: str) -> str:
    c = str(c or "").strip()
    if not c or "/" in c or "\\" in c or ".." in c:
        raise HTTPException(status_code=422, detail="bad campaign id")
    return c


_PHASES = ("lobby", "configuring", "running", "paused", "ended")


def _phase_gate(campaign: str, expected: str) -> None:
    """M2: server-side phase gate — 409 when phase != expected."""
    meta = read_campaign_meta(campaign)
    cur = str(meta.get("phase") or "lobby")
    if cur != expected:
        raise HTTPException(status_code=409,
                            detail="campaign phase=%s, expected %s (phase gate)" % (cur, expected))


@router.get("/api/campaigns")
async def list_campaigns(authorization: str | None = Header(default=None),
                         token: str | None = Query(default=None)) -> dict[str, Any]:
    """团列表（任意启用端可读）。"""
    _require_any_end(authorization=authorization, token=token)
    out = []
    for cid in list_active_campaigns():
        meta = read_campaign_meta(cid)
        cps = list_checkpoints(cid)
        last = cps[-1] if cps else None
        out.append({
            "campaign_id": cid,
            "name": meta.get("name", cid),
            "ruleset": meta.get("ruleset", "coc7"),
            "module_id": meta.get("module_id", ""),
            "phase": meta.get("phase", "lobby"),
            "players": len(list_players(cid)),
            "checkpoints": len(cps),
            "last_checkpoint": last.get("snapshot_id") if last else None,
            "last_seq": meta.get("last_seq", -1),
        })
    return {"campaigns": out, "count": len(out)}


@router.post("/api/campaigns", status_code=201)
async def create_campaign(body: dict[str, Any],
                          entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """新建团（主持人）。M5: 连接码=campaign_id 可枚举，文档明示非密钥；默认 uuid 短码。"""
    name = str((body or {}).get("name") or "").strip() or ("campaign-" + uuid.uuid4().hex[:6])
    ruleset = str((body or {}).get("ruleset") or "coc7")
    module_ref = str((body or {}).get("module_ref") or "").strip()
    cid = str((body or {}).get("campaign_id") or ("c_" + uuid.uuid4().hex[:6])).strip()
    cid = _campaign_id(cid)
    from app.repository.campaign_folder import campaign_dir
    if (CAMPAIGNS_ROOT / cid / "campaign.json").is_file():
        raise HTTPException(status_code=409, detail="campaign exists: %s" % cid)
    ensure_campaign(cid)
    write_campaign_meta(cid, name=name, ruleset=ruleset, module_id=module_ref,
                       phase="lobby", created_at=_now())
    from app.web import rest as rest_mod
    store = rest_mod._store()
    await store.init()
    ev = make_event(seq=0, campaign_id=cid, type="PHASE_UPDATED",
                    payload={"campaign_id": cid, "phase": "lobby",
                             "actor": "kp", "reason": "campaign created"},
                    actor="kp", ts=_now())
    await store.append(cid, [ev])
    return {"ok": True, "campaign_id": cid, "name": name, "phase": "lobby",
            "join_code_note": "连接码=campaign_id，非密钥（鉴权靠端 token）"}


@router.get("/api/campaigns/{campaign}/lobby")
async def lobby_view(campaign: str,
                     entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """开始页聚合。M4: 复用 scene_api._scenes_for / list_checkpoints / state.characters。"""
    from app.web import rest as rest_mod
    from app.web.scene_api import _resolve_module, _scenes_for
    c = _campaign_id(campaign)
    ensure_campaign(c)
    meta = read_campaign_meta(c)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    state = rest_mod.project(events, c)
    mid = _resolve_module(c, str(meta.get("module_id") or ""))
    scenes = _scenes_for(c, mid) if mid else []
    cps = list_checkpoints(c)
    players = []
    for pid in list_players(c):
        card = state.characters.get(pid, {})
        players.append({"player_id": pid, "name": str((card or {}).get("name") or pid)})
    return {
        "campaign_id": c,
        "name": meta.get("name", c),
        "ruleset": meta.get("ruleset", "coc7"),
        "module_id": meta.get("module_id", ""),
        "phase": meta.get("phase", "lobby"),
        "started_seq": meta.get("started_seq"),
        "players": players,
        "scene_count": len(scenes),
        "checkpoints": cps,
        "last_seq": meta.get("last_seq", -1),
    }


@router.post("/api/campaigns/{campaign}/configure", status_code=201)
async def campaign_configure(campaign: str, body: dict[str, Any] | None = None,
                             entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """进入配置阶段：phase lobby -> configuring（开团前的团配置）。

    T14 补：原实现只有 configuring -> running（start），但无任何路径把
    lobby 推进到 configuring，导致「新建团 -> 开始游戏」必 409。本端点补齐
    lobby -> configuring 这一跳，使 新建 -> 配置 -> 开始 流程闭环。
    """
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    ensure_campaign(c)
    _phase_gate(c, "lobby")
    store = rest_mod._store()
    await store.init()
    update_campaign_meta(c, phase="configuring")
    ev = make_event(seq=0, campaign_id=c, type="PHASE_UPDATED",
                    payload={"campaign_id": c, "phase": "configuring",
                             "actor": "kp", "reason": "entering configuration"},
                    actor="kp", ts=_now())
    await store.append(c, [ev])
    return {"ok": True, "campaign_id": c, "phase": "configuring"}


@router.post("/api/campaigns/{campaign}/start", status_code=201)
async def campaign_start(campaign: str, body: dict[str, Any] | None = None,
                         entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """开始游戏：phase -> running，记 started_seq + 自动存档点 + PHASE_UPDATED(running)."""
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    ensure_campaign(c)
    _phase_gate(c, "configuring")
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    tip = events[-1].seq if events else -1
    started_seq = tip + 1
    update_campaign_meta(c, phase="running", started_seq=started_seq,
                         last_started_at=_now())
    ev = make_event(seq=0, campaign_id=c, type="PHASE_UPDATED",
                    payload={"campaign_id": c, "phase": "running",
                             "started_seq": started_seq, "actor": "kp",
                             "reason": "campaign started"},
                    actor="kp", ts=_now())
    await store.append(c, [ev])
    try:
        state = rest_mod.project(events + [ev], c)
        from app.repository import campaign_folder as cf
        snap = {"schema": "trpg.snapshot.v1", "campaign_id": c,
                "snapshot_id": "auto-start-%06d" % started_seq,
                "kind": "auto", "seq": started_seq, "ts": _now(),
                "label": "开团自动存档", "reason": "campaign start",
                "phase": "running",  # S2: snapshot schema carries phase
                "state": state.model_dump(mode="json")}
        cf.write_checkpoint(c, "auto", "start", started_seq, snap)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "campaign_id": c, "phase": "running",
            "started_seq": started_seq}


@router.post("/api/campaigns/{campaign}/pause")
async def campaign_pause(campaign: str, body: dict[str, Any] | None = None,
                         entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    ensure_campaign(c)
    _phase_gate(c, "running")
    update_campaign_meta(c, phase="paused")
    store = rest_mod._store()
    await store.init()
    ev = make_event(seq=0, campaign_id=c, type="PHASE_UPDATED",
                    payload={"campaign_id": c, "phase": "paused",
                             "actor": "kp", "reason": "paused"},
                    actor="kp", ts=_now())
    await store.append(c, [ev])
    return {"ok": True, "campaign_id": c, "phase": "paused"}


@router.post("/api/campaigns/{campaign}/end")
async def campaign_end(campaign: str, body: dict[str, Any] | None = None,
                       entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    ensure_campaign(c)
    update_campaign_meta(c, phase="ended")
    store = rest_mod._store()
    await store.init()
    ev = make_event(seq=0, campaign_id=c, type="PHASE_UPDATED",
                    payload={"campaign_id": c, "phase": "ended",
                             "actor": "kp", "reason": "ended"},
                    actor="kp", ts=_now())
    await store.append(c, [ev])
    return {"ok": True, "campaign_id": c, "phase": "ended"}


@router.post("/api/campaigns/{campaign}/resume", status_code=201)
async def campaign_resume(campaign: str, body: dict[str, Any],
                          entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """读档（S2 ruling）：从 checkpoint 恢复新历程，不落 TIMELINE_ROLLBACK。"""
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    ensure_campaign(c)
    checkpoint_id = str((body or {}).get("checkpoint_id") or "").strip()
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    tip = events[-1].seq if events else -1
    if not checkpoint_id:
        cp = latest_checkpoint_at_or_before(c, tip)
        if cp is None:
            raise HTTPException(status_code=422, detail="no checkpoint to resume from")
        checkpoint_id = cp.get("snapshot_id") or cp.get("file")
    started_seq = tip + 1
    update_campaign_meta(c, phase="running", started_seq=started_seq,
                         current_checkpoint=checkpoint_id, last_started_at=_now())
    ev = make_event(seq=0, campaign_id=c, type="PHASE_UPDATED",
                    payload={"campaign_id": c, "phase": "running",
                             "started_seq": started_seq, "actor": "kp",
                             "reason": "resumed from %s" % checkpoint_id},
                    actor="kp", ts=_now())
    await store.append(c, [ev])
    return {"ok": True, "campaign_id": c, "phase": "running",
            "started_seq": started_seq, "resumed_from": checkpoint_id}


@router.get("/api/campaigns/{campaign}/checkpoints")
async def campaign_checkpoints(campaign: str,
                               entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    c = _campaign_id(campaign)
    ensure_campaign(c)
    cps = list_checkpoints(c)
    return {"campaign": c, "count": len(cps), "checkpoints": cps}
