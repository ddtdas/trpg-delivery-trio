# -*- coding: utf-8 -*-
"""T14-② proposal_id 不透明性 + 广播面身份检查（只读）。"""
import json, re, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.npc.director import _new_proposal_id

ids = [_new_proposal_id() for _ in range(12)]
print("sampled_proposal_ids =", ids)
bad = [i for i in ids if not re.fullmatch(r"npcprop_[0-9a-f]{12}", i)]
print("non_opaque_count =", len(bad), bad)
print("contains_identity_substring =",
      any(s in i for i in ids for s in ("npc_clerk", "npc_martha", "pl-001", "pl_001", "c_", "room", "kp")))

con = sqlite3.connect(str(ROOT / "data" / "trpg.db"))
rows = con.execute("select campaign_id, payload from events where type='NPC_ACT_PROPOSED'"
                   " order by seq desc limit 3").fetchall()
print("")
print("=== 广播面（事件流）NPC_ACT_PROPOSED payload 实样 ===")
for camp, pay in rows:
    try:
        d = json.loads(pay)
    except Exception:
        d = {"_raw": pay[:200]}
    print(camp, "->", json.dumps(d, ensure_ascii=False))
    print("   keys =", sorted(d.keys()))
    print("   lines_is_empty =", d.get("lines") == [])

# 广播帧：玩家侧实际拿到的是什么
rows2 = con.execute("select campaign_id, payload from events where type='NPC_ACT_APPROVED'"
                    " order by seq desc limit 2").fetchall()
print("")
print("=== NPC_ACT_APPROVED payload 实样（批准后才下发）===")
for camp, pay in rows2:
    try:
        d = json.loads(pay)
    except Exception:
        d = {"_raw": pay[:200]}
    print(camp, "->", json.dumps(d, ensure_ascii=False)[:300])
