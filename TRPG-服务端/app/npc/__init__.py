"""R28-R31: NPC 自主性（additive 分层）。

模块划分
--------
skills.py   -- R28 按 NPC 生成的一次性（团内临时）技能，与全局技能表隔离
memory.py   -- R29 NPC 记忆（见过谁 / 发生过什么 / 玩家做过什么），GM 可查/改/清
director.py -- R30/R31 反应生成 + 主持人决定权（复用统一审批总线）
routes.py   -- additive REST 层（GM 控制面 + 玩家可见读口）

铁律
----
- 不新增事件类型、不新增协议帧：只用既有 NPC_ACT_PROPOSED / NPC_ACT_APPROVED。
- 自动生成的行为**绝不直接下发玩家**：先入 GM 待审队列，经既有审批总线
  POST /api/campaigns/{c}/approvals 拍板后才产生 NPC_ACT_APPROVED。
- 不新建第二套审批机制，不新建第二套鉴权体系。
"""
from __future__ import annotations
