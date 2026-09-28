# -*- coding: utf-8 -*-
"""只读：条件请求（If-None-Match / If-Modified-Since）在两类服务路径上是否回 304。"""
from __future__ import annotations
import httpx

c = httpx.Client(base_url="http://127.0.0.1:9211", timeout=20)

def probe(path: str, label: str) -> None:
    r = c.get(path)
    et = r.headers.get("etag")
    lm = r.headers.get("last-modified")
    cc = r.headers.get("cache-control", "【缺失】")
    print("  %s" % label)
    print("     GET            -> %s  len=%s  cc=%s" % (r.status_code, r.headers.get("content-length"), cc))
    print("     etag=%s  last-modified=%s" % (et, lm))
    r2 = c.get(path, headers={"If-None-Match": et} if et else {})
    print("     If-None-Match  -> %s   (304 表示服务端支持回源校验)" % r2.status_code)
    if lm:
        r3 = c.get(path, headers={"If-Modified-Since": lm})
        print("     If-Modified-Since -> %s" % r3.status_code)
    print("")

print("=== A. StaticFiles 挂载（/app/assets/*）===")
probe("/app/assets/theme-cnmods.css", "theme-cnmods.css（未加头，未哈希）")
probe("/app/assets/index-DsfUF84T.js", "index-DsfUF84T.js（有哈希）")

print("=== B. 我手写 FileResponse（/player/*）===")
probe("/player/strings.json", "strings.json（我加了 no-cache）")
probe("/player/app.js", "app.js（我加了 no-cache）")

print("=== C. SPA 入口 ===")
probe("/app/", "/app/ index.html（我加了 no-cache）")
