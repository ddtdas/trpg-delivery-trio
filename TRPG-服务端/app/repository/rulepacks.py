"""规则包 (rulepack) 的校验与写入 —— additive (R22 判据 2 的另一套)。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.repository.errors import RepoError
from app.repository.paths import safe_join, validate_entry_id
from app.repository.spec import (REPO_ENGINE_VERSION,
                                 SUPPORTED_RULEPACK_SCHEMA_VERSIONS,
                                 normalize_schema_version, version_lt)

RULEPACK_MANIFEST_NAMES = ("rulepack.yaml", "rulepack.yml", "manifest.json")


def read_rulepack_manifest(root: Path) -> tuple[dict[str, Any], str]:
    root = Path(root)
    for name in RULEPACK_MANIFEST_NAMES:
        p = root / name
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RepoError("RULEPACK_MANIFEST_INVALID",
                                "rulepack manifest 解析失败(%s): %s" % (name, exc),
                                {"file": name}) from exc
            if not isinstance(data, dict):
                raise RepoError("RULEPACK_MANIFEST_INVALID", "rulepack manifest 不是映射", {"file": name})
            return data, name
    raise RepoError("RULEPACK_MANIFEST_MISSING",
                    "规则包内未找到 rulepack.yaml/rulepack.yml/manifest.json",
                    {"root": str(root), "looked_for": list(RULEPACK_MANIFEST_NAMES)})


def validate_rulepack(root: Path) -> dict[str, Any]:
    """规则包校验: manifest -> id -> 版本 -> 引用文件。"""
    root = Path(root)
    if not root.is_dir():
        raise RepoError("REPO_ENTRY_NOT_FOUND", "规则包目录不存在: %s" % root, {"path": str(root)})
    manifest, name = read_rulepack_manifest(root)
    raw_id = manifest.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise RepoError("RULEPACK_ID_MISSING", "rulepack: id required", {"manifest": name})
    rid = validate_entry_id(raw_id.strip(), label="rulepack.id")

    sv = normalize_schema_version(manifest.get("schema_version"))
    if sv not in SUPPORTED_RULEPACK_SCHEMA_VERSIONS:
        raise RepoError("RULEPACK_VERSION_INCOMPATIBLE",
                        "schema_version=%r 不受支持" % sv,
                        {"schema_version": sv, "engine_version": REPO_ENGINE_VERSION})
    min_engine = manifest.get("min_engine_version")
    if min_engine and version_lt(REPO_ENGINE_VERSION, str(min_engine)):
        raise RepoError("RULEPACK_VERSION_INCOMPATIBLE",
                        "min_engine_version=%s 高于当前引擎 %s" % (min_engine, REPO_ENGINE_VERSION),
                        {"min_engine_version": str(min_engine), "engine_version": REPO_ENGINE_VERSION})

    files = manifest.get("files") or {}
    if isinstance(files, dict):
        missing = []
        for rel in files.values():
            if not isinstance(rel, str) or not rel:
                continue
            if not safe_join(root, rel, label="rulepack.files").is_file():
                missing.append(rel)
        if missing:
            raise RepoError("RULEPACK_FILE_MISSING",
                            "规则包引用的文件不存在: %s" % ", ".join(sorted(missing)),
                            {"rulepack_id": rid, "missing": sorted(missing)})
    return {"ok": True, "rulepack_id": rid, "manifest": manifest, "manifest_name": name}
