# R2 契约变更声明：NPC gate 默认值由 locked 改为 open

> 声明方：implementer-npc（T3 / R28-R31）｜ 日期：R2 迭代 ｜ 状态：已实施并验证
> 关联需求：R30（NPC 反应与对话自动生成）、R31（主持人决定权与随时改）

## 1. 变更内容（breaking-ish：改变了既有默认行为）

| 项 | 变更前 | 变更后 |
|---|---|---|
| `POST /api/campaigns/{c}/npc_act` | 恒 `403 npc_act locked (default 403)` | **默认解锁**，返回 `201` + 候选入主持人待审队列 |
| `Hub.npc_guard`（app/web/ws.py） | 恒 `{"kind":"ERROR","error":"npc_act locked (default 403)"}` | 默认 `{"kind":"ACK","up":"NPC_ACT","gate":"open"}`，并可委派同一条审批总线 |
| MCP 工具 `mcp__trpg__npc_act` | 恒 403（`app/mcp/auth.py:78` 恒真式） | **默认解锁**（R30 第三处锁，t14 已修） |

## 2. 依据

R30 要求「NPC 反应与对话可自动生成」，R31 要求「主持人可随时决定/改写/中断」。
若 `npc_act` 恒 403，这两条能力在运行期完全不可达（前序契约把该端点当占位保留）。
因此解锁是满足 R30/R31 的必要条件。

## 3. 回退开关（已保留，逐字兼容）

```powershell
$env:TRPG_NPC_GATE = "locked"      # 任何非 locked 值（含未设置）= 解锁（默认）
python scripts\_serve.py 9211
```

锁回后错误响应与改造前**逐字一致**：
- REST：`403 {"detail": "npc_act locked (default 403)"}`
- WS：`{"kind": "ERROR", "error": "npc_act locked (default 403)"}`

## 4. 解锁后的行为边界（重要：解锁 != 自动对玩家生效）

解锁只让**候选**进入主持人待审队列，**不改变**「自动行为必须先过主持人」这一硬约束：

1. `npc_act` 只产生 `NPC_ACT_PROPOSED` 事件 + `npc_proposal[status=pending]` 记录；
   事件 payload 的 `lines` 恒为 `[]`（候选正文**不进事件流**）。
2. 只有经**既有唯一审批总线** `POST /api/campaigns/{c}/approvals` 拍板（approve/edit），
   才产生 `NPC_ACT_APPROVED`（`actor=approved_by="kp"`），正文经 `payload.line` 下发给玩家；
   驳回不产生任何事件。
3. 审批总线的 **NPC 分支要求主持端凭据**：无 token → `401`；玩家端(mobile) token → `403 kp_only`。
4. 未命中 `npc_proposal` 的 `proposal_id` 走原有旁白分支，语义与改造前逐字一致。

## 5. 验证证据（可复现）

```
ssh <110> → cd <TRPG-服务端>
python scripts\verify_npc_r28_r31.py     # 26 条判据，VERIFY_RESULT=PASS / exit 0
python scripts\verify_npc_ws_guard.py    # 7 条判据，含锁回开关验证，VERIFY_RESULT=PASS / exit 0
```

关键原始输出见 `run/verify_npc_r28_r31.txt`、`run/verify_npc_ws_guard.txt`。

## 6. 兼容性影响面

- **调用方**：任何依赖 `npc_act` 返回 403 的客户端/测试会看到 201。若需要旧行为，设 `TRPG_NPC_GATE=locked`。
- **`decide_approval` 签名**：`(campaign, body)` → `(campaign, body, request: Request)`。
  HTTP 路由层不受影响；**直接以函数方式调用**它的代码需同步补第三个实参。
- **冻结文件未改**：未新增事件类型、未新增协议帧（`events.py` / `ws_protocol.py` / `ws_bridge.py` sha256 前后一致）。

## 7. 追加（t14）：MCP 工具 mcp__trpg__npc_act 的第三处硬锁

### 变更内容
| 项 | 变更前 | 变更后 |
|---|---|---|
| app/mcp/auth.py:78 | if raw == "npc_act" or (NPC_GATE_OPEN is False and raw == "npc_act") —— **恒真式**，无论开关如何都抛 npc_forbidden | if raw == "npc_act" and not NPC_GATE_OPEN: —— 真正的开关判定 |
| auth.NPC_GATE_OPEN | 硬编码 False（且因恒真式而无效） | os.environ.get("TRPG_NPC_GATE", "open") != "locked"，与 REST/WS **同一个开关** |
| auth.TOOL_ACCESS["npc_act"] | "forbidden" | "actor"（候选仍必须先过主持人；门关时抛 npc_forbidden） |
| app/mcp/server.py | 无 npc_act 分发分支（落到 404 unknown_tool） | 新增 do_npc_act()，委派 app.npc.director.handle_npc_act |
| server.describe() | "reserved_403": ["mcp__trpg__npc_act"]（静态） | 动态：门开 [] / 门关保留旧声明；新增 "npc_gate": "open" 或 "locked" |
| app/mcp/schemas.py:32 | # reserved: registered but always 403 | # R2 (R30): 门开时可用; TRPG_NPC_GATE=locked 回锁 403 |
| app/mcp/schemas.py:109 | "npc_act": {"error": "npc_forbidden"} | 成功体骨架 {seq,type,proposal_id,npc_id,status,visible_to_players,note} |

### 为什么必须做（依据）
app/mcp/auth.py:15 原本写着 NPC_GATE_OPEN = False  # four-gate NPC opening; default closed
—— 即**原设计就存在这个门**，只是第 78 行的判定写成了恒真式，使门永远无效。R30/R31 要求
「NPC 反应与对话可自动生成」「主持人可随时决定」，因此把门做成真开关是满足需求的必要条件。

### 边界（与 REST/WS 完全同源，未新建任何机制）
1. 门开只让**候选**进入主持人待审队列（NPC_ACT_PROPOSED + npc_proposal[status=pending]）；
2. 拍板仍走**既有唯一审批总线** POST /api/campaigns/{c}/approvals，才产生 NPC_ACT_APPROVED；
3. npc_act 响应**不回显候选台词**（与 REST 一致）；
4. **未新增事件类型、未新增协议帧**：FROZEN_NAMES=13、ALL_NAMES=14 不变，
   trpg/agent/events.py sha256 仍为 839B1016610D54D9...。

### 回退
    $env:TRPG_NPC_GATE = "locked"     # REST / WS / MCP 三处同时回锁，错误语义逐字恢复旧版

锁回后：REST 403 npc_act locked (default 403)；WS {"kind":"ERROR","error":"npc_act locked (default 403)"}；
MCP 403 {"error":"npc_forbidden"}，且 describe().reserved_403 == ["mcp__trpg__npc_act"]。

### 验证
    python scripts/verify_mcp_npc_act.py    # 13 条判据，VERIFY_RESULT=PASS / exit 0
    python scripts/verify_npc_r28_r31.py    # 回归 26 条，PASS
    python scripts/verify_npc_ws_guard.py   # 回归 7 条，PASS

### 声明（对 app/mcp 自带 FROZEN 头的说明）
app/mcp/auth.py 与 schemas.py 头部写有 FROZEN (MIT) 与
Source: docs/contracts/security-sync.md v1.0 第1/2节 (t4 frozen)，
并声明「Any change requires a contract change」。
**本文件（docs/R2-NPC-CONTRACT-CHANGE.md）即该契约变更记录。**
另注：docs/contracts/ 目录在本交付包内**不存在**（mcp-contract.md / runtime-contract.md /
security-sync.md 三份均缺失），而冻结的 docs/CROSS-END-CONTRACT.md 第 1.5 节仍按 6 项 sha256 比对
（AC-7.28）—— 该缺失已作为交付缺陷上报队长。
