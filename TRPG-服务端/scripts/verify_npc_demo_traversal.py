# -*- coding: utf-8 -*-
"""路径穿越实测（httpx 不做路径归一化，才能测到真穿越）。"""
import httpx
c = httpx.Client(base_url="http://127.0.0.1:9211", timeout=20.0)
CASES = [
    "/npc-demo/index.html",
    "/npc-demo/does-not-exist.html",
    "/npc-demo/%2e%2e/app/main.py",
    "/npc-demo/..%2fapp%2fmain.py",
    "/npc-demo/%2e%2e%2f%2e%2e%2fconfigs/access_config.yaml",
    "/npc-demo/....//app/main.py",
]
for u in CASES:
    try:
        r = c.get(u)
        body = r.text[:80].replace("\n", " ")
        print("%-52s -> %d len=%-6d %s" % (u, r.status_code, len(r.content), body))
    except Exception as exc:
        print("%-52s -> EXC %s" % (u, exc))
print("")
print("对照：既有 /app 路由同样行为（不属于本次改动）")
for u in ["/app/does-not-exist.js", "/player/does-not-exist.js"]:
    r = c.get(u)
    print("%-52s -> %d len=%d" % (u, r.status_code, len(r.content)))
