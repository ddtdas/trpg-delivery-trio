"""Server-authoritative visibility (MIT).

Only the server projection decides who sees what; client claims are
never trusted. whisper targets are exact player-id sets; private
literals never appear in another viewer's DTO.
Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any

from app.domain.model import SessionState

PUBLIC = "public"
WHISPER = "whisper"
CONDITION = "condition"


def visible_infos(state: SessionState, viewer: str,
                  is_kp: bool = False) -> dict[str, dict[str, Any]]:
    """Infos visible to viewer. KP sees everything (incl. secrets needed
    to run the table); players see public + their whispers + met conditions."""
    out: dict[str, dict[str, Any]] = {}
    for info_id, info in state.infos.items():
        scope = info.get("scope", PUBLIC)
        if scope == PUBLIC:
            out[info_id] = _public_view(info_id, info)
        elif scope == WHISPER:
            if is_kp or viewer in info.get("targets", []):
                out[info_id] = _public_view(info_id, info)
        elif scope == CONDITION:
            if is_kp or info.get("condition_met"):
                out[info_id] = _public_view(info_id, info)
    return out


def _public_view(info_id: str, info: dict[str, Any]) -> dict[str, Any]:
    return {"info_id": info_id, "scope": info.get("scope"),
            "body_ref": info.get("body_ref")}


def filter_state_for(state: SessionState, viewer: str,
                     is_kp: bool = False) -> dict[str, Any]:
    """Authoritative per-viewer DTO. Private literals (role secrets,
    other players' whisper bodies, unmet-condition bodies) are stripped."""
    data = state.model_dump(mode="json")
    data["infos"] = visible_infos(state, viewer, is_kp)
    clues = {}
    for clue_id, clue in state.clues.items():
        if is_kp or clue.get("scope", PUBLIC) == PUBLIC \
                or clue.get("condition_met"):
            clues[clue_id] = clue
    data["clues"] = clues
    if not is_kp:
        data["roles"] = {pid: {"role_ref": r.get("role_ref")}
                         for pid, r in state.roles.items()}
        data.pop("table_token", None)
    return data


def can_see_map(state: SessionState, viewer: str, map_id: str,
                is_kp: bool = False) -> bool:
    if is_kp:
        return True
    revealed = state.infos.get("map:%s" % map_id, {})
    if revealed.get("scope") == PUBLIC:
        return True
    if revealed.get("scope") == WHISPER and viewer in revealed.get("targets", []):
        return True
    return map_id in state.maps and bool(state.maps[map_id].get("public", False))


def assert_no_leak(full: dict[str, Any], dto: dict[str, Any],
                   viewer: str) -> None:
    """Test helper: every secret literal in full must be absent from dto,
    unless viewer is KP or an explicit whisper target."""
    import json

    blob = json.dumps(dto, ensure_ascii=False)
    for pid, role in full.get("roles", {}).items():
        if pid == viewer:
            continue
        secret = (role or {}).get("secret_ref")
        if secret and secret in blob:
            raise AssertionError("secret leak for %s" % pid)
    for iid, info in full.get("infos", {}).items():
        if info.get("scope") == WHISPER and viewer not in info.get("targets", []):
            body = info.get("body_ref", "")
            if body and body in blob:
                raise AssertionError("whisper leak %s" % iid)


# ---- jubensha isolation (T26 M9-A): murderer secret masking ----

SPECTATOR = "spectator"


def mask_role_for(role: dict[str, Any], viewer: str, pid: str,
                  is_kp: bool = False) -> dict[str, Any]:
    """Murderer secret: event stream keeps secret_ref; everyone except KP
    (and never spectators) sees role_ref only. Owner does NOT see their
    own secret through DTOs either — KP reveals it out-of-band.

    T15: secret travels as secret_ref (a vault pointer, never the literal);
    the pointer itself is KP-only, so even a leaked ref discloses nothing."""
    if is_kp:
        return dict(role)
    return {"role_ref": role.get("role_ref")}


def secret_pointer(secret_ref: str) -> str:
    """T15: store/display only the pointer form (already the case for
    ROLE_ASSIGNED.secret_ref); literals must never be substituted in."""
    if not isinstance(secret_ref, str) or not secret_ref.strip():
        raise ValueError("secret_ref must be a non-empty string")
    return secret_ref.strip()


def filter_state_jubensha(state: SessionState, viewer: str,
                          role: str = "pl",
                          is_kp: bool = False) -> dict[str, Any]:
    """Jubensha-tightened DTO: spectator sees public only; players keep
    public + own whispers; secrets masked via mask_role_for."""
    dto = filter_state_for(state, viewer, is_kp)
    if role == SPECTATOR and not is_kp:
        dto["infos"] = {k: v for k, v in dto.get("infos", {}).items()
                        if v.get("scope") == PUBLIC}
        dto["clues"] = {k: v for k, v in dto.get("clues", {}).items()
                        if v.get("scope", PUBLIC) == PUBLIC}
        dto["roles"] = {}
        dto["votes"] = []
    dto["roles"] = {pid: mask_role_for(r, viewer, pid, is_kp)
                    for pid, r in (dto.get("roles", {}) or {}).items()}
    if not is_kp:
        # belt-and-braces: no secret_ref literal anywhere in player DTOs
        import json as _json

        blob = _json.dumps(dto, ensure_ascii=False)
        assert "secret_ref" not in blob, "jubensha secret key leaked"
    return dto


# ============================================================================
# R9 (additive) —— 事件流服务端权威裁剪
# ----------------------------------------------------------------------------
# 缺口（GAP-MATRIX R9 = FAIL）：GET /api/campaigns/{c}/events 不过滤 viewer；
# WS STATE_DELTA 为房间级广播。本段是**唯一的**事件可见性判据，
# REST 事件流（app/web/rest.py）与 WS 下发（app/web/ws.py）两条路径都必须经过它。
#
# 纪律：上方既有函数（visible_infos / filter_state_for / can_see_map /
#       assert_no_leak / mask_role_for）一律原样复用，不改语义；
#       不新增事件类型（app/domain/events.py 是冻结文件）。
# ============================================================================

# 玩家端一律不可见的事件类型（待审提案 / 驳回理由 / GM 内省 / 真相）
KP_ONLY_EVENT_TYPES: frozenset[str] = frozenset({
    "NARRATION_PROPOSED",     # R17：GM 发送前玩家收不到任何结果
    "NARRATION_REJECTED",     # R11：驳回理由可能含隐藏信息，玩家只收中性反馈
    "NPC_ACT_PROPOSED",       # R30/R31：NPC 自动行为必须先过 GM 审批
    "EVENT_INJECTED",         # GM 调试注入
    "SNAPSHOT_LOADED",        # 载入存档属 GM 操作
    "TABLE_CONFIG_UPDATED",   # 桌面配置属 GM 侧
    "CARD_REVERTED",          # 卡回退属 GM 侧
})

# 非 KP 一律剥离的 payload 键（秘密指针 / 骰种 / 真相引用 / GM 备注）
SECRET_PAYLOAD_KEYS: tuple[str, ...] = (
    "secret_ref", "seed", "truth", "truth_tree_ref", "timeline_ref",
    "solution", "culprit", "gm_notes", "kp_notes", "reasoning",
)

# 非 KP 且非该事件 actor 时剥离的 payload 键（他人意图摘要）
ACTOR_ONLY_PAYLOAD_KEYS: tuple[str, ...] = ("intent_summary",)

# R9 暗骰门禁（t16）：CHECK_RESOLVED 是**冻结模型**，payload 里没有 scope 字段，
# 因此无法用作用域判定可见性，只能看「这颗骰子属于谁」。
# 约定：card_id 指向 KP 本人（kp/gm/keeper/dm…）或为空 => 暗骰，非 KP 一律不可见。
# 依据：R19 感知检定写入的 card_id 是**发起玩家**（pipeline_api.perception_check:
#       card_id=actor），所以「不归属任何玩家」的检定就是 KP 暗骰。
# 空 card_id 采取 fail-closed（无法归属 = 不对外可见）。
DARK_ROLL_CARD_IDS: frozenset[str] = frozenset({
    "kp", "gm", "keeper", "dm", "gm_id", "kp_id", "keeper_id", "system",
})


# R9 暗骰（补全）：**掷骰者**为 KP 亦判暗骰。
# 语义理由：暗骰的判据是「这颗骰子属谁的私有信息」，不是 card_id 的字面值 ——
#   KP 本人掷的骰按定义就是暗骰（玩家侧只该看到结果被采纳后的叙述）；
#   KP 替 NPC 掷骰时 card_id 写的是 NPC 标识（如 "npc_butler"）而**不是**
#   "kp"，只看 card_id 会把这一整类漏掉。
# 与 DARK_ROLL_CARD_IDS 的「空值 fail-closed」合起来：非 KP 可见的 CHECK_RESOLVED
#   只剩「明确归属某位玩家」的检定。
#
# 已登记的未规定边界（本轮不修；登记见 docs/ROADMAP-DEFERRED.md §3 L12）：
#   既不属 DARK_ROLL_ACTORS、card_id 又是「非空且非 KP 别名」时，本函数返回
#   False ⇒ 该 CHECK_RESOLVED **对非 KP 可见**。由此下列两种组合都判为可见：
#     (actor="",           card_id="npc_butler")
#     (actor="npc_butler", card_id="npc_butler")
#   —— card_id 泛指 NPC 归属（而不是玩家 id）时会被当成「某位玩家」。
#   这两条组合不在 R9 判据覆盖范围内，**属已登记的未规定边界，不是缺陷**。
DARK_ROLL_ACTORS: frozenset[str] = frozenset({"kp", "gm", "keeper", "dm"})


def is_dark_roll(payload: dict[str, Any] | None, actor: str = "") -> bool:
    """该 CHECK_RESOLVED 是否为 KP 暗骰（非 KP 不可见）。

    R9 判据（两条取或，任一命中即裁剪）：
      1) **掷骰者**是 KP：event.actor 属 DARK_ROLL_ACTORS —— 语义
         「KP 的骰，非 KP 不可见」，覆盖 card_id 为 NPC 标识的情形；
      2) card_id 指向 KP 本人或为空（空值 fail-closed：无法归属任何
         玩家的检定不对外可见）。
    """
    who = str(actor or "").strip().lower()
    if who in DARK_ROLL_ACTORS:
        return True
    owner = str((payload or {}).get("card_id") or "").strip().lower()
    return (not owner) or (owner in DARK_ROLL_CARD_IDS)


def event_scope(ev: dict[str, Any]) -> str:
    """事件 payload 的作用域；缺省 public（与 events.Scope 一致）。"""
    payload = ev.get("payload")
    scope = (payload or {}).get("scope") if isinstance(payload, dict) else None
    return scope if scope in (PUBLIC, WHISPER, CONDITION) else PUBLIC


def clip_event(ev: dict[str, Any], viewer: str, is_kp: bool = False,
               state: SessionState | None = None) -> dict[str, Any] | None:
    """单个事件 DTO -> 该 viewer 可见的副本；不可见返回 None（服务端权威）。"""
    if not isinstance(ev, dict):
        return None
    if is_kp:
        return ev
    etype = str(ev.get("type") or "")
    if etype in KP_ONLY_EVENT_TYPES:
        return None
    payload = dict(ev.get("payload") or {})
    scope = event_scope(ev)
    targets = list(payload.get("targets") or [])
    if scope == WHISPER and viewer not in targets:
        return None
    if scope == CONDITION and viewer not in targets \
            and not payload.get("condition_met"):
        return None
    if etype == "CLUE_GRANTED" and not payload.get("condition_met"):
        return None
    if etype == "CHECK_RESOLVED" and is_dark_roll(payload, str(ev.get("actor") or "")):
        return None  # R9 暗骰：KP 私有的检定结果，玩家侧整条不可见
    if etype == "MAP_UPDATED" and state is not None:
        if not can_see_map(state, viewer, str(payload.get("map_id") or ""), is_kp):
            return None
    if etype == "ROLE_ASSIGNED":
        # 复用既有 mask_role_for：非 KP 只见 role_ref（secret_ref 是指针，KP-only）
        masked = mask_role_for(payload, viewer,
                               str(payload.get("player_id") or ""), is_kp)
        for keep in ("campaign_id", "player_id"):
            if keep in payload:
                masked.setdefault(keep, payload[keep])
        payload = masked
    if etype == "PRIVATE_MSG":
        # M3 (T6): 私聊仅【发送者 + 目标】可见（KP 全见）。非参与方整条裁剪，
        # 不泄露 from/to/text 任何字段。
        if not is_kp:
            if str(payload.get("from_player") or "") != viewer \
                    and viewer not in (payload.get("to_players") or []):
                return None
        payload["text"] = str(payload.get("text") or "")
    for key in SECRET_PAYLOAD_KEYS:
        payload.pop(key, None)
    if str(ev.get("actor") or "") != viewer:
        for key in ACTOR_ONLY_PAYLOAD_KEYS:
            payload.pop(key, None)
    out = dict(ev)
    out["payload"] = payload
    return out


def clip_events(events: list[dict[str, Any]], viewer: str, is_kp: bool = False,
                state: SessionState | None = None) -> list[dict[str, Any]]:
    """事件 DTO 列表 -> 该 viewer 的裁剪列表（顺序与 seq 语义不变）。"""
    out: list[dict[str, Any]] = []
    for ev in events or []:
        clipped = clip_event(ev, viewer, is_kp, state)
        if clipped is not None:
            out.append(clipped)
    return out


def leaked_literals(full: list[dict[str, Any]], dto: list[dict[str, Any]],
                    viewer: str, is_kp: bool = False) -> list[str]:
    """R9 负例判据：全量流中的秘密字面量若出现在 dto 中即返回其名称（应为空表）。

    覆盖：KP-only 事件正文/理由、他人 whisper body_ref、秘密指针键、
    骰种、真相引用、他人 intent_summary。
    """
    import json

    blob = json.dumps(dto, ensure_ascii=False)
    hits: list[str] = []
    if is_kp:
        return hits
    for ev in full or []:
        etype = str(ev.get("type") or "")
        payload = ev.get("payload") or {}
        if etype in KP_ONLY_EVENT_TYPES:
            for key in ("text", "reason", "reasoning"):
                val = payload.get(key)
                if isinstance(val, str) and val and val in blob:
                    hits.append("%s.%s" % (etype, key))
            continue
        if etype == "CHECK_RESOLVED" and is_dark_roll(payload, str(ev.get("actor") or "")):
            for key in ("target", "summary", "seed"):
                val = payload.get(key)
                if isinstance(val, str) and val and val in blob:
                    hits.append("%s.%s" % (etype, key))
            continue
        if event_scope(ev) == WHISPER \
                and viewer not in (payload.get("targets") or []):
            val = payload.get("body_ref")
            if isinstance(val, str) and val and val in blob:
                hits.append("%s.body_ref" % etype)
        for key in SECRET_PAYLOAD_KEYS:
            val = payload.get(key)
            if isinstance(val, str) and val and val in blob:
                hits.append("%s.%s" % (etype, key))
        if str(ev.get("actor") or "") != viewer:
            val = payload.get("intent_summary")
            if isinstance(val, str) and val and val in blob:
                hits.append("%s.intent_summary" % etype)
    return sorted(set(hits))