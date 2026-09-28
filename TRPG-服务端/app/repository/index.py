"""仓库索引: modules/index.json + rulepacks/index.json (R22 判据 1/2) —— additive。

设计要点
--------
* 索引条目字段: id / name / ruleset / version / sha256 / size / path (+ files/kind)。
* **sha256/size/files 指什么（R35-2 澄清，勿再误读）**: 三者描述的是条目的
  **解包后目录内容**，由 sha256_dir() 一并算出 —— sha256 = 对
  "每行 <相对路径> + NUL + 该文件 sha256 + 换行" 拼接串取 sha256；
  size = 目录内文件大小之和；files = 目录内文件个数。
  **它不是可下载产物 (.modpkg) 的 sha256**：产物是打包后的 zip 容器，两者
  必然不同。产物自身的 sha256 由 GET /api/modules/{id}/package 与
  GET /api/modules/{id}/download 的 X-Artifact-Sha256 响应对给出
  （见 app/web/rest_hotreload.py 的 _module_artifact）。
  该语义被 scripts/r2_verify_invariants.py 的 I2 判据锁定
  （entry.sha256 == sha256_dir(<dir>)），**不得**改成产物摘要。
  导入侧同源命名见 app/repository/importer.py: content_sha256 = 本字段,
  package_sha256 = 产物字节摘要。
* **确定性重建**: build_index() 只依赖磁盘内容 + 墓碑文件, entries 逐字节可复现;
  generated_at 只写顶层, 不进入 entries; fingerprint = sha256(canonical(entries))。
  因此「重启后从磁盘重建, 结果一致」可直接用 fingerprint 相等来判定。
* 软删 (R22 判据 2) 通过同目录隐藏墓碑文件 .tombstones.json 持久化, 重建不丢。
* 写入一律「临时文件 + os.replace」原子替换, 不会留下半个 index.json。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.repository.errors import RepoError
from app.repository.spec import (INDEX_FILENAME, SKIP_PREFIXES,
                                 TOMBSTONE_FILENAME, normalize_schema_version)
from app.repository.paths import is_symlinkish, safe_join

INDEX_SCHEMA = "RepoIndex v1"
VALID_KINDS = ("modules", "rulepacks")

_MANIFEST_NAMES = {"modules": ("module.yaml", "module.yml", "manifest.json"),
                   "rulepacks": ("rulepack.yaml", "rulepack.yml", "manifest.json")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_files(root: Path) -> list[Path]:
    """目录下全部文件 (相对路径 POSIX, 字典序) —— 排序保证确定性。"""
    root = Path(root)
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file():
            out.append(p)
    out.sort(key=lambda p: p.relative_to(root).as_posix())
    return out


def sha256_dir(root: Path) -> tuple[str, int, int]:
    """目录摘要 = sha256(每行 '<rel>\\0<file_sha256>\\n') ; 返回 (digest, bytes, files)。"""
    root = Path(root)
    h = hashlib.sha256()
    total = 0
    files = dir_files(root)
    for p in files:
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(sha256_file(p).encode("ascii"))
        h.update(b"\n")
        total += p.stat().st_size
    return h.hexdigest(), total, len(files)


def _read_manifest(root: Path, kind: str) -> dict[str, Any]:
    for name in _MANIFEST_NAMES[kind]:
        p = root / name
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def _entry_fields(manifest: dict[str, Any], kind: str, fallback_id: str) -> dict[str, Any]:
    if kind == "modules":
        return {"id": str(manifest.get("id") or fallback_id),
                "name": str(manifest.get("name") or fallback_id),
                "ruleset": str(manifest.get("ruleset") or ""),
                "version": str(manifest.get("version") or "")}
    return {"id": str(manifest.get("id") or fallback_id),
            "name": str(manifest.get("display_name") or manifest.get("name") or fallback_id),
            "ruleset": str(manifest.get("id") or fallback_id),
            "version": str(manifest.get("version") or "")}


def tombstone_path(root: Path) -> Path:
    return Path(root) / TOMBSTONE_FILENAME


def read_tombstones(root: Path) -> dict[str, Any]:
    p = tombstone_path(root)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    entries = data.get("entries") if isinstance(data, dict) else None
    return entries if isinstance(entries, dict) else {}


def _write_tombstones(root: Path, entries: dict[str, Any]) -> None:
    _atomic_write_json(tombstone_path(root),
                       {"schema": "RepoTombstones v1", "entries": dict(sorted(entries.items()))})


def mark_deleted(root: Path, entry_id: str, *, reason: str = "") -> dict[str, Any]:
    """软删: 只在墓碑里打标记, **不物理删除** 目录/文件。"""
    entries = read_tombstones(root)
    entries[entry_id] = {"deleted": True, "deleted_at": _now(), "reason": reason}
    _write_tombstones(root, entries)
    return entries[entry_id]


def unmark_deleted(root: Path, entry_id: str) -> bool:
    entries = read_tombstones(root)
    if entry_id not in entries:
        return False
    del entries[entry_id]
    _write_tombstones(root, entries)
    return True


def _atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-%d" % os.getpid())
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _atomic_write_json(path: Path, data: Any) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def index_path(root: Path, kind: str) -> Path:
    if kind not in VALID_KINDS:
        raise RepoError("REPO_BAD_KIND", "kind=%r" % (kind,), {"kind": kind})
    return Path(root) / INDEX_FILENAME


def scan_entries(root: Path, kind: str) -> list[dict[str, Any]]:
    """扫描仓库根下的一级条目 -> 确定性排序的 entry 列表 (不含 generated_at)。"""
    root = Path(root)
    if not root.is_dir():
        return []
    tombstones = read_tombstones(root)
    entries: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if child.name.startswith(SKIP_PREFIXES):
            continue
        if is_symlinkish(child):   # 符号链接/junction 目录永不成为仓库条目
            continue
        manifest = _read_manifest(child, kind)
        fields = _entry_fields(manifest, kind, child.name)
        digest, size, nfiles = sha256_dir(child)
        tomb = tombstones.get(child.name) or tombstones.get(fields["id"]) or {}
        entries.append({
            "id": fields["id"],
            "name": fields["name"],
            "ruleset": fields["ruleset"],
            "version": fields["version"],
            "sha256": digest,
            "size": size,
            "files": nfiles,
            "path": "%s/%s" % (kind, child.name),
            "dir": child.name,
            "schema_version": normalize_schema_version(manifest.get("schema_version")),
            "deleted": bool(tomb.get("deleted")),
            "deleted_at": tomb.get("deleted_at"),
        })
    entries.sort(key=lambda e: e["id"])
    return entries


def fingerprint(entries: list[dict[str, Any]]) -> str:
    canon = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(canon.encode("utf-8"))


def build_index(root: Path, kind: str) -> dict[str, Any]:
    """从磁盘重建索引 (纯函数, 除 generated_at 外完全确定)。"""
    if kind not in VALID_KINDS:
        raise RepoError("REPO_BAD_KIND", "kind=%r" % (kind,), {"kind": kind})
    entries = scan_entries(root, kind)
    return {
        "schema": INDEX_SCHEMA,
        "kind": kind,
        "root": Path(root).as_posix(),
        "count": len(entries),
        "deleted_count": sum(1 for e in entries if e["deleted"]),
        "fingerprint": fingerprint(entries),
        "generated_at": _now(),
        "entries": entries,
    }


def write_index(root: Path, kind: str) -> dict[str, Any]:
    """重建并原子落盘 <root>/index.json, 返回索引对象。"""
    idx = build_index(root, kind)
    _atomic_write_json(index_path(root, kind), idx)
    return idx


def load_index(root: Path, kind: str, *, rebuild: bool = False) -> dict[str, Any]:
    """读索引; 缺失或 rebuild=True 时从磁盘重建 (重启后自愈)。"""
    p = index_path(root, kind)
    if rebuild or not p.is_file():
        return write_index(root, kind)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return write_index(root, kind)
    if not isinstance(data, dict) or data.get("schema") != INDEX_SCHEMA or "entries" not in data:
        return write_index(root, kind)
    data.setdefault("fingerprint", fingerprint(data["entries"]))
    return data


def find_entry(root: Path, kind: str, entry_id: str, *,
               include_deleted: bool = True, rebuild: bool = False) -> dict[str, Any] | None:
    idx = load_index(root, kind, rebuild=rebuild)
    for e in idx.get("entries", []):
        if e.get("id") == entry_id or e.get("dir") == entry_id:
            if e.get("deleted") and not include_deleted:
                return None
            return e
    return None


def rebuild_all(roots: Any) -> dict[str, Any]:
    """两套索引一起重建 -> {kind: index}。"""
    out: dict[str, Any] = {}
    for kind, root in (("modules", roots.modules), ("rulepacks", roots.rulepacks)):
        Path(root).mkdir(parents=True, exist_ok=True)
        out[kind] = write_index(root, kind)
    return out


def entry_dir(root: Path, kind: str, entry_id: str) -> Path:
    """按 id 安全定位条目目录 (走路径穿越防护)。"""
    return safe_join(root, entry_id, label="%s entry" % kind)
