# -*- coding: utf-8 -*-
import hashlib, io, os, re
ROOT = r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端"
rest = os.path.join(ROOT, "app", "web", "rest.py")
b = open(rest, "rb").read()
print("rest.py", len(b), hashlib.sha256(b).hexdigest())
src = io.open(rest, encoding="utf-8").read().splitlines()
for i, ln in enumerate(src, 1):
    if 340 <= i <= 360:
        print("L%-4d %s" % (i, ln.rstrip()[:120]))

print("--- deliver_after_decision 无规格时的行为 ---")
pa = io.open(os.path.join(ROOT, "app", "web", "pipeline_api.py"), encoding="utf-8").read()
m = re.search(r"async def deliver_after_decision[\s\S]{0,900}", pa)
print(m.group(0)[:900] if m else "NOT FOUND")

print("--- 谁在写 pipeline_store（登记投递规格）---")
hits = []
for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "app")):
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        p = os.path.join(dirpath, fn)
        t = io.open(p, encoding="utf-8", errors="replace").read()
        if "register" in t and ("pipeline_store" in t or "put_spec" in t or "delivery_spec" in t):
            hits.append(os.path.relpath(p, ROOT))
print(hits)
