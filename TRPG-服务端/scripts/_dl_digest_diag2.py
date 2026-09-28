# -*- coding: utf-8 -*-
"""只读诊断 v2：exec rules 脚本的全部顶层函数定义，复算 modules/rulepacks 摘要。只读。"""
from __future__ import annotations
import hashlib, json, re, time
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
GATE = SRV / "scripts" / "r2_verify_invariants.py"
src = GATE.read_text(encoding="utf-8")

# 抽取全部顶层函数定义（无副作用）
defs = re.findall(r"^def [\s\S]*?(?=\n\S|\Z)", src, flags=re.M)
ns = {"hashlib": hashlib, "Path": Path, "json": json}
for d in defs:
    try:
        exec(d, ns)
    except Exception as exc:
        print("  [skip def] %s" % exc)
print("抽取到函数:", sorted(k for k, v in ns.items() if callable(v) and not k.startswith("_") and k not in ("hashlib", "Path", "json")))

sha256_dir = ns["sha256_dir"]
missing = []
for kind in ("modules", "rulepacks"):
    root = SRV / kind
    idx = json.loads((root / "index.json").read_text(encoding="utf-8"))
    print("")
    print("=" * 104)
    print("%s/index.json  generated_at=%s" % (kind, idx.get("generated_at")))
    print("  fingerprint = %s" % idx.get("fingerprint"))
    for e in idx["entries"]:
        d = root / str(e.get("dir") or e["id"])
        digest, size, nfiles = sha256_dir(d)
        ok = (digest == e.get("sha256"))
        print("  %-18s %s" % (e["id"], "MATCH" if ok else "**MISMATCH (digest)**"))
        if not ok:
            missing.append((kind, e["id"], d))
        print("      entry.sha256  = %s" % e.get("sha256"))
        print("      recomputed    = %s" % digest)
        print("      entry.size=%-8s recomputed.size=%-8s entry.files=%-4s recomputed.nfiles=%s" % (
            e.get("size"), size, e.get("files"), nfiles))

print("")
print("=" * 104)
for kind, mid, d in missing:
    print("⚠️ 逐文件清单：%s/%s  (目录 %s)" % (kind, mid, d))
    for p in sorted(d.rglob("*")):
        if p.is_file():
            b = p.read_bytes()
            print("     %-64s %7d B  mtime=%s  sha256=%s" % (
                str(p.relative_to(d)).replace("\\", "/"), len(b),
                time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)),
                hashlib.sha256(b).hexdigest()[:20]))
