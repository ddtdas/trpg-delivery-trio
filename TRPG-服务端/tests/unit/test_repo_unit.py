"""仓库层单元测试 (R22 判据 1/2/3 + R13 错误码表)。"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest
import yaml

from _pkgbuild import bad_packages, build_module
from app.repository import index as repo_index
from app.repository import paths as repo_paths
from app.repository import pkg as repo_pkg
from app.repository import prep as repo_prep
from app.repository import rulepacks as repo_rulepacks
from app.repository.errors import R13_BAD_PACKAGE_CODES, RepoError, error_code_table
from app.repository.importer import validate_package


# --------------------------------------------------------------- R22 判据 3

TRAVERSAL_INPUTS = [
    "../etc/passwd",
    "..\\windows\\system32",
    "a/../../b",
    "a/b/../../../c",
    "%2e%2e%2fetc",
    "%2E%2E%2Fetc",
    "%252e%252e%252fetc",
    "%25252e%25252e%25252fetc",
    "..%2f..%2fetc",
    "/etc/passwd",
    "//server/share/x",
    "\\\\server\\share\\x",
    "C:\\Windows\\System32",
    "c:/windows",
    "~/secret",
    "",
    ".",
    "a/./../../b",
    "nul\x00byte",
    "sub\x00/x",
    "a/b.",
    "a/b ",
]


@pytest.mark.parametrize("raw", TRAVERSAL_INPUTS)
def test_safe_join_rejects_traversal(raw, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(RepoError) as ei:
        repo_paths.safe_join(root, raw)
    assert ei.value.code == "REPO_PATH_TRAVERSAL"
    assert ei.value.http_status == 400


def test_safe_join_accepts_plain_relative(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    got = repo_paths.safe_join(root, "sub/file.yaml")
    assert got == (root / "sub" / "file.yaml").resolve()


def test_safe_join_rejects_symlink_component(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("top-secret", encoding="utf-8")
    link = root / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:  # Windows 需要开发者模式
        pytest.skip("symlink not permitted here: %s" % exc)
    with pytest.raises(RepoError) as ei:
        repo_paths.safe_join(root, "link/secret.txt")
    assert ei.value.code == "REPO_PATH_TRAVERSAL"
    assert "符号链接" in ei.value.message or "junction" in ei.value.message


def test_entry_id_whitelist():
    for bad in ["../x", "a/b", "a\\b", "%2e%2e", "", "a b", "x" * 65, ".hidden"]:
        with pytest.raises(RepoError) as ei:
            repo_paths.validate_entry_id(bad)
        assert ei.value.code == "REPO_ENTRY_INVALID_ID"
    assert repo_paths.validate_entry_id("sample_coc") == "sample_coc"
    assert repo_paths.validate_entry_id("coc7") == "coc7"


# --------------------------------------------------------------- R22 判据 1

def test_index_rebuild_is_deterministic(repo_roots):
    build_module(repo_roots.modules / "mod_a", mid="mod_a", nodes=3)
    build_module(repo_roots.modules / "mod_b", mid="mod_b", nodes=4)
    first = repo_index.write_index(repo_roots.modules, "modules")
    second = repo_index.build_index(repo_roots.modules, "modules")
    third = repo_index.build_index(repo_roots.modules, "modules")
    assert first["entries"] == second["entries"] == third["entries"]
    assert first["fingerprint"] == second["fingerprint"] == third["fingerprint"]
    assert first["count"] == 2
    e = second["entries"][0]
    for key in ("id", "name", "ruleset", "version", "sha256", "size", "path"):
        assert key in e, key
    assert e["path"].startswith("modules/")
    assert len(e["sha256"]) == 64


def test_index_survives_restart_and_matches_disk(repo_roots):
    build_module(repo_roots.modules / "mod_a", mid="mod_a")
    repo_index.write_index(repo_roots.modules, "modules")
    on_disk = json.loads((repo_roots.modules / "index.json").read_text(encoding="utf-8"))
    # 模拟重启: 丢弃内存态, 直接重新从磁盘重建
    rebuilt = repo_index.write_index(repo_roots.modules, "modules")
    assert rebuilt["entries"] == on_disk["entries"]
    assert rebuilt["fingerprint"] == on_disk["fingerprint"]


def test_rulepack_index_has_required_fields(repo_roots):
    rp = repo_roots.rulepacks / "dnd5e"
    rp.mkdir(parents=True, exist_ok=True)
    (rp / "rulepack.yaml").write_text(
        "id: dnd5e\nversion: \"1.0.0\"\ndisplay_name: \"D&D 5e\"\n", encoding="utf-8")
    idx = repo_index.write_index(repo_roots.rulepacks, "rulepacks")
    ids = sorted(e["id"] for e in idx["entries"])
    assert ids == ["coc7", "dnd5e"]
    assert all(len(e["sha256"]) == 64 and e["size"] > 0 for e in idx["entries"])


# ------------------------------------------- R22/R23 规则包 manifest 格式版本

@pytest.mark.parametrize("sv", ["2", "2.0", "2.0.0", "1", "1.0", "1.0.0", None])
def test_rulepack_schema_version_generation_2_is_accepted(repo_roots, sv):
    """R23 的规则包内容代次是 2: 若声明 schema_version="2" 不得被判不兼容。"""
    d = repo_roots.rulepacks / "gen2"
    d.mkdir(parents=True, exist_ok=True)
    body = {"id": "gen2", "display_name": "gen2", "version": "2.0.0"}
    if sv is not None:
        body["schema_version"] = sv
    (d / "rulepack.yaml").write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    out = repo_rulepacks.validate_rulepack(d)
    assert out["ok"] is True and out["rulepack_id"] == "gen2"
    entry = [e for e in repo_index.scan_entries(repo_roots.rulepacks, "rulepacks")
             if e["id"] == "gen2"][0]
    assert entry["schema_version"] == (sv or "1")


def test_rulepack_future_schema_version_still_rejected(repo_roots):
    """尚未放行的未来代次仍须明确拒绝 (明确错误码, 不是 500)。"""
    d = repo_roots.rulepacks / "gen99"
    d.mkdir(parents=True, exist_ok=True)
    (d / "rulepack.yaml").write_text(
        yaml.safe_dump({"id": "gen99", "schema_version": "99"}, allow_unicode=True), encoding="utf-8")
    with pytest.raises(RepoError) as ei:
        repo_rulepacks.validate_rulepack(d)
    assert ei.value.code == "RULEPACK_VERSION_INCOMPATIBLE"


def test_rulepack_content_schema_is_not_conflated_with_schema_version(repo_roots):
    """manifest.schema (R23 内容模型代次, 如 schema: 2) 不得被当成 manifest 格式版本读取。"""
    d = repo_roots.rulepacks / "contentgen"
    d.mkdir(parents=True, exist_ok=True)
    (d / "rulepack.yaml").write_text(
        yaml.safe_dump({"id": "contentgen", "schema": 2, "version": "2.0.0"}, allow_unicode=True),
        encoding="utf-8")
    out = repo_rulepacks.validate_rulepack(d)
    assert out["ok"] is True
    entry = [e for e in repo_index.scan_entries(repo_roots.rulepacks, "rulepacks")
             if e["id"] == "contentgen"][0]
    assert entry["schema_version"] == "1", "schema:2 是内容代次, 不是 manifest 格式版本"


# --------------------------------------------------------------- R22 判据 2

def test_soft_delete_marks_without_removing(repo_roots):
    build_module(repo_roots.modules / "mod_a", mid="mod_a")
    repo_index.write_index(repo_roots.modules, "modules")
    tomb = repo_index.mark_deleted(repo_roots.modules, "mod_a", reason="unit-test")
    assert tomb["deleted"] is True
    assert (repo_roots.modules / "mod_a" / "module.yaml").is_file()  # 未物理删除
    idx = repo_index.write_index(repo_roots.modules, "modules")
    entry = [e for e in idx["entries"] if e["id"] == "mod_a"][0]
    assert entry["deleted"] is True
    assert entry["deleted_at"] == tomb["deleted_at"]
    # 再次重建 (模拟重启) 仍保持软删
    assert repo_index.build_index(repo_roots.modules, "modules")["entries"] == idx["entries"]
    # restore
    assert repo_index.unmark_deleted(repo_roots.modules, "mod_a") is True
    idx2 = repo_index.write_index(repo_roots.modules, "modules")
    assert [e for e in idx2["entries"] if e["id"] == "mod_a"][0]["deleted"] is False


# --------------------------------------------------------------- R13

def test_r13_five_bad_packages_get_five_distinct_codes(repo_roots):
    codes = {}
    for name, root in bad_packages(repo_roots.staging / "bad").items():
        with pytest.raises(RepoError) as ei:
            validate_package(root, rulepacks_root=repo_roots.rulepacks)
        codes[name] = ei.value.code
        assert ei.value.http_status == 422
    assert codes == R13_BAD_PACKAGE_CODES
    assert len(set(codes.values())) == 5


def test_r13_missing_ruleset_is_distinct(repo_roots):
    root = build_module(repo_roots.staging / "unknown_rs", ruleset="gurps")["root"]
    with pytest.raises(RepoError) as ei:
        validate_package(root, rulepacks_root=repo_roots.rulepacks)
    assert ei.value.code == "MODULE_RULESET_UNKNOWN"


def test_r13_initial_scene_invalid(repo_roots):
    root = build_module(repo_roots.staging / "bad_start", initial_scene="n_absent")["root"]
    with pytest.raises(RepoError) as ei:
        validate_package(root, rulepacks_root=repo_roots.rulepacks)
    assert ei.value.code == "MODULE_INITIAL_SCENE_INVALID"


def test_error_code_table_is_complete():
    table = error_code_table()
    codes = {c["code"] for c in table["codes"]}
    for code in R13_BAD_PACKAGE_CODES.values():
        assert code in codes
    assert table["count"] == len(codes)


def test_good_package_validates(repo_roots):
    pkg = build_module(repo_roots.staging / "good", declared_counts={"scenes": 2, "event_nodes": 3, "npcs": 1})
    checked = validate_package(pkg["root"], rulepacks_root=repo_roots.rulepacks)
    assert checked["module_id"] == "t_mod"
    assert checked["counts"] == {"areas": 1, "rooms": 2, "scenes": 2,
                                 "event_nodes": 3, "event_edges": 2, "npcs": 1, "clues": 1}
    assert checked["declared"] == {"scenes": 2, "event_nodes": 3, "npcs": 1}


# --------------------------------------------------------------- modpkg

def test_modpkg_pack_extract_roundtrip(repo_roots):
    pkg = build_module(repo_roots.staging / "good")
    out = repo_roots.staging / "good.modpkg"
    info = repo_pkg.pack_module(pkg["root"], out, source_note="unit-test")
    assert info["container"]["magic"] == "trpg.modpkg/v1"
    dest = repo_roots.staging / "unpacked"
    repo_pkg.extract_modpkg(out, dest)
    assert (dest / "module.yaml").is_file()
    assert repo_pkg.sha256_file(out) == info["sha256"]
    checked = validate_package(dest, rulepacks_root=repo_roots.rulepacks)
    assert checked["module_id"] == "t_mod"


def test_modpkg_roundtrip_preserves_dir_digest(repo_roots):
    pkg = build_module(repo_roots.staging / "good")
    out = repo_roots.staging / "roundtrip.modpkg"
    repo_pkg.pack_module(pkg["root"], out)
    dest = repo_roots.staging / "roundtrip_out"
    repo_pkg.extract_modpkg(out, dest)
    assert not (dest / "manifest.json").exists(), "容器 manifest 不应残留为模组内容"
    assert repo_index.sha256_dir(pkg["root"]) == repo_index.sha256_dir(dest)


def test_extract_rejects_traversal_zip(repo_roots):
    evil = repo_roots.staging / "evil.modpkg"
    evil.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../pwned.yaml", "id: pwned\n")
    with pytest.raises(RepoError) as ei:
        repo_pkg.extract_zip_safely(evil, repo_roots.staging / "evil_out")
    assert ei.value.code == "MODULE_PACKAGE_CORRUPT"


def test_extract_rejects_absolute_zip_entry(repo_roots):
    evil = repo_roots.staging / "evil2.modpkg"
    evil.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("/abs/pwned.yaml", "x: 1\n")
    with pytest.raises(RepoError) as ei:
        repo_pkg.extract_zip_safely(evil, repo_roots.staging / "evil2_out")
    assert ei.value.code == "MODULE_PACKAGE_CORRUPT"


# --------------------------------------------------------------- R3 prep

def test_prep_generates_anchors_and_zero_dangling(repo_roots):
    pkg = build_module(repo_roots.staging / "good", nodes=4, rooms=3, npcs=2, clues=2)
    checked = validate_package(pkg["root"], rulepacks_root=repo_roots.rulepacks)
    prepared = repo_prep.prepare(pkg["root"], manifest=checked["manifest"], graph=checked["graph"],
                                 clues=checked["clues"], npcs=checked["npcs"], maps=checked["maps"],
                                 module_sha256="deadbeef")
    assert prepared["ready"] is True
    assert prepared["event_graph"]["dangling_edges"] == []
    assert prepared["checks"]["dangling_edges"] == 0
    assert prepared["checks"]["all_rooms_have_anchors"] is True
    assert prepared["counts"]["anchors"] >= 3 * 2
    assert prepared["counts"]["rooms"] == 3
    assert len(prepared["npcs"]) == 2 and len(prepared["clues"]) == 2
    # 确定性: 同输入两次结果一致
    again = repo_prep.prepare(pkg["root"], manifest=checked["manifest"], graph=checked["graph"],
                              clues=checked["clues"], npcs=checked["npcs"], maps=checked["maps"],
                              module_sha256="deadbeef")
    assert again["maps"] == prepared["maps"]
    assert again["event_graph"] == prepared["event_graph"]


def test_prep_anchor_count_scales_with_room_area():
    small = repo_prep.anchors_for_room({"id": "s", "x": 0, "y": 0, "w": 100, "h": 100})
    big = repo_prep.anchors_for_room({"id": "b", "x": 0, "y": 0, "w": 600, "h": 400})
    assert len(small) == 2
    assert len(big) > len(small)
    assert all(a["room"] in ("s", "b") for a in small + big)


def test_prep_declared_furniture_wins():
    room = {"id": "r", "x": 0, "y": 0, "w": 200, "h": 200,
            "furniture": [{"id": "f1", "name": "书柜", "x": 10, "y": 10}]}
    anchors = repo_prep.anchors_for_room(room)
    assert len(anchors) == 1 and anchors[0]["source"] == "declared" and anchors[0]["name"] == "书柜"
