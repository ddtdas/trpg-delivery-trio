"""T7 (additive): M4 主持人看板 + NPC 倾向 REST API.

Board:
  GET  /api/campaigns/{c}/board                    主持人看板全量（玩家/NPC/剧情/AI）
  POST /api/campaigns/{c}/board/npc-tendency      主持人改 NPC 倾向 -> NPC_TENDENCY_UPDATED(source=host)
  POST /api/campaigns/{c}/board/npc-refresh       触发 AI 重算倾向（JOB_STATUS 句柄）
  GET  /api/campaigns/{c}/board/unexplored        未探索地区（地图 rooms - 已访问场景 rooms）

NPC tendency: source=host -> direct write; source=ai -> pending until
approve (NPC_TENDENCY_APPROVED). Board view hides AI internals for
non-host viewers (scope: host-only endpoints via _require_kp_end).
Python 3.12 compatible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.config import APP_ROOT
from app.domain.events import make_event
from app.web.access import _require_kp_end

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _campaign_id(c: str) -> str:
    c = str(c or "").strip()
    if not c or "/" in c or "\\" in c or ".." in c:
        raise HTTPException(status_code=422, detail="bad campaign id")
    return c


@router.get("/api/campaigns/{campaign}/board")
async def board_view(campaign: str,
                     entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """主持人看板全量（玩家/NPC/剧情阶段/AI 建议）。"""
    from app.web import rest as rest_mod
    from app.domain.rollback import project_with_rollback
    from app.repository.campaign_folder import (
        ensure_campaign, list_npcs, list_players, read_player_state,
        read_dsh_state, read_relations)
    c = _campaign_id(campaign)
    ensure_campaign(c)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    # P1-4: authoritative state is the rollback-truncated projection
    state = project_with_rollback(events, c)

    players = []
    for pid in list_players(c):
        st = read_player_state(c, pid)
        card = state.characters.get(pid, {})
        players.append({
            "player_id": pid,
            "name": str((card or {}).get("name") or pid),
            "status": str(st.get("status") or "在场"),
            "position": st.get("position") or {},
            "hp": st.get("hp"), "san": st.get("san"),
            "chat_state": st.get("chat_state", ""),
        })

    npcs = []
    for nid in list_npcs(c):
        tend = (state.npc_tendencies or {}).get(nid, {})
        npcs.append({
            "npc_id": nid,
            "name": nid,
            "position": {"map_id": str(getattr(state, "current_scene", "") or ""),
                         "room": ""},
            "behavior_tendency": tend,
            "story_stage": str((tend or {}).get("stage", "") or "调查中"),
            "items": [],
            "visibility": "revealed",
        })

    story = {
        "act_no": getattr(state, "act_no", 0),
        "current_scene": getattr(state, "current_scene", ""),
        "scene_count": len(getattr(state, "scene_trace", [])),
        "progress": "in-progress",
    }
    dsh = read_dsh_state(c)
    ai = {
        "next_step": str(dsh.get("next_step") or ""),
        "confidence": float(dsh.get("confidence") or 0.0),
        "pending_proposals": list(dsh.get("pending_proposals") or []),
        "needs_host": bool(dsh.get("needs_host", False)),
    }
    return {"campaign": c, "players": players, "npcs": npcs,
            "story": story, "ai": ai, "relations": read_relations(c)}


@router.get("/api/campaigns/{campaign}/board/unexplored")
async def board_unexplored(campaign: str,
                           entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """未探索地区：模块地图所有 rooms - 已访问场景 rooms。"""
    from app.web import rest as rest_mod
    from app.web.scene_api import _module_dir, _load_maps, _load_graph
    c = _campaign_id(campaign)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    state = rest_mod.project(events, c)
    # module from table config (same resolution as scene_api)
    try:
        from app.web import access as access_mod
        cfg = (rest_mod.TABLES.get(access_mod._table_entry_by_campaign(c)) or {}).get("config") or {}
        mid = str(cfg.get("module") or cfg.get("module_id") or "dead_light")
    except Exception:  # noqa: BLE001
        mid = "dead_light"
    try:
        mdir = _module_dir(mid)
        maps = _load_maps(mdir)
        graph = _load_graph(mdir)
        all_rooms = {r.get("id") for m in maps for r in (m.get("rooms") or [])}
        visited = {str(n.get("room_ref")) for n in (graph.get("nodes") or [])
                   if str(n.get("map_ref") or "") in {m.get("id") for m in maps}}
        # visited only counts rooms actually entered by scene advances
        scene_explored = {s.get("room_ref") for s in getattr(state, "scene_trace", [])}
        unexplored = sorted(all_rooms - scene_explored)
        return {"campaign": c, "module_id": mid,
                "all_rooms": sorted(all_rooms),
                "explored": sorted(scene_explored),
                "unexplored": unexplored}
    except Exception:  # noqa: BLE001 — module lookup may fail
        return {"campaign": c, "module_id": mid, "unexplored": []}


@router.post("/api/campaigns/{campaign}/board/npc-tendency", status_code=201)
async def board_npc_tendency(campaign: str, body: dict[str, Any],
                             entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """主持人修改 NPC 倾向 -> NPC_TENDENCY_UPDATED(source=host) 直写。"""
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    npc_id = str((body or {}).get("npc_id") or "").strip()
    if not npc_id:
        raise HTTPException(status_code=422, detail="npc_id required")
    tendency = dict((body or {}).get("tendency") or {})
    if not tendency:
        raise HTTPException(status_code=422, detail="tendency required")
    store = rest_mod._store()
    await store.init()
    ev = make_event(seq=0, campaign_id=c, type="NPC_TENDENCY_UPDATED",
                    payload={"campaign_id": c, "npc_id": npc_id,
                             "tendency": tendency, "source": "host"},
                    actor="kp", ts=_now())
    seqs = await store.append(c, [ev])
    # write to campaign folder tendency.json
    try:
        from app.repository import campaign_folder as cf
        cf.ensure_campaign(c)
        cf.write_npc(c, npc_id, tendency=tendency)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "seq": seqs[0], "npc_id": npc_id,
            "tendency": tendency, "source": "host"}


@router.post("/api/campaigns/{campaign}/board/npc-refresh", status_code=202)
async def board_npc_refresh(campaign: str, body: dict[str, Any] | None = None,
                            entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """触发 AI 重算 NPC 倾向。

    M4 (T8): 如实返回 DSH loop 是否已启用 —— 不再许诺假的 queued job。
    """
    c = _campaign_id(campaign)
    npc_id = str((body or {}).get("npc_id") or "").strip()
    loop_enabled = False
    try:
        from app.dsh import loop as dsh_loop
        loop_enabled = dsh_loop.poke(c) or True  # poke returns running; True means registered
        from app.dsh import loop as _l2
        snap = _l2.registry_snapshot()
        loop_enabled = c in snap and snap[c].get("running", False)
    except Exception:  # noqa: BLE001
        loop_enabled = False
    if not loop_enabled:
        return {"ok": True, "status": "not_enabled",
                "npc_id": npc_id or "all",
                "note": "DSH loop 未对本团启用（无 active campaign 目录或未达启动条件）；倾向由主持人直写生效",
                "loop_running": False}
    return {"ok": True, "status": "triggered", "npc_id": npc_id or "all",
            "loop_running": True,
            "note": "DSH loop 已启用，下一 tick 重算该 NPC 倾向并在 .dsh/ 落盘"}
