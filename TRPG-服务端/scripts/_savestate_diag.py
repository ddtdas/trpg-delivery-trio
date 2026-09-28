# -*- coding: utf-8 -*-
"""只读：确认 save_state.json 与 compiled.json 是否逐字节相同；以及 dir_files 的过滤规则。"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
src = (SRV / "scripts" / "r2_verify_invariants.py").read_text(encoding="utf-8")
defs = re.findall(r"^def [\s\S]*?(?=\n\S|\Z)", src, flags=re.M)
ns = {"hashlib": hashlib, "Path": Path, "json": json}
for d in defs:
    try: exec(d, ns)
    except Exception: pass
print("=== dir_files 的实现（决定 save_state.json 是否计入摘要）===")
i = src.find("def dir_files")
print(src[i:i+700])

d = SRV / "modules" / "dead_light"
a = (d / "compiled" / "save_state.json").read_bytes()
b = (d / "compiled" / "dead_light.compiled.json").read_bytes()
print("")
print("=== 两文件比对 ===")
print("  save_state.json          %7d B  %s" % (len(a), hashlib.sha256(a).hexdigest()))
print("  dead_light.compiled.json %7d B  %s" % (len(b), hashlib.sha256(b).hexdigest()))
print("  逐字节相同 =", a == b)

files = ns["dir_files"](d)
rel = [p.relative_to(d).as_posix() for p in files]
print("")
print("=== dir_files(dead_light) 实际纳入的文件 ===")
for r in rel:
    print("   ", r)
print("  save_state.json 是否计入 =", "compiled/save_state.json" in rel)

dg, size, n = ns["sha256_dir"](d)
idx = json.loads((SRV / "modules" / "index.json").read_text(encoding="utf-8"))
e = [x for x in idx["entries"] if x["id"] == "dead_light"][0]
print("")
print("=== 摘要复核 ===")
print("  entry.sha256 =", e["sha256"])
print("  recomputed   =", dg)
print("  MATCH        =", dg == e["sha256"])
print("  entry.size=%s  recomputed.size=%s  (差 %s)" % (e["size"], size, size - e["size"]))
print("  14112 - 13477 =", 14112 - 13477)
