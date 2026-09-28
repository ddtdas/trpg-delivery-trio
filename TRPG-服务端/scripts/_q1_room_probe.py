# -*- coding: utf-8 -*-
"""① /npc/state 现值复核；② 事件图节点是否带房间/位置信息（判断 room 能否落地）。"""
import glob, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import httpx, yaml

CFG = yaml.safe_load((ROOT / "configs" / "access_config.yaml").read_text(encoding="utf-8"))
KP = {"Authorization": "Bearer " + str((CFG.get("ends") or {}).get("webapp", {}).get("token") or "")}
c = httpx.Client(base_url="http://127.0.0.1:9211", timeout=20.0)
r = c.get("/api/campaigns/c_r2npc/npc/state", headers=KP)
j = r.json()
print("GET /npc/state -> %d len=%d" % (r.status_code, len(r.content)))
print("keys =", sorted(j.keys()))
print("npc_meta =", json.dumps(j.get("npc_meta"), ensure_ascii=False))
print("")
print("=== event_graph.yaml 节点结构（看有没有 room/location）===")
for p in sorted(glob.glob(str(ROOT / "modules" / "*" / "event_graph.yaml"))):
    d = yaml.safe_load(open(p, encoding="utf-8")) or {}
    print(os.path.basename(os.path.dirname(p)), "-> top keys:", list(d.keys()))
    nodes = d.get("nodes") or d.get("events") or []
    if isinstance(nodes, list) and nodes:
        print("   node[0] keys:", sorted(nodes[0].keys()) if isinstance(nodes[0], dict) else type(nodes[0]))
        print("   node[0]:", json.dumps(nodes[0], ensure_ascii=False)[:300])
    elif isinstance(nodes, dict) and nodes:
        k0 = list(nodes)[0]
        print("   node[%s] keys:" % k0, sorted(nodes[k0].keys()))
    break
print("")
print("=== 全部模块 yaml 里出现 room/location/场景 字样的键 ===")
hits = []
for p in glob.glob(str(ROOT / "modules" / "**" / "*.yaml"), recursive=True):
    try:
        d = yaml.safe_load(open(p, encoding="utf-8")) or {}
    except Exception:
        continue
    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).lower() in ("room", "location", "scene", "area", "map_id", "room_id"):
                    hits.append((os.path.relpath(p, ROOT), path + "/" + str(k)))
                walk(v, path + "/" + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o[:3]):
                walk(v, path + "[%d]" % i)
    walk(d)
for h in hits[:30]:
    print("  ", h[0], "->", h[1])
print("  total:", len(hits))
