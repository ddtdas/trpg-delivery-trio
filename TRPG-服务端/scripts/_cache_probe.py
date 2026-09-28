# -*- coding: utf-8 -*-
"""实测 /player/ 与 /app/ 静态响应的缓存头（pipeline 报的验收风险）。只读。"""
from __future__ import annotations
import httpx, re
from pathlib import Path

B = "http://127.0.0.1:9211"
c = httpx.Client(base_url=B, timeout=20, follow_redirects=False)

print("=== /player/ 关键资源的响应头 ===")
for path in ["/player/", "/player/index.html", "/player/app.js", "/player/strings.json", "/player/app.css"]:
    try:
        r = c.get(path)
        h = {k.lower(): v for k, v in r.headers.items()}
        print("  %-24s %s  len=%-7s etag=%-18s lastmod=%-30s cachectl=%s" % (
            path, r.status_code, h.get("content-length", "-"), (h.get("etag", "-") or "-")[:18],
            (h.get("last-modified", "-") or "-")[:30], h.get("cache-control", "**缺失**")))
    except Exception as exc:
        print("  %-24s FAILED %s" % (path, exc))

print("")
print("=== index.html 里 app.js / strings 的引用方式（有无版本串）===")
try:
    html = c.get("/player/index.html").text
    for m in re.finditer(r'<(script|link)[^>]*(src|href)="([^"]+)"', html):
        print("   ", m.group(0)[:150])
except Exception as exc:
    print("   FAILED", exc)

print("")
print("=== strings.json 是运行时 fetch 还是打包进 JS？ ===")
for f in ["/player/app.js"]:
    try:
        js = c.get(f).text
        for kw in ["strings.json", "fetch(", "STRINGS", "i18n"]:
            print("   %-16s in %s -> x%d" % (kw, f, js.count(kw)))
    except Exception as exc:
        print("   FAILED", exc)

print("")
print("=== /app/ 构建产物的缓存头（对照）===")
for path in ["/app/", "/app/assets/index-BUCDjFsz.js"]:
    try:
        r = c.get(path)
        h = {k.lower(): v for k, v in r.headers.items()}
        print("  %-34s %s  len=%-7s cachectl=%s" % (path, r.status_code, h.get("content-length", "-"),
              h.get("cache-control", "**缺失**")))
    except Exception as exc:
        print("  %-34s FAILED %s" % (path, exc))

print("")
print("=== 本机是否有 strings.json 的版本串引用（player-web/index.html）===")
P = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\player-web\index.html")
t = P.read_text(encoding="utf-8")
for m in re.finditer(r'<(script|link)[^>]*>', t):
    print("   ", m.group(0)[:150])
print("   'strings' 出现次数 =", t.count("strings"))
