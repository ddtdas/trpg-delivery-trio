# 前端运行契约（冻结件 ❄ v1.0 · 2026-09-19）

> 依据：04 事件协议（WS 协议消息帧／perf 打点）、build_plan_v1 §1/§2。
> 传输：单端口 `ws://127.0.0.1:9210/ws?table=<id>&viewer=<id>&role=kp|pl|spectator`；REST `/api/*` 查询降级；scope 一律后端计算，前端不可伪造。

## 1. Server→Client（8 类，全带 `seq,campaign_id,scope,ts`）

1. `STATE_DELTA{delta:{field,value}}` scope=viewer 可见子集。
2. `TURN_UPDATED{turn:{state:COLLECTING|CLOSING|RESOLVING|DISTRIBUTED|ADVANCED, submitted:[{player_id,intent}], total, countdown_end_ts}}`。
3. `NARRATION_PENDING{proposal:{id,text,intention?,source}}` scope=kp（仅 KP 连接推送）。
4. `NARRATION_APPROVED{narration:{id,text}}` scope=public。
5. `WHISPER{targets[], packet:{info_id,body}}` scope=whisper（只推目标连接；Hub 断言非目标帧绝无 body 字段）。
6. `INFO_REVEALED{packet:{info_id,body}}` scope=condition（条件满足才推）。
7. `BRANCH_TAKEN{branch:{node_id,label,consequences[]}}` scope=public。
8. `JOB_STATUS{actor_id, job:{job_id,status:queued|running|done|failed,result_ref?}}` scope=actor（只推提交者）。

## 2. Client→Server（6 类，全带 `campaign,actor{id,token?},req_id`）

1. `SUBMIT_ACTION{campaign,actor,action,intent}` → `ACTION_SUBMITTED`（窗口关闭后进补交 LATE／PENDING_APPROVAL）。
2. `START_TURN{campaign,actor(kp),window_sec}` → `TURN_STARTED`。
3. `CLOSE_WINDOW{campaign,actor(kp)}` → `TURN_CLOSED{submit_map,order[]}`。
4. `APPROVE_NARRATION{campaign,actor(kp),proposal_id,decision:approve|edit|reject,edited_text?}` → 批准三事件之一。
5. `COMMAND{campaign,actor,cmd:{type:roll_check|map|quick,payload}}` → 检定／地图走命令链（地图写须 KP 批准）。
6. `AUDIO_CHUNK{campaign,player_id,mime:audio/opus,chunk_base64,seq}` → 服务端组帧转写；失败可 REST 批量导入补。

## 3. perf 五字段（随事件附加，落 `perf_metrics` 独表，不混事件流）

- `vad_ms`（voice/pipeline 端点）／`stt_ms`（voice→文本段）／`llm_first_token_ms`（agent/gateway 首 token）／`tts_first_packet_ms`（voice/tts_out 首包）／`approve_wait_ms`（agent/approvals，仅 turn 路径）。
- 派生：`voice_loop = vad+stt+llm_first+tts_first`（目标 1.0–1.3s，硬限 1.6s）；`turn_settlement` 另计软目标。
- 查询：`GET /api/metrics/latency?campaign=<id>&n=100` → `{mean,p95,segments:{5 段},n}`；仪表盘最近 100 条均值＋P95＋五段分解条。

## 4. 心跳／重连／降级

- 心跳：server 每 15s `PING{ts}`；client 30s 无帧主动重连（指数退避 1/2/4/8s，上限 30s），重连带 `last_seq`；server 重放 `last_seq+1..tip` 的可见子集（按 viewer 过滤）。
- 断线提交：重连后先调 `session_state` 对账再补交；窗口已关进 LATE 队列待 KP 批。
- 降级：WS 不可用时 REST 轮询 `GET /api/state?since=<seq>`（2s 一次）；纯文字模式关闭音频帧。

## 5. 自查清单

- [x] S→C 8 类全字段齐（含 scope 语义＋WHISPER 非目标无 body 断言）
- [x] C→S 6 类全字段齐（含 req_id 幂等＋LATE 补交）
- [x] perf 五字段＋派生＋查询接口齐
- [x] 心跳 15s／重连退避／last_seq 重放／REST 降级齐
- [x] 无 AGPL 内容
