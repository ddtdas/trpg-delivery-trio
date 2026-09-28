# -*- coding: utf-8 -*-
"""定位 CRLF 违规文件：modules/ 与 rulepacks/ 全量按字节数 CR/LF。"""
from __future__ import annotations
import hashlib, time
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
print("=== modules/ + rulepacks/ 逐文件 CR 统计（读字节，不用文本工具）===")
bad = []
for top in ("modules", "rulepacks"):
    root = SRV / top
    if not root.is_dir():
        print("  %s/ MISSING" % top); continue
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        b = p.read_bytes()
        cr = b.count(b"\r")
        lf = b.count(b"\n")
        if cr:
            bad.append(p)
            print("  *** CR=%d LF=%d %7d B  %s  mtime=%s" % (
                cr, lf, len(b), p.relative_to(SRV).as_posix(),
                time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))
    print("  -- %s/ 扫描完成，文件数=%d --" % (top, sum(1 for q in root.rglob("*") if q.is_file())))
print("")
print("=== 顶层文件（modules/ rulepacks/ 的 index.json 等）===")
for p in sorted(SRV.iterdir()):
    if p.is_file() and p.suffix in (".json", ".yaml", ".yml", ".md"):
        b = p.read_bytes()
        print("  %-34s %7d B  CR=%d" % (p.name, len(b), b.count(b"\r")))
print("")
print("=== 违规文件清单 ===")
if not bad:
    print("  （无）—— 但门禁报 FAIL，需复核门禁的扫描范围定义")
else:
    for p in bad:
        b = p.read_bytes()
        print("  %-56s CR=%d  %d B  %s" % (p.relative_to(SRV).as_posix(), b.count(b"\r"), len(b),
              hashlib.sha256(b).hexdigest()[:16]))
print("")
print("=== 门禁里这条不变量怎么写的 ===")
src = (SRV / "scripts" / "r2_verify_invariants.py").read_text(encoding="utf-8")
i = src.find("no CRLF in modules")
print(src[max(0,i-900):i+400])
