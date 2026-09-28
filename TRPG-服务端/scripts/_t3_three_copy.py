# -*- coding: utf-8 -*-
"""三端 strings.json 键集合一致性 + 哈希长度自检（纪律 D/E）。只读。"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
COPIES = [
    ("服务端/player-web", PKG / "TRPG-服务端" / "player-web" / "strings.json"),
    ("Web客户端/client", PKG / "TRPG-Web客户端" / "client" / "strings.json"),
    ("微信小程序", PKG / "TRPG-微信小程序客户端" / "strings.json"),
]

data = {}
print("=== 三端 strings.json 现状 ===")
for name, p in COPIES:
    if not p.exists():
        print("%-22s **MISSING**  %s" % (name, p)); continue
    b = p.read_bytes()
    h = hashlib.sha256(b).hexdigest()
    try:
        j = json.loads(b.decode("utf-8"))
        keys = set(j.keys())
    except Exception as exc:
        j, keys = {}, set()
        print("%-22s JSON 解析失败: %s" % (name, exc))
    data[name] = (h, keys, b)
    print("%-22s size=%-6d cr=%-4d sha256=%s (len=%d) keys=%d"
          % (name, len(b), b.count(b"\r"), h, len(h), len(keys)))

print("")
print("=== 键集合两两差异 ===")
names = list(data.keys())
base = names[0]
for other in names[1:]:
    a, b = data[base][1], data[other][1]
    print("%s  vs  %s" % (base, other))
    print("   only_in_%s = %s" % (base, sorted(a - b)))
    print("   only_in_%s = %s" % (other, sorted(b - a)))
    shared = a & b
    diffv = [k for k in shared if json.loads(data[base][2].decode("utf-8")).get(k)
             != json.loads(data[other][2].decode("utf-8")).get(k)]
    print("   value_diff = %s" % (diffv or "无"))
    print("   键集合一致 = %s" % (a == b))

print("")
print("=== NPC 两键在三端的值 ===")
for name, p in COPIES:
    if not p.exists():
        continue
    j = json.loads(p.read_text(encoding="utf-8"))
    print("%-22s ev.NPC_ACT_APPROVED=%r  ev.NPC_ACT_PROPOSED=%r"
          % (name, j.get("ev.NPC_ACT_APPROVED"), j.get("ev.NPC_ACT_PROPOSED")))

print("")
print("=== 纪律 E：哈希长度自检（我汇报过的值，应为 64）===")
REPORTED = {
    "app/web/rest.py": "133aba6bd3b5c79d6486a9e72264f4eda1d4733b895011edd58da1571b2ec184",
    "app/web/ws.py": "3aa792a9dbe582c5a32d705d45e8079c82cf5c2097144cca6cd4247a01ded0ce",
    "app/main.py": "c9acda6087d3a5c4ad07ee9f9c093e6c41da032f5f02af97e57e615d2e079111",
    "app/mcp/auth.py": "63f065ae1e9f936dff0107992c7cc22b2c198812cd5005d74bcf39dae645077e",
    "app/mcp/schemas.py": "569db3b51b77b96f7e2b40bc32fb0f9c582eeca41ce5ffdbaeb24edd49921b25",
    "app/mcp/server.py": "d95e1b84c5a8c400c47488a9f077ec28d5656d7762c28dbd97439243704f1acc",
    "docs/R2-NPC-CONTRACT-CHANGE.md": "4e494ecb43f1cf7731315e0c7f0b88668250151c1ae7f806f461367e8b52aad5",
    "player-web/strings.json": "896f551bf8046bc946bec615d71cf6fadc3473a4f4ebdd98080ae532de37c0ab",
}
bad = []
for rel, h in REPORTED.items():
    p = PKG / "TRPG-服务端" / rel
    actual = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "(missing)"
    ok_len = len(h) == 64
    ok_match = (h == actual)
    if not (ok_len and ok_match):
        bad.append(rel)
    print("%-34s len=%-3d 长度OK=%-5s 与实盘一致=%-5s" % (rel, len(h), ok_len, ok_match))
print("自检失败项 =", bad or "无")

print("")
print("=== 纪律 D：我是否碰过单出口产物 ===")
for rel in ["web/dist", "rulepacks/index.json", "modules/index.json"]:
    p = PKG / "TRPG-服务端" / rel
    print("%-24s exists=%s" % (rel, p.exists()))
