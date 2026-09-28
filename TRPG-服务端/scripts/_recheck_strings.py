# -*- coding: utf-8 -*-
"""复核 strings.json 当前真实状态（rules 报 3609B/5391e027，我修成 3522B/896f551b）+ 小程序端两份副本。"""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
FILES = [
    ("服务端/player-web/strings.json", PKG / "TRPG-服务端" / "player-web" / "strings.json"),
    ("Web客户端/client/strings.json", PKG / "TRPG-Web客户端" / "client" / "strings.json"),
    ("小程序/strings.json", PKG / "TRPG-微信小程序客户端" / "strings.json"),
    ("小程序/strings.js", PKG / "TRPG-微信小程序客户端" / "strings.js"),
]
NEED = ["ev.NPC_ACT_PROPOSED", "ev.NPC_ACT_APPROVED"]
for name, p in FILES:
    if not p.exists():
        print("%-32s MISSING" % name); continue
    b = p.read_bytes()
    h = hashlib.sha256(b).hexdigest()
    mt = time.strftime("%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
    txt = b.decode("utf-8", "replace")
    present = {k: (k in txt) for k in NEED}
    print("%-32s size=%-6d cr=%-4d lf=%-4d sha256=%s mtime=%s" % (name, len(b), b.count(b"\r"), b.count(b"\n"), h, mt))
    print("%-32s   含2键 = %s" % ("", present))
    if p.suffix == ".json":
        try:
            j = json.loads(txt)
            print("%-32s   keys=%d" % ("", len(j)))
        except Exception as exc:
            print("%-32s   JSON解析失败: %s" % ("", exc))

print("")
print("=== 两两逐字节比较 ===")
data = {n: (p.read_bytes() if p.exists() else None) for n, p in FILES}
ns = list(data)
for i in range(len(ns)):
    for j in range(i + 1, len(ns)):
        a, b = data[ns[i]], data[ns[j]]
        if a is None or b is None:
            print("  %-30s vs %-30s (缺文件)" % (ns[i], ns[j])); continue
        print("  %-30s vs %-30s -> %s" % (ns[i], ns[j], "IDENTICAL" if a == b else "DIFFER"))

print("")
print("=== 小程序目录里所有含 ev.NPC 的文件 ===")
wx = PKG / "TRPG-微信小程序客户端"
for p in sorted(wx.rglob("*")):
    if p.is_file() and p.suffix.lower() in (".json", ".js", ".wxss", ".wxml", ".ts"):
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if "NPC_ACT" in t:
            print("  命中:", p.relative_to(wx))
