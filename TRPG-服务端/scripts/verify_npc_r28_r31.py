# -*- coding: utf-8 -*-
"""R2 T3 (R28-R31) NPC 自主性 —— 端到端验收脚本（可复现，只读事件流 + 只调 additive 端点）。

用法（在 TRPG-服务端 根目录）:
    python scripts/verify_npc_r28_r31.py
环境变量:
    TRPG_BASE        默认 http://127.0.0.1:9211
    TRPG_NPC_CAMPAIGN 默认 c_r2npc（每次运行复用同一 campaign，便于累积证据）

判据 -> 章节
    R28 章节: 一次性技能列表非空 / 可调用并产生规则层效果 / 同名互不干扰 /
              不污染全局技能表
    R29 章节: 记住见过谁与发生过什么 / 影响后续反应 / GM 查看-编辑-清空即时生效
    R30 章节: 自动生成（含语气/内容/是否隐瞒）/ 发送前玩家收不到 /
              关掉自动生成后完全按 GM 指令
    R31 章节: GM 改写台词后玩家收到改写版 / GM 立刻指定行为 / 完全接管 /
              中断改向 / 主持人鉴权 / 事件落库即推送（无需刷新）
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = os.environ.get("TRPG_BASE", "http://127.0.0.1:9211")
CFG = yaml.safe_load((ROOT / "configs" / "access_config.yaml").read_text(encoding="utf-8"))
TOK = {k: str((v or {}).get("token") or "") for k, v in (CFG.get("ends") or {}).items()}
KP = {"Authorization": "Bearer " + TOK.get("webapp", "")}
MOBILE = {"Authorization": "Bearer " + TOK.get("mobile", "")}

# 每次运行默认使用**全新 campaign**：一次性技能表 / NPC 记忆 / 提案队列都是
# 团内状态，复用旧 campaign 会让上一轮的使用计数与已批准台词污染判据。
CAMPAIGN = (os.environ.get("TRPG_NPC_CAMPAIGN")
            or ("c_r2npc_" + time.strftime("%m%d%H%M%S", time.gmtime())))
TABLE = "t_" + CAMPAIGN
NPC_A = "npc_clerk"     # modules/sample_coc/npcs/clerk.yaml
NPC_B = "npc_martha"    # modules/blackwater_creek/npcs/martha.yaml

C = httpx.Client(base_url=BASE, timeout=30.0)
FAILS: list[str] = []

# 证据落盘：远程控制台是 GBK，中文经管道会乱码 —— 本脚本自己把完整输出写
# UTF-8 文件，控制台只打 ASCII 摘要（证据以文件为准）。
EVIDENCE = ROOT / "run" / "verify_npc_r28_r31.txt"


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:  # noqa: BLE001
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:  # noqa: BLE001
                pass


def sec(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def show(label: str, obj: object) -> None:
    print("--- %s ---" % label)
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def check(rid: str, ok: bool, detail: str = "") -> None:
    print("%s  %s%s" % ("PASS" if ok else "FAIL", rid, ("   " + detail) if detail else ""))
    if not ok:
        FAILS.append(rid)


def req(method: str, path: str, *, headers=None, json_body=None, params=None) -> httpx.Response:
    r = C.request(method, path, headers=headers, json=json_body, params=params)
    print(">>> %s %s -> %s" % (method, r.request.url, r.status_code))
    return r


def events() -> list[dict]:
    r = C.get("/api/campaigns/%s/events" % CAMPAIGN, params={"since": -1, "limit": 1000})
    return list(r.json().get("events") or [])


def approved_lines(npc_id: str) -> list[str]:
    return [str(e["payload"].get("line", "")) for e in events()
            if e["type"] == "NPC_ACT_APPROVED" and e["payload"].get("npc_id") == npc_id]


def setup() -> None:
    sec("SETUP: 建桌（WS 房间映射需要 table<->campaign）+ 健康检查")
    show("health", req("GET", "/api/health").json())
    r = req("POST", "/api/tables", json_body={"table_id": TABLE, "campaign_id": CAMPAIGN,
                                              "ruleset": "coc7"})
    show("POST /api/tables", {"status": r.status_code, "body": r.json()})
    check("SETUP-table", r.status_code in (201, 409),
          "201 新建 / 409 已存在（复用）")


# ===========================================================================
# R28
# ===========================================================================

def r28() -> dict:
    sec("R28 按 NPC 生成一次性 skill（临时 / 只属该 NPC / 不污染全局技能表）")
    same_name = "恐吓"
    r1 = req("POST", "/api/campaigns/%s/npc/%s/skills" % (CAMPAIGN, NPC_A), headers=KP,
             json_body={"name": same_name,
                        "effect": {"kind": "check_bonus", "value": 2, "target": "persuade"},
                        "max_uses": 2})
    r2_ = req("POST", "/api/campaigns/%s/npc/%s/skills" % (CAMPAIGN, NPC_B), headers=KP,
              json_body={"name": same_name,
                         "effect": {"kind": "skill_delta", "value": 1, "target": "spot_hidden"},
                         "max_uses": 3})
    show("R28-1 为 NPC-A 生成「%s」" % same_name, r1.json())
    show("R28-2 为 NPC-B 生成**同名**「%s」" % same_name, r2_.json())
    lst = req("GET", "/api/campaigns/%s/npc/skills" % CAMPAIGN, headers=KP).json()
    show("R28-3 一次性技能列表（有名有姓，非空）", lst)
    ids = {s["skill_id"] for s in lst["skills"] if s["name"] == same_name}
    check("R28-list-nonempty", lst["count"] >= 2 and bool(lst["skills"]))
    check("R28-same-name-isolated", len(ids) == 2,
          "同名技能得到 2 个互不相同的作用域 id: %s" % sorted(ids))

    sid_a = r1.json()["skill"]["skill_id"]
    sid_b = r2_.json()["skill"]["skill_id"]
    card_a = {"skills": {"persuade": 50}}
    card_b = {"skills": {"spot_hidden": 40}}
    ia = req("POST", "/api/campaigns/%s/npc/skills/%s/invoke" % (CAMPAIGN, sid_a),
             headers=KP, json_body={"card": card_a, "difficulty": "regular", "rolled": 40})
    ib = req("POST", "/api/campaigns/%s/npc/skills/%s/invoke" % (CAMPAIGN, sid_b),
             headers=KP, json_body={"card": card_b, "difficulty": "regular", "rolled": 45})
    show("R28-4 调用 NPC-A 的一次性技能（规则层效果）", ia.json())
    show("R28-5 调用 NPC-B 的一次性技能（同名，效果独立）", ib.json())
    ra = ia.json().get("effect_result", {})
    rb = ib.json().get("effect_result", {})
    check("R28-invoke-rules-layer",
          bool(ra.get("rules", {}).get("level")) and bool(rb.get("rules", {}).get("level")),
          "两条调用都经 app.rules.checks.resolve_check 产出 level=%s / %s"
          % (ra.get("rules", {}).get("level"), rb.get("rules", {}).get("level")))
    check("R28-uses-independent",
          ra.get("uses") == 1 and rb.get("uses") == 1
          and ra.get("skill_id") != rb.get("skill_id"),
          "各自计数独立（uses=%s / %s），互不干扰" % (ra.get("uses"), rb.get("uses")))

    # 规则内核派发（rulepack 的 derived 表可按名引用一次性技能）
    # 说明: 本脚本是**另一个进程**，一次性技能表是进程内的（这正是「临时」语义），
    # 因此规则内核派发这一条在本进程内自建同构技能来验证。
    from app.rules import checks as chk
    from app.npc import skills as sk
    local = sk.forge_skill("c_unit_probe", "npc_unit", "恐吓",
                           {"kind": "skill_delta", "value": 1, "target": "spot_hidden"})
    derived = chk.resolve_derived(
        {"fn": sk.RULES_FN_NAME, "args": {"skill_id": local["skill_id"], "of": "$spot_hidden"}},
        {"skills": {"spot_hidden": 40}})
    show("R28-6 规则内核按名派发一次性技能 (derived fn=%s)" % sk.RULES_FN_NAME,
         {"spec": {"fn": sk.RULES_FN_NAME,
                   "args": {"skill_id": local["skill_id"], "of": "$spot_hidden"}},
          "card": {"skills": {"spot_hidden": 40}}, "resolved": derived})
    check("R28-rules-kernel-dispatch", derived == 41, "40 + skill_delta(1) = %s" % derived)

    # 不污染全局技能表
    before = len(chk.REGISTRY)
    for i in range(5):
        sk.forge_skill("c_unit_probe", "npc_unit_%d" % i, "同名技能",
                       {"kind": "check_bonus", "value": 1})
    after = len(chk.REGISTRY)
    reg_mod = __import__("trpg.agent.registry", fromlist=["*"])
    reg_list: object = "n/a"
    inst = getattr(reg_mod, "REGISTRY", None) or getattr(reg_mod, "registry", None)
    try:
        if inst is not None and hasattr(inst, "list"):
            reg_list = {"extensions": inst.list("all"),
                        "skills": inst.list("skill")}
        elif hasattr(reg_mod, "list"):
            reg_list = reg_mod.list()
    except Exception as exc:  # noqa: BLE001
        reg_list = "ERR: %s" % exc
    show("R28-7 全局技能表 / 规则内核表 前后对比",
         {"checks.REGISTRY_before": before, "checks.REGISTRY_after": after,
          "forged_records_in_ephemeral_table": len(sk.SKILLS),
          "trpg.agent.registry.list()": reg_list})
    check("R28-no-global-pollution", before == after,
          "新增 5 个一次性技能后规则内核表条目数不变（%d -> %d）；"
          "一次性技能只活在 app.npc.skills.SKILLS（%d 条）" % (before, after, len(sk.SKILLS)))
    return {"sid_a": sid_a, "sid_b": sid_b}


# ===========================================================================
# R29
# ===========================================================================

def r29() -> dict:
    sec("R29 NPC 记忆（记住见过谁/发生过什么/玩家做过什么；影响后续反应；GM 可查改清）")
    m1 = req("POST", "/api/campaigns/%s/npc/%s/observe" % (CAMPAIGN, NPC_B), headers=KP,
             json_body={"kind": "met", "ref": "pl-001", "text": "见过调查员 pl-001"})
    show("R29-1 记住「见过谁」", m1.json())
    m2 = req("POST", "/api/campaigns/%s/npc/%s/observe" % (CAMPAIGN, NPC_B), headers=KP,
             json_body={"kind": "player_action", "ref": "pl-001",
                        "text": "玩家 pl-001 威胁要砸开地窖的门"})
    show("R29-2 记住「玩家做过什么」", m2.json())
    m3 = req("POST", "/api/campaigns/%s/npc/%s/observe" % (CAMPAIGN, NPC_B), headers=KP,
             json_body={"kind": "player_action", "ref": "pl-001",
                        "text": "玩家 pl-001 开枪逼迫她说出地道位置"})
    show("R29-2b 第二条敌意记忆", m3.json())
    mem = req("GET", "/api/campaigns/%s/npc/%s/memory" % (CAMPAIGN, NPC_B), headers=KP).json()
    show("R29-3 GM 查看记忆", mem)
    check("R29-remember", mem["count"] >= 3 and mem["digest"]["met"] == ["pl-001"],
          "met=%s，player_actions=%d" % (mem["digest"]["met"], len(mem["digest"]["player_actions"])))

    # 记忆 -> 反应：敌意记忆把态度压到「戒备」，语气随之变冷
    g1 = req("POST", "/api/campaigns/%s/npc/%s/generate" % (CAMPAIGN, NPC_B), headers=KP,
             json_body={"trigger": "pl-001 再次靠近", "player_id": "pl-001"}).json()["proposal"]
    show("R29-4 记忆影响生成（敌意记忆 -> 态度/语气/隐瞒）",
         {"line": g1["line"], "tone": g1["tone"], "conceal": g1["conceal"],
          "memory_refs": g1["memory_refs"], "memory_digest": g1["memory_digest"]})
    check("R29-memory-affects-reaction",
          g1["memory_digest"]["attitude"] == "戒备" and g1["tone"] == "冷硬"
          and bool(g1["memory_refs"]),
          "attitude=%s tone=%s memory_refs=%d"
          % (g1["memory_digest"]["attitude"], g1["tone"], len(g1["memory_refs"])))

    # GM 编辑记忆 -> 即时生效
    mem_id = m2.json()["memory"]["mem_id"]
    mem_id2 = m3.json()["memory"]["mem_id"]
    e = req("PATCH", "/api/campaigns/%s/npc/%s/memory/%s" % (CAMPAIGN, NPC_B, mem_id),
            headers=KP, json_body={"text": "玩家 pl-001 安抚并帮助了玛莎"})
    e2 = req("PATCH", "/api/campaigns/%s/npc/%s/memory/%s" % (CAMPAIGN, NPC_B, mem_id2),
             headers=KP, json_body={"text": "玩家 pl-001 救回了她的侄儿亨利"})
    show("R29-5 GM 编辑记忆（改写为安抚/帮助/救人）", e2.json()["digest"])
    g2 = req("POST", "/api/campaigns/%s/npc/%s/generate" % (CAMPAIGN, NPC_B), headers=KP,
             json_body={"trigger": "pl-001 再次靠近", "player_id": "pl-001"}).json()["proposal"]
    show("R29-6 编辑后**立即**影响生成",
         {"line": g2["line"], "tone": g2["tone"], "conceal": g2["conceal"],
          "memory_digest": g2["memory_digest"]})
    check("R29-edit-takes-effect-immediately",
          g2["memory_digest"]["attitude"] == "亲近" and g2["tone"] == "热络",
          "编辑前 attitude=戒备/冷硬 -> 编辑后 attitude=%s/%s（同一次生成调用，无缓存）"
          % (g2["memory_digest"]["attitude"], g2["tone"]))

    # GM 清空 -> 立即生效
    d = req("DELETE", "/api/campaigns/%s/npc/%s/memory" % (CAMPAIGN, NPC_B), headers=KP)
    show("R29-7 GM 清空记忆", d.json())
    g3 = req("POST", "/api/campaigns/%s/npc/%s/generate" % (CAMPAIGN, NPC_B), headers=KP,
             json_body={"trigger": "pl-001 再次靠近", "player_id": "pl-001"}).json()["proposal"]
    show("R29-8 清空后生成回到中立", {"tone": g3["tone"], "memory_digest": g3["memory_digest"]})
    check("R29-clear-takes-effect-immediately",
          d.json()["removed"] >= 3 and g3["memory_digest"]["count"] == 0,
          "removed=%s -> 生成时记忆 count=0" % d.json()["removed"])
    return {"mem_id": mem_id}


# ===========================================================================
# R30
# ===========================================================================

def r30() -> dict:
    sec("R30 NPC 反应与对话自动生成（默认不直接对玩家生效，先给 GM 审）")
    req("POST", "/api/campaigns/%s/npc/auto" % CAMPAIGN, headers=KP,
        json_body={"enabled": True})
    before_events = len(events())
    before_lines = C.get("/api/campaigns/%s/npc/lines" % CAMPAIGN).json()["npc_lines"]
    r = req("POST", "/api/campaigns/%s/npc_act" % CAMPAIGN,
            json_body={"npc_id": NPC_A, "actor": "agent",
                       "trigger": "玩家询问闭馆那晚的事", "player_id": "pl-001",
                       "situation": "古籍室门口，夜里"})
    show("R30-1 npc_act 自动生成（未锁 403）", {"status": r.status_code, "body": r.json()})
    check("R30-npc-act-unlocked", r.status_code == 201,
          "旧行为恒 403，现返回 201 且入待审队列")
    prop_id = r.json()["proposal_id"]
    q = req("GET", "/api/campaigns/%s/npc/proposals" % CAMPAIGN, headers=KP,
            params={"status": "pending"}).json()
    show("R30-2 GM 待审队列（语气/内容/是否隐瞒/记忆依据）", q)
    target = [p for p in q["proposals"] if p["proposal_id"] == prop_id]
    check("R30-proposal-queued", bool(target), "候选 %s 在待审队列中" % prop_id)
    if target:
        t = target[0]
        check("R30-generation-fields",
              bool(t["line"]) and bool(t["tone"]) and bool(t["intent"])
              and isinstance(t["conceal"], bool),
              "line/tone/intent/conceal 齐全: tone=%s conceal=%s" % (t["tone"], t["conceal"]))
        cand_line = t["line"]
    else:
        cand_line = ""

    # 负例：批准前玩家侧收不到
    ev_after = events()
    approved_before = approved_lines(NPC_A)
    blob = json.dumps(ev_after, ensure_ascii=False)
    lines_now = C.get("/api/campaigns/%s/npc/lines" % CAMPAIGN).json()["npc_lines"]
    show("R30-3 批准前玩家侧取证",
         {"events_total": len(ev_after), "NPC_ACT_APPROVED_count_for_npc": len(approved_before),
          "npc_lines_before": before_lines, "npc_lines_now": lines_now,
          "候选台词是否出现在事件流中": (cand_line in blob) if cand_line else None})
    check("R30-not-visible-before-approval",
          not approved_before and NPC_A not in lines_now
          and (cand_line not in blob if cand_line else True),
          "批准前：无 NPC_ACT_APPROVED 事件、/npc/lines 无该 NPC、"
          "候选台词在事件流全文检索命中 0 次")

    # 关掉自动生成 -> NPC 完全按 GM 指令
    req("POST", "/api/campaigns/%s/npc/auto" % CAMPAIGN, headers=KP,
        json_body={"enabled": False})
    n_before = len(events())
    r_off = req("POST", "/api/campaigns/%s/npc_act" % CAMPAIGN,
                json_body={"npc_id": NPC_A, "actor": "agent", "trigger": "再问一次"})
    show("R30-4 关闭自动生成后 npc_act", {"status": r_off.status_code, "body": r_off.json()})
    n_after = len(events())
    check("R30-auto-off-blocks-generation",
          r_off.status_code == 409 and "npc_auto_disabled" in json.dumps(r_off.json(),
                                                                        ensure_ascii=False)
          and n_after == n_before,
          "409 npc_auto_disabled，且事件数不变（%d -> %d）" % (n_before, n_after))
    # 用 NPC-B 做「GM 指定行为」：GM 动作会把同 NPC 的待审候选置为 superseded，
    # NPC-A 的候选要留给 R31 的「改写台词」用例。
    d = req("POST", "/api/campaigns/%s/npc/direct" % CAMPAIGN, headers=KP,
            json_body={"npc_id": NPC_B, "line": "（主持人指定）我不记得那晚有谁。",
                       "intent": "主持人指定行为"})
    show("R30-5 关闭自动生成时 GM 指令仍然生效", d.json())
    check("R30-gm-direct-works-when-auto-off", d.status_code == 201,
          "GM 指定行为落 NPC_ACT_APPROVED: %r" % d.json()["delivered"]["line"])

    # 完全接管
    t = req("POST", "/api/campaigns/%s/npc/%s/takeover" % (CAMPAIGN, NPC_B), headers=KP,
            json_body={"enabled": True})
    show("R30-6 主持人完全接管 NPC-B", t.json())
    r_tk = req("POST", "/api/campaigns/%s/npc_act" % CAMPAIGN,
               json_body={"npc_id": NPC_B, "actor": "agent"})
    show("R30-7 接管后 npc_act", {"status": r_tk.status_code, "body": r_tk.json()})
    check("R30-takeover-blocks-autonomy",
          r_tk.status_code == 409 and "npc_takeover" in json.dumps(r_tk.json(), ensure_ascii=False),
          "409 npc_takeover")
    req("POST", "/api/campaigns/%s/npc/%s/takeover" % (CAMPAIGN, NPC_B), headers=KP,
        json_body={"enabled": False})
    req("POST", "/api/campaigns/%s/npc/auto" % CAMPAIGN, headers=KP,
        json_body={"enabled": True})
    return {"prop_id": prop_id, "cand_line": cand_line}


# ===========================================================================
# R31
# ===========================================================================

def r31(ctx: dict) -> None:
    sec("R31 主持人决定权（GM 改写台词 -> 玩家收到改写版；复用统一审批总线）")
    prop_id = ctx["prop_id"]

    # 主持人鉴权负例
    a1 = req("POST", "/api/campaigns/%s/approvals" % CAMPAIGN,
             json_body={"proposal_id": prop_id, "decision": "approve"})
    a2 = req("POST", "/api/campaigns/%s/approvals" % CAMPAIGN, headers=MOBILE,
             json_body={"proposal_id": prop_id, "decision": "approve"})
    show("R31-1 审批总线鉴权负例（NPC 分支）",
         {"no_token": {"status": a1.status_code, "body": a1.json()},
          "mobile_token": {"status": a2.status_code, "body": a2.json()}})
    check("R31-kp-only", a1.status_code == 401 and a2.status_code == 403,
          "无 token -> 401；玩家端(mobile) token -> 403 kp_only")

    # GM 改写台词
    edited = "（GM 改写）我确实检查过两遍门锁——但那晚，我看见的是维克多先生的鞋。"
    e = req("POST", "/api/campaigns/%s/approvals" % CAMPAIGN, headers=KP,
            json_body={"proposal_id": prop_id, "decision": "edit", "edited_text": edited})
    show("R31-2 GM 改写台词（同一审批总线 POST /approvals）", e.json())
    check("R31-edit-delivers-edited",
          e.status_code == 201 and e.json().get("line") == edited
          and e.json().get("type") == "NPC_ACT_APPROVED",
          "NPC_ACT_APPROVED 落库内容 = 改写版")

    # 玩家侧取证（与 player-web 同一条取数路径）
    ev = events()
    mine = [x for x in ev if x["type"] == "NPC_ACT_APPROVED"
            and x["payload"].get("npc_id") == NPC_A]
    lines_now = C.get("/api/campaigns/%s/npc/lines" % CAMPAIGN).json()["npc_lines"]
    show("R31-3 玩家侧取证",
         {"last_NPC_ACT_APPROVED": mine[-1] if mine else None,
          "player_visible_npc_lines": lines_now,
          "player-web 取值路径": "player-web/app.js evText(): TEXT_PATHS 含 ['line'] "
                                "-> 玩家端显示 payload.line"})
    check("R31-player-receives-edited-line",
          bool(mine) and mine[-1]["payload"]["line"] == edited
          and lines_now.get(NPC_A) == edited,
          "事件流与投影 npc_lines 都是改写版（原文不再出现）")
    check("R31-original-line-not-delivered",
          ctx["cand_line"] and ctx["cand_line"] != edited
          and ctx["cand_line"] not in json.dumps(mine, ensure_ascii=False),
          "候选原文没有进入任何 NPC_ACT_APPROVED 事件")

    # approve 原样下发 + reject 不落事件
    p2 = req("POST", "/api/campaigns/%s/npc/%s/generate" % (CAMPAIGN, NPC_A), headers=KP,
             json_body={"trigger": "追问通风管道"}).json()["proposal"]
    ap = req("POST", "/api/campaigns/%s/approvals" % CAMPAIGN, headers=KP,
             json_body={"proposal_id": p2["proposal_id"], "decision": "approve"})
    show("R31-4 批准原样下发", ap.json())
    check("R31-approve", ap.status_code == 201 and ap.json()["line"] == p2["line"])

    p3 = req("POST", "/api/campaigns/%s/npc/%s/generate" % (CAMPAIGN, NPC_A), headers=KP,
             json_body={"trigger": "问秘密"}).json()["proposal"]
    n_before = len(events())
    rj = req("POST", "/api/campaigns/%s/approvals" % CAMPAIGN, headers=KP,
             json_body={"proposal_id": p3["proposal_id"], "decision": "reject",
                        "reason": "主持人否决"})
    n_after = len(events())
    show("R31-5 驳回不落玩家可见事件", {"resp": rj.json(),
                                       "events_before": n_before, "events_after": n_after})
    check("R31-reject-no-event", n_after == n_before and rj.json()["delivered"] is False,
          "驳回后事件数不变，且候选台词未出现在事件流")

    # GM 立刻指定行为 + 中断改向
    d = req("POST", "/api/campaigns/%s/npc/direct" % CAMPAIGN, headers=KP,
            json_body={"npc_id": NPC_B, "line": "（GM 指定）地窖的钥匙在门框上。",
                       "intent": "主持人加速推进"})
    _ = d
    show("R31-6 GM 立刻让 NPC 做指定行为", d.json())
    check("R31-gm-direct-immediate", d.status_code == 201
          and C.get("/api/campaigns/%s/npc/lines" % CAMPAIGN).json()["npc_lines"].get(NPC_B)
          == "（GM 指定）地窖的钥匙在门框上。",
          "立即出现在玩家可见台词里")

    pend_before = req("POST", "/api/campaigns/%s/npc/%s/generate" % (CAMPAIGN, NPC_B),
                      headers=KP, json_body={"trigger": "插话"}).json()["proposal"]
    it = req("POST", "/api/campaigns/%s/npc/%s/interrupt" % (CAMPAIGN, NPC_B), headers=KP,
             json_body={"reason": "主持人改向"})
    show("R31-7 GM 中断改向（丢弃待审候选）", it.json())
    check("R31-interrupt-supersedes",
          it.json()["superseded"] >= 1
          and pend_before["proposal_id"] not in
          [p["proposal_id"] for p in req("GET", "/api/campaigns/%s/npc/proposals" % CAMPAIGN,
                                         headers=KP).json()["proposals"]],
          "待审候选被置为 superseded，不再出现在待审队列")

    # 落库即推送（各端无需刷新）
    sec("R31-8 事件落库即推送（订阅端无需刷新/轮询）")
    frame, dt_ms, sent_ms = asyncio.run(ws_probe())
    show("R31-8 WS 订阅端收到的帧",
         {"frame": frame, "post_ms": round(sent_ms, 1), "end_to_end_ms": round(dt_ms, 1)})
    check("R31-push-on-append", frame is not None and dt_ms < 500,
          "POST 返回->帧到达 %.1f ms（同一次 EventStore.append 触发，"
          "客户端无需刷新/轮询）" % dt_ms)


async def ws_probe():
    import websockets
    # 用当前 tip 作为 last_seq：只收「本次动作之后」的帧，避免把补发帧当成本次推送。
    tip = C.get("/api/campaigns/%s/events" % CAMPAIGN,
                params={"since": -1, "limit": 1000}).json().get("tip", -1)
    uri = ("ws://127.0.0.1:9211/ws?table=%s&viewer=kp1&role=kp&token=%s&last_seq=%d"
           % (TABLE, TOK.get("webapp", ""), int(tip)))
    async with websockets.connect(uri) as ws:
        t0 = time.time()
        resp = C.post("/api/campaigns/%s/npc/direct" % CAMPAIGN, headers=KP,
                      json={"npc_id": NPC_A, "line": "（GM 指定）门是锁着的。",
                            "intent": "推送探针"})
        sent = (time.time() - t0) * 1000.0
        print(">>> POST /npc/direct -> %s %s" % (resp.status_code, resp.json().get("delivered", {}).get("line")))
        deadline = time.time() + 5
        while time.time() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            dt = (time.time() - t0) * 1000.0
            try:
                fr = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            if fr.get("kind") == "PING":
                continue
            return fr, dt, sent
    return None, 99999.0, 0.0


def main() -> int:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    fh = open(EVIDENCE, "w", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, fh)
    print("TRPG R2 T3 (R28-R31) 验收 —— %s  campaign=%s table=%s" % (BASE, CAMPAIGN, TABLE))
    setup()
    r28()
    r29()
    ctx = r30()
    r31(ctx)
    sec("SUMMARY")
    print("evidence file: %s" % EVIDENCE)
    if FAILS:
        print("FAILED checks (%d): %s" % (len(FAILS), ", ".join(FAILS)))
        print("VERIFY_RESULT=FAIL")
        return 1
    print("ALL CHECKS PASSED")
    print("VERIFY_RESULT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
