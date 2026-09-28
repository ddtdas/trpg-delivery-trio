# -*- coding: utf-8 -*-
"""定位 47001117… 的来源；并独立复算 rest.py 权威哈希 + visibility 冻结面。"""
from __future__ import annotations
import hashlib, time
from pathlib import Path

TARGET = "47001117db5d48ca62af2a381afd7652a205acac20659929c2484485cfadf82c"
ROOTS = [Path(r"C:\_r2npc_stage"), Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\_r2_backup"),
         Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")]
print("=== 全盘找 sha256 == 47001117… 的文件（限三个根）===")
found = []
n = 0
for root in ROOTS:
    if not root.is_dir():
        continue
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        n += 1
        try:
            h = hashlib.sha256(p.read_bytes()).hexdigest()
        except Exception:
            continue
        if h == TARGET:
            found.append(p)
print("  扫描文件数 =", n)
print("  命中 =", found if found else "**0 个（该哈希在任何副本中都不存在）**")

print("")
print("=== 权威 rest.py 复算（三种独立方式）===")
R = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\app\web\rest.py")
b = R.read_bytes()
print("  size      =", len(b))
print("  cr count  =", b.count(b"\r"), " lf count =", b.count(b"\n"), " lone_lf =", b.count(b"\n") - b.count(b"\r\n"))
print("  sha256    =", hashlib.sha256(b).hexdigest())
print("  mtime     =", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(R.stat().st_mtime)))
print("  realtime 报的 = 29e1cc3f9363f23da61a680b4b967cfd80b87a9f9b2a54a5ce9a45eaf72f4218")
print("  一致 =", hashlib.sha256(b).hexdigest() == "29e1cc3f9363f23da61a680b4b967cfd80b87a9f9b2a54a5ce9a45eaf72f4218")

print("")
print("=== 我的 NPC 标记是否都在权威文件里（逐条）===")
t = R.read_text(encoding="utf-8")
for needle in ["import os", "NPC_GATE_OPEN", "TRPG_NPC_GATE", "class NpcAct", "handle_npc_act",
               "is_npc_proposal", "npc_proposal", "decide_approval"]:
    print("  %-20s x%d" % (needle, t.count(needle)))

print("")
print("=== 独立复核 realtime 的第 2 点（visibility 冻结面）===")
V = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\app\domain\visibility.py")
vt = V.read_text(encoding="utf-8")
print("  visibility.py sha256 =", hashlib.sha256(V.read_bytes()).hexdigest())
i = vt.find("KP_ONLY_EVENT_TYPES")
print("  KP_ONLY_EVENT_TYPES 段落：")
for ln in vt[i:i + 700].splitlines()[:14]:
    print("    " + ln.rstrip())

print("")
print("=== 独立复核 realtime 的第 1 点（app.js 推送驱动）===")
J = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-Web客户端\client\app.js")
jt = J.read_text(encoding="utf-8")
for needle in ["POLL_FALLBACK_MS = 15000", "PUSH_DEBOUNCE_MS = 60", "KNOWN_KINDS", "STATE_DELTA: 1", "pushRefresh", "pushWsFrame"]:
    print("  %-26s x%d" % (needle, jt.count(needle)))
