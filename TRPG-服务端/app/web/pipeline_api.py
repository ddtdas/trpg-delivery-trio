"""T7 (additive): 统一审批总线闭环路由 (R10/R11/R17/R18/R19)。

设计要点（D4 增量分层，零冻结文件改动）:
  * **复用既有审批总线** `POST /api/campaigns/{c}/approvals`（本模块只新增
    GET 待审队列与候选生成端点，**不新建第二套审批机制**）;
  * **候选正文不进事件流/公开帧**: NARRATION_PROPOSED 只带脱敏标签，
    真实正文存 app.app_core.pipeline_store，只有 KP token 能通过
    `GET /api/campaigns/{c}/approvals` 读到 —— 因此「GM 发送前玩家收不到任何结果」
    不依赖其它任务的裁剪也成立;
  * **下发一律定向**: 结果/字幕/感知通知走既有
    `INFO_REVEALED(scope=whisper, targets=[X])` -> ws_bridge 映射为冻结 WHISPER 帧
    -> Hub.viewer_may_see 按 targets 服务端权威过滤，其他人拿不到;
  * 事件类型与协议帧**一个都不新增**（EVENT_INJECTED / INFO_REVEALED / CHECK_RESOLVED /
    NARRATION_* 全部既有）。

鉴权复用既有端隔离（不新造鉴权体系）:
  玩家端点 = mobile token；主持人端点 = webapp token。
Python 3.12 compatible.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.app_core import action_pipeline, interactions, perception, pipeline_store
from app.app_core.command_bus import CommandBus, CommandError
from app.config import APP_ROOT
from app.store.projector import project
from app.web import access as access_mod
from app.web import rest as rest_mod
from app.web.access import _require_kp_end, _require_player_end

router = APIRouter()

MODULES_DIR = APP_ROOT / "modules"
DEFAULT_MODULE = "sample_coc"
REJECT_TEXT = "主持人暂未允许该动作。"
SUBTITLE_REJECT_TEXT = "主持人暂未放行这段字幕。"
NOTICE_REJECT_TEXT = "主持人暂未下发这条感知提示。"

# checks.grade 的字面量 -> 冻结 CheckLevel 字面量（events.CheckLevel）
_LEVEL_MAP = {"critical": "crit", "success": "success", "hard": "hard",
              "extreme": "extreme", "fail": "fail", "fumble": "fumble"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InteractBody(StrictModel):
    player_id: str
    object_id: str
    action: str
    room: str = ""
    turn_no: int | None = None
    seed: int | None = None
    req_id: str | None = None
    module_id: str | None = None


class ResolveBody(StrictModel):
    turn_no: int | None = None
    close_window: bool = True
    seed_base: int | None = None
    skill: int = 50
    difficulty: str = "regular"


class EnterBody(StrictModel):
    player_id: str
    room: str
    module_id: str | None = None


class CheckBody(StrictModel):
    player_id: str
    room: str
    skill: int = 50
    difficulty: str = "regular"
    seed: int | None = None
    newcomer_id: str = ""
    auto_send: bool = True
    turn_no: int | None = None
    req_id: str | None = None
    module_id: str | None = None


# ---- 内部工具 -------------------------------------------------------------

def _opaque(prefix: str, campaign: str, *parts: Any) -> str:
    """T7 候选 id：**不含**玩家/房间/物件身份的不透明 id。

    为什么必须不透明：候选通过既有 propose_narration 落 NARRATION_PROPOSED，
    而 NARRATION_APPROVED/EDITED 在冻结的 ws_bridge 里被映射成 **public 帧**
    （契约 §8.1，人人可见）。若 id 里嵌身份（"s:c:r_reading:pl_b:19"），
    公开帧就等于向全桌广播「谁在哪个房间做了什么」—— 实测 R18 泄露点
    （pl_a 的 WS 帧里出现 pl_b）。身份仍完整保留在 pipeline_store 与
    KP 通道（/approvals、/pipeline/queue）里，玩家侧拿不到。
    同一组输入 -> 同一 id，幂等语义不变。
    """
    raw = "|".join([campaign] + [str(p) for p in parts])
    return "%s:%s:%s" % (prefix, campaign,
                         hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _events(campaign: str) -> list[Any]:
    store = rest_mod._store()
    await store.init()
    return await store.replay(campaign)


async def _state(campaign: str) -> Any:
    return project(await _events(campaign), campaign)


def _module_dir(campaign: str, module_id: str | None = None) -> Path:
    """campaign -> 模组目录（显式参数 > 桌配置 > 默认模组）。"""
    mid = str(module_id or "").strip()
    if not mid:
        tid = access_mod._table_entry_by_campaign(campaign)
        cfg = (rest_mod.TABLES.get(tid) or {}).get("config") or {}
        mid = str(cfg.get("module") or cfg.get("module_id") or "").strip()
    if mid and (MODULES_DIR / mid).is_dir():
        return MODULES_DIR / mid
    return MODULES_DIR / DEFAULT_MODULE


def _map_id(module_dir: Path) -> str:
    rooms = interactions.load_rooms(module_dir)
    compiled = module_dir / "compiled" / "rooms.json"
    if compiled.is_file():
        import json as _json
        try:
            data = _json.loads(compiled.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("map_id"):
                return str(data["map_id"])
        except (OSError, ValueError):
            pass
    maps_dir = module_dir / "maps"
    if maps_dir.is_dir():
        import json as _json
        for f in sorted(maps_dir.glob("*.json")):
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("id"):
                return str(data["id"])
    return "map_main" if rooms else "map_default"


def _cmd_inject_event(ctx: dict) -> list[dict]:
    """CommandBus 实例级 handler: EVENT_INJECTED（既有事件类型，非新类型）。"""
    p = ctx["params"]
    node_id = str(p.get("node_id") or "").strip()
    if not node_id:
        raise CommandError("node_id required")
    payload = p.get("payload")
    dry = p.get("dry_run_result")
    return [{"type": "EVENT_INJECTED",
             "payload": {"campaign_id": p.get("campaign_id", ""),
                         "node_id": node_id,
                         "payload": dict(payload) if isinstance(payload, dict) else {},
                         "dry_run_result": dict(dry) if isinstance(dry, dict) else {}}}]


async def _bus(campaign: str) -> CommandBus:
    """唯一写路径: command_bus（附带 T7 的 inject_event handler，不改 COMMANDS 表）。"""
    store = rest_mod._store()
    await store.init()
    bus = CommandBus(store, campaign, guard=access_mod._guard_for(campaign))
    bus.register("inject_event", _cmd_inject_event)
    return bus


async def _propose(campaign: str, proposal_id: str, label: str, actor: str,
                   reasoning: str, req_id: str | None = None) -> dict:
    return await (await _bus(campaign)).dispatch(
        "propose_narration",
        {"campaign_id": campaign, "proposal_id": proposal_id, "text": label,
         "intention": None, "reasoning": reasoning, "source": "agent"},
        actor=actor, key=req_id)


async def _deliver_whisper(campaign: str, info_id: str, targets: list[str],
                           text: str, actor: str = "kp") -> dict:
    """定向下发: INFO_REVEALED(whisper) -> 冻结 WHISPER 帧 -> 只到 targets。"""
    return await (await _bus(campaign)).dispatch(
        "distribute_info",
        {"campaign_id": campaign, "info_id": info_id, "scope": "whisper",
         "targets": list(targets), "body_ref": text},
        actor=actor)


def _action_text(action: Any) -> str:
    if isinstance(action, dict):
        text = action.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    if isinstance(action, str):
        return action.strip()
    return ""


# ---- R10/R11: 地点交互 ----------------------------------------------------

@router.get("/api/campaigns/{campaign}/interactives")
async def list_interactives(campaign: str, room: str = Query(default=""),
                            viewer: str = Query(default=""),
                            module_id: str | None = Query(default=None),
                            entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    """R10: 房间内可交互物 + 动作集（服务端按 viewer 当前房间裁剪）。"""
    mdir = _module_dir(campaign, module_id)
    data = interactions.load_interactives(mdir)
    objects = list(data["objects"])
    rooms = list(data["rooms"])
    if viewer:
        state = await _state(campaign)
        my_room = perception.positions_from_state(state).get(viewer, "")
        if my_room:
            objects = [o for o in objects if o["room"] == my_room]
            rooms = [r for r in rooms if r["id"] == my_room]
    if room:
        objects = [o for o in objects if o["room"] == room]
        rooms = [r for r in rooms if r["id"] == room]
    out = [{"id": o["id"], "name": o["name"], "kind": o["kind"], "room": o["room"],
            "anchor": o["anchor"],
            "actions": [{"action": a, "label": interactions.ACTION_LABELS[a],
                         "sensitive": interactions.is_sensitive(o, a)}
                        for a in o["actions"]]}
           for o in objects]
    return {"campaign": campaign, "module": data["module"], "source": data["source"],
            "rooms": rooms, "objects": out, "count": len(out)}


@router.post("/api/campaigns/{campaign}/interact", status_code=201)
async def interact(campaign: str, body: InteractBody,
                   entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    """R10/R11: 执行一次地点交互。

    敏感动作（撬锁/取走）-> 生成待审候选（NARRATION_PROPOSED，脱敏标签），
    玩家进入「已上报待主持人」状态，批准后才下发；
    非敏感动作（查看/搜索）-> 结果立即进事件流（EVENT_INJECTED）并定向回显。
    """
    actor = str(body.player_id or "").strip()
    if not actor:
        raise HTTPException(status_code=422, detail="player_id required")
    mdir = _module_dir(campaign, body.module_id)
    try:
        obj = interactions.find_object(mdir, body.object_id, body.room or None)
        result = interactions.resolve_action(campaign, obj, body.action,
                                             seed=body.seed)
    except interactions.InteractionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    label = "【待审·%s】%s → %s" % (result["action_label"], actor, obj["name"])
    if result["sensitive"]:
        pid = _opaque("i", campaign, obj["id"], body.action, actor)
        pipeline_store.register(campaign, pid, {
            "kind": "interaction", "actor": actor, "targets": [actor],
            "room": obj["room"], "object_id": obj["id"], "action": body.action,
            "text": result["text"], "reject_text": REJECT_TEXT,
            "label": label,
            "effect": {"kind": "interaction", "result": result}})
        try:
            await _propose(campaign, pid, label, actor,
                           "T7 敏感交互待审: %s/%s" % (obj["id"], body.action),
                           req_id=body.req_id)
        except (CommandError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True, "status": "pending_approval",
                "state": "已上报待主持人", "proposal_id": pid,
                "object_id": obj["id"], "action": body.action, "label": label}
    try:
        receipt = await (await _bus(campaign)).dispatch(
            "inject_event",
            {"campaign_id": campaign, "node_id": obj["room"] or "interaction",
             "payload": {"kind": "interaction", "object_id": obj["id"],
                         "room": obj["room"], "action": body.action,
                         "actor": actor, "result": result},
             "dry_run_result": {"text": result["text"], "level": result["level"],
                                "success": result["success"]}},
            actor=actor, key=body.req_id)
        await _deliver_whisper(campaign, "info:interact:%s:%s" % (obj["id"], _now_ms()),
                               [actor], result["text"], actor="kp")
    except (CommandError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "status": "ok", "result": result, "delivered": True,
            "seqs": list(receipt.get("seqs") or [])}


# ---- R11/R17: 待审队列（KP）----------------------------------------------

@router.get("/api/campaigns/{campaign}/approvals")
async def list_approvals(campaign: str,
                         entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """R11: 主持人待审队列（additive GET；决定仍走既有 POST 同路径）。

    只有 webapp(KP) token 能读；玩家的候选正文不经任何玩家可读路径暴露。
    """
    state = await _state(campaign)
    specs = {s["proposal_id"]: s for s in pipeline_store.all_items(campaign)}
    out: list[dict[str, Any]] = []
    for item in state.approvals.values():
        if item.status != "pending":
            continue
        spec = specs.get(item.proposal_id) or {}
        out.append({"proposal_id": item.proposal_id, "status": item.status,
                    "source": item.source,
                    "kind": spec.get("kind") or "narration",
                    "actor": spec.get("actor") or "",
                    "targets": list(spec.get("targets") or []),
                    "label": item.text,
                    "text": spec.get("text") or item.text,
                    "room": spec.get("room"), "object_id": spec.get("object_id"),
                    "action": spec.get("action"), "turn_no": spec.get("turn_no")})
    return {"campaign": campaign, "pending": out, "count": len(out)}


@router.get("/api/campaigns/{campaign}/pipeline/queue")
async def pipeline_queue(campaign: str,
                         entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """主持人视角的全部登记条目（含已下发/已驳回，便于复盘）。"""
    items = pipeline_store.all_items(campaign)
    return {"campaign": campaign, "items": items, "count": len(items)}


@router.get("/api/campaigns/{campaign}/pipeline/mine")
async def pipeline_mine(campaign: str, player_id: str = Query(..., min_length=1),
                        entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    """玩家视角: 自己提交的交互/行动状态（「已上报待主持人」/ 已下发 / 已驳回）。

    只回自己相关的条目，且**只回自己已收到的正文**（未下发时不回正文）。
    """
    items = pipeline_store.for_actor(campaign, player_id)
    out = []
    for it in items:
        status = it.get("status")
        row = {"proposal_id": it.get("proposal_id"), "status": status,
               "kind": it.get("kind"), "label": it.get("label"),
               "state": ("已上报待主持人" if status == pipeline_store.PENDING
                         else ("已下发" if status == pipeline_store.DELIVERED else "已驳回"))}
        if status == pipeline_store.DELIVERED:
            row["text"] = it.get("delivered_text")
        elif status == pipeline_store.REJECTED:
            row["text"] = it.get("delivered_text")
        out.append(row)
    return {"campaign": campaign, "player_id": player_id, "items": out,
            "count": len(out)}


# ---- R17: 同时行动流水线 --------------------------------------------------

@router.post("/api/campaigns/{campaign}/pipeline/resolve", status_code=201)
async def resolve_pipeline(campaign: str, body: ResolveBody,
                           entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """R17 ②③: 关闭行动窗 -> 服务端批量计算 -> 候选进 GM 待审队列（不下发）。"""
    state = await _state(campaign)
    turn = state.turn
    if turn is None or not turn.submitted:
        raise HTTPException(status_code=422, detail="no submitted actions to resolve")
    if body.turn_no is not None and int(body.turn_no) != int(turn.turn_no):
        raise HTTPException(status_code=409,
                            detail="turn_no mismatch: %s" % turn.turn_no)
    closed = False
    if body.close_window and str(turn.state) == "COLLECTING":
        await (await _bus(campaign)).dispatch(
            "close_window",
            {"campaign_id": campaign, "turn_no": turn.turn_no,
             "order": sorted(turn.submitted.keys()),
             "submit_map": {k: True for k in turn.submitted}},
            actor="kp")
        closed = True
        state = await _state(campaign)
        turn = state.turn
    candidates = action_pipeline.resolve_window(campaign, turn, skill=body.skill,
                                                difficulty=body.difficulty,
                                                seed_base=body.seed_base)
    existing = {s["proposal_id"] for s in pipeline_store.all_items(campaign)}
    created: list[dict[str, Any]] = []
    for cand in candidates:
        pid = cand["proposal_id"]
        if pid in existing:
            created.append({"proposal_id": pid, "player_id": cand["player_id"],
                            "duplicate": True})
            continue
        label = "【待审·行动结果】%s · 第 %s 回合" % (cand["player_id"], cand["turn_no"])
        pipeline_store.register(campaign, pid, {
            "kind": "action_result", "actor": cand["player_id"],
            "targets": [cand["player_id"]], "text": cand["text"],
            "reject_text": REJECT_TEXT, "turn_no": cand["turn_no"],
            "check": cand["check"], "label": label})
        await _propose(campaign, pid, label, "system", cand["reasoning"])
        created.append({"proposal_id": pid, "player_id": cand["player_id"],
                        "label": label, "duplicate": False})
    return {"campaign": campaign, "turn_no": turn.turn_no if turn else 0,
            "closed_window": closed, "candidates": created, "count": len(created)}


# ---- R18/R19: 感知回显 + 检定通知 -----------------------------------------

@router.post("/api/campaigns/{campaign}/perception/enter", status_code=201)
async def perception_enter(campaign: str, body: EnterBody,
                           entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    """R18: B 进入房间 -> 生成 B 的定向字幕候选（先过 GM 字幕审核）。"""
    actor = str(body.player_id or "").strip()
    if not actor or not str(body.room or "").strip():
        raise HTTPException(status_code=422, detail="player_id/room required")
    mdir = _module_dir(campaign, body.module_id)
    rooms = interactions.load_rooms(mdir)
    rname = perception.room_name(rooms, body.room)
    await (await _bus(campaign)).dispatch(
        "map_update",
        {"campaign_id": campaign, "map_id": _map_id(mdir), "op": "move",
         "target": actor, "delta": {"room": body.room}},
        actor=actor)
    state = await _state(campaign)
    positions = perception.positions_from_state(state)
    submitted = (state.turn.submitted if state.turn else {}) or {}
    others = [{"token": tok,
               "action_text": _action_text((submitted.get(tok) or {}).get("action"))}
              for tok in perception.occupants(positions, body.room, exclude=actor)]
    subtitle = perception.mover_subtitle(actor, rname, others)
    pid = _opaque("s", campaign, body.room, actor, int(state.last_seq))
    label = "【待审·字幕】%s 进入 %s" % (actor, rname)
    pipeline_store.register(campaign, pid, {
        "kind": "subtitle", "actor": actor, "targets": [actor],
        "room": body.room, "text": subtitle, "label": label,
        "reject_text": SUBTITLE_REJECT_TEXT})
    await _propose(campaign, pid, label, actor, "T7 感知回显字幕候选（R18）")
    return {"ok": True, "status": "pending_approval", "proposal_id": pid,
            "room": body.room, "room_name": rname,
            "others": [o["token"] for o in others], "label": label}


@router.post("/api/campaigns/{campaign}/perception/check", status_code=201)
async def perception_check(campaign: str, body: CheckBody,
                           entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    """R19: 感知/侦察检定 -> CHECK_RESOLVED（可追溯）；成功才下发中性通知。"""
    actor = str(body.player_id or "").strip()
    if not actor or not str(body.room or "").strip():
        raise HTTPException(status_code=422, detail="player_id/room required")
    mdir = _module_dir(campaign, body.module_id)
    rooms = interactions.load_rooms(mdir)
    rname = perception.room_name(rooms, body.room)
    seed = body.seed if body.seed is not None else perception.perception_seed(
        campaign, actor, body.room)
    try:
        chk = perception.resolve_perception(skill=body.skill,
                                            difficulty=body.difficulty, seed=seed)
    except (perception.PerceptionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    turn_no = body.turn_no
    if turn_no is None:
        st = await _state(campaign)
        turn_no = int(st.turn.turn_no) if st.turn else 0
    receipt = await (await _bus(campaign)).dispatch(
        "resolve_check",
        {"campaign_id": campaign, "turn_no": turn_no, "card_id": actor,
         "target": "感知/侦察", "difficulty": chk["difficulty_code"],
         "rolled": [chk["rolled"]], "total": chk["rolled"],
         "level": _LEVEL_MAP.get(chk["level"], chk["level"]),
         "seed": str(chk["seed"]),
         "summary": "skill=%s difficulty=%s success=%s" % (
             chk["skill"], chk["difficulty"], chk["success"])},
        actor=actor, key=body.req_id)
    seqs = list(receipt.get("seqs") or [])
    text = perception.occupant_notice(rname)
    delivered = False
    pid: str | None = None
    if chk["success"]:
        if body.auto_send:
            await _deliver_whisper(
                campaign, "info:perception:%s:%s" % (actor, seqs[0] if seqs else 0),
                [actor], text, actor="kp")
            delivered = True
        else:
            pid = _opaque("n", campaign, body.room, actor,
                          seqs[0] if seqs else 0)
            pipeline_store.register(campaign, pid, {
                "kind": "perception", "actor": actor, "targets": [actor],
                "room": body.room, "text": text,
                "label": "【待审·感知提示】%s @ %s" % (actor, rname),
                "reject_text": NOTICE_REJECT_TEXT})
            await _propose(campaign, pid,
                           "【待审·感知提示】%s @ %s" % (actor, rname),
                           actor, "T7 检定驱动的感知通知（R19）")
    return {"ok": True, "success": bool(chk["success"]), "check": chk,
            "text": text if chk["success"] else "", "delivered": delivered,
            "proposal_id": pid, "room": body.room, "room_name": rname,
            "seqs": seqs}


# ---- 既有审批总线的投递钩子（由 app/web/rest.py 调用）----------------------

def adjust_decision(campaign: str, proposal_id: str, decision: str,
                    payload: dict[str, Any]) -> dict[str, Any]:
    """定向候选的决定事件正文**脱敏**。

    NARRATION_APPROVED/EDITED 会被 ws_bridge 映射成 **public** 帧（房间级广播），
    若正文照原样落库，GM 改写的定向字幕/行动结果就会泄露给全桌。
    因此凡是有投递规格的候选，决定事件只带脱敏正文，真实内容走 whisper 定向投递。
    无投递规格的候选（既有 agent 叙事链路）**行为与改造前完全一致**。
    """
    spec = pipeline_store.get(campaign, proposal_id)
    if not spec:
        return payload
    if decision == "reject":
        return {"proposal_id": proposal_id, "reason": "kp rejected"}
    if decision == "edit":
        return {"proposal_id": proposal_id, "text": "", "diff": {}}
    return {"proposal_id": proposal_id, "text": ""}


async def deliver_after_decision(campaign: str, proposal_id: str, decision: str,
                                 edited_text: str = "") -> dict[str, Any] | None:
    """GM 决定后执行**定向投递**（无投递规格 -> None，行为不变）。"""
    spec = pipeline_store.get(campaign, proposal_id)
    if not spec:
        return None
    targets = [str(t) for t in (spec.get("targets") or []) if str(t).strip()]
    if not targets:
        return None
    if decision == "reject":
        text = str(spec.get("reject_text") or REJECT_TEXT)
        status = pipeline_store.REJECTED
    else:
        text = str(edited_text or "").strip() or str(spec.get("text") or "")
        status = pipeline_store.DELIVERED
    bus = await _bus(campaign)
    info_id = "info:%s" % proposal_id
    await bus.dispatch("distribute_info",
                       {"campaign_id": campaign, "info_id": info_id,
                        "scope": "whisper", "targets": targets, "body_ref": text},
                       actor="kp")
    effect_seqs: list[int] = []
    effect = spec.get("effect")
    if status == pipeline_store.DELIVERED and isinstance(effect, dict):
        result = effect.get("result") if isinstance(effect.get("result"), dict) else {}
        receipt = await bus.dispatch(
            "inject_event",
            {"campaign_id": campaign, "node_id": str(spec.get("room") or "interaction"),
             "payload": {"kind": effect.get("kind") or "interaction",
                         "object_id": spec.get("object_id"), "room": spec.get("room"),
                         "action": spec.get("action"), "actor": spec.get("actor"),
                         "result": result, "approved": True},
             "dry_run_result": {"text": text, "level": result.get("level"),
                                "success": result.get("success")}},
            actor="kp")
        effect_seqs = list(receipt.get("seqs") or [])
    pipeline_store.set_status(campaign, proposal_id, status, delivered_text=text,
                              delivered_info_id=info_id, effect_seqs=effect_seqs)
    return {"delivered": True, "status": status, "targets": targets,
            "info_id": info_id, "text": text, "effect_seqs": effect_seqs}
