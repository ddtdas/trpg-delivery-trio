# -*- coding: utf-8 -*-
"""核实 tester 的「strings.js 只抓到 27 个键形」——是结构差异还是正则假象？只读。"""
from __future__ import annotations
import json, re
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
MP = PKG / "TRPG-微信小程序客户端"
js_path = MP / "strings.js"
jn_path = MP / "strings.json"

t = js_path.read_text(encoding="utf-8")
b = js_path.read_bytes()
d = json.loads(jn_path.read_text(encoding="utf-8"))

print("strings.js  size=%d cr=%d" % (len(b), b.count(b"\r")))
print("strings.json size=%d" % jn_path.stat().st_size)
print("")
print("--- strings.js 头 6 行 ---")
for ln in t.splitlines()[:6]:
    print("   " + ln[:130])
print("  ...")
print("--- strings.js 尾 4 行 ---")
for ln in t.splitlines()[-4:]:
    print("   " + ln[:130])
print("")

# 我的正则（mirror_authoritative S3 用的）
r_mine = dict(re.findall(r'^\s*"([^"]+)":\s*"([^"]*)"', t, flags=re.M))
# 更宽松
r_loose = dict(re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', t))
# 更严格（行首无缩进）
r_strict = dict(re.findall(r'^"([^"]+)":\s*"([^"]*)"', t, flags=re.M))
# tester 可能的写法：module.exports = { ... } 里带引号 but 单引号
r_single = dict(re.findall(r"'([^']+)'\s*:\s*'([^']*)'", t))

for name, m in (("mine  ^\\s*\"k\": \"v\"", r_mine), ("loose \"k\":\"v\"", r_loose),
                ("strict ^\"k\":", r_strict), ("single-quote", r_single)):
    print("  %-24s keys=%d" % (name, len(m)))

print("")
print("=== 判定 ===")
print("  json keys =", len(d))
print("  mine keys =", len(r_mine))
print("  set(r_mine) == set(d)      ->", set(r_mine) == set(d))
print("  r_mine == d (逐值相等)      ->", r_mine == d)
diff_k = set(r_mine) ^ set(d)
print("  键集合差集 =", sorted(diff_k) if diff_k else "（空）")
vdiff = [k for k in set(r_mine) & set(d) if r_mine[k] != d[k]]
print("  值不同的键 =", vdiff if vdiff else "（无）")
print("")
print("=== 结论 ===")
if r_mine == d:
    print("  strings.js 与 strings.json 【85 键逐值完全一致】 =>「json=85 vs js=27」是正则/量法假象，不是结构性差异。")
else:
    print("  两者不一致，需进一步查。")
