"""模组包 (.modpkg) 打包与安全解包 (R1/R2/R22) —— additive。

.modpkg 是一个 zip 容器:
    manifest.json          # 容器元数据 (magic / id / version / sha256 / files)
    <模组根文件...>        # module.yaml / event_graph.yaml / clues.yaml / npcs/ / maps/

安全解包拒绝: 绝对路径条目、'..' 条目、符号链接条目、超限体积、非 zip 文件。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.repository.errors import RepoError
from app.repository.spec import (MAX_PACKAGE_BYTES, MAX_UNPACK_BYTES, MODPKG_EXT,
                                 MODPKG_MAGIC, MODULE_MANIFEST_NAMES)

_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_WIN_DRIVE = __import__("re").compile(r"^[A-Za-z]:")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_zipfile(path: Path) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    try:
        with open(p, "rb") as fh:
            head = fh.read(4)
    except OSError:
        return False
    if head[:4] not in _ZIP_MAGIC:
        return False
    return zipfile.is_zipfile(p)


def _reject_entry(name: str, reason: str) -> RepoError:
    return RepoError("MODULE_PACKAGE_CORRUPT", "包内条目非法(%s): %r" % (reason, name),
                     {"entry": name, "reason": reason})


def extract_zip_safely(zip_path: Path, dest: Path, *,
                       max_bytes: int = MAX_UNPACK_BYTES) -> int:
    """安全解包 zip 到 dest; 返回条目数。任何非法条目 -> MODULE_PACKAGE_CORRUPT。"""
    zip_path = Path(zip_path)
    dest = Path(dest)
    if not is_zipfile(zip_path):
        raise RepoError("MODULE_PACKAGE_CORRUPT", "不是合法 zip/modpkg: %s" % zip_path,
                        {"path": str(zip_path)})
    dest.mkdir(parents=True, exist_ok=True)
    total = 0
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            norm = str(name).replace("\\", "/")
            if norm.startswith("/") or norm.startswith("//") or _WIN_DRIVE.match(norm):
                raise _reject_entry(name, "绝对路径")
            parts = [p for p in norm.split("/") if p not in ("", ".")]
            if any(p == ".." for p in parts):
                raise _reject_entry(name, "上跳 ..")
            if not parts:
                continue
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise _reject_entry(name, "符号链接")
            total += int(info.file_size or 0)
            if total > max_bytes:
                raise RepoError("MODULE_PACKAGE_CORRUPT",
                                "解包体积超限(%d > %d)" % (total, max_bytes),
                                {"path": str(zip_path)})
            target = dest.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            count += 1
    if count == 0:
        raise RepoError("MODULE_PACKAGE_CORRUPT", "包内没有任何文件条目", {"path": str(zip_path)})
    return count


def flatten_single_root(dest: Path) -> Path:
    """若解包后只有一层同名根目录且其内含 manifest, 则把它提升上来。"""
    dest = Path(dest)
    children = [c for c in dest.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        inner = children[0]
        if any((inner / n).is_file() for n in MODULE_MANIFEST_NAMES):
            for item in list(inner.iterdir()):
                shutil.move(str(item), str(dest / item.name))
            inner.rmdir()
    return dest


def extract_modpkg(pkg_path: Path, dest: Path) -> dict[str, Any]:
    """解包 .modpkg -> dest, 返回容器 manifest.json 内容(可能为空 dict)。"""
    pkg_path = Path(pkg_path)
    if not pkg_path.is_file():
        raise RepoError("MODULE_PACKAGE_NOT_FOUND", "包不存在: %s" % pkg_path,
                        {"path": str(pkg_path)})
    if pkg_path.stat().st_size > MAX_PACKAGE_BYTES:
        raise RepoError("MODULE_PACKAGE_CORRUPT", "包体积超限: %d" % pkg_path.stat().st_size,
                        {"path": str(pkg_path)})
    extract_zip_safely(pkg_path, dest)
    container: dict[str, Any] = {}
    cpath = Path(dest) / "manifest.json"
    if cpath.is_file():
        try:
            data = json.loads(cpath.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                container = data
        except Exception:
            container = {}
    flatten_single_root(dest)
    # 容器 manifest.json 是「包元数据」而非模组内容: 取出后删除,
    # 保证 pack -> extract 往返后目录内容与原模组逐字节一致 (sha256 不变)。
    if container.get("magic") == MODPKG_MAGIC:
        cpath = Path(dest) / "manifest.json"
        if cpath.is_file():
            cpath.unlink()
    return container


#: 确定性打包时使用的固定容器时间戳 (使「同输入 -> 同字节」可被机器断言)
DETERMINISTIC_PACKED_AT = "1970-01-01T00:00:00+00:00"


def pack_module(module_dir: Path, out_path: Path, *,
                source_note: str = "", extra: dict[str, Any] | None = None,
                deterministic: bool = False) -> dict[str, Any]:
    """把一个模组目录打成单文件 .modpkg (manifest.json 置于包首)。

    deterministic=True 时容器 manifest 的 packed_at 取固定值 —— 否则打包结果
    会因时间戳而每次不同, 使「同输入必得同字节」无法被断言 (R26 确定性判据)。
    默认 False: 既有调用方行为逐字节不变。
    """
    module_dir = Path(module_dir)
    out_path = Path(out_path)
    if not module_dir.is_dir():
        raise RepoError("MODULE_PACKAGE_NOT_FOUND", "模组目录不存在: %s" % module_dir,
                        {"path": str(module_dir)})
    files = sorted([p for p in module_dir.rglob("*") if p.is_file()],
                   key=lambda p: p.relative_to(module_dir).as_posix())
    manifest: dict[str, Any] = {}
    for name in MODULE_MANIFEST_NAMES:
        if (module_dir / name).is_file():
            try:
                data = yaml.safe_load((module_dir / name).read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    manifest = data
            except Exception:
                manifest = {}
            break
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp-%d" % os.getpid())
    container = {
        "magic": MODPKG_MAGIC,
        "packed_at": DETERMINISTIC_PACKED_AT if deterministic else _now(),
        "module_id": str(manifest.get("id") or module_dir.name),
        "name": str(manifest.get("name") or module_dir.name),
        "ruleset": str(manifest.get("ruleset") or ""),
        "version": str(manifest.get("version") or ""),
        "source_note": source_note,
        "files": [p.relative_to(module_dir).as_posix() for p in files],
    }
    if extra:
        container.update(extra)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        if deterministic:
            # zip 条目默认携带源文件 mtime -> 同内容也会因 mtime 不同而字节不同。
            # 确定性打包时统一压成固定时间戳 (1980-01-01, zip 纪元下限), 使
            # 「同输入 -> 同字节」可被机器断言。默认分支逐字节不变。
            zi = zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, json.dumps(container, ensure_ascii=False, indent=2))
            for p in files:
                arc = p.relative_to(module_dir).as_posix()
                ent = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
                ent.compress_type = zipfile.ZIP_DEFLATED
                ent.external_attr = 0o644 << 16
                zf.writestr(ent, p.read_bytes())
        else:
            zf.writestr("manifest.json", json.dumps(container, ensure_ascii=False, indent=2))
            for p in files:
                zf.write(p, p.relative_to(module_dir).as_posix())
    os.replace(tmp, out_path)
    digest = sha256_file(out_path)
    return {"path": str(out_path), "sha256": digest, "size": out_path.stat().st_size,
            "files": len(files), "container": container}
