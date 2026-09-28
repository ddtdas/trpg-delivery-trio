# -*- coding: utf-8 -*-
import io, os, time
ROOT = r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端"
src = io.open(os.path.join(ROOT, "app", "npc", "routes.py"), encoding="utf-8").read()
print("--- npc/routes.py 路由 ---")
for ln in src.splitlines():
    s = ln.strip()
    if s.startswith("@router.") or s.startswith("def ") or s.startswith("async def "):
        print("  ", s[:130])
for p in ("app/web/rest.py", "app/main.py", "app/npc/routes.py"):
    st = os.stat(os.path.join(ROOT, p.replace("/", os.sep)))
    print("%-24s mtime=%s" % (p, time.strftime("%m/%d %H:%M:%S", time.localtime(st.st_mtime))))
