# -*- coding: utf-8 -*-
"""紧急：Plan A 补丁是否还在？app.js 为何从 48659 变 48818？镜像是否破裂？"""
from __future__ import annotations
import hashlib, json, time, urllib.request
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
SRV = PKG / "TRPG-服务端"

sp = SRV / "app" / "web" / "static.py"
b = sp.read_bytes()
print("=== app/web/static.py 现状 ===")
print("  %d B  sha256=%s" % (len(b), hashlib.sha256(b).hexdigest()))
print("  mtime=%s" % time.strftime("%m-%d %H:%M:%S", time.localtime(sp.stat().st_mtime)))
print("  CR=%d  'NO_CACHE' 出现 %d 次  'no-cache' 出现 %d 次" % (
    b.count(b"\r"), b.count(b"NO_CACHE"), b.count(b"no-cache")))
print("  Plan A 判定:", "【仍在】" if b.count(b"NO_CACHE") >= 5 else "【已被覆盖/回退】")

print("")
print("=== 线上响应头（Plan A 覆盖的路径）===")
for path in ["/player/", "/player/app.js", "/player/strings.json", "/app/", "/npc-demo/"]:
    try:
        req = urllib.request.Request("http://127.0.0.1:9211" + path)
        with urllib.request.urlopen(req, timeout=15) as r:
            print("  %-22s %s len=%-7d Cache-Control=%s" % (
                path, r.status, len(r.read()), r.headers.get("Cache-Control", "【缺失】")))
    except Exception as e:
        print("  %-22s ERR %s" % (path, e))

print("")
print("=== 镜像：player-web/app.js vs client/app.js ===")
for rel in ["TRPG-服务端/player-web/app.js", "TRPG-Web客户端/client/app.js"]:
    p = PKG / rel
    bb = p.read_bytes()
    print("  %-40s %7d B cr=%d sha=%s mtime=%s" % (
        rel, len(bb), bb.count(b"\r"), hashlib.sha256(bb).hexdigest()[:16],
        time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))
a = (PKG / "TRPG-服务端/player-web/app.js").read_bytes()
c = (PKG / "TRPG-Web客户端/client/app.js").read_bytes()
print("  逐字节相同 =", a == c)

print("")
print("=== 线上 /player/app.js 与磁盘是否一致 ===")
with urllib.request.urlopen("http://127.0.0.1:9211/player/app.js", timeout=15) as r:
    live = r.read()
print("  线上 %d B sha=%s" % (len(live), hashlib.sha256(live).hexdigest()[:16]))
print("  磁盘 %d B sha=%s" % (len(a), hashlib.sha256(a).hexdigest()[:16]))
print("  一致 =", live == a)
