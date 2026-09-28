"""热重载层 (R27 / R24 / R25 / R26) —— additive。

职责:
  * spec.py     —— 常量与错误类型 (编译产物结构版本 / 轮询间隔 / 保存文件名)
  * compiled.py —— 「自建等价结构」的读取、结构校验、可交互物契约校验、确定性摘要
  * diff.py     —— 两份编译产物的**确定性**差异 -> 复用既有域事件类型的变更规格
  * watcher.py  —— mtime+sha256 文件监听 + 热重载应用 + 旧状态回滚

设计铁律 (与冻结契约一致):
  * **不新增事件类型**: 变更规格只使用 app.domain.events.EVENT_TYPES 里已有的类型。
  * **不新增 WS 帧**: 变更通过 EventStore.append 落库, 由既有单一收口
    (EventStore.on_append = app.web.ws_bridge.publish_events) 自动广播成冻结的 8 帧。
    本层**绝不**直接调用 hub.publish / publish_events。
  * **不新增第二套机制**: 状态仍走 SessionState + EventStore + projector。
"""
