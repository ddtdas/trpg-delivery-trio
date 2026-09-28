# -*- coding: utf-8 -*-
"""诊断 modules/index.json 的 dead_light 摘要过期。只读。"""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
SRV = PKG / "TRPG-服务端"

# 找 modules 目录
cands = list(SRV.rglob("index.json"))
print("=== 候选 index.json ===")
for p in cands:
    if "modules" in str(p) or "rulepacks" in str(p):
        print("  %-70s %7d B  mtime=%s" % (str(p.relative_to(PKG)), p.stat().st_size,
              time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))

for name in ("modules", "rulepacks"):
    d = SRV / "data" / name
    if not d.is_dir():
        for c in SRV.rglob(name):
            if c.is_dir() and (c / "index.json").is_file():
                d = c; break
    idx = d / "index.json"
    if not idx.is_file():
        continue
    print("")
    print("=" * 90)
    print("目录: %s" % d)
    print("index.json: %d B  mtime=%s" % (idx.stat().st_size,
          time.strftime("%m-%d %H:%M:%S", time.localtime(idx.stat().st_mtime))))
    data = json.loads(idx.read_text(encoding="utf-8"))
    print("  顶层键:", list(data))
    ents = data.get("entries") or data.get("modules") or []
    if isinstance(ents, dict):
        ents = [{"id": k, **v} for k, v in ents.items()]
    for e in ents:
        mid = e.get("id") or e.get("module_id")
        dig = e.get("digest") or e.get("sha256")
        print("   entry id=%-16s digest=%s  keys=%s" % (mid, (dig or "-")[:24], sorted(e)))
        # 找对应模块文件
        for cand in d.rglob("*"):
            if cand.is_file() and cand.name != "index.json" and mid and mid in str(cand):
                b = cand.read_bytes()
                h = hashlib.sha256(b).hexdigest()
                mark = "MATCH" if dig and h.startswith(dig[:24]) else "**STALE**"
                print("        %-58s %7d B  mtime=%s  sha256=%s  %s" % (
                    str(cand.relative_to(d)), len(b),
                    time.strftime("%m-%d %H:%M:%S", time.localtime(cand.stat().st_mtime)), h[:24], mark))
print("")
print("=== dead_light 相关文件（全包）===")
for p in PKG.rglob("*dead_light*"):
    if p.is_file() and "node_modules" not in str(p):
        st = p.stat()
        print("  %-78s %8d B  mtime=%s" % (str(p.relative_to(PKG)), st.st_size,
              time.strftime("%m-%d %H:%M:%S", time.localtime(st.st_mtime))))
