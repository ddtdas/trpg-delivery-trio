# -*- coding: utf-8 -*-
"""只读：/app/assets/ 的 served 响应头 + 与磁盘对比（R32 theme 陈旧风险复核）。"""
from __future__ import annotations
import hashlib, httpx
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
c = httpx.Client(base_url="http://127.0.0.1:9211", timeout=20)

print("=== served 响应 vs 磁盘（R32 主题与构建资产）===")
for p in ["/app/assets/theme-cnmods.css", "/app/assets/index-DAU2_EXr.css", "/app/assets/index-DsfUF84T.js"]:
    r = c.get(p)
    disk = SRV / "web" / "dist" / p.replace("/app/", "")
    dhash = hashlib.sha256(disk.read_bytes()).hexdigest() if disk.is_file() else "-"
    print("  %-36s %s len=%-7s cc=%-22s disk_sha=%s" % (
        p, r.status_code, r.headers.get("content-length", "-"),
        r.headers.get("cache-control", "**缺失**"), dhash[:16]))

print("")
print("=== index.html 的引用（是否有 hash）===")
ix = SRV / "web" / "dist" / "index.html"
txt = ix.read_text(encoding="utf-8")
print("  dist/index.html 大小 =", len(txt.encode()), "B")
for line in txt.splitlines():
    s = line.strip()
    if "theme" in s or "stylesheet" in s or "script" in s:
        print("   ", s[:160])

print("")
print("=== 主题文件全包定位（找 8732 与 9568 两个字节数）===")
for p in sorted((SRV / "web").rglob("*theme*")):
    if p.is_file():
        b = p.read_bytes()
        print("  %-58s %6d B  %s" % (str(p.relative_to(SRV)), len(b), hashlib.sha256(b).hexdigest()[:16]))
for p in sorted((SRV).rglob("*cnmods*")):
    if p.is_file():
        b = p.read_bytes()
        print("  %-58s %6d B  %s" % (str(p.relative_to(SRV)), len(b), hashlib.sha256(b).hexdigest()[:16]))
