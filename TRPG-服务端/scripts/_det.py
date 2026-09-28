# -*- coding: utf-8 -*-
"""门禁确定性复现（连跑两次，逐字节比对）+ 两个 _sjs_*.py 的归属线索。"""
from __future__ import annotations
import hashlib, subprocess, sys
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
G = SRV / "scripts" / "r2_verify_invariants.py"

runs = []
for i in (1, 2):
    r = subprocess.run([sys.executable, "-X", "utf8", str(G)], cwd=str(SRV),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "")
    runs.append((out, r.returncode))
    print("  第%d次: EXIT=%d  输出 %d 字符  sha256=%s" % (i, r.returncode, len(out), hashlib.sha256(out.encode("utf-8")).hexdigest()[:24]))

print("")
print("  两次输出逐字节相同 :", runs[0][0] == runs[1][0])
print("  两次退出码相同     :", runs[0][1] == runs[1][1])
# 去掉必然含时间的行后再比（若有）
import re
def strip_time(s):
    return re.sub(r"^\s*(as of|时间|NOW).*$", "", s, flags=re.M)
print("  去时间行后仍相同   :", strip_time(runs[0][0]) == strip_time(runs[1][0]))

print("")
print("=== 两个 _sjs_*.py 的头部（判归属）===")
for name in ("_sjs_check.py", "_sjs_forensic.py"):
    p = SRV / "scripts" / name
    if not p.exists():
        print("  %s MISSING" % name); continue
    b = p.read_bytes()
    print("  --- %s  %d B  cr=%d  sha=%s  mtime=%s ---" % (
        name, len(b), b.count(b"\r"), hashlib.sha256(b).hexdigest()[:16],
        __import__("datetime").datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M:%S")))
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()[:8], 1):
        print("      L%d: %s" % (i, line[:120]))
