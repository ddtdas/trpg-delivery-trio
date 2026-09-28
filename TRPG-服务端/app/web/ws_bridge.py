"""T2 (additive): 域事件 -> WS 广播桥 (ENDPOINT-SPEC-NEW §8 / 队长裁决)。

背景: 生产路径此前从不调用 Hub.publish (app/web/ws.py:148 无生产调用方) ->
8 类下行帧在生产永不出现, 实时性为 0 (T1 实测)。

本模块提供**唯一的**「域事件 -> 冻结 8 帧」映射器 + 发布函数, 由
app/main.py 的 lifespan 挂到 EventStore.on_append 上 (单一收口):
    EventStore.on_append = ws_bridge.publish_events

铁律:
  - 单一收口: 只在 EventStore.append 成功后触发; 禁止业务分支散点 publish。
  - best-effort: 任何异常都被吞掉并记日志, 绝不向调用方抛出 —— 发布失败
    不影响事件落库与 HTTP 响应。
  - 帧复用: 严格复用冻结 8 帧 (app/web/ws_protocol.ServerFrame); **不新增帧
    类型、不改帧字段** (ws_protocol.py 是冻结契约, sha256 必须不变)。
  - 一事件一帧: 客户端按 seq 去重 (§3.4.2), 同 seq 发两帧会导致丢帧,
    故每个事件**只发一帧**。
  - 隔离: 不改 /app; 不改既有 /access 11 端点行为。

隐私设计 (SPEC §8.1 主推方案 —— **回退帧一律不带 payload**):
  兜底 STATE_DELTA 恒为 delta={"field":"event","value":{"type":<类型>,"redacted":true}}。
  理由:
    ① STATE_DELTA 是**房间级广播** —— Hub.viewer_may_see (app/web/ws.py) 只过滤
       WHISPER / NARRATION_PENDING / JOB_STATUS; 带 payload 等于向全体玩家泄密
       (契约 v1.20 已明确此实现事实)。
    ② **轮询才是主通道与完整性权威** (契约 §3.4.1); 回退帧的唯一职责只是
       「提示有变化」, 详情由轮询按可见性正确下发。
    ③ **按类型白名单必然漂移**: 域事件现有 37 种且会持续新增 —— 首版 9 类白名单
       实测漏了 18 类, 其中含 ROLE_ASSIGNED.secret_ref、CHECK_RESOLVED.seed、
       MAP_UPDATED、NARRATION_REJECTED.reason 等真实外泄。
  ⇒ 因此**不维护类型清单** (清单不存在就不会漂移)。防漂移由测试保证:
    tests/test_ws_broadcast_bridge.py::test_no_fallback_frame_leaks_payload_for_any_event_type
    (遍历全部 EVENT_TYPES, 断言回退帧不含 payload 键、且不把 payload 内容带出去)。
  证据: evidence/T2-ws-broadcast.txt §9。
Python 3.12 compatible.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.web.ws_protocol import ServerFrame

logger = logging.getLogger("trpg.ws_bridge")

# 事件类型 -> 冻结帧类型 (未列出的一律回退 STATE_DELTA)
_EVENT_FRAME_MAP: dict[str, str] = {
    "SCENE_UPDATED": "BRANCH_TAKEN",
    "TURN_STARTED": "TURN_UPDATED",
    "TURN_CLOSED": "TURN_UPDATED",
    "ACTION_WITHDRAWN": "TURN_UPDATED",
    "ACTION_SUBMITTED": "STATE_DELTA",
    "NARRATION_PROPOSED": "NARRATION_PENDING",
    "NARRATION_APPROVED": "NARRATION_APPROVED",
    "NARRATION_EDITED": "NARRATION_APPROVED",
    "INFO_REVEALED": "INFO_REVEALED",
    "BRANCH_TAKEN": "BRANCH_TAKEN",
    "ACT_ADVANCED": "BRANCH_TAKEN",
    "PRIVATE_MSG": "WHISPER",
    "CHAT_POLICY_UPDATED": "STATE_DELTA",
    "CHAT_MODE_SET": "STATE_DELTA",  # legacy alias (T6-3)
    "COMBAT_STARTED": "STATE_DELTA",
    "COMBAT_ROUND_PROPOSED": "STATE_DELTA",
    "COMBAT_ROUND_APPROVED": "STATE_DELTA",
    "COMBAT_ROUND_REJECTED": "STATE_DELTA",
    "COMBAT_ENDED": "STATE_DELTA",
    "NPC_TENDENCY_UPDATED": "STATE_DELTA",
    "NPC_TENDENCY_APPROVED": "STATE_DELTA",
    "SNAPSHOT_CREATED": "STATE_DELTA",
    "CHECKPOINT_TAKEN": "STATE_DELTA",
    "TIMELINE_ROLLBACK": "STATE_DELTA",
    "NPC_INFO_GENERATED": "STATE_DELTA",
    "PHASE_UPDATED": "STATE_DELTA",
}

# projector 的 turn.state -> 冻结 TurnState 字面量
_TURN_STATE_MAP: dict[str, str] = {
    "COLLECTING": "COLLECTING",
    "CLOSED": "CLOSING",
    "RESOLVING": "RESOLVING",
    "DISTRIBUTED": "DISTRIBUTED",
    "ADVANCED": "ADVANCED",
}


def _epoch(ts: Any) -> int:
    """ISO 字符串/数值 -> epoch 秒 (int); 解析失败回退 0 (帧字段要求 int)。"""
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, str) and ts:
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            return 0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    return 0


def _get_hub() -> Any:
    """惰性取 app.main.hub (避免 event_store <-> main 的循环 import)。"""
    try:
        from app.main import hub
    except Exception:  # noqa: BLE001 — 无 hub 环境 (纯 store 脚本) 直接跳过
        return None
    return hub


def _rooms_for(campaign_id: str) -> list[str]:
    """campaign -> 需要发布的房间 (table_id 与 campaign 双写, 去重)。

    WS 客户端用 ?table=<table_id> 订阅, 而事件按 campaign_id 落库; 两者可能
    不同 (t_acc vs c_acc), 故双写以免漏投。反查不到 table_id 时退化为 campaign。
    """
    rooms: list[str] = []
    try:
        from app.web import rest as rest_mod
        for tid, t in list(rest_mod.TABLES.items()):
            if str(t.get("campaign_id") or "") == campaign_id:
                if tid not in rooms:
                    rooms.append(tid)
                break
    except Exception:  # noqa: BLE001
        pass
    if campaign_id not in rooms:
        rooms.append(campaign_id)
    return rooms


async def _turn_info(campaign_id: str) -> dict[str, Any] | None:
    """投影当前回合 (TURN_UPDATED 需要完整 turn 对象)。"""
    from app.web import rest as rest_mod
    store = rest_mod._store()
    await store.init()
    events = await store.replay(campaign_id)
    turn = rest_mod.project(events, campaign_id).turn
    if turn is None:
        return None
    submitted = turn.submitted or {}
    return {
        "state": _TURN_STATE_MAP.get(str(turn.state), "COLLECTING"),
        "submitted": [{"player_id": pid,
                       "intent": (val or {}).get("intent") or None}
                      for pid, val in submitted.items()],
        "total": len(submitted),
        "countdown_end_ts": _epoch(turn.countdown_end_ts),
    }


async def build_frame(campaign_id: str, event: Any) -> ServerFrame | None:
    """域事件 -> 冻结帧 (一事件一帧); 无法映射时回退 STATE_DELTA。失败返回 None。"""
    seq = int(getattr(event, "seq", -1))
    if seq < 0:
        return None
    etype = str(getattr(event, "type", ""))
    payload = dict(getattr(event, "payload", None) or {})
    ts = _epoch(getattr(event, "ts", None))
    kind = _EVENT_FRAME_MAP.get(etype)
    base: dict[str, Any] = {"seq": seq, "campaign_id": campaign_id, "ts": ts}

    if kind == "TURN_UPDATED":
        turn = await _turn_info(campaign_id)
        if turn is None:
            kind = None  # 无回合投影 -> 回退摘要 (避免构造非法帧)
        else:
            return ServerFrame(kind="TURN_UPDATED", scope="public", turn=turn, **base)

    if kind == "NARRATION_PENDING":
        return ServerFrame(kind="NARRATION_PENDING", scope="kp", **base,
                           proposal={"id": str(payload.get("proposal_id", "")),
                                     "text": str(payload.get("text", "")),
                                     "intention": payload.get("intention"),
                                     "source": str(payload.get("source", "agent"))})

    if kind == "NARRATION_APPROVED":
        return ServerFrame(kind="NARRATION_APPROVED", scope="public", **base,
                           narration={"id": str(payload.get("proposal_id", "")),
                                      "text": str(payload.get("text", ""))})

    if kind == "BRANCH_TAKEN":
        # SCENE_UPDATED -> BRANCH_TAKEN (scene_id 作为节点)
        if etype == "SCENE_UPDATED":
            node_id = str(payload.get("scene_id") or "")
            label = str(payload.get("scene_id") or "")
            return ServerFrame(kind="BRANCH_TAKEN", scope="public", **base,
                               branch={"node_id": node_id, "label": label,
                                       "consequences": []})
        # ACT_ADVANCED -> BRANCH_TAKEN (act_no/act_name 映射到 node_id/label)
        node_id = str(payload.get("node_id") or ("act:%s" % payload.get("act_no", "")))
        label = str(payload.get("label") or payload.get("act_name") or "")
        return ServerFrame(kind="BRANCH_TAKEN", scope="public", **base,
                           branch={"node_id": node_id, "label": label,
                                   "consequences": list(
                                       payload.get("consequences") or [])})

    if kind == "INFO_REVEALED":
        info_id = str(payload.get("info_id", ""))
        body = str(payload.get("body_ref", ""))
        if str(payload.get("scope", "")) == "whisper":
            # 目标专属: 交给 Hub 的目标过滤 + 脱敏 (绝不落成公开帧)
            return ServerFrame(kind="WHISPER", scope="whisper", **base,
                               targets=list(payload.get("targets") or []),
                               packet={"info_id": info_id, "body": body})
        return ServerFrame(kind="INFO_REVEALED", scope="condition", **base,
                           packet={"info_id": info_id, "body": body})

    if kind == "WHISPER" and etype == "PRIVATE_MSG":
        # M3 (T6): 私聊 -> 冻结 WHISPER 帧（targets=to_players, packet.body=text）。
        # 目标过滤 + 非目标脱敏由 Hub.viewer_may_see / _strip_whisper 完成（服务端权威）。
        return ServerFrame(kind="WHISPER", scope="whisper", **base,
                           targets=list(payload.get("to_players") or []),
                           packet={"info_id": str(payload.get("from_player", "")),
                                   "body": str(payload.get("text", ""))})

    if kind == "STATE_DELTA" and etype == "CHAT_MODE_SET":
        # M3 (T6): 主持人切四态 -> STATE_DELTA(chat_mode) 广播（玩家徽标实时更新）。
        return ServerFrame(kind="STATE_DELTA", scope="public", **base,
                           delta={"field": "chat_mode",
                                  "value": {"mode": str(payload.get("mode", "")),
                                            "actor": str(payload.get("actor", ""))}})

    if kind == "STATE_DELTA" and etype == "PHASE_UPDATED":
        return ServerFrame(kind="STATE_DELTA", scope="public", **base,
                           delta={"field": "phase",
                                  "value": {"phase": str(payload.get("phase", "")),
                                            "started_seq": payload.get("started_seq")}})

    if kind == "STATE_DELTA" and etype == "ACTION_SUBMITTED":
        return ServerFrame(kind="STATE_DELTA", scope="public", **base,
                           delta={"field": "action",
                                  "value": {"player_id": str(payload.get("player_id", "")),
                                            "intent_summary": str(
                                                payload.get("intent_summary", ""))}})

    # 兜底: STATE_DELTA(event) —— **一律不带 payload** (SPEC §8.1 主推方案)。
    # 理由:
    #   ① STATE_DELTA 是**房间级广播** —— Hub.viewer_may_see 只过滤 WHISPER /
    #      NARRATION_PENDING / JOB_STATUS (app/web/ws.py), 带 payload 等于向全体玩家泄密;
    #   ② **轮询才是主通道与完整性权威** (契约 §3.4.1), 详情由轮询按可见性正确下发;
    #      回退帧的唯一职责只是「提示有变化」;
    #   ③ **按类型白名单必然漂移**: 域事件现有 37 种且会持续新增 —— 首版 9 类白名单
    #      实测漏了 18 类, 其中含 ROLE_ASSIGNED.secret_ref、CHECK_RESOLVED.seed、
    #      MAP_UPDATED、NARRATION_REJECTED.reason 等真实外泄。
    return ServerFrame(kind="STATE_DELTA", scope="public", **base,
                       delta={"field": "event",
                              "value": {"type": etype, "redacted": True}})


async def publish_events(campaign_id: str, events: list[Any]) -> None:
    """EventStore.on_append 的默认实现: 把已落库事件 best-effort 广播到其房间。

    绝不抛出 (异常只记日志) —— 发布失败不得影响落库与 HTTP 响应。
    """
    try:
        hub = _get_hub()
        if hub is None:
            return
        rooms = _rooms_for(campaign_id)
        for ev in events:
            try:
                frame = await build_frame(campaign_id, ev)
                if frame is None:
                    continue
                for room in rooms:
                    await hub.publish(room, frame)
            except Exception:  # noqa: BLE001 — 单帧失败不影响其它帧/落库
                logger.warning("ws_bridge: build/publish failed for %r",
                               getattr(ev, "type", None), exc_info=True)
                continue
    except Exception:  # noqa: BLE001 — 兜底: 发布绝不向调用方抛出
        logger.warning("ws_bridge: publish_events failed", exc_info=True)
        return