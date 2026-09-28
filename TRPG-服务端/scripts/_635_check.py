# -*- coding: utf-8 -*-
"""决定性检验：14112 - 13477 = 635 是否恰等于该文件的 LF 行数（=> 当时那份是 CRLF 变体）。"""
from __future__ import annotations
import hashlib
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
for rel in ["modules/dead_light/compiled/save_state.json",
            "modules/dead_light/compiled/dead_light.compiled.json"]:
    p = SRV / rel
    b = p.read_bytes()
    lf = b.count(b"\n"); cr = b.count(b"\r")
    print("%-56s %6d B  LF=%d  CR=%d" % (rel, len(b), lf, cr))
    print("   若全文改 CRLF 则大小 = %d + %d = %d   (14112 ? %s)" % (
        len(b), lf, len(b) + lf, "YES 完全吻合" if len(b) + lf == 14112 else "NO"))

print("")
print("=== 结论式对照 ===")
b = (SRV / "modules/dead_light/compiled/save_state.json").read_bytes()
print("  14112 (当时) - 13477 (现) = %d" % (14112 - 13477))
print("  现值 LF 行数              = %d" % b.count(b"\n"))
print("  相等 => %s" % (14112 - 13477 == b.count(b"\n")))
print("  => 当时那份 14112 B 就是【同内容的 CRLF 变体】（每 \\n 多 1 个 \\r）")
