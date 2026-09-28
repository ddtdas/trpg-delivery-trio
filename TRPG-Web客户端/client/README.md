# TRPG 跑团玩家端（PC / 移动浏览器版）

零构建、零 npm 依赖、无 CDN 外链的玩家端页面。整目录直接拷贝到服务端
`server/player-web/` 后由 `GET /player/` 托管，浏览器打开即用。

实现依据：`docs/CROSS-END-CONTRACT.md` **v1.1**（T1 定稿冻结）。

## 文件

| 文件 | 作用 |
|---|---|
| `index.html` | 三视图骨架（连接设置 / 桌面 / 语音），仅引用本地 `app.css`、`app.js` |
| `app.css` | 设计令牌（CSS 变量）+ 契约 §2 组件语义类名 |
| `app.js` | 全部逻辑：F1–F10、事件流、15s 兜底轮询、WS（可选）、录音上传、**R10/R11 地点交互面板**（本轮新增） |
| `tokens.json` | 设计令牌机器可读副本（逐值等于契约 §2） |
| `strings.json` | 固定文案表（逐字等于契约 §5.1 + §5.2，另含 `ext.*` 扩展文案） |
| `README.md` | 本文件 |

## 部署

1. 把本目录内容拷到服务端 `server/player-web/`（服务端 `/player/` 静态托管该目录）。
2. 浏览器打开 `http://<服务器地址>:9210/player/`。
3. 在「连接设置」填写：服务器地址（默认取当前页面 origin）、mobile 端访问 token、
   连接码、玩家 ID、昵称 → 「测试连接」→「解析连接码」→「加入跑团」。

也支持 URL 预填：`/player/?server=http://192.168.10.110:9210&code=TABLE-0001&pid=pl-001&token=<mobile token>`。

## 接入端点（契约 §1.1：玩家端只允许用这些）

| 用途 | 请求 | 鉴权 |
|---|---|---|
| 服务信息（F1） | `GET /access/info` | 任意启用端 token |
| 连接码解析（F2） | `GET /access/table/resolve?code=` | 任意启用端 token |
| 会话状态（F5） | `GET /access/mobile/state?table_id=` | mobile 端 token |
| 提交行动（F6） | `POST /access/mobile/action` | mobile 端 token |
| 玩家录音上传（F8） | `POST /access/player/audio`（multipart） | mobile 端 token |
| 设备状态（F9） | `GET /access/device/status?device_id=` | 任意启用端 token |
| **事件流（F7 主通道）** | `GET /api/campaigns/{campaign}/events?since=&limit=` | 无（`/api` 口径） |
| 实时订阅（可选增强） | `WS /ws?table=&viewer=&role=pl&last_seq=&token=` | 任一启用端 token |
| **场景交互物（R10）** | `GET /api/campaigns/{campaign}/interactives?viewer=<playerId>` | mobile 端 token |
| **提交交互（R10/R11）** | `POST /api/campaigns/{campaign}/interact` | mobile 端 token |
| **我的交互状态** | `GET /api/campaigns/{campaign}/pipeline/mine?player_id=` | mobile 端 token |

- `/access/*` 响应包裹：成功 `{ok:true,data,code:0}`，失败 `{ok:false,error,code}`。
- `/api/*` 不使用该包裹：成功直接读 `events`/`tip`，失败读 `detail`。
- REST 请求带 `Authorization: Bearer <mobile token>`；WS 因浏览器限制以 `?token=` 传递。
- **WS 地址是 `/ws`**，不是 `/access/info` 的 `data.ws`（`/access/ws` 只是使用说明文档端点，契约 §1.4）。

## 功能清单（与小程序端逐项相同）

F1 服务器连接、F2 连接码、F3 玩家身份（本地保存）、F4 加入桌面、F5 回合状态（15s 兜底轮询；实时性由 WS 推送驱动）、
F6 行动提交（仅 COLLECTING 可提交 + req_id 幂等）、F7 事件流（最近 50 条）、
F8 语音录制与上传、F9 设备状态（只读）、F10 连接状态与对账。

契约 §4 中标注为延期、两端一致地不提供的两项，本页面同样不实现（延期原因与范围见 `docs/ROADMAP-DEFERRED.md`，按契约 §6.1-1 不在客户端 README 展开）。

## R10/R11 地点交互面板（本轮新增，additive）

- **入口**：加入桌面后在「桌面」视图底部自动渲染一块「地点交互」卡片（纯 JS 注入 DOM，**不改 `index.html` / `app.css`**，因此镜像面只有 `app.js`）。
- **数据来源**：`GET /api/campaigns/{campaign}/interactives?viewer=<playerId>` —— 房间、可交互物、**热区锚点 `anchor{x,y}`** 与**动作集**全部由服务端下发（前端不硬编码场景、不猜坐标）。
- **热区**：按房间矩形等比缩放到 `#ixMap` 区域内，点击热区即出现该物件的动作按钮（如「查看 / 搜索 / 撬锁（需报备）」）。
- **非敏感动作**：服务端直接返回检定结果（`{status:"ok", result:{level, rolled, success, text}}`），面板回显并进入事件流。
- **敏感动作**（`sensitive=true`）：**不直接生效**，返回 `{status:"pending_approval", proposal_id, state:"已上报待主持人"}` 并进入统一审批总线；
  面板底部「我的交互」持续展示 `已上报待主持人 / 主持人已允许 / 主持人暂未允许`，**主持人拍板前玩家侧看不到任何结果正文**。
- **拍板后**：结果经定向 whisper 下发，面板**无需刷新页面**即就地更新（WS 帧触发；2.5s 节流，本人有未决定报备时强制刷新以免漏帧）。
- 该面板不影响既有 15s 兜底轮询 / WS / 提交链路（全部为新增函数与 4 处单行钩子）。
- 本目录 `README.md` 与 `TRPG-Web客户端/client/README.md` **逐字节一致**（镜像不变量，5+1 文件同规则）。

## F7 事件流的实现口径

- 主通道是 REST 事件流（命名空间「事件流 type」），**不依赖 WS 下行帧**：WS 仅作**可选增强**（契约 §3.4.2）；
  **发布路径已生效**（T2 按队长裁决落地 additive 发布，实测可收到 `TURN_UPDATED` 等真实帧），
  但**轮询仍是完整性与兜底的权威来源**，WS 不可用时静默降级（§3.4.2）。
- **取数做法 (a)**（契约 §4.1 F7）：首次 `?since=-1&limit=1000`（服务端上限 1000）→ 客户端取**最新 50 条**；
  之后每 15s（兜底）用 `?since=<游标>&limit=50` 增量补齐（收到 WS 帧即立即再拉一次）；**任一请求拉满（条数 == limit）则用推进后的游标续拉，最多 3 轮**（防滞后、不丢事件）。
- **渲染顺序**：**seq 降序（最新在最上）**，展示最新 50 条。
- **游标权威**（契约 §3.4.2）：`last_seq` **只由轮询推进，绝不由 WS 帧推进**；WS 帧 `seq <= last_seq` 直接丢弃，
  `seq > last_seq` 渲染但不动游标（该 seq 随后由轮询再返回，按 **seq 去重**保证只渲染一次）。
- **请求一律带 `?token=<mobile token>`**（服务端当前忽略，属前向兼容：后续服务端给该端点加鉴权时两端无需改代码）。
- 类型标签取契约 §5.2 的 `ev.*` 映射；未知 type → `ev.OTHER` + 原始 type 文本。
- 正文提取规则**与小程序端 `lib/event-view.js` 逐条一致**：先按 type 特化
  （ACTION_SUBMITTED / TURN_STARTED / TURN_CLOSED / CHECK_RESOLVED / VOTE_CAST / ROLE_ASSIGNED /
  EVIDENCE_DEALT），再按通用字段路径
  `text → body → body_ref → label → message → summary → seg.text → action.text → next_preview →
  line → reason → ref → clue_id → transcript_ref → truth_tree_ref → summary_ref → role_ref →
  npc_id → op → level → status_text → info_id` 取第一个非空字符串，最后回退 `JSON.stringify(payload)`。
- 条目渲染：`.ev-kind` 类型标签 + `.ev-ts`「#seq HH:MM:SS」+ `.ev-text` 正文；按 **seq 降序（最新在最上）**，取**前** 50 条。
- WS 增强帧（可选）同样并入事件流，排在 REST 事件之后，正文用 `ext.ev.*` 模板
  （与小程序端 `lib/ws-client.js::frameText` 逐条一致）。
- **可见性过滤（契约 §7.2 R1，本轮升级为服务端裁剪）**：REST 事件流**已由服务端按 `viewer` 裁剪**（响应含 `filtered=true`），
  暗骰（`CHECK_RESOLVED` 归属 KP）与 KP-only 事件在非 KP 视图**整条不返回**；
  客户端保留 `payload.scope` / `targets` 二次过滤作为兜底 —— `payload.scope` 缺失或为 `public` 才默认可见，
  否则要求 `payload.targets` 含本人，或 `scope=condition` 且 `condition_met===true`。
- WS 作为可选增强：收到契约 §3.2 的 8 类已知帧即并入事件流；`PING` 只刷新心跳；
  `ACK`/`ERROR` 等未知 kind 一律忽略；WS 连不上不影响任何功能（契约 §3.1）。
- **WS 静默降级（契约 §3.4.2）**：连不上 / 握手 403 / 被拒 / 断开 → **不得报错、不得阻塞 UI、
  不得改变任何文案**。因此页面上的 F10 状态行**只由 REST 轮询驱动**（成功→已连接；
  连续失败 <3 次→重连中…；≥3 次→已断开），WS 的连接状态**只记在内存、不写任何可见文案**。
- **连接 WS 前先校验**（契约 §3.1）：加入桌面时先调用 `GET /access/info` 确认 token 与可达性，
  再解析连接码并连接 `/ws`；不依据 WS 关闭码/握手状态码做错误分类（任何失败的升级都归一 HTTP 403）。
- 固定文案与扩展文案表（`strings.json`，三端逐字节一致）与小程序端 `clients/miniprogram/strings.json`
  **键集合与取值完全相同**（0 差异）。

## 本地存储键

`trpg.playerId` / `trpg.playerName` / `trpg.server` / `trpg.code` / `trpg.token`，
以及对账游标 `trpg_last_seq_<table_id>`（键规则与小程序端相同；存的是事件流 seq 游标，
同时作为 WS 重连的 `last_seq`）。

## 重连策略（契约 §3.5）

指数退避 1/2/4/8 秒，上限 30 秒；重连请求携带 `last_seq`；30 秒无任何帧主动重连；
重连成功后用 `since=<游标>` 补齐事件流。状态行文案固定为 §5.1 的 `st.*` 四态。

心跳以**收到服务端 PING** 为准（服务端每 15s 下发一条 `{"kind":"PING"}`）；客户端**不上行 PING**
（服务端忽略上行 PING 且无 PONG 应答）。任何收到的帧（含 PING）都会刷新 `lastFrameTs`，
只有连续 30 秒收不到任何帧才主动重连。

## 浏览器兼容与降级

- 录音（F8）需要安全上下文：`https://` 或 `http://localhost` / `http://127.0.0.1`。
  在明文 HTTP 的局域网地址下 `navigator.mediaDevices` 不可用，页面会明确提示
  「当前环境不支持录音（需要 HTTPS/localhost 且设备有可用麦克风）」，其余功能不受影响。
- 无 `crypto.randomUUID()` 时回退为「时间戳 + 随机数」的 `req_id`。
- token 只存本地存储、只随请求发送，不硬编码、不写日志；recorder token 从不下发到玩家端。
