#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T18 — G6 封装准备：三件套打包脚本 + 排除规则 + 哈希回拉重算。

用法
----
  python scripts/_t18_pack.py                     # dry-run 报告（默认，不落盘）
  python scripts/_t18_pack.py --json out.json     # 同时写机器可读报告
  python scripts/_t18_pack.py --write             # 真正产出 zip + .sha256
  python scripts/_t18_pack.py --no-deterministic  # 关闭确定性时间戳

设计原则
--------
1. **规则表驱动**：每条排除规则都带 reason，报告里逐条打印 —— 可审计、可争辩。
2. **默认 dry-run**：zip 在内存（BytesIO）里构建，只算 sha256/大小，**不落盘**。
   加 --write 才真正产出 zip 与 .sha256 旁挂文件。
3. **确定性**：条目按路径排序、时间戳固定为 1980-01-01，保证「同输入同哈希」。
   这样「哈希回拉重算」才有意义：任何人重跑都能得到同一个 sha256。
4. **保护清单 PROTECTED 优先于任何排除规则**。存在的意义：web/dist 是单出口
   构建产物（captain 规则 3）**必须交付**，而一个天真的 "dist" 排除规则会把它
   误伤。保护清单让这条陷阱在结构上无法发生。
5. **只读三棵树**；唯一写操作是 --write 时的 zip 与 .sha256。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
import zipfile

# ---------------------------------------------------------------- 路径

DEFAULT_PKG = r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套"

TREES = [
    {"name": "TRPG-服务端", "zip": "TRPG-服务端.zip"},
    {"name": "TRPG-Web客户端", "zip": "TRPG-Web客户端.zip"},
    {"name": "TRPG-微信小程序客户端", "zip": "TRPG-微信小程序客户端.zip"},
]

# ---------------------------------------------------------------- 排除规则

# kind:
#   dir      —— 任意层级、目录名精确等于 pattern
#   suffix   —— 文件后缀（小写比较）
#   glob     —— 文件名（basename）匹配，用 fnmatch
#   rootglob —— 相对树根的路径匹配，用 fnmatch（可含 /）
#   rootfile —— 相对树根的路径精确等于 pattern

EXCLUDE_RULES = [
    # ---- 缓存与元数据（任意层级） ----
    {"kind": "dir", "pattern": "__pycache__", "reason": "Python 字节码缓存，可由 .py 重建"},
    {"kind": "dir", "pattern": ".pytest_cache", "reason": "pytest 运行缓存"},
    {"kind": "dir", "pattern": ".mypy_cache", "reason": "mypy 缓存"},
    {"kind": "dir", "pattern": ".ruff_cache", "reason": "ruff 缓存"},
    {"kind": "dir", "pattern": ".git", "reason": "版本库元数据，不属于交付内容"},
    {"kind": "dir", "pattern": ".hg", "reason": "版本库元数据"},
    {"kind": "dir", "pattern": ".svn", "reason": "版本库元数据"},
    {"kind": "dir", "pattern": ".idea", "reason": "IDE 工程配置"},
    {"kind": "dir", "pattern": ".vscode", "reason": "IDE 工程配置"},
    {"kind": "dir", "pattern": "node_modules", "reason": "依赖树，可由 package.json 重建（captain 规则 3）"},
    {"kind": "dir", "pattern": ".venv", "reason": "虚拟环境"},
    {"kind": "dir", "pattern": "venv", "reason": "虚拟环境"},
    {"kind": "dir", "pattern": "htmlcov", "reason": "覆盖率 HTML 产物"},
    {"kind": "dir", "pattern": ".tox", "reason": "tox 环境"},
    {"kind": "dir", "pattern": ".eggs", "reason": "构建中间产物"},

    # ---- 文件后缀 ----
    {"kind": "suffix", "pattern": ".pyc", "reason": "Python 字节码"},
    {"kind": "suffix", "pattern": ".pyo", "reason": "Python 字节码"},
    {"kind": "suffix", "pattern": ".pyd", "reason": "Python 扩展中间产物"},
    {"kind": "suffix", "pattern": ".log", "reason": "运行日志"},
    {"kind": "suffix", "pattern": ".tmp", "reason": "临时文件"},
    {"kind": "suffix", "pattern": ".swp", "reason": "编辑器交换文件"},
    {"kind": "suffix", "pattern": ".swo", "reason": "编辑器交换文件"},

    # ---- 备份与冲突残留（任意层级） ----
    # 注意：fnmatch 的 "*.bak" 只匹配**以 .bak 结尾**的名字，因此
    #   app/main.py.t7bak / app/main.py.t8bak 这类「.tNbak」后缀
    #   既不匹配 "*.bak" 也不匹配 "*.bak-*" —— 早期版本会把它俩放进包。
    #   已用 classify() 直测复现并补齐（captain 统一残留规则明确列出 *.t7bak / *.t8bak）。
    {"kind": "glob", "pattern": "*.bak", "reason": "备份文件（封装前应清理，不应进交付包）"},
    {"kind": "glob", "pattern": "*.bak-*", "reason": "备份文件（*.bak-t5 / *.bak-t13 等）"},
    {"kind": "glob", "pattern": "*bak-*", "reason": "备份文件兜底（覆盖 *.bak-t5 / *.bak-r2npc 等非 .bak 前缀写法）"},
    {"kind": "glob", "pattern": "*.t7bak", "reason": "T7 备份残留（如 app/main.py.t7bak）"},
    {"kind": "glob", "pattern": "*.t8bak", "reason": "T8 备份残留（如 app/main.py.t8bak）"},
    {"kind": "glob", "pattern": "*.t*bak", "reason": "任意 .tN bak 备份残留兜底"},
    {"kind": "glob", "pattern": "*.r2npc", "reason": "r2npc 备份残留（captain 统一残留规则）"},
    {"kind": "glob", "pattern": "*.t5bak", "reason": "T5 备份残留"},
    # ---- captain D2 细化：可变更类脚本不得随包交付 ----
    # 理由（captain 原文）：只读脚本是**证据链**（评审者可复算每个判据）；
    # 可变更脚本是**改文件工具**，不属交付物。实测本树内 11 个文件命中本类，
    # 早期版本全部漏放（INCLUDE）—— 已用 classify() 直测复现后补齐。
    {"kind": "glob", "pattern": "patch_*.py", "reason": "可变更类：改文件工具，不随包交付（captain D2）"},
    {"kind": "glob", "pattern": "_t*_patch.py", "reason": "可变更类：T* 补丁工具，不随包交付（captain D2）"},
    {"kind": "glob", "pattern": "*_test_serve.py", "reason": "调试用临时服务脚本（captain D2 残留清单）"},
    {"kind": "glob", "pattern": "*_test*.wav", "reason": "测试音频残留（captain D2 残留清单；data/ 之外也须拦）"},
    {"kind": "glob", "pattern": "*modpkg.tmp*", "reason": "原子写临时残留兜底（无连字符变体，captain D2 残留清单）"},
    {"kind": "glob", "pattern": "*~", "reason": "编辑器临时文件"},
    {"kind": "glob", "pattern": "*.orig", "reason": "合并冲突残留"},
    {"kind": "glob", "pattern": "*.rej", "reason": "合并冲突残留"},
    {"kind": "glob", "pattern": "*.tmp-*", "reason": "原子写临时残留（如 死光.modpkg.tmp-14976）"},

    # ---- 服务端：运行产物目录（树根一级） ----
    # 注意：必须用 rootdir（按树根一级目录名匹配并剪枝）。
    # 早期版本用 rootglob "run" 只匹配到路径恰好等于 "run" 的**文件**，
    # 结果 run/ 目录下的 11 个文件被漏放进了包 —— 已修正，并保留此注释防回退。
    {"kind": "rootdir", "pattern": "run", "reason": "服务端运行产物目录（进程句柄/日志）"},
    {"kind": "rootdir", "pattern": "run.*", "reason": "归档运行目录（run.arch-* 等）"},

    # ---- 服务端：树根一级的调试脚本与调试残留 ----
    {"kind": "rootglob", "pattern": "_t*.py", "reason": "树根一级的临时/调试脚本，应归入 scripts/ 或不交付"},
    {"kind": "rootglob", "pattern": "_r2_*", "reason": "调试残留（如 _r2_puttest.txt）"},
    {"kind": "rootglob", "pattern": "_*puttest*", "reason": "调试残留"},
]

# ---- 保护清单：命中即强制包含，优先级高于一切排除规则 ----
# 这一条是为了让「天真的 dist 排除」在结构上不可能误伤 GM 前端构建产物。
PROTECTED = [
    {"kind": "rootglob", "pattern": "web/dist/*", "reason": "GM 前端单出口构建产物，必须交付（captain 规则 3）"},
    {"kind": "rootglob", "pattern": "web/dist/**", "reason": "同上"},
    # ---- captain D-裁决（t18 D2/D3）后补充：前端的源码与静态资源同属交付物 ----
    # web/src、web/public 是前端**源码**（非构建产物），web/dist/keeper-ui 是随
    # dist 一起交付的独立 UI 子目录（106 文件 / 8 MB，captain 规则 4 明令不得被
    # vite build 清空）。三者都必须显式列入 PROTECTED，理由与 web/dist 相同：
    # 任何按名字做的天真排除（如 node_modules / src / public 通配）都不得误伤它们。
    {"kind": "rootglob", "pattern": "web/src/*", "reason": "前端源码，属交付物（captain D-裁决）"},
    {"kind": "rootglob", "pattern": "web/src/**", "reason": "同上"},
    {"kind": "rootglob", "pattern": "web/public/*", "reason": "前端静态资源源码，属交付物（captain D-裁决）"},
    {"kind": "rootglob", "pattern": "web/public/**", "reason": "同上"},
    {"kind": "rootglob", "pattern": "web/dist/keeper-ui/*", "reason": "keeper-ui 独立 UI 子目录，不得被 dist 排除误伤"},
    {"kind": "rootglob", "pattern": "web/dist/keeper-ui/**", "reason": "同上"},
]

# ---- 每棵树的附加策略 ----
# keep_only: 某目录下只交付这些（相对树根的精确路径）。None 表示不启用。
# extra_exclude: 该树独有的额外排除规则。
TREE_POLICY = {
    "TRPG-服务端": {
        "keep_only": {
            "data": ["data/.gitkeep"],
        },
        "extra_exclude": [
            {"kind": "rootglob", "pattern": "data/.repo_staging/*", "reason": "导入暂存目录（运行态）"},
            {"kind": "rootglob", "pattern": "data/audio_import/*", "reason": "音频导入缓存（运行态）"},
            {"kind": "rootglob", "pattern": "data/module_prep/*", "reason": "模组预处理缓存（运行态）"},
            {"kind": "rootglob", "pattern": "data/pipeline/*", "reason": "流水线中间产物（运行态）"},
        ],
        "keep_only_reason": "data/ 只交付 .gitkeep：其余是运行态（注册表、导入记录、暂存、缓存），交付后由首次运行重建",
    },
    "TRPG-Web客户端": {
        "keep_only": {},
        "extra_exclude": [
            {"kind": "rootglob", "pattern": "run/*", "reason": "本地预览运行目录"},
        ],
    },
    "TRPG-微信小程序客户端": {
        "keep_only": {},
        "extra_exclude": [],
    },
}

# ---- 自检断言：必备项必须进包，禁项必须不进包 ----
# 支持两种写法：{"pattern": fnmatch 模式} 或 {"segment": 路径段名}
REQUIRED = {
    "TRPG-服务端": [
        {"pattern": "app/main.py", "why": "服务端入口（含 repo 中间件与错误码桥接）"},
        {"pattern": "app/web/ws_protocol.py", "why": "冻结的 WS 契约（8 帧）"},
        {"pattern": "app/domain/events.py", "why": "冻结的事件类型表"},
        {"pattern": "app/hotreload/watcher.py", "why": "T5 热重载"},
        {"pattern": "app/web/rest_hotreload.py", "why": "T5 热重载 REST 路由"},
        {"pattern": "web/dist/index.html", "why": "GM 前端单出口构建产物入口（captain 规则 3）"},
        {"pattern": "modules/dead_light/module.yaml", "why": "T5 模组"},
        {"pattern": "modules/dead_light/compiled/dead_light.compiled.json", "why": "T5 自建等价结构"},
        {"pattern": "modules/blackwater_creek/module.yaml", "why": "既有模组"},
        {"pattern": "modpacks/死光.modpkg", "why": "T5 单文件容器（R24 一键下载的产物）"},
        {"pattern": "docs/CROSS-END-CONTRACT.md", "why": "跨端契约"},
        {"pattern": "rulepacks/coc7/rulepack.yaml", "why": "规则包"},
        {"pattern": "requirements.txt", "why": "依赖清单"},
        {"pattern": "wheels/*.whl", "why": "离线安装轮子"},
    ],
    "TRPG-Web客户端": [
        {"pattern": "client/index.html", "why": "客户端入口"},
        {"pattern": "client/strings.json", "why": "DEFECT-001 镜像不变量的一方"},
        {"pattern": "client/app.js", "why": "客户端逻辑"},
    ],
    "TRPG-微信小程序客户端": [
        {"pattern": "app.json", "why": "小程序入口配置"},
        {"pattern": "strings.json", "why": "固定文案（契约 §5）"},
        {"pattern": "pages/table/table.js", "why": "主页面"},
    ],
}

FORBIDDEN = {
    "TRPG-服务端": [
        {"segment": "__pycache__", "why": "字节码缓存"},
        {"pattern": "*.pyc", "why": "字节码"},
        {"pattern": "*.bak-t5", "why": "备份文件"},
        {"pattern": "*.bak-t13", "why": "备份文件"},
        {"segment": "node_modules", "why": "依赖树（captain 规则 3）"},
        {"segment": ".pytest_cache", "why": "pytest 缓存"},
        {"segment": "run", "why": "运行产物目录"},
        {"pattern": "*.tmp-*", "why": "原子写临时残留"},
        {"pattern": "_t7_*.py", "why": "他人调试脚本（根一级）"},
        {"pattern": "data/pipeline/*", "why": "流水线中间产物"},
        {"pattern": "*.log", "why": "运行日志"},
    ],
    "TRPG-Web客户端": [
        {"segment": "__pycache__", "why": "字节码缓存"},
        {"segment": "node_modules", "why": "依赖树"},
        {"segment": "run", "why": "本地预览运行目录"},
        {"pattern": "*.bak-t13", "why": "备份文件"},
        {"pattern": "*.log", "why": "运行日志"},
    ],
    "TRPG-微信小程序客户端": [
        {"pattern": "*.bak-t5", "why": "备份文件"},
        {"segment": "__pycache__", "why": "字节码缓存"},
    ],
}


# ---- 需要队长裁决的决策点（脚本不擅自决定，只在报告里列出影响面） ----
DECISIONS = [
    {
        "id": "D1",
        "question": "tests/ 是否随交付包发布？",
        "old_policy": "不交付（旧 zip 里 tests/ 条目数为 0）",
        "script_default": "交付",
        "why": "tests/ 是「验证已发生」的证据，评审方通常希望看到；且体积小。"
               "但旧打包策略把它排除了。",
    },
    {
        "id": "D2",
        "question": "scripts/ 下的一次性取证脚本（_t1_evidence.py / _t5_evidence.py）是否交付？",
        "old_policy": "不交付（旧 zip 只含 _serve.py / start.ps1 / stop.ps1）",
        "script_default": "交付",
        "why": "它们是证据文档里逐条命令的来源，交付可复现；但属工具而非运行所需。",
    },
    {
        "id": "D3",
        "question": "npc-demo/ 是否交付？",
        "old_policy": "不交付",
        "script_default": "交付",
        "why": "单个 index.html，可能是演示件；若已废弃应删除而不是靠排除规则隐藏。",
    },
    {
        "id": "D4",
        "question": "服务端树根一级的 _t7_e2e.py / _t7_modcheck.py / _t7_patch.py 如何处理？",
        "old_policy": "不存在（后加的）",
        "script_default": "排除",
        "why": "属他人调试脚本；建议由作者决定移入 scripts/ 还是删除，脚本只负责不让它进包。",
    },
    {
        "id": "D5",
        "question": "死光.modpkg.tmp-14976 等原子写残留由谁清理？",
        "old_policy": "不存在（后加的）",
        "script_default": "排除",
        "why": "疑似 T5 打包原子写的残留；排除只是不让它进包，磁盘上仍需作者清理。",
    },
]

# ---------------------------------------------------------------- 匹配

import fnmatch


def _norm(rel: str) -> str:
    return rel.replace(os.sep, "/")


def _match(rule: dict, rel: str, is_dir: bool) -> bool:
    kind = rule["kind"]
    pat = rule["pattern"]
    rel = _norm(rel)
    base = rel.rsplit("/", 1)[-1]
    parts = rel.split("/")
    if kind == "dir":
        return is_dir and base == pat
    if kind == "suffix":
        return (not is_dir) and base.lower().endswith(pat)
    if kind == "glob":
        return (not is_dir) and fnmatch.fnmatch(base, pat)
    if kind == "rootglob":
        return fnmatch.fnmatch(rel, pat)
    if kind == "rootfile":
        return rel == pat
    if kind == "rootdir":
        # 树根一级目录名匹配：命中则该目录整棵子树都不交付
        return parts[0] == pat or fnmatch.fnmatch(parts[0], pat)
    raise ValueError("unknown rule kind: %s" % kind)


def classify(rel: str, tree: str, rules: list) -> tuple:
    """返回 (是否包含, 命中规则或 None)。PROTECTED 优先。"""
    is_dir = False
    for r in PROTECTED:
        if _match(r, rel, is_dir):
            return True, {"protected": True, "reason": r["reason"]}
    policy = TREE_POLICY.get(tree, {})
    # keep_only：该目录下只交付白名单
    for d, allowed in (policy.get("keep_only") or {}).items():
        if _norm(rel) == d or _norm(rel).startswith(d + "/"):
            if _norm(rel) in [_norm(a) for a in allowed]:
                return True, None
            return False, {"reason": policy.get("keep_only_reason", "keep_only 白名单外"), "rule": "keep_only:" + d}
    for r in rules:
        if _match(r, rel, is_dir):
            return False, r
    return True, None


def collect(root: str, tree: str) -> tuple:
    """遍历一棵树，返回 (included, excluded, prune_dirs)。"""
    rules = list(EXCLUDE_RULES) + list(TREE_POLICY.get(tree, {}).get("extra_exclude", []))
    included, excluded = [], []
    dir_rule_names = {r["pattern"] for r in rules if r["kind"] == "dir"}
    rootdir_rules = [r for r in rules if r["kind"] == "rootdir"]
    pruned = []          # 被整棵剪掉的目录（含其下文件数）
    for dp, dns, fns in os.walk(root):
        # 剪枝：整目录命中的直接跳过
        keep = []
        for d in dns:
            rel = _norm(os.path.relpath(os.path.join(dp, d), root))
            hit = None
            if d in dir_rule_names:
                hit = {"reason": "目录名命中排除规则", "rule": "dir:" + d}
            else:
                for r in rootdir_rules:
                    if _match(r, rel, True):
                        hit = r
                        break
            if hit:
                n = sum(len(f) for _, _, f in os.walk(os.path.join(dp, d)))
                pruned.append((rel + "/", hit, n))
                continue
            keep.append(d)
        dns[:] = keep
        for f in fns:
            rel = _norm(os.path.relpath(os.path.join(dp, f), root))
            ok, why = classify(rel, tree, rules)
            if ok:
                included.append(rel)
            else:
                excluded.append((rel, why, os.path.getsize(os.path.join(dp, f))))
    return sorted(included), excluded, pruned


# ---------------------------------------------------------------- 打包

FIXED_DT = (1980, 1, 1, 0, 0, 0)


def build_zip_bytes(root: str, tree: str, files: list, deterministic: bool = True) -> bytes:
    """在内存里构建 zip，返回字节。deterministic=True 时时间戳固定、条目排序。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in (sorted(files) if deterministic else files):
            src = os.path.join(root, rel.replace("/", os.sep))
            arc = tree + "/" + rel
            if deterministic:
                zi = zipfile.ZipInfo(arc, date_time=FIXED_DT)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                with open(src, "rb") as fh:
                    zf.writestr(zi, fh.read())
            else:
                zf.write(src, arc)
    return buf.getvalue()


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_sidecar(p: str):
    if not os.path.isfile(p):
        return None
    txt = open(p, "rb").read().decode("utf-8", "replace").strip()
    return txt.split()[0] if txt else None


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", default=DEFAULT_PKG)
    ap.add_argument("--json", default=None, help="把机器可读报告写到该路径")
    ap.add_argument("--write", action="store_true", help="真正产出 zip 与 .sha256（默认 dry-run）")
    ap.add_argument("--no-deterministic", action="store_true")
    args = ap.parse_args()

    pkg = args.pkg
    det = not args.no_deterministic
    mode = "WRITE" if args.write else "DRY-RUN"

    print("=" * 86)
    print("T18 G6 封装准备 — 三件套打包 dry-run 报告")
    print("  模式        : %s%s" % (mode, "" if args.write else "（不产出 zip，只在内存构建并算哈希）"))
    print("  交付包根    : %s" % pkg)
    print("  确定性打包  : %s（条目排序 + 时间戳固定 1980-01-01）" % det)
    print("  时间        : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 86)

    report = {"pkg": pkg, "mode": mode, "deterministic": det,
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "trees": [], "decisions": DECISIONS}

    for t in TREES:
        name, zname = t["name"], t["zip"]
        root = os.path.join(pkg, name)
        if not os.path.isdir(root):
            print("!! 缺少目录: %s" % root)
            continue
        included, excluded, pruned = collect(root, name)
        inc_bytes = sum(os.path.getsize(os.path.join(root, p.replace("/", os.sep))) for p in included)
        exc_bytes = sum(e[2] for e in excluded if isinstance(e[2], int))
        pruned_files = sum(p[2] for p in pruned)
        total_files = len(included) + len(excluded) + pruned_files

        blob = build_zip_bytes(root, name, included, det)
        digest = hashlib.sha256(blob).hexdigest()

        zpath = os.path.join(pkg, zname)
        spath = zpath + ".sha256"
        old_digest = read_sidecar(spath)
        old_size = os.path.getsize(zpath) if os.path.isfile(zpath) else None
        old_names = None
        if os.path.isfile(zpath):
            try:
                with zipfile.ZipFile(zpath) as zf:
                    pref = name + "/"
                    old_names = set(n[len(pref):] for n in zf.namelist()
                                    if n.startswith(pref) and not n.endswith("/"))
            except Exception as e:  # noqa
                print("  (旧 zip 读取失败: %s)" % e)

        print()
        print("-" * 86)
        print("【%s】" % name)
        print("-" * 86)
        print("  树内文件      : %d（含被整目录剪枝的 %d）" % (total_files, pruned_files))
        print("  将交付        : %d 个文件 / %d B（原始未压缩）" % (len(included), inc_bytes))
        print("  将排除        : %d 项 + %d 个整目录剪枝项 / %d B" % (len(excluded), len(pruned), exc_bytes))
        print("  预计 zip      : %d B" % len(blob))
        print("  预计 sha256   : %s" % digest)
        if old_digest:
            same = "一致" if old_digest == digest else "**不一致（现有 zip 已过期）**"
            print("  现有 .sha256  : %s  -> %s" % (old_digest, same))
        if old_size:
            print("  现有 zip 大小 : %d B" % old_size)
        if old_names is not None:
            inc_set = set(included)
            stale = sorted(old_names - inc_set)
            added = sorted(inc_set - old_names)
            print("  与现有 zip 比 : 现有 %d 条，新增 %d，陈旧（zip 里有、树里已无）%d"
                  % (len(old_names), len(added), len(stale)))
            if stale:
                from collections import Counter
                c = Counter(s.rsplit("/", 1)[0] if "/" in s else "<root>" for s in stale)
                print("     陈旧条目按目录:")
                for k, v in sorted(c.items(), key=lambda kv: -kv[1])[:8]:
                    print("       %-46s %4d" % (k, v))
                for s in stale[:5]:
                    print("       e.g. %s" % s)
            if added:
                from collections import Counter
                c = Counter(a.rsplit("/", 1)[0] if "/" in a else "<root>" for a in added)
                print("     新增条目按目录:")
                for k, v in sorted(c.items(), key=lambda kv: -kv[1])[:8]:
                    print("       %-46s %4d" % (k, v))

        # 逐规则统计
        from collections import Counter
        rc = Counter()
        for rel, why, _sz in excluded:
            if why and why.get("protected"):
                continue
            rc[(why or {}).get("rule") or (why or {}).get("reason", "?")] += 1
        for rel, why, n in pruned:
            rc[(why or {}).get("rule") or (why or {}).get("reason", "?")] += 1
        if rc:
            print("  排除规则命中统计:")
            for k, v in sorted(rc.items(), key=lambda kv: -kv[1]):
                print("     %-52s %5d" % (k, v))

        # ---- 自检断言：必备项在不在、禁项有没有混进来 ----
        inc_set_all = set(included)
        checks = []
        def _hits(spec):
            if "segment" in spec:
                seg = spec["segment"]
                return any(seg in p.split("/") for p in inc_set_all)
            return any(fnmatch.fnmatch(p, spec["pattern"]) for p in inc_set_all)

        for req in REQUIRED.get(name, []):
            checks.append((_hits(req), "REQUIRED", req.get("pattern") or req.get("segment"), req["why"]))
        for forb in FORBIDDEN.get(name, []):
            checks.append((not _hits(forb), "FORBIDDEN", forb.get("pattern") or forb.get("segment"), forb["why"]))
        bad = [c for c in checks if not c[0]]
        print("  自检断言      : %d 条, %s" % (len(checks), "全部通过" if not bad else "**%d 条不通过**" % len(bad)))
        for ok, kind, pat, why in checks:
            print("     [%s] %-9s %-40s %s" % ("OK" if ok else "!!", kind, pat, why))

        # 哈希回拉：即将写入的 .sha256 内容
        sidecar_text = "%s  %s\n" % (digest, zname)
        print("  哈希回拉（将写入 %s）:" % (zname + ".sha256"))
        print("     %r" % sidecar_text)
        if args.write:
            with open(zpath, "wb") as fh:
                fh.write(blob)
            with open(spath, "wb") as fh:
                fh.write(sidecar_text.encode("utf-8"))
            print("     -> 已写入 zip 与 .sha256")

        report["trees"].append({
            "tree": name, "zip": zname, "included": len(included),
            "included_bytes": inc_bytes, "excluded": len(excluded),
            "zip_bytes": len(blob), "sha256": digest,
            "old_sha256": old_digest, "old_zip_bytes": old_size,
            "changed": (old_digest != digest),
            "stale_in_old_zip": (len(old_names - set(included)) if old_names is not None else None),
            "new_vs_old_zip": (len(set(included) - old_names) if old_names is not None else None),
            "rule_hits": dict(rc),
            "pruned_dirs": len(pruned),
            "total_files": total_files,
            "assertions": [{"ok": c[0], "kind": c[1], "pattern": c[2], "why": c[3]} for c in checks],
        })

    # ---- 决策点 ----
    print()
    print("=" * 86)
    print("待队长裁决的决策点（脚本不擅自决定，只列影响面）")
    print("=" * 86)
    for d in DECISIONS:
        print("  [%s] %s" % (d["id"], d["question"]))
        print("       旧策略      : %s" % d["old_policy"])
        print("       脚本默认    : %s" % d["script_default"])
        print("       说明        : %s" % d["why"])
    print()
    print("  注：D1/D2/D3 的默认值与旧打包策略不同 —— 这是**有意偏离**，"
          "因为旧 zip 构建于 03:49，其后三棵树都有大量新增。")

    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        print("\n机器可读报告已写入: %s" % args.json)

    print()
    print("=" * 86)
    print("EXIT=0  %s" % ("已落盘" if args.write else "DRY-RUN：未产出任何 zip，交付包未被改动"))
    print("=" * 86)
    return 0


if __name__ == "__main__":
    sys.exit(main())
