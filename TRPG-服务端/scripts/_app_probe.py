# -*- coding: utf-8 -*-
"""核查 /app/ 构建产物的真实资源名（gmui 报 index-BUCDjFsz.js 200，我实测 404）。只读。"""
from __future__ import annotations
import re
import httpx

B = "http://127.0.0.1:9211"
c = httpx.Client(base_url=B, timeout=20, follow_redirects=False)

r = c.get("/app/")
print("GET /app/ ->", r.status_code, "len =", len(r.text))
html = r.text
refs = re.findall(r'(?:src|href)="([^"]+)"', html)
print("引用资源:", refs)
print("")
print("--- /app/ HTML 全文 ---")
print(html)

print("")
print("=== 逐个探测引用资源 ===")
for ref in refs:
    path = ref if ref.startswith("/") else "/app/" + ref.lstrip("./")
    try:
        rr = c.get(path)
        print("  %-46s %s  len=%s" % (path, rr.status_code, rr.headers.get("content-length", "-")))
    except Exception as exc:
        print("  %-46s FAILED %s" % (path, exc))

print("")
print("=== keeper-ui 与 assets 目录可达性 ===")
for path in ["/app/keeper-ui/index.html", "/app/assets/", "/app/theme.css", "/app/dist/"]:
    try:
        rr = c.get(path)
        print("  %-46s %s  len=%s" % (path, rr.status_code, rr.headers.get("content-length", "-")))
    except Exception as exc:
        print("  %-46s FAILED %s" % (path, exc))
