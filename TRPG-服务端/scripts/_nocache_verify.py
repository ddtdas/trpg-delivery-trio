# -*- coding: utf-8 -*-
"""重启后验证：Cache-Control: no-cache 是否生效 + 回归。只读。"""
from __future__ import annotations
import httpx

B = "http://127.0.0.1:9211"
c = httpx.Client(base_url=B, timeout=20, follow_redirects=False)

print("=== 队长要求 3：原始响应头（证明 Cache-Control: no-cache 生效）===")
for path in ["/player/app.js", "/player/strings.json", "/app/"]:
    r = c.get(path)
    print("")
    print("GET %s  ->  HTTP %d" % (path, r.status_code))
    for k, v in r.headers.items():
        print("    %s: %s" % (k, v))

print("")
print("=== 其余静态路径同样核对 ===")
for path in ["/player/", "/player/index.html", "/player/app.css", "/app", "/npc-demo/", "/npc-demo/index.html"]:
    r = c.get(path)
    print("  %-24s %s  len=%-7s cache-control=%s" % (
        path, r.status_code, r.headers.get("content-length", "-"), r.headers.get("cache-control", "**缺失**")))

print("")
print("=== 队长要求 4：回归四项 ===")
for path in ["/player/", "/app/", "/npc-demo/", "/api/health"]:
    r = c.get(path)
    print("  %-16s -> %s   len=%s" % (path, r.status_code, r.headers.get("content-length", "-")))

print("")
print("=== 内容正确性抽查（三端 strings 与镜像）===")
r = c.get("/player/strings.json")
print("  /player/strings.json len=%s  (期望 3522)" % r.headers.get("content-length"))
r2 = c.get("/player/app.js")
print("  /player/app.js      len=%s  (期望 48659)" % r2.headers.get("content-length"))

print("")
print("=== 304 回源校验实测（no-cache 应带 ETag 回源；命中则 304）===")
r3 = c.get("/player/strings.json")
et = r3.headers.get("etag")
print("  first  etag =", et)
r4 = c.get("/player/strings.json", headers={"If-None-Match": et})
print("  second (If-None-Match) ->  HTTP %d  (期望 304)" % r4.status_code)
print("  second cache-control =", r4.headers.get("cache-control", "**缺失**"))

print("")
print("=== 未加头的对照：/app/assets（StaticFiles 挂载，未改动）===")
for path in ["/app/assets/theme-cnmods.css", "/app/assets/index-DsfUF84T.js"]:
    r5 = c.get(path)
    print("  %-38s %s  cache-control=%s" % (path, r5.status_code, r5.headers.get("cache-control", "**缺失（仍未加头）**")))
