"""R4/R5/R15/R16/R20 —— GM 单窗口总览与控制面（**全部 additive**，独立 APIRouter）。

挂载方式与 `app/web/pipeline_api.py`、`app/web/rules_api.py`、`app/npc/routes.py` 同源：
只在 `app/main.py` 加 import + include_router 两行，不改任何既有模块。

冻结件遵守：
  * 不新增 WS 帧（R16 交汇提示复用既有 `BRANCH_TAKEN`）。
  * 不新增事件类型（`app/domain/events.py` EVENT_TYPES 未改）。
  * R15 落图**复用既有 `MAP_UPDATED` + 既有 `map_command`**，不新增 map op。
  * R4 复用既有 `access._advice_core`（同一 gateway/降级链），**不另造第二套建议机制**；
    差别仅在于 scene/events 由**服务端装配权威状态**，而非调用方传入。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.agent import roles as roles_mod
from app.app_core import interactions
from app.store.event_store import EventStore
from app.store.projector import project
from app.web.access import ADVICE_TYPES, _advice_core, _require_kp_end
from app.web.rest import DEFAULT_DB, MapCommand, map_command

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _state(campaign: str):
    store = EventStore(DEFAULT_DB)
    await store.init()
    events = await store.replay(campaign)
    return project(events, campaign), events


# ---------------------------------------------------------------- 地图折叠 (R5 ①/R15)

def _fold_map(maps: dict[str, Any]) -> dict[str, Any]:
    """把 `state.maps[map_id].ops` 折叠成 {token: room}。

    投影器只记录 ops 日志（`{op,target,delta}`），不折叠空间关系；此处按 ops 顺序重放。
    delta 的房间字段名做**防御性**兼容（room / room_id / to），并原样回报所用字段名，
    以便调用方核验"确实读了真实状态"而非编造。
    """
    out: dict[str, Any] = {}
    for map_id, m in (maps or {}).items():
        tokens: dict[str, str] = {}
        room_keys: set[str] = set()
        fog: list[str] = []
        for op in (m or {}).get("ops", []):
            o, target, delta = op.get("op"), str(op.get("target", "")), op.get("delta") or {}
            room = None
            for k in ("room", "room_id", "to", "to_room"):
                if isinstance(delta.get(k), str) and delta.get(k):
                    room = delta[k]
                    room_keys.add(k)
                    break
            if o in ("move", "add_token") and target and room:
                tokens[target] = room
            elif o == "set_fog" and target:
                if target not in fog:
                    fog.append(target)
        out[map_id] = {"map_id": map_id, "token_rooms": tokens, "fog": fog,
                       "op_count": len((m or {}).get("ops", [])),
                       "room_field_keys": sorted(room_keys)}
    return out


# ---------------------------------------------------------------- R5 六类信息块

@router.get("/api/campaigns/{campaign}/overview")
async def overview(campaign: str, _: Any = Depends(_require_kp_end)) -> dict[str, Any]:
    """R5：单窗口总览所需的 6 类信息块，一次取齐（GM 端首屏不再拼多个请求）。"""
    st, events = await _state(campaign)
    folded = _fold_map(st.maps)
    first_map = next(iter(folded.values()), {"map_id": "", "token_rooms": {}, "fog": []})
    token_rooms = first_map.get("token_rooms", {})

    # ② 玩家位置/状态
    # 实测：库中**没有任何 campaign 有 CHARACTER_CREATED 事件**，玩家只以地图棋子形式存在。
    # 因此玩家集合取「角色卡 ∪ 地图棋子」的并集 —— 否则 ② 块在真实数据上恒为空。
    chars_all = dict(st.characters or {})
    for tok in token_rooms:
        if tok.startswith("pl_") and tok not in chars_all:
            chars_all[tok] = {}
    players: list[dict[str, Any]] = []
    for pid, ch in chars_all.items():
        ch = ch or {}
        players.append({
            "player_id": pid,
            "name": ch.get("name") or ch.get("char_name") or pid,
            "occupation": ch.get("occupation") or ch.get("job") or "",
            "hp": ch.get("hp"), "mp": ch.get("mp"), "san": ch.get("san"),
            "status": ch.get("status") or ("已定卡" if pid in (st.finalized_cards or []) else "未定卡"),
            "room_id": token_rooms.get(pid, ""),
            "source": "character_card" if (st.characters or {}).get(pid) else "map_token",
        })

    # ③ 当前回合与已提交行动
    turn = None
    if st.turn is not None:
        t = st.turn
        turn = {"turn_no": t.turn_no, "state": t.state,
                "countdown_end_ts": t.countdown_end_ts,
                "submitted": [{"player_id": k, "intent": (v or {}).get("intent", "")}
                              for k, v in (t.submitted or {}).items()],
                "submitted_count": len(t.submitted or {}), "order": list(t.order or [])}

    # ④ 待审队列
    pending = [{"proposal_id": a.proposal_id, "text": a.text, "intention": a.intention,
                "source": a.source, "status": a.status}
               for a in (st.approvals or {}).values() if a.status == "pending"]

    # ⑤ 事件/线索
    recent_events = [{"seq": e.seq, "type": e.type, "ts": e.ts} for e in events[-20:]]
    clues = [{"clue_id": k, **(v or {})} for k, v in (st.clues or {}).items()]
    infos = [{"info_id": k, **(v or {})} for k, v in (st.infos or {}).items()]

    # ⑥ NPC 状态
    npcs = [{"npc_id": k, "line": v} for k, v in (st.npc_lines or {}).items()]

    return {
        "campaign_id": campaign, "generated_ts": _now(),
        "blocks": {
            "map": {"map_id": first_map.get("map_id", ""),
                    "rooms": sorted(set(token_rooms.values())),
                    "tokens": token_rooms, "fog": first_map.get("fog", []),
                    "maps_count": len(folded)},
            "players": players,
            "turn": turn,
            "approvals": {"pending_count": len(pending), "pending": pending},
            "events": {"recent": recent_events, "clues": clues, "infos": infos,
                       "tip": (events[-1].seq if events else -1)},
            "npcs": {"count": len(npcs), "npcs": npcs},
        },
        "counts": {"players": len(players), "pending": len(pending),
                   "clues": len(clues), "npcs": len(npcs), "events": len(events)},
    }


# ---------------------------------------------------------------- R16 并行线程

@router.get("/api/campaigns/{campaign}/threads")
async def threads(campaign: str, _: Any = Depends(_require_kp_end)) -> dict[str, Any]:
    """R16：并行叙事线程并列视图 + 交汇提示。

    数据源是既有投影 `state.branches`（由冻结的 BRANCH_TAKEN/BRANCH_OVERRIDDEN 折叠而来）。
    交汇判定：两条线程的 `node_id` 相同（同一节点被多次进入），或其中之一是另一条的
    前驱/后继链上的节点（用已有 branch 记录的出现顺序做保守判定）。
    **不新增 WS 帧** —— 交汇提示作为本接口的读侧结论返回。
    """
    st, _ = await _state(campaign)
    branches = [b or {} for b in (st.branches or [])]
    by_node: dict[str, list[int]] = {}
    for i, b in enumerate(branches):
        nid = str(b.get("node_id") or b.get("label") or f"b{i}")
        by_node.setdefault(nid, []).append(i)

    lines: list[dict[str, Any]] = []
    for nid, idxs in by_node.items():
        b0 = branches[idxs[0]]
        lines.append({"node_id": nid, "label": b0.get("label", nid),
                      "visits": len(idxs), "seqs": [branches[i].get("seq") for i in idxs],
                      "consequences": b0.get("consequences", [])})

    convergence: list[dict[str, Any]] = []
    for nid, idxs in by_node.items():
        if len(idxs) > 1:
            convergence.append({"node_id": nid, "kind": "same_node",
                                "visits": len(idxs),
                                "message": f"线程在节点「{nid}」交汇（{len(idxs)} 次进入）"})
    # 保守的前驱/后继交汇：后一节点被较早线程走到过
    for i in range(1, len(branches)):
        cur = str(branches[i].get("node_id") or "")
        prev = str(branches[i - 1].get("node_id") or "")
        if cur and cur in by_node and len(by_node[cur]) > 1 and cur != prev:
            if not any(c["node_id"] == cur for c in convergence):
                convergence.append({"node_id": cur, "kind": "shared_successor",
                                    "message": f"线程汇入后继节点「{cur}」"})

    return {"campaign_id": campaign, "generated_ts": _now(),
            "parallel_count": len(lines), "lines": lines,
            "convergence": convergence,
            "has_convergence": bool(convergence),
            "convergence_hint": (convergence[0]["message"] if convergence
                                 else "暂无交汇：各线程仍在独立推进")}


# ---------------------------------------------------------------- R15 一键分配

def _module_map_rooms(campaign: str) -> tuple[str, list[str], str]:
    """战役所属模组的地图定义 -> (map_id, room_ids, module_id)。

    与 app/web/pipeline_api.py 同源（桌配置 module/module_id > 默认模组）：战役在数据
    模型里**不绑定模组**（库里没有 campaign->module 表），故这里复用同一个解析函数，
    不自造第二套口径。模组侧不可读时返回空值，退回纯状态折叠。
    """
    try:
        from app.web.pipeline_api import _map_id as _pipeline_map_id
        from app.web.pipeline_api import _module_dir as _pipeline_module_dir

        mdir = _pipeline_module_dir(campaign)
        rooms = [str(r.get("id")) for r in interactions.load_rooms(mdir) if r.get("id")]
        return str(_pipeline_map_id(mdir) or ""), rooms, mdir.name
    except Exception:  # noqa: BLE001 -- 模组侧不可读时退回纯状态折叠，不影响既有语义
        return "", [], ""


def _resolve_map(campaign: str, folded: dict[str, Any],
                 explicit_id: str = "") -> dict[str, Any]:
    """suggest 与 apply **共用**的地图解析（R35-7：空态判定必须一致）。

    优先级：调用方显式 map_id > 投影折叠出的地图 > 模组地图定义。
    房间集合 = 折叠出的 token 房间 ∪ 模组地图声明的房间 —— 后者是"一键落位在开局前
    也能真的落位"的关键：地图 ops 还没产生时，房间只能来自模组定义。
    无地图 -> 抛 422 "no map for campaign"（两个端点同一形状、同一 detail）。
    """
    state_first = next(iter(folded.values()), {}) or {}
    state_map_id = str(state_first.get("map_id", "") or "")
    mod_map_id, mod_rooms, mod_id = _module_map_rooms(campaign)
    map_id = str(explicit_id or "").strip() or state_map_id or mod_map_id
    if not map_id:
        raise HTTPException(status_code=422, detail="no map for campaign")
    token_rooms = state_first.get("token_rooms", {}) or {}
    rooms = sorted({str(r) for r in token_rooms.values() if r} | set(mod_rooms))
    if state_map_id and mod_rooms:
        source = "state_ops+module"
    elif state_map_id:
        source = "state_ops"
    else:
        source = "module"
    return {"map_id": map_id, "rooms": rooms, "source": source,
            "module_id": mod_id, "module_map_id": mod_map_id}


def _suggest(st: Any, folded: dict[str, Any], rooms: list[str]) -> list[dict[str, Any]]:
    """确定性分配建议（无随机、可复现）。

    依据**真实状态**：①已折叠的 token→room；②角色卡（谁还没落位）；③NPC 所在房间；
    ④**模组地图声明的房间**（R35-7：地图 ops 尚未产生时的落位目标来源）。
    每条建议都带 reason 与 evidence（引用了哪些真实字段/值），便于核验非模板化。
    """
    first = next(iter(folded.values()), {"map_id": "", "token_rooms": {}})
    map_id, token_rooms = first.get("map_id", ""), dict(first.get("token_rooms", {}))
    rooms = sorted(set(rooms) | {str(v) for v in token_rooms.values() if v})
    chars = list((st.characters or {}).keys())
    for tok in token_rooms:  # 玩家也可能只以棋子形式存在（见 overview ② 的说明）
        if tok.startswith("pl_") and tok not in chars:
            chars.append(tok)
    npc_rooms = {k: token_rooms.get(k) for k in (st.npc_lines or {}) if token_rooms.get(k)}
    occupancy: dict[str, int] = {}
    for r in token_rooms.values():
        occupancy[r] = occupancy.get(r, 0) + 1

    out: list[dict[str, Any]] = []
    for pid in chars:
        cur = token_rooms.get(pid)
        if cur is None:
            # 未落位：放进人最多的房间（保持队伍聚集），否则第一个房间
            target = max(occupancy, key=lambda r: occupancy[r]) if occupancy else (rooms[0] if rooms else "")
            out.append({"player_id": pid, "from_room": None, "to_room": target,
                        "kind": "place",
                        "reason": f"角色 {pid} 尚未在地图上落位；建议放入当前人数最多的房间以保持队伍聚集",
                        "evidence": {"occupancy": dict(occupancy), "rooms": rooms,
                                     "source": "state.maps[*].ops 折叠 + 模组地图房间表"
                                               " + state.characters"}})
        elif npc_rooms and cur not in npc_rooms.values():
            # 有人物在别的房间而 NPC 房无人：建议前往最近的 NPC 房
            target = next((r for r in npc_rooms.values() if occupancy.get(r, 0) == 0), None)
            if target:
                out.append({"player_id": pid, "from_room": cur, "to_room": target,
                            "kind": "escort",
                            "reason": f"NPC 所在房间「{target}」当前无玩家在场；建议 {pid} 前往以推进互动",
                            "evidence": {"npc_rooms": npc_rooms, "occupancy": dict(occupancy),
                                         "source": "state.npc_lines ∩ 折叠后的 token→room"}})
    if not out:
        out.append({"player_id": "", "from_room": None, "to_room": "",
                    "kind": "noop",
                    "reason": "当前状态下无需调整：所有角色均已落位且 NPC 房间已有玩家",
                    "evidence": {"occupancy": dict(occupancy), "npc_rooms": npc_rooms}})
    return out


@router.get("/api/campaigns/{campaign}/allocation/suggest")
async def allocation_suggest(campaign: str, _: Any = Depends(_require_kp_end)) -> dict[str, Any]:
    """R15：一键分配建议（读侧）。落图走 /allocation/apply。

    R35-7 空态契约：**无地图时本端点与 apply 同样返回 422 "no map for campaign"**。
    此前本端点返回 200 + map_id=""，而 apply 返回 422 —— 调用方无法区分
    "这张战役没有地图" 与 "有地图但没有需要调整的项"，两个端点的判定必须一致。
    """
    st, _ = await _state(campaign)
    folded = _fold_map(st.maps)
    r = _resolve_map(campaign, folded)
    sug = _suggest(st, folded, r["rooms"])
    return {"campaign_id": campaign, "map_id": r["map_id"],
            "map_source": r["source"], "module_id": r["module_id"],
            "rooms": r["rooms"],
            "suggestions": sug, "count": len(sug), "generated_ts": _now()}


@router.post("/api/campaigns/{campaign}/allocation/apply", status_code=201)
async def allocation_apply(campaign: str, body: dict[str, Any] = Body(default={}),
                           _: Any = Depends(_require_kp_end)) -> dict[str, Any]:
    """R15：一键应用 —— **复用既有 map_command / 既有 MAP_OPS**，不新增 op、不新增事件。

    R35-7 修复（现象：201 但 applied_count=0、地图未产生）:
      * 地图解析与 suggest **共用** _resolve_map：无地图时同样 422 "no map for campaign"，
        且"没有地图 ops"时会退回模组地图定义 -> 开局前也能落位（这才是"一次性落位"）;
      * 请求体同时接受 suggestions 与 **assignments**（后者此前被静默忽略，
        于是"传了分配表却 201 + applied_count=0"）；空列表 = 用服务端建议（保持既有语义）;
      * 未落位棋子用既有 add_token、已在图上的用既有 move（都是既有 MAP_OPS）;
      * **不再静默空转**：给出目标房间的条目照常落位；给不出的进 skipped 并带原因；
        若确有可落位条目却一条也没落成 -> 422，而不是 201 假成功。
    """
    st, _ = await _state(campaign)
    folded = _fold_map(st.maps)
    r = _resolve_map(campaign, folded, str(body.get("map_id") or ""))
    map_id, rooms = r["map_id"], r["rooms"]
    placed = {str(k) for k in ((next(iter(folded.values()), {}) or {})
                               .get("token_rooms", {}) or {})}

    items = body.get("suggestions")
    if not isinstance(items, list) or not items:
        items = body.get("assignments")
    if not isinstance(items, list) or not items:
        items = [s for s in _suggest(st, folded, rooms) if s.get("kind") != "noop"]

    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for s in items:
        if not isinstance(s, dict):
            skipped.append({"item": repr(s)[:80], "reason": "not_an_object"})
            continue
        pid = str(s.get("player_id") or "")
        room = str(s.get("to_room") or s.get("room") or "")
        if not pid:
            skipped.append({"player_id": "", "to_room": room, "kind": s.get("kind"),
                            "reason": "empty_player_id"})
            continue
        if not room:
            room = rooms[0] if rooms else ""
        if not room:
            skipped.append({"player_id": pid, "to_room": "", "kind": s.get("kind"),
                            "reason": "no_room_available"})
            continue
        op = "move" if pid in placed else "add_token"
        res = await map_command(campaign, MapCommand(
            map_id=map_id, op=op, target=pid, delta={"room": room}, actor="kp"))
        placed.add(pid)
        applied.append({"player_id": pid, "to_room": room, "op": op,
                        "seq": res.get("seq")})

    if skipped and not applied:
        # 有请求、但一条都没落成 -> 不能报 201 让调用方以为成功（R35-7 假成功）
        raise HTTPException(status_code=422, detail={
            "error": "allocation_apply_noop",
            "message": "没有任何条目可落位；请检查 player_id/to_room",
            "map_id": map_id, "skipped": skipped})
    return {"campaign_id": campaign, "map_id": map_id,
            "map_source": r["source"], "module_id": r["module_id"], "rooms": rooms,
            "requested_count": len(items), "applied_count": len(applied),
            "applied": applied, "skipped": skipped,
            "noop": not applied,
            "reason": ("当前状态下无需调整（无待落位角色）" if not applied else ""),
            "ts": _now()}


# ---------------------------------------------------------------- R20 角色启停

@router.get("/api/campaigns/{campaign}/agents/roles")
async def agents_roles(campaign: str, _: Any = Depends(_require_kp_end)) -> dict[str, Any]:
    """R20：≥4 个职责角色 + 各自启停 + 健康/降级态（UI 直接渲染）。"""
    return roles_mod.role_summary(campaign)


@router.post("/api/campaigns/{campaign}/agents/roles/{role_id}")
async def agents_role_set(campaign: str, role_id: str,
                          body: dict[str, Any] = Body(default={}),
                          _: Any = Depends(_require_kp_end)) -> dict[str, Any]:
    """R20：单独启用/停用某角色（其余角色不受影响）。"""
    if role_id not in roles_mod.ROLE_IDS:
        raise HTTPException(status_code=404, detail="unknown role %r" % role_id)
    enabled = bool(body.get("enabled", True))
    changed = roles_mod.set_enabled(campaign, role_id, enabled)
    return {"campaign_id": campaign, **changed,
            "summary": roles_mod.role_summary(campaign)}


@router.post("/api/campaigns/{campaign}/agents/roles/{role_id}/probe")
async def agents_role_probe(campaign: str, role_id: str,
                            body: dict[str, Any] = Body(default={}),
                            _: Any = Depends(_require_kp_end)) -> dict[str, Any]:
    """R20 验收探针：让指定角色"工作"并可选注入失败，用于证明
    ①单角色失败不影响其他角色 ②降级对 GM 可见。**不落事件、不改业务状态。**"""
    if role_id not in roles_mod.ROLE_IDS:
        raise HTTPException(status_code=404, detail="unknown role %r" % role_id)
    fail = bool(body.get("fail", False))

    def _work() -> str:
        if fail:
            raise RuntimeError("probe: injected failure")
        return "ok"

    result, degraded = roles_mod.run_role(campaign, role_id, _work, fallback="unavailable")
    return {"campaign_id": campaign, "role_id": role_id, "result": result,
            "degraded": degraded, "summary": roles_mod.role_summary(campaign)}


# ---------------------------------------------------------------- R4 grounding

@router.post("/api/campaigns/{campaign}/advice/grounded")
async def advice_grounded(campaign: str, body: dict[str, Any] = Body(default={}),
                          _: Any = Depends(_require_kp_end)) -> dict[str, Any]:
    """R4：建议必须引用**真实**场景/玩家/NPC 状态。

    与既有 `POST /access/advice` 的区别**仅**在于：scene 与 events **由服务端装配权威状态**，
    调用方不再（也无法）自行传入 —— 从而杜绝"退化为通用模板"。
    复用同一个 `_advice_core`（同一 gateway、同一降级链、同一幂等键）。
    """
    rtype = str(body.get("request_type") or "ruling")
    if rtype not in ADVICE_TYPES:
        raise HTTPException(status_code=422, detail="bad request_type %r" % rtype)
    st, events = await _state(campaign)
    folded = _fold_map(st.maps)
    first = next(iter(folded.values()), {"map_id": "", "token_rooms": {}})
    token_rooms = first.get("token_rooms", {})

    # —— 服务端装配权威上下文 ——
    chars = st.characters or {}
    scene_parts = [f"地图={first.get('map_id','') or '未载入'}"]
    for pid, ch in list(chars.items())[:8]:
        nm = (ch or {}).get("name") or pid
        scene_parts.append(f"{nm}@{token_rooms.get(pid,'未落位')}")
    if st.npc_lines:
        scene_parts.append("NPC：" + "；".join(f"{k}→{str(v)[:40]}" for k, v in list(st.npc_lines.items())[:4]))
    if st.turn is not None:
        scene_parts.append(f"回合#{st.turn.turn_no}/{st.turn.state}")
    scene = " | ".join(scene_parts)

    grounded_events = [f"{e.type}#{e.seq}" for e in events[-20:]]
    hint = str(body.get("hint") or "")

    res = _advice_core(campaign, rtype, scene, grounded_events, hint, str(body.get("req_id") or ""))
    return {"campaign_id": campaign, **res,
            "grounding": {"scene_assembled_by": "server",
                          "scene": scene,
                          "player_count": len(chars),
                          "npc_count": len(st.npc_lines or {}),
                          "event_refs": grounded_events,
                          "token_rooms": token_rooms},
            "ts": _now()}
