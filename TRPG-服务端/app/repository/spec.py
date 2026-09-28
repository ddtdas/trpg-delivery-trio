"""模组/规则包 schema 规范与版本兼容性常量 (R13/R22) —— additive。

版本兼容判据 (确定、可测):
  * manifest.schema_version (缺省 "1") 必须落在 SUPPORTED_*_SCHEMA_VERSIONS 内;
  * manifest.min_engine_version (可选) 不得高于 REPO_ENGINE_VERSION;
  任一不满足 -> MODULE_VERSION_INCOMPATIBLE / RULEPACK_VERSION_INCOMPATIBLE。
"""
from __future__ import annotations

import re
from typing import Any

#: 仓库层自身作为「引擎」的版本 (与 app.VERSION 解耦, 便于稳定判定)
REPO_ENGINE_VERSION = "0.1.0"

SUPPORTED_MODULE_SCHEMA_VERSIONS: tuple[str, ...] = ("1", "1.0", "1.0.0")
#: 规则包 manifest 格式版本白名单。R23 的规则包内容代次为 2, 故 2.x 一并放行,
#: 避免「内容侧写 schema_version: "2" 就被仓库层判不兼容」的跨任务地雷。
#: 注意: 这里判的是 **仓库层打包/manifest 格式版本**(manifest.schema_version),
#: 与规则包自身的**内容模型代次**(manifest.schema, 例如 R23 的 schema: 2)是两个概念,
#: 后者不被本字段读取, 以免语义混淆。
SUPPORTED_RULEPACK_SCHEMA_VERSIONS: tuple[str, ...] = ("1", "1.0", "1.0.0", "2", "2.0", "2.0.0")

MODULE_MANIFEST_NAMES: tuple[str, ...] = ("module.yaml", "module.yml", "manifest.json")
RULEPACK_MANIFEST_NAMES: tuple[str, ...] = ("rulepack.yaml", "rulepack.yml", "manifest.json")

MODPKG_MAGIC = "trpg.modpkg/v1"
MODPKG_EXT = ".modpkg"

#: 条目 id 白名单: 首字符字母数字, 其余字母数字/_/./- ; 长度 <= 64
ENTRY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")

#: 索引文件名 (相对仓库根)
INDEX_FILENAME = "index.json"
#: 软删墓碑文件名 (相对仓库根, 隐藏文件 -> 扫描时自动跳过)
TOMBSTONE_FILENAME = ".tombstones.json"

#: 扫描仓库目录时跳过的名字前缀 (打包目录 / 暂存目录 / 隐藏文件)
SKIP_PREFIXES: tuple[str, ...] = (".", "_")

MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_UNPACK_BYTES = 256 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 30.0


def parse_version(text: Any) -> tuple[int, ...]:
    """把 '1.2.3-t12' 解析为 (1,2,3) —— 非数字段一律忽略, 永不抛异常。"""
    out: list[int] = []
    for chunk in re.split(r"[.\-_+]", str(text or "").strip()):
        m = re.match(r"^(\d+)", chunk)
        if m:
            out.append(int(m.group(1)))
        elif out:
            break
    return tuple(out) or (0,)


def version_lt(a: Any, b: Any) -> bool:
    """a < b (按数值段比较, 缺位补 0)。"""
    va, vb = parse_version(a), parse_version(b)
    n = max(len(va), len(vb))
    va = va + (0,) * (n - len(va))
    vb = vb + (0,) * (n - len(vb))
    return va < vb


def normalize_schema_version(raw: Any) -> str:
    return str(raw if raw is not None else "1").strip()
