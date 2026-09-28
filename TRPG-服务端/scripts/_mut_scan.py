# -*- coding: utf-8 -*-
"""穷举 scripts/ 下所有【具备文件变更能力】的脚本，并检查队长的排除规则是否覆盖它们。只读。"""
from __future__ import annotations
import re
from pathlib import Path

S = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\scripts")

MUT = re.compile(r"write_text|write_bytes|WriteAllText|WriteAllBytes|shutil\.copy|copyfile|copy2|copytree|"
                 r"os\.replace|os\.remove|\.unlink\(|shutil\.rmtree|\.mkdir\(|os\.makedirs|"
                 r"open\([^)]*['\"][wa]b?['\"]|Set-Content|Out-File", re.I)

# 队长的排除规则（D2）
EXCL = [re.compile(r"^patch_.*\.py$"), re.compile(r"^_t\d*_patch\.py$"), re.compile(r"^_t7_e2e\.py$"),
        re.compile(r"^_t7_modcheck\.py$"), re.compile(r".*_test_serve\.py$")]

def excluded(name: str) -> str | None:
    for rx in EXCL:
        if rx.match(name):
            return rx.pattern
    return None

rows = []
for p in sorted(S.glob("*.py")):
    b = p.read_bytes()
    t = b.decode("utf-8", errors="replace")
    hits = [m.group(0) for m in MUT.finditer(t)]
    # 排除注释行里的提及
    real = []
    for i, ln in enumerate(t.splitlines(), 1):
        s = ln.strip()
        if s.startswith("#"):
            continue
        if MUT.search(ln):
            real.append((i, s[:96]))
    if real:
        rows.append((p.name, len(b), len(real), excluded(p.name), real[:3]))

print("=== 具备文件变更能力的脚本，以及队长排除规则是否覆盖 ===")
gap = []
for name, size, cnt, ex, sample in rows:
    mark = "已排除" if ex else "**未覆盖**"
    if not ex:
        gap.append(name)
    print("%-32s %6dB  变更点=%-2d  %s" % (name, size, cnt, mark))
    for ln, s in sample:
        print("        L%-4d %s" % (ln, s))

print("")
print("=== ⚠️ 队长规则【未覆盖】但具备变更能力的脚本 (%d 个) ===" % len(gap))
for n in gap:
    print("   ", n)

print("")
print("=== 其中属于【我】(npc) 的 ===")
mine = [n for n in gap if n.startswith(("_t3_", "_t14_", "sync_wx", "fix_t3", "npc")) or "npc" in n]
for n in mine:
    print("   ", n)
