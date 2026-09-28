"""仓库层集成测试: 走真实 FastAPI 应用 + 真实 HTTP 下载 (R1/R2/R3/R13/R22)。"""
from __future__ import annotations

import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from _pkgbuild import bad_packages, build_module
from app.main import app
from app.repository import index as repo_index
from app.repository.pkg import pack_module, sha256_file
from app.web import rest_repo


@pytest.fixture()
def client(repo_roots):
    rest_repo.set_roots(repo_roots)
    with TestClient(app) as c:
        yield c
    rest_repo.set_roots(repo_repo_default())


def repo_repo_default():
    from app.repository.roots import RepoRoots

    return RepoRoots.default()


@pytest.fixture()
def http_file_server(tmp_path):
    """真实 HTTP 服务器 (用于 R2 的「下载后导入」)。"""
    serve_dir = tmp_path / "http"
    serve_dir.mkdir(parents=True, exist_ok=True)

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):  # noqa: D102
            return

    handler = functools.partial(_Quiet, directory=str(serve_dir))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield serve_dir, "http://127.0.0.1:%d" % port
    finally:
        httpd.shutdown()
        httpd.server_close()


# ------------------------------------------------------------------ R22 API

def test_routes_are_additive_and_reachable(client):
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"])
    for p in ("/api/modules", "/api/modules/import", "/api/modules/{module_id}",
              "/api/rulepacks", "/api/rulepacks/{rulepack_id}",
              "/api/repository/index", "/api/repository/rebuild",
              "/api/repository/error_codes"):
        assert p in paths, p
    # 既有路由未被破坏
    for p in ("/api/health", "/api/tables", "/api/state", "/api/session_state"):
        assert p in paths, p


def test_repository_error_codes_endpoint(client):
    body = client.get("/api/repository/error_codes").json()
    assert body["ok"] is True
    assert body["r13_bad_package_codes"] == {
        "missing_manifest": "MODULE_MANIFEST_MISSING",
        "missing_id": "MODULE_ID_MISSING",
        "dangling_edge": "MODULE_GRAPH_DANGLING_EDGE",
        "missing_referenced_file": "MODULE_FILE_MISSING",
        "version_incompatible": "MODULE_VERSION_INCOMPATIBLE",
    }
    assert len({c["code"] for c in body["codes"]}) == body["count"]


def test_list_read_write_soft_delete_module(client, repo_roots, good_module):
    put = client.put("/api/modules/t_mod", json={"source_path": str(good_module["root"])})
    assert put.status_code == 200, put.text
    assert put.json()["entry"]["id"] == "t_mod"

    lst = client.get("/api/modules").json()
    assert lst["count"] == 1
    e = lst["entries"][0]
    for key in ("id", "name", "ruleset", "version", "sha256", "size", "path"):
        assert key in e, key

    got = client.get("/api/modules/t_mod").json()
    assert got["ok"] and got["valid"] is True
    assert got["counts"]["event_nodes"] == 3
    assert "module.yaml" in got["files"]

    # 重复写不覆盖 -> 409
    dup = client.put("/api/modules/t_mod", json={"source_path": str(good_module["root"])})
    assert dup.status_code == 409
    assert dup.json()["error_code"] == "REPO_ENTRY_EXISTS"

    dele = client.delete("/api/modules/t_mod?reason=integration")
    assert dele.status_code == 200
    body = dele.json()
    assert body["deleted"] is True and body["physical_delete"] is False and body["on_disk"] is True
    assert (repo_roots.modules / "t_mod" / "module.yaml").is_file()

    assert client.get("/api/modules").json()["count"] == 0
    assert client.get("/api/modules?include_deleted=true").json()["count"] == 1
    gone = client.get("/api/modules/t_mod")
    assert gone.status_code == 410
    assert gone.json()["error_code"] == "REPO_ENTRY_DELETED"

    res = client.post("/api/modules/t_mod/restore")
    assert res.status_code == 200 and res.json()["restored"] is True
    assert client.get("/api/modules/t_mod").status_code == 200


def test_module_index_after_restart_is_identical(client, repo_roots, good_module):
    client.put("/api/modules/t_mod", json={"source_path": str(good_module["root"])})
    before = client.get("/api/repository/index").json()
    # 删除索引文件, 模拟「重启后从磁盘重建」
    (repo_roots.modules / "index.json").unlink()
    after = client.get("/api/repository/index").json()
    assert after["modules"]["entries"] == before["modules"]["entries"]
    assert after["modules"]["fingerprint"] == before["modules"]["fingerprint"]


# ---------------------------------------------------------- R22 判据 3 (API)

@pytest.mark.parametrize("raw", [
    "..%2f..%2fetc",
    "%2e%2e%2f%2e%2e%2fetc",
    "%252e%252e%252fetc",
    "..%5c..%5cwindows",
    "%2e%2e",
    "a%2f..%2f..%2fb",
])
def test_path_traversal_rejected_over_http(client, raw):
    r = client.get("/api/modules/%s" % raw)
    assert r.status_code == 400, r.text
    assert r.json()["error_code"] == "REPO_PATH_TRAVERSAL"


@pytest.mark.parametrize("raw", ["a b", "x" * 70, "-dash"])
def test_invalid_entry_id_over_http(client, raw):
    r = client.get("/api/modules/%s" % raw)
    assert r.status_code == 400, r.text
    assert r.json()["error_code"] == "REPO_ENTRY_INVALID_ID"


def test_path_traversal_rejected_in_write_body(client, repo_roots, good_module):
    r = client.put("/api/modules/evil", json={
        "manifest": {"id": "evil", "ruleset": "coc7", "initial_scene": "n1"},
        "files": {"../../escape.yaml": "id: evil\n"},
    })
    assert r.status_code == 400, r.text
    assert r.json()["error_code"] == "REPO_PATH_TRAVERSAL"
    # 失败不留半成品: 暂存区必须被清空
    assert list(repo_roots.staging.glob("put_*")) == []
    assert not (repo_roots.modules / "evil").exists()
    assert not (repo_roots.staging.parent / "escape.yaml").exists()


# ---------------------------------------------------------- R1: import API

def test_import_local_dir_returns_session_handle(client, repo_roots):
    pkg = build_module(repo_roots.staging / "good",
                       declared_counts={"scenes": 2, "event_nodes": 3, "npcs": 1})
    r = client.post("/api/modules/import", json={
        "source": "local", "path": str(pkg["root"]),
        "expected": {"scenes": 2, "event_nodes": 3, "npcs": 1},
        "open_session": True, "overwrite": False})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["imported"] is True
    assert body["module_id"] == "t_mod"
    assert body["counts"] == {"areas": 1, "rooms": 2, "scenes": 2, "event_nodes": 3,
                              "event_edges": 2, "npcs": 1, "clues": 1}
    assert body["declared_verified"] is True
    assert body["prepared"]["ready"] is True
    assert body["prepared"]["checks"]["dangling_edges"] == 0
    h = body["session"]
    assert h and h["table_id"] and h["campaign_id"] and h["initial_scene"] == "n1"
    # 开局句柄可被既有 TABLES 注册表解析
    t = client.get("/api/tables/%s" % h["table_id"])
    assert t.status_code == 200
    assert t.json()["campaign_id"] == h["campaign_id"]
    assert t.json()["config"]["module_id"] == "t_mod"
    # prep 工件已落盘
    assert (repo_roots.prep / "t_mod.json").is_file()


def test_import_expected_mismatch_is_explicit(client, repo_roots):
    pkg = build_module(repo_roots.staging / "good")
    r = client.post("/api/modules/import", json={
        "source": "local", "path": str(pkg["root"]),
        "expected": {"scenes": 99, "event_nodes": 3, "npcs": 1}})
    assert r.status_code == 422
    assert r.json()["error_code"] == "MODULE_COUNT_MISMATCH"
    assert not (repo_roots.modules / "t_mod").exists()


def test_import_library_source(client, repo_roots, good_module):
    client.put("/api/modules/t_mod", json={"source_path": str(good_module["root"])})
    r = client.post("/api/modules/import", json={
        "source": "library", "module_id": "t_mod", "overwrite": True})
    assert r.status_code == 201, r.text
    assert r.json()["transport"] == "library"
    assert r.json()["module_id"] == "t_mod"


def test_import_five_bad_packages_return_five_codes(client, repo_roots):
    seen = {}
    for name, root in bad_packages(repo_roots.staging / "bad").items():
        r = client.post("/api/modules/import", json={"source": "local", "path": str(root)})
        assert r.status_code == 422, "%s -> %s" % (name, r.text)
        assert r.status_code != 500
        seen[name] = r.json()["error_code"]
    assert seen == {
        "missing_manifest": "MODULE_MANIFEST_MISSING",
        "missing_id": "MODULE_ID_MISSING",
        "dangling_edge": "MODULE_GRAPH_DANGLING_EDGE",
        "missing_referenced_file": "MODULE_FILE_MISSING",
        "version_incompatible": "MODULE_VERSION_INCOMPATIBLE",
    }
    assert len(set(seen.values())) == 5
    assert client.get("/api/modules").json()["count"] == 0


# ---------------------------------------------------------- R2: download import

def test_import_from_url_with_sha256(client, repo_roots, http_file_server, good_module):
    serve_dir, base = http_file_server
    out = serve_dir / "t_mod.modpkg"
    info = pack_module(good_module["root"], out, source_note="integration")
    r = client.post("/api/modules/import", json={
        "source": "url", "url": "%s/t_mod.modpkg" % base, "sha256": info["sha256"],
        "open_session": True})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["transport"] == "url"
    assert body["sha256"] == info["sha256"]
    assert body["prepared"]["ready"] is True
    assert (repo_roots.modules / "t_mod" / "module.yaml").is_file()


def test_import_from_url_sha256_mismatch_leaves_no_partial(client, repo_roots,
                                                            http_file_server, good_module):
    serve_dir, base = http_file_server
    out = serve_dir / "t_mod.modpkg"
    pack_module(good_module["root"], out, source_note="integration")
    r = client.post("/api/modules/import", json={
        "source": "url", "url": "%s/t_mod.modpkg" % base, "sha256": "0" * 64})
    assert r.status_code == 422
    assert r.json()["error_code"] == "MODULE_PACKAGE_SHA256_MISMATCH"
    # 原子性: 不留半成品
    assert not (repo_roots.modules / "t_mod").exists()
    assert list(repo_roots.staging.glob("imp_*")) == []
    assert client.get("/api/modules").json()["count"] == 0


def test_import_from_url_without_sha256_rejected(client, http_file_server, good_module):
    serve_dir, base = http_file_server
    out = serve_dir / "t_mod.modpkg"
    pack_module(good_module["root"], out)
    r = client.post("/api/modules/import", json={"source": "url", "url": "%s/t_mod.modpkg" % base})
    assert r.status_code == 422
    assert r.json()["error_code"] == "MODULE_PACKAGE_SHA256_REQUIRED"


def test_import_rejects_non_http_scheme(client, tmp_path):
    r = client.post("/api/modules/import", json={
        "source": "url", "url": "file:///C:/windows/win.ini", "sha256": "0" * 64})
    assert r.status_code == 400
    assert r.json()["error_code"] == "MODULE_DOWNLOAD_SCHEME_REJECTED"


def test_import_from_url_404_is_502_not_500(client, http_file_server):
    _serve_dir, base = http_file_server
    r = client.post("/api/modules/import", json={
        "source": "url", "url": "%s/nope.modpkg" % base, "sha256": "0" * 64})
    assert r.status_code == 502
    assert r.json()["error_code"] == "MODULE_DOWNLOAD_FAILED"


# ---------------------------------------------------------- R3: prep endpoint

def test_prepared_endpoint_after_import(client, repo_roots, good_module):
    client.post("/api/modules/import", json={"source": "local", "path": str(good_module["root"])})
    r = client.get("/api/modules/t_mod/prepared")
    assert r.status_code == 200, r.text
    p = r.json()["prepared"]
    assert p["ready"] is True
    assert p["checks"]["dangling_edges"] == 0
    assert p["checks"]["all_rooms_have_anchors"] is True
    assert p["maps"][0]["rooms"][0]["anchors"], "家具锚点必须存在"
    assert p["event_graph"]["initial_scene"] == "n1"
    assert len(p["npcs"]) == 1 and len(p["clues"]) == 1


# ---------------------------------------------------------- rulepacks CRUD

def test_rulepacks_crud(client, repo_roots):
    lst = client.get("/api/rulepacks").json()
    assert lst["count"] == 1 and lst["entries"][0]["id"] == "coc7"

    put = client.put("/api/rulepacks/dnd5e", json={
        "rulepack_yaml": "id: dnd5e\nversion: \"1.0.0\"\ndisplay_name: \"D&D 5e\"\n"})
    assert put.status_code == 200, put.text
    assert client.get("/api/rulepacks").json()["count"] == 2

    got = client.get("/api/rulepacks/dnd5e").json()
    assert got["valid"] is True and got["manifest"]["id"] == "dnd5e"

    dele = client.delete("/api/rulepacks/dnd5e")
    assert dele.status_code == 200 and dele.json()["physical_delete"] is False
    assert (repo_roots.rulepacks / "dnd5e" / "rulepack.yaml").is_file()
    assert client.get("/api/rulepacks").json()["count"] == 1
    assert client.get("/api/rulepacks/dnd5e").status_code == 410
    assert client.post("/api/rulepacks/dnd5e/restore").status_code == 200
    assert client.get("/api/rulepacks").json()["count"] == 2


def test_rulepack_missing_manifest_code(client):
    r = client.put("/api/rulepacks/broken", json={"files": {"readme.txt": "hi"}})
    assert r.status_code == 422
    assert r.json()["error_code"] == "RULEPACK_MANIFEST_MISSING"


def test_rebuild_endpoint_reports_fingerprints(client, repo_roots, good_module):
    client.put("/api/modules/t_mod", json={"source_path": str(good_module["root"])})
    r = client.post("/api/repository/rebuild")
    assert r.status_code == 200
    body = r.json()
    assert body["modules"]["count"] == 1
    assert body["rulepacks"]["count"] == 1
    assert len(body["modules"]["fingerprint"]) == 64
    assert (repo_roots.modules / "index.json").is_file()
    assert (repo_roots.rulepacks / "index.json").is_file()
