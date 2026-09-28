# -*- coding: utf-8 -*-
"""T3 UI 实测准备：建桌/建 campaign、解析连接码、生成一条待审 NPC 候选。"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
import httpx, yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BASE = os.environ.get("TRPG_BASE", "http://127.0.0.1:9211")
CFG = yaml.safe_load((ROOT / "configs" / "access_config.yaml").read_text(encoding="utf-8"))
TOK = {k: str((v or {}).get("token") or "") for k, v in (CFG.get("ends") or {}).items()}
KP = {"Authorization": "Bearer " + TOK["webapp"]}
MOBILE = TOK["mobile"]

STAMP = time.strftime("%m%d%H%M%S", time.gmtime())
TABLE = os.environ.get("T3_TABLE") or ("t_uiprobe_" + STAMP)
CAMPAIGN = os.environ.get("T3_CAMPAIGN") or ("c_uiprobe_" + STAMP)
NPC = "npc_clerk"
EDIT = "（GM 改写·UI 实测）我确实锁了门——但那晚我看见的是维克多先生的鞋。@%s" % STAMP

c = httpx.Client(base_url=BASE, timeout=30.0)
r = c.post("/api/tables", json={"table_id": TABLE, "campaign_id": CAMPAIGN, "ruleset": "coc7"})
print("POST /api/tables ->", r.status_code, json.dumps(r.json(), ensure_ascii=False))

rv = c.get("/access/table/resolve", params={"code": TABLE, "token": MOBILE})
print("GET /access/table/resolve?code=%s -> %s" % (TABLE, rv.status_code))
print(json.dumps(rv.json(), ensure_ascii=False, indent=2))

g = c.post("/api/campaigns/%s/npc/%s/generate" % (CAMPAIGN, NPC), headers=KP,
           json={"trigger": "玩家询问闭馆那晚", "player_id": "pl-001"})
print("POST /npc/generate ->", g.status_code, json.dumps(g.json(), ensure_ascii=False))

prop = g.json().get("proposal", {})
print("RESULT=" + json.dumps({"table": TABLE, "campaign": CAMPAIGN, "npc": NPC,
                              "proposal_id": prop.get("proposal_id"),
                              "candidate": prop.get("line"), "edit": EDIT,
                              "mobile_token": MOBILE, "kp_token": TOK["webapp"],
                              "base": BASE}, ensure_ascii=False))
