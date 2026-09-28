#!/usr/bin/env python3
"""T1 取证脚本: 对运行中的服务端逐条打 R22/R1/R2/R13/R3 的验收证据。

用法:
    python scripts/_t1_evidence.py --base http://127.0.0.1:9212

输出: 每节先给「命令」, 再给「原始输出」(服务端原样 JSON), 最后给「判定」。
脚本自身只在 data/_t1_evidence/ 下建临时素材, 结束时清理 (不污染交付包)。
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socketserver
import sys
import threading
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRATCH = ROOT / "data" / "_t1_evidence"
MID = "t1_evidence_mod"


def hr(title: str) -> None:
    print("\n" + "=" * 78)
    print("## " + title)
    print("=" * 78)


def cmd(line: str) -> None:
    print("\n[CMD] " + line)


def show(label: str, resp) -> dict:
    print("[HTTP] %s -> %s" % (label, resp.status_code))
    try:
        body = resp.json()
    except Exception:
        body = {"_raw": resp.text[:400]}
    print("[OUT] " + json.dumps(body, ensure_ascii=False)[:4000])
    return body


# ------------------------------------------------------------------ fixtures

def build_evidence_module() -> Path:
    """合法包 + 5 类坏包 (全部落在 data/_t1_evidence/ 下)。"""
    root = SCRATCH / "pkg_good"
    (root / "npcs").mkdir(parents=True, exist_ok=True)
    (root / "maps").mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": MID, "name": "T1 取证模组", "ruleset": "coc7", "version": "1.0.0",
        "schema_version": "1", "initial_scene": "n1_start",
        "counts": {"scenes": 3, "event_nodes": 4, "npcs": 2},
        "files": {"event_graph": "event_graph.yaml", "clues": "clues.yaml",
                  "npcs": ["npcs/npc_a.yaml", "npcs/npc_b.yaml"],
                  "maps": ["maps/m1.json"]},
    }
    (root / "module.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    nodes = [
        {"id": "n1_start", "title": "起点", "actions": ["看"], "clue_refs": ["c1"], "npc_refs": ["npc_a"], "map_ref": "m1"},
        {"id": "n2_mid", "title": "中段", "actions": ["走"]},
        {"id": "n3_room", "title": "房间", "actions": ["搜"], "map_ref": "m1"},
        {"id": "n4_end", "title": "终局", "actions": ["结"]},
    ]
    edges = [{"from": "n1_start", "to": "n2_mid", "condition": {}, "label": "前进"},
             {"from": "n2_mid", "to": "n3_room", "condition": {}, "label": "深入"},
             {"from": "n3_room", "to": "n4_end", "condition": {}, "label": "收束"}]
    (root / "event_graph.yaml").write_text(
        yaml.safe_dump({"nodes": nodes, "edges": edges}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / "clues.yaml").write_text(yaml.safe_dump({"clues": [
        {"id": "c1", "kind": "物证", "location": "n1_start", "points_to": "n4_end", "scope": "public", "text": "线索"}]},
        allow_unicode=True, sort_keys=False), encoding="utf-8")
    for nid, name in (("npc_a", "甲"), ("npc_b", "乙")):
        (root / "npcs" / ("%s.yaml" % nid)).write_text(
            yaml.safe_dump({"id": nid, "name": name, "role": "角色", "lines": ["a", "b"]},
                           allow_unicode=True, sort_keys=False), encoding="utf-8")
    rooms = [{"id": "r1", "name": "门厅", "x": 20, "y": 20, "w": 200, "h": 140},
             {"id": "r2", "name": "书房", "x": 240, "y": 20, "w": 320, "h": 140},
             {"id": "r3", "name": "地窖", "x": 240, "y": 180, "w": 200, "h": 160}]
    (root / "maps" / "m1.json").write_text(json.dumps(
        {"id": "m1", "name": "取证地图", "rooms": rooms, "doors": [], "tokens_start": []},
        ensure_ascii=False, indent=2), encoding="utf-8")

    bad = SCRATCH / "bad"
    # 1) 缺 manifest
    b = bad / "missing_manifest"
    shutil.copytree(root, b, dirs_exist_ok=True)
    (b / "module.yaml").unlink()
    # 2) 缺 id
    b = bad / "missing_id"
    shutil.copytree(root, b, dirs_exist_ok=True)
    m = dict(manifest); m.pop("id")
    (b / "module.yaml").write_text(yaml.safe_dump(m, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # 3) 图悬挂
    b = bad / "dangling_edge"
    shutil.copytree(root, b, dirs_exist_ok=True)
    (b / "event_graph.yaml").write_text(yaml.safe_dump(
        {"nodes": nodes, "edges": edges + [{"from": "n4_end", "to": "n_nowhere", "condition": {}}]},
        allow_unicode=True, sort_keys=False), encoding="utf-8")
    # 4) 引用文件缺失
    b = bad / "missing_referenced_file"
    shutil.copytree(root, b, dirs_exist_ok=True)
    (b / "npcs" / "npc_b.yaml").unlink()
    # 5) 版本不兼容
    b = bad / "version_incompatible"
    shutil.copytree(root, b, dirs_exist_ok=True)
    m = dict(manifest); m["schema_version"] = "99"
    (b / "module.yaml").write_text(yaml.safe_dump(m, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return root


def raw_request(host: str, port: int, raw_path: str, timeout: float = 10.0) -> str:
    """原样发线上路径 (等价 curl --path-as-is), 绕过任何客户端规范化。"""
    import socket

    req = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nConnection: close\r\n\r\n"
           % (raw_path, host, port)).encode("latin-1")
    s = socket.create_connection((host, port), timeout=timeout)
    s.sendall(req)
    chunks = []
    while True:
        b = s.recv(65536)
        if not b:
            break
        chunks.append(b)
    s.close()
    return b"".join(chunks).decode("utf-8", "replace")


def start_file_server(serve_dir: Path):
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            return

    handler = functools.partial(_Quiet, directory=str(serve_dir))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


# ---------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:9212")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    c = httpx.Client(base_url=base, timeout=30.0)

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH, ignore_errors=True)
    good = build_evidence_module()
    print("BASE=%s" % base)
    print("SCRATCH=%s" % SCRATCH)

    hr("0. 环境")
    cmd("GET %s/api/health" % base)
    show("health", c.get("/api/health"))

    hr("1. R22-1 索引: modules/index.json + rulepacks/index.json (id/name/ruleset/version/sha256/size/path)")
    cmd("GET %s/api/repository/index" % base)
    idx = show("repository/index", c.get("/api/repository/index"))
    for kind in ("modules", "rulepacks"):
        ent = (idx.get(kind) or {}).get("entries") or []
        print("[CHK] %s count=%d fingerprint=%s" % (kind, len(ent), (idx.get(kind) or {}).get("fingerprint")))
        for e in ent:
            print("      %-18s name=%-14s ruleset=%-6s ver=%-7s size=%-7d sha256=%s path=%s"
                  % (e["id"], e["name"], e["ruleset"], e["version"], e["size"], e["sha256"][:16] + "...", e["path"]))
    print("[CHK] index files on disk: modules/index.json=%s rulepacks/index.json=%s"
          % ((ROOT / "modules" / "index.json").is_file(), (ROOT / "rulepacks" / "index.json").is_file()))

    hr("2. R22-1 重启后从磁盘重建且结果一致 (删索引文件 -> 服务端自愈 -> fingerprint 必须相同)")
    fp_before = {"modules": idx["modules"]["fingerprint"], "rulepacks": idx["rulepacks"]["fingerprint"]}
    (ROOT / "modules" / "index.json").unlink(missing_ok=True)
    (ROOT / "rulepacks" / "index.json").unlink(missing_ok=True)
    cmd("rm modules/index.json rulepacks/index.json; GET %s/api/repository/index" % base)
    idx2 = show("repository/index (rebuilt)", c.get("/api/repository/index"))
    fp_after = {"modules": idx2["modules"]["fingerprint"], "rulepacks": idx2["rulepacks"]["fingerprint"]}
    print("[CHK] fingerprint before = %s" % json.dumps(fp_before))
    print("[CHK] fingerprint after  = %s" % json.dumps(fp_after))
    print("[VERDICT] R22-1 重启重建一致: %s" % (fp_before == fp_after))

    hr("3. R22-3 路径穿越防护 (../ / 绝对路径 / 符号链接 / URL 编码绕过)")
    hostport = base.split("//", 1)[1]
    host, port = hostport.split(":")[0], int(hostport.split(":")[1])
    traversal = ["/api/modules/..%2f..%2fetc", "/api/modules/%2e%2e%2f%2e%2e%2fetc",
                 "/api/modules/%252e%252e%252fetc", "/api/modules/..%5c..%5cwindows",
                 "/api/modules/../../etc/passwd", "/api/modules/..%2F..%2F..%2Fwindows",
                 "/api/rulepacks/%2e%2e%2f%2e%2e%2fetc", "/api/modules/C:%5cWindows",
                 "/api/modules/a%2f..%2f..%2fb"]
    for raw in traversal:
        cmd('curl --path-as-is -s -i "%s%s"' % (base, raw))
        txt = raw_request(host, port, raw)
        status = txt.split("\r\n", 1)[0]
        bodytxt = txt.split("\r\n\r\n", 1)[-1].strip()
        print("[HTTP] %s" % status)
        print("[OUT] %s" % bodytxt[:500])
        print("[CHK] raw=%-40s %s" % (raw, status))
    print("-- 写入请求体里的路径穿越 --")
    cmd('PUT %s/api/modules/evil {"files":{"../../escape.yaml":"id: evil"}}' % base)
    show("write traversal", c.put("/api/modules/evil", json={
        "manifest": {"id": "evil", "ruleset": "coc7", "initial_scene": "n1"},
        "files": {"../../escape.yaml": "id: evil\n"}}))
    print("-- 符号链接: ① 仓库根内的链接目录 ② 离线收件箱里的链接包 --")
    outside = SCRATCH / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "module.yaml").write_text("id: evil\nruleset: coc7\n", encoding="utf-8")
    mod_link = ROOT / "modules" / "t1_evil_link"
    inbox_link = ROOT / "data" / "imports" / "t1_evil_link"
    made = []
    for lk in (mod_link, inbox_link):
        lk.parent.mkdir(parents=True, exist_ok=True)
        try:
            if lk.exists() or lk.is_symlink():
                lk.unlink()
            lk.symlink_to(outside, target_is_directory=True)
            made.append(lk)
        except OSError as exc:
            print("[SKIP] 无法创建符号链接(需开发者模式/管理员): %s" % exc)
    if made:
        c.post("/api/repository/rebuild")
        cmd('GET %s/api/modules/t1_evil_link  (链接目录不会被索引为仓库条目)' % base)
        show("symlink dir read", c.get("/api/modules/t1_evil_link"))
        cmd('POST %s/api/modules/import {"source":"local","path":"t1_evil_link"}  (收件箱内相对路径)' % base)
        show("symlink inbox import", c.post("/api/modules/import",
                                            json={"source": "local", "path": "t1_evil_link"}))
        cmd('PUT %s/api/modules/t1_evil_link2 {"source_path":"%s"}  (绝对路径符号链接)' % (base, mod_link))
        show("symlink absolute source_path", c.put("/api/modules/t1_evil_link2",
                                                   json={"source_path": str(mod_link)}))
        for lk in made:
            if lk.is_symlink():
                lk.unlink()

    hr("4. R13 五类坏包 -> 五个不同且明确的错误码")
    expect = {"missing_manifest": "MODULE_MANIFEST_MISSING",
              "missing_id": "MODULE_ID_MISSING",
              "dangling_edge": "MODULE_GRAPH_DANGLING_EDGE",
              "missing_referenced_file": "MODULE_FILE_MISSING",
              "version_incompatible": "MODULE_VERSION_INCOMPATIBLE"}
    got = {}
    for name in sorted(expect):
        p = SCRATCH / "bad" / name
        cmd('POST %s/api/modules/import {"source":"local","path":"%s"}' % (base, p))
        r = c.post("/api/modules/import", json={"source": "local", "path": str(p)})
        body = show("import %s" % name, r)
        got[name] = (r.status_code, body.get("error_code"))
    print("[CHK] 实际: %s" % json.dumps({k: v[1] for k, v in got.items()}, ensure_ascii=False))
    print("[VERDICT] 五个错误码互不相同: %s" % (len({v[1] for v in got.values()}) == 5))
    print("[VERDICT] 与 R13 期望一致: %s" % all(got[k][1] == expect[k] for k in expect))
    print("[VERDICT] 无 500: %s" % all(v[0] != 500 for v in got.values()))

    hr("5. R1 合法包导入 -> 2xx + 计数与声明一致 + 开局句柄")
    LOCAL_SHA: dict = {}
    LIB_SHA: dict = {}
    cmd('POST %s/api/modules/import {"source":"local","path":"%s","expected":{...},"open_session":true}' % (base, good))
    r = c.post("/api/modules/import", json={
        "source": "local", "path": str(good), "overwrite": True, "open_session": True,
        "expected": {"scenes": 3, "event_nodes": 4, "npcs": 2}})
    body = show("import good", r)
    LOCAL_SHA["v"] = body.get("content_sha256")
    print("[CHK] content_sha256(local)=%s" % LOCAL_SHA["v"])
    print("[CHK] status=%s counts=%s declared=%s declared_verified=%s"
          % (r.status_code, json.dumps(body.get("counts")), json.dumps(body.get("declared")), body.get("declared_verified")))
    h = body.get("session") or {}
    print("[CHK] session_handle=%s" % json.dumps(h, ensure_ascii=False))
    if h.get("table_id"):
        cmd("GET %s/api/tables/%s" % (base, h["table_id"]))
        show("table from handle", c.get("/api/tables/%s" % h["table_id"]))
    print("[VERDICT] R1 合法包 2xx: %s" % (200 <= r.status_code < 300))
    print("[VERDICT] R1 计数与声明一致: %s" % (
        body.get("counts", {}).get("scenes") == 3 and body.get("counts", {}).get("event_nodes") == 4
        and body.get("counts", {}).get("npcs") == 2))

    hr("6. R2 下载后导入: ①本地离线包 ②远程 URL (sha256 必校验, 失败不留半成品)")
    cmd('POST %s/api/modules/import {"source":"library","module_id":"%s","overwrite":true}' % (base, MID))
    _lib = show("import source=library", c.post("/api/modules/import",
                                                json={"source": "library", "module_id": MID, "overwrite": True}))
    LIB_SHA["v"] = _lib.get("content_sha256")
    print("[CHK] content_sha256(library)=%s" % LIB_SHA["v"])
    sys.path.insert(0, str(ROOT))
    from app.repository.pkg import pack_module, sha256_file  # noqa: E402

    serve_dir = SCRATCH / "http"
    serve_dir.mkdir(parents=True, exist_ok=True)
    pkg_out = serve_dir / ("%s.modpkg" % MID)
    info = pack_module(good, pkg_out, source_note="t1-evidence")
    print("[CHK] packed %s size=%d sha256=%s" % (pkg_out.name, info["size"], info["sha256"]))
    httpd, url_base = start_file_server(serve_dir)
    try:
        cmd('POST %s/api/modules/import {"source":"url","url":"%s/%s.modpkg","sha256":"%s","overwrite":true}'
            % (base, url_base, MID, info["sha256"]))
        r = c.post("/api/modules/import", json={"source": "url", "url": "%s/%s.modpkg" % (url_base, MID),
                                                "sha256": info["sha256"], "overwrite": True})
        body = show("import url (sha256 ok)", r)
        print("[CHK] status=%s sha256=%s" % (r.status_code, body.get("sha256")))
        print("[VERDICT] R2 URL 下载+sha256 校验通过: %s" % (r.status_code == 201 and body.get("sha256") == info["sha256"]))

        cmd('POST %s/api/modules/import {"source":"url","url":"...","sha256":"000...0"}' % base)
        r2 = c.post("/api/modules/import", json={"source": "url", "url": "%s/%s.modpkg" % (url_base, MID),
                                                 "sha256": "0" * 64, "overwrite": True})
        show("import url (sha256 mismatch)", r2)
        leftover = sorted(p.name for p in (ROOT / "modules").iterdir() if p.name.startswith(".old_"))
        staging = sorted(p.name for p in (ROOT / "data" / ".repo_staging").glob("imp_*"))
        print("[CHK] 半成品检查: .old_*=%s staging=%s" % (leftover, staging))
        print("[VERDICT] R2 sha256 不一致被拒: %s" % (r2.status_code == 422 and r2.json().get("error_code") == "MODULE_PACKAGE_SHA256_MISMATCH"))
        print("[VERDICT] R2 原子性(无半成品): %s" % (not leftover and not staging))

        cmd('POST %s/api/modules/import {"source":"url",...} (无 sha256)' % base)
        r3 = c.post("/api/modules/import", json={"source": "url", "url": "%s/%s.modpkg" % (url_base, MID)})
        show("import url (no sha256)", r3)
        print("[VERDICT] R2 远程导入强制 sha256: %s"
              % (r3.json().get("error_code") == "MODULE_PACKAGE_SHA256_REQUIRED"))
        print("[CHK] content_sha256: local=%s library=%s url=%s"
              % (LOCAL_SHA.get("v"), LIB_SHA.get("v"), body.get("content_sha256")))
        print("[VERDICT] R2 下载后导入内容无损(三路 content_sha256 一致): %s"
              % (LOCAL_SHA.get("v") and LOCAL_SHA["v"] == LIB_SHA.get("v") == body.get("content_sha256")))
    finally:
        httpd.shutdown()
        httpd.server_close()

    hr("7. R3 导入后地图/事件准备 (房间/区域/家具锚点 + 事件图 + NPC 卡 + 线索, 悬挂边 0)")
    cmd("GET %s/api/modules/%s/prepared" % (base, MID))
    prep = show("prepared", c.get("/api/modules/%s/prepared" % MID)).get("prepared") or {}
    print("[CHK] ready=%s counts=%s" % (prep.get("ready"), json.dumps(prep.get("counts"), ensure_ascii=False)))
    print("[CHK] checks=%s" % json.dumps(prep.get("checks"), ensure_ascii=False))
    print("[CHK] event_graph dangling=%s acyclic=%s initial=%s"
          % (prep.get("event_graph", {}).get("dangling_edges"),
             prep.get("event_graph", {}).get("acyclic"), prep.get("event_graph", {}).get("initial_scene")))
    for m in prep.get("maps", []):
        for room in m.get("rooms", []):
            print("      map=%s room=%-6s anchors=%d %s" % (m["id"], room["id"], len(room["anchors"]),
                  [a["id"] for a in room["anchors"]]))
    print("[CHK] npcs=%s" % json.dumps([n["id"] for n in prep.get("npcs", [])], ensure_ascii=False))
    print("[CHK] clues=%s" % json.dumps([cl["id"] for cl in prep.get("clues", [])], ensure_ascii=False))

    hr("8. R22-2 列目录 / 读单个 / 写入 / 软删 (模组 + 规则包各一套)")
    cmd("GET %s/api/modules" % base)
    show("list modules", c.get("/api/modules"))
    cmd("GET %s/api/modules/%s" % (base, MID))
    show("read module", c.get("/api/modules/%s" % MID))
    cmd("PUT %s/api/rulepacks/t1_probe  (写入)" % base)
    show("write rulepack", c.put("/api/rulepacks/t1_probe", json={
        "rulepack_yaml": 'id: t1_probe\nversion: "1.0.0"\ndisplay_name: "T1 取证规则包"\n'}))
    cmd("GET %s/api/rulepacks" % base)
    show("list rulepacks", c.get("/api/rulepacks"))
    cmd("DELETE %s/api/modules/%s?reason=evidence" % (base, MID))
    d = show("soft delete module", c.delete("/api/modules/%s" % MID, params={"reason": "evidence"}))
    print("[CHK] on_disk=%s physical_delete=%s dir_exists=%s"
          % (d.get("on_disk"), d.get("physical_delete"), (ROOT / "modules" / MID).is_dir()))
    cmd("GET %s/api/modules/%s  (软删后读单个)" % (base, MID))
    show("read after soft delete", c.get("/api/modules/%s" % MID))
    cmd("GET %s/api/modules  (软删后列目录)" % base)
    show("list after soft delete", c.get("/api/modules"))
    cmd("DELETE %s/api/rulepacks/t1_probe" % base)
    show("soft delete rulepack", c.delete("/api/rulepacks/t1_probe"))
    print("[CHK] rulepack dir still on disk: %s" % (ROOT / "rulepacks" / "t1_probe" / "rulepack.yaml").is_file())
    cmd("POST %s/api/modules/%s/restore" % (base, MID))
    show("restore module", c.post("/api/modules/%s/restore" % MID))

    hr("9. 真实交付模组只读验收 (sample_coc / blackwater_creek)")
    for mid in ("sample_coc", "blackwater_creek"):
        cmd("GET %s/api/modules/%s + /prepared" % (base, mid))
        det = show("read %s" % mid, c.get("/api/modules/%s" % mid))
        p = show("prepared %s" % mid, c.get("/api/modules/%s/prepared" % mid)).get("prepared") or {}
        print("[CHK] %s counts=%s ready=%s dangling=%s rooms_with_anchors=%s"
              % (mid, json.dumps(p.get("counts"), ensure_ascii=False), p.get("ready"),
                 p.get("checks", {}).get("dangling_edges"),
                 all(r["anchors"] for m in p.get("maps", []) for r in m["rooms"])))

    hr("10. 清理临时素材")
    for p in (ROOT / "modules" / MID, ROOT / "rulepacks" / "t1_probe",
              ROOT / "data" / "module_prep" / ("%s.json" % MID)):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.is_file():
            p.unlink()
    shutil.rmtree(SCRATCH, ignore_errors=True)
    # 清掉本次取证写进 tables_registry.json 的临时桌 (避免污染交付包测试数据)
    reg = ROOT / "data" / "tables_registry.json"
    if reg.is_file():
        try:
            data = json.loads(reg.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                before = len(data)
                data = {k: v for k, v in data.items()
                        if MID not in k and MID not in json.dumps(v, ensure_ascii=False)}
                inner = data.get("tables")
                if isinstance(inner, dict):
                    data["tables"] = {k: v for k, v in inner.items()
                                      if MID not in k and MID not in json.dumps(v, ensure_ascii=False)}
                elif isinstance(inner, list):
                    data["tables"] = [t for t in inner if MID not in json.dumps(t, ensure_ascii=False)]
                reg.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                print("[CHK] tables_registry cleaned: %d -> %d keys=%s"
                      % (before, len(data), sorted(data)[:10]))
        except Exception as exc:
            print("[WARN] tables_registry cleanup skipped: %s" % exc)
    # 清掉本次取证留下的墓碑/导入日志
    for t in (ROOT / "modules" / ".tombstones.json", ROOT / "rulepacks" / ".tombstones.json"):
        if t.is_file():
            try:
                d = json.loads(t.read_text(encoding="utf-8"))
                ents = d.get("entries") if isinstance(d.get("entries"), dict) else {}
                d["entries"] = {k: v for k, v in ents.items() if k not in (MID, "t1_probe")}
                t.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
                print("[CHK] tombstone %s entries=%s" % (t.parent.name, sorted(d["entries"])))
            except Exception as exc:
                print("[WARN] tombstone cleanup skipped: %s" % exc)
    log = ROOT / "data" / "repo_imports.jsonl"
    if log.is_file():
        log.unlink()
        print("[CHK] repo_imports.jsonl removed (取证日志, 下次真实导入会重建)")
    c.post("/api/repository/rebuild")
    print("[CHK] modules now: %s" % [e["id"] for e in c.get("/api/modules").json()["entries"]])
    print("[CHK] rulepacks now: %s" % [e["id"] for e in c.get("/api/rulepacks").json()["entries"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
