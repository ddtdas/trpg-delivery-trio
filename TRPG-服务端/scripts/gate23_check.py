# -*- coding: utf-8 -*-
"""门禁 2+3 独立复算：三端键集合 / 共有键值差异 / 小程序 JS<->JSON。只读，不写入。"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

P = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
E = {
    "svc/player-web": P / "TRPG-服务端" / "player-web" / "strings.json",
    "web/client":     P / "TRPG-Web客户端" / "client" / "strings.json",
    "miniprogram":    P / "TRPG-微信小程序客户端" / "strings.json",
}
d = {k: json.loads(v.read_text(encoding="utf-8")) for k, v in E.items()}
js_txt = (P / "TRPG-微信小程序客户端" / "strings.js").read_text(encoding="utf-8")
js = dict(re.findall(r'^\s*"([^"]+)":\s*"([^"]*)"', js_txt, flags=re.M))

ks = list(d.values())
print("键数            :", {k: len(v) for k, v in d.items()}, " strings.js:", len(js))
print("三端键集合两两相等 :", all(set(x) == set(ks[0]) for x in ks))
print("共有键值零差异     :", all(d["svc/player-web"][k] == d["web/client"][k] == d["miniprogram"][k]
                                 for k in d["svc/player-web"]))
print("JS<->JSON 键集合相等:", set(js) == set(d["miniprogram"]))
print("JS<->JSON 逐值相等  :", js == d["miniprogram"])
print("两键值(小程序)     :", {k: d["miniprogram"][k] for k in ("ev.NPC_ACT_PROPOSED", "ev.NPC_ACT_APPROVED")})
print("")
for k, v in E.items():
    b = v.read_bytes()
    print("  %-15s %d B  cr=%d  %s" % (k, len(b), b.count(b"\r"), hashlib.sha256(b).hexdigest()))
jb = (P / "TRPG-微信小程序客户端" / "strings.js").read_bytes()
print("  %-15s %d B  cr=%d  %s" % ("miniprogram js", len(jb), jb.count(b"\r"), hashlib.sha256(jb).hexdigest()))
print("")
ok = (all(set(x) == set(ks[0]) for x in ks)
      and all(d["svc/player-web"][k] == d["web/client"][k] == d["miniprogram"][k] for k in d["svc/player-web"])
      and js == d["miniprogram"]
      and len(js) > 0 and all(len(x) > 0 for x in ks)  # 口径: 只断言非空+三端相等; 键数会漂移, 不作为断言值
      and all(v.read_bytes().count(b"\r") == 0 for v in E.values()) and jb.count(b"\r") == 0)
print("GATES_2_3 = %s" % ("PASS" if ok else "FAIL"))
import sys as _sys
_sys.exit(0 if ok else 1)
