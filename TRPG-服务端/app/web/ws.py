"""TRPG WS Hub: rooms, directed broadcast, resume, heartbeat (MIT).

Rooms keyed by table id; each connection carries viewer + role
(kp|pl|spectator) from `?table=&viewer=&role=`. resumption replays
last_seq+1..tip filtered by viewer. Heartbeat: server PING every 15s.
EX-2 D4: main.py lifespan 启动 heartbeat_loop 后台任务周期下发 PING
(复用 ws_protocol.PingFrame 编码, 仅活跃连接, 失败连接剔除防 ping 风暴)。
Python 3.12 compatible.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

from app.web.ws_protocol import (
    PingFrame,
    ProtocolError,
    ServerFrame,
    decode_client,
    encode_server,
)

HEARTBEAT_SEC = 15

KP_ONLY_UP = ("START_TURN", "CLOSE_WINDOW", "APPROVE_NARRATION")


@dataclass
class Connection:
    table_id: str
    viewer_id: str
    role: str
    send: object = None  # async callable taking a dict frame
    last_seq: int = -1


@dataclass
class StoredFrame:
    seq: int
    campaign_id: str
    frame: dict


@dataclass
class TableRoom:
    table_id: str
    campaign_id: str = ""
    members: dict[str, Connection] = field(default_factory=dict)  # viewer_id -> conn
    log: list[StoredFrame] = field(default_factory=list)
    seen_req_ids: set[str] = field(default_factory=set)


def viewer_may_see(frame: ServerFrame, viewer: Connection,
                   info_meta: "tuple[str, list[str]] | None" = None) -> bool:
    """Visibility filter (server-authoritative, R9).

    info_meta: INFO_REVEALED 帧对应域信息的 (scope, targets)，由 _info_meta()
    从**权威投影**取回，而不是读帧自带的 scope —— 冻结帧对 INFO_REVEALED 的
    scope 恒为 "condition"（ws_bridge 是冻结文件），不携带域作用域。
    """
    if frame.kind == "WHISPER":
        # KP 全见（与 filter_state_for(is_kp=True) 口径一致）；玩家仅目标可收
        return viewer.role == "kp" or (
            bool(frame.targets) and viewer.viewer_id in frame.targets)
    if frame.kind == "NARRATION_PENDING":
        return viewer.role == "kp"
    if frame.kind == "JOB_STATUS":
        return frame.actor_id == viewer.viewer_id or viewer.role == "kp"
    if frame.kind == "INFO_REVEALED":
        if viewer.role == "kp":
            return True
        scope, targets = info_meta if info_meta is not None else ("condition", [])
        if scope == "public":
            return True
        return viewer.viewer_id in list(targets or [])
    return True


# R9: INFO_REVEALED 帧的域作用域缓存 —— 键 (campaign_id, seq)，
# 一个 seq 只查一次库（同一帧会因多房间发布 / 多连接补发而被反复询问）。
_INFO_META_CACHE: dict[tuple[str, int], "tuple[str, list[str]]"] = {}
_INFO_META_CACHE_MAX = 4096


async def _info_meta(campaign_id: str, info_id: str,
                     seq: int = -1) -> "tuple[str, list[str]]":
    """R9: 取该 INFO_REVEALED 帧对应**权威事件**的 (scope, targets)。

    走 EventStore.one(seq) 主键查询（O(1)），不再全量 replay+project ——
    否则每次 INFO_REVEALED 广播的延迟会随事件总数线性增长。
    取不到一律按 condition/空目标（fail-closed：只有 KP 能看到）。
    """
    if not campaign_id or not info_id or seq < 0:
        return ("condition", [])
    key = (campaign_id, int(seq))
    cached = _INFO_META_CACHE.get(key)
    if cached is not None:
        return cached
    result: "tuple[str, list[str]]" = ("condition", [])
    try:
        from app.web import rest as rest_mod
        store = rest_mod._store()
        await store.init()
        ev = await store.one(int(seq))
        if ev is not None and str(ev.campaign_id) == campaign_id \
                and str(ev.type) == "INFO_REVEALED":
            payload = dict(ev.payload or {})
            if str(payload.get("info_id") or "") == info_id:
                result = (str(payload.get("scope") or "condition"),
                          list(payload.get("targets") or []))
    except Exception:  # noqa: BLE001 — fail-closed
        result = ("condition", [])
    if len(_INFO_META_CACHE) >= _INFO_META_CACHE_MAX:
        _INFO_META_CACHE.clear()
    _INFO_META_CACHE[key] = result
    return result


def project_frame(frame: ServerFrame, viewer: Connection) -> dict:
    """R9: 逐 viewer 的帧投影 —— 帧类型与字段集合不变，只裁剪内容。

    - WHISPER: 复用既有 _strip_whisper（非目标连 body 键都没有）
    - TURN_UPDATED: 非 KP 只看到自己的提交条目（R17：GM 审核前不泄露他人行动）
    - STATE_DELTA(action): 非 actor 的非 KP 看不到他人 intent_summary
    """
    raw = encode_server(frame)
    if viewer.role == "kp":
        return raw
    if frame.kind == "WHISPER":
        return _strip_whisper(raw, viewer.viewer_id)
    if frame.kind == "TURN_UPDATED" and isinstance(raw.get("turn"), dict):
        turn = dict(raw["turn"])
        turn["submitted"] = [
            s for s in (turn.get("submitted") or [])
            if str((s or {}).get("player_id") or "") == viewer.viewer_id]
        out = dict(raw)
        out["turn"] = turn
        return out
    if frame.kind == "STATE_DELTA" and isinstance(raw.get("delta"), dict):
        delta = dict(raw["delta"])
        value = delta.get("value")
        if isinstance(value, dict) \
                and str(value.get("player_id") or "") not in ("", viewer.viewer_id):
            delta["value"] = {k: v for k, v in value.items()
                              if k != "intent_summary"}
            out = dict(raw)
            out["delta"] = delta
            return out
    return raw


class Hub:
    def __init__(self) -> None:
        self._rooms: dict[str, TableRoom] = {}
        self._lock = asyncio.Lock()

    def room(self, table_id: str) -> TableRoom:
        room = self._rooms.get(table_id)
        if room is None:
            room = TableRoom(table_id=table_id)
            self._rooms[table_id] = room
        return room

    async def connect(self, conn: Connection, last_seq: int = -1) -> list[dict]:
        """Register; return catch-up frames (last_seq+1..tip, viewer-filtered)."""
        async with self._lock:
            room = self.room(conn.table_id)
            conn.last_seq = last_seq
            room.members[conn.viewer_id] = conn
            missed = [s.frame for s in room.log if s.seq > last_seq]
        out: list[dict] = []
        for raw in missed:
            payload = await self._deliverable(raw, conn)
            if payload is not None:
                out.append(payload)
        return out

    async def disconnect(self, table_id: str, viewer_id: str) -> None:
        async with self._lock:
            room = self._rooms.get(table_id)
            if room and viewer_id in room.members:
                del room.members[viewer_id]

    async def _deliverable(self, raw: dict, conn: Connection) -> dict | None:
        """R9: 单帧 -> 该连接可收的载荷；不可见返回 None。

        connect/catch_up 的回放路径与 publish 的实时路径共用同一判据，
        避免「实时路径已裁剪、补发路径仍全量」的旁路。
        """
        try:
            frame = ServerFrame(**raw)
        except Exception:
            return None
        meta = None
        if frame.kind == "INFO_REVEALED":
            meta = await _info_meta(
                frame.campaign_id,
                frame.packet.info_id if frame.packet else "",
                frame.seq)
        if not viewer_may_see(frame, conn, meta):
            return None
        return project_frame(frame, conn)

    async def catch_up(self, table_id: str, viewer_id: str,
                       last_seq: int) -> list[dict]:
        """Event-cursor补发: frames after last_seq, viewer-filtered.

        T26 M9-A: mirrors REST /resume tail semantics for WS reconnects.
        Reuses connect()'s filter path without re-registering."""
        async with self._lock:
            room = self._rooms.get(table_id)
            if room is None:
                return []
            conn = room.members.get(viewer_id)
            missed = [s.frame for s in room.log if s.seq > last_seq]
        if conn is None:
            return []
        out: list[dict] = []
        for raw in missed:
            payload = await self._deliverable(raw, conn)
            if payload is not None:
                out.append(payload)
        return out

    def cursor(self, table_id: str) -> int:
        """Tip seq of the room log (-1 when empty)."""
        room = self._rooms.get(table_id)
        if not room or not room.log:
            return -1
        return max(s.seq for s in room.log)

    async def npc_guard(self, table_id: str, viewer_id: str,
                        payload: "dict | None" = None) -> dict:
        """R30/R31 (additive): NPC 上行不再硬锁 403, 与 REST 同源、同一条总线。

        - 与 REST 共用同一个开关 rest.NPC_GATE_OPEN（TRPG_NPC_GATE=locked 时
          锁回，错误文案与 REST 逐字一致）；
        - 解锁时把请求交给 app.npc.director.handle_npc_act —— 即**同一条**统一
          审批总线：候选落 NPC_ACT_PROPOSED + npc_proposal[status=pending]，
          经 POST /api/campaigns/{c}/approvals 拍板才产生 NPC_ACT_APPROVED；
        - 冻结协议里没有 NPC_ACT 上行帧，故本方法不新增帧类型，只做服务端委派。
        """
        room = self._rooms.get(table_id)
        conn = room.members.get(viewer_id) if room else None
        if conn is None:
            return {"kind": "ERROR", "error": "actor_required"}
        from app.web import rest as rest_mod
        if not getattr(rest_mod, "NPC_GATE_OPEN", True):
            return {"kind": "ERROR", "error": "npc_act locked (default 403)"}
        if not isinstance(payload, dict) or not payload:
            return {"kind": "ACK", "up": "NPC_ACT", "gate": "open",
                    "route": "POST /api/campaigns/{campaign}/npc_act"}
        from fastapi import HTTPException as _HTTPException
        from pydantic import ValidationError as _ValidationError
        from app.npc import director as npc_director
        campaign = rest_mod.TABLES.get(table_id, {}).get("campaign_id") or table_id
        try:
            # 与 REST 完全同构：先过**同一个**请求模型（校验 / extra=forbid 语义一致）
            body = rest_mod.NpcAct(**payload)
        except _ValidationError as exc:
            return {"kind": "ERROR", "error": "validation_error", "detail": str(exc)}
        try:
            result = await npc_director.handle_npc_act(campaign, body)
        except _HTTPException as exc:
            return {"kind": "ERROR", "error": str(exc.detail)}
        except Exception as exc:  # noqa: BLE001 - 上行错误语义不变
            return {"kind": "ERROR", "error": str(exc)}
        return {"kind": "ACK", "up": "NPC_ACT", "gate": "open", "result": result}

    async def publish(self, table_id: str, frame: ServerFrame) -> dict[str, list[str]]:
        """Append + fan out with visibility filter. Returns {viewer: kinds}."""
        raw_full = encode_server(frame)
        # Canonical non-target WHISPER copy: no body field at all (contract §1.5).
        raw_redacted = _strip_whisper(raw_full, "") if frame.kind == "WHISPER" else raw_full
        async with self._lock:
            room = self.room(table_id)
            if not room.campaign_id:
                room.campaign_id = frame.campaign_id
            room.log.append(StoredFrame(seq=frame.seq, campaign_id=frame.campaign_id,
                                       frame=raw_full))
            targets = list(room.members.values())
        info_meta = None
        if frame.kind == "INFO_REVEALED":
            info_meta = await _info_meta(
                frame.campaign_id,
                frame.packet.info_id if frame.packet else "",
                frame.seq)
        delivered: dict[str, list[str]] = {}
        for conn in targets:
            if not viewer_may_see(frame, conn, info_meta):
                continue
            payload = project_frame(frame, conn)
            if frame.kind == "WHISPER":
                # Hard guarantee: body literal never leaves for non-targets,
                # and even target frames carry exactly their own packet.
                assert "body" not in str(payload.get("packet", {})) or \
                    conn.viewer_id in (frame.targets or []) or \
                    conn.role == "kp", "whisper leak"
            await _send(conn, payload)
            delivered.setdefault(conn.viewer_id, []).append(frame.kind)
            conn.last_seq = max(conn.last_seq, frame.seq)
        return delivered

    async def handle_up(self, table_id: str, viewer_id: str, raw: dict) -> dict:
        """Validate an upstream client frame. Returns an ack/error dict."""
        try:
            frame = decode_client(raw)
        except ProtocolError as exc:
            return {"kind": "ERROR", "error": str(exc)}
        if frame.kind in KP_ONLY_UP:
            room = self.room(table_id)
            conn = room.members.get(viewer_id)
            if conn is None or conn.role != "kp":
                return {"kind": "ERROR", "error": "kp_only"}
        room = self.room(table_id)
        if frame.req_id in room.seen_req_ids:
            return {"kind": "ACK", "req_id": frame.req_id, "duplicate": True}
        room.seen_req_ids.add(frame.req_id)
        if frame.kind == "AUDIO_CHUNK":
            return await self._audio_chunk(table_id, frame)
        return {"kind": "ACK", "req_id": frame.req_id, "up": frame.kind}

    # ---- V-2 (additive): AUDIO_CHUNK 实时组帧 -> 段完成 -> STT 转写落库 ----
    _audio_buffers: "dict[tuple[str, str], dict]" = {}
    AUDIO_SEG_MAX_BYTES = 200 * 1024
    AUDIO_SEG_TIMEOUT_S = 2.0

    async def _audio_chunk(self, table_id: str, frame: ClientFrame) -> dict:
        """累积 AUDIO_CHUNK 帧成段; 空 chunk(静音)/超时/上限 -> 切段转写。

        additive: 不改 ws_protocol 冻结帧格式; speaker=player_id;
        转写经 stt_service (mock/降级), 结果落 TRANSCRIPT_APPENDED(source=stt)。
        """
        from app.web import rest as rest_mod
        from app.voice import stt_service as stt_mod
        import asyncio as _asyncio, time as _time, base64 as _b64
        # AUDIO_CHUNK 字段在 ClientFrame 顶层 (player_id/mime/chunk_base64/seq)
        player_id = str(getattr(frame, "player_id", "") or getattr(frame, "actor_id", "") or "stt")
        chunk_b64 = str(getattr(frame, "chunk_base64", "") or "")
        seq = getattr(frame, "seq", None)
        key = (table_id, player_id)
        now = _time.time()
        buf = self._audio_buffers.setdefault(key, {"bytes": [], "n": 0, "t0": now})

        async def _finalize() -> dict:
            """切段: 聚合字节 -> 转写落库 (await 于 handle_up 事件循环内完成)."""
            data = b"".join(buf["bytes"])
            buf["bytes"] = []; buf["n"] = 0
            if not data:
                return {"kind": "ACK", "up": "AUDIO_CHUNK", "note": "segment-empty"}
            seg_n = getattr(self, "_audio_seg_seq", 0) + 1
            setattr(self, "_audio_seg_seq", seg_n)

            async def _run() -> None:
                try:
                    result = await _asyncio.to_thread(stt_mod.transcribe, data)
                    text = result.text
                    degraded = result.degraded
                except Exception:
                    text = "[STT 降级] 组帧转写不可用"; degraded = True
                try:
                    store = rest_mod._store()
                    await store.init()
                    # t5 fix (reviewer P2-1): WS 只有 table 参数, 原实现把 table_id
                    # 当 campaign_id 落库 -> 事件进错命名空间; 与 REST 侧同源解析
                    # (access.py _audio_import_core 同规则: TABLES 映射优先, 兜底 table_id)。
                    campaign = rest_mod.TABLES.get(table_id, {}).get("campaign_id") or table_id
                    ev = rest_mod.make_event(
                        seq=0, campaign_id=campaign,
                        type="TRANSCRIPT_APPENDED",
                        payload={"campaign_id": campaign,
                                 "seg": {"text": text, "t0": 0.0, "t1": 0.0,
                                         "speaker": player_id},
                                 "source": "stt"},
                        actor=player_id, ts=_now())
                    await store.append(campaign, [ev])
                except Exception as exc:  # noqa: BLE001
                    print("V2_STORE_ERR:", repr(exc))
            try:
                await _run()
            except Exception:
                pass
            return {"kind": "ACK", "up": "AUDIO_CHUNK", "seg": seg_n,
                    "bytes": len(data), "stt": "done"}

        # 空 chunk(静音标记) -> 立即切段
        if not chunk_b64:
            return await _finalize()
        try:
            chunk = _b64.b64decode(chunk_b64)
        except Exception:
            return {"kind": "ERROR", "error": "bad base64 in AUDIO_CHUNK"}
        if not chunk:
            return await _finalize()
        buf["bytes"].append(chunk); buf["n"] += 1
        # 超时(惰性结算): 距首帧 > 2s -> 切段
        if now - buf["t0"] > self.AUDIO_SEG_TIMEOUT_S:
            return await _finalize()
        # 上限 -> 切段
        if sum(len(b) for b in buf["bytes"]) >= self.AUDIO_SEG_MAX_BYTES:
            return await _finalize()
        return {"kind": "ACK", "req_id": frame.req_id, "up": "AUDIO_CHUNK",
                "buffered": len(buf["bytes"]), "seq": seq}

    def ping_frame(self) -> dict:
        return PingFrame(ts=int(time.time())).model_dump(mode="json")

    async def ping_all(self) -> int:
        """EX-2 D4: 向所有活跃连接下发 PING 帧, 返回成功下发数.

        复用 ws_protocol.PingFrame 编码 (ping_frame); 单连接发送失败仅剔除该连接
        (try/except 兜底), 不中断其他连接 —— 防 ping 风暴/死连接堆积。
        """
        async with self._lock:
            snapshot = [(tid, vid, conn)
                        for tid, room in self._rooms.items()
                        for vid, conn in list(room.members.items())]
        payload = self.ping_frame()
        sent = 0
        dead: list[tuple[str, str]] = []
        for tid, vid, conn in snapshot:
            try:
                await _send(conn, payload)
                sent += 1
            except Exception:
                dead.append((tid, vid))
        for tid, vid in dead:
            await self.disconnect(tid, vid)
        return sent


async def heartbeat_loop(hub: Hub, interval: float = HEARTBEAT_SEC) -> None:
    """EX-2 D4: 周期心跳后台任务 (每 interval 秒向全部连接发 PING).

    由 app.main lifespan 启动/取消; 单轮异常不终止循环 (continue 兜底),
    服务关闭时经 CancelledError 停止。
    """
    while True:
        try:
            await asyncio.sleep(interval)
            await hub.ping_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            continue  # 单轮异常不终止心跳


def _strip_whisper(raw_full: dict, viewer_id: str) -> dict:
    """Target copy keeps {info_id, body}; non-target copy has NO body key."""
    packet = dict(raw_full.get("packet", {}))
    out = dict(raw_full)
    if viewer_id and viewer_id in (raw_full.get("targets") or []):
        out["packet"] = {"info_id": packet.get("info_id"), "body": packet.get("body")}
    else:
        redacted = {"info_id": packet.get("info_id")}
        out["packet"] = redacted
    return out


async def _send(conn: Connection, payload: dict) -> None:
    send = conn.send
    if callable(send):
        res = send(payload)
        if asyncio.iscoroutine(res):
            await res
