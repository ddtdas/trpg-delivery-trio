"""TRPG 仓库层 (repository) —— R22/R1/R2/R13/R3 的 additive 增量层.

不修改任何冻结文件 (app/domain/events.py / app/web/ws_protocol.py /
app/web/ws_bridge.py / docs/CROSS-END-CONTRACT.md), 不新增事件类型,
不新增协议帧; 只新增文件 + 新增路由 (additive)。

模块职责
--------
errors.py     错误码表 (R13: 5 类坏包各自独立错误码)
spec.py       模组/规则包 schema 版本与引擎兼容性常量
paths.py      路径穿越防护 (../ / 绝对路径 / 符号链接 / URL 编码绕过)
roots.py      仓库根目录集合 (可注入, 便于测试隔离)
index.py      modules/index.json + rulepacks/index.json 的确定性重建
pkg.py        .modpkg 单文件容器打包/安全解包
prep.py       导入后地图/事件/NPC/线索准备 (R3)
importer.py   导入编排: 解析 -> 校验 -> 落库 -> 准备 -> 开局句柄 (R1/R2)
"""
from __future__ import annotations

__all__ = [
    "errors", "spec", "paths", "roots", "index", "pkg", "prep", "importer",
]
