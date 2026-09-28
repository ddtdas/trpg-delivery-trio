# -*- coding: utf-8 -*-
import io, os
ROOT = r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端"
src = io.open(os.path.join(ROOT, "app", "web", "rest.py"), encoding="utf-8").read().splitlines()
for i in range(344, 410):
    print("L%-4d %s" % (i + 1, src[i].rstrip()[:160]))
