"""M3 (additive, T6): 私聊系统 —— 同场景玩家私聊 + 主持人四态调控。

设计（T5 §3 + MASTER-PLAN M3）:
  * 四态（服务端权威，不靠前端隐藏）:
      chat_enabled  能私聊 + 公共频道（默认）
      chat_disabled 不能私聊，公共频道开放
      public_only   能交流(公共频道)，不能私聊（对齐用户表述）
      all_disabled  私聊 + 公共频道全关
  * 事件: CHAT_MODE_SET（主持人直写）/ PRIVATE_MSG（玩家，门控）
  * 传输: 复用冻结 WS 帧 —— PRIVATE_MSG -> WHISPER（ws_bridge 映射）;
          CHAT_MODE_SET -> STATE_DELTA(chat_mode)。
  * 同场景约束: to_players 必须与发送者同房间/同场景（positions_from_state 派生），
    跨场景拒绝 422。
  * 鉴权复用端隔离: 主持人端点 = webapp token；玩家端点 = mobile token
    （玩家身份自报 player_id，与 /access/mobile/action 同构）。
Python 3.12 compatible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.app_core.perception import positions_from_state
from app.domain.events import make_event
from app.store.projector import project
from app.web import rest as rest_mod
from app.web.access import _require_kp_end, _require_player_end

router = APIRouter()

CHAT_MODES: tuple[str, ...] = (
    "chat_enabled", "chat_disabled", "public_only", "all_disabled",
)

# 公共频道专用目标标记：私聊端点收到 _public_ 时由服务端展开为全体玩家，
# 事件/WS 仍走 PRIVATE_MSG + WHISPER（目标=全体），玩家端以「公共」标签展示。
PUBLIC_TARGET = "_public_"

# 四态 -> 玩家状态文案（前端徽标；服务端权威派生）
MODE_PLAYER_STATE: dict[str, str] = {
    "chat_enabled": "可私聊",
    "chat_disabled": "仅公共",
    "public_only": "仅公共",
    "all_disabled": "不能交流",
}

# 私聊 / 公共频道开关（服务端权威门控）
_MODE_PRIVATE_ALLOWED: dict[str, bool] = {
    "chat_enabled": True,
    "chat_disabled": False,
    "public_only": False,
    "all_disabled": False,
}
_MODE_PUBLIC_ALLOWED: dict[str, bool] = {
    "chat_enabled": True,
    "chat_disabled": True,
    "public_only": True,
    "all_disabled": False,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatModeBody(StrictModel):
    mode: Literal["chat_enabled", "chat_disabled", "public_only", "all_disabled"]
    scope: str = "campaign"  # campaign（本版整团）| player:<id> | pair:<a>+<b>


class PrivateMsgBody(StrictModel):
    player_id: str
    to_players: list[str]
    text: str
    room_ref: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_campaign(table_id_or_campaign: str) -> str:
    """table_id / campaign 双写解析（与 ws_bridge._rooms_for / rest 同源）。"""
    t = rest_mod.TABLES.get(table_id_or_campaign)
    if t and str(t.get("campaign_id") or ""):
        return str(t["campaign_id"])
    return table_id_or_campaign


async def _project_async(campaign: str):
    store = rest_mod._store()
    await store.init()
    events = await store.replay(campaign)
    return project(events, campaign)


@router.get("/api/campaigns/{campaign}/chat/status")
async def chat_status(
    campaign: str,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> dict[str, Any]:
    """GET 四态 + 玩家状态（任意启用端 token 可读；匿名按玩家视角默认）。

    返回 {campaign, mode, players:[{id, chat_state}], private_allowed, public_allowed}。
    players 取投影态里已建卡玩家 + 已落位 token，去重排序。
    """
    from app.web.access import _require_any_end
    _require_any_end(authorization=authorization, token=token)
    camp = _resolve_campaign(campaign)
    state = await _project_async(camp)
    mode = state.chat_mode or "chat_enabled"
    pos = positions_from_state(state)
    ids: list[str] = []
    # characters 的键是 card_id，值内含 player_id
    for cid, card in list(state.characters.items()):
        pid = str((card or {}).get("player_id") or cid)
        if pid not in ids:
            ids.append(pid)
    for tok in list(pos.keys()):
        if tok not in ids:
            ids.append(tok)
    return {
        "campaign": camp,
        "mode": mode,
        "players": [{"id": pid, "chat_state": MODE_PLAYER_STATE.get(mode, "可私聊")}
                    for pid in sorted(ids)],
        "private_allowed": _MODE_PRIVATE_ALLOWED.get(mode, True),
        "public_allowed": _MODE_PUBLIC_ALLOWED.get(mode, True),
    }


@router.post("/api/campaigns/{campaign}/chat/mode", status_code=201)
async def chat_set_mode(
    campaign: str,
    body: ChatModeBody,
    entry: dict[str, Any] = Depends(_require_kp_end),
) -> dict[str, Any]:
    """主持人调控四态 -> CHAT_MODE_SET（服务端权威直写，玩家仅读展示）。"""
    camp = _resolve_campaign(campaign)
    store = rest_mod._store()
    await store.init()
    ev = make_event(
        seq=0, campaign_id=camp, type="CHAT_POLICY_UPDATED",
        payload={"campaign_id": camp, "mode": body.mode, "actor": "kp"},
        actor="kp", ts=_now(),
    )
    seqs = await store.append(camp, [ev])
    return {"seq": seqs[0], "type": "CHAT_POLICY_UPDATED",
            "mode": body.mode, "scope": body.scope}


@router.post("/api/campaigns/{campaign}/chat/private", status_code=201)
async def chat_send_private(
    campaign: str,
    body: PrivateMsgBody,
    entry: dict[str, Any] = Depends(_require_player_end),
) -> dict[str, Any]:
    """玩家私聊 -> PRIVATE_MSG（门控，服务端权威）。

    1) 四态: 仅 chat_enabled 放行私聊；其余 403（含明确文案）；
    2) 同场景: 发送者有位置时，目标必须在同一房间（positions_from_state）；
       目标未落位视为待定放行；已落位且不同房间 -> 422。
    """
    camp = _resolve_campaign(campaign)
    sender = str(body.player_id or "").strip()
    text = str(body.text or "").strip()
    if not sender:
        raise HTTPException(status_code=422, detail="player_id required")
    if not text:
        raise HTTPException(status_code=422, detail="text required")
    targets = [str(t).strip() for t in body.to_players
               if str(t).strip() and str(t).strip() != sender]
    if not targets:
        raise HTTPException(status_code=422,
                            detail="to_players required and must exclude sender")
    if len(text) > 2000:
        raise HTTPException(status_code=422, detail="text too long (max 2000)")
    state = await _project_async(camp)
    mode = state.chat_mode or "chat_enabled"
    is_public = PUBLIC_TARGET in targets
    if is_public:
        # 公共频道：四态中 public_only/chat_disabled/chat_enabled 放行；all_disabled 拒绝。
        if not _MODE_PUBLIC_ALLOWED.get(mode, True):
            raise HTTPException(
                status_code=403,
                detail="公共频道已关闭（主持人当前设为『%s』）" % MODE_PLAYER_STATE.get(mode, mode))
        # 展开为全体玩家（已建卡 + 已落位 token，去重、排除发送者）
        ids: list[str] = []
        for cid in list(state.characters.keys()):
            if cid not in ids:
                ids.append(cid)
        for tok in list(positions_from_state(state).keys()):
            if tok not in ids:
                ids.append(tok)
        targets = [t for t in ids if t != sender]
        if not targets:
            raise HTTPException(status_code=422, detail="无其他玩家可发送公共消息")
    else:
        if not _MODE_PRIVATE_ALLOWED.get(mode, True):
            raise HTTPException(
                status_code=403,
                detail="私聊已关闭（主持人当前设为『%s』）" % MODE_PLAYER_STATE.get(mode, mode))
        pos = positions_from_state(state)
        sender_room = pos.get(sender, "")
        if sender_room:
            for t in targets:
                t_room = pos.get(t, "")
                if t_room and t_room != sender_room:
                    raise HTTPException(
                        status_code=422,
                        detail="私聊仅限同场景玩家：%s 与 %s 不在同一场景" % (sender, t))
    store = rest_mod._store()
    await store.init()
    payload: dict[str, Any] = {"campaign_id": camp, "from_player": sender,
                               "to_players": targets, "text": text,
                               "room_ref": body.room_ref or (positions_from_state(state).get(sender, "") or None)}
    ev = make_event(
        seq=0, campaign_id=camp, type="PRIVATE_MSG", payload=payload,
        actor=sender, ts=_now(),
    )
    seqs = await store.append(camp, [ev])
    return {"seq": seqs[0], "type": "PRIVATE_MSG",
            "to_players": targets, "public": is_public}