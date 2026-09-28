# -*- coding: utf-8 -*-
"""定位 R9 role 降级的全部实现点（语义搜索，而非精确串）。"""
from __future__ import annotations
import re, time
from pathlib import Path
SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
FILES = ["app/main.py", "app/web/rest.py", "app/web/ws.py", "app/web/access.py",
         "app/web/ws_bridge.py", "app/web/ws_protocol.py"]
print("=== 所有含 'webapp' 且同行/邻行含 role 的位置 ===")
for rel in FILES:
    p = SRV / rel
    if not p.is_file():
        print("  %-24s MISSING" % rel); continue
    lines = p.read_text(encoding="utf-8").splitlines()
    hits = []
    for i, ln in enumerate(lines):
        if "webapp" in ln and "role" in ln.lower():
            hits.append((i + 1, ln.strip()))
        elif "webapp" in ln:
            ctx = " ".join(lines[max(0, i - 2):i + 3])
            if "role" in ctx.lower():
                hits.append((i + 1, ln.strip()))
    mt = time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
    print("  %-24s mtime=%s  hits=%d" % (rel, mt, len(hits)))
    for n, t in hits:
        print("      L%-4d %s" % (n, t[:150]))

print("")
print("=== main.py 里 role 降级段落（L100-120 上下文）===")
lines = (SRV / "app/main.py").read_text(encoding="utf-8").splitlines()
for i in range(98, min(len(lines), 122)):
    print("  L%-4d %s" % (i + 1, lines[i]))

print("")
print("=== main.py 全文里 'role' 出现处 ===")
for i, ln in enumerate(lines):
    if "role" in ln.lower():
        print("  L%-4d %s" % (i + 1, ln.strip()[:150]))
