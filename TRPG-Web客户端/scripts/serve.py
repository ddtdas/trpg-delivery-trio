#!/usr/bin/env python3
"""TRPG 客户端 —— 零依赖本地静态服务器 + 同源反向代理（SPEC §六 方案 B）。

一个端口同时承担两件事：

  1. 静态托管 `client/`，使 http://127.0.0.1:<port>/index.html?server=... 可直接打开；
  2. **同源反向代理** /api/*、/access/*、/ws 到真实服务端。

为什么需要反代：浏览器同源策略会拦掉跨源的 fetch 与 WebSocket。
让页面一律走同源（页面 origin = 本机静态服务），再由本进程转发到真实服务端，
就一次性解决了 fetch 与 WebSocket 两类跨源，且**不需要改动服务端冻结面**。

/ws 支持 WebSocket 升级：转发握手；上游回 101 后进入**双向字节透传**。

代理目标解析顺序（SPEC §六）：
  1. 请求自带的 ?server=<url>（单请求覆盖）
  2. --proxy-target 命令行
  3. run/client.json 的 proxy_target / server 字段
  4. ../trpg-server/run/server.json 的 port
  目标不可达 -> 502 + 明确 JSON 提示（绝不静默挂起）。

日志：本进程自己打开 --log 指定的文件并接管 stdout/stderr，
**不依赖调用方的管道重定向** —— 否则本进程会继承调用方（cmd/PowerShell）的
stdout 句柄，导致调用方永远等不到管道 EOF 而卡住。
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import select
import socket
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

SERVICE_NAME = "trpg-client"
IDENTITY_PATH = "/__trpg_client__"
VERSION = "1.1.0"

CRLF = chr(13) + chr(10)
CRLF2 = CRLF + CRLF
CRLFB = CRLF.encode()
CRLF2B = CRLF2.encode()

PROXY_PREFIXES = ("/api/", "/access/")
PROXY_EXACT = ("/ws", "/api", "/access")
PROXY_TIMEOUT = 15
WS_CONNECT_TIMEOUT = 10


def is_proxy_path(path: str) -> bool:
    p = path.split("?")[0]
    return p in PROXY_EXACT or p.startswith(PROXY_PREFIXES)


class Handler(SimpleHTTPRequestHandler):
    """静态托管 + 同源反代 + 身份端点。"""

    server_version = "trpg-client-serve/1.1"
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, obj: dict) -> None:
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _send_502(self, exc: object, target: str) -> None:
        self._send_json(502, {
            "ok": False,
            "error": "proxy_target_unreachable",
            "detail": "无法连接服务端 " + target + ": " + str(exc),
            "hint": "请确认服务端已启动（trpg-server/start.bat），"
                    "或用 start.bat <port> <server-url> 指定地址。",
        })

    def _send_identity(self) -> None:
        self._send_json(200, {
            "service": SERVICE_NAME,
            "ok": True,
            "pid": os.getpid(),
            "port": self.server.server_address[1],
            "version": VERSION,
            "proxy_target": self.server.proxy_target or "",
        })

    def _request_target(self) -> str:
        q = parse_qs(urlparse(self.path).query)
        override = q.get("server", [""])[0]
        if override:
            return override
        return self.server.proxy_target or ""

    def _proxy_http(self, target: str) -> None:
        u = urlparse(target)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "https" else 80)

        body = None
        cl = self.headers.get("Content-Length")
        if cl:
            try:
                body = self.rfile.read(int(cl))
            except (ValueError, OSError):
                body = None

        headers = {}
        for k, v in self.headers.items():
            if k.lower() in ("host", "connection", "accept-encoding"):
                continue
            headers[k] = v
        headers["Host"] = host + ":" + str(port)

        conn = None
        try:
            conn = http.client.HTTPConnection(host, port, timeout=PROXY_TIMEOUT)
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            status = resp.status
            resp_headers = resp.getheaders()
        except Exception as exc:            # noqa: BLE001 - 上游任何故障都转 502
            self._send_502(exc, target)
            return
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:           # noqa: BLE001
                    pass

        self.send_response(status)
        for k, v in resp_headers:
            if k.lower() in ("transfer-encoding", "connection", "content-length"):
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _proxy_websocket(self, target: str) -> None:
        u = urlparse(target)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "https" else 80)

        try:
            upstream = socket.create_connection((host, port), timeout=WS_CONNECT_TIMEOUT)
        except Exception as exc:            # noqa: BLE001
            self._send_502(exc, target)
            return

        # 重放握手：保留客户端全部头（含 Sec-WebSocket-Key），只换 Host
        lines = ["GET " + self.path + " HTTP/1.1"]
        for k, v in self.headers.items():
            if k.lower() == "host":
                continue
            lines.append(k + ": " + v)
        lines.append("Host: " + host + ":" + str(port))
        try:
            upstream.sendall((CRLF.join(lines) + CRLF2).encode("latin-1"))
        except OSError as exc:
            upstream.close()
            self._send_502(exc, target)
            return

        buf = b""
        try:
            upstream.settimeout(WS_CONNECT_TIMEOUT)
            while CRLF2B not in buf:
                chunk = upstream.recv(4096)
                if not chunk:
                    break
                buf += chunk
        except OSError:
            pass

        head, sep, rest = buf.partition(CRLF2B)
        if not head or not sep:
            upstream.close()
            self._send_502("no HTTP response from upstream", target)
            return

        status_line = head.split(CRLFB)[0].decode("latin-1", "replace")

        try:
            self.connection.sendall(head + CRLF2B)
            if rest:
                self.connection.sendall(rest)
        except OSError:
            upstream.close()
            return

        if " 101" not in status_line:
            # 上游拒绝升级（如 403）：响应已透传，收尾即可
            upstream.close()
            self.close_connection = True
            return

        self._pump(self.connection, upstream)

    @staticmethod
    def _pump(client: socket.socket, upstream: socket.socket) -> None:
        """101 之后的双向字节透传，直到任一端关闭。"""
        client.setblocking(False)
        upstream.setblocking(False)
        socks = [client, upstream]
        try:
            while True:
                try:
                    r, _, x = select.select(socks, [], socks, 30)
                except (OSError, ValueError):
                    return
                if x:
                    return
                if not r:
                    continue                # 30s 静默：继续等（心跳由服务端下发）
                for s in r:
                    other = upstream if s is client else client
                    try:
                        data = s.recv(65536)
                    except BlockingIOError:
                        continue
                    except OSError:
                        return
                    if not data:
                        return
                    try:
                        other.sendall(data)
                    except OSError:
                        return
        finally:
            try:
                upstream.close()
            except OSError:
                pass

    def _serve_html_with_hint(self, path_only: str) -> bool:
        """未配置服务端时，在页面顶部注入一条中文提示。

        只改本进程的输出，**不改动 client/ 目录里的任何文件** ——
        client/ 的 6 个文件必须与权威源逐字节一致，不能在打包期改写。
        返回 True 表示已处理（调用方直接 return）。
        """
        if self.server.proxy_target:
            return False
        if path_only not in ("/", "/index.html"):
            return False
        index = Path(self.directory) / "index.html"
        if not index.is_file():
            return False
        try:
            html = index.read_text(encoding="utf-8")
        except OSError:
            return False
        if "<body>" not in html:
            return False
        banner = (
            '<div style="margin:0;padding:10px 14px;background:#3a2a12;color:#ffcf7a;'
            'border-bottom:1px solid #7a5a20;font:14px/1.7 system-ui,"Microsoft YaHei",sans-serif">'
            '请先启动服务端，或在本页填写服务端地址 —— 双击「TRPG-服务端\\start.bat」启动服务端；'
            '若两个压缩包不在同一父目录，请在下方「服务器地址」填写服务端地址（如 http://127.0.0.1:9210）后点「测试连接」。'
            '<br>注意：本页地址栏里的 ?server= 请保持为本页地址，不要改成服务端端口。</div>'
        )
        html = html.replace("<body>", "<body>" + banner, 1)
        payload = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)
        return True

    def _dispatch(self) -> None:
        if self.path.split("?")[0] == IDENTITY_PATH:
            self._send_identity()
            return

        if not is_proxy_path(self.path):
            if self.command in ("GET", "HEAD"):
                if self._serve_html_with_hint(self.path.split("?")[0]):
                    return
                super().do_GET()
            else:
                self._send_json(405, {"ok": False, "error": "method_not_allowed"})
            return

        target = self._request_target()
        if not target:
            self._send_json(502, {
                "ok": False,
                "error": "proxy_target_unknown",
                "detail": "未指定服务端地址，无法转发 " + self.path,
                "hint": "请先启动服务端（双击「TRPG-服务端\\start.bat」），"
                        "或用 start.bat <port> <server-url> 指定地址。",
            })
            return

        if self.path.split("?")[0] == "/ws":
            self._proxy_websocket(target)
        else:
            self._proxy_http(target)

    def do_GET(self) -> None:      # noqa: N802
        self._dispatch()

    def do_HEAD(self) -> None:     # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:     # noqa: N802
        self._dispatch()

    def do_PUT(self) -> None:      # noqa: N802
        self._dispatch()

    def do_PATCH(self) -> None:    # noqa: N802
        self._dispatch()

    def do_DELETE(self) -> None:   # noqa: N802
        self._dispatch()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._dispatch()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[serve] " + self.address_string() + " " + (fmt % args) + chr(10))
        sys.stderr.flush()


def take_over_log(path: str) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = open(target, "a", encoding="utf-8", buffering=1)
    sys.stdout = handle
    sys.stderr = handle


def resolve_proxy_target(cli_value: str, repo_root: Path) -> str:
    """--proxy-target -> run/client.json -> ../trpg-server/run/server.json"""
    if cli_value:
        return cli_value

    client_json = repo_root / "run" / "client.json"
    if client_json.is_file():
        try:
            obj = json.loads(client_json.read_text(encoding="utf-8"))
            for key in ("proxy_target", "server"):
                if obj.get(key):
                    return str(obj[key])
        except (OSError, ValueError):
            pass

    # 同级目录候选名：开发树叫 trpg-server；交付包解压后叫「TRPG-服务端」。
    for sib_name in ("trpg-server", "TRPG-服务端"):
        sibling = repo_root.parent / sib_name / "run" / "server.json"
        if not sibling.is_file():
            continue
        try:
            obj = json.loads(sibling.read_text(encoding="utf-8"))
            port = int(obj.get("port") or 0)
            if port > 0:
                return "http://127.0.0.1:" + str(port)
        except (OSError, ValueError, TypeError):
            pass

    return ""



def _access_urls(host, port):
    """返回可供访问的 URL 列表。绑定 0.0.0.0 时列出本机全部非回环 IPv4。"""
    loop = "http://127.0.0.1:" + str(port) + "/index.html"
    if host not in ("0.0.0.0", "::", ""):
        return ["http://" + host + ":" + str(port) + "/index.html"]
    urls = [loop]
    seen = {"127.0.0.1"}
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = item[4][0]
            if ip and ip not in seen:
                seen.add(ip)
                urls.append("http://" + ip + ":" + str(port) + "/index.html")
    except OSError:
        pass
    return urls

def main() -> int:
    ap = argparse.ArgumentParser(description="TRPG client static server + same-origin proxy")
    ap.add_argument("--port", type=int, default=0, help="监听端口；0 = 由内核分配")
    ap.add_argument("--root", default=str(REPO_ROOT / "client"), help="站点根目录")
    ap.add_argument("--json", default="", help="把 client.json 发现文件写到该路径")
    ap.add_argument("--log", default="", help="日志文件（自行打开并接管 stdio）")
    ap.add_argument("--proxy-target", default="", help="反代目标，如 http://127.0.0.1:9210")
    ap.add_argument("--host", default=(os.environ.get("TRPG_CLIENT_HOST") or "0.0.0.0"),
                    help="listen address; 127.0.0.1=loopback only, 0.0.0.0=LAN reachable")
    args = ap.parse_args()

    take_over_log(args.log)

    root = Path(args.root).resolve()
    if not (root / "index.html").is_file():
        sys.stderr.write("ERROR: index.html not found under " + str(root) + chr(10))
        return 1

    target = resolve_proxy_target(args.proxy_target, REPO_ROOT)

    handler = partial(Handler, directory=str(root))
    try:
        httpd = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as exc:
        sys.stderr.write("ERROR: cannot bind " + args.host + ":" + str(args.port) + " (" + str(exc) + ")" + chr(10))
        return 2

    port = httpd.server_address[1]
    httpd.proxy_target = target
    httpd.daemon_threads = True

    info = {
        "service": SERVICE_NAME,
        "port": port,
        "host": args.host,
        "bind": args.host + ":" + str(port),
        "urls": _access_urls(args.host, port),
        "pid": os.getpid(),
        "root": str(root),
        "url": "http://127.0.0.1:" + str(port) + "/index.html",
        "identity": "http://127.0.0.1:" + str(port) + IDENTITY_PATH,
        "proxy_target": target,
        "proxy_paths": list(PROXY_PREFIXES) + list(PROXY_EXACT),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if args.json:
        jp = Path(args.json)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    sys.stderr.write("[serve] listening on " + args.host + ":" + str(port) + " (root=" + str(root) + ")" + chr(10))
    for _u in info["urls"]:
        sys.stderr.write("[serve] url = " + _u + chr(10))
    sys.stderr.write("[serve] proxy target = " + (target or "<unresolved>") + chr(10))
    sys.stderr.flush()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
