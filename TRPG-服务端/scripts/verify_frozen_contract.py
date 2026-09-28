# -*- coding: utf-8 -*-
r"""验收规范第 4 条：断言可复算性，不断言观测值。

本脚本**不硬编码任何 sha256**：它从冻结契约 docs/CROSS-END-CONTRACT.md 第 1.5 节的
声明表里读出「声明的 sha256」，与「现场重算的 sha256」比对 —— 断言的是
    声明值 == 现算值
这条不变量对契约升版免疫（契约改声明，脚本自动跟随），也对文件内容变化敏感（改了即 FAIL）。

复核者可自行复算：
    Get-FileHash <PROJ>\trpg\agent\events.py -Algorithm SHA256
"""
from __future__ import annotations
import hashlib, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # <PROJ> = TRPG-服务端
DOC = ROOT / "docs" / "CROSS-END-CONTRACT.md"
ROW = re.compile(r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([0-9A-Fa-f]{64})\s*\|\s*$", re.M)

RESULTS: list[tuple[str, str, bool, str]] = []


def emit(s: str = "") -> None:
    print(s)


emit("=" * 108)
emit("AC-7.28 冻结契约复算（断言：契约声明值 == 现场重算值；脚本内无任何硬编码哈希）")
emit("=" * 108)
emit("声明来源: %s  第 1.5 节" % DOC.relative_to(ROOT))
emit("复算命令: Get-FileHash <PROJ>\\<file> -Algorithm SHA256   （或 python -c hashlib）")
emit("")

text = DOC.read_text(encoding="utf-8")
declared = [(m.group(1).strip(), m.group(2).upper()) for m in ROW.finditer(text)]
if not declared:
    emit("ABORT: 未从契约第 1.5 节解析到任何 sha256 声明行")
    sys.exit(2)

emit("%-40s %-10s %-66s %s" % ("声明文件（相对 PROJ）", "状态", "声明 sha256", "现算 == 声明"))
emit("-" * 108)
allok = True
for rel, want in declared:
    p = ROOT / rel
    if not p.is_file():
        RESULTS.append((rel, "MISSING", False, "文件不存在"))
        allok = False
        emit("%-40s %-10s %-66s %s" % (rel, "MISSING", want, "n/a"))
        continue
    got = hashlib.sha256(p.read_bytes()).hexdigest().upper()
    same = (got == want)
    allok = allok and same
    RESULTS.append((rel, "EXISTS", same, got))
    emit("%-40s %-10s %-66s %s" % (rel, "EXISTS", want, "YES" if same else "**NO** -> " + got))

emit("")
emit("-" * 108)
miss = [r[0] for r in RESULTS if r[1] == "MISSING"]
bad = [r[0] for r in RESULTS if r[1] == "EXISTS" and not r[2]]
emit("声明项数 = %d   存在且一致 = %d   缺失 = %d   存在但不一致 = %d"
     % (len(RESULTS), len([r for r in RESULTS if r[2]]), len(miss), len(bad)))
if miss:
    emit("缺失清单（阻断 AC-7.28）：")
    for m in miss:
        emit("   - %s" % m)
if bad:
    emit("不一致清单（冻结契约被改动）：")
    for m in bad:
        emit("   - %s" % m)
emit("")
emit("INVARIANT_AC_7_28 = %s" % ("PASS" if allok else "FAIL"))
emit("")
emit("【报告口径】本条为**不变量**：判据是「声明值 == 现算值」，不是某个具体哈希值。")
emit("上面打印的 sha256 属**时点观测值**，仅供人眼核对；复核者请用上方命令自行复算。")
sys.exit(0 if allok else 1)
