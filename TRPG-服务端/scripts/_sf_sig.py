# -*- coding: utf-8 -*-
"""只读：确认 StaticFiles 的可挂钩签名（决定 D2 补丁形状）。"""
from __future__ import annotations
import inspect
import starlette
from starlette.staticfiles import StaticFiles
print("starlette:", starlette.__version__)
for nm in ("file_response", "get_response", "__call__"):
    m = getattr(StaticFiles, nm, None)
    print("  StaticFiles.%-14s %s" % (nm, inspect.signature(m) if m else "(无)"))
try:
    from fastapi.staticfiles import StaticFiles as FS2
    print("  fastapi.staticfiles.StaticFiles is starlette's:", FS2 is StaticFiles)
except Exception as e:
    print("  fastapi import err", e)
import fastapi
print("fastapi:", fastapi.__version__)
