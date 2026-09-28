# -*- coding: utf-8 -*-
"""只读诊断：modules/index.json 的 dead_light 条目 files[] 与磁盘实际文件集是否一致。只读。"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

SRV = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端")
MODS = SRV / "modules"
idx = json.loads((MODS / "index.json").read_text(encoding="utf-8"))

for e in idx["entries"]:
    mid = e["id"]
    d = MODS / e.get("dir", mid)
    on_disk = sorted(str(p.relative_to(d)).replace("\\", "/") for p in d.rglob("*") if p.is_file())
    listed = e.get("files")
    print("=" * 100)
    print("module = %s   dir = %s" % (mid, e.get("dir")))
    print("  entry.digest      = %s" % e.get("sha256"))
    print("  entry.size        = %s" % e.get("size"))
    print("  entry.files 类型  = %s   个数 = %s" % (type(listed).__name__, (len(listed) if listed is not None else "None")))
    if isinstance(listed, list) and listed and isinstance(listed[0], dict):
        lf = sorted(f.get("path") or f.get("name") or "" for f in listed)
        print("  files[] 为【对象列表】, 示例:", listed[0])
    elif isinstance(listed, list):
        lf = sorted(str(x) for x in listed)
    else:
        lf = []
    print("  磁盘文件数 = %d   files[] 数 = %d" % (len(on_disk), len(lf)))
    only_disk = sorted(set(on_disk) - set(lf))
    only_list = sorted(set(lf) - set(on_disk))
    print("  ⚠️ 仅在磁盘（未列入 files[]）: %s" % (only_disk or "（无）"))
    print("  ⚠️ 仅在 files[]（磁盘缺失）  : %s" % (only_list or "（无）"))
    if not only_disk and not only_list:
        print("  ✅ 文件集一致 -> 差异不在此，需查【摘要算法/顺序/字段】")
