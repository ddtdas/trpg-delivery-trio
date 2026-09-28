# -*- coding: utf-8 -*-
"""镜像一致性 + 三端 strings 一致性（一条脚本覆盖两处破口）。v4.1。

v1 只覆盖 6 个镜像文件（硬编码），不覆盖小程序端 —— 本轮真正的破口正是小程序端。
v2 增加 S1-S5 五条小程序端断言。
v3（队长广播 ① 要求）：**整目录自动发现**替代硬编码文件名 —— 否则将来新增文件会漏判。
     并增加「目录文件集合相等」断言：任一目录多/少文件都直接判 FAIL。
v4（implementer-rules ⑤ 建议）：**自证有牙（TEETH）** —— 把真实断言抽成纯谓词，
     再用内存内的反例证明这些谓词**确实会返回 False**；否则「绿灯」可能只是谓词恒真。
     反例覆盖：CRLF 篡改 / 字节篡改 / 缺键 / 多余键 / 值漂移 / 文件集合多出（双向），

只读，不写入任何文件（反例全部在内存中构造，不落盘）。
"""
from __future__ import annotations
import hashlib, json, sys, re, time
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
A = PKG / "TRPG-服务端" / "player-web"
B = PKG / "TRPG-Web客户端" / "client"
WX = PKG / "TRPG-微信小程序客户端"


# ---- 真实断言所用的纯谓词（TEETH 直接对它们做负向对照）----------------------
def eq_bytes(x: bytes, y: bytes) -> bool:
    """镜像逐字节相等（会捕捉 CRLF 漂移）。"""
    return x == y


def eq_maps(a: dict, b: dict) -> bool:
    """键集合相等【且】逐值相等（比只比键数强：键数相同而值漂移也会 False）。"""
    return set(a) == set(b) and a == b


def setdiff(a: set, b: set) -> tuple:
    """返回 (仅 a 有, 仅 b 有)。"""
    return (sorted(a - b), sorted(b - a))


def no_setdiff(a: set, b: set) -> bool:
    """两个文件集合【无差异】—— 真实 SETEQUAL 断言所用的同一谓词。"""
    return setdiff(a, b) == ([], [])


def discover(d: Path) -> dict:
    """自动发现目录下全部普通文件（不硬编码文件名）。"""
    if not d.is_dir():
        return {}
    return {p.name: p for p in sorted(d.iterdir()) if p.is_file()}


print("=" * 132)
print("PART 1  镜像不变量：player-web/ <-> client/ 逐字节一致（整目录自动发现）")
print("=" * 132)
da, db = discover(A), discover(B)
seta, setb = set(da), set(db)
only_a, only_b = setdiff(seta, setb)
seteq_fresh = no_setdiff(seta, setb)
common = sorted(seta & setb)

print("A = %s" % A)
print("B = %s" % B)
print("A 文件数 = %d   B 文件数 = %d   共有 = %d" % (len(seta), len(setb), len(common)))
print("仅 A 有: %s" % (only_a or "（无）"))
print("仅 B 有: %s" % (only_b or "（无）"))
print("")
print("%-15s %-9s %-6s %-64s %-19s %s" % ("file", "size", "cr", "sha256", "mtime", "A==B"))
print("-" * 132)
allok = True
for f in common:
    a, b = da[f], db[f]
    ba, bb = a.read_bytes(), b.read_bytes()
    same = eq_bytes(ba, bb)
    allok = allok and same
    print("%-15s %-9d %-6d %-64s %-19s %s" % (
        f, len(ba), ba.count(b"\r"), hashlib.sha256(ba).hexdigest(),
        time.strftime("%m-%d %H:%M:%S", time.localtime(a.stat().st_mtime)), "YES" if same else "**NO**"))
    if not same:
        print("%-15s %-9d %-6d %-64s  (client 侧)" % ("", len(bb), bb.count(b"\r"), hashlib.sha256(bb).hexdigest()))

seteq = seteq_fresh
allok = allok and seteq
print("")
print("  SETEQUAL 两目录文件集合相等 :", seteq)
print("  IDENTICAL 共有文件逐字节相同 :", all(eq_bytes(da[f].read_bytes(), db[f].read_bytes()) for f in common))
print("")
print("MIRROR_RESULT = %s" % ("%d/%d PASS" % (len(common), len(common)) if allok else "FAIL"))

print("")
print("=" * 132)
print("PART 2  三端 strings 一致性")
print("=" * 132)
SVC, WEB, MP = A / "strings.json", B / "strings.json", WX / "strings.json"
MPJS = WX / "strings.js"
for p in (SVC, WEB, MP, MPJS):
    if not p.exists():
        print("MISSING:", p); raise SystemExit(2)

d_svc = json.loads(SVC.read_text(encoding="utf-8"))
d_web = json.loads(WEB.read_text(encoding="utf-8"))
d_mp = json.loads(MP.read_text(encoding="utf-8"))
js = dict(re.findall(r'^\s*"([^"]+)":\s*"([^"]*)"', MPJS.read_text(encoding="utf-8"), flags=re.M))

for name, p, n in (("svc/player-web", SVC, len(d_svc)), ("web/client", WEB, len(d_web)),
                   ("miniprogram json", MP, len(d_mp)), ("miniprogram js", MPJS, len(js))):
    b = p.read_bytes()
    print("  %-18s keys=%-4d cr=%-3d size=%-6d %s" % (name, n, b.count(b"\r"), len(b), hashlib.sha256(b).hexdigest()))

S1 = set(d_svc) == set(d_web) == set(d_mp)
S2 = len(d_svc) == len(d_web) == len(d_mp)   # 不钉具体值：键数会漂移，断言的是「三端相等」
S3 = eq_maps(js, d_mp)
S4 = all(p.read_bytes().count(b"\r") == 0 for p in (SVC, WEB, MP, MPJS))
print("")
print("  S1 三端 json 键集合两两相等          :", S1)
print("  S2 三端 json 键数相等（不钉具体值）   :", S2, "  keys=%d" % len(d_svc))
print("  S3 小程序 strings.js <-> json 逐值相等:", S3)
print("  S4 四个文件 crlf=0                   :", S4)
print("  S5 三端 json 逐字节相同（更强）      :", eq_bytes(SVC.read_bytes(), WEB.read_bytes()) and eq_bytes(WEB.read_bytes(), MP.read_bytes()))
strok = S1 and S2 and S3 and S4
print("")
print("STRINGS_RESULT = %s" % ("PASS" if strok else "FAIL"))

# ---- PART 3: TEETH —— 自证谓词会报红（rules ⑤）-------------------------------
print("")
print("=" * 132)
print("PART 3  TEETH 自证有牙：对真实断言所用的同一批谓词注入内存反例，必须返回 False")
print("=" * 132)
TEETH_CASES = [
    ("CRLF 篡改 (LF vs CRLF)  应判不同", eq_bytes, (b'{"a": 1}\n', b'{"a": 1}\r\n'), False),
    ("字节内容篡改            应判不同", eq_bytes, (b'{"a": 1}\n', b'{"a": 2}\n'), False),
    ("缺键 (json 多一个键)    应判不相等", eq_maps, ({"a": "1"}, {"a": "1", "b": "2"}), False),
    ("多余键 (js 多一个键)    应判不相等", eq_maps, ({"a": "1", "b": "2"}, {"a": "1"}), False),
    ("值漂移 (键同值不同)     应判不相等", eq_maps, ({"a": "1"}, {"a": "2"}), False),
    ("文件集合 A 多出一个     应判不相等", no_setdiff, ({"index.html"}, {"index.html", "extra.js"}), False),
    ("文件集合 B 多出一个     应判不相等", no_setdiff, ({"index.html", "extra.js"}, {"index.html"}), False),
    ("-- 干净对照 --", None, None, None),
    ("相同字节                应判相同", eq_bytes, (b'{"a": 1}\n', b'{"a": 1}\n'), True),
    ("相同映射                应判相等", eq_maps, ({"a": "1"}, {"a": "1"}), True),
    ("相同文件集合            应判相等", no_setdiff, ({"a"}, {"a"}), True),
]

teeth_ok = True
tamper_n = 0
clean_n = 0
for label, fn, args, expect in TEETH_CASES:
    if fn is None:
        print("  %s" % label)
        continue
    got = fn(*args)
    ok = (got == expect)
    teeth_ok = teeth_ok and ok
    if expect is False:
        tamper_n += 1
    else:
        clean_n += 1
    print("  [%s] %-34s -> %-5s (期望 %-5s)" % ("PASS" if ok else "FAIL", label, got, expect))

print("")
print("  负向对照（必须报红）= %d 条   干净对照（必须为真）= %d 条" % (tamper_n, clean_n))
print("  非真空要求：负向对照 >= 4 且 干净对照 >= 2 :", tamper_n >= 4 and clean_n >= 2)
teeth_ok = teeth_ok and tamper_n >= 4 and clean_n >= 2
print("")
print("TEETH_RESULT = %s" % ("PASS (谓词已被证明会报红)" if teeth_ok else "FAIL (谓词可能恒真)"))
print("")
print("OVERALL = %s" % ("ALL PASS" if (allok and strok and teeth_ok) else "FAIL"))
# 退出码必须承载判据：此前本脚本【无 sys.exit】=> OVERALL=FAIL 却 EXIT=0（绿在退出码上）。
sys.exit(0 if (allok and strok and teeth_ok) else 1)