# -*- coding: utf-8 -*-
"""两处回滚点比对 + 当前 pid 复核。"""
from __future__ import annotations
import hashlib, time
from pathlib import Path

L1 = Path(r"C:\_r2npc_stage\rollback")
L2 = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\_r2_backup\t3")

for label, d in (("A) C:\\_r2npc_stage\\rollback", L1), ("B) ...\\_r2_backup\\t3", L2)):
    print("=== %s  存在=%s ===" % (label, d.is_dir()))
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.is_file():
                b = p.read_bytes()
                print("  %-58s %7d B  %s  mtime=%s" % (
                    p.name, len(b), hashlib.sha256(b).hexdigest(),
                    time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))
    print("")

# 同名文件跨两处比对
if L1.is_dir() and L2.is_dir():
    n1 = {p.name: p for p in L1.iterdir() if p.is_file()}
    n2 = {p.name: p for p in L2.iterdir() if p.is_file()}
    print("=== 两处同名文件是否一致 ===")
    common = sorted(set(n1) & set(n2))
    print("  同名:", common or "无")
    for n in common:
        a, b = n1[n].read_bytes(), n2[n].read_bytes()
        print("   %-58s %s" % (n, "IDENTICAL" if a == b else "DIFFER"))
    print("  仅 A 有:", sorted(set(n1) - set(n2)))
    print("  仅 B 有:", sorted(set(n2) - set(n1)))
    print("")
    print("  合计 A=%d 个, B=%d 个" % (len(n1), len(n2)))

print("")
print("=== 当前 9211 权威取值 ===")
import httpx
try:
    h = httpx.get("http://127.0.0.1:9211/api/health", timeout=10)
    print("  health:", h.status_code, h.text)
except Exception as exc:
    print("  health FAILED:", exc)
