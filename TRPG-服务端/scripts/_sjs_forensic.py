# -*- coding: utf-8 -*-
"""彻底核实「strings.js 键数 27 vs 85」——包内所有 strings.js 全枚举 + 多种量法。只读。"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")

print("=== 包内全部 strings.js / strings.json ===")
js_files = sorted(p for p in PKG.rglob("strings.js") if "node_modules" not in str(p))
jn_files = sorted(p for p in PKG.rglob("strings.json") if "node_modules" not in str(p))
for p in js_files:
    b = p.read_bytes()
    print("  JS   %-58s %6d B  cr=%d  %s" % (str(p.relative_to(PKG)), len(b), b.count(b"\r"),
          hashlib.sha256(b).hexdigest()[:16]))
for p in jn_files:
    b = p.read_bytes()
    print("  JSON %-58s %6d B  cr=%d  %s" % (str(p.relative_to(PKG)), len(b), b.count(b"\r"),
          hashlib.sha256(b).hexdigest()[:16]))

MP = PKG / "TRPG-微信小程序客户端" / "strings.js"
t = MP.read_text(encoding="utf-8")

print("")
print("=== 多种量法（同一个文件）===")
pats = [
    ("A  ^\\s*\"k\":\\s*\"v\"",        r'^\s*"([^"]+)":\s*"([^"]*)"'),
    ("B  \"k\":\\s*\"v\"",             r'"([^"]+)"\s*:\s*"([^"]*)"'),
    ("C  ^\"k\":",                     r'^"([^"]+)":'),
    ("D  仅匹配【ev. 前缀】(类 tester)", r'^\s*"(ev\.[^"]+)":\s*"([^"]*)"'),
    ("E  仅匹配【ext. 前缀】",          r'^\s*"(ext\.[^"]+)":\s*"([^"]*)"'),
]
for name, pat in pats:
    m = re.findall(pat, t, flags=re.M)
    print("  %-32s -> %d" % (name, len(m)))

d = json.loads((PKG / "TRPG-微信小程序客户端" / "strings.json").read_text(encoding="utf-8"))
mine = dict(re.findall(r'^\s*"([^"]+)":\s*"([^"]*)"', t, flags=re.M))
print("")
print("=== 判定 ===")
print("  json 键数        =", len(d))
print("  我的量法键数     =", len(mine))
print("  set(js) == set(json)  =", set(mine) == set(d))
print("  js == json (含值)     =", mine == d)
print("  键集合差集            =", sorted(set(mine) ^ set(d)) or "（空）")
print("  值不同的键            =", [k for k in set(mine) & set(d) if mine[k] != d[k]] or "（无）")
print("")
print("  各前缀键数（js）:", {p: sum(1 for k in mine if k.startswith(p)) for p in ("ev.", "ext.", "ui.")} or "n/a")
print("  js 行数 =", len(t.splitlines()), "  json 行数 =", len((PKG/'TRPG-微信小程序客户端'/'strings.json').read_text(encoding='utf-8').splitlines()))
