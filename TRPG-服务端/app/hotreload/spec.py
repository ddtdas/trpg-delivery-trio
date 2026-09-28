"""热重载层常量与错误类型 (R27) —— additive。"""
from __future__ import annotations

from typing import Any

#: 编译产物结构版本 (自建等价结构)
COMPILED_SCHEMA = "DeadLightCompiled v1"
#: 保存文件 (R26 ②「导入后保存文件」) 相对模块目录的路径
SAVE_RELPATH = "compiled/save_state.json"
#: 编译产物 (R26 ②「自建等价结构」) 相对模块目录的路径
COMPILED_RELPATH = "compiled/dead_light.compiled.json"
#: 出处/摘要 (R26 ①「原版本体文档」的合法替代: 公开元数据 + 摘要 + 出处)
SOURCE_RELPATH = "source/PROVENANCE.json"

#: 绑定表持久化 (F-9): 相对 <app_root>/data 的路径。
#: 放在 data/ 之下, 与 prep/imports/staging 同域 —— 交付打包策略只保留 data/.gitkeep,
#: 运行态绑定表不会进包 (也不会被误当成交付内容)。
BINDINGS_RELPATH = "hotreload/bindings.json"
#: 绑定表文件结构版本
BINDINGS_SCHEMA = "HotReloadBindings v1"

#: 文件监听轮询间隔 (秒) —— 「改保存文件后若干秒内状态更新并推送」
POLL_INTERVAL_S = 1.0
#: 回滚历史深度
HISTORY_DEPTH = 16
#: 每次热重载最多产生的变更事件数 (防护)
MAX_CHANGES_PER_APPLY = 512

#: 可交互物必须声明的动作集 (至少一个, 且必须在 ALLOWED_ACTIONS 内)
ALLOWED_ACTIONS: tuple[str, ...] = (
    "inspect", "take", "use", "open", "close", "read", "light",
    "search", "listen", "talk", "attack", "break",
)


#: 错误码 -> HTTP 状态 (未列出的默认 422)。
#: 与既有 RepoError 的「每个错误码都有明确状态、绝不 500」契约同源。
ERROR_STATUS: dict[str, int] = {
    "HOTRELOAD_NOT_BOUND": 404,
    "COMPILED_FILE_MISSING": 404,
    "HOTRELOAD_NO_HISTORY": 409,
    "COMPILED_INTERACTABLE_DUPLICATE": 409,
}


class CompiledError(ValueError):
    """编译产物结构非法 / 热重载前置条件不满足。"""

    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None,
                 http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = dict(detail or {})
        self.http_status = int(http_status if http_status is not None
                               else ERROR_STATUS.get(code, 422))

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "error_code": self.code, "message": self.message,
                "http_status": self.http_status, "detail": self.detail}
