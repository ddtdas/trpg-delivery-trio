# -*- coding: utf-8 -*-
"""Q1 验收：/npc/state 新增 npc_meta；既有字段零变化。"""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import httpx, yaml

BASE = "http://127.0.0.1:9211"
CFG = yaml.safe_load((ROOT / "configs" / "access_config.yaml").read_text(encoding="utf-8"))
KP = {"Authorization": "Bearer " + str((CFG.get("ends") or {}).get("webapp", {}).get("token") or "")}
c = httpx.Client(base_url=BASE, timeout=30.0)

for camp in ("c_r2npc", "c_r2npc_0926214912"):
    r = c.get("/api/campaigns/%s/npc/state" % camp, headers=KP)
    print("GET /api/campaigns/%s/npc/state -> %d len=%d" % (camp, r.status_code, len(r.content)))
    if r.status_code != 200:
        print("   ", r.text[:200]); continue
    j = r.json()
    print("   既有键(必须全在) =", sorted(j.keys()))
    print("   npc_meta =", json.dumps(j.get("npc_meta"), ensure_ascii=False))
    print("   tip =", j.get("tip"), " pending_count =", j.get("pending_count"))
    print("   player_visible_lines keys =", sorted((j.get("player_visible_lines") or {}).keys()))

print("")
print("=== 玩家读口 /npc/lines 必须**不含** npc_meta / name（卡数据不外泄）===")
r = c.get("/api/campaigns/c_r2npc/npc/lines")
print("GET /npc/lines (无鉴权) -> %d  keys=%s" % (r.status_code, sorted(r.json().keys())))
print("含 npc_meta =", "npc_meta" in r.json())

print("")
print("=== 未知名 npc_id 走 has_card=False 分支（不 500）===")
from app.npc.director import npc_meta
print(json.dumps(npc_meta(["npc_clerk", "npc_does_not_exist", "*", ""]), ensure_ascii=False, indent=1))
