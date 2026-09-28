# -*- coding: utf-8 -*-
import io, os, re
ROOT = r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端"
d = os.path.join(ROOT, "app", "npc", "director.py")
src = io.open(d, encoding="utf-8").read()
print("director.py bytes:", len(src.encode("utf-8")))
for m in re.finditer(r"^(?:def |async def |.*proposal_id.*=.*|.*_PID.*=.*|.*prefix.*=.*)$", src, re.M):
    t = m.group(0).strip()
    if t and ("def " in t or "proposal_id" in t or "prefix" in t or "_PID" in t):
        print("  ", t[:140])
