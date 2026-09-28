# MINIPROGRAM.md —— 微信小程序玩家端

> 状态：**骨架**（T7 阶段定稿）。标 `【待回填】` 的条目在 T4/T5/T6 完成后替换为实测值。
> 一致性依据：`CROSS-END-CONTRACT.md` **v1.4（冻结）** —— §1 端点、§2 设计令牌、§3 WS 规则、
> §4 功能清单、§5 固定文案、§7 风险。**已冻结，不得偏离**。
> 本端与 `PLAYER-WEB.md` 描述的浏览器端**功能集合与文案逐字相同**。

---

## 1. 定位

- 玩家端 **微信小程序版**，直连主持端服务器 `9210` 的 `/access/*`、`/api/campaigns/{c}/events` 与 `/ws`。
- **不使用任何中转网关**：交付物中不得存在 9321 中转服务，代码中不得出现 `9321` 引用。
- 无 npm 依赖，导入微信开发者工具即可运行。

## 2. 文件结构（`clients/miniprogram/`）

```
clients/miniprogram/
  app.js / app.json / app.wxss          小程序入口与全局样式
  project.config.json                   项目配置（开发者工具识别）
  project.private.config.json           私有配置
  sitemap.json                          索引配置
  lib/
    config-store.js                     服务器地址 / 连接码 / 玩家身份本地存储
    api-client.js                       /access/* 与 /api/* 请求封装（Bearer 鉴权、两种响应口径）
    ws-client.js                        /ws 连接、退避重连、last_seq 对账（可选增强通道）
    req-id.js                           req_id 生成（幂等）
  pages/
    setup/                              连接设置
    table/                              桌面
    voice/                              语音
  tokens.wxss                           设计令牌（与契约 §2 逐值一致）
  strings.json                          固定文案（与契约 §5.1 / §5.2 逐值一致）
  tests/contract.test.js                契约自测（node 直接跑）
  README.md                             本端说明
```

## 3. 导入与运行

1. 打开 **微信开发者工具** → 导入项目。
2. 目录选择 `clients/miniprogram`。
3. AppID：可用「测试号」或填自有 AppID。
4. 详情 → 本地设置 → 勾选 **不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书**（局域网 `http://` 直连必须）。
5. 编译后进入「连接设置」页，填入服务器地址、连接码、玩家 ID 与 **mobile 端 token** → 「测试连接」。

## 4. 鉴权

- 所有 `/access/*` 请求携带 `Authorization: Bearer <mobile token>`。
- token 在设置页填写并本地保存（`wx.setStorageSync`），**不硬编码、不写日志**。
- 三端 token 定义见 `DEPLOY.md` 第 5 节；`recorder` token 绝不用于客户端。
- **未启用端一律 401**（即使带了 token）。
- 鉴权矩阵（契约 §1.6）：`/access/table/resolve` 任意启用端 200；`POST /access/player/audio` 仅 mobile 端 200，
  webapp / recorder → **403 mobile_only**（不是 401）。

## 5. 合法域名

| 模式 | 配置位置 | 说明 |
|---|---|---|
| 开发 / 演示 | 开发者工具 → 详情 → 本地设置 → 不校验合法域名 | 可用 `http://192.168.10.110:9210` |
| 生产 | 小程序后台 → 开发 → 开发设置 → 服务器域名 | 需 `https://` + 已备案域名 |

生产必须同时配置两类域名：

- **request 合法域名**：`https://<你的域名>`（`wx.request` / `wx.uploadFile`）
- **socket 合法域名**：`https://<你的域名>`（`wx.connectSocket`，注意这里是 `https` 写法）

> 若公网入口启用 Cloudflare Access，小程序 `wx.request` 不会带浏览器会话，
> 需改用 **Service Token**（`CF-Access-Client-Id` / `CF-Access-Client-Secret`），
> 或让小程序走局域网/内网。详见 `DEPLOY.md` §6.3.5.2。

【待回填：AC-4 第 18 条 —— 两种模式配置步骤截图与说明落盘路径】

## 6. 权限声明

- 语音录制需在 `app.json` 声明 `scope.record` 及用途说明（`permission` / `requiredPrivateInfos` 按微信最新规范）。
- 首次录音时微信会弹窗申请麦克风权限；用户拒绝后需引导到设置页重新授权。

【待回填：T4 实际 `app.json` 权限声明片段】

## 7. 功能清单（与浏览器端逐项相同）

| # | 名称 | 交互 | 端点 / 通道 |
|---|---|---|---|
| F1 | 服务器连接 | 地址输入 + 「测试连接」 | `GET /access/info` |
| F2 | 连接码 | 输入 → 「解析」→ 显示桌名 / 战役 | `GET /access/table/resolve` |
| F3 | 玩家身份 | 玩家 ID + 昵称，本地保存 | wx storage |
| F4 | 加入桌面 | 「加入跑团」→ 桌面页 | 组合 F1 + F2 |
| F5 | 回合状态 | `turn_no / state / 已提交数`，15s 兜底轮询（实时性由 WS 推送驱动） | `GET /access/mobile/state` |
| F6 | 行动提交 | 仅 `COLLECTING` 可提交；`req_id` 幂等 | `POST /access/mobile/action` |
| F7 | 事件流 | 最近 **50** 条 | **`GET /api/campaigns/{c}/events`（主通道；首次 `limit=1000` 取最新 50，增量 `limit=50` + 拉满续拉）** + WS 帧（可选合并） |
| F8 | 语音录制上传 | `wx.getRecorderManager()` → `wx.uploadFile` | `POST /access/player/audio` |
| F9 | 设备状态（只读） | 输入 `device_id` → 「查询」 | `GET /access/device/status` |
| F10 | 连接状态与对账 | 状态行（四态由轮询驱动，**WS 状态不得产生可见文案**）+ 退避重连 + `last_seq` 补齐 | /access/info + 事件流 + WS（可选） |
| F11 | 骰点托盘 | **两端都不提供**（延期） | — |
| F12 | 玩家私语 | **两端都不提供**（延期） | — |

> **玩家端不得调用**：`/access/advice`、`/access/nl`、`/access/voice/register`、`/access/voice/transcript`、
> `/access/audio_upload`、`POST /access/device/status`、`/access/host/*`、`/mcp/*`，
> 以及 `/api/*`（**唯一例外**是 `/api/campaigns/{c}/events`）。

### 7.1 事件通道（★ 与 PC 端逐字一致）

**主通道 = REST 轮询（必须实现）**：

```
GET /api/campaigns/{campaign}/events?since=<last_seq>&limit=50&token=<mobile token>    # 增量
GET /api/campaigns/{campaign}/events?since=-1&limit=1000&token=<mobile token>        # 首次
```

- **必须带查询参数 `?token=<mobile token>`**（契约 **v1.12** §4.1 F7，**首次与增量都要带**）：服务端**当前不校验**，带上是无害的。
  ⚠️ **`Authorization: Bearer` 头不构成等价替代** —— 该端点若服务端将来只读 query 参数，头不会被识别。
  **只带 header、不带 `?token=` = 未满足本条**（parity 组 (j) 会判 FAIL；小程序侧 `lib/api-client.js` 目前只带 header，需补 query 参数）。
- **取数口径（契约 v1.12 §3.4.1，队长裁决 v1.10 生效）**：
  - **首次**：`since=-1&limit=1000&token=<mobile>`（服务端上限 1000）→ 按 `seq` 取**最新 50 条** → **降序**渲染；
    ⚠️ 陷阱：`since=-1&limit=50` 返回的是**最旧** 50 条，不是最新（服务端按 seq 升序取前 limit 条）。
    （🚫 做法 (b) 已于 v1.24 **正式废弃、不得采用**：`since` 是 seq 阈值而非条数，单团 seq 稀疏时会严重少返回。）
  - **增量**：`since=<本地 last_seq>&limit=50&token=<mobile>` → 新事件插入顶部（保持降序）。
  - **排空规则**：**某次返回条数 == 50（拉满）时，立即用推进后的游标续拉，最多 3 轮**。
- 每 **15s** 一次（兜底）；收到 WS 帧即立即再拉一次；提交行动后立即再拉一次。
- **解析口径**：`/api/*` 层**不使用** `/access/*` 的 `ok/data` 包裹 —— 成功读 `events` / `tip`，失败读 `detail`。
  小程序侧 `api-client.js` 必须区分这两种口径，否则事件流永远为空。
- **必须按可见性过滤**（契约 R1）：服务端返回全部事件，客户端只显示 `scope=public`、
  或 `targets` 含本人、或 `condition_met` 的事件。

**增强通道 = WS 广播（可选，不得成为依赖）**：

```
ws://<host>:9210/ws?table=<table_id>&viewer=<player_id>&role=pl&last_seq=<int>&token=<mobile token>
```

- **WS 路径恒为 `/ws`**；`info.data.ws` 的值 `"/access/ws"` 只是**说明端点**，**禁止**作为连接地址
  （`wx.connectSocket({url: base + info.data.ws})` 会失败）。
- ⚠️ **鉴权/参数失败的可观测形态是「握手阶段 HTTP 403」**，**永远收不到 4400 关闭码**；
  四种情形（无 token / role 非法 / 缺 table / token 错误）实测**全部 403**。
- **静默降级**：连不上 / 403 / 断开 → 只走轮询，**不得报错、不得阻塞 UI、不得改变文案**。
- 已知 kind 的 8 类下行帧 → 合并进事件流，**按 seq 去重**（**同一 seq 以轮询结果为准，REST 胜出**）；`PING` 只刷新心跳；`ACK` / `ERROR` / 未知 kind **忽略**。

**心跳与重连**：

- 心跳以**服务端 PING 到达**为准（每 15s）。小程序上行 PING 被静默忽略且**无 PONG**。
- **距上次收到服务端帧（含 PING）超过 30s ⇒ 判定断线并重连**。
- 退避 **1 / 2 / 4 / 8s，上限 30s**；重连带 `last_seq`；恢复后按 `since=last_seq` 补齐。

### 7.2 三个命名空间（**铁律**）

| # | 命名空间 | 字段名 | 玩家端 |
|---|---|---|---|
| A | WS 帧 kind | `kind` | 可选使用 |
| B | 事件流 type | `type` | **是（F7）** |
| C | agent EventKind | `kind`（小写） | **否，不得出现** |

### 7.3 与浏览器端的关键对齐点

| 项 | 规则（两端一致） |
|---|---|
| 录音上传 | 表单字段 `name=file`，`formData: { campaign, kind: 'voice', player_id }` |
| last_seq 存储键 | `trpg_last_seq_<table>`（小程序用 `wx.setStorageSync('trpg_last_seq_'+table, seq)`） |
| 退避重连 | 1 / 2 / 4 / 8s，上限 30s |
| 行动门控 | 只有 `COLLECTING` 可提交；其余状态原样显示字符串（契约 R2） |
| F9 无记录 | 404 → `无该设备记录` |
| URL 预填 | 小程序**不支持**（无等价物，契约明示不作为功能差异） |
| 文案 | 逐字取自契约 §5.1 / §5.2，两端相同 |

## 8. 自测

```powershell
# 1) 契约单测（Node 直接跑，无需开发者工具）
node clients/miniprogram/tests/contract.test.js

# 2) 语法自检
Get-ChildItem -Recurse clients/miniprogram -Include *.js | ForEach-Object { node --check $_.FullName }
Get-ChildItem -Recurse clients/miniprogram -Include *.json | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json | Out-Null; "ok $($_.Name)" }

# 3) 事件流主通道直打（F7）
Invoke-RestMethod "http://192.168.10.110:9210/api/campaigns/<campaign>/events?since=-1&limit=1000&token=<mobile token>"   # 首次
Invoke-RestMethod "http://192.168.10.110:9210/api/campaigns/<campaign>/events?since=0&limit=50&token=<mobile token>"          # 增量
```

【待回填：T4 自测证据 `evidence/T4-mp.txt`；微信开发者工具是否可用（若不可用需如实标注「无法工具验证」）】

## 9. 发布流程（如需正式上线）

1. 服务端具备 **HTTPS + 已备案域名**（见 `DEPLOY.md` §6.3 / §7）。
2. 小程序后台配置 request / socket 合法域名。
3. 关闭「不校验合法域名」开关，真机预览确认可用。
4. 上传代码 → 提交审核 → 发布。

## 10. 常见问题

| 现象 | 原因 | 处置 |
|---|---|---|
| 请求被拦截 / `url not in domain list` | 合法域名未配置 | 开发模式勾选「不校验合法域名」，或按第 5 节配置 |
| WS 连不上 | 只配了 request 域名 / 路径用了 `info.ws` | 补配 **socket 合法域名**；路径恒为 `/ws` |
| WS 握手 403 | token / role / table 参数错 | 属预期可观测形态；自动降级到轮询，不影响功能 |
| 事件流一直为空 | `api-client.js` 按 `ok/data` 解析了 `/api/*` | 见 §7.1：`/api/*` 用 `events`/`detail` 口径 |
| 录音报错 | 未声明 `scope.record` 或用户拒绝授权 | 见第 6 节 |
| 真机可用、模拟器不可用（或反之） | 网络环境不同 | 模拟器走本机网络；真机需与服务器同网段或走公网 |
| 页面文案与 PC 端不一致 | 偏离契约 §5 | 以 `CROSS-END-CONTRACT.md` 为准修正，重跑 parity 检查 |
| 出现 9321 相关报错 | 残留旧网关代码 | 本端不得引用 9321，属缺陷，须修复 |
