"""R24/R25/R26/R27 集成测试: 真 HTTP (TestClient) 走完 死光.modpkg -> 导入 -> 热重载 -> 回滚。"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.hotreload import compiled as hc

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"  # R2: tests/integration/ -> server root


@pytest.fixture(autouse=True)
def _isolated_bindings(tmp_path, monkeypatch):
    """F-9: 绑定表持久化落到 tmp —— 集成测试不得写入真实 data/。"""
    monkeypatch.setenv("TRPG_HOTRELOAD_BINDINGS", str(tmp_path / "hr_bindings.json"))


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "_t5_build_deadlight", SCRIPTS / "_t5_build_deadlight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def api(repo_roots, tmp_path, monkeypatch):
    """隔离的 app 实例: 事件库/快照/仓库根全部指向 tmp。"""
    from app.web import rest as rest_mod
    from app.web import rest_repo

    monkeypatch.setattr(rest_mod, "DEFAULT_DB", tmp_path / "trpg.db", raising=False)
    monkeypatch.setattr(rest_mod, "SNAP_BASE", tmp_path / "snapshots", raising=False)
    rest_mod.TABLES.clear()
    rest_repo.set_roots(repo_roots)

    from app.main import app
    from app.hotreload import watcher as hrw

    hrw._WATCHER = None                      # 每个用例一个干净的监听器
    with TestClient(app) as c:
        yield c, repo_roots
    hrw._WATCHER = None


@pytest.fixture()
def deadlight(repo_roots):
    b = _load_builder()
    meta = b.build_module(repo_roots.base if hasattr(repo_roots, "base") else repo_roots.modules.parent)
    from app.repository.pkg import pack_module
    out = repo_roots.modules.parent / "死光.modpkg"
    pack_module(repo_roots.modules / "dead_light", out)
    import hashlib
    return {"meta": meta, "pkg": out,
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "module_dir": repo_roots.modules / "dead_light"}


# --------------------------------------------------------------- R25/R26 容器

def test_modpkg_is_readable_and_contains_both_content_classes(api, deadlight):
    """R26: 单文件容器可被服务端读取, 且 source/ 与 compiled/ 两类内容齐备。"""
    import zipfile

    names = zipfile.ZipFile(deadlight["pkg"]).namelist()
    assert any(n.startswith("source/") for n in names), names
    assert any(n.startswith("compiled/") for n in names), names
    assert "module.yaml" in names
    src = set(n for n in names if n.startswith("source/"))
    assert {"source/PROVENANCE.json", "source/SUMMARY.md",
            "source/LICENSE-NOTICE.md"} <= src
    comp = set(n for n in names if n.startswith("compiled/"))
    assert {"compiled/dead_light.compiled.json", "compiled/save_state.json",
            "compiled/compiled.manifest.json"} <= comp


def test_source_contains_no_copyrighted_body_text(deadlight):
    """D-05: source/ 只能是元数据 + 摘要 + 出处, 不得复制模组正文。"""
    prov = json.loads((deadlight["module_dir"] / "source" / "PROVENANCE.json")
                      .read_text(encoding="utf-8"))
    assert prov["source_type"] == "public_metadata_only"
    assert prov["original_title"] == "Dead Light"
    assert prov["publisher"] == "Chaosium Inc."
    assert prov["sources"] and all(s["url"].startswith("http") for s in prov["sources"])
    assert prov["not_included"]
    assert "版权" in prov["copyright_notice"]


# --------------------------------------------------------------- R24 库 / 下载

def test_library_lists_name_ruleset_version_checksum_size(api, deadlight):
    c, roots = api
    r = c.get("/api/modules")
    assert r.status_code == 200, r.text
    e = [x for x in r.json()["entries"] if x["id"] == "dead_light"]
    assert e, r.text
    e = e[0]
    for k in ("id", "name", "ruleset", "version", "sha256", "size", "path"):
        assert k in e and e[k] not in (None, ""), k
    assert e["ruleset"] == "coc7" and e["version"] == "1.0.0"


def test_download_then_import_roundtrip(api, deadlight):
    """R24: 一键下载即可直接导入 —— 下载的 .modpkg 重新导入后内容逐字节一致。"""
    c, roots = api
    first = c.post("/api/modules/import",
                   json={"source": "local", "path": str(deadlight["pkg"]),
                         "sha256": deadlight["sha256"], "overwrite": True,
                         "open_session": True})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["counts"]["rooms"] == 10
    assert body["counts"]["event_nodes"] == 14
    assert body["declared_verified"] is True

    dl = c.get("/api/modules/dead_light/download")
    assert dl.status_code == 200, dl.text
    got = roots.modules.parent / "downloaded.modpkg"
    got.write_bytes(dl.content)
    assert got.stat().st_size > 0

    import hashlib
    sha = hashlib.sha256(got.read_bytes()).hexdigest()
    second = c.post("/api/modules/import",
                    json={"source": "local", "path": str(got), "sha256": sha,
                          "module_id": "dead_light_copy", "overwrite": True})
    assert second.status_code == 201, second.text
    assert second.json()["content_sha256"] == body["content_sha256"], "下载->导入必须无损"


# --------------------------------------------------------------- R27 热重载

def _bind_and_import(c, roots, deadlight):
    r = c.post("/api/modules/import",
               json={"source": "local", "path": str(deadlight["pkg"]),
                     "sha256": deadlight["sha256"], "overwrite": True,
                     "open_session": True})
    assert r.status_code == 201, r.text
    body = r.json()
    campaign = body["session"]["campaign_id"]
    b = c.post("/api/hotreload/bind",
               json={"campaign_id": campaign, "module_id": "dead_light",
                     "table_id": body["session"].get("table_id", "")})
    assert b.status_code == 201, b.text
    return campaign, body


def test_hotreload_bind_apply_idempotent_and_diff_empty_on_reimport(api, deadlight):
    c, roots = api
    campaign, _ = _bind_and_import(c, roots, deadlight)

    a1 = c.post("/api/hotreload/apply", json={"campaign_id": campaign})
    assert a1.status_code == 200, a1.text
    assert a1.json()["change_count"] == 0, "刚导入的状态必须与绑定初值一致"
    a2 = c.post("/api/hotreload/apply", json={"campaign_id": campaign})
    assert a2.json()["change_count"] == 0, "二次导入 diff 必须为空"
    assert a2.json()["seqs"] == []


def test_hotreload_detects_save_file_change_and_appends_existing_event_types(api, deadlight):
    c, roots = api
    campaign, _ = _bind_and_import(c, roots, deadlight)
    save = roots.modules / "dead_light" / "compiled" / "save_state.json"

    state = json.loads(save.read_text(encoding="utf-8"))
    state["maps"][0]["interactables"][0]["x"] = float(
        state["maps"][0]["interactables"][0]["x"]) + 5.0
    state["clues"].append({"id": "c_hotreload_probe", "kind": "mark", "location": "n_lobby"})
    save.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
    st = save.stat()
    os.utime(save, (st.st_atime, st.st_mtime + 2))
    del st

    t = c.post("/api/hotreload/tick")
    assert t.status_code == 200, t.text
    fired = t.json()["fired"]
    assert len(fired) == 1, t.text
    assert fired[0]["change_count"] >= 2
    assert fired[0]["seqs"], "变更必须落库(进而由既有单一收口广播)"
    assert len(fired[0]["seqs"]) == fired[0]["change_count"], "一变更一事件, 不合并"

    # 追加的事件必须全部是冻结的既有类型, 且 MAP_UPDATED/CLUE_GRANTED 都在
    from app.domain.events import EVENT_TYPES

    types = {x["type"] for x in fired[0]["changes"]}
    assert types <= set(EVENT_TYPES), types - set(EVENT_TYPES)
    assert "MAP_UPDATED" in types and "CLUE_GRANTED" in types, types
    # 注: 这里断言的是**热重载产出的变更类型**, 而不是 /events 端点的回读 ——
    # 后者按 R9 可见性裁剪, 玩家视角本就看不到 MAP_UPDATED (那是 KP 帧内容)。

    # 再次 tick: 无变更 -> 不触发 (幂等)
    t2 = c.post("/api/hotreload/tick")
    assert t2.json()["fired_count"] == 0


def test_hotreload_state_and_rollback(api, deadlight):
    c, roots = api
    campaign, _ = _bind_and_import(c, roots, deadlight)
    save = roots.modules / "dead_light" / "compiled" / "save_state.json"
    before = c.post("/api/hotreload/apply", json={"campaign_id": campaign}).json()["digest"]

    state = json.loads(save.read_text(encoding="utf-8"))
    state["maps"][1]["interactables"][0]["y"] = float(
        state["maps"][1]["interactables"][0]["y"]) + 7.0
    save.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
    st = save.stat()
    os.utime(save, (st.st_atime, st.st_mtime + 2))
    c.post("/api/hotreload/tick")
    mid = c.get("/api/hotreload/state", params={"campaign_id": campaign}).json()
    assert mid["binding"]["apply_count"] >= 1
    assert mid["binding"]["applied_digest"] != before

    rb = c.post("/api/hotreload/rollback", json={"campaign_id": campaign, "steps": 1})
    assert rb.status_code == 200, rb.text
    assert rb.json()["digest"] == before, "回滚后必须回到旧状态"
    assert any(x["type"] == "SNAPSHOT_LOADED" for x in rb.json()["changes"])
    assert rb.json()["seqs"], "回滚也必须落库(进而由既有单一收口广播)"


def test_hotreload_out_of_room_position_is_rejected_with_explicit_code(api, deadlight):
    c, roots = api
    campaign, _ = _bind_and_import(c, roots, deadlight)
    state = json.loads((roots.modules / "dead_light" / "compiled" / "save_state.json")
                       .read_text(encoding="utf-8"))
    it = state["maps"][0]["interactables"][0]
    it["x"] = 99999.0                       # 远在房间之外
    r = c.post("/api/hotreload/apply", json={"campaign_id": campaign, "state": state})
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "COMPILED_INTERACTABLE_OUT_OF_ROOM"


def test_hotreload_unbound_returns_explicit_code_not_500(api, deadlight):
    c, _ = api
    r = c.post("/api/hotreload/apply", json={"campaign_id": "no_such_campaign"})
    assert r.status_code == 404, r.text
    assert r.json()["error_code"] == "HOTRELOAD_NOT_BOUND"
    s = c.get("/api/hotreload/state", params={"campaign_id": "no_such_campaign"})
    assert s.status_code == 404 and s.json()["error_code"] == "HOTRELOAD_NOT_BOUND"


def test_interactables_all_have_room_anchor_actions_inside_bounds(deadlight):
    """每个可交互物 {房间, 锚点, 动作集} 齐备且位置在房间边界内 (全量 22 个)。"""
    comp = json.loads((deadlight["module_dir"] / "compiled" / "dead_light.compiled.json")
                      .read_text(encoding="utf-8"))
    out = hc.validate_compiled(comp)
    assert out["counts"]["interactables"] == 22
    rects = {}
    for m in comp["maps"]:
        for r in m["rooms"]:
            rects[r["id"]] = r["rect"]
    for m in comp["maps"]:
        for it in m["interactables"]:
            assert it["room"] in rects
            assert it["anchor"]
            assert it["actions"]
            rc = rects[it["room"]]
            assert rc["x"] <= it["x"] <= rc["x"] + rc["w"], it["id"]
            assert rc["y"] <= it["y"] <= rc["y"] + rc["h"], it["id"]
