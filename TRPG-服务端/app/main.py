"""TRPG single-process assembly (MIT). W-E T12: /api + static + WS + /mcp.
EX-2 D3/D4: /ws 握手 token 校验 + PING 心跳后台任务 (additive 安全加固).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.config import get_version
from app.mcp.server import router as mcp_router
from app.web.access import (install_access_error_handler,
                            load_persisted_tables, router as access_router,
                            token_end_name, token_matches_any_enabled_end)
from app.store.event_store import EventStore
from app.web import ws_bridge
from app.web.identity import router as identity_router
from app.web.pipeline_api import router as pipeline_router  # T7 (additive)
from app.web.rest import router as rest_router
# R4/R5/R15/R16/R20 (additive): GM 单窗口总览 + 分配建议 + 并行线程 + 角色启停 + grounded 建议.
from app.web.overview_api import router as overview_router
# R23 (additive): rulepack binding + per-ruleset resolution surface.
from app.web.rules_api import router as rules_router
from app.npc.routes import router as npc_router  # R28-R31 (additive)
# M3 (additive, T6): 私聊系统（四态调控 + 同场景私聊）。
from app.web.chat_api import router as chat_router
from app.web.scene_api import router as scene_router  # T1 (additive): 场景栏目 + 模组地图生成
# T7 (additive): M4 看板 / M5 战斗 / M6 轨迹快照 / M7 仪表盘
from app.web.board_api import router as board_router
from app.web.combat_api import router as combat_router
from app.web.timeline_api import router as timeline_router
from app.web.dashboard_api import router as dashboard_router
from app.web.wizard_api import router as wizard_router  # T7 (P1a): 8 步向导 REST 入口
from app.web.launcher_api import router as launcher_router  # T13 (additive): 大厅/场次管理
from app.web.rest_repo import (install_repo_error_handler,
                               install_repo_path_guard, router as repo_router)
from app.web.static import mount_static
from app.web.ws import Connection, Hub, heartbeat_loop

hub = Hub()

_hb_task: asyncio.Task | None = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """EX-2 D4: 启动即拉起 PING 心跳后台任务, 服务关闭时取消 (不泄漏任务).

    T2 (additive, ENDPOINT-SPEC-NEW §8): 同时把「事件落库 -> WS 广播」的发布
    回调挂到 EventStore 的单一收口上。未挂载时 on_append 为 None, 行为与改造前
    完全一致 (既有测试/纯 store 脚本不受影响)。
    """
    global _hb_task
    # S1 (T8 fix): single append sink = (a) WS broadcast + (b) story/events.jsonl
    # append-only durable mirror (the basis for M6 rollback-to-any-seq).
    async def _on_append(campaign_id: str, events) -> None:
        try:
            await ws_bridge.publish_events(campaign_id, events)
        except Exception:  # noqa: BLE001 — broadcast failure must not block the mirror
            pass
        try:
            from app.repository import campaign_folder as _cf
            for ev in events or ():
                d = getattr(ev, "model_dump", None)
                payload = d(mode="json") if callable(d) else dict(ev)
                _cf.append_event(campaign_id, payload)
                # P1-2 (T10): CHARACTER_CREATED -> players/<player_id>/card.json
                if str(ev.type) == "CHARACTER_CREATED":
                    card = dict(payload.get("card") or {})
                    pid = str(card.get("player_id") or ev.payload.get("player_id") or "")
                    if pid:
                        _cf.ensure_campaign(campaign_id)
                        _cf.write_player(campaign_id, pid,
                                         card=card,
                                         state={"position": {},
                                                "status": "在场",
                                                "hp": (card.get("derived") or {}).get("hp_max"),
                                                "san": card.get("san_current")})
                # P2: COMBAT_STARTED -> seed NPC profiles for participants
                if str(ev.type) == "COMBAT_STARTED":
                    for p in (ev.payload.get("participants") or []):
                        nid = str((p or {}).get("id") or "")
                        if nid and (p or {}).get("kind") == "npc":
                            _cf.ensure_campaign(campaign_id)
                            _cf.write_npc(campaign_id, nid,
                                          profile={"id": nid, "name": nid, "role": "npc"},
                                          state={"hp": (p or {}).get("hp")})
        except Exception:  # noqa: BLE001 — mirror is best-effort
            pass

    EventStore.on_append = _on_append
    # T2: 载入持久化的 table 注册表 —— 否则服务重启后所有已开桌的
    # table<->campaign 映射丢失, /access/table/resolve 恒 exists:false (F2 失效)。
    load_persisted_tables()
    _hb_task = asyncio.create_task(heartbeat_loop(hub), name="ws-heartbeat")
    # S2 (T8 fix): start a DSH loop for every ACTIVE campaign
    # (campaigns/<id>/campaign.json exists). Loops park in HOLD/WAIT_HOST
    # until their own compute tick; resident cap enforced by ensure_loop.
    _dsh_loops: list = []
    try:
        from app.dsh import loop as dsh_loop
        from app.repository import campaign_folder as _cf
        for _cid in _cf.list_active_campaigns():
            try:
                _dsh_loops.append(await dsh_loop.ensure_loop(_cid))
            except Exception:  # noqa: BLE001 — one bad campaign must not block others
                continue
    except Exception:  # noqa: BLE001 — loop subsystem optional
        pass
    try:
        yield
    finally:
        try:
            for _lp in _dsh_loops:
                await _lp.stop()
        except Exception:  # noqa: BLE001
            pass
        EventStore.on_append = None
        if _hb_task is not None:
            _hb_task.cancel()
            try:
                await _hb_task
            except asyncio.CancelledError:
                pass
            _hb_task = None


app = FastAPI(title="trpg", version=get_version(), lifespan=_lifespan)

app.include_router(rest_router)
app.include_router(rules_router)  # R23: /api/rules/*
app.include_router(npc_router)  # R28-R31 (additive): NPC 自主性控制面
app.include_router(chat_router)  # M3 (additive, T6): /api/campaigns/{c}/chat/*
# T1 (additive): 场景栏目 REST (scenes CRUD/advance + module maps/scene-graph/generate-map)
app.include_router(scene_router)
# T7 (additive): M4 看板 / M5 战斗 / M6 轨迹快照 / M7 仪表盘
app.include_router(board_router)
app.include_router(combat_router)
app.include_router(timeline_router)
app.include_router(dashboard_router)
app.include_router(wizard_router)  # T7 (P1a)
app.include_router(launcher_router)  # T13: 大厅/场次管理
app.include_router(mcp_router)
app.include_router(access_router)
# T7 (additive): 统一审批总线闭环路由 (R10/R11/R17/R18/R19)
app.include_router(pipeline_router)
app.include_router(overview_router)  # R4/R5/R15/R16/R20 (additive)
# SPEC-SERVER-IDENTITY v1.0 (additive): 部署身份端点 GET /__trpg_server__。
# 与 /api/health（只表示「活着」）分离；无鉴权，只暴露部署身份，不含密钥/令牌。
app.include_router(identity_router)
# R22/R1/R2/R13/R3 (additive): 模组仓库 + 规则仓库 REST, 路径穿越守卫,
# RepoError -> {error_code,message,http_status,detail} 映射。
app.include_router(repo_router)
install_repo_path_guard(app)
install_repo_error_handler(app)
install_access_error_handler(app)
mount_static(app)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    params = dict(ws.query_params)
    table_id = params.get("table", "")
    viewer_id = params.get("viewer", "")
    role = params.get("role", "pl")
    try:
        last_seq = int(params.get("last_seq", "-1"))
    except ValueError:
        last_seq = -1
    if not table_id or not viewer_id or role not in ("kp", "pl", "spectator"):
        await ws.close(code=4400)
        return
    # EX-2 D3: token 校验 (?token= 或 Authorization: Bearer; 与 /access 同源,
    # 任一启用端 token 放行). 缺失/不匹配 -> 4400 关闭 (沿用既有参数错误码).
    token = params.get("token", "") or ""
    if not token:
        authz = ws.headers.get("authorization", "")
        if str(authz).lower().startswith("bearer "):
            token = str(authz)[7:].strip()
    if not token_matches_any_enabled_end(token):
        await ws.close(code=4400)
        return
    # R9 (additive): 角色由 **token 所属端** 决定 —— 非 KP 端 token 不得自封 kp。
    # 既有实现信任 ?role=kp，玩家只要改查询串即可拿到 KP 帧（R9 第三条外泄路径）。
    if token_end_name(token) != "webapp" and role == "kp":
        role = "pl"
    await ws.accept()

    async def send(payload: dict) -> None:
        await ws.send_json(payload)

    conn = Connection(table_id=table_id, viewer_id=viewer_id, role=role, send=send)
    missed = await hub.connect(conn, last_seq)
    for frame in missed:
        await ws.send_json(frame)
    try:
        while True:
            raw = await ws.receive_json()
            if isinstance(raw, dict) and raw.get("kind") == "PING":
                continue  # client pings need no reply; server PING comes from hub
            ack = await hub.handle_up(table_id, viewer_id, raw if isinstance(raw, dict) else {})
            await ws.send_json(ack)
    except WebSocketDisconnect:
        await hub.disconnect(table_id, viewer_id)


@app.get("/")
def root() -> dict:
    return {"service": "trpg", "health": "/api/health"}