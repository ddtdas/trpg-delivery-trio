"""TRPG MCP streamable-http server: /mcp tools/list + tools/call (MIT).

Thin adapter over CommandBus/QueryBus-adjacent tool functions; permission
enforced at the entry via auth.check_tool_access. EX-MCP: /mcp 会话端点
(GET /mcp 握手 + POST /mcp/tools/list) 加 /access 同源 token 鉴权 —— 任一
启用端 (webapp/mobile/recorder) token 放行, 无/错/未启用端 401; 既有
/mcp/tools/call 行为保持不变 (工具级 actor/KP 矩阵仍由 check_tool_access
把关)。Python 3.12 compatible; additive。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.config import APP_ROOT
from app.mcp import auth as _mcp_auth
from app.mcp.auth import AuthError, check_tool_access
from app.mcp.schemas import ALL_NAMES, FROZEN_NAMES, frozen_name, tool_spec
from app.mcp.tools_checks import do_check, do_preview
from app.mcp.tools_media import do_image, do_job_status, do_summarize, do_transcribe
from app.mcp.tools_table import (do_character_create, do_event_inject,
                                 do_info_distribute, do_map_command,
                                 do_narration_approve, do_narration_propose,
                                 do_session_state)
from app.store.event_store import EventStore
from app.web.access import token_matches_any_enabled_end

router = APIRouter()

DATA_DIR = APP_ROOT / "data"
DEFAULT_DB = DATA_DIR / "trpg.db"


def _require_any_enabled_end(authorization: str | None = Header(default=None),
                             token: str | None = Query(default=None)) -> None:
    """EX-MCP: /mcp 会话端点鉴权 —— 与 /access 同源 (任一启用端 token 放行).

    无/错 token、未启用端 token 一律 401 (detail 与既有 MCP _err 同形)。
    供 GET /mcp 握手与 POST /mcp/tools/list 使用; /mcp/tools/call 行为不变。
    """
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if token:
        provided = token
    if not token_matches_any_enabled_end(provided):
        raise HTTPException(status_code=401, detail={"error": "bad or missing token"})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CallBody(StrictModel):
    name: str
    arguments: dict[str, Any] = {}


def _store() -> EventStore:
    return EventStore(Path(DEFAULT_DB))


def _err(error: str, status: int = 403) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error})


@router.get("/mcp")
def mcp_handshake(_: None = Depends(_require_any_enabled_end)) -> dict:
    return {"service": "trpg-mcp", "transport": "streamable-http",
            "server": "trpg", "tools": len(FROZEN_NAMES)}


@router.post("/mcp/tools/list")
def tools_list(_: None = Depends(_require_any_enabled_end)) -> dict:
    return {"tools": [{"name": n} for n in ALL_NAMES]}


@router.post("/mcp/tools/call")
async def tools_call(body: CallBody) -> dict:
    name = body.name
    raw = name.replace("mcp__trpg__", "", 1) if name.startswith("mcp__trpg__") \
        else name
    args = dict(body.arguments or {})
    store = _store()
    try:
        actor = check_tool_access(raw, args)
    except AuthError as exc:
        raise _err(exc.error) from exc
    try:
        if raw == "roll_preview":
            return await do_preview(args)
        if raw == "session_state":
            return await do_session_state(args, store)
        if raw == "job_get_status":
            return await do_job_status(args)
        if raw == "roll_check":
            return await do_check(args, store)
        if raw == "character_create":
            return await do_character_create(args, store)
        if raw == "narration_propose":
            return await do_narration_propose(args, store)
        if raw == "narration_approve":
            return await do_narration_approve(args, store)
        if raw == "info_distribute":
            return await do_info_distribute(args, store)
        if raw == "event_inject":
            return await do_event_inject(args, store)
        if raw == "map_command":
            return await do_map_command(args, store, actor)
        if raw == "transcribe_audio":
            return await do_transcribe(args, store)
        if raw == "image_generate":
            return await do_image(args, store)
        if raw == "summarize_session":
            return await do_summarize(args, store)
        if raw == "npc_act":
            return await do_npc_act(args, store)
    except AuthError as exc:
        raise _err(exc.error) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail={"error": "unknown_tool",
                                                 "name": name})


async def do_npc_act(args: dict[str, Any], store: EventStore) -> dict[str, Any]:
    """R2 (R30/R31): MCP npc_act —— 与 REST/WS **同源**。

    委派 app.npc.director.handle_npc_act：候选一律入主持人待审队列
    （NPC_ACT_PROPOSED + npc_proposal[status=pending]），经既有唯一审批总线
    POST /api/campaigns/{c}/approvals 拍板后才产生 NPC_ACT_APPROVED。
    响应**不回显候选台词**（与 REST 一致）。
    """
    from app.npc import director as _npc_director
    from app.web.rest import NpcAct
    campaign_id = str(args.get("campaign_id") or "").strip()
    if not campaign_id:
        raise _err("campaign_id_required", 422)
    payload = {k: v for k, v in args.items()
               if k in ("npc_id", "lines", "trigger", "player_id",
                        "situation")}
    try:
        body = NpcAct(**payload)
    except ValueError as exc:
        raise _err("validation_error", 422) from exc
    try:
        return await _npc_director.handle_npc_act(campaign_id, body)
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, str):
            detail = {"error": detail.split(":")[0].strip() or "npc_error",
                      "detail": detail}
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc


def describe() -> dict[str, Any]:
    return {"server": "trpg", "tools": [tool_spec(r) for r in
                                        [n.replace("mcp__trpg__", "")
                                         for n in FROZEN_NAMES]],
            # R2 (R30): 门开时 npc_act 不再是保留 403 工具；门关时逐字保留旧声明。
            "reserved_403": ([] if _mcp_auth.NPC_GATE_OPEN
                             else [frozen_name("npc_act")]),
            "npc_gate": ("open" if _mcp_auth.NPC_GATE_OPEN else "locked")}
