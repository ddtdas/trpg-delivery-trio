# -*- coding: utf-8 -*-
"""核查 gmui 的 I8c 形态：?cb= 缓存旁路 vs 无旁路，看头与状态。"""
from __future__ import annotations
import hashlib, httpx

c = httpx.Client(base_url="http://127.0.0.1:9211", timeout=20)
P = "/app/assets/theme-cnmods.css"

print("=== A. I8c 的取法（带 ?cb= 随机旁路）===")
r = c.get(P + "?cb=probe123")
print("   GET %-42s -> %s len=%s cc=%s" % (P + "?cb=probe123", r.status_code, r.headers.get("content-length"), r.headers.get("cache-control", "【缺失】")))
print("   sha256(served) =", hashlib.sha256(r.content).hexdigest())

print("")
print("=== B. 浏览器真正会请求的 URL（index.html 里那个，无旁路）===")
r2 = c.get(P)
print("   GET %-42s -> %s len=%s cc=%s" % (P, r2.status_code, r2.headers.get("content-length"), r2.headers.get("cache-control", "【缺失】")))
print("   sha256(served) =", hashlib.sha256(r2.content).hexdigest())
print("   etag=%s  last-modified=%s" % (r2.headers.get("etag"), r2.headers.get("last-modified")))

print("")
print("=== C. 关键点：两次内容相同 => I8c 在有/无旁路时【结论完全一样】===")
print("   同内容 =", r.content == r2.content)

print("")
print("=== D. 用陈旧 ETag 复现「客户端缓存仍生效」的判定 ===")
et = r2.headers.get("etag")
r3 = c.get(P, headers={"If-None-Match": et})
print("   无旁路 + If-None-Match(当前 etag) ->", r3.status_code, "(304 => 客户端不会重下，仍用本地那份)")
r4 = c.get(P, headers={"If-None-Match": '"STALE-OLD-ETAG"'})
print("   无旁路 + If-None-Match(陈旧 etag) ->", r4.status_code, "(200 => 会重下)")
print("   带旁路 + If-None-Match(陈旧 etag) ->", c.get(P + "?cb=x", headers={"If-None-Match": '"STALE-OLD-ETAG"'}).status_code, "(200，因为 URL 换了，缓存必然未命中)")
