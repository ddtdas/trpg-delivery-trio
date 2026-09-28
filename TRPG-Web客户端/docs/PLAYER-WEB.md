# PLAYER-WEB.md —— PC / 移动浏览器玩家端

> 状态：**骨架**（T7 阶段定稿）。标 `【待回填】` 的条目在 T3/T5/T6 完成后替换为实测值。
> 一致性依据：`CROSS-END-CONTRACT.md` **v1.4（冻结）** —— §1 端点、§2 设计令牌、§3 WS 规则、
> §4 功能清单、§5 固定文案、§7 风险。**已冻结，不得偏离**。

---

## 1. 定位

- 玩家端 **浏览器版**，同时服务 PC 与手机浏览器（响应式，同一套代码）。
- **零构建**：纯原生 HTML/CSS/JS，无 npm 依赖、无打包步骤、无 CDN 外链。
- 由主持端服务端托管在 `/player/`，浏览器直开即用。
- 与微信小程序端 `clients/miniprogram/` **功能集合与视觉令牌完全相同**。

## 2. 文件结构（`clients/web-player/`）

```
clients/web-player/
  index.html     三视图（连接设置 / 桌面 / 语音），JS 切换
  app.css        设计令牌 + 组件语义类名（严格按契约 §2）
  app.js         全部逻辑
  tokens.json    设计令牌（与契约 §2 逐值一致）
  strings.json   固定文案（与契约 §5.1 / §5.2 逐值一致）
  README.md      本端说明
```

## 3. 部署

服务端从 `server/player-web/` 目录托管 `/player/`：

```powershell
# 方式一：交付包已内置（推荐）—— server/player-web/ 即为本端内容
# 方式二：从源码目录拷入
Copy-Item -Recurse -Force clients\web-player\* server\player-web\
```

> 交付包构建时由 `packaging/build-delivery.mjs` **自动**把 `clients/web-player/` 同步为
> 包内 `server/player-web/`（权威源），并断言 `index.html` 存在且非占位页。

## 4. 访问与 URL 预填

```
http://127.0.0.1:9210/player/                     本机
http://192.168.10.110:9210/player/                局域网
https://<公网域名>/player/                        经穿透/反代
```

支持 URL 预填（**仅 PC 端**；小程序无等价物，按契约不作为功能差异）：

```
/player/?server=http://192.168.10.110:9210&code=TABLE-XXXX&pid=pl-001&token=<mobile token>
```

## 5. 功能清单（F1–F10 全部实现；F11/F12 明确不做）

| # | 名称 | 交互 | 端点 / 通道 |
|---|---|---|---|
| F1 | 服务器连接 | 地址输入 + 「测试连接」，显示 version 与三端启用状态 | `GET /access/info` |
| F2 | 连接码 | 输入 → 「解析」→ 显示桌名 / 战役 | `GET /access/table/resolve` |
| F3 | 玩家身份 | 玩家 ID + 昵称，本地保存 | localStorage |
| F4 | 加入桌面 | 「加入跑团」→ 进入桌面视图 | 组合 F1 + F2 |
| F5 | 回合状态 | `turn_no / state / 已提交数`，15s 兜底轮询（实时性由 WS 推送驱动） | `GET /access/mobile/state` |
| F6 | 行动提交 | 仅 `turn.state === COLLECTING` 可提交；`req_id` 幂等 | `POST /access/mobile/action` |
| F7 | 事件流 | 最近 **50** 条（类型标签 + 文本 + 时间） | **`GET /api/campaigns/{c}/events`（主通道；首次 `limit=1000` 取最新 50，增量 `limit=50` + 拉满续拉）** + WS 帧（可选合并） |
| F8 | 语音录制上传 | 「开始录音 / 停止并上传」，显示 `bytes` / `file_ref` / `stt.status` | `POST /access/player/audio` |
| F9 | 设备状态（只读） | 输入 `device_id` → 「查询」 | `GET /access/device/status` |
| F10 | 连接状态与对账 | 状态行 连接中/已连接/重连中/已断开；断线自动补齐。**状态行四态由轮询驱动；WS 状态不得产生可见文案** | /access/info + 事件流 + WS（可选） |
| F11 | 骰点托盘 | **两端都不提供**（延期，见 `ROADMAP-DEFERRED.md`） | — |
| F12 | 玩家私语 | **两端都不提供**（延期，同上） | — |

> **玩家端不得调用**：`/access/advice`、`/access/nl`、`/access/voice/register`、`/access/voice/transcript`、
> `/access/audio_upload`、`POST /access/device/status`、`/access/host/*`、`/mcp/*`，
> 以及 `/api/*`（**唯一例外**是 `/api/campaigns/{c}/events`）。这些是 KP / recorder 端能力。

### 5.1 关键行为约定

- **行动门控**：**只有** `COLLECTING` 可提交；其余状态**原样显示 state 字符串**，不得因未知状态崩溃或隐藏状态行（契约 R2）。
- **幂等**：`req_id` 用 `crypto.randomUUID()`（不支持时回退「时间戳 + 随机」）；重复 → `重复提交已忽略`。
- **空校验**：行动描述为空 → `行动描述不能为空`，**不发请求**。
- **F5 空回合**：`turn == null` → 显示 `尚未开启回合`。
- **F9 无记录**：404 → 显示 `无该设备记录`。
- **F2 不存在**：`exists:false` → 显示 `连接码不存在`（**不是**网络错误）。
- **F1 失败**：401 → `身份验证失败：token 无效或未启用该端`；网络失败 → `网络连接失败，请检查服务器地址与网络`。

### 5.2 本地存储键

| 键 | 内容 |
|---|---|
| `trpg.playerId` | 玩家 ID |
| `trpg.playerName` | 昵称 |
| `trpg.server` | 服务器地址 |
| `trpg.code` | 连接码 |
| `trpg.token` | mobile 端 token |
| `trpg_last_seq_<table>` | 事件对账水位（与小程序端键规则相同） |

> `token` 为本地保存的玩家凭据，**不得写入日志、不得回显到页面**。

## 6. 事件通道（★ 主通道是 REST 轮询，WS 只是可选增强）

> 契约 §3.4 明确：**F7 的主通道恒为 REST 轮询**，WS 广播是**可选增强**，**不得成为依赖**。

### 6.1 主通道：REST 轮询（**必须实现**）

```
GET /api/campaigns/{campaign}/events?since=<last_seq>&limit=50&token=<mobile token>   # 增量
GET /api/campaigns/{campaign}/events?since=-1&limit=1000&token=<mobile token>       # 首次
```

- 每 **15s** 一次（兜底）；收到 WS 帧即**立即**再拉一次；提交行动后**立即**再拉一次。
- **必须带查询参数 `?token=<mobile token>`**（契约 **v1.12** §4.1 F7 前向兼容要求，**首次与增量都要带**）：
  服务端**当前不校验**该参数，但带上是无害的；这样后续服务端加鉴权/可见性过滤时是**纯 additive 变更**，客户端无需改代码。
  ⚠️ **`Authorization: Bearer` 头不构成等价替代** —— 该端点若服务端将来只读 query 参数，头不会被识别。
  **只带 header、不带 `?token=` = 未满足本条**（parity 会判 FAIL）。其余 `/access/*` 端点两者仍等价。
- **取数口径（契约 v1.12 §3.4.1，队长裁决 v1.10 生效）**：
  - **首次**：`since=-1&limit=1000&token=<mobile>`（服务端上限 1000）→ 客户端按 `seq` 取**最新 50 条** → **降序**渲染；
    ⚠️ 陷阱：`since=-1&limit=50` 返回的是**最旧**的 50 条，不是最新的（服务端按 seq 升序取前 limit 条）。
    （🚫 做法 (b) 已于 v1.24 **正式废弃、不得采用**：`since` 是 seq 阈值而非条数，单团 seq 稀疏时会严重少返回。）
  - **增量**：`since=<本地 last_seq>&limit=50&token=<mobile>` → 新事件**插入顶部**（保持降序）。
  - **排空规则**：**某次返回条数 == 50（拉满）时，立即用推进后的游标续拉，最多 3 轮**（防滞后、不丢事件）。
- **解析口径注意**：`/api/*` 层**不使用** `/access/*` 的统一包裹。
  成功直接读 `events` 与 `tip`；失败读 `detail`（4xx/422）。**不要**按 `ok/data` 解析。
- **必须按可见性过滤**（契约 R1）：该端点返回**全部**事件，服务端不做 viewer 过滤。
  客户端只显示 `scope=public`、或 `targets` 含本人、或 `condition_met` 的事件。
- 无论 WS 是否可用，该轮询**都必须实现** —— 它是功能可用的基线。

### 6.2 增强通道：WS 广播（可选接入）

```
ws://<host>:9210/ws?table=<table_id>&viewer=<player_id>&role=pl&last_seq=<int>&token=<mobile token>
```

- **WS 路径恒为 `/ws`。**
- ⚠️ **陷阱**：`GET /access/info` 返回的 `data.ws` 值是字符串 `"/access/ws"`，
  但它**只是返回 WS 使用说明的 GET 文档端点，不是 WebSocket 地址**。
  **禁止** `new WebSocket(base + info.data.ws)` —— 那样握手必然失败。
- ⚠️ **鉴权/参数失败的可观测形态是「握手阶段 HTTP 403」**（空 body、`Connection: close`）。
  服务端在 `accept()` **之前**就 `close(4400)`，连接从未升级为 WebSocket，
  因此客户端**永远收不到 4400 关闭码**。实测四种情形（无 token / role 非法 / 缺 table / token 错误）
  **全部为 HTTP 403**，无差异。
  → **不要**依赖 WS 关闭码做错误分类；**先用 F1 的 `/access/info` 校验 token 与可达性**，再尝试 WS。
- **静默降级**：连不上 / 403 / 被拒 / 断开 → 只走 §6.1 轮询，**不得报错、不得阻塞 UI、不得改变任何文案**。
- 收到**已知 kind**（8 类下行帧）→ 合并渲染进事件流，**按 seq 去重**；**同一 seq 以轮询结果为准（REST 胜出，与到达顺序无关）**。
- 收到 `PING` → 只刷新心跳，**不进事件列表**。
- 收到 `ACK` / `ERROR` / 未知 kind → **忽略**（不崩溃、不写入事件列表）。
- WS 恢复后**不得**重复渲染已显示的 seq（以本地 `last_seq` 为准）。

### 6.3 心跳与重连

- 心跳以**服务端 PING 到达**为准：服务端每 **15s** 下发 `{"kind":"PING","ts":<int>}`。
- 客户端上行 `{"kind":"PING"}` 会被服务端**静默忽略且不回 PONG** —— **不得**用「发 PING 等 PONG」判存活。
- 判据恒为：**距上次收到服务端帧（含 PING）超过 30s ⇒ 判定断线并重连**。
- 重连退避：**1 / 2 / 4 / 8s，上限 30s**；重连时带上 `last_seq`；重连成功后按 `since=last_seq` 补齐，无重复、无丢失。

## 7. 三个命名空间（**铁律，勿混用**）

| # | 命名空间 | 字段名 | 取值示例 | 玩家端 |
|---|---|---|---|---|
| A | WS 帧 kind | `kind` | STATE_DELTA / PING / ACK / ERROR | 可选使用 |
| B | 事件流 type | `type` | ACTION_SUBMITTED / NARRATION_APPROVED / TRANSCRIPT_APPENDED | **是（F7）** |
| C | agent EventKind | `kind`（小写） | say / act / roll / clue … | **否，不得出现** |

- WS 帧字段名是 `kind`，**不是** `type`；事件流字段名是 `type`，**不是** `kind`。
- 命名空间 C **不得出现在玩家端任何代码或文案里**。

## 8. 响应式与可访问性

| 项 | PC | 移动端 |
|---|---|---|
| 容器 | 居中，`max-width: 560px` | 100% 宽 |
| 导航 | 顶部 tab | 底部 tabBar（`navHeight=48px`） |
| 触摸目标 | 可点元素 `min-height ≥ 44px` | 同左 |
| 功能集合 | 完全相同 | 完全相同 |

【待回填：T3 实测截图 —— 1440x900 与 390x844 两种视口；证据路径 `evidence/T3-web.txt`】

## 9. 自测步骤

```powershell
# 1) 页面可打开
(Invoke-WebRequest http://127.0.0.1:9210/player/ -UseBasicParsing).StatusCode    # 期望 200

# 2) 连通性（F1）
Invoke-RestMethod "http://127.0.0.1:9210/access/info?token=<mobile token>"

# 3) 连接码解析（F2）
Invoke-RestMethod "http://127.0.0.1:9210/access/table/resolve?code=<code>&token=<mobile token>"

# 4) 回合状态（F5）
Invoke-RestMethod "http://127.0.0.1:9210/access/mobile/state?table_id=<table>&token=<mobile token>"

# 5) 事件流主通道（F7）—— 注意 /api/* 不用 ok/data 包裹
Invoke-RestMethod "http://127.0.0.1:9210/api/campaigns/<campaign>/events?since=-1&limit=1000&token=<mobile token>"   # 首次（取最新 50）
Invoke-RestMethod "http://127.0.0.1:9210/api/campaigns/<campaign>/events?since=0&limit=50&token=<mobile token>"     # 增量
```

浏览器侧另需人工确认：测试连接成功、加入桌面、提交行动、事件流刷新、录音上传、断网重连。

【待回填：T3 自测证据（`evidence/T3-web.txt`）与 T6 端到端结论（`evidence/T6-acceptance.md`）】

## 10. 常见问题

| 现象 | 原因 | 处置 |
|---|---|---|
| 页面打不开（404 `player_not_built`） | `server/player-web/` 为空 | 见第 3 节拷入文件 |
| 「测试连接」失败 | 服务器地址错 / 未启动 / token 无效 | 先 `/api/health`，再核对 token |
| 提示 `身份验证失败：token 无效或未启用该端` | token 非 mobile 端或未启用 | 用 `access_config.yaml` 的 mobile token |
| 提交按钮一直禁用 | 未开回合（非 COLLECTING） | 主持端开启行动窗口 |
| 事件流一直为空 | 未走 REST 轮询 / `since` 传错 | F7 主通道是轮询，检查 `/api/campaigns/{c}/events` |
| 事件流出现不该看到的事件 | 未按 §6.1 做可见性过滤（契约 R1） | 按 scope / targets / condition_met 过滤 |
| WS 连不上（403） | 路径错（用了 `info.ws`）或 token/参数错 | 路径恒为 `/ws`；403 属预期可观测形态，自动降级到轮询即可 |
| 录音无反应 | 浏览器未授权麦克风 / 非安全上下文 | 允许麦克风；非 `localhost` 的 `http://` 页面 `getUserMedia` 受限，需 HTTPS |
| 出现「重复提交已忽略」 | `req_id` 重复 | 正常幂等行为，非故障 |
