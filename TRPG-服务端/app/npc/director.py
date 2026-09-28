"""R30 + R31: NPC 反应自动生成 & 主持人决定权 —— additive 分层。

需求判据 -> 本模块实现
--------------------------------------------------------------
R30「基于性格 / 目的 / 记忆 + 场景生成（含语气、内容、是否隐瞒）」
    -> generate(): 读 NPC 卡（role/description/traits/secret/lines/ai_lines）
       + memory.digest()（态度 / 见过谁 / 玩家做过什么）+ 场景(trigger/situation)
       -> 产出 {line, tone, intent, conceal, memory_refs}。
       确定性、无网络依赖；同一 trigger 稳定复现（可测试）。
R30「默认不直接对玩家生效，先给 GM 审」
    -> 生成结果只落 NPC_ACT_PROPOSED 事件 + npc_proposal(status=pending)；
       玩家侧没有任何正文可见（冻结帧语义下 NPC_ACT_PROPOSED 只出 redacted
       STATE_DELTA）。npc_act 的响应也**不回显候选台词**。
R31「所有自动行为必须先过主持人；复用既有统一审批总线」
    -> 决策入口仍是 POST /api/campaigns/{c}/approvals（本模块只被它调用：
       is_npc_proposal() / decide_npc()）。批准/改写才落 NPC_ACT_APPROVED，
       且该事件 actor=approved_by="kp" —— 只有主持人拍板才到达玩家。
R31「GM 可改台词/意图/目标/记忆、让 NPC 立刻做指定行为、完全接管；GM 修改优先」
    -> decide_npc(edit) 改写台词；direct() 立刻指定行为；
       set_takeover() 完全接管；set_auto(False) 关掉自动生成；
       interrupt() 中断改向。任何 GM 动作都会把同 NPC 的 pending 候选置为
       superseded（后写的事件在投影里覆盖前者 -> GM 版本优先）。

不新增事件类型 / 不新增协议帧 / 不新建第二套审批机制。
Python 3.12 compatible.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterable, Mapping

import aiosqlite
import yaml
from fastapi import HTTPException

from app.config import APP_ROOT
from app.npc import memory as mem_mod

__all__ = [
    "MODULES_DIR",
    "generate",
    "handle_npc_act",
    "is_npc_proposal",
    "decide_npc",
    "direct",
    "interrupt",
    "set_auto",
    "set_takeover",
    "get_settings",
    "pending",
    "player_lines",
    "supersede",
    "find_npc_card",
    "npc_meta",
]

MODULES_DIR = APP_ROOT / "modules"

PROPOSAL_STATUSES = ("pending", "approved", "edited", "rejected", "superseded")

_TONE_BY_ATTITUDE = {"戒备": "冷硬", "疏离": "疏远", "中立": "平常",
                     "配合": "缓和", "亲近": "热络"}

_AI_PREFIXES = ("建议台词", "建议台词1", "建议台词2", "建议台词3")

# R30 硬化: 候选台词**不写进事件 payload**（lines=[]），只留在 GM 专属的
# npc_proposal 表里。理由: 事件流 GET /api/campaigns/{c}/events 在 R9 服务端
# 裁剪落地之前是全量返回的 —— 候选台词一旦进 payload，就等于「批准前玩家可见」。
# 冻结 payload 模型 NpcActProposed.lines 有默认值，置空不违反契约；
# 批准后的正文由 NPC_ACT_APPROVED.line 承载（那才是给玩家的正式下发）。
BROADCAST_PENDING_LINES = False


def _pending_lines_payload(cand: list[str]) -> list[str]:
    return list(cand) if BROADCAST_PENDING_LINES else []


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_proposal_id() -> str:
    return "npcprop_%s" % uuid.uuid4().hex[:12]


def _rest():
    """惰性取 app.web.rest（避免 rest <-> npc 的循环 import）。"""
    from app.web import rest as rest_mod
    return rest_mod


async def _append(campaign_id: str, events: list[Any]) -> list[int]:
    rest_mod = _rest()
    store = rest_mod._store()
    await store.init()
    return await store.append(campaign_id, events)


# ---------------------------------------------------------------------------
# NPC 卡加载（读 modules/*/npcs/*.yaml；与 trpg.agent.scene_coordinator 同源）
# ---------------------------------------------------------------------------

def find_npc_card(npc_id: str, module_id: str | None = None) -> dict[str, Any]:
    """按 id 在 modules 下定位 NPC 卡。找不到 -> KeyError。"""
    if not isinstance(npc_id, str) or not npc_id.strip():
        raise ValueError("npc_id must be a non-empty string")
    npc_id = npc_id.strip()
    roots: list[Path] = []
    if module_id:
        roots.append(MODULES_DIR / str(module_id) / "npcs")
    if MODULES_DIR.is_dir():
        roots.extend(sorted(p / "npcs" for p in MODULES_DIR.iterdir()
                            if p.is_dir()))
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.yaml")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except (OSError, yaml.YAMLError):
                continue
            if isinstance(data, Mapping) and str(data.get("id")) == npc_id:
                return dict(data)
    raise KeyError(npc_id)


def _card_or_404(npc_id: str, module_id: str | None = None) -> dict[str, Any]:
    try:
        return find_npc_card(npc_id, module_id)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail="unknown npc_id: %r" % npc_id) from None


def npc_meta(npc_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """R5/t8 追加（additive）：把 NPC 卡上的**可读**信息附给 GM 界面。

    只读 modules/*/npcs/*.yaml，不新增机制、不改任何既有字段。
    刻意只取 name/role/visibility/hooks —— 卡上的 secret / stance / description
    属 KP 机密，不在这里外泄（玩家读口 /npc/lines 更不经过本函数）。
    """
    out: dict[str, dict[str, Any]] = {}
    for raw in npc_ids:
        nid = str(raw or "").strip()
        if not nid or nid == "*" or nid in out:
            continue
        try:
            card = find_npc_card(nid)
        except (KeyError, ValueError):
            out[nid] = {"npc_id": nid, "name": nid, "role": "", "visibility": "",
                        "hooks": [], "scenes": npc_scenes(nid), "has_card": False}
            continue
        out[nid] = {
            "npc_id": nid,
            "name": str(card.get("name") or nid),
            "role": str(card.get("role") or ""),
            "visibility": str(card.get("visibility") or ""),
            "hooks": [str(h) for h in (card.get("hooks") or [])],
            "scenes": npc_scenes(nid),
            "has_card": True,
        }
    return out


def npc_scenes(npc_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Q1 补（additive）：该 NPC 出现在事件图的哪些场景节点。

    只读 modules/*/event_graph.yaml 的 nodes[].npc_refs —— **纯既有静态数据**，
    不新增事件类型、不新增投影机制（EVENT_TYPES 37 项不变）。
    注意：这是「可能出现的场景」，不是「当前所在房间」；后者需要会话层的节点游标，
    当前事件流里不存在（无 NODE_ENTERED 类事件），需另行裁决。
    """
    nid = str(npc_id or "").strip()
    if not nid:
        return []
    out: list[dict[str, Any]] = []
    if not MODULES_DIR.is_dir():
        return []
    for mod in sorted(p for p in MODULES_DIR.iterdir() if p.is_dir()):
        gpath = mod / "event_graph.yaml"
        if not gpath.is_file():
            continue
        try:
            with open(gpath, encoding="utf-8") as f:
                graph = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            continue
        for node in (graph.get("nodes") or []):
            if not isinstance(node, Mapping):
                continue
            if nid not in [str(x) for x in (node.get("npc_refs") or [])]:
                continue
            out.append({"module_id": mod.name,
                        "node_id": str(node.get("id") or ""),
                        "title": str(node.get("title") or ""),
                        "map_ref": str(node.get("map_ref") or "")})
            if len(out) >= limit:
                return out
    return out


def _strip_ai_prefix(text: str) -> str:
    s = str(text).strip()
    if s.startswith("建议台词"):
        # 形如 "建议台词1(KP 可选用):'…'" -> 取冒号后的正文
        for sep in ("：", ":"):
            if sep in s:
                s = s.split(sep, 1)[1].strip()
                break
    return s.strip().strip("'").strip('"').strip()


def _line_pool(card: Mapping[str, Any]) -> list[str]:
    pool: list[str] = []
    for raw in list(card.get("ai_lines") or []):
        s = _strip_ai_prefix(raw)
        if s:
            pool.append(s)
    for raw in list(card.get("lines") or []):
        s = str(raw).strip()
        if s:
            pool.append(s)
    return pool


def _pick_index(pool: list[str], trigger: str, situation: str,
                mem_count: int) -> int:
    """确定性选行：场景 + 记忆规模共同决定（记忆会改变后续反应）。"""
    seed = "%s|%s|%d" % (trigger or "", situation or "", mem_count)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % len(pool)


def _memory_clause(card: Mapping[str, Any], mem: Mapping[str, Any],
                   player_id: str) -> str:
    name = str(card.get("name") or card.get("id") or "NPC")
    pid = str(player_id or "")
    if pid and pid in (mem.get("met") or []):
        return "（%s 认出了 %s）" % (name, pid)
    if mem.get("hostile") and mem.get("attitude") in ("戒备", "疏离"):
        return "（%s 的语气冷了下来，显然还记着先前的事）" % name
    if mem.get("friendly") and mem.get("attitude") in ("配合", "亲近"):
        return "（%s 的态度比之前松动了许多）" % name
    return ""


def _intent(card: Mapping[str, Any], mem: Mapping[str, Any],
            conceal: bool) -> str:
    """GM 可见的意图说明。**绝不复制 secret 正文**（避免外泄到玩家侧）。"""
    bits: list[str] = []
    role = str(card.get("role") or "").strip()
    if role:
        bits.append("目的：%s" % role)
    stance = str(card.get("stance") or "").strip()
    if stance:
        bits.append("立场：%s" % stance)
    traits = card.get("traits")
    if isinstance(traits, Mapping) and traits:
        bits.append("性格：%s" % json.dumps(dict(traits), ensure_ascii=False))
    bits.append("对玩家态度：%s" % mem.get("attitude", "中立"))
    bits.append("是否隐瞒：%s" % ("是（与自身旧事有关；细节见 NPC 卡 secret 字段，仅 GM 可见）"
                                  if conceal else "否"))
    return "；".join(bits)


# ---------------------------------------------------------------------------
# npc_proposal / npc_setting 读写
# ---------------------------------------------------------------------------

#: 候选状态 -> 玩家可见性（唯一判据，供所有读口共用）。
#: 只有 GM 拍板放行的状态才对玩家可见；pending/rejected/superseded 一律不可见 ——
#: 与 npc_act / generate 成功体里标注 visible_to_players=False 是同一语义
#: （契约骨架见 docs/R2-NPC-CONTRACT-CHANGE.md）。
_PLAYER_VISIBLE_STATUSES = ("approved", "edited")


def _player_visible(status: Any) -> bool:
    return str(status) in _PLAYER_VISIBLE_STATUSES


def _proposal_row(row: aiosqlite.Row) -> dict[str, Any]:
    """候选的统一序列化 —— **feed 列表/详情/state 三条读口共用**。

    R35-13b: visible_to_players 此前只在创建响应上临时补写（generate / npc_act），
    列表读口 _proposal_row 不带该键，于是同一实体在"创建"与"待审队列"两种视图里
    字段不一致（待审队列里读不到该键 -> 判据 all(x.get('visible_to_players') is False)
    为假）。这里按状态统一导出，让三条读口与创建响应形状一致。
    """
    status = row["status"]
    return {"proposal_id": row["proposal_id"], "campaign_id": row["campaign_id"],
            "npc_id": row["npc_id"], "line": row["line"], "tone": row["tone"],
            "intent": row["intent"], "conceal": bool(row["conceal"]),
            "memory_refs": json.loads(row["memory_refs"] or "[]"),
            "source": row["source"], "status": status,
            "visible_to_players": _player_visible(status),
            "final_line": row["final_line"], "edit_from": row["edit_from"],
            "created_ts": row["created_ts"], "decided_ts": row["decided_ts"],
            "decided_by": row["decided_by"]}


async def _insert_proposal(rec: Mapping[str, Any]) -> dict[str, Any]:
    await mem_mod.init()
    async with aiosqlite.connect(str(mem_mod.DB_PATH)) as db:
        await db.execute(
            "INSERT INTO npc_proposal (proposal_id, campaign_id, npc_id, line,"
            " tone, intent, conceal, memory_refs, source, status, final_line,"
            " edit_from, created_ts, decided_ts, decided_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec["proposal_id"], rec["campaign_id"], rec["npc_id"], rec["line"],
             rec.get("tone", ""), rec.get("intent", ""),
             1 if rec.get("conceal") else 0,
             json.dumps(list(rec.get("memory_refs") or []), ensure_ascii=False),
             rec.get("source", "auto"), rec.get("status", "pending"),
             rec.get("final_line", ""), rec.get("edit_from", ""),
             rec.get("created_ts") or _utcnow(),
             rec.get("decided_ts", ""), rec.get("decided_by", "")))
        await db.commit()
    return dict(rec)


async def _get_proposal(campaign_id: str, proposal_id: str) -> dict[str, Any] | None:
    await mem_mod.init()
    async with aiosqlite.connect(str(mem_mod.DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM npc_proposal WHERE proposal_id=? AND campaign_id=?",
            (proposal_id, campaign_id)) as cur:
            row = await cur.fetchone()
    return _proposal_row(row) if row is not None else None


async def is_npc_proposal(campaign_id: str, proposal_id: str) -> bool:
    """审批总线用它判断「这条提案是不是 NPC 提案」——不需要新增请求字段。"""
    if not proposal_id:
        return False
    try:
        return await _get_proposal(campaign_id, proposal_id) is not None
    except Exception:  # noqa: BLE001 — 判定失败按「非 NPC 提案」走既有语义
        return False


async def _set_status(proposal_id: str, status: str, *,
                      final_line: str | None = None,
                      edit_from: str | None = None,
                      decided_by: str = "") -> None:
    if status not in PROPOSAL_STATUSES:
        raise ValueError("bad status: %r" % status)
    await mem_mod.init()
    sets = ["status=?", "decided_ts=?", "decided_by=?"]
    args: list[Any] = [status, _utcnow(), decided_by]
    if final_line is not None:
        sets.append("final_line=?")
        args.append(final_line)
    if edit_from is not None:
        sets.append("edit_from=?")
        args.append(edit_from)
    args.append(proposal_id)
    async with aiosqlite.connect(str(mem_mod.DB_PATH)) as db:
        await db.execute("UPDATE npc_proposal SET %s WHERE proposal_id=?"
                         % ", ".join(sets), tuple(args))
        await db.commit()


async def supersede(campaign_id: str, npc_id: str,
                    keep: str | None = None) -> int:
    """把同 NPC 仍处 pending 的候选置为 superseded（GM 版本优先 / 中断改向）。"""
    await mem_mod.init()
    sql = ("UPDATE npc_proposal SET status='superseded', decided_ts=?,"
           " decided_by='kp' WHERE campaign_id=? AND npc_id=?"
           " AND status='pending'")
    args: list[Any] = [_utcnow(), campaign_id, npc_id]
    if keep:
        sql += " AND proposal_id<>?"
        args.append(keep)
    async with aiosqlite.connect(str(mem_mod.DB_PATH)) as db:
        cur = await db.execute(sql, tuple(args))
        await db.commit()
        return int(cur.rowcount or 0)


async def pending(campaign_id: str, status: str = "pending",
                  npc_id: str | None = None) -> list[dict[str, Any]]:
    """GM 待审队列（含语气 / 意图 / 是否隐瞒 / 记忆依据）。"""
    if status not in PROPOSAL_STATUSES and status != "all":
        raise ValueError("status must be one of %s|all" % (list(PROPOSAL_STATUSES),))
    await mem_mod.init()
    sql = "SELECT * FROM npc_proposal WHERE campaign_id=?"
    args: list[Any] = [campaign_id]
    if status != "all":
        sql += " AND status=?"
        args.append(status)
    if npc_id:
        sql += " AND npc_id=?"
        args.append(npc_id)
    sql += " ORDER BY created_ts ASC, rowid ASC"
    async with aiosqlite.connect(str(mem_mod.DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, tuple(args)) as cur:
            rows = await cur.fetchall()
    return [_proposal_row(r) for r in rows]


async def get_settings(campaign_id: str, npc_id: str | None = None) -> dict[str, Any]:
    """读取自动生成开关：campaign 级('*') 与 NPC 级覆盖。"""
    await mem_mod.init()
    async with aiosqlite.connect(str(mem_mod.DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM npc_setting WHERE campaign_id=?", (campaign_id,)) as cur:
            rows = await cur.fetchall()
    table = {r["npc_id"]: {"auto": bool(r["auto"]),
                           "takeover": bool(r["takeover"]),
                           "updated_ts": r["updated_ts"]} for r in rows}
    base = table.get("*", {"auto": True, "takeover": False, "updated_ts": ""})
    eff = {"auto": base["auto"], "takeover": base["takeover"]}
    if npc_id:
        over = table.get(npc_id)
        if over:
            eff = {"auto": over["auto"], "takeover": over["takeover"]}
    return {"campaign_id": campaign_id, "npc_id": npc_id or "*",
            "auto": eff["auto"], "takeover": eff["takeover"], "table": table}


async def _write_setting(campaign_id: str, npc_id: str, *,
                         auto: bool | None = None,
                         takeover: bool | None = None) -> dict[str, Any]:
    await mem_mod.init()
    cur = await get_settings(campaign_id, npc_id if npc_id != "*" else None)
    row = cur["table"].get(npc_id, {})
    new_auto = row.get("auto", True) if auto is None else bool(auto)
    new_take = row.get("takeover", False) if takeover is None else bool(takeover)
    async with aiosqlite.connect(str(mem_mod.DB_PATH)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO npc_setting (campaign_id, npc_id, auto,"
            " takeover, updated_ts) VALUES (?,?,?,?,?)",
            (campaign_id, npc_id, 1 if new_auto else 0,
             1 if new_take else 0, _utcnow()))
        await db.commit()
    return await get_settings(campaign_id, npc_id if npc_id != "*" else None)


async def set_auto(campaign_id: str, enabled: bool,
                   npc_id: str | None = None) -> dict[str, Any]:
    """开/关自动生成（关掉后 NPC 完全按 GM 指令）。"""
    return await _write_setting(campaign_id, npc_id or "*", auto=enabled)


async def set_takeover(campaign_id: str, npc_id: str,
                       enabled: bool = True) -> dict[str, Any]:
    """GM 完全接管该 NPC：自动行为停用。"""
    if not npc_id:
        raise ValueError("npc_id required")
    out = await _write_setting(campaign_id, npc_id, takeover=enabled)
    if enabled:
        await supersede(campaign_id, npc_id)
    return out


# ---------------------------------------------------------------------------
# R30 生成
# ---------------------------------------------------------------------------

async def generate(campaign_id: str, npc_id: str, *, trigger: str = "",
                   player_id: str = "", situation: str = "",
                   module_id: str | None = None) -> dict[str, Any]:
    """生成一条 NPC 反应候选（语气 / 内容 / 是否隐瞒），入 GM 待审队列。"""
    card = _card_or_404(npc_id, module_id)
    mem = await mem_mod.digest(campaign_id, npc_id)
    pool = _line_pool(card)
    if not pool:
        raise HTTPException(status_code=422,
                            detail="npc %s has no lines/ai_lines" % npc_id)
    idx = _pick_index(pool, trigger, situation, int(mem.get("count") or 0))
    base = pool[idx]
    attitude = str(mem.get("attitude") or "中立")
    tone = _TONE_BY_ATTITUDE.get(attitude, "平常")
    conceal = bool(str(card.get("secret") or "").strip()) and attitude != "亲近"
    clause = _memory_clause(card, mem, player_id)
    line = (clause + base) if clause else base
    intent = _intent(card, mem, conceal)

    pid = str(player_id or "")
    if pid and pid not in (mem.get("met") or []):
        await mem_mod.remember(campaign_id, npc_id, "met",
                               "见过 %s" % pid, ref=pid, source="auto")

    rec = {"proposal_id": _new_proposal_id(), "campaign_id": campaign_id,
           "npc_id": npc_id, "line": line, "tone": tone, "intent": intent,
           "conceal": conceal, "memory_refs": list(mem.get("memory_refs") or []),
           "source": "auto", "status": "pending", "final_line": "",
           "edit_from": "", "created_ts": _utcnow(), "decided_ts": "",
           "decided_by": ""}
    await _insert_proposal(rec)

    rest_mod = _rest()
    ev = rest_mod.make_event(0, campaign_id, "NPC_ACT_PROPOSED",
                             {"campaign_id": campaign_id, "npc_id": npc_id,
                              "lines": _pending_lines_payload([line]),
                              "context_ref": rec["proposal_id"]},
                             "agent", rest_mod._now())
    seqs = await _append(campaign_id, [ev])
    out = dict(rec)
    out["seq"] = seqs[0] if seqs else -1
    out["type"] = "NPC_ACT_PROPOSED"
    out["visible_to_players"] = False
    out["memory_digest"] = {"count": mem.get("count", 0),
                            "attitude": attitude,
                            "met": list(mem.get("met") or []),
                            "hostile": mem.get("hostile", 0),
                            "friendly": mem.get("friendly", 0)}
    return out


async def handle_npc_act(campaign_id: str, body: Any) -> dict[str, Any]:
    """REST POST /api/campaigns/{c}/npc_act 的实体（R30 解锁）。

    响应**不回显候选台词**（避免玩家侧通过该端点窥探 GM 待审内容）；
    GM 通过 GET /api/campaigns/{c}/npc/proposals 读取。
    """
    npc_id = str(getattr(body, "npc_id", "") or "").strip()
    if not npc_id:
        raise HTTPException(status_code=422, detail="npc_id required")
    _card_or_404(npc_id)
    settings = await get_settings(campaign_id, npc_id)
    if settings["takeover"]:
        raise HTTPException(status_code=409,
                            detail="npc_takeover: NPC 已由主持人完全接管，自动行为停用")
    if not settings["auto"]:
        raise HTTPException(status_code=409,
                            detail="npc_auto_disabled: 自动生成已关闭；请用"
                                   " POST /api/campaigns/{c}/npc/direct 由主持人指定行为")
    lines = [str(x) for x in (getattr(body, "lines", None) or []) if str(x).strip()]
    actor = str(getattr(body, "actor", "") or "agent")
    if lines:
        prop = await propose_explicit(campaign_id, npc_id, lines, actor=actor)
    else:
        prop = await generate(campaign_id, npc_id,
                              trigger=str(getattr(body, "trigger", "") or ""),
                              player_id=str(getattr(body, "player_id", "") or ""),
                              situation=str(getattr(body, "situation", "") or ""))
    return {"seq": prop.get("seq", -1), "type": "NPC_ACT_PROPOSED",
            "proposal_id": prop["proposal_id"], "npc_id": npc_id,
            "status": "pending", "visible_to_players": False,
            "note": "候选已入主持人待审队列，批准/改写前玩家不可见"}


async def propose_explicit(campaign_id: str, npc_id: str, lines: Iterable[str],
                           *, actor: str = "agent") -> dict[str, Any]:
    """显式候选（调用方给台词）：仍然先入 GM 待审队列。"""
    cand = [str(x).strip() for x in lines if str(x).strip()]
    if not cand:
        raise HTTPException(status_code=422, detail="lines must not be empty")
    rec = {"proposal_id": _new_proposal_id(), "campaign_id": campaign_id,
           "npc_id": npc_id, "line": cand[0], "tone": "（调用方给定）",
           "intent": "由 %s 显式提交的候选台词" % actor, "conceal": False,
           "memory_refs": [], "source": "explicit", "status": "pending",
           "final_line": "", "edit_from": "", "created_ts": _utcnow(),
           "decided_ts": "", "decided_by": ""}
    await _insert_proposal(rec)
    rest_mod = _rest()
    ev = rest_mod.make_event(0, campaign_id, "NPC_ACT_PROPOSED",
                             {"campaign_id": campaign_id, "npc_id": npc_id,
                              "lines": _pending_lines_payload(cand),
                              "context_ref": rec["proposal_id"]},
                             actor, rest_mod._now())
    seqs = await _append(campaign_id, [ev])
    rec["seq"] = seqs[0] if seqs else -1
    rec["type"] = "NPC_ACT_PROPOSED"
    rec["visible_to_players"] = False
    return rec


# ---------------------------------------------------------------------------
# R31 主持人决定权
# ---------------------------------------------------------------------------

def _require_kp(request: Any) -> None:
    """NPC 决策必须由主持人发起（复用既有 KP 端鉴权，不新造鉴权体系）。

    webapp 端 token = 主持端凭据；mobile/recorder 端 token -> 403 kp_only。
    """
    if request is None:
        return
    from app.web import access as access_mod
    auth = request.headers.get("authorization")
    token = request.query_params.get("token")
    access_mod._require_kp_end(authorization=auth, token=token)


async def decide_npc(campaign_id: str, body: Any,
                     request: Any = None) -> dict[str, Any]:
    """审批总线的 NPC 分支：批准 / 改写 / 驳回。

    - approve -> NPC_ACT_APPROVED(line=候选原文)
    - edit    -> NPC_ACT_APPROVED(line=edited_text)  （GM 改写优先）
    - reject  -> 不落任何玩家可见事件（驳回不泄露候选内容）
    """
    _require_kp(request)
    decision = str(getattr(body, "decision", "") or "")
    proposal_id = str(getattr(body, "proposal_id", "") or "")
    prop = await _get_proposal(campaign_id, proposal_id)
    if prop is None:
        raise HTTPException(status_code=404,
                            detail="unknown npc proposal: %r" % proposal_id)
    if prop["status"] != "pending":
        raise HTTPException(status_code=409,
                            detail="npc proposal already %s" % prop["status"])
    if decision == "reject":
        await _set_status(proposal_id, "rejected", decided_by="kp")
        return {"proposal_id": proposal_id, "npc_id": prop["npc_id"],
                "status": "rejected", "delivered": False, "type": None,
                "seq": None, "line": None,
                "reason": str(getattr(body, "reason", "") or "rejected by kp")}
    if decision == "edit":
        final = str(getattr(body, "edited_text", "") or "").strip()
        if not final:
            raise HTTPException(status_code=422,
                                detail="edited_text required for edit")
        status = "edited"
    else:
        final = prop["line"]
        status = "approved"
    rest_mod = _rest()
    ev = rest_mod.make_event(0, campaign_id, "NPC_ACT_APPROVED",
                             {"campaign_id": campaign_id,
                              "npc_id": prop["npc_id"], "line": final},
                             "kp", rest_mod._now(), approved_by="kp")
    seqs = await _append(campaign_id, [ev])
    await _set_status(proposal_id, status, final_line=final,
                      edit_from=(prop["line"] if status == "edited" else ""),
                      decided_by="kp")
    superseded = await supersede(campaign_id, prop["npc_id"], keep=proposal_id)
    await mem_mod.remember(campaign_id, prop["npc_id"], "event",
                           "我说过：%s" % final, source="approved")
    return {"proposal_id": proposal_id, "npc_id": prop["npc_id"],
            "status": status, "delivered": True, "type": "NPC_ACT_APPROVED",
            "seq": seqs[0] if seqs else -1, "line": final,
            "edit": ({"from": prop["line"], "to": final}
                     if status == "edited" else None),
            "superseded": superseded}


async def direct(campaign_id: str, npc_id: str, line: str,
                 intent: str = "") -> dict[str, Any]:
    """GM 立刻让 NPC 做指定行为（完全按 GM 指令，不经自动生成）。"""
    npc_id = str(npc_id or "").strip()
    text = str(line or "").strip()
    if not npc_id or not text:
        raise HTTPException(status_code=422, detail="npc_id / line required")
    _card_or_404(npc_id)
    superseded = await supersede(campaign_id, npc_id)
    rec = {"proposal_id": _new_proposal_id(), "campaign_id": campaign_id,
           "npc_id": npc_id, "line": text, "tone": "（主持人指定）",
           "intent": str(intent or "主持人直接指定行为"), "conceal": False,
           "memory_refs": [], "source": "gm_direct", "status": "approved",
           "final_line": text, "edit_from": "", "created_ts": _utcnow(),
           "decided_ts": _utcnow(), "decided_by": "kp"}
    await _insert_proposal(rec)
    rest_mod = _rest()
    ev = rest_mod.make_event(0, campaign_id, "NPC_ACT_APPROVED",
                             {"campaign_id": campaign_id, "npc_id": npc_id,
                              "line": text}, "kp", rest_mod._now(),
                             approved_by="kp")
    seqs = await _append(campaign_id, [ev])
    await mem_mod.remember(campaign_id, npc_id, "event",
                           "我说过：%s" % text, source="gm_direct")
    return {"proposal_id": rec["proposal_id"], "npc_id": npc_id,
            "status": "approved", "delivered": True,
            "type": "NPC_ACT_APPROVED", "seq": seqs[0] if seqs else -1,
            "line": text, "source": "gm_direct", "superseded": superseded}


async def interrupt(campaign_id: str, npc_id: str,
                    reason: str = "") -> dict[str, Any]:
    """GM 中断改向：丢弃该 NPC 所有待审候选（可随时改）。"""
    n = await supersede(campaign_id, npc_id)
    await mem_mod.remember(campaign_id, npc_id, "gm_note",
                           "主持人中断改向：%s" % (reason or "（无说明）"),
                           source="gm")
    return {"npc_id": npc_id, "superseded": n, "reason": reason}


async def player_lines(campaign_id: str) -> dict[str, Any]:
    """玩家可见的 NPC 台词（来自事件投影：只有 NPC_ACT_APPROVED 会落这里）。"""
    rest_mod = _rest()
    store = rest_mod._store()
    await store.init()
    events = await store.replay(campaign_id)
    state = rest_mod.project(events, campaign_id)
    return {"campaign_id": campaign_id, "npc_lines": dict(state.npc_lines),
            "tip": events[-1].seq if events else -1}
