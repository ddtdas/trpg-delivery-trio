# -*- coding: utf-8 -*-
"""纪律 A 修复：player-web/strings.json 被我改成了 CRLF（原为 LF），现按字节还原为 LF 并同步镜像。"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "player-web" / "strings.json"
B = ROOT.parent / "TRPG-Web客户端" / "client" / "strings.json"

print("before: A cr=%d lf=%d sha=%s" % (A.read_bytes().count(b"\r"), A.read_bytes().count(b"\n"),
                                        hashlib.sha256(A.read_bytes()).hexdigest()))
raw = A.read_bytes()
fixed = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
A.write_bytes(fixed)
print("after : A cr=%d lf=%d sha=%s" % (A.read_bytes().count(b"\r"), A.read_bytes().count(b"\n"),
                                        hashlib.sha256(A.read_bytes()).hexdigest()))
# 同步镜像（字节级）
B.write_bytes(A.read_bytes())
print("mirror: B cr=%d lf=%d sha=%s" % (B.read_bytes().count(b"\r"), B.read_bytes().count(b"\n"),
                                        hashlib.sha256(B.read_bytes()).hexdigest()))
print("mirror_identical =", A.read_bytes() == B.read_bytes())

ja = json.loads(A.read_text(encoding="utf-8"))
jb = json.loads(B.read_text(encoding="utf-8"))
print("keys A=%d B=%d equal=%s" % (len(ja), len(jb), ja == jb))
print("NPC keys:", ja.get("ev.NPC_ACT_APPROVED"), "/", ja.get("ev.NPC_ACT_PROPOSED"))

# 全目录镜像复核（6 对）
PA, PB = ROOT / "player-web", ROOT.parent / "TRPG-Web客户端" / "client"
for f in ("app.js", "app.css", "tokens.json", "strings.json", "index.html", "README.md"):
    x, y = (PA / f), (PB / f)
    hx = hashlib.sha256(x.read_bytes()).hexdigest() if x.exists() else "MISSING"
    hy = hashlib.sha256(y.read_bytes()).hexdigest() if y.exists() else "MISSING"
    print("MIRROR %-13s %s  %s" % (f, hx[:24], "SAME" if hx == hy else "**DIFF**"))
