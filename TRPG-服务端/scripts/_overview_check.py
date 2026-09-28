# -*- coding: utf-8 -*-
"""只读：① 复核 theme 两个文件的现场真值 ② 复核 /overview 是否真的交付（不被 SPA 兜底骗）。"""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path
import httpx

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
def info(p: Path):
    b = p.read_bytes()
    return "%7d B  cr=%-3d %s  mtime=%s" % (len(b), b.count(b"\r"), hashlib.sha256(b).hexdigest(),
            time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)))

print("=== ① theme 两文件现场真值（gmui 报 8732/8732）===")
for p in [SRV/"web"/"dist"/"assets"/"theme-cnmods.css", SRV/"web"/"public"/"assets"/"theme-cnmods.css"]:
    print("  %-46s %s" % (str(p.relative_to(SRV)), info(p) if p.is_file() else "MISSING"))
print("  dist/assets / public/assets 目录全清单:")
for d in [SRV/"web"/"dist"/"assets", SRV/"web"/"public"/"assets"]:
    for f in sorted(d.iterdir()) if d.is_dir() else []:
        if f.is_file():
            print("    %-52s %s" % (str(f.relative_to(SRV)), info(f)))
print("  /app/assets/theme-cnmods.css  served:")
try:
    r = httpx.get("http://127.0.0.1:9211/app/assets/theme-cnmods.css", timeout=10)
    print("    HTTP %s  len=%s  cc=%s" % (r.status_code, r.headers.get("content-length"), r.headers.get("cache-control", "缺失")))
    print("    served sha256 =", hashlib.sha256(r.content).hexdigest())
except Exception as e:
    print("    FAILED", e)

print("")
print("=== ② 构建产物：index.html 引用 vs dist 实际文件 ===")
ix = SRV/"web"/"dist"/"index.html"
print("  index.html %s" % info(ix))
print("  引用:", [s.strip() for s in ix.read_text(encoding="utf-8").splitlines() if "assets/" in s])

print("")
print("=== ③ overview 路由是否真的存在（不看 200，看代码与服务端数据）===")
bundle = (SRV/"web"/"dist"/"assets"/"index-DsfUF84T.js").read_text(encoding="utf-8", errors="replace")
for kw in ["overview", "/overview", "GM 总览", "map_library", "blockCount"]:
    print("  bundle 中含 %-14s : %d 次" % (kw, bundle.count(kw)))
print("  bundle 中 overview 附近的片段:")
i = bundle.find("overview")
while i != -1 and i < len(bundle):
    print("    ...%s..." % bundle[max(0,i-90):i+110].replace("\n"," "))
    i = bundle.find("overview", i+1)
    if bundle.count("overview") > 6: break

print("")
print("=== ④ 服务端 overview API（openapi）===")
try:
    spec = httpx.get("http://127.0.0.1:9211/openapi.json", timeout=20).json()
    paths = sorted(spec.get("paths", {}))
    print("  overview 相关路径:", [p for p in paths if "overview" in p.lower()] or "（无）")
    print("  全部路径数 =", len(paths))
except Exception as e:
    print("  openapi FAILED", e)
