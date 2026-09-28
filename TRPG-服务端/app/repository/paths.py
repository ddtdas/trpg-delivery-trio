"""路径穿越防护 (R22 判据 3) —— additive。

拒绝并返回明确错误码 REPO_PATH_TRAVERSAL 的情形:
  * '../' 上跳 (含 '..\\' 反斜杠变体、任意层数);
  * 绝对路径 ('/x', '\\\\srv\\share', 'C:\\x', '~');
  * 符号链接 / Windows junction (路径任一已存在组件是链接);
  * URL 编码绕过 (%2e%2e%2f, 双层 %252e%252e%252f, '+' 空格变体);
  * NUL 字节、盘符冒号、Windows 尾随空格/点等别名技巧。
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, unquote_plus

from app.repository.errors import RepoError
from app.repository.spec import ENTRY_ID_RE

#: 反复解码轮数 (覆盖 %25 双层/三层编码绕过)
MAX_DECODE_ROUNDS = 4
_WIN_DRIVE_RE = __import__("re").compile(r"^[A-Za-z]:")


def decode_layers(raw: str, rounds: int = MAX_DECODE_ROUNDS) -> str:
    """反复 URL 解码直到稳定 —— 专门用来打掉 %252e%252e%252f 这类多层绕过。"""
    s = str(raw)
    for _ in range(max(1, rounds)):
        nxt = unquote_plus(s)
        if nxt == s:
            break
        s = nxt
    return s


def _reject(raw: object, reason: str, label: str, **extra: object) -> "RepoError":
    detail = {"label": label, "raw": raw, "reason": reason}
    detail.update(extra)
    return RepoError("REPO_PATH_TRAVERSAL", "%s: %r" % (reason, raw), detail)


def validate_entry_id(entry_id: object, *, label: str = "entry_id") -> str:
    """条目 id 白名单校验; 非法 -> REPO_ENTRY_INVALID_ID (400)。"""
    if not isinstance(entry_id, str):
        raise RepoError("REPO_ENTRY_INVALID_ID", "id 必须是字符串", {"label": label, "raw": entry_id})
    raw = entry_id
    decoded = decode_layers(raw)
    if decoded != raw:
        raise RepoError("REPO_ENTRY_INVALID_ID",
                        "id 不允许 URL 编码: %r" % raw, {"label": label, "raw": raw, "decoded": decoded})
    if not ENTRY_ID_RE.match(raw):
        raise RepoError("REPO_ENTRY_INVALID_ID",
                        "id 不符合 [A-Za-z0-9][A-Za-z0-9_.-]{0,63}: %r" % raw,
                        {"label": label, "raw": raw})
    return raw


def is_symlinkish(p: Path) -> bool:
    """符号链接或 Windows junction。"""
    try:
        if p.is_symlink():
            return True
    except OSError:
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        try:
            if isjunction(p):
                return True
        except OSError:
            return True
    return False


def assert_within(root: Path, target: Path, *, label: str = "path") -> Path:
    """确保 target 解析后仍位于 root 之内, 且路径上没有任何链接组件。"""
    root_p = Path(root)
    root_real = root_p.resolve()
    tgt = Path(target)

    # 1) 逐级检查 root 之下每个组件是否为链接 (含 junction)
    try:
        rel_parts = tgt.relative_to(root_p).parts
    except ValueError:
        raise _reject(str(target), "目标不在仓库根下", label) from None
    cur = root_p
    if is_symlinkish(cur):
        raise _reject(str(target), "仓库根自身是符号链接/junction", label, component=str(cur))
    for part in rel_parts:
        cur = cur / part
        if is_symlinkish(cur):
            raise _reject(str(target), "路径包含符号链接/junction", label, component=str(cur))

    # 2) 解析后必须落在 root 内
    real = tgt.resolve()
    if real != root_real and root_real not in real.parents:
        raise _reject(str(target), "解析后越出仓库根目录", label,
                      root=str(root_real), resolved=str(real))
    return real


def safe_join(root: Path, rel: object, *, label: str = "path") -> Path:
    """把相对路径 rel 安全地拼到 root 下; 任何可疑形态一律 REPO_PATH_TRAVERSAL。"""
    if not isinstance(rel, str) or not rel:
        raise _reject(rel, "路径为空或非字符串", label)
    if "\x00" in rel:
        raise _reject(rel, "路径含 NUL 字节", label)

    decoded = decode_layers(rel)
    norm = decoded.replace("\\", "/")
    if "\x00" in norm:
        raise _reject(rel, "路径含 NUL 字节(解码后)", label, decoded=decoded)
    if decoded != rel:
        raise _reject(rel, "路径含 URL 编码绕过", label, decoded=decoded)
    if norm.startswith("/") or norm.startswith("//") or _WIN_DRIVE_RE.match(norm) or norm.startswith("~"):
        raise _reject(rel, "绝对路径被拒绝", label, decoded=decoded)

    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts:
        raise _reject(rel, "路径为空(规范化后)", label)
    for part in parts:
        if part == "..":
            raise _reject(rel, "路径含 .. 上跳", label, decoded=decoded)
        if ":" in part:
            raise _reject(rel, "路径段含冒号(盘符/ADS)", label, segment=part)
        if part != part.rstrip(" ."):
            raise _reject(rel, "路径段以空格/点结尾(Windows 别名)", label, segment=part)

    target = Path(root).joinpath(*parts)
    return assert_within(root, target, label=label)


def rel_posix(root: Path, target: Path) -> str:
    """仓库根内的 POSIX 风格相对路径。"""
    return Path(target).resolve().relative_to(Path(root).resolve()).as_posix()
