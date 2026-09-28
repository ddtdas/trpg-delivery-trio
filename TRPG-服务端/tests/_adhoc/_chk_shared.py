# -*- coding: utf-8 -*-
import hashlib
import io
import os
import re

ROOT = r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端"
rest = os.path.join(ROOT, "app", "web", "rest.py")
main = os.path.join(ROOT, "app", "main.py")
appjs = os.path.join(ROOT, "player-web", "app.js")

for p in (rest, main, appjs):
    b = open(p, "rb").read()
    print("%-46s %7d  %s" % (os.path.relpath(p, ROOT), len(b), hashlib.sha256(b).hexdigest().upper()[:16]))

print("--- rest.py: T7 标记与 NPC 相关行 ---")
src = io.open(rest, encoding="utf-8").read().splitlines()
for i, ln in enumerate(src, 1):
    if "T7 (additive)" in ln or "deliver_after_decision" in ln or "NPC" in ln or "def decide_approval" in ln:
        print("L%-4d %s" % (i, ln.rstrip()[:150]))

print("--- main.py: include_router 行 ---")
msrc = io.open(main, encoding="utf-8").read().splitlines()
for i, ln in enumerate(msrc, 1):
    if "include_router" in ln or "import" in ln and "router" in ln:
        print("L%-4d %s" % (i, ln.rstrip()[:150]))
