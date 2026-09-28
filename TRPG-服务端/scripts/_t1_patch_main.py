#!/usr/bin/env python3
"""一次性 patch: 把仓库路由/守卫/错误码映射挂到 app/main.py (additive)。"""
from __future__ import annotations

from pathlib import Path

P = Path(__file__).resolve().parent.parent / "app" / "main.py"


def main() -> int:
    raw = P.read_bytes()
    src = raw.decode("utf-8")
    if "rest_repo" in src:
        print("ALREADY_PATCHED")
        return 0
    nl = "\r\n" if "\r\n" in src else "\n"

    old_import = "from app.web.rest import router as rest_router" + nl
    new_import = ("from app.web.rest import router as rest_router" + nl +
                  "from app.web.rest_repo import (install_repo_error_handler," + nl +
                  "                               install_repo_path_guard, router as repo_router)" + nl)
    assert old_import in src, "anchor 1 not found"
    src = src.replace(old_import, new_import, 1)

    old_inc = "app.include_router(identity_router)" + nl
    new_inc = ("app.include_router(identity_router)" + nl +
               "# R22/R1/R2/R13/R3 (additive): 模组仓库 + 规则仓库 REST, 路径穿越守卫," + nl +
               "# RepoError -> {error_code,message,http_status,detail} 映射。" + nl +
               "app.include_router(repo_router)" + nl +
               "install_repo_path_guard(app)" + nl +
               "install_repo_error_handler(app)" + nl)
    assert old_inc in src, "anchor 2 not found"
    src = src.replace(old_inc, new_inc, 1)

    P.write_bytes(src.encode("utf-8"))
    print("PATCHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
