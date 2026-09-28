# -*- coding: utf-8 -*-
"""独立复核 realtime 的「ws npc_guard 结构性不可达」结论。只读。"""
from __future__ import annotations
import hashlib, re, time
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")

P = SRV / "app" / "web" / "ws_protocol.py"
W = SRV / "app" / "web" / "ws.py"
for p in (P, W):
    b = p.read_bytes()
    print("%-28s %6d B  cr=%d  %s  mtime=%s" % (p.name, len(b), b.count(b"\r"),
          hashlib.sha256(b).hexdigest(), time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))

pt = P.read_text(encoding="utf-8")
print("")
print("=== ws_protocol.py: CLIENT_KINDS 定义 ===")
i = pt.find("CLIENT_KINDS")
print(pt[max(0, i - 320):i + 260])

print("")
print("=== ws_protocol.py: 是否有 NPC_ACT ===")
print("  'NPC_ACT' 出现次数 =", pt.count("NPC_ACT"))
print("  'unknown client kind' 出现次数 =", pt.count("unknown client kind"))

wt = W.read_text(encoding="utf-8")
print("")
print("=== ws.py: npc_guard 引用点 ===")
for i, ln in enumerate(wt.splitlines(), 1):
    if "npc_guard" in ln:
        print("  L%-4d %s" % (i, ln.strip()[:120]))
print("  'NPC_ACT' 出现次数 =", wt.count("NPC_ACT"))

print("")
print("=== 全 app/ 内 npc_guard 引用 ===")
tot = 0
for p in (SRV / "app").rglob("*.py"):
    t = p.read_text(encoding="utf-8", errors="replace")
    n = t.count("npc_guard")
    if n:
        tot += n
        print("  %-42s x%d" % (str(p.relative_to(SRV)), n))
print("  合计 =", tot)
