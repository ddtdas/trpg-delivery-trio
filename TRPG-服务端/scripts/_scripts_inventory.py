# -*- coding: utf-8 -*-
"""盘点交付包 TRPG-服务端/scripts/ 下我新增的脚本，按「只读验证器」vs「一次性补丁」分类。只读。"""
from __future__ import annotations
import hashlib, re, time
from pathlib import Path

S = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\scripts")
ONE_SHOT_PAT = re.compile(r'\b(OLD|OLD_STR|TAIL|ANCHOR)\b|count\(|occurrences|ABORT')
READONLY_PAT = re.compile(r'verify|mirror|audit|gate23|recheck|frozen')

rows = []
for p in sorted(S.glob("*.py")):
    b = p.read_bytes()
    t = b.decode("utf-8", errors="replace")
    one = bool(ONE_SHOT_PAT.search(t)) or p.name.startswith(("patch_", "fix_")) or p.name.startswith("_t3_")
    ro = bool(READONLY_PAT.search(p.name)) and "patch" not in p.name
    rows.append((p.name, len(b), b.count(b"\r"), hashlib.sha256(b).hexdigest()[:12],
                 time.strftime("%m-%d %H:%M", time.localtime(p.stat().st_mtime)), one, ro, t.count("WriteAllBytes") + t.count("write_text") + t.count("WriteAllText") + t.count("write_bytes")))

print("%-34s %7s %4s %-13s %-12s %-8s %-8s %s" % ("file", "size", "cr", "sha256[:12]", "mtime", "oneShot", "readOnly", "writeCalls"))
print("-" * 118)
for r in rows:
    print("%-34s %7d %4d %-13s %-12s %-8s %-8s %d" % (r[0], r[1], r[2], r[3], r[4], "YES" if r[5] else "", "YES" if r[6] else "", r[7]))

print("")
print("=== 分类统计 ===")
one = [r[0] for r in rows if r[5]]
ro = [r[0] for r in rows if r[6]]
print("  一次性补丁类 (%d):" % len(one))
for n in one:
    print("     ", n)
print("  只读验证器类 (%d):" % len(ro))
for n in ro:
    print("     ", n)
print("  其余 (%d):" % len([r for r in rows if not r[5] and not r[6]]))
for r in rows:
    if not r[5] and not r[6]:
        print("     ", r[0])
print("")
print("  scripts/ 下 .py 总数 =", len(rows))
