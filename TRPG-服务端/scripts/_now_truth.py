# -*- coding: utf-8 -*-
"""最新真值：门禁全量输出（不过滤）+ 三端键数 + 墓碑字节。"""
from __future__ import annotations
import hashlib, json, subprocess, sys, time
from pathlib import Path

PKG = Path(r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套")
SRV = PKG / "TRPG-服务端"
print("NOW =", time.strftime("%Y-%m-%d %H:%M:%S"))
print("")
print("=== 门禁全量输出（不过滤，按原样）===")
r = subprocess.run([sys.executable, "-X", "utf8", str(SRV / "scripts" / "r2_verify_invariants.py")],
                   cwd=str(SRV), capture_output=True, text=True, encoding="utf-8", errors="replace")
out = (r.stdout or "") + (r.stderr or "")
for line in out.splitlines():
    if line.strip():
        print("  " + line.rstrip())
print("  GATE_EXIT =", r.returncode)
gp = SRV / "scripts" / "r2_verify_invariants.py"
print("  gate script: %d B  sha256=%s  mtime=%s" % (
    gp.stat().st_size, hashlib.sha256(gp.read_bytes()).hexdigest(),
    time.strftime("%H:%M:%S", time.localtime(gp.stat().st_mtime))))

print("")
print("=== 三端 strings.json + strings.js 键数（可真值）===")
for rel in ["TRPG-服务端/player-web/strings.json", "TRPG-Web客户端/client/strings.json",
            "TRPG-微信小程序客户端/strings.json", "TRPG-微信小程序客户端/strings.js"]:
    p = PKG / rel
    b = p.read_bytes()
    nkeys = None
    try:
        if p.suffix == ".json":
            nkeys = len(json.loads(b.decode("utf-8")))
        else:
            import re
            nkeys = len(re.findall(r'^\s*"', b.decode("utf-8"), flags=re.M))
    except Exception as e:
        nkeys = "ERR %s" % e
    print("  %-44s %6d B cr=%d keys=%s sha=%s mtime=%s" % (
        rel, len(b), b.count(b"\r"), nkeys, hashlib.sha256(b).hexdigest()[:16],
        time.strftime("%H:%M:%S", time.localtime(p.stat().st_mtime))))

print("")
print("=== 两个 .tombstones.json 现状（是否已被修复）===")
for k in ("modules", "rulepacks"):
    p = SRV / k / ".tombstones.json"
    if p.is_file():
        b = p.read_bytes()
        print("  %-10s %3d B  CR=%d LF=%d  sha=%s  mtime=%s" % (
            k, len(b), b.count(b"\r"), b.count(b"\n"), hashlib.sha256(b).hexdigest()[:16],
            time.strftime("%H:%M:%S", time.localtime(p.stat().st_mtime))))
    else:
        print("  %-10s MISSING" % k)
