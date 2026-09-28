# -*- coding: utf-8 -*-
"""行尾审计：对比当前文件与其 r2npc 回滚点的 CR / LF / 行数。只读。"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT.parent
RB = Path(r"C:\_r2npc_stage\rollback")

PAIRS = [
    ("app/mcp/auth.py", "TRPG-服务端__app_mcp_auth.py.bak-r2npc"),
    ("app/mcp/schemas.py", "TRPG-服务端__app_mcp_schemas.py.bak-r2npc"),
    ("app/mcp/server.py", "TRPG-服务端__app_mcp_server.py.bak-r2npc"),
    ("app/web/rest.py", "TRPG-服务端__app_web_rest.py.bak-r2npc"),
    ("app/web/ws.py", "TRPG-服务端__app_web_ws.py.bak-r2npc"),
    ("app/main.py", "TRPG-服务端__app_main.py.bak-r2npc"),
    ("player-web/strings.json", "TRPG-服务端__player-web_strings.json.bak-r2npc"),
]


def stat(p: Path):
    b = p.read_bytes()
    cr = b.count(b"\r")
    lf = b.count(b"\n")
    crlf = b.count(b"\r\n")
    return dict(size=len(b), cr=cr, lf=lf, crlf=crlf, lone_lf=lf - crlf,
                style=("CRLF" if crlf == lf and crlf > 0 else ("LF" if cr == 0 else "MIXED")))


print("%-26s %-28s %-28s" % ("file", "now", "before(rollback)"))
print("-" * 90)
rows = []
for rel, bak in PAIRS:
    cur = ROOT / rel
    old = RB / bak
    if not cur.exists():
        print("%-26s MISSING" % rel); continue
    s_now = stat(cur)
    s_old = stat(old) if old.exists() else None
    f = lambda s: "size=%d cr=%d lf=%d crlf=%d lone=%d %s" % (s["size"], s["cr"], s["lf"], s["crlf"], s["lone_lf"], s["style"]) if s else "(no backup)"
    print("%-26s %-28s %-28s" % (rel, f(s_now), f(s_old)))
    rows.append((rel, s_now, s_old))

print("")
print("=== 其他我改/新建的文件（无回滚点可比，只报当前风格）===")
OTHERS = ["docs/R2-NPC-CONTRACT-CHANGE.md", "app/npc/__init__.py", "app/npc/skills.py",
          "app/npc/memory.py", "app/npc/director.py", "app/npc/routes.py",
          "scripts/patch_r2npc.py", "scripts/patch_r2npc_ws.py", "scripts/patch_r2npc_ws2.py",
          "scripts/patch_r2npc_mcp.py", "scripts/patch_t14_doc.py",
          "scripts/verify_npc_r28_r31.py", "scripts/verify_npc_ws_guard.py",
          "scripts/verify_mcp_npc_act.py", "scripts/_t14_probe.py"]
for rel in OTHERS:
    p = ROOT / rel
    if p.exists():
        s = stat(p)
        print("%-40s cr=%-5d lf=%-5d lone_lf=%-5d %s" % (rel, s["cr"], s["lf"], s["lone_lf"], s["style"]))
    else:
        print("%-40s MISSING" % rel)

print("")
print("=== 参考：未被我碰过的同类文件（包内基线风格）===")
for rel in ["app/web/access.py", "app/web/ws_protocol.py", "app/domain/events.py",
            "docs/CROSS-END-CONTRACT.md", "scripts/_serve.py", "player-web/app.js",
            "player-web/index.html"]:
    p = ROOT / rel
    if p.exists():
        s = stat(p)
        print("%-40s cr=%-5d lf=%-5d lone_lf=%-5d %s" % (rel, s["cr"], s["lf"], s["lone_lf"], s["style"]))
