"""TRPG 仓库层错误码表 (R13) —— additive 增量层。

R13 判据: 5 类坏包必须返回 **各自不同且明确** 的错误码,
不得都抛同一个 MapChainError 文本; 非法包必须返回明确错误码而不是 500。

五类坏包 -> 五个独立错误码:
  1. 缺 manifest        -> MODULE_MANIFEST_MISSING
  2. 缺 id              -> MODULE_ID_MISSING
  3. 图悬挂             -> MODULE_GRAPH_DANGLING_EDGE
  4. 引用文件缺失       -> MODULE_FILE_MISSING
  5. 版本不兼容         -> MODULE_VERSION_INCOMPATIBLE
"""
from __future__ import annotations

from typing import Any

#: code -> (http_status, 默认中文说明)
ERROR_TABLE: dict[str, tuple[int, str]] = {
    # ---- R13 五类坏包: 必须各自独立, 顺序即校验顺序 ----
    "MODULE_MANIFEST_MISSING": (422, "模组包缺少 manifest(module.yaml/module.yml/manifest.json)"),
    "MODULE_ID_MISSING": (422, "manifest 缺少 id 字段, 或 id 不是合法标识符"),
    "MODULE_VERSION_INCOMPATIBLE": (422, "模组 schema_version/min_engine_version 与当前服务端不兼容"),
    "MODULE_GRAPH_DANGLING_EDGE": (422, "事件图存在悬挂边: edge.from/edge.to 不在 nodes 中"),
    "MODULE_FILE_MISSING": (422, "manifest 声明的引用文件在包内不存在"),
    # ---- 结构类 ----
    "MODULE_MANIFEST_INVALID": (422, "manifest 不是 YAML/JSON 映射, 或字段类型非法"),
    "MODULE_GRAPH_MISSING": (422, "事件图文件缺失或不是 YAML/JSON 映射"),
    "MODULE_GRAPH_EMPTY": (422, "事件图 nodes[] 为空或节点缺少 id"),
    "MODULE_INITIAL_SCENE_INVALID": (422, "initial_scene 缺失或不在事件图 nodes 中"),
    "MODULE_REF_INTEGRITY": (422, "模组内部引用悬空(clue_refs/npc_refs/map_ref/clue.location/clue.points_to)"),
    "MODULE_RULESET_MISSING": (422, "manifest 缺少 ruleset 字段"),
    "MODULE_RULESET_UNKNOWN": (422, "manifest 声明的 ruleset 在规则仓库中不存在"),
    "MODULE_COUNT_MISMATCH": (422, "实际场景数/事件节点数/NPC 数与声明不一致"),
    # ---- 包 / 传输类 ----
    "MODULE_PACKAGE_NOT_FOUND": (404, "指定的包或路径不存在"),
    "MODULE_PACKAGE_CORRUPT": (422, "包不是合法 zip/modpkg, 或含非法条目"),
    "MODULE_PACKAGE_SHA256_MISMATCH": (422, "读取/下载后的 sha256 与声明不一致"),
    "MODULE_PACKAGE_SHA256_REQUIRED": (422, "远程 URL 导入必须提供 sha256"),
    "MODULE_DOWNLOAD_FAILED": (502, "从远程 URL 下载模组包失败"),
    "MODULE_DOWNLOAD_SCHEME_REJECTED": (400, "下载 URL 协议不被允许(仅 http/https)"),
    # ---- 仓库条目类 ----
    "REPO_ENTRY_NOT_FOUND": (404, "仓库条目不存在"),
    "REPO_ENTRY_DELETED": (410, "仓库条目已软删(未物理删除, 可 restore)"),
    "REPO_ENTRY_EXISTS": (409, "仓库条目已存在(需 overwrite=true)"),
    "REPO_ENTRY_INVALID_ID": (400, "条目 id 非法(仅 [A-Za-z0-9][A-Za-z0-9_.-]{0,63})"),
    "REPO_PATH_TRAVERSAL": (400, "路径穿越/绝对路径/符号链接被拒绝"),
    "REPO_BAD_KIND": (400, "仓库类别非法(仅 modules/rulepacks)"),
    "REPO_WRITE_BODY_INVALID": (422, "写入请求体非法"),
    "REPO_SESSION_EXISTS": (409, "开局句柄冲突: table_id 已存在"),
    "REPO_IMPORT_FAILED": (500, "导入失败(已回滚, 未留下半成品)"),
    # ---- 规则包 ----
    "RULEPACK_MANIFEST_MISSING": (422, "规则包缺少 rulepack.yaml/rulepack.yml/manifest.json"),
    "RULEPACK_ID_MISSING": (422, "规则包 manifest 缺少 id 字段"),
    "RULEPACK_MANIFEST_INVALID": (422, "规则包 manifest 不是 YAML/JSON 映射"),
    "RULEPACK_FILE_MISSING": (422, "规则包 manifest 引用的文件不存在"),
    "RULEPACK_VERSION_INCOMPATIBLE": (422, "规则包 schema_version/min_engine_version 不兼容"),
    "RULEPACK_ENTRY_NOT_FOUND": (404, "规则包不存在"),
    "RULEPACK_ENTRY_DELETED": (410, "规则包已软删"),
    "RULEPACK_ENTRY_EXISTS": (409, "规则包已存在(需 overwrite=true)"),
}


class RepoError(Exception):
    """仓库层统一异常: 携带明确的 error_code + http_status + detail。"""

    def __init__(self, code: str, message: str = "", detail: Any = None) -> None:
        entry = ERROR_TABLE.get(code)
        if entry is None:  # 防呆: 不允许抛出未登记的错误码
            raise KeyError("unknown repo error code: %r" % (code,))
        status, default_msg = entry
        msg = message or default_msg
        super().__init__("[%s] %s" % (code, msg))
        self.code = code
        self.http_status = status
        self.message = msg
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "error_code": self.code, "message": self.message,
                "http_status": self.http_status, "detail": self.detail}


def error_code_table() -> dict[str, Any]:
    """错误码表全量导出 (供 /api/repository/error_codes 与验收取证)。"""
    return {"ok": True, "schema": "RepoErrorTable v1", "count": len(ERROR_TABLE),
            "codes": [{"code": c, "http_status": s, "message": m}
                      for c, (s, m) in sorted(ERROR_TABLE.items())]}


#: R13 五类坏包 -> 错误码 (验收直接比对)
R13_BAD_PACKAGE_CODES: dict[str, str] = {
    "missing_manifest": "MODULE_MANIFEST_MISSING",
    "missing_id": "MODULE_ID_MISSING",
    "dangling_edge": "MODULE_GRAPH_DANGLING_EDGE",
    "missing_referenced_file": "MODULE_FILE_MISSING",
    "version_incompatible": "MODULE_VERSION_INCOMPATIBLE",
}
