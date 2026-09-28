"""TRPG REST full version (MIT). W-H T26: + save/resume + map/npc guards.
EX-MISC G-1/G-2/P3: 延迟真采样环 + session_state projected_hash + 版本串同源.

Extends the T5 skeleton; /api/health shape is unchanged.
Illegal submissions -> 4xx. Event appends go through EventStore.
M9 rule: edit only — existing routes untouched in shape.
Python 3.12 compatible.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.config import APP_ROOT, get_version
from app.domain.events import EVENT_TYPES, GameEvent, make_event
from app.store.event_store import EventStore
from app.store.projector import project
from app.store.snapshot import latest_snapshot, resume, save_snapshot

router = APIRouter()

DATA_DIR = APP_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB = DATA_DIR / "trpg.db"

SNAP_BASE = APP_ROOT / "data" / "snapshots"

# t5 fix (reviewer P3): /api/campaigns/{c}/audio_import 的 chunks_base64 合计长度上限
# (base64 解码前内存防护; 常规录音 ~5MB base64, 64MB 上限足够宽松)。
AUDIO_IMPORT_MAX_B64 = 64 * 1024 * 1024

MAP_OPS = ("move", "add_token", "set_fog", "set_status", "set_light")

PERF_FIELDS = ["vad_ms", "stt_ms", "llm_first_token_ms",
               "tts_first_packet_ms", "approve_wait_ms"]

# ---- EX-MISC G-1: 延迟真采样环 (additive) --------------------------------
# 事件处理耗时采样: command_bus 提交→事件落库→WS 下发 的近似耗时。
# 环形队列 (maxlen), 服务运行中自采集; /api/metrics/latency 返回 samples/n/avg/p95。
MAX_LATENCY_SAMPLES = 200
_latency_ring: "collections.deque[tuple[int, int]]" = collections.deque(
    maxlen=MAX_LATENCY_SAMPLES)  # (ts_ms, elapsed_ms)


def record_latency_ms(ms: int) -> None:
    """追加一条延迟采样 (ts_ms, ms). additive, 线程内单进程足够."""
    if isinstance(ms, (int, float)) and ms >= 0:
        _latency_ring.append((int(time.time() * 1000), int(ms)))


def clear_latency_ring() -> None:
    """测试隔离用: 清空采样环."""
    _latency_ring.clear()


def latency_snapshot(n: int = 100) -> dict[str, Any]:
    """最近 n 条采样 -> {samples:[{t,ms}], n, avg, p95}."""
    if n < 1 or n > MAX_LATENCY_SAMPLES:
        n = MAX_LATENCY_SAMPLES
    items = list(_latency_ring)[-n:]
    ms_list = [ms for _, ms in items]
    n_ = len(ms_list)
    avg = round(sum(ms_list) / n_) if n_ else 0
    p95 = 0
    if n_:
        s = sorted(ms_list)
        idx = min(n_ - 1, max(0, int(n_ * 0.95) - 1))
        p95 = s[idx]
    return {"samples": [{"t": t, "ms": ms} for t, ms in items],
            "n": n_, "avg": avg, "p95": p95}


# ---- EX-MISC G-2: 事件流至 tip 的哈希 (additive) --------------------------
def projected_hash(events: list[GameEvent]) -> str:
    """事件流至 tip 的 sha256 (seq+type+payload 链, 同 MCP session_state 口径)."""
    canon = json.dumps([{"seq": e.seq, "type": e.type,
                         "payload": e.payload} for e in events],
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# In-memory tables registry (durable table state lives in events; W-D scope).
TABLES: dict[str, dict[str, Any]] = {}


def _store(path: Path | None = None) -> EventStore:
    return EventStore(path or DEFAULT_DB)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TableCreate(StrictModel):
    table_id: str
    campaign_id: str
    ruleset: str = "coc7"
    config: dict[str, Any] = {}


class EventSubmit(StrictModel):
    type: str
    payload: dict[str, Any] = {}
    actor: str
    approved_by: str | None = None
    causal: list[str] = []


class ApprovalBody(StrictModel):
    proposal_id: str
    decision: str  # approve | edit | reject
    edited_text: str | None = None
    reason: str | None = None


class AudioImport(StrictModel):
    player_id: str
    mime: str = "audio/opus"
    chunks_base64: list[str] = []


def _require_known_type(type: str) -> None:
    if type not in EVENT_TYPES:
        raise HTTPException(status_code=422, detail="unknown event type: %r" % type)


@router.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": get_version(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics/latency")
def latency() -> dict:
    # Skeleton kept for T5 clients; canonical shape lives at /api/metrics/latency.
    return {
        "fields": PERF_FIELDS,
        "count": 0,
        "mean": {},
        "p95": {},
    }


# ---- tables CRUD ----

@router.post("/api/tables", status_code=201)
def create_table(body: TableCreate) -> dict:
    if not body.table_id.strip() or not body.campaign_id.strip():
        raise HTTPException(status_code=422, detail="table_id/campaign_id required")
    if len(body.table_id.strip()) > 128 or len(body.campaign_id.strip()) > 128:
        raise HTTPException(status_code=422, detail="table_id/campaign_id too long (max 128)")
    if body.table_id in TABLES:
        raise HTTPException(status_code=409, detail="table exists")
    TABLES[body.table_id] = {"table_id": body.table_id,
                             "campaign_id": body.campaign_id,
                             "ruleset": body.ruleset, "config": body.config}
    # T10 (队长裁决, additive): 任何建桌路径都「创建即落盘」, 关闭
    # 「经 /api/tables 建桌要等下一次 resolve 才机会性落盘」的残留窗口。
    # 惰性 import 避免 rest <-> access 循环依赖; 持久化失败不得影响既有端点
    # 的签名与响应, 故 try/except 兜底。
    try:
        from app.web import access as _access_mod
        _access_mod.persist_tables()
    except Exception:  # noqa: BLE001 — best-effort
        pass
    return TABLES[body.table_id]


@router.get("/api/tables")
def list_tables() -> dict:
    return {"tables": list(TABLES.values())}


@router.get("/api/tables/{table_id}")
def get_table(table_id: str) -> dict:
    try:
        return TABLES[table_id]
    except KeyError:
        raise HTTPException(status_code=404, detail="table not found") from None


@router.patch("/api/tables/{table_id}")
def patch_table(table_id: str, body: dict[str, Any]) -> dict:
    if table_id not in TABLES:
        raise HTTPException(status_code=404, detail="table not found")
    if not isinstance(body, dict) or "config" not in body:
        raise HTTPException(status_code=422, detail="body.config required")
    TABLES[table_id]["config"] = body["config"]
    return TABLES[table_id]


@router.delete("/api/tables/{table_id}")
def delete_table(table_id: str) -> dict:
    if table_id not in TABLES:
        raise HTTPException(status_code=404, detail="table not found")
    del TABLES[table_id]
    return {"deleted": table_id}


# ---- events: submit + query (REST fallback for WS) ----

@router.post("/api/campaigns/{campaign}/events", status_code=201)
async def submit_event(campaign: str, body: EventSubmit) -> dict:
    if not body.actor.strip():
        raise HTTPException(status_code=422, detail="actor required")
    _require_known_type(body.type)
    try:
        ev = make_event(seq=0, campaign_id=campaign, type=body.type,
                        payload=body.payload, actor=body.actor,
                        ts=_now(), approved_by=body.approved_by,
                        causal=body.causal)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store = _store()
    await store.init()
    _t0 = time.perf_counter()
    seqs = await store.append(campaign, [ev])
    record_latency_ms(int((time.perf_counter() - _t0) * 1000))  # G-1 采样
    return {"seq": seqs[0], "type": body.type}


# ---- R9 (additive): 服务端权威 viewer 判定与事件裁剪 ----------------------
# 缺口（GAP-MATRIX R9 = FAIL）：本端点此前返回全部事件、不做 viewer 过滤，
# 仅靠客户端展示过滤 —— 违反「服务端权威裁剪」。
# 判定来源是 **token 所属端**（configs/access_config.yaml），不是查询串：
#   webapp(KP 端) token -> 全量（既有 GM 行为不变）
#   mobile / recorder token -> 强制玩家视角；**忽略 ?role=kp**
#   无 token / 未知 token -> 匿名按玩家视角（fail-closed，只给 public）
# 裁剪判据单一收口在 app.domain.visibility.clip_events（REST 与 WS 共用）。


def _end_name_for(token: str, authorization: str | None) -> str | None:
    """token -> 启用端名；未知/无 token 返回 None（不抛异常）。"""
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if token:
        provided = token
    if not provided:
        return None
    try:
        from app.web import access as _access_mod
        return _access_mod.token_end_name(provided)
    except Exception:  # noqa: BLE001 — 配置不可用时 fail-closed 按玩家处理
        return None


def resolve_viewer(token: str = "", authorization: str | None = None,
                   viewer: str = "", role: str = "") -> tuple[str, bool]:
    """(viewer_id, is_kp) —— 服务端权威；客户端自报的 role 一律不采信。"""
    if _end_name_for(token, authorization) == "webapp":
        return (viewer or "kp"), True
    return viewer, False


def _clip_event_dtos(events: list[GameEvent], dtos: list[dict[str, Any]],
                     viewer: str, is_kp: bool) -> list[dict[str, Any]]:
    """按 viewer 裁剪事件 DTO（KP 直通；玩家走 visibility.clip_events）。"""
    if is_kp:
        return dtos
    # R17: 非 KP 玩家不得看到【他人】ACTION_SUBMITTED（GM 审核前的行动正文）。
    # 与 WS 侧 project_frame(ws.py L145-154) 口径一致：他人行动明细分片不下发。
    dtos = [d for d in dtos
            if not (str(d.get("type") or "") == "ACTION_SUBMITTED"
                    and str((d.get("payload") or {}).get("player_id")
                            or d.get("actor") or "") != viewer)]
    from app.domain.visibility import clip_events
    # state 只被 clip_event 里 MAP_UPDATED 的 can_see_map 使用；本批没有 MAP_UPDATED 时
    # 跳过 project()，否则玩家端每拉一次事件流都要付一次 O(事件总数) 的投影代价
    # （R12 推送驱动下每来一帧就会拉一次）。实测 N=1600 时该投影占玩家端延迟约 14%。
    state = None
    if events and any(str(d.get("type") or "") == "MAP_UPDATED" for d in dtos):
        try:
            state = project(events, events[0].campaign_id)
        except Exception:  # noqa: BLE001 — 投影失败不阻断读取（保守裁剪）
            state = None
    return clip_events(dtos, viewer, False, state)


@router.get("/api/campaigns/{campaign}/events")
async def list_events(campaign: str, since: int = -1, limit: int = 200,
                      viewer: str = "", role: str = "", token: str = "",
                      authorization: str | None = Header(default=None)) -> dict:
    """事件流（R9：服务端权威裁剪）。viewer/role 由 token 决定，查询串不可提权。"""
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be 1..1000")
    store = _store()
    await store.init()
    events = await store.replay(campaign)
    resolved, is_kp = resolve_viewer(token, authorization, viewer, role)
    out = [e for e in events if e.seq > since][:limit]
    dtos = _clip_event_dtos(events, [e.model_dump(mode="json") for e in out],
                            resolved, is_kp)
    return {"events": dtos,
            "viewer": resolved, "scope": "kp" if is_kp else "player",
            "filtered": not is_kp,
            "tip": events[-1].seq if events else -1}


@router.get("/api/state")
async def rest_state(campaign: str = "", since: int = -1,
                     viewer: str = "", role: str = "", token: str = "",
                     authorization: str | None = Header(default=None)) -> dict:
    """WS fallback poll: GET /api/state?campaign=&since= (R9 同源裁剪)."""
    if not campaign:
        raise HTTPException(status_code=422, detail="campaign required")
    return await list_events(campaign, since=since, viewer=viewer, role=role,
                             token=token, authorization=authorization)


@router.get("/api/session_state")
async def session_state(campaign: str = "", viewer: str = "") -> dict:
    """Reconnect reconcile: tip + counts + projected_hash (contract §4断线提交)."""
    if not campaign:
        raise HTTPException(status_code=422, detail="campaign required")
    store = _store()
    await store.init()
    events = await store.replay(campaign)
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.type] = by_type.get(e.type, 0) + 1
    return {"campaign": campaign, "viewer": viewer,
            "tip": events[-1].seq if events else -1,
            "count": len(events), "by_type": by_type,
            "projected_hash": projected_hash(events)}


# ---- approvals ----

_APPROVAL_MAP = {"approve": "NARRATION_APPROVED", "edit": "NARRATION_EDITED",
                 "reject": "NARRATION_REJECTED"}


@router.post("/api/campaigns/{campaign}/approvals", status_code=201)
async def decide_approval(campaign: str, body: ApprovalBody,
                          request: Request) -> dict:
    if body.decision not in _APPROVAL_MAP:
        raise HTTPException(status_code=422, detail="decision must be approve|edit|reject")
    if body.decision == "edit" and not body.edited_text:
        raise HTTPException(status_code=422, detail="edited_text required for edit")
    # R31 (additive): NPC 提案走**同一条**审批总线 —— 由 proposal_id 是否命中
    # npc_proposal 判定, 不需要新增请求字段; 未命中时语义与改造前逐字一致。
    # NPC 分支额外要求主持端 (webapp) 凭据, 保证「自动行为必须先过主持人」。
    from app.npc import director as _npc_director
    if await _npc_director.is_npc_proposal(campaign, body.proposal_id):
        return await _npc_director.decide_npc(campaign, body, request)
    etype = _APPROVAL_MAP[body.decision]
    if etype == "NARRATION_APPROVED":
        payload: dict[str, Any] = {"proposal_id": body.proposal_id,
                                   "text": body.edited_text or ""}
    elif etype == "NARRATION_EDITED":
        payload = {"proposal_id": body.proposal_id, "text": body.edited_text or "",
                   "diff": {}}
    else:
        payload = {"proposal_id": body.proposal_id,
                   "reason": body.reason or "rejected by kp"}
    # ---- T7 (additive): 定向候选的决定正文脱敏 --------------------------
    # 有投递规格的候选（T7 交互结果/行动结果/字幕/感知通知）: 决定事件只带
    # 脱敏正文，真实内容经 INFO_REVEALED(whisper) 定向下发 —— 避免
    # NARRATION_APPROVED/EDITED 被 ws_bridge 映射成的 **public 帧** 把定向内容
    # 广播给全桌。无投递规格的候选（既有 agent 叙事链路）行为与改造前完全一致。
    from app.web import pipeline_api as _pipeline
    payload = _pipeline.adjust_decision(campaign, body.proposal_id,
                                        body.decision, payload)
    ev = GameEvent(seq=0, campaign_id=campaign, type=etype, payload=payload,
                   actor="kp", approved_by="kp", ts=_now())
    store = _store()
    await store.init()
    _t0 = time.perf_counter()
    seqs = await store.append(campaign, [ev])
    record_latency_ms(int((time.perf_counter() - _t0) * 1000))  # G-1 采样
    # T7 (additive): 决定后执行定向投递（无投递规格 -> None，行为不变）
    delivery = await _pipeline.deliver_after_decision(
        campaign, body.proposal_id, body.decision, body.edited_text or "")
    resp: dict[str, Any] = {"seq": seqs[0], "type": etype}
    if delivery:
        resp["delivery"] = delivery
    return resp


# ---- perf + audio-import fallback ----

@router.get("/api/metrics/latency")
def metrics_latency(campaign: str = "", n: int = 100) -> dict:
    """Contract §3 query + EX-MISC G-1: 真延迟采样, 响应 additive。

    既有字段 mean/p95/segments/n 保留 (前端 LatencySummary 兼容);
    新增 samples:[{t,ms}] 与 avg (环形延迟队列入口, 服务运行中自采集)。
    """
    if n < 1 or n > MAX_LATENCY_SAMPLES:
        raise HTTPException(status_code=422, detail="n must be 1..%d" % MAX_LATENCY_SAMPLES)
    snap = latency_snapshot(n)
    return {"mean": snap["avg"], "p95": snap["p95"],
            "segments": {k: 0 for k in PERF_FIELDS}, "n": snap["n"],
            "campaign": campaign,
            "samples": snap["samples"], "avg": snap["avg"]}


@router.post("/api/campaigns/{campaign}/audio_import", status_code=201)
async def audio_import(campaign: str, body: AudioImport) -> dict:
    if body.mime != "audio/opus":
        raise HTTPException(status_code=422, detail="mime must be audio/opus")
    if not body.chunks_base64:
        raise HTTPException(status_code=422, detail="chunks_base64 required")
    if sum(len(c) for c in body.chunks_base64) > AUDIO_IMPORT_MAX_B64:
        raise HTTPException(status_code=422,
                            detail="chunks_base64 too large (max %d bytes)" % AUDIO_IMPORT_MAX_B64)
    store = _store()
    await store.init()
    ev = make_event(seq=0, campaign_id=campaign, type="TRANSCRIPT_APPENDED",
                    payload={"campaign_id": campaign,
                             "seg": {"text": "[imported %d chunks]" % len(body.chunks_base64),
                                     "t0": 0.0, "t1": 0.0, "speaker": body.player_id},
                             "source": "import"},
                    actor=body.player_id, ts=_now())
    _t0 = time.perf_counter()
    seqs = await store.append(campaign, [ev])
    record_latency_ms(int((time.perf_counter() - _t0) * 1000))  # G-1 采样
    return {"seq": seqs[0], "job": {"job_id": "job_import_%d" % int(time.time()),
                                    "status": "done"}}


# ---- save / resume (T26 M9-A: snapshot + cursor catch-up) ----

class SnapshotBody(StrictModel):
    cursor: str = ""


@router.post("/api/campaigns/{campaign}/save", status_code=201)
async def save_campaign(campaign: str, body: SnapshotBody | None = None) -> dict:
    """Persist a snapshot of the projected state; returns seq cursor."""
    store = _store()
    await store.init()
    events = await store.replay(campaign)
    state = project(events, campaign)
    if body and body.cursor and state.turn is not None:
        state.turn.cursor = body.cursor
    path = save_snapshot(SNAP_BASE, state)
    sev = make_event(seq=0, campaign_id=campaign, type="SNAPSHOT_SAVED",
                     payload={"campaign_id": campaign,
                              "snapshot_ref": path.name,
                              "event_seq_at": state.last_seq},
                     actor="system", ts=_now())
    seqs = await store.append(campaign, [sev])
    return {"snapshot_ref": path.name, "event_seq_at": state.last_seq,
            "seq": seqs[0], "cursor": state.turn.cursor if state.turn else ""}


@router.get("/api/campaigns/{campaign}/resume")
async def resume_campaign(campaign: str, since: int = -1,
                          viewer: str = "", role: str = "", token: str = "",
                          authorization: str | None = Header(default=None)) -> dict:
    """Crash resume: snapshot cursor + tail events after `since` (R9 同源裁剪)."""
    store = _store()
    await store.init()
    state = await resume(store, SNAP_BASE, campaign)
    events = await store.replay(campaign)
    resolved, is_kp = resolve_viewer(token, authorization, viewer, role)
    tail = _clip_event_dtos(events,
                            [e.model_dump(mode="json") for e in events if e.seq > since],
                            resolved, is_kp)
    snap = latest_snapshot(SNAP_BASE, campaign)
    return {"campaign": campaign, "tip": events[-1].seq if events else -1,
            "viewer": resolved, "scope": "kp" if is_kp else "player",
            "cursor": state.turn.cursor if state.turn else "",
            "snapshot_ref": snap.name if snap else None,
            "event_seq_at": state.last_seq, "events": tail,
            "count": len(tail)}


@router.get("/api/campaigns/{campaign}/snapshots")
async def list_snapshots(campaign: str) -> dict:
    from app.store.snapshot import snapshot_index

    return {"campaign": campaign,
            "snapshots": snapshot_index(SNAP_BASE, campaign)}


# ---- review DTO (T15 M9: event stream -> ReviewView data) ----

@router.get("/api/campaigns/{campaign}/review")
async def review_view(campaign: str, viewer: str = "",
                      is_kp: bool = False, token: str = "",
                      authorization: str | None = Header(default=None)) -> dict:
    """复盘视图数据 DTO: turns/checks/narrations/branches/votes/truth.

    Server-side projection; per-viewer visibility enforced (whisper +
    role masking reuse filter_state_for). Pure read, no new events."""
    from app.domain.visibility import filter_state_for

    # R9: is_kp 不再采信查询串 —— 由 token 所属端判定（webapp=KP 端）。
    # 非 KP 调用方即使传 is_kp=true 也只拿到玩家视角。
    # viewer 形参默认与 /events 一致取 "": 真实取值由 token 判定; 预设 "kp" 会让
    # 无 token 调用在响应里回显 viewer="kp" (假称 KP 端), 与 /events 口径不一致。
    viewer, is_kp = resolve_viewer(token, authorization, viewer,
                                   "kp" if is_kp else "")
    store = _store()
    await store.init()
    events = await store.replay(campaign)
    state = project(events, campaign)
    dto = filter_state_for(state, viewer, is_kp)
    turn = state.turn
    return {"campaign": campaign, "viewer": viewer,
            "tip": events[-1].seq if events else -1,
            "turns": [{"turn_no": turn.turn_no if turn else 0,
                       "state": turn.state if turn else "IDLE",
                       "submitted": len(turn.submitted) if turn else 0,
                       "cursor": turn.cursor if turn else ""}],
            "checks": (list(state.checks) if is_kp else
                       [{"seq": c.get("seq"), "card_id": c.get("card_id"),
                         "target": c.get("target"), "total": c.get("total"),
                         "level": c.get("level")} for c in state.checks]),
            "narrations": (dict(state.narrations) if is_kp else
                           {pid: n for pid, n in state.narrations.items()
                            if n.get("status") in ("approved", "edited")}),
            "branches": list(state.branches), "votes": list(state.votes),
            "truth": (dict(state.truth) if is_kp else {}),
            "summaries": list(state.summaries),
            "transcript_ready": state.transcript_ready,
            "visible_infos": dto.get("infos", {}),
            "visible_clues": dto.get("clues", {})}


# ---- map command chain (T26 M9-A: via bus validation, approval-gated) ----

MAP_APPROVAL_REQUIRED = ("set_fog", "set_light")


class MapCommand(StrictModel):
    map_id: str
    op: str
    target: str
    delta: dict[str, Any] = {}
    actor: str = "kp"
    approved: bool = False


@router.post("/api/campaigns/{campaign}/map", status_code=201)
async def map_command(campaign: str, body: MapCommand) -> dict:
    """Map ops go through the command chain; fog/light need approval flag.

    The backend projection stays authoritative (can_see_map); this gate
    only decides whether the op is admitted to the event stream."""
    if body.op not in MAP_OPS:
        raise HTTPException(status_code=422, detail="bad op %r" % body.op)
    if not body.map_id.strip() or not body.target.strip():
        raise HTTPException(status_code=422, detail="map_id/target required")
    if body.op in MAP_APPROVAL_REQUIRED and not body.approved:
        raise HTTPException(status_code=403, detail="map op requires approval")
    store = _store()
    await store.init()
    ev = make_event(seq=0, campaign_id=campaign, type="MAP_UPDATED",
                    payload={"campaign_id": campaign, "map_id": body.map_id,
                             "op": body.op, "target": body.target,
                             "delta": body.delta},
                    actor=body.actor or "kp", ts=_now())
    seqs = await store.append(campaign, [ev])
    return {"seq": seqs[0], "type": "MAP_UPDATED", "op": body.op}


# ---- NPC gate (T26 M9-A -> R30: 默认解锁, 仍可锁回) ----

# R30: NPC 自主性解锁。默认开放; 设 TRPG_NPC_GATE=locked 可恢复旧 403 语义
# (状态码与 detail 文案逐字不变, 既有契约语义保持)。
NPC_GATE_OPEN = os.environ.get("TRPG_NPC_GATE", "open").strip().lower() != "locked"


class NpcAct(StrictModel):
    npc_id: str
    lines: list[str] = []
    actor: str = "agent"
    # R30 (additive): 场景输入 —— 自动生成台词/语气/隐瞒判定的依据。
    trigger: str = ""
    player_id: str = ""
    situation: str = ""


@router.post("/api/campaigns/{campaign}/npc_act", status_code=201)
async def npc_act(campaign: str, body: NpcAct) -> dict:
    """R30: NPC 行动 (默认解锁; TRPG_NPC_GATE=locked 可锁回 403)。

    自动行为**不直接对玩家生效**: 候选一律入主持人待审队列
    (NPC_ACT_PROPOSED + npc_proposal[status=pending]), 经既有统一审批总线
    POST /api/campaigns/{campaign}/approvals 拍板后才产生 NPC_ACT_APPROVED。
    响应不回显候选台词 (避免经本端点窥探 GM 待审内容)。
    """
    if not NPC_GATE_OPEN:
        raise HTTPException(status_code=403, detail="npc_act locked (default 403)")
    from app.npc import director as npc_director
    return await npc_director.handle_npc_act(campaign, body)
