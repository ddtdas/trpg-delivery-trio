"""R28-R31 的 additive REST 层（GM 控制面 + 玩家可见读口）。

路由总览（全部 additive，不动任何既有路由）
--------------------------------------------------------------
R28 一次性技能
  POST   /api/campaigns/{c}/npc/{npc_id}/skills           生成一次性技能
  GET    /api/campaigns/{c}/npc/skills                    列出（?npc_id= 过滤）
  POST   /api/campaigns/{c}/npc/skills/{skill_id}/invoke  调用 -> 规则层效果
  DELETE /api/campaigns/{c}/npc/skills/{skill_id}         丢弃
R29 NPC 记忆
  GET    /api/campaigns/{c}/npc/{npc_id}/memory           查看
  POST   /api/campaigns/{c}/npc/{npc_id}/observe          写入（见过谁/发生过什么）
  PATCH  /api/campaigns/{c}/npc/{npc_id}/memory/{mem_id}  编辑（即时生效）
  DELETE /api/campaigns/{c}/npc/{npc_id}/memory           清空（?mem_id= 单条）
  POST   /api/campaigns/{c}/npc/{npc_id}/ingest           从事件流自动归纳
R30/R31 NPC 自主性
  GET    /api/campaigns/{c}/npc/proposals                 主持人待审队列
  POST   /api/campaigns/{c}/npc/{npc_id}/generate         触发一次自动生成
  POST   /api/campaigns/{c}/npc/direct                    主持人指定行为（立即生效）
  POST   /api/campaigns/{c}/npc/{npc_id}/interrupt        中断改向（丢弃待审）
  POST   /api/campaigns/{c}/npc/auto                      开关自动生成
  POST   /api/campaigns/{c}/npc/{npc_id}/takeover         主持人完全接管
  GET    /api/campaigns/{c}/npc/state                     总览（开关 + 待审数 + 台词）
  GET    /api/campaigns/{c}/npc/lines                     玩家可见 NPC 台词（无鉴权）

鉴权：GM 控制面复用既有 KP 端鉴权（app.web.access._require_kp_end，
webapp 端 token = 主持端凭据；mobile/recorder token -> 403 kp_only），
不新造鉴权体系。玩家可见读口（/npc/lines）不带鉴权，与既有事件流一致。

决策入口不在这里：批准 / 改写 / 驳回仍走既有统一审批总线
POST /api/campaigns/{c}/approvals（禁止新建第二套）。
Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.npc import director as npc_director
from app.npc import memory as npc_memory
from app.npc import skills as npc_skills

router = APIRouter()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def kp_guard(authorization: str | None = Header(default=None),
             token: str | None = Query(default=None)) -> dict[str, Any]:
    """GM 控制面鉴权：复用既有 KP 端鉴权（不新造体系）。"""
    from app.web import access as access_mod
    return access_mod._require_kp_end(authorization=authorization, token=token)


KP = Depends(kp_guard)


# ---- 请求体 ---------------------------------------------------------------

class SkillForge(StrictModel):
    name: str
    effect: dict[str, Any] = {}
    max_uses: int = 3


class SkillInvoke(StrictModel):
    card: dict[str, Any]
    target: str | None = None
    difficulty: str = "regular"
    rolled: int | None = None
    seed: int | None = None


class Observe(StrictModel):
    text: str
    kind: str = "event"
    ref: str = ""
    source: str = "gm"


class MemoryEdit(StrictModel):
    text: str | None = None
    kind: str | None = None
    ref: str | None = None


class GenerateBody(StrictModel):
    trigger: str = ""
    player_id: str = ""
    situation: str = ""


class DirectBody(StrictModel):
    npc_id: str
    line: str
    intent: str = ""


class AutoBody(StrictModel):
    enabled: bool
    npc_id: str | None = None


class TakeoverBody(StrictModel):
    enabled: bool = True


class InterruptBody(StrictModel):
    reason: str = ""


def _skill_or_404(skill_id: str) -> dict[str, Any]:
    rec = npc_skills.get_skill(skill_id)
    if rec is None:
        raise HTTPException(status_code=404,
                            detail="unknown ephemeral skill: %r" % skill_id)
    return rec


# ---- R28 一次性技能 -------------------------------------------------------

@router.post("/api/campaigns/{campaign}/npc/{npc_id}/skills", status_code=201)
def forge_npc_skill(campaign: str, npc_id: str, body: SkillForge,
                    _kp: dict = KP) -> dict:
    try:
        rec = npc_skills.forge_skill(campaign, npc_id, body.name,
                                     body.effect, max_uses=body.max_uses)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"skill": rec, "campaign_id": campaign,
            "rules_registry_size": npc_skills.registry_size()}


@router.get("/api/campaigns/{campaign}/npc/skills")
def list_npc_skills(campaign: str, npc_id: str | None = None,
                    _kp: dict = KP) -> dict:
    items = npc_skills.list_skills(campaign, npc_id)
    return {"campaign_id": campaign, "npc_id": npc_id,
            "count": len(items), "skills": items,
            "rules_registry_size": npc_skills.registry_size()}


@router.post("/api/campaigns/{campaign}/npc/skills/{skill_id}/invoke")
def invoke_npc_skill(campaign: str, skill_id: str, body: SkillInvoke,
                     _kp: dict = KP) -> dict:
    rec = _skill_or_404(skill_id)
    if rec["campaign_id"] != campaign:
        raise HTTPException(status_code=404,
                            detail="ephemeral skill belongs to another campaign")
    try:
        out = npc_skills.invoke_skill(skill_id, body.card, target=body.target,
                                      difficulty=body.difficulty,
                                      rolled=body.rolled, seed=body.seed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"campaign_id": campaign, "effect_result": out}


@router.delete("/api/campaigns/{campaign}/npc/skills/{skill_id}")
def drop_npc_skill(campaign: str, skill_id: str, _kp: dict = KP) -> dict:
    rec = _skill_or_404(skill_id)
    if rec["campaign_id"] != campaign:
        raise HTTPException(status_code=404,
                            detail="ephemeral skill belongs to another campaign")
    return {"dropped": npc_skills.drop_skill(skill_id), "skill_id": skill_id}


# ---- R29 NPC 记忆 ---------------------------------------------------------

@router.get("/api/campaigns/{campaign}/npc/{npc_id}/memory")
async def get_npc_memory(campaign: str, npc_id: str, limit: int = 200,
                         _kp: dict = KP) -> dict:
    mems = await npc_memory.recall(campaign, npc_id, limit=limit)
    digest = await npc_memory.digest(campaign, npc_id, limit=limit)
    return {"campaign_id": campaign, "npc_id": npc_id, "count": len(mems),
            "memories": mems, "digest": digest}


@router.post("/api/campaigns/{campaign}/npc/{npc_id}/observe", status_code=201)
async def observe_npc(campaign: str, npc_id: str, body: Observe,
                      _kp: dict = KP) -> dict:
    try:
        mem = await npc_memory.remember(campaign, npc_id, body.kind,
                                        body.text, ref=body.ref,
                                        source=body.source)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"memory": mem,
            "digest": await npc_memory.digest(campaign, npc_id)}


@router.patch("/api/campaigns/{campaign}/npc/{npc_id}/memory/{mem_id}")
async def edit_npc_memory(campaign: str, npc_id: str, mem_id: str,
                          body: MemoryEdit, _kp: dict = KP) -> dict:
    try:
        ok = await npc_memory.update_memory(mem_id, text=body.text,
                                            kind=body.kind, ref=body.ref)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="unknown mem_id: %r" % mem_id)
    return {"updated": True, "mem_id": mem_id,
            "memories": await npc_memory.recall(campaign, npc_id),
            "digest": await npc_memory.digest(campaign, npc_id)}


@router.delete("/api/campaigns/{campaign}/npc/{npc_id}/memory")
async def clear_npc_memory(campaign: str, npc_id: str,
                           mem_id: str | None = None, _kp: dict = KP) -> dict:
    removed = await npc_memory.forget(campaign, npc_id, mem_id=mem_id)
    return {"removed": removed, "npc_id": npc_id, "mem_id": mem_id,
            "digest": await npc_memory.digest(campaign, npc_id)}


@router.post("/api/campaigns/{campaign}/npc/{npc_id}/ingest")
async def ingest_npc_memory(campaign: str, npc_id: str, _kp: dict = KP) -> dict:
    from app.web import rest as rest_mod
    store = rest_mod._store()
    await store.init()
    events = await store.replay(campaign)
    written = await npc_memory.ingest_events(campaign, npc_id, events)
    return {"campaign_id": campaign, "npc_id": npc_id,
            "events_scanned": len(events), "memories_written": written,
            "digest": await npc_memory.digest(campaign, npc_id)}


# ---- R30/R31 待审队列 / 生成 / 主持人决定 ---------------------------------

@router.get("/api/campaigns/{campaign}/npc/proposals")
async def list_npc_proposals(campaign: str, status: str = "pending",
                             npc_id: str | None = None,
                             _kp: dict = KP) -> dict:
    try:
        items = await npc_director.pending(campaign, status=status, npc_id=npc_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"campaign_id": campaign, "status": status,
            "count": len(items), "proposals": items}


@router.post("/api/campaigns/{campaign}/npc/{npc_id}/generate", status_code=201)
async def generate_npc(campaign: str, npc_id: str, body: GenerateBody | None = None,
                       _kp: dict = KP) -> dict:
    b = body or GenerateBody()
    settings = await npc_director.get_settings(campaign, npc_id)
    if settings["takeover"]:
        raise HTTPException(status_code=409,
                            detail="npc_takeover: NPC 已由主持人完全接管")
    return {"proposal": await npc_director.generate(
        campaign, npc_id, trigger=b.trigger, player_id=b.player_id,
        situation=b.situation)}


@router.post("/api/campaigns/{campaign}/npc/direct", status_code=201)
async def direct_npc(campaign: str, body: DirectBody, _kp: dict = KP) -> dict:
    return {"delivered": await npc_director.direct(campaign, body.npc_id,
                                                   body.line, body.intent)}


@router.post("/api/campaigns/{campaign}/npc/{npc_id}/interrupt")
async def interrupt_npc(campaign: str, npc_id: str,
                        body: InterruptBody | None = None,
                        _kp: dict = KP) -> dict:
    b = body or InterruptBody()
    return await npc_director.interrupt(campaign, npc_id, reason=b.reason)


@router.post("/api/campaigns/{campaign}/npc/auto")
async def set_npc_auto(campaign: str, body: AutoBody, _kp: dict = KP) -> dict:
    return await npc_director.set_auto(campaign, body.enabled, body.npc_id)


@router.post("/api/campaigns/{campaign}/npc/{npc_id}/takeover")
async def set_npc_takeover(campaign: str, npc_id: str,
                           body: TakeoverBody | None = None,
                           _kp: dict = KP) -> dict:
    b = body or TakeoverBody()
    return await npc_director.set_takeover(campaign, npc_id, b.enabled)


@router.get("/api/campaigns/{campaign}/npc/state")
async def npc_state(campaign: str, npc_id: str | None = None,
                    _kp: dict = KP) -> dict:
    settings = await npc_director.get_settings(campaign, npc_id)
    pending_items = await npc_director.pending(campaign, status="pending")
    lines = await npc_director.player_lines(campaign)
    # R5/t8 追加（additive）：把 NPC 卡的可读名/身份/关联场景节点附给 GM 界面。
    ids: list[str] = [str(k) for k in (lines["npc_lines"] or {})]
    ids += [str(it.get("npc_id") or "") for it in pending_items]
    ids += [str(k) for k in ((settings.get("table") or {})) if k != "*"]
    return {"campaign_id": campaign, "settings": settings,
            "pending_count": len(pending_items),
            "pending": pending_items,
            "player_visible_lines": lines["npc_lines"], "tip": lines["tip"],
            "npc_meta": npc_director.npc_meta(ids),
            "skills": npc_skills.list_skills(campaign)}


# ---- 玩家可见读口（无鉴权：与既有事件流一致，只含已批准内容） ---------------

@router.get("/api/campaigns/{campaign}/npc/lines")
async def npc_lines_public(campaign: str) -> dict:
    return await npc_director.player_lines(campaign)
