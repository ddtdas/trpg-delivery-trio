# MCP 契约（冻结件 ❄ v1.0 · 2026-09-19）

> 依据：`trpg_run/docs/04_event_protocol_spec.md`、`05_dsh_integration.md`、`plan/build_plan_v1.md §1/§2`。
> 地位：冻结规格，后续实现不得偏离；改名禁令——工具全名一经冻结永不改名，只增版本；新增工具走契约变更（merge 回本文件＋广播）。
> 挂载：单进程 FastAPI 同端口 streamable-http `http://127.0.0.1:9210/mcp`（stdio 仅瘦客户端备用）；DSH 侧 serverName=`trpg`；全名冻结表 `mcp__trpg__<raw>`。

## 1. 冻结全名表（13 名：11 启用＋session_state＋job_get_status；npc_act 预留 403）

| # | raw 名 | 冻结全名 | 状态 | 权限 |
|---|---|---|---|---|
| 1 | `character_create` | `mcp__trpg__character_create` | 启用 | 玩家/写（含 validate） |
| 2 | `roll_check` | `mcp__trpg__roll_check` | 启用 | KP/写（落 CHECK_RESOLVED） |
| 3 | `roll_preview` | `mcp__trpg__roll_preview` | 启用 | 公开/读（只读推演，不落事件，防双骰） |
| 4 | `event_inject` | `mcp__trpg__event_inject` | 启用 | KP/写（dry_run 预览＋白名单＋批准） |
| 5 | `narration_propose` | `mcp__trpg__narration_propose` | 启用 | agent/写→待批（不落库，进 KP 待批队列，须带 actor.id） |
| 6 | `narration_approve` | `mcp__trpg__narration_approve` | 启用 | KP/写（批准/编辑/否决） |
| 7 | `info_distribute` | `mcp__trpg__info_distribute` | 启用 | KP/写（public/whisper/hidden/condition） |
| 8 | `transcribe_audio` | `mcp__trpg__transcribe_audio` | 启用 | KP/写（job 语义） |
| 9 | `image_generate` | `mcp__trpg__image_generate` | 启用 | 玩家/写（job 语义，写 ImageRef） |
| 10 | `map_command` | `mcp__trpg__map_command` | 启用 | 读公开／写 KP（读侧含 map_get 语义，走命令链＋批准） |
| 11 | `summarize_session` | `mcp__trpg__summarize_session` | 启用 | KP/写（job 语义，可匿名化） |
| 12 | `session_state` | `mcp__trpg__session_state` | 启用 | 公开/读（只读对账快照，见 security-sync.md） |
| 13 | `job_get_status` | `mcp__trpg__job_get_status` | 启用 | 公开/读（按 actor 过滤，只见自己提交的 job） |
| — | `npc_act` | `mcp__trpg__npc_act` | 预留 | 注册但调用即 403（四重开闸后解除，见 02 §NPC） |

> 口径说明：`map_get` 为 `map_command` 的只读操作模式（`op:"get"`），不占独立全名，11 启用口径以此为准。

## 2. 通用信封

- 每个写工具入参必带 `actor:{id:string, token?:string}`；KP 写工具无/错 token → `403 {error:"kp_token_required"|"actor_required"}`；校验位置 server 入口 `_require_kp`／`_require_actor` 装饰器。
- 写工具成功返回 `{ok:true, events:[{seq,type}], job_id?}`；`seq/hash` 与 EventStore 一致；`payload` 全 JSON 可序列化、无函数。
- DSH 调用示例：`uv run trpg-mcp --table=tbl_demo --transport=streamable-http`；调试 `npx @modelcontextprotocol/inspector`。

## 3. 工具签名（input/output 骨架）

1. `character_create{actor, ruleset, card{attrs,skills,background,secret_ref?}}` → `{ok, card_id, validation_report}`；非法卡 422；落 `CHARACTER_CREATED`（KP 批入桌时 `CARD_FINALIZED`）。
2. `roll_check{actor(kp), campaign_id, turn_no, card_id, target, difficulty, bonus?, penalty?, seed}` → `{ok, rolled[], total, level, seed}`；落 `CHECK_RESOLVED`。
3. `roll_preview{campaign_id, card_id, target, difficulty, bonus?, penalty?}` → `{total, level, note:"preview-only"}`；不落事件。
4. `event_inject{actor(kp), campaign_id, node_id, payload, dry_run:bool}` → dry_run 时 `{dry_run_result}` 不落库；`dry_run:false` 须白名单＋批准，落 `EVENT_INJECTED`。
5. `narration_propose{actor{id}, campaign_id, text, intention?, reasoning, source}` → `{ok, proposal_id}`；进待批队列，落 `NARRATION_PROPOSED`。
6. `narration_approve{actor(kp), proposal_id, decision:approve|edit|reject, edited_text?, diff?}` → 落 `NARRATION_APPROVED|NARRATION_EDITED|NARRATION_REJECTED`。
7. `info_distribute{actor(kp), campaign_id, info_id, scope:public|whisper|condition, targets[], body_ref}` → 落 `INFO_REVEALED`（condition 由 VisibilityEngine 求值）。
8. `transcribe_audio{actor(kp), campaign_id, audio_ref, speaker?}` → `{ok, job_id}`；完成落 `TRANSCRIPT_READY`＋`TRANSCRIPT_APPENDED*`。
9. `image_generate{actor, card_id?, prompt, style?, engine?}` → `{ok, job_id}`；降级链 云API→兼容API→占位图；完成落 `PORTRAIT_READY{image_ref{file_url,prompt,engine,date}}`。
10. `map_command{actor, campaign_id, map_id, op:get|move|add_token|set_fog|set_status|set_light, target?, delta?}` → 读直接返；写走命令链＋KP 批准，落 `MAP_UPDATED`。
11. `summarize_session{actor(kp), campaign_id, anonymize?:bool}` → `{ok, job_id}`；完成落 `SESSION_SUMMARIZED{summary_ref,hooks[],next_preview}`。
12. `session_state{campaign_id}` → `{campaign_id, event_seq, projected_hash, pending_approvals[], turn_cursor}`（只读，不落事件）。
13. `job_get_status{actor, job_id}` → `{job_id, status:queued|running|done|failed, result_ref?}`；完成经 WS `JOB_STATUS` 回调。
— `npc_act` 任意调用 → `403 {error:"npc_forbidden"}`（未开闸）。

## 4. job 提交约定

- 长任务（8/9/11）同步返 `job_id`（`job_<campaign>_<seq>`），状态机 `queued→running→done|failed`；可选 `job_cancel`。
- 客户端用 `job_get_status` 轮询＋ WS `JOB_STATUS{scope=actor}` 推送；完成事件（TRANSCRIPT_READY／PORTRAIT_READY／SESSION_SUMMARIZED）写入事件流回查。
- `approve_wait_ms` 只在 turn 路径打点，不阻塞 job。

## 5. 自查清单（冻结核对）

- [x] 13 全名 `mcp__trpg__*` 齐全（含 session_state／job_get_status；npc_act 预留 403 另列）
- [x] 每工具 input/output 骨架齐
- [x] 权限三级（公开读／玩家写／KP 写＋agent 待批）与 04 §MCP 矩阵一致
- [x] job 规则（job_id 生成、queued/running/done/failed、回调映射）齐
- [x] 传输为 streamable-http 同 9210 端口（05-N1），stdio 仅备用
- [x] 无 AGPL 内容（ComfyUI/SD 只 HTTP 隔离引用名）
