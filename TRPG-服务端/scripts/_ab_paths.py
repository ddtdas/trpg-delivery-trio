# -*- coding: utf-8 -*-
"""复核 gmui 的 ② 更正：A 路径(StaticFiles) vs B 路径(手写 FileResponse) 的 304 能力。"""
from __future__ import annotations
import urllib.request, urllib.error

def probe(path, extra=None, label=""):
    h = dict(extra or {})
    req = urllib.request.Request("http://127.0.0.1:9211" + path, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
            cc = r.headers.get("Cache-Control", "【缺失】")
            et = r.headers.get("ETag", "-")
            lm = r.headers.get("Last-Modified", "-")
            return "%s %-42s %s len=%-7d cc=%-10s etag=%s" % (label, path, r.status, len(body), cc, ("有" if et != "-" else "无"))
    except urllib.error.HTTPError as e:
        return "%s %-42s %s len=0       cc=%s" % (label, path, e.code, e.headers.get("Cache-Control", "【缺失】"))

print("=== 无条件请求（基线）===")
for p in ["/app/", "/app/assets/theme-cnmods.css", "/app/assets/index-DsfUF84T.js", "/player/", "/player/app.js"]:
    print("  " + probe(p))
print("")
print("=== 条件请求 1：先取 ETag/Last-Modified，再带 If-None-Match（判 304 能力）===")
for p in ["/app/", "/app/assets/theme-cnmods.css", "/app/assets/index-DsfUF84T.js", "/player/", "/player/app.js"]:
    req = urllib.request.Request("http://127.0.0.1:9211" + p)
    with urllib.request.urlopen(req, timeout=15) as r:
        et = r.headers.get("ETag"); lm = r.headers.get("Last-Modified"); r.read()
    h = {}
    if et:
        h["If-None-Match"] = et
    elif lm:
        h["If-Modified-Since"] = lm
    print("  " + probe(p, h, label="[cond]"))

print("")
print("=== 结论 ===")
print("  A 路径 = StaticFiles 挂载 /app/assets/*     -> 支持 304")
print("  B 路径 = 手写 FileResponse /app/ 与 /player/* -> 不支持 304（条件请求仍 200 全量）")
