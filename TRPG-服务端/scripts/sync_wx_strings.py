# -*- coding: utf-8 -*-
"""队长裁决：同步小程序端 2 个文件（strings.json + strings.js），字节级写入，保持 LF。

禁止 Set-Content/Out-File/Path.write_text；只用 read_bytes/write_bytes。
"""
from __future__ import annotations
import hashlib, json, re, shutil, sys
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
WX = PKG / "TRPG-微信小程序客户端"
RB = Path(r"C:\_r2npc_stage\rollback")
RB.mkdir(parents=True, exist_ok=True)

PAIR = ("ev.NPC_ACT_PROPOSED", "NPC 台词待审")
PAIR2 = ("ev.NPC_ACT_APPROVED", "NPC 台词")
TAIL = b'"ext.ev.directed": "\xe5\xae\x9a\xe5\x90\x91\xe6\xb6\x88\xe6\x81\xaf {body}"\n}'
NEW_TAIL = (b'"ext.ev.directed": "\xe5\xae\x9a\xe5\x90\x91\xe6\xb6\x88\xe6\x81\xaf {body}",\n'
            + ('  "%s": "%s",\n' % PAIR).encode("utf-8")
            + ('  "%s": "%s"\n' % PAIR2).encode("utf-8")
            + b"}")

TARGETS = [WX / "strings.json", WX / "strings.js"]
for p in TARGETS:
    b = p.read_bytes()
    shutil.copy2(p, RB / ("TRPG-微信小程序客户端__%s.bak-r2npcsync" % p.name))
    n = b.count(TAIL)
    print("%-14s before size=%-6d cr=%-4d sha=%s  tail_occurrences=%d" %
          (p.name, len(b), b.count(b"\r"), hashlib.sha256(b).hexdigest(), n))
    if n != 1:
        print("ABORT: tail occurrences != 1"); sys.exit(2)
    nb = b.replace(TAIL, NEW_TAIL, 1)
    if nb.count(b"\r") != 0:
        print("ABORT: would introduce CR"); sys.exit(2)
    p.write_bytes(nb)          # 字节级写入，零翻译
    b2 = p.read_bytes()
    print("%-14s after  size=%-6d cr=%-4d sha=%s" % (p.name, len(b2), b2.count(b"\r"),
                                                     hashlib.sha256(b2).hexdigest()))

print("")
print("=== 门禁校验（队长 ④）===")
ends = [
    ("服务端/player-web", PKG / "TRPG-服务端" / "player-web" / "strings.json"),
    ("Web客户端/client", PKG / "TRPG-Web客户端" / "client" / "strings.json"),
    ("微信小程序", WX / "strings.json"),
]
sets = {}
for name, p in ends:
    j = json.loads(p.read_text(encoding="utf-8"))
    sets[name] = set(j)
    print("%-20s keys=%-4d cr=%-3d sha=%s" % (name, len(j), p.read_bytes().count(b"\r"),
                                              hashlib.sha256(p.read_bytes()).hexdigest()))
ks = list(sets.values())
ident = all(k == ks[0] for k in ks)
print("KEY_SETS_IDENTICAL =", ident)
print("三端键数相同 =", len(set(len(k) for k in ks)) == 1, "  keys=%d" % len(ks[0]))
if not ident:
    for i in range(1, len(ks)):
        print("  only_in_%s = %s" % (list(sets)[0], sorted(ks[0] - ks[i])))
        print("  only_in_%s = %s" % (list(sets)[i], sorted(ks[i] - ks[0])))

# JS 侧
js = (WX / "strings.js").read_bytes().decode("utf-8")
pairs = re.findall(r'^\s*"([^"]+)":\s*"([^"]*)"', js, flags=re.M)
jsmap = dict(pairs)
print("")
print("strings.js 解析到 %d 个键（重复键数=%d）" % (len(jsmap), len(pairs) - len(jsmap)))
jn = json.loads((WX / "strings.json").read_text(encoding="utf-8"))
print("JS_JSON_CONSISTENT =", jsmap == jn)
if jsmap != jn:
    print("  only_in_js   =", sorted(set(jsmap) - set(jn)))
    print("  only_in_json =", sorted(set(jn) - set(jsmap)))
    print("  value_diff   =", [k for k in set(jsmap) & set(jn) if jsmap[k] != jn[k]])
print("JS 侧含 2 键 =", (PAIR[0] in jsmap, PAIR2[0] in jsmap))
print("JSON 侧含 2 键 =", (PAIR[0] in jn, PAIR2[0] in jn))
