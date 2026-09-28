# -*- coding: utf-8 -*-
"""独立复核：线上 /player/app.js 到底有没有运行时 fetch strings.json。"""
from __future__ import annotations
import re, urllib.request

def get(u):
    with urllib.request.urlopen(u, timeout=15) as r:
        return r.status, r.read(), dict(r.headers)

st, body, hdr = get("http://127.0.0.1:9211/player/app.js")
txt = body.decode("utf-8")
print("GET /player/app.js -> %s  len=%d  Cache-Control=%s" % (st, len(body), hdr.get("Cache-Control", "【缺失】")))

for pat in ["strings.json", "strings", "fetch(", "XMLHttpRequest", "ix.title", "var S ="]:
    idxs = [m.start() for m in re.finditer(re.escape(pat), txt)]
    print("  %-16s 出现 %d 次" % (pat, len(idxs)))

print("")
print("=== 每一处 'strings.json' 的上下文（行号 + 前后 90 字符）===")
lines = txt.splitlines()
for i, ln in enumerate(lines, 1):
    if "strings.json" in ln:
        print("  L%d: %s" % (i, ln.strip()[:180]))
        # 判断是否在注释里
        s = ln.strip()
        kind = "注释" if (s.startswith("//") or s.startswith("/*") or s.startswith("*")) else "【代码】"
        print("      -> 该行首字符判定: %s" % kind)

print("")
print("=== 所有 'fetch(' 的上下文 ===")
for i, ln in enumerate(lines, 1):
    if "fetch(" in ln:
        print("  L%d: %s" % (i, ln.strip()[:180]))

print("")
print("=== 是否内联文案表 S ===")
m = re.search(r"var S = \{", txt)
print("  'var S = {' 位置:", m.start() if m else "未找到")
print("  内联表片段:", repr(txt[m.start():m.start()+160]) if m else "-")

print("")
print("=== 线上 /player/strings.json 是否含 ix.title ===")
st2, b2, h2 = get("http://127.0.0.1:9211/player/strings.json")
import json
d = json.loads(b2.decode("utf-8"))
print("  len=%d keys=%d  'ix.title' in? %s  ix.* 个数=%d" % (
    len(b2), len(d), "ix.title" in d, sum(1 for k in d if k.startswith("ix."))))
