# -*- coding: utf-8 -*-
"""复核 gmui 提到的行尾问题（app/main.py）与三端 strings 当前值。只读。"""
from __future__ import annotations
import hashlib, time
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
PKG = SRV.parent

print("=== app/main.py 行尾复核（gmui 自报曾插入 3 行裸 LF 并已还原）===")
for rel in ["app/main.py", "app/web/rest.py", "app/web/static.py", "app/npc/director.py", "app/npc/routes.py"]:
    p = SRV / rel
    b = p.read_bytes()
    cr, lf = b.count(b"\r"), b.count(b"\n")
    crlf = b.count(b"\r\n")
    lone_lf = lf - crlf
    lone_cr = cr - crlf
    verdict = "纯 CRLF" if (lone_lf == 0 and lone_cr == 0 and crlf > 0) else \
              ("纯 LF" if (cr == 0) else "**混合/异常**")
    print("  %-22s cr=%-4d lf=%-4d crlf=%-4d lone_lf=%-3d lone_cr=%-3d  %s  mtime=%s" % (
        rel, cr, lf, crlf, lone_lf, lone_cr, verdict,
        time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))

print("")
print("=== 三端 strings 当前值（现场复算）===")
for name, p in (("svc/player-web", PKG / "TRPG-服务端" / "player-web" / "strings.json"),
                ("web/client",     PKG / "TRPG-Web客户端" / "client" / "strings.json"),
                ("miniprogram",    PKG / "TRPG-微信小程序客户端" / "strings.json"),
                ("miniprogram js", PKG / "TRPG-微信小程序客户端" / "strings.js")):
    b = p.read_bytes()
    import json, re
    if p.suffix == ".json":
        n = len(json.loads(b.decode("utf-8")))
    else:
        n = len(re.findall(r'^\s*"([^"]+)":', b.decode("utf-8"), flags=re.M))
    print("  %-15s %6d B  cr=%d  keys=%-4d  %s  mtime=%s" % (
        name, len(b), b.count(b"\r"), n, hashlib.sha256(b).hexdigest(),
        time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))

print("")
print("=== /npc-demo 静态页路径（供 gmui 跑 r2_dist_integrity.ps1）===")
for p in sorted((SRV / "npc-demo").rglob("*")):
    if p.is_file():
        b = p.read_bytes()
        print("  %-46s %6d B  cr=%d  %s" % (str(p.relative_to(SRV)), len(b), b.count(b"\r"),
              hashlib.sha256(b).hexdigest()))
print("  mount: app/web/static.py -> demo_dir = APP_ROOT / 'npc-demo'; routes /npc-demo, /npc-demo/, /npc-demo/{path}")
