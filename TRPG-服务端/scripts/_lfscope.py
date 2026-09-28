# -*- coding: utf-8 -*-
"""把 rules 的 229 文件 CRLF 普查收敛成【真正暴露面】：枚举包内所有 LF/CRLF 断言，再与 CRLF 文件集求交。只读。"""
from __future__ import annotations
import hashlib, re, sys
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
SRV = PKG / "TRPG-服务端"

PAT = re.compile(r"content_is_lf|crlf|CRLF|b\"\\\\r\"|count\(b'\\\\r'\)|\\\\r\\\\n|no CRLF|LF\b", re.I)

print("=== A. 包内所有 LF/CRLF 断言的出处（.py / .ps1）===")
hits = []
for p in list(SRV.rglob("*.py")) + list(SRV.rglob("*.ps1")):
    if any(x in str(p) for x in ("node_modules", ".git", "web\\dist", "web/dist")):
        continue
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        continue
    for i, ln in enumerate(lines, 1):
        if PAT.search(ln):
            rel = str(p.relative_to(PKG))
            hits.append((rel, i, ln.strip()[:120]))
print("  命中 %d 处" % len(hits))
for rel, i, ln in hits[:40]:
    print("    %s:%d  %s" % (rel, i, ln))
if len(hits) > 40:
    print("    ...(还有 %d 处)" % (len(hits) - 40))

print("")
print("=== B. 全包 CRLF 文件集（含 CR 的文件）===")
crlf = []
for p in PKG.rglob("*"):
    if not p.is_file():
        continue
    if any(x in str(p) for x in ("node_modules", ".git")):
        continue
    try:
        b = p.read_bytes()
    except Exception:
        continue
    n = b.count(b"\r")
    if n:
        crlf.append((str(p.relative_to(PKG)), n, len(b)))
crlf.sort(key=lambda t: -t[1])
print("  含 CR 的文件数 = %d" % len(crlf))

print("")
print("=== C. ★ 求交：被【断言】要求 LF 的树 ∩ 实际含 CRLF 的树 ===")
# 断言覆盖的树（皆由 A 段出处人工确认；此处显式列出以便复核）
ASSERTED_TREES = [("modules", SRV / "modules"), ("rulepacks", SRV / "rulepacks")]
for name, tree in ASSERTED_TREES:
    bad = [t for t in crlf if str(t[0]).replace("/", "\\").startswith(str(tree.relative_to(PKG)))]
    print("  %-10s 断言=必须 LF   含CRLF文件数=%d   %s" % (name, len(bad), bad if bad else ""))
print("  => 【真正暴露面】就是上面这两行；229 个含 CRLF 的文件里，落在被断言树内的只有它们。")

print("")
print("=== D. .bak* 残留盘点（我此前说 9 个、全为 .bak-t5）===")
baks = []
for p in PKG.rglob("*.bak*"):
    if p.is_file():
        baks.append((str(p.relative_to(PKG)), len(p.read_bytes())))
print("  总数 = %d" % len(baks))
from collections import Counter
c = Counter(re.sub(r"^.*(\.bak[a-z0-9\-]*)", r"\1", n) for n, _ in baks)
for k, v in sorted(c.items()):
    print("    %-16s %d" % (k, v))
for n, s in sorted(baks):
    print("      %s  %d B" % (n, s))

print("")
print("=== E. rules 报的四条打包卫生问题（现场复核）===")
z = SRV / "TRPG-服务端.zip"
print("  1) TRPG-服务端.zip                :", ("存在 %d B" % z.stat().st_size) if z.exists() else "不存在")
pc = SRV / ".pytest_cache"
print("  2) .pytest_cache/                 :", ("存在，%d 个文件" % sum(1 for _ in pc.rglob("*") if _.is_file())) if pc.exists() else "不存在")
run = SRV / "run"
if run.exists():
    logs = [(str(x.relative_to(PKG)), x.stat().st_size) for x in run.rglob("*") if x.is_file()]
    print("  3) run/ 下文件数 = %d，合计 %d B" % (len(logs), sum(s for _, s in logs)))
    for n, s in sorted(logs, key=lambda t: -t[1])[:6]:
        print("       %s  %d B" % (n, s))
else:
    print("  3) run/ 不存在")
