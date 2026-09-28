# -*- coding: utf-8 -*-
"""只读：modules/index.json 是否【真的被重跑】？save_state.json 现状？门禁现状？"""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
idx = SRV / "modules" / "index.json"
b = idx.read_bytes()
print("=== modules/index.json ===")
print("  %d B  sha256=%s" % (len(b), hashlib.sha256(b).hexdigest()))
print("  mtime = %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(idx.stat().st_mtime)))
print("  NOW   = %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

d = SRV / "modules" / "dead_light"
for rel in ["compiled/save_state.json", "compiled/dead_light.compiled.json",
            "compiled/compiled.manifest.json"]:
    p = d / rel
    bb = p.read_bytes()
    print("  %-34s %7d B  %s  mtime=%s" % (rel, len(bb), hashlib.sha256(bb).hexdigest()[:16],
          time.strftime("%H:%M:%S", time.localtime(p.stat().st_mtime))))
a = (d / "compiled" / "save_state.json").read_bytes()
c = (d / "compiled" / "dead_light.compiled.json").read_bytes()
print("  save_state == compiled.json ?", a == c)

import re
src = (SRV / "scripts" / "r2_verify_invariants.py").read_text(encoding="utf-8")
print("")
print("=== 现行门禁版本 ===")
print("  scripts/r2_verify_invariants.py %d B  sha256=%s" % (len(src.encode()), hashlib.sha256(src.encode()).hexdigest()))
print("  crlf count =", src.count("\r"))
m = re.search(r"^MY_SCRIPT_SHA\s*=\s*\"([0-9a-f]+)\"", src, flags=re.M)
print("  MY_SCRIPT_SHA =", m.group(1) if m else "(未找到)")
ns = {"hashlib": hashlib, "Path": Path, "json": json}
for dd in re.findall(r"^def [\s\S]*?(?=\n\S|\Z)", src, flags=re.M):
    try: exec(dd, ns)
    except Exception: pass
dg, size, n = ns["sha256_dir"](d)
e = [x for x in json.loads(b.decode("utf-8"))["entries"] if x["id"] == "dead_light"][0]
print("  entry.sha256 =", e["sha256"])
print("  recomputed   =", dg, " MATCH =", dg == e["sha256"])
print("  entry.size=%s recomputed.size=%s nfiles=%s" % (e["size"], size, n))

print("")
print("=== 我 §41 记录的关键事实复述 ===")
print("  §41 观测时 modules/index.json mtime = 2026-09-27 13:06:51.245")
print("  节 ① 记录: 13:21:25 save_state.json 被写回 13477 B(cad7efff) => 摘要重新吻合；index【从未重新生成】")
print("  14112 - 13477 = %d" % (14112 - 13477))
