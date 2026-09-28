# 安全与对账契约（冻结件 ❄ v1.0 · 2026-09-19）

> 依据：04 事件协议（MCP 权限矩阵／perf 打点）、05 DSH 集成（N3 token／N6 对账）、build_plan_v1 §1。
> 原则：服务端权威——VisibilityEngine 与权限校验只在后端生效；客户端只做镜像，任何越权显示即 P0 缺陷。

## 1. token 生命周期

1. `TABLE_CREATED` 时生成 `table_token`（`tt_<rand24>`），只随 KP 通道下发，存 server 侧配置（`configs/table_<id>.token`，0600 权限），永不进事件 payload／日志／PL 可见 DTO。
2. 注入：KP 前端存内存＋`TRPG_TABLE_TOKEN` 环境变量（DSH skill 模板强制工具带 `actor:{id:'kp',token}`）。
3. 校验：server 入口 `_require_kp` 比对常量时间；失败 `403 {error:"kp_token_required"|"actor_required"}` 并记审计事件（不记 token 值）。
4. 轮换／吊销：KP 可调 `rotate_token`（旧 token 5 分钟宽限）；`revoke` 即时失效；轮换落 `TABLE_CONFIG_UPDATED{diff:["table_token_rotated"]}`（不记值）。
5. 备选：KP/只读双实例（`trpg`／`trpg-ro`，后者只注册 4 只读工具）二选一必实现其一；默认单实例＋token。

## 2. 权限矩阵（13 工具 × 3 角色；✅允许／❌403／—不适用）

| 工具 | KP（持 token） | PL（玩家本人资源） | 旁听（只读公开流） |
|---|---|---|---|
| character_create | ✅（代建／审批入桌） | ✅（仅自己 card） | ❌ |
| roll_check | ✅ | ❌ | ❌ |
| roll_preview | ✅ | ✅ | ✅ |
| event_inject | ✅（白名单＋批准） | ❌ | ❌ |
| narration_propose | ✅（可代提） | ✅（经 slot 才可，仍待批） | ❌ |
| narration_approve | ✅ | ❌ | ❌ |
| info_distribute | ✅ | ❌ | ❌ |
| transcribe_audio | ✅（job） | ❌（可上传音频块，见 runtime AUDIO_CHUNK） | ❌ |
| image_generate | ✅ | ✅（job，仅自己 card） | ❌ |
| map_command（读 get） | ✅ | ✅（可见范围） | ✅（公开层） |
| map_command（写） | ✅（命令链＋批准） | ❌ | ❌ |
| summarize_session | ✅（job，可匿名化） | ❌ | ❌ |
| session_state | ✅（全量对账字段） | ✅（pending 只见与己相关） | ✅（event_seq＋hash） |
| job_get_status | ✅ | ✅（仅自己提交的 job） | ❌ |
| npc_act（预留） | ❌（默认 403，四重开闸后解除） | ❌ | ❌ |

- 私密字面量（secret_ref／凶手 secret／whisper body／condition 未满足 body）永不出后端 DTO；Hub 层断言"非目标绝无该字段"（M4a 单测）。
- 越权调用一律 403，不泄露"是否存在"的区分信息。

## 3. session_state 对账（goal resume 必经）

- 只读快照：`{campaign_id, event_seq, projected_hash, pending_approvals[], turn_cursor}`；`projected_hash`=M2 确定性序列化（事件 seq 序＋JSON sorts keys＋sha256）。
- 对账伪代码：
```
cli = session_state(campaign_id)                 # DSH resume 前必调
srv = EventStore.tip(campaign_id)                # seq + hash
assert cli.event_seq <= srv.seq, "client-ahead: full-resync"
if cli.projected_hash != replay_hash(upto=cli.event_seq): full-resync + context_builder 重建
replay(srv.events[cli.event_seq:])               # 追平
context_builder.rebuild(viewer)                  # 按可见性裁剪后恢复叙事
```
- EventStore 为唯一事实源；goal 中断 `resume` 前必须先对账再叙事；失配时全量重放，禁止"接着编"。

## 4. 自查清单

- [x] token 生成／存储／注入／校验／轮换／吊销全生命周期齐
- [x] 13×3 权限矩阵齐（含 npc_act 预留 403、map 读写分权、job 按 actor 过滤）
- [x] session_state 字段＋projected_hash 算法齐
- [x] 对账伪代码齐（resume 必调，失配全量重放）
- [x] 私密不出 DTO 断言齐；无 AGPL 内容
