# -*- coding: utf-8 -*-
"""只读诊断：直接用 rules 的 sha256_dir() 复算 dead_light，定位差异来源。只读。"""
from __future__ import annotations
import hashlib, json, re, time
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
GATE = SRV / "scripts" / "r2_verify_invariants.py"
src = GATE.read_text(encoding="utf-8")

# 抽取 sha256_dir 函数源码（从 def 到下一个顶层 def/赋值）
m = re.search(r"^def sha256_dir\(.*?\n(?=^def |^[A-Z_]+\s*=|^\S)", src, flags=re.M | re.S)
if not m:
    print("未找到 sha256_dir，改为打印其定义上下文：")
    i = src.find("def sha256_dir")
    print(src[i-200:i+1400]); raise SystemExit(1)
fn_src = m.group(0)
print("=== 抽取到的 sha256_dir（rules 的原始实现）===")
print(fn_src)
ns = {}
exec(fn_src, ns)
sha256_dir = ns["sha256_dir"]

for kind in ("modules", "rulepacks"):
    root = SRV / kind
    idx = json.loads((root / "index.json").read_text(encoding="utf-8"))
    print("=" * 100)
    print("%s/index.json  generated_at=%s  fingerprint=%s" % (kind, idx.get("generated_at"), idx.get("fingerprint")))
    for e in idx["entries"]:
        d = root / str(e.get("dir") or e["id"])
        digest, size, nfiles = sha256_dir(d)
        ok = (digest == e.get("sha256")) and (size == e.get("size"))
        print("  %-18s entry.sha256=%s" % (e["id"], e.get("sha256")))
        print("  %-18s recomputed  =%s   %s" % ("", digest, "MATCH" if ok else "**MISMATCH**"))
        print("  %-18s entry.size=%s  recomputed.size=%s  entry.files=%s  recomputed.nfiles=%s" % (
            "", e.get("size"), size, e.get("files"), nfiles))
        if not ok:
            print("  ⚠️ 逐文件清单（复算实际纳入的文件）:")
            for p in sorted(d.rglob("*")):
                if p.is_file():
                    b = p.read_bytes()
                    print("       %-62s %7d B  mtime=%s  sha256=%s" % (
                        str(p.relative_to(d)).replace("\\", "/"), len(b),
                        time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)),
                        hashlib.sha256(b).hexdigest()[:16]))
