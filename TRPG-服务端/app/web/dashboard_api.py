"""T7 (additive): M7 仪表盘 REST API.

  GET  /api/campaigns/{campaign}/dashboard          进度 + AI 建议 + needs_host
  POST /api/campaigns/{campaign}/dashboard/refresh  触发 DSH 重算（JOB_STATUS 句柄）

Progress is computed from the projected state (events count, act, scene,
branch count); the AI section mirrors .dsh/loop_state.json written by the
M8 loop. ``needs_host`` is the decision-point flag: when true the loop is
parked in WAIT_HOST and no automatic write happens.
Python 3.12 compatible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.web.access import _require_kp_end

router = APIRouter()


def _campaign_id(c: str) -> str:
    c = str(c or "").strip()
    if not c or "/" in c or "\\" in c or ".." in c:
        raise HTTPException(status_code=422, detail="bad campaign id")
    return c


@router.get("/api/campaigns/{campaign}/dashboard")
async def dashboard(campaign: str,
                    entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    from app.web import rest as rest_mod
    from app.repository.campaign_folder import read_dsh_state, read_campaign_meta
    c = _campaign_id(campaign)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    from app.domain.rollback import project_with_rollback
    state = project_with_rollback(events, c)  # P1-4: rollback-truncated view
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.type] = by_type.get(e.type, 0) + 1
    meta = read_campaign_meta(c)
    dsh = read_dsh_state(c)
    pending = []
    combat = getattr(state, "combat", {}) or {}
    if combat.get("pending_resolutions"):
        pending.append("combat_round:%s" % combat.get("round"))
    for nid, tend in (getattr(state, "npc_tendencies", {}) or {}).items():
        if (tend or {}).get("status") == "pending":
            pending.append("npc_tendency:%s" % nid)
    progress = {
        "total_events": len(events),
        "by_type": by_type,
        "act_no": getattr(state, "act_no", 0),
        "current_scene": getattr(state, "current_scene", ""),
        "branch_count": len(getattr(state, "branches", [])),
        "timeline_branches": len(getattr(state, "timeline_branches", [])),
        "checkpoints": len(getattr(state, "checkpoints", {})),
        "progress_pct": min(100, int(len(events) / 2)) if events else 0,
    }
    ai = {
        "next_step": str(dsh.get("next_step") or ""),
        "confidence": float(dsh.get("confidence") or 0.0),
        "rationale": str(dsh.get("rationale") or ""),
        "pending": pending,
        "needs_host": bool(dsh.get("needs_host", False)),
        "phase": str(dsh.get("phase") or "idle"),
    }
    return {"campaign": c, "progress": progress, "ai": ai,
            "current_checkpoint": meta.get("current_checkpoint", ""),
            "last_seq": meta.get("last_seq", -1)}


@router.post("/api/campaigns/{campaign}/dashboard/refresh", status_code=202)
async def dashboard_refresh(campaign: str, body: dict[str, Any] | None = None,
                            entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    c = _campaign_id(campaign)
    job_id = "job_dash_%s_%d" % (c, int(datetime.now().timestamp()))
    # Poke the DSH loop (if running) to recompute on the next tick.
    poked = False
    try:
        from app.dsh import loop as loop_mod
        poked = loop_mod.poke(c)
    except Exception:  # noqa: BLE001 — loop not started yet is fine
        poked = False
    return {"ok": True, "job_id": job_id,
            "status": "triggered" if poked else "not_enabled",
            "loop_poked": poked,
            "note": "DSH loop (M8) 会在下一 tick 重新演算（未启用时 AI 建议为空）"}
