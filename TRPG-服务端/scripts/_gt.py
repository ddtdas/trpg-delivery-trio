# -*- coding: utf-8 -*-
"""Ground truth for docs audit: zips, digests, sidecars, versions, assets, strings."""
import hashlib, json, os, zipfile, collections
T = r"C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套"
NAMES = ["TRPG-服务端", "TRPG-Web客户端", "TRPG-微信小程序客户端"]
gt = {}
print("=== ZIP / SIDECAR ===")
for n in NAMES:
    zp = os.path.join(T, n + ".zip")
    sp = os.path.join(T, n + ".zip.sha256")
    raw = open(zp, "rb").read()
    h = hashlib.sha256(raw).hexdigest()
    side_raw = open(sp, "rb").read()
    side = side_raw.decode("utf-8-sig").strip()
    parts = side.split()
    side_name = parts[1] if len(parts) > 1 else "<MISSING>"
    z = zipfile.ZipFile(zp)
    ents = [e for e in z.infolist() if not e.is_dir()]
    bad = [e.filename for e in ents if any(s in e.filename.lower() for s in (".bak", ".pyc", ".log", ".env")) or "/run/" in e.filename]
    gt[n] = dict(size=len(raw), sha256=h, side_sha=parts[0].lower(), side_name=side_name,
                 side_ok=(parts[0].lower() == h and side_name == n + ".zip"), entries=len(ents))
    print("  %-24s size=%-10d sha=%s" % (n, len(raw), h))
    print("      sidecar=%s name=%s MATCH=%s entries=%d badhits=%d" % (parts[0][:16] + "…", side_name, gt[n]["side_ok"], len(ents), len(bad)))

print()
print("=== VERSION / HEALTH SOURCE ===")
import re
vp = os.path.join(T, "TRPG-服务端", "app", "config.py")
vt = open(vp, encoding="utf-8", errors="replace").read()
m = re.search(r"VERSION\s*[:=]\s*[\x27\"]([^\x27\"]+)", vt)
print("  app/config.py VERSION ->", m.group(1) if m else "<not found>")
for mm in re.finditer(r"def get_version.*?(?=\ndef |\Z)", vt, re.S):
    print("  get_version body:", " ".join(mm.group(0).split())[:300])

print()
print("=== DIST ASSETS (authoritative) ===")
dd = os.path.join(T, "TRPG-服务端", "web", "dist")
assets = {}
for fn in sorted(os.listdir(os.path.join(dd, "assets"))):
    p = os.path.join(dd, "assets", fn)
    assets[fn] = os.path.getsize(p)
    print("  assets/%-28s %8d" % (fn, os.path.getsize(p)))
gt["assets"] = assets
gt["index_html"] = open(os.path.join(dd, "index.html"), encoding="utf-8").read()

print()
print("=== STRINGS KEYS ===")
for rel in ("TRPG-服务端/player-web/strings.json", "TRPG-Web客户端/client/strings.json", "TRPG-微信小程序客户端/strings.json"):
    p = os.path.join(T, rel.replace("/", os.sep))
    d = json.loads(open(p, encoding="utf-8").read())
    print("  %-44s keys=%d sha=%s" % (rel, len(d), hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]))
    gt.setdefault("strings_keys", []).append((rel, len(d)))

print()
print("=== TOKENS ===")
for rel in ("TRPG-服务端/configs/access_config.yaml",):
    print("  " + rel + ":")
    for ln in open(os.path.join(T, rel.replace("/", os.sep)), encoding="utf-8").read().splitlines():
        if "token" in ln or "provider" in ln or "model" in ln or "poll" in ln:
            print("    " + ln.strip())

open(r"E:\dsh3080工作区存放位置\dsh_gzq1\_r2doc_cache\ground_truth.json", "w", encoding="utf-8").write(json.dumps(gt, ensure_ascii=False, indent=1))
print()
print("ground_truth.json written")