# -*- coding: utf-8 -*-
"""T3 补充验收：app/web/ws.py 的 npc_guard 硬锁 403 已解锁，且走**同一条**统一审批总线。

证明链：
  1) 无成员 -> actor_required（既有语义不变）
  2) 有成员 + 空 payload -> ACK gate=open（不再返回 npc_act locked）
  3) 有成员 + payload -> 委派 app.npc.director.handle_npc_act，返回 proposal_id
  4) 该 proposal_id 出现在**服务端进程**的 GM 待审队列（GET /npc/proposals）
     —— 说明 WS 上行与 REST 上行落的是同一个 npc_proposal 存储
  5) 用**既有唯一审批总线** POST /api/campaigns/{c}/approvals 拍板 -> NPC_ACT_APPROVED
     —— 说明没有第二套审批机制
  6) 把 rest.NPC_GATE_OPEN 置 False -> 恢复 403 文案（与 REST 逐字一致）

用法：python scripts/verify_npc_ws_guard.py
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

STAMP = time.strftime("%m%d%H%M%S", time.gmtime())
TABLE = "t_wsguard_" + STAMP
CAMPAIGN = "c_wsguard_" + STAMP
NPC = "npc_clerk"
FAILS: list[str] = []

EVIDENCE = ROOT / "run" / "verify_npc_ws_guard.txt"


class _Tee:
    def __init__(self, *s):
        self._s = s

    def write(self, d):
        for x in self._s:
            try:
                x.write(d)
            except Exception:  # noqa: BLE001
                pass

    def flush(self):
        for x in self._s:
            try:
                x.flush()
            except Exception:  # noqa: BLE001
                pass


def show(label, obj):
    print("--- %s ---" % label)
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def check(rid, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", rid, ("   " + detail) if detail else ""))
    if not ok:
        FAILS.append(rid)


def main() -> int:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    fh = open(EVIDENCE, "w", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, fh)

    from app.web.ws import Connection, Hub
    from app.web import rest as rest_mod

    print("T3 ws npc_guard 验收 —— %s  table=%s campaign=%s" % (BASE, TABLE, CAMPAIGN))
    rest_mod.TABLES[TABLE] = {"table_id": TABLE, "campaign_id": CAMPAIGN,
                              "ruleset": "coc7", "config": {}}
    hub = Hub()
    c = httpx.Client(base_url=BASE, timeout=30.0)

    async def run():
        r0 = await hub.npc_guard(TABLE, "nobody")
        room = hub.room(TABLE)
        room.members["v1"] = Connection(table_id=TABLE, viewer_id="v1", role="kp")
        r1 = await hub.npc_guard(TABLE, "v1")
        r2 = await hub.npc_guard(TABLE, "v1", {"npc_id": NPC, "actor": "agent",
                                               "trigger": "ws 上行：玩家询问闭馆那晚",
                                               "player_id": "pl-001"})
        return r0, r1, r2

    r0, r1, r2 = asyncio.run(run())
    show("1) 无成员连接", r0)
    show("2) 有成员 + 空 payload（解锁后应 ACK gate=open）", r1)
    show("3) 有成员 + payload（委派 handle_npc_act）", r2)
    check("WS-guard-no-hardlock", r1.get("kind") == "ACK" and r1.get("gate") == "open",
          "不再返回 npc_act locked；返回 %s" % r1)
    check("WS-guard-actor-required", r0.get("error") == "actor_required",
          "既有语义不变：%s" % r0)
    prop_id = (r2.get("result") or {}).get("proposal_id", "")
    check("WS-guard-delegates", r2.get("kind") == "ACK" and bool(prop_id),
          "委派成功，proposal_id=%s" % prop_id)

    # 4) 同一存储：服务端进程的 GM 待审队列里能看到它
    q = c.get("/api/campaigns/%s/npc/proposals" % CAMPAIGN, headers=KP,
              params={"status": "pending"}).json()
    show("4) 服务端 GM 待审队列（GET /npc/proposals）", q)
    ids = [p["proposal_id"] for p in q.get("proposals", [])]
    check("WS-guard-same-store", prop_id in ids,
          "WS 上行落的候选出现在同一 npc_proposal 存储：%s" % ids)

    # 5) 既有唯一审批总线拍板
    ap = c.post("/api/campaigns/%s/approvals" % CAMPAIGN, headers=KP,
                json={"proposal_id": prop_id, "decision": "edit",
                      "edited_text": "（GM 改写·WS 上行）我那晚锁了门,但看见维克多先生。"})
    show("5) 经统一审批总线 POST /approvals 拍板", ap.json())
    body = ap.json()
    check("WS-guard-single-approval-bus",
          ap.status_code == 201 and body.get("type") == "NPC_ACT_APPROVED"
          and body.get("line") == "（GM 改写·WS 上行）我那晚锁了门,但看见维克多先生。",
          "WS 上行的候选与 REST 上行走**同一条**审批总线，未新建第二套")

    lines = c.get("/api/campaigns/%s/npc/lines" % CAMPAIGN).json()["npc_lines"]
    show("5b) 玩家可见台词（批准后才出现）", lines)
    check("WS-guard-player-visible-after-approval",
          lines.get(NPC) == "（GM 改写·WS 上行）我那晚锁了门,但看见维克多先生。",
          "批准前玩家侧不可见，批准后才出现改写版")

    # 6) 开关锁回
    async def locked():
        rest_mod.NPC_GATE_OPEN = False
        try:
            return await hub.npc_guard(TABLE, "v1", {"npc_id": NPC, "actor": "agent"})
        finally:
            rest_mod.NPC_GATE_OPEN = True

    r6 = asyncio.run(locked())
    show("6) NPC_GATE_OPEN=False（锁回）", r6)
    check("WS-guard-lock-switch", r6.get("error") == "npc_act locked (default 403)",
          "与 REST 共用同一开关，文案逐字一致")

    print("")
    print("=" * 70)
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
