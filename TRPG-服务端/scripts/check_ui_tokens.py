#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_ui_tokens.py —— R32 三端令牌一致性校验（可复现证据工具）

用法（在 TRPG-服务端 目录下）：
    python scripts/check_ui_tokens.py

校验对象（唯一令牌源 = tokens.json v2.0）：
  1. TRPG-服务端/player-web/tokens.json
  2. TRPG-Web客户端/client/tokens.json          （必须与 1 逐字节一致）
  3. TRPG-服务端/player-web/app.css 的 :root{}
  4. TRPG-Web客户端/client/app.css 的 :root{}    （必须与 3 逐字节一致）
  5. TRPG-微信小程序客户端/tokens.wxss 的 page{}
  6. TRPG-微信小程序客户端/tokens.wxss 的驼峰别名块（契约 §2 键名）

另附「目录镜像不变量」（captain 裁决，强制）：
  7. TRPG-服务端/player-web/  与  TRPG-Web客户端/client/
     整目录逐字节镜像 —— 文件名集合相同，且每个文件 sha256 相同。
     断言范围**自动发现**（当前 6 个文件：app.js / app.css / tokens.json /
     strings.json / index.html / README.md），任一文件增删或内容分叉都会 FAIL。

另附「strings.json 三端一致性」（captain 纪律 D）：
  8. TRPG-服务端/player-web/strings.json
     TRPG-Web客户端/client/strings.json
     TRPG-微信小程序客户端/strings.json
     三处**键集合必须一致**（依据 docs/ROADMAP-DEFERRED.md「不允许一端有一端无」），
     并同时报告是否逐字节相同。任一端缺键/多键都会 FAIL。

另附「R32 GM 主题覆盖层：可复算不变量」（captain 验收规范第 4 条）：
  9. 断言**可复算性**，不断言观测值 ——
     · 不变量：web/dist/assets/theme-cnmods.css 必须与源码真源
       web/public/assets/theme-cnmods.css **逐字节相同**（对重建免疫）；
     · 不变量：web/dist/index.html 必须含主题 <link>，且它**排在 bundle CSS 之后**
       （顺序不变量，R32 靠"后加载覆盖"生效，不用 !important）；
     · 哈希只作**时点观测值**记录，绝不硬编码为断言。

哈希纪律（captain 纪律 E）：本脚本所有 sha256 均由 sha256() 直接计算，
  绝不手抄；输出附 64 长度自检（HASH_LEN_OK）。

退出码：0 = 全部一致；1 = 存在不一致。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

# 输出编码：SSH/非 UTF-8 控制台会把中文路径显示成乱码（判据不受影响，只是不耐看）。
# 这里只改【标准输出】的编码，不改任何文件、不影响任何断言。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")   # Python 3.7+
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent                      # TRPG-服务端
PKG_ROOT = APP_ROOT.parent                  # TRPG-交付包-三件套

P_TOKENS_JSON = APP_ROOT / "player-web" / "tokens.json"
P_APP_CSS = APP_ROOT / "player-web" / "app.css"
C_TOKENS_JSON = PKG_ROOT / "TRPG-Web客户端" / "client" / "tokens.json"
C_APP_CSS = PKG_ROOT / "TRPG-Web客户端" / "client" / "app.css"
P_DIR = APP_ROOT / "player-web"
C_DIR = PKG_ROOT / "TRPG-Web客户端" / "client"
MP_TOKENS_WXSS = PKG_ROOT / "TRPG-微信小程序客户端" / "tokens.wxss"

# R32 GM 主题覆盖层：源码真源 vs 构建产物（captain 验收规范第 4 条，只断言可复算性）
WEB_ROOT = APP_ROOT / "web"
GM_THEME_SRC = WEB_ROOT / "public" / "assets" / "theme-cnmods.css"
GM_THEME_DIST = WEB_ROOT / "dist" / "assets" / "theme-cnmods.css"
GM_INDEX = WEB_ROOT / "dist" / "index.html"
GM_THEME_LINK = '<link rel="stylesheet" href="/app/assets/theme-cnmods.css">'

# 覆盖层的【内容语义】锚点（gmui 建议：这是最容易被构建误伤的资产）。
# 为什么不能只靠「dist == public」：若某次构建把 public 真源本身重新生成为别的主题，
# 两端会一起变，那条断言照样 PASS —— 那正是最危险的静默破坏。
# 本表锚定令牌【名与值】，对重建免疫，对内容替换敏感。
OVERLAY_REQUIRED = {
    "--bg": "#101014",
    "--card": "#141c23",
    "--muted": "#b9b9b9",
    "--border": "rgba(255, 255, 255, 0.24)",
    "--focus": "#ffbb70",
    "--trpg-accent": "#ffbb70",
    "--trpg-accent-hover": "#fac583",
    "--trpg-accent-pressed": "#dba45e",
    "--trpg-ink": "#3d1b00",
    "--trpg-err": "#e88080",
    "--trpg-card-translucent": "rgba(20, 28, 35, 0.73)",
    "--trpg-blur": "8px",
    "--trpg-shadow-none": "none",
    "--trpg-radius-card": "4px",
    "--trpg-radius-ctl": "3px",
    "--trpg-radius-chip": "2px",
}

# 覆盖层锚点 -> tokens.json 真源键（**独立见证**）。
#
# 为什么需要它：OVERLAY_REQUIRED 本身是【手写常量】。若我抄错一个值，
# 覆盖层检查与真实主题会一起错、且互相印证为绿 —— 那是「单一事实来源 = 我的手」。
# 把每个锚点绑到 tokens.json 的对应键后，同一结论有【两个不同产物的见证】：
#   theme-cnmods.css（CSS 覆盖层） 与 tokens.json（设计令牌真源，由不同流程产出）
# 想静默替换主题，必须同时、且一致地改坏两者 —— 难度与可发现性都显著上升。
# 它也让我抄错时【立刻报红】，而不是把错值固化成新基准。
ANCHOR_SOURCE = {
    "--bg": "color.bg",
    "--card": "color.card",
    "--muted": "color.muted",
    "--border": "color.border",
    "--focus": "color.focus",
    "--trpg-accent": "color.accent",
    "--trpg-accent-hover": "color.accentHover",
    "--trpg-accent-pressed": "color.accentPressed",
    "--trpg-ink": "color.accentText",
    "--trpg-err": "color.err",
    "--trpg-card-translucent": "color.cardTranslucent",
    "--trpg-blur": "layout.blur",
    "--trpg-shadow-none": "shadow.none",
    "--trpg-radius-card": "radius.card",
    "--trpg-radius-ctl": "radius.ctl",
    "--trpg-radius-chip": "radius.chip",
}


def _norm_css_value(v) -> str:
    """CSS 值比较前归一：去掉全部空白。
    例: 'rgba(255, 255, 255, 0.24)' == 'rgba(255,255,255,0.24)'
    只归一【空白】，不做任何数值/颜色等价换算 —— 换算会掩盖真实差异。
    """
    return re.sub(r"\s+", "", str(v))


def tokens_json_flat() -> dict:
    """把 tokens.json 展平成点分键（如 color.bg）。取不到则返回 {}。"""
    p = P_DIR / "tokens.json"
    if not p.is_file():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    out = {}

    def walk(o, pre=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, pre + str(k) + ".")
        elif not isinstance(o, list):
            out[pre[:-1]] = o

    walk(obj)
    return out


def anchor_source_report() -> tuple:
    """断言：每个覆盖层锚点都必须有一个 tokens.json 独立见证，且两者逐值相等。"""
    rows, bad = [], 0

    # 4a. 覆盖面：锚点集与见证表必须【完全对应】—— 新加锚点不许没有见证。
    no_witness = sorted(set(OVERLAY_REQUIRED) - set(ANCHOR_SOURCE))
    no_anchor = sorted(set(ANCHOR_SOURCE) - set(OVERLAY_REQUIRED))
    cover_ok = not no_witness and not no_anchor
    rows.append(("锚点见证覆盖", "OK" if cover_ok else "BAD",
                 f"锚点={len(OVERLAY_REQUIRED)} 见证={len(ANCHOR_SOURCE)}"
                 + (f" 无见证={no_witness}" if no_witness else "")
                 + (f" 见证无锚点={no_anchor}" if no_anchor else "")))
    if not cover_ok:
        bad += 1

    flat = tokens_json_flat()
    if not flat:
        rows.append(("锚点 <- tokens.json 独立见证", "SKIPPED", "tokens.json 不可读"))
        return rows, bad

    mismatch = []
    for name, src in sorted(ANCHOR_SOURCE.items()):
        if src not in flat:
            mismatch.append(f"{name}<-{src} 键缺失")
            continue
        if _norm_css_value(flat[src]) != _norm_css_value(OVERLAY_REQUIRED[name]):
            mismatch.append(f"{name}={OVERLAY_REQUIRED[name]} != {src}={flat[src]}")
    ok = not mismatch
    rows.append(("锚点 <- tokens.json 独立见证", "OK" if ok else "BAD",
                 f"见证={len(ANCHOR_SOURCE)} 值不符={len(mismatch)}"
                 + (("  例: " + "; ".join(mismatch[:3])) if not ok else "")))
    if not ok:
        bad += 1
    return rows, bad

# strings.json 三端共 3 个副本（captain 纪律 D）：键集合必须一致。
STRINGS_FILES = {
    "player-web": APP_ROOT / "player-web" / "strings.json",
    "client": PKG_ROOT / "TRPG-Web客户端" / "client" / "strings.json",
    "miniprogram": PKG_ROOT / "TRPG-微信小程序客户端" / "strings.json",
}

# tokens.json 键 -> 小程序契约驼峰变量名（None = 无驼峰别名）
CONTRACT_ALIAS = {
    "color.accentText": "--color-accentText",
    "color.chipBg": "--color-chipBg",
    "color.errBarBg": "--color-errBarBg",
    "color.errBarBorder": "--color-errBarBorder",
    "layout.maxWidth": "--layout-maxWidth",
    "layout.navHeight": "--layout-navHeight",
    "layout.tapMin": "--layout-tapMin",
}


def camel_to_kebab(name: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name).lower()


def var_name(group: str, key: str) -> str:
    if group == "font" and key == "stack":
        return "--font-stack"
    if group == "shadow" and key == "focusGlow":
        return "--focus-glow"
    return f"--{group}-{camel_to_kebab(key)}"


def parse_block(text: str, selector: str) -> dict:
    """取第一个 <selector>{...} 块内的自定义属性。"""
    idx = text.find(selector)
    if idx < 0:
        return {}
    end = text.find("}", idx)
    body = text[idx + len(selector):end]
    out = {}
    for m in re.finditer(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);", body):
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def parse_all_blocks(text: str, selector: str) -> dict:
    out = {}
    for m in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", text):
        for d in re.finditer(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);", m.group(1)):
            out[d.group(1).strip()] = d.group(2).strip()
    return out


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel_files(d: Path) -> dict:
    """递归收集目录下所有文件，键 = 相对 POSIX 路径（含子目录）。

    为什么必须递归：只比顶层文件时，【新增一个子目录】或【子目录内新增/删除文件】
    这一整类单边差异会被【静默忽略】，而检查器仍打印 MIRROR_FILES=N DIFF=0。
    """
    out = {}
    for p in sorted(d.rglob("*")):
        if p.is_file():
            out[p.relative_to(d).as_posix()] = p
    return out


def mirror_report() -> tuple:
    """目录镜像不变量：player-web/ 与 client/ 必须整目录逐字节相同。

    文件名集合**自动发现**（不硬编码名字），且**递归**（子目录同样覆盖）。
    任一目录新增 / 删除 / 改内容都会被捕获 —— 「多一个」和「少一个」同样报红。
    """
    fa, fb = rel_files(P_DIR), rel_files(C_DIR)
    rows, bad = [], 0
    for name in sorted(set(fa) | set(fb)):
        pa, pb = fa.get(name), fb.get(name)
        if pa is None or pb is None:
            rows.append((name, "<only-b>" if pa is None else "<missing>",
                         "<only-a>" if pb is None else "<missing>", "ONE-SIDE-ONLY"))
            bad += 1
            continue
        ha, hb = sha256(pa), sha256(pb)
        ok = ha == hb
        if not ok:
            bad += 1
        rows.append((name, ha[:16], hb[:16], "IDENTICAL" if ok else "DIFFERENT"))
    return rows, bad


def flatten_keys(obj, prefix: str = "") -> set:
    """递归收集 JSON 的全部键路径（用于三端键集合比对）。"""
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(prefix + str(k))
            out |= flatten_keys(v, prefix + str(k) + ".")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out |= flatten_keys(v, prefix + str(i) + ".")
    return out


def strings_report() -> tuple:
    """strings.json 三端一致性：键集合必须一致，并报告是否逐字节相同。"""
    loaded, rows, bad = {}, [], 0
    for label, p in STRINGS_FILES.items():
        if not p.is_file():
            rows.append((label, "<missing>", -1, -1, "MISSING"))
            bad += 1
            continue
        raw = p.read_bytes()
        h = sha256(p)
        try:
            keys = flatten_keys(json.loads(raw.decode("utf-8-sig")))
        except Exception as exc:  # noqa: BLE001
            rows.append((label, h[:16], len(raw), -1, "PARSE-FAIL: " + str(exc)[:40]))
            bad += 1
            continue
        loaded[label] = (h, len(raw), keys)
        rows.append((label, h[:16], len(raw), len(keys), "ok"))

    labels = list(loaded.keys())
    key_bad = 0
    if len(labels) >= 2:
        base = labels[0]
        for other in labels[1:]:
            if loaded[base][2] != loaded[other][2]:
                key_bad += 1
    byte_identical = len({v[0] for v in loaded.values()}) == 1 and len(loaded) == len(STRINGS_FILES)
    bad += key_bad
    return rows, bad, key_bad, byte_identical


def gm_theme_report() -> tuple:
    """R32 GM 主题覆盖层：断言可复算性，不断言观测值（验收规范第 4 条）。

    返回 (rows, bad, skipped)。rows 每项 = (断言名, 结果, 说明)。
    """
    if not WEB_ROOT.is_dir():
        return [], 0, True
    rows, bad = [], 0

    # 断言 1（不变量）：源码真源 与 dist 产物逐字节相同 —— 对重建免疫
    if GM_THEME_SRC.is_file() and GM_THEME_DIST.is_file():
        same = GM_THEME_SRC.read_bytes() == GM_THEME_DIST.read_bytes()
        rows.append(("dist == public (逐字节)", "IDENTICAL" if same else "DIFFERENT",
                     f"{GM_THEME_DIST.stat().st_size}B vs {GM_THEME_SRC.stat().st_size}B"))
        if not same:
            bad += 1
    elif GM_THEME_DIST.is_file() and not GM_THEME_SRC.is_file():
        # dist 里有产物但源码真源缺失 -> 下次重建必被 emptyOutDir 静默删除
        rows.append(("源码真源存在", "MISSING", "web/public/assets/theme-cnmods.css 不存在，重建会静默删掉覆盖层"))
        bad += 1
    else:
        return rows, bad, True   # 两端都没有：非 GM 部署形态，跳过

    # 断言 2（不变量）：dist/index.html 含主题 link
    if GM_INDEX.is_file():
        html = GM_INDEX.read_text(encoding="utf-8", errors="replace")
        has_link = GM_THEME_LINK in html
        rows.append(("index.html 含主题 <link>", "yes" if has_link else "NO", ""))
        if not has_link:
            bad += 1
        # 断言 3（不变量）：主题 link 必须排在 bundle CSS link 之后
        ti = html.find(GM_THEME_LINK)
        bi = html.find("/app/assets/index-")
        if ti >= 0 and bi >= 0:
            ordered = ti > bi
            rows.append(("主题 <link> 在 bundle CSS 之后", "yes" if ordered else "NO",
                         "顺序决定 R32 是否生效（同优先级后加载者胜）"))
            if not ordered:
                bad += 1
        else:
            rows.append(("主题 <link> 在 bundle CSS 之后", "n/a", "缺少可比对的 bundle CSS link"))
            bad += 1
    else:
        rows.append(("index.html 存在", "MISSING", str(GM_INDEX)))
        bad += 1

    # 断言 4（不变量）：覆盖层仍是「魔都」令牌层 —— 防构建把【真源】覆盖成别的主题
    for label, p in (("public", GM_THEME_SRC), ("dist", GM_THEME_DIST)):
        if not p.is_file():
            continue
        raw = p.read_text(encoding="utf-8", errors="replace")
        found = {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[A-Za-z0-9-]+)\s*:\s*([^;]+);", raw)}
        missing = [n for n in OVERLAY_REQUIRED if n not in found]
        wrong = [f"{n}={found[n]}!={OVERLAY_REQUIRED[n]}" for n in OVERLAY_REQUIRED if n in found and found[n] != OVERLAY_REQUIRED[n]]
        okay = not missing and not wrong
        rows.append((f"覆盖层令牌语义 ({label})", "OK" if okay else "BAD",
                     f"锚点={len(OVERLAY_REQUIRED)} 缺失={len(missing)} 值不符={len(wrong)}"
                     + (("  例: " + "; ".join((missing + wrong)[:3])) if not okay else "")))
        if not okay:
            bad += 1

    # 断言 5（不变量）：每个锚点都必须有 tokens.json 独立见证（见 ANCHOR_SOURCE 注释）。
    # 这条把「我的手写常量」从唯一事实来源降级为「两个产物共同见证的结论」。
    arows, abad = anchor_source_report()
    rows.extend(arows)
    bad += abad

    return rows, bad, False



def cache_header_report() -> tuple:
    """静态资源的缓存头部策略（补 gmui 报的 I8d 缺口：其门禁里该条为死代码）。

    FAIL 判据【只取一条】：构建产物路径上 Cache-Control **缺失**。
    理由：缺失时浏览器可对响应施加【启发式新鲜度】（约 10% of age），
          可能不向服务端发条件请求 —— 这正是「改了文件但浏览器跑旧版」的唯一真实机制。
    不作 FAIL 的: no-cache（可协商，304，最好）/ no-store（永不陈旧，只是低效）。
    服务端不可达时 SKIPPED —— 本脚本原本纯文件检查，不强制依赖运行中的服务。
    """
    rows, bad = [], 0
    try:
        import httpx
    except Exception:
        rows.append(("缓存头部策略", "SKIPPED", "无 httpx"))
        return rows, bad
    base = os.environ.get("TRPG_BASE") or "http://127.0.0.1:9211"
    # (URL 路径, 磁盘文件) —— 磁盘文件用于【兜底识别】
    # tester 定稿判据: /app/ 下 HTTP 200 对路径存在性【信息量为 0】。
    #   判定存在须：响应体与磁盘同路径文件【逐字节/sha256 相等】
    #   （长度相等是必要不充分）。或先探一条【本次随机生成】的确定不存在路径作对照。
    # 字节不符 => 该行拿到的可能是 SPA 兜底文档 => 【不据此行判定缓存头部】。
    srv_root = Path(__file__).resolve().parent.parent
    web, pw = srv_root / "web", srv_root / "player-web"
    targets = [
        ("/app/", web / "dist" / "index.html"),
        ("/app/assets/theme-cnmods.css", web / "dist" / "assets" / "theme-cnmods.css"),
        ("/player/", pw / "index.html"),
        ("/player/app.js", pw / "app.js"),
        ("/player/strings.json", pw / "strings.json"),
    ]
    absent, seen, notreal = [], [], []
    ctrl_dig = None
    try:
        with httpx.Client(base_url=base, timeout=8, follow_redirects=False) as c:
            # 本次随机对照：确定不存在的路径（固定串用久了会失去对照意义）
            # 【必须在 /app/ 前缀下】—— 兜底是 /app 挂载的行为；根路径同样串会 404，
            # 那样对照哈希是 404 响应体，永远匹配不上任何目标 => 探测器静默失效。
            cr = c.get("/app/__ctrl_%d_%d__/" % (os.getpid(), int(time.time() * 1000) % 1000000))
            ctrl_dig = hashlib.sha256(cr.content).hexdigest().lower()
            # 对照自证：对照本身必须【确实拿到兜底文档】，否则本探测器无判别力
            idx_dig = None
            idx = web / "dist" / "index.html"
            if idx.is_file():
                idx_dig = hashlib.sha256(idx.read_bytes()).hexdigest().lower()
            if cr.status_code != 200 or (idx_dig is not None and ctrl_dig != idx_dig):
                rows.append(("缓存头部策略", "SKIPPED",
                             f"对照未取到兜底文档 (status={cr.status_code}) —— 探测器无判别力，不作判定"))
                return rows, bad
            for p, disk in targets:
                r = c.get(p)
                cc = r.headers.get("cache-control")
                dig = hashlib.sha256(r.content).hexdigest().lower()
                # 【顺序要紧】先比【该路径声明的磁盘文件】——
                # 因为 /app/ 的合法响应【就是】index.html，它同时等于对照哈希。
                # 先比对照会把 /app/ 误判成兜底（我第一版就犯了这个错）。
                real = disk.is_file() and hashlib.sha256(disk.read_bytes()).hexdigest().lower() == dig
                if real:
                    seen.append(f"{p}->{cc or chr(45)}[OK]")
                elif dig == ctrl_dig:
                    notreal.append(p)
                    seen.append(f"{p}->[FALLBACK]")
                    continue
                else:
                    notreal.append(p)
                    seen.append(f"{p}->[BYTES-DIFFER]")
                    continue
                if r.status_code == 200 and not cc:
                    absent.append(p)
    except Exception as exc:
        rows.append(("缓存头部策略", "SKIPPED", f"服务不可达 {type(exc).__name__}"))
        return rows, bad
    ok = not absent
    rows.append(("缓存头部策略 (Cache-Control 缺失)", "OK" if ok else "BAD",
                 f"检查={len(seen)} 缺失={len(absent)}"
                 + (("  例: " + "; ".join(absent[:3])) if not ok else "")
                 + f"   [{", ".join(seen)}]"))
    if not ok:
        bad += 1
    if notreal:
        bad += 1
        rows.append(("兜底/字节不符 (该行不作缓存判定)", "BAD",
                     f"计={len(notreal)}  例: " + "; ".join(notreal[:3])
                     + "  [对照 sha256=" + (ctrl_dig or "-")[:16] + "...]"))
    return rows, bad



def src_manifest_report() -> tuple:
    """web/src-manifest.txt 是否仍描述当前 web/src 树（gmui 建、配方由我提）。

    不变量（可断言）: manifest 里每行的 path|length|sha256 与磁盘实际值一致，
                     且 manifest 的文件集合 == web/src 下实际文件集合（双向）。
    时点观测值（仅打印）: manifest 自身的 sha256 与文件数 —— 不比对硬编码值。

    价值: 对【单文件编辑免疫】（改文件必须重生成 manifest），对【整体状态敏感】。
    这是把「构建 2 的源码状态无法复现」从【承认】变成【可断言】的那一层。
    """
    rows, bad = [], 0
    root = Path(__file__).resolve().parent.parent
    man = root / "web" / "src-manifest.txt"
    src = root / "web" / "src"
    if not man.is_file():
        rows.append(("web/src 源码清单", "SKIPPED", f"无 {man}"))
        return rows, bad
    listed = {}
    bad_lines = []
    for ln in man.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split("|")
        if len(parts) != 3:
            bad_lines.append(ln[:60])
            continue
        rel, size, dig = parts[0].strip(), parts[1].strip(), parts[2].strip().lower()
        listed[rel.replace("\\", "/").lstrip("/")] = (size, dig)
    actual = {}
    if src.is_dir():
        for p in sorted(src.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            actual[rel] = hashlib.sha256(p.read_bytes()).hexdigest().lower()
    mismatch, missing, extra = [], [], []
    for rel, (size, dig) in sorted(listed.items()):
        if rel not in actual:
            missing.append(rel)
        elif actual[rel] != dig:
            mismatch.append(rel)
    for rel in sorted(actual):
        if rel not in listed:
            extra.append(rel)
    ok = not (mismatch or missing or extra or bad_lines)
    mh = hashlib.sha256(man.read_bytes()).hexdigest().lower()
    rows.append(("web/src 源码清单 = 树状态", "OK" if ok else "BAD",
                 f"manifest_files={len(listed)}  tree_files={len(actual)}"
                 f"  值不符={len(mismatch)} 清单有树无={len(missing)} 树有清单无={len(extra)}"
                 f"  [时点观测值 manifest_sha256={mh[:16]}... len={len(mh)}]"))
    for label, items in (("值不符", mismatch), ("清单有树无", missing), ("树有清单无", extra)):
        for it in items[:4]:
            rows.append((f"  {label}", "BAD", it))
    for ln in bad_lines[:3]:
        rows.append(("  清单行格式非法", "BAD", ln))
    if not ok:
        bad += 1
    return rows, bad


def hash_selfcheck() -> tuple:
    """纪律 E：所有被断言的哈希均由本脚本计算，附 64 长度自检。"""
    targets = [P_TOKENS_JSON, P_APP_CSS, C_TOKENS_JSON, C_APP_CSS, MP_TOKENS_WXSS]
    targets += sorted(STRINGS_FILES.values())
    targets += sorted(p for p in P_DIR.iterdir() if p.is_file())
    lines, bad_len = [], 0
    seen = set()
    for p in targets:
        if not p.is_file() or str(p) in seen:
            continue
        seen.add(str(p))
        h = sha256(p)
        if len(h) != 64:
            bad_len += 1
        lines.append((str(p), h, len(p.read_bytes()), len(h)))
    return lines, bad_len


def main() -> int:
    for p in (P_TOKENS_JSON, P_APP_CSS, C_TOKENS_JSON, C_APP_CSS, MP_TOKENS_WXSS):
        if not p.is_file():
            print(f"[FAIL] 缺文件: {p}")
            return 1

    tokens = json.loads(P_TOKENS_JSON.read_text(encoding="utf-8"))
    pc_root = parse_block(P_APP_CSS.read_text(encoding="utf-8"), ":root")
    c_root = parse_block(C_APP_CSS.read_text(encoding="utf-8"), ":root")
    mp_text = MP_TOKENS_WXSS.read_text(encoding="utf-8")
    mp_page = parse_all_blocks(mp_text, "page")
    mp_alias = {}
    for m in re.finditer(r"page\s*\{([^}]*)\}", mp_text):
        for d in re.finditer(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);", m.group(1)):
            mp_alias[d.group(1).strip()] = d.group(2).strip()

    rows, bad = [], 0
    for group in ("color", "radius", "space", "font", "layout", "shadow", "motion"):
        for key, value in (tokens.get(group) or {}).items():
            v = var_name(group, key)
            path = f"{group}.{key}"
            ok_pc = pc_root.get(v) == value
            ok_c = c_root.get(v) == value
            ok_mp = mp_page.get(v) == value
            alias = CONTRACT_ALIAS.get(path)
            ok_alias = (mp_alias.get(alias) == value) if alias else True
            ok = ok_pc and ok_c and ok_mp and ok_alias
            if not ok:
                bad += 1
            rows.append((path, v, value, ok_pc, ok_c, ok_mp, ok_alias, ok))

    print(f"tokens.json      : {P_TOKENS_JSON}")
    print(f"  sha256         : {sha256(P_TOKENS_JSON)}")
    print(f"client tokens.json sha256 : {sha256(C_TOKENS_JSON)}  (identical={sha256(C_TOKENS_JSON) == sha256(P_TOKENS_JSON)})")
    print(f"player-web/app.css sha256 : {sha256(P_APP_CSS)}")
    print(f"client/app.css     sha256 : {sha256(C_APP_CSS)}  (identical={sha256(C_APP_CSS) == sha256(P_APP_CSS)})")
    print()
    print(f"{'token':32} {'css var':32} {'value':42} PC  WEB MP  ALIAS")
    for path, v, value, a, b, c, d, ok in rows:
        print(f"{path:32} {v:32} {value:42} {'ok' if a else 'X ':3} {'ok' if b else 'X ':3} {'ok' if c else 'X ':3} {'ok' if d else 'X '}")
    print()
    print("---- 目录镜像不变量（强制）: player-web/ == client/ ----")
    mrows, mbad = mirror_report()
    print(f"{'file':16} {'player-web(server)':18} {'client(web)':18} verdict")
    for name, ha, hb, verdict in mrows:
        print(f"{name:16} {ha:18} {hb:18} {verdict}")
    print(f"MIRROR_FILES={len(mrows)}  MIRROR_DIFF={mbad}")
    bad += mbad
    print()
    print("---- strings.json 三端一致性（纪律 D）----")
    srows, sbad, key_bad, byte_identical = strings_report()
    print(f"{'end':12} {'sha256(16)':18} {'bytes':>7} {'keys':>5} verdict")
    for label, h, nbytes, nkeys, verdict in srows:
        print(f"{label:12} {h:18} {nbytes:7} {nkeys:5} {verdict}")
    print(f"STRINGS_COPIES={len(srows)}  KEY_SET_MISMATCH={key_bad}  BYTE_IDENTICAL={byte_identical}")
    bad += sbad
    print()
    print("---- R32 GM 主题覆盖层：可复算不变量（验收规范第 4 条）----")
    grows, gbad, gskip = gm_theme_report()
    if gskip:
        print("SKIPPED（无 GM web/ 部署形态）")
    else:
        for name, result, note in grows:
            print(f"  {result:10} {name}   {note}")
        print(f"GM_THEME_BAD={gbad}")
    bad += gbad
    print()
    print("---- web/src 源码清单是否仍描述当前树（补「构建 2 源码不可复现」缺口）----")
    srows, sbad = src_manifest_report()
    for name, result, note in srows:
        print(f"  {result:10} {name}   {note}")
    bad += sbad
    print()
    print("---- 静态资源缓存头部策略（补 I8d 缺口）----")
    crows, cbad = cache_header_report()
    for name, result, note in crows:
        print(f"  {result:10} {name}   {note}")
    bad += cbad
    print()
    print("---- 哈希自检（纪律 E：不手抄，长度应为 64）----")
    hlines, bad_len = hash_selfcheck()
    for path, h, nbytes, hlen in hlines:
        print(f"  {h}  len={hlen}  {nbytes:7}  {path}")
    print(f"HASH_COUNT={len(hlines)}  HASH_LEN_BAD={bad_len}")
    bad += bad_len
    print()
    total = len(rows)
    print(f"CHECKED={total}  MISMATCH={bad}")
    print("RESULT=" + ("PASS" if bad == 0 else "FAIL"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())