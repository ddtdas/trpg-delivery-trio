"""T5 取证脚本: 死光.modpkg (R25/R26) + 库/下载 (R24) + 热重载 (R27) —— 真实 HTTP + 真实 WS。

用法: python scripts/_t5_evidence.py --base http://127.0.0.1:9212 --root <服务端根> [--token <webapp token>]

判据: 命令 -> 原始输出 -> 判定。全部走真实 HTTP/WS, 不用 TestClient。
自清理: 解绑热重载 / 删除本次导入的副本 / 还原保存文件。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VERDICTS: list[tuple[str, bool]] = []
FROZEN_SERVER_KINDS = ("STATE_DELTA", "TURN_UPDATED", "NARRATION_PENDING",
                       "NARRATION_APPROVED", "WHISPER", "INFO_REVEALED",
                       "BRANCH_TAKEN", "JOB_STATUS")


def head(t: str) -> None:
    print("\n" + "=" * 78)
    print("== " + t)
    print("=" * 78)


def verdict(name: str, ok: bool, extra: str = "") -> None:
    VERDICTS.append((name, bool(ok)))
    print("[VERDICT] %-52s %s %s" % (name, bool(ok), extra))


def req(base: str, path: str, body=None, method: str | None = None, raw: bool = False):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(base + path, data=data,
                               method=method or ("POST" if data else "GET"),
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            payload = x.read()
            return x.status, (payload if raw else json.loads(payload.decode("utf-8")))
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload.decode("utf-8"))
        except Exception:
            return e.code, {"_raw": payload[:400].decode("utf-8", "replace")}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


# ------------------------------------------------------------------ 极简 WS 客户端
class WS:
    """无第三方依赖的 WebSocket 客户端 (握手 + 文本帧 + ping/pong + close)。"""

    def __init__(self, host: str, port: int, path: str, timeout: float = 20.0) -> None:
        self.s = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
                     "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                     "Sec-WebSocket-Version: 13\r\n\r\n") % (path, host, port, key)
        self.s.sendall(handshake.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.s.recv(4096)
            if not chunk:
                raise RuntimeError("ws handshake closed")
            buf += chunk
        head_raw, self.rest = buf.split(b"\r\n\r\n", 1)
        status = head_raw.split(b"\r\n")[0].decode("latin-1")
        if "101" not in status:
            raise RuntimeError("ws handshake failed: %s" % status)

    def _need(self, n: int) -> None:
        while len(self.rest) < n:
            chunk = self.s.recv(4096)
            if not chunk:
                raise RuntimeError("ws closed")
            self.rest += chunk

    def recv(self, timeout: float = 20.0):
        self.s.settimeout(timeout)
        deadline = time.time() + timeout
        while True:
            self._need(2)
            b1, b2 = self.rest[0], self.rest[1]
            opcode = b1 & 0x0F
            ln = b2 & 0x7F
            off = 2
            if ln == 126:
                self._need(4)
                ln = struct.unpack(">H", self.rest[2:4])[0]
                off = 4
            elif ln == 127:
                self._need(10)
                ln = struct.unpack(">Q", self.rest[2:10])[0]
                off = 10
            self._need(off + ln)
            payload = self.rest[off:off + ln]
            self.rest = self.rest[off + ln:]
            if opcode == 1:
                return json.loads(payload.decode("utf-8"))
            if opcode == 8:
                raise RuntimeError("ws closed by server")
            if opcode == 9:
                self.s.sendall(b"\x8a\x80" + os.urandom(4))
                continue
            if time.time() > deadline:
                raise TimeoutError("ws recv timeout")

    def close(self) -> None:
        try:
            self.s.close()
        except Exception:
            pass


# ------------------------------------------------------------------ 凭据解析
def _resolve_token(cli_token: str | None, root: Path) -> str:
    """D2：脚本内**零凭据字面量** —— token 只能来自命令行或交付包自带的配置。

    读取顺序：
      1) 显式 --token（CI / 自动化场景）
      2) <root>/configs/access_config.yaml 的 ends.webapp.token
    两者都取不到时返回空串（调用方据此以退出码 2 终止）。
    本函数**从不打印 token 值**，只打印来源与长度，避免日志二次泄露。
    """
    if cli_token:
        print("token: 来自 --token（不回显），长度=%d" % len(cli_token))
        return cli_token
    cfg_path = root / "configs" / "access_config.yaml"
    if not cfg_path.is_file():
        print("FATAL: 既未给 --token，也找不到 %s" % cfg_path, file=sys.stderr)
        return ""
    import yaml
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:                       # noqa: BLE001
        print("FATAL: 解析 %s 失败: %r" % (cfg_path, exc), file=sys.stderr)
        return ""
    tk = str((((cfg.get("ends") or {}).get("webapp")) or {}).get("token") or "")
    if not tk:
        print("FATAL: %s 的 ends.webapp.token 为空" % cfg_path, file=sys.stderr)
        return ""
    print("token: 来自 %s 的 ends.webapp（不回显），长度=%d" % (cfg_path.name, len(tk)))
    return tk


# ------------------------------------------------------------------ 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:9212")
    ap.add_argument("--root", default=".")
    # D2（captain 裁决）：取证脚本内**不得出现凭据字面量**。
    # 显式 --token 优先；缺省时从交付包自带的 configs/access_config.yaml 读取，且只读不回显。
    ap.add_argument("--token", default=None,
                    help="webapp token（缺省从 <root>/configs/access_config.yaml "
                         "的 ends.webapp.token 读取；脚本内不存凭据）")
    ap.add_argument("--pkg", default="")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    root = Path(a.root).resolve()
    a.token = _resolve_token(a.token, root)
    if not a.token:
        return 2
    pkg = Path(a.pkg) if a.pkg else (root / "死光.modpkg")
    save = root / "modules" / "dead_light" / "compiled" / "save_state.json"
    # 备份**按 LF 归一化**后再留: 本脚本必须幂等 —— 跑完不得把 CRLF 留在交付树上。
    # (DEFECT-004 的最后一处实例正出在这里: 下面改写保存文件时漏了 newline="\n",
    #  Windows 下写成 CRLF; 而末尾"还原"又把旧快照原样搬回, 于是污染被永久保留,
    #  目录摘要随之变化 -> modules/index.json 立刻变陈旧。)
    save_backup = (save.read_bytes().replace(b"\r\n", b"\n")
                   if save.is_file() else None)

    # ---------------------------------------------------------------- 0 确定性构建
    head("0. 确定性: 二次构建 死光.modpkg 逐字节一致 + 重建索引")
    sys.path.insert(0, str(root))
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_t5_build_deadlight", root / "scripts" / "_t5_build_deadlight.py")
    bmod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(bmod)
    from app.repository.pkg import pack_module as _pack

    bmod.build_module(root)
    _pack(root / "modules" / "dead_light", pkg, deterministic=True)
    sha_a = sha256_file(pkg)
    bmod.build_module(root)
    _pack(root / "modules" / "dead_light", pkg, deterministic=True)
    sha_b = sha256_file(pkg)
    print("build#1 sha256 =", sha_a)
    print("build#2 sha256 =", sha_b)
    verdict("R26-4 二次构建 sha256 相同(确定性)", sha_a == sha_b)

    s_rb, rb_body = req(base, "/api/repository/rebuild", {}, "POST")
    print("POST /api/repository/rebuild ->", s_rb,
          json.dumps(rb_body, ensure_ascii=False)[:260])
    verdict("R22-1 重建索引成功", s_rb == 200)

    # ---------------------------------------------------------------- 1 容器结构
    head("1. R25/R26 单文件容器结构 (source/ 与 compiled/ 两类内容齐备)")
    import zipfile
    zf = zipfile.ZipFile(pkg)
    names = zf.namelist()
    print("pkg =", pkg, os.path.getsize(pkg), "bytes")
    print("sha256 =", sha256_file(pkg))
    print("entries = %d" % len(names))
    for n in sorted(names):
        print("   ", n)
    src = sorted(n for n in names if n.startswith("source/"))
    comp = sorted(n for n in names if n.startswith("compiled/"))
    print("source/   =", src)
    print("compiled/ =", comp)
    verdict("R26-1 容器含 source/", len(src) >= 3)
    verdict("R26-2 容器含 compiled/", len(comp) >= 3)

    prov = json.loads((root / "modules" / "dead_light" / "source" / "PROVENANCE.json")
                      .read_text(encoding="utf-8"))
    print("PROVENANCE.source_type =", prov["source_type"])
    print("PROVENANCE.original_title =", prov["original_title"], "/", prov["publisher"])
    print("PROVENANCE.sources =", [s["url"] for s in prov["sources"]])
    print("PROVENANCE.not_included =", prov["not_included"])
    verdict("R26-3 source/ 仅公开元数据+摘要+出处(D-05)",
            prov["source_type"] == "public_metadata_only" and bool(prov["not_included"]))

    # ---------------------------------------------------------------- 2 R24 库列表
    head("2. R24 模组库列表: 名称/规则包/版本/校验和/大小")
    s, idx = req(base, "/api/modules")
    print("GET /api/modules ->", s)
    rows = idx.get("entries", [])
    for e in rows:
        print("   %-18s %-10s %-8s %-8s %s %s" % (e["id"], e.get("ruleset"), e.get("version"),
                                                  e.get("name"), str(e.get("sha256"))[:16],
                                                  e.get("size")))
    dl = [e for e in rows if e["id"] == "dead_light"]
    verdict("R24-1 库列表含 dead_light 且字段齐全",
            bool(dl) and all(dl[0].get(k) not in (None, "") for k in
                             ("id", "name", "ruleset", "version", "sha256", "size", "path")))

    # ---------------------------------------------------------------- 3 导入
    head("3. R1/R2 导入 死光.modpkg (sha256 强制校验)")
    before = sha256_file(pkg)          # 必须取「当前磁盘上」的包摘要, 否则会被判 sha256 不一致
    s, imp1 = req(base, "/api/modules/import",
                  {"source": "local", "path": str(pkg), "sha256": before, "overwrite": True,
                   "open_session": True})
    print("POST /api/modules/import ->", s)
    print("counts =", json.dumps(imp1.get("counts"), ensure_ascii=False, sort_keys=True))
    print("declared_verified =", imp1.get("declared_verified"))
    print("content_sha256 =", imp1.get("content_sha256"))
    print("session.campaign_id =", (imp1.get("session") or {}).get("campaign_id"))
    print("session.table_id    =", (imp1.get("session") or {}).get("table_id"))
    campaign = (imp1.get("session") or {}).get("campaign_id", "")
    table = (imp1.get("session") or {}).get("table_id", "")
    verdict("R1-1 导入成功 201", s == 201)
    verdict("R1-2 计数与声明一致", imp1.get("declared_verified") is True)
    verdict("R1-3 counts 与场景设计一致",
            imp1.get("counts", {}).get("rooms") == 10
            and imp1.get("counts", {}).get("event_nodes") == 14
            and imp1.get("counts", {}).get("npcs") == 5)

    # ---------------------------------------------------------------- 4 下载->导入
    head("4. R24 一键下载即可直接导入 (下载的 .modpkg 重新导入内容无损)")
    s, blob = req(base, "/api/modules/dead_light/download", raw=True)
    got = root / "data" / ".repo_staging" / "ev_downloaded.modpkg"
    got.parent.mkdir(parents=True, exist_ok=True)
    got.write_bytes(blob)
    print("GET /api/modules/dead_light/download ->", s, len(blob), "bytes")
    print("downloaded sha256 =", sha256_bytes(blob))
    s2, imp2 = req(base, "/api/modules/import",
                   {"source": "local", "path": str(got), "sha256": sha256_bytes(blob),
                    "module_id": "dead_light_copy", "overwrite": True})
    print("POST /api/modules/import (下载件) ->", s2)
    print("content_sha256#1 =", imp1.get("content_sha256"))
    print("content_sha256#2 =", imp2.get("content_sha256"))
    verdict("R24-2 下载件可直接导入", s2 == 201)
    verdict("R24-3 下载->导入 内容无损(sha256 相同)",
            imp1.get("content_sha256") == imp2.get("content_sha256"))

    # ---------------------------------------------------------------- 5 R3 准备
    head("5. R3 导入后地图/事件准备 (锚点 + 事件图 + NPC + 线索, 悬挂边为 0)")
    s, prep = req(base, "/api/modules/dead_light/prepared")
    pd = prep.get("prepared", {})
    print("GET /api/modules/dead_light/prepared ->", s, "cached =", prep.get("cached"))
    print("ready =", pd.get("ready"), "counts =",
          json.dumps(pd.get("counts"), ensure_ascii=False, sort_keys=True))
    print("checks =", json.dumps(pd.get("checks"), ensure_ascii=False, sort_keys=True)[:420])
    verdict("R3-1 prepared ready=True", pd.get("ready") is True)
    verdict("R3-2 悬挂边为 0", pd.get("checks", {}).get("dangling_edges") == 0)
    verdict("R3-3 事件图无环且从初始场景可达",
            pd.get("event_graph", {}).get("acyclic") is True
            and pd.get("checks", {}).get("graph_connected_from_start") is True)

    # ---------------------------------------------------------------- 6 可交互物
    head("6. 每个可交互物 {房间, 锚点, 动作集} 齐备且位置落在房间边界内")
    comp = json.loads((root / "modules" / "dead_light" / "compiled" /
                       "dead_light.compiled.json").read_text(encoding="utf-8"))
    rects = {r["id"]: r["rect"] for m in comp["maps"] for r in m["rooms"]}
    n_ok = n_bad = 0
    for m in comp["maps"]:
        for it in m["interactables"]:
            rc = rects.get(it["room"])
            ok = (rc is not None and bool(it["anchor"]) and bool(it["actions"])
                  and rc["x"] <= it["x"] <= rc["x"] + rc["w"]
                  and rc["y"] <= it["y"] <= rc["y"] + rc["h"])
            n_ok += ok
            n_bad += (not ok)
    print("interactables = %d, 契约通过 = %d, 违例 = %d" % (n_ok + n_bad, n_ok, n_bad))
    print("sample:", json.dumps(comp["maps"][0]["interactables"][0], ensure_ascii=False))
    verdict("R26-5 全部可交互物满足 {房间,锚点,动作集}+边界内",
            n_ok == 22 and n_bad == 0)

    # ---------------------------------------------------------------- 7 绑定 + 幂等
    head("7. R27 绑定保存文件 + 二次导入 diff 为空 (确定性)")
    s, b = req(base, "/api/hotreload/bind",
               {"campaign_id": campaign, "module_id": "dead_light", "table_id": table})
    print("POST /api/hotreload/bind ->", s, json.dumps(b.get("bound", {}), ensure_ascii=False)[:220])
    s, ap1 = req(base, "/api/hotreload/apply", {"campaign_id": campaign})
    print("apply#1 ->", s, "change_count =", ap1.get("change_count"), "digest =", ap1.get("digest"))
    s, ap2 = req(base, "/api/hotreload/apply", {"campaign_id": campaign})
    print("apply#2 ->", s, "change_count =", ap2.get("change_count"), "seqs =", ap2.get("seqs"))
    verdict("R27-1 二次导入 diff 为空", ap2.get("change_count") == 0 and ap2.get("seqs") == [])
    digest_before = ap1.get("digest")

    # ---------------------------------------------------------------- 8 真 WS 推送
    head("8. R27 真 WS 客户端: 改保存文件 -> 后台监听自动热重载 -> 收到推送帧")
    host, port = base.split("//")[1].split("/")[0].split(":")
    ws = None
    frames: list[dict] = []
    try:
        ws = WS(host, int(port), "/ws?table=%s&viewer=kp&role=kp&token=%s&last_seq=-1"
                % (table, a.token))
        print("WS 握手 101 成功: /ws?table=%s&viewer=kp&role=kp" % table)
    except Exception as exc:  # noqa: BLE001
        print("WS 握手失败:", exc)
    if ws is not None:
        state = json.loads(save.read_text(encoding="utf-8"))
        moved = state["maps"][0]["interactables"][0]
        old_x = moved["x"]
        moved["x"] = float(old_x) + 3.0
        state["clues"].append({"id": "c_ev_probe", "kind": "mark", "location": "n_lobby"})
        save.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8", newline="\n")
        print("已改保存文件: it_fuel_pump.x %s -> %s, 追加线索 c_ev_probe" % (old_x, moved["x"]))
        print("不调用任何手动接口, 只等后台监听 (interval=1.0s) ...")
        t0 = time.time()
        t_first = None
        # 只等「变更帧」: PING 是冻结契约 §4 的心跳帧 (明确不在 8+6 之内), 不计入。
        try:
            while time.time() - t0 < 15:
                f = ws.recv(timeout=15)
                if f.get("kind") == "PING":
                    continue
                if t_first is None:
                    t_first = time.time() - t0
                frames.append(f)
                if len(frames) >= 2:
                    break
        except Exception as exc:  # noqa: BLE001
            print("WS 收取结束:", type(exc).__name__, exc)
        elapsed = t_first if t_first is not None else 99.0
        print("收到 %d 个变更帧, 首帧用时 %.2fs" % (len(frames), elapsed))
        for f in frames[:12]:
            print("   kind=%-20s seq=%-4s scope=%-8s delta=%s"
                  % (f.get("kind"), f.get("seq"), f.get("scope"),
                     json.dumps(f.get("delta"), ensure_ascii=False)[:90]))
        kinds = {f.get("kind") for f in frames}
        verdict("R27-2 收到推送帧(无需手动调用)", len(frames) > 0)
        verdict("R27-3 变更帧类型全部属于冻结 8 帧 (PING 为契约 §4 心跳, 不计)",
                bool(kinds) and kinds <= set(FROZEN_SERVER_KINDS), str(sorted(kinds)))
        verdict("R27-4 若干秒内(<=8s)自动热重载并推送", 0 < len(frames) and elapsed <= 8.0,
                "%.2fs" % elapsed)
    else:
        verdict("R27-2 收到推送帧(无需手动调用)", False, "WS 不可用")

    s, st = req(base, "/api/hotreload/state?campaign_id=" + campaign)
    print("GET /api/hotreload/state ->", s)
    print("binding =", json.dumps(st.get("binding", {}), ensure_ascii=False))
    bd = st.get("binding", {})
    verdict("R27-5 状态已被后台监听更新",
            bd.get("apply_count", 0) >= 2 and bd.get("applied_digest") != digest_before)
    s_hs, hs = req(base, "/api/hotreload/status")
    print("GET /api/hotreload/status ->", s_hs, "running =", hs.get("running"),
          "polls =", hs.get("polls"), "hot_applies =", hs.get("hot_applies"),
          "interval_s =", hs.get("interval_s"))
    verdict("R27-6 后台监听任务在跑且确实轮询过",
            s_hs == 200 and hs.get("running") is True and int(hs.get("polls") or 0) >= 1)

    # ---------------------------------------------------------------- 9 回滚
    head("9. R27 旧状态可回滚")
    s, rb = req(base, "/api/hotreload/rollback", {"campaign_id": campaign, "steps": 1})
    print("POST /api/hotreload/rollback ->", s)
    print("rolled_back_steps =", rb.get("rolled_back_steps"), "digest =", rb.get("digest"))
    print("change_count =", rb.get("change_count"), "seqs =", rb.get("seqs"))
    print("changes =", json.dumps([c.get("type") for c in rb.get("changes", [])], ensure_ascii=False))
    verdict("R27-7 回滚后回到旧状态摘要", rb.get("digest") == digest_before)
    verdict("R27-8 回滚落库(SNAPSHOT_LOADED, 既有类型)",
            bool(rb.get("seqs")) and any(c.get("type") == "SNAPSHOT_LOADED"
                                         for c in rb.get("changes", [])))

    # ---------------------------------------------------------------- 10 错误码
    head("10. 明确错误码, 绝不 500")
    probes = [
        ("未绑定 -> HOTRELOAD_NOT_BOUND", "/api/hotreload/apply",
         {"campaign_id": "no_such_campaign_xyz"}, 404, "HOTRELOAD_NOT_BOUND"),
        ("越界可交互物 -> COMPILED_INTERACTABLE_OUT_OF_ROOM", "/api/hotreload/apply",
         {"campaign_id": campaign,
          "state": dict(comp, maps=[dict(comp["maps"][0],
                                        interactables=[dict(comp["maps"][0]["interactables"][0],
                                                            x=99999.0)])] + comp["maps"][1:])},
         422, "COMPILED_INTERACTABLE_OUT_OF_ROOM"),
        ("缺动作集 -> COMPILED_INTERACTABLE_ACTIONS_MISSING", "/api/hotreload/apply",
         {"campaign_id": campaign,
          "state": dict(comp, maps=[dict(comp["maps"][0],
                                        interactables=[dict(comp["maps"][0]["interactables"][0],
                                                            actions=[])])] + comp["maps"][1:])},
         422, "COMPILED_INTERACTABLE_ACTIONS_MISSING"),
        ("路径穿越 -> REPO_PATH_TRAVERSAL", "/api/hotreload/bind",
         {"campaign_id": "x", "save_path": "../../../etc/passwd"}, 400, "REPO_PATH_TRAVERSAL"),
    ]
    all_ok = True
    for label, path, body, want_status, want_code in probes:
        st_code, resp = req(base, path, body)
        code = resp.get("error_code")
        ok = (st_code == want_status and code == want_code)
        all_ok = all_ok and ok and st_code != 500
        print("%-56s -> %s %s  %s" % (label, st_code, code, "OK" if ok else "MISMATCH"))
    verdict("R27-9 四类错误均返回明确码且非 500", all_ok)

    # ---------------------------------------------------------------- 11 清理
    head("11. 自清理")
    if ws is not None:
        ws.close()
    req(base, "/api/hotreload/unbind", {"campaign_id": campaign})
    if table:
        s_t, _ = req(base, "/api/tables/%s" % table, None, "DELETE")
        print("DELETE /api/tables/%s -> %s (清理本次开局句柄)" % (table, s_t))
    if save_backup is not None:
        save.write_bytes(save_backup)
    if got.is_file():
        got.unlink()
    print("已解绑热重载 / 还原保存文件 / 删除下载件")
    print("modules 目录:", sorted(p.name for p in (root / "modules").iterdir()))
    verdict("清理后无残留副本", not (root / "modules" / "dead_light_copy").exists())

    head("汇总")
    for n, ok in VERDICTS:
        print("[VERDICT] %-52s %s" % (n, ok))
    bad = [n for n, ok in VERDICTS if not ok]
    print("\nTOTAL=%d  FAILED=%d" % (len(VERDICTS), len(bad)))
    if bad:
        print("FAILED:", bad)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
