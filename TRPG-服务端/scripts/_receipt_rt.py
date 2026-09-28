# -*- coding: utf-8 -*-
"""回执 implementer-realtime：① 回滚点位置 ② role 降级是否在已加载文件里 ③ npc 路由条数。"""
from __future__ import annotations
import glob, hashlib, json, os, time
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
SRV = PKG / "TRPG-服务端"
RB = Path(r"C:\_r2npc_stage\rollback")

print("=== ① 我的回滚点：在交付树【之外】(刻意，见 T3-D1) ===")
print("目录:", RB, "存在=", RB.is_dir())
if RB.is_dir():
    for p in sorted(RB.iterdir()):
        if p.is_file():
            b = p.read_bytes()
            print("  %-58s %7d B  %s  mtime=%s" % (p.name, len(b), hashlib.sha256(b).hexdigest(),
                  time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))

print("")
print("=== ② 交付包内 .bak 统计（刻意的：不污染交付物）===")
allbak = [p for p in PKG.rglob("*") if p.is_file() and ".bak" in p.name]
print("  .bak-r2npc 数量 =", len([p for p in allbak if p.name.endswith(".bak-r2npc")]))
print("  其余 .bak* 数量 =", len([p for p in allbak if not p.name.endswith(".bak-r2npc")]))
for p in allbak:
    print("   ", p.relative_to(PKG), p.stat().st_size, "B")

print("")
print("=== ③ role 降级是否在【已加载】的文件里（决定 main.py 待加载是否要紧）===")
NEEDLES = ['token_end_name(token) != "webapp"', 'role = "pl"', "def resolve_viewer", "def token_end_name"]
for rel in ["app/main.py", "app/web/rest.py", "app/web/ws.py", "app/web/access.py"]:
    p = SRV / rel
    if not p.is_file():
        print("  %-24s MISSING" % rel); continue
    t = p.read_text(encoding="utf-8")
    mt = time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
    print("  %-24s mtime=%s  %s" % (rel, mt, {n: t.count(n) for n in NEEDLES}))

print("")
print("=== ④ 线上 npc 路由条数（openapi.json，只读）===")
import httpx
d = httpx.get("http://127.0.0.1:9211/openapi.json", timeout=20).json()
ps = sorted(p for p in d["paths"] if "/npc" in p)
print("  含 /npc 的路径数 =", len(ps))
for p in ps:
    print("   ", p, sorted(d["paths"][p].keys()))
