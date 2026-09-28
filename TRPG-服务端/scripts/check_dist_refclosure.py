#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dist 引用闭包断言 —— 在 dist.new 尚未上台时先判定它能不能用。

归属: implementer-ui（脚本在 scripts/ 下）。不改 r2_deploy_dist.ps1，只供其调用一行。

为什么需要它（缺口来自 implementer-gmui 认领的 r2_deploy_dist.ps1 真缺口）:
  该脚本的 I1「引用全部存在」跑在 swap 【之后】—— 它能发现并回滚，
  但那一刻 dist 已经被换过一次。本脚本把同一条判据前移到 staging 期:
  失败 => 从未触碰线上 dist，连回滚都不需要。

判据（不变量，可断言）:
  1) index.html 中每个本地引用，都能在 dist 内解析到一个真实文件
  2) 若线上 dist 存在 keeper-ui/，则被检查的 dist 也必须存在且非空
     （否则 swap 会把 106 个文件丢掉 —— 从「白屏几百毫秒」变成「白屏到永远」）
时点观测值（仅打印，不作断言）: 被引用文件数、未被引用文件数

用法:
  python scripts/check_dist_refclosure.py                  # 默认 web/dist
  python scripts/check_dist_refclosure.py web/dist.new     # staging 期
  exit 0 = 闭包成立 ; exit 1 = 有引用指向不存在的文件
"""
import os
import re
import sys
from pathlib import Path

REF_RE = re.compile(r"""(?:src|href)\s*=\s*("([^"]*)"|'([^']*)')""", re.I)
EXTERNAL = ("http://", "https://", "//", "data:", "mailto:", "javascript:")


def refs_of(index_text: str):
    out = []
    for m in REF_RE.finditer(index_text):
        url = (m.group(2) or m.group(3) or "").strip()
        if not url or url.startswith("#"):
            continue
        if url.lower().startswith(EXTERNAL):
            continue
        out.append(url)
    return out


def resolve(dist: Path, url: str):
    """把 URL 路径解析成 dist 内的候选磁盘路径（对挂载前缀变化免疫）。"""
    rel = url.split("?")[0].split("#")[0].lstrip("/")
    cands = [dist / rel]
    parts = rel.split("/")
    if len(parts) > 1:
        cands.append(dist.joinpath(*parts[1:]))   # /app/assets/x -> assets/x
    return cands


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    arg = sys.argv[1] if len(sys.argv) > 1 else "web/dist"
    dist = Path(arg)
    if not dist.is_absolute():
        dist = root / arg
    print("[dist_refclosure] 被检查的 dist = %s" % dist)
    if not dist.is_dir():
        print("  BAD  dist 不存在")
        return 1

    idx = dist / "index.html"
    if not idx.is_file():
        print("  BAD  index.html 不存在")
        return 1
    text = idx.read_text(encoding="utf-8", errors="replace")
    urls = refs_of(text)

    missing = []
    resolved = []
    for u in urls:
        hit = None
        for c in resolve(dist, u):
            if c.is_file():
                hit = c
                break
        if hit is None:
            missing.append(u)
        else:
            resolved.append((u, hit))

    all_files = {p for p in dist.rglob("*") if p.is_file()}
    referenced = {p for _, p in resolved}
    unreferenced = sorted(p for p in all_files - referenced)

    bad = 0
    if missing:
        bad += 1
        print("  BAD  引用闭包不成立: %d 个引用在 dist 内不存在" % len(missing))
        for u in missing[:8]:
            print("         缺: %s" % u)
    else:
        print("  OK   引用闭包成立: 引用=%d 全部可解析" % len(urls))

    # keeper-ui 硬前置（仅当线上 dist 有它时才要求）
    live = dist.parent / "dist"
    live_keeper = live / "keeper-ui"
    need_keeper = dist.resolve() != live.resolve() and live_keeper.is_dir()
    if need_keeper:
        k = dist / "keeper-ui"
        n = len([p for p in k.rglob("*") if p.is_file()]) if k.is_dir() else 0
        if n == 0:
            bad += 1
            print("  BAD  keeper-ui 缺失或为空（线上 dist 有它）—— swap 会丢掉它")
        else:
            print("  OK   keeper-ui 存在且非空: %d 个文件" % n)

    print("  [时点观测值] files_total=%d referenced=%d unreferenced=%d"
          % (len(all_files), len(referenced), len(unreferenced)))
    for p in unreferenced[:5]:
        print("       未被引用: %s" % p.relative_to(dist).as_posix())
    print("RESULT=%s" % ("FAIL" if bad else "PASS"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())