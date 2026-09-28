# TRPG 跑团玩家端（微信小程序）

微信小程序玩家端 **直连主持端服务器**（FastAPI，默认端口 9210）的 `/access/*` + `/ws` +
`/api/campaigns/{c}/events` 契约，不经过任何玩家端中转服务。主持端仍是回合与判定的唯一权威；
小程序只持有 **mobile 端 token**，不持有主持端（webapp）或录音端（recorder）凭据。

实现依据：`docs/CROSS-END-CONTRACT.md`（v1.7 冻结；本端自检脚本直接解析该文件，令牌/文案逐值比对）。

## 一、导入与运行

### 1.1 两种导入方式（都不需要真实 AppID）

`project.config.json` 内为 `"appid": "touristappid"` —— 这是微信开发者工具的**官方游客 AppID**（无 AppID 模式）。
导入时按下面**任一种**方式操作都可以：

**方式 A：游客模式 / 无 AppID（最省事，推荐）**
1. 打开「微信开发者工具」→ 首页选 **导入项目**（不是「新建项目」）。
2. **目录**：选择本目录 `clients/miniprogram`（`project.config.json` 与 `app.json` 就在这一层）。
3. **AppID**：保持工具读到的 `touristappid`，或选择「**无 AppID / 游客模式**」。
4. 后端服务选「**不使用云服务**」→ 点「导入」→ 工具直接编译并进入模拟器。

**方式 B：测试号（需要扫码登录，但功能最完整）**
1. 同样走「导入项目」→ 选目录 `clients/miniprogram`。
2. **AppID** 右侧点「**测试号**」→ 工具会申请一个测试号并自动写入（无需自己注册小程序）。
3. 后端服务选「**不使用云服务**」→ 点「导入」。
   > 测试号方式还能额外使用「真机预览 / 真机调试」（需手机扫码）。

**两种方式共同的两步**
5. 首次编译后进入「连接设置」页；在**详情 → 本地设置**中勾选
   「不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书」，即可直连 `http://<IP>:9210`。
6. **本项目不需要真实 AppID 即可运行全部功能**：F1–F10 只用 `wx.request` / `wx.connectSocket` /
   `wx.getRecorderManager` / `wx.uploadFile` 与本地 storage，不依赖云开发、不依赖任何 npm 包。

> 若导入时工具仍弹窗要求填 AppID：选「测试号」或留空即可，**不要**填真实 AppID。
> （把 `appid` 改成空字符串 `""` 也能跑，但导入对话框会要求你手动再选一次「测试号」，故本交付保留官方游客值。）

### 1.2 命令行（CLI）的已知限制

本机已安装 `C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat`，但 `cli open / cli preview / cli auto`
在**未登录**状态下**必定失败**，与 `appid` 取值无关 —— 实测记录：

| 命令 | 结果 |
|---|---|
| `cli.bat islogin` | `{"login":false}` |
| `cli.bat open --project <本目录>`（appid=`touristappid`） | `code 10: 不存在此 AppID 请检查后重新输入` |
| `cli.bat open --project <本目录>`（appid=`""`） | 同上（`code 10`） |
| `cli.bat open --project <本目录> --appid touristappid` | 同上（`code 10`） |
| `cli.bat auto --project <本目录> --auto-port 9420` | 失败（同样要求登录态） |

结论：**CLI 会拿 AppID 去微信服务器校验，未登录时任何 AppID（含空值、游客值）都判为「不存在」**。
因此本端不使用 CLI 做编译验证，改为 **GUI 导入（1.1 步骤）+ 项目内静态自检 + 真实服务端直连实测** 三重替代，
未伪造任何编译截图（本会话无交互桌面，`CopyFromScreen` 报「句柄无效」）。
需要 CLI 自动化（`preview`/`upload`/真机调试）时，必须先 `cli.bat login` 扫码登录并改用你自己的真实 AppID。

### 1.3 生产发布（可选）

微信公众平台 → 开发 → 开发设置 → 服务器域名，把主持端 **HTTPS** 域名加入
   `request 合法域名` 与 `socket 合法域名`（`wss://` 同域）。

### 1.4 连接设置页填写

- **服务器地址**：`http://<主持端局域网 IP>:9210`（走公网穿透时填对应的 `https://` 地址）。
  ⚠ **该字段默认留空、不预填任何地址**（交付给他人时不携带本环境信息），必须由使用者填写；
  输入框里的示例（`ph.server`）只是占位提示，不是默认值。
- **mobile token**：主持端 `configs/access_config.yaml` 中 `ends.mobile.token`
- **连接码 / 玩家 ID / 昵称**

填好后依次点「测试连接」→「解析连接码」→「加入跑团」。

> 三页导航为**底部 tabBar**（连接设置 / 桌面 / 语音），高度令牌 `navHeight=48px`；
> PC 端为顶部 tab。这是契约 §2 允许的**唯一导航形态差异**，功能集合两端完全相同。

## 二、直连契约（与 PC 玩家端完全一致）

| 用途 | 方法 + 路径 | 鉴权 |
|---|---|---|
| F1 服务信息 | `GET /access/info` | 任意启用端 token |
| F2 连接码解析 | `GET /access/table/resolve?code=` | 任意启用端 token |
| F5 会话状态 | `GET /access/mobile/state?table_id=` | mobile 端 token |
| F6 行动提交 | `POST /access/mobile/action` | mobile 端 token |
| F7 事件流（**主通道**） | `GET /api/campaigns/{campaign}/events?since=&limit=&token=` | 服务端当前不校验；**契约 v1.8 要求一律带上 `token`**（前向兼容，见下） |
| F7 实时订阅（可选增强） | `WS /ws?table=&viewer=&role=pl&last_seq=&token=` | 任意启用端 token |
| F8 玩家录音上传 | `POST /access/player/audio`（multipart） | mobile 端 token |
| F9 录音设备状态 | `GET /access/device/status?device_id=` | 任意启用端 token |

- 鉴权头：`Authorization: Bearer <mobile token>`（WS 用 `token` 查询参数）。
- `/access/*` 统一包裹：成功 `{ok:true,data,code:0}`；失败 `{ok:false,error,code:<http>}`。
- `/api/*` **不使用**该包裹：成功直接返回 `{events,tip}`，失败 `{detail:"…"}` + 4xx/422。
- **不得**把 `/access/info` 的 `data.ws`（值 `/access/ws`）当作 WebSocket 地址 —— 那是文档端点，
  真实 WS 路径是 `/ws`（契约 §1.4）。
- `last_seq` 持久化键：`trpg_last_seq_<table>`（与 PC 端 key 规则相同）。
- 断线退避：1s/2s/4s/8s… 上限 30s；30s 无帧主动重连；重连携带 `last_seq` 并用 `since=` 补齐。
- `PING`（15s 心跳）只刷新心跳，不进入事件列表；`ACK` / `ERROR` 等非 8 类下行帧一律静默忽略（契约 §3.3）。
- **F7 主通道恒为 REST 轮询**（兜底 15s + 收到 WS 帧即拉一次；提交后立即拉一次），WS 只是可选增强：连不上/握手 403/被拒/断开一律**静默降级** ——
  不报错、不阻塞 UI、**不改变任何可见文案**（WS 状态只记内存，不写页面）。收到已知 kind 才按 seq 去重合并渲染；ACK/ERROR/未知 kind 忽略。
- **状态行（F10）**：桌面页**只有一行**连接状态行，**四态只由轮询驱动**（与 PC 端 `app.js:348-353/679-684` 同语义）：
  请求成功 → `st.connected`；连续失败 **<3** 次 → `st.reconnecting`；连续失败 **≥3** 次 → `st.closed`；进入桌面页初值 `st.connecting`。
  WS 连不上/403/断开**不改变任何可见文案**（严格满足契约 §3.4.2 静默降级）。
- **连接 WS 前先用 `GET /access/info` 校验 token 与可达性**（契约 §3.1）；不得用 WS 关闭码/握手状态码做错误分类
  （4400 永不到达客户端，任何失败的升级都归一 HTTP 403，无法区分 token 错/参数错/路径错/网络故障）。
- **F7 取数规则（契约 §4.1 F7 / §3.4.1）**：**首次取数采用做法 (a)**：`since=-1&limit=1000` → 客户端按 seq 取**最新 50 条**（**未采用做法 (b)**，故无需另行声明 tip-50）；之后增量 `since=<本地 last_seq>&limit=50`，**返回满 50 则用推进后的游标续拉，最多 3 轮**。
  ⚠ 陷阱：`since=-1&limit=50` 返回的是**最旧**的 50 条，不得直接当「最新 50 条」渲染。
- **渲染顺序**：按 **seq 降序（最新在最上）**，只展示最新 50 条。
- **前向兼容（契约 v1.8 §4.1 F7，两端必须遵守）**：请求该端点时**一律带 `?token=<mobile token>`**。
  服务端当前忽略该参数（行为不变），带上是无害的；一旦服务端后续给它加鉴权/可见性过滤（additive），两端无需改代码即可兼容。

## 三、文件结构

```
app.js / app.json / app.wxss        小程序入口、页面 + 底部 tabBar + scope.record、组件类名
project.config.json / project.private.config.json / sitemap.json
tokens.wxss                         设计令牌（契约 §2 逐值一致）
strings.json / strings.js           固定文案（契约 §5.1 基础文案 + §5.2 事件类型标签，逐字一致）
lib/config-store.js                 本地配置与校验（trpg.server/trpg.code/trpg.playerId/trpg.playerName/trpg.token）
lib/api-client.js                   /access + /api 客户端（Bearer 鉴权、两种响应口径、错误文案）
lib/ws-client.js                    /ws 订阅（8 类下行帧 + PING、last_seq、退避重连、帧文本）
lib/event-view.js                   F7 事件流视图（§5.2 标签、R1 可见性过滤、文本抽取）
lib/req-id.js                       req_id 幂等标识
lib/strings-map.js                  文案键 → WXML 可绑定标识符
pages/setup|table|voice/            连接设置 / 桌面 / 语音 三页
tests/contract.test.js              契约自检（node tests/contract.test.js）
```

## 四、功能清单（与 PC 玩家端逐项一致）

| # | 功能 | 小程序 | PC |
|---|---|---|---|
| F1 | 服务器连接（测试连接，显示版本与三端启用） | ✅ | ✅ |
| F2 | 连接码解析（不存在显示「连接码不存在」） | ✅ | ✅ |
| F3 | 玩家身份本地保存 | ✅ | ✅ |
| F4 | 加入跑团 → 桌面页 | ✅ | ✅ |
| F5 | 回合状态（15s 兜底轮询） | ✅ | ✅ |
| F6 | 行动提交（COLLECTING 门控 + req_id 幂等） | ✅ | ✅ |
| F7 | 事件流最新 50 条（REST 主通道 + WS 合并；seq 降序、最新在最上） | ✅ | ✅ |
| F8 | 语音录制与上传 | ✅ | ✅ |
| F9 | 录音设备状态只读 | ✅ | ✅ |
| F10 | 连接状态与断线对账 | ✅ | ✅ |
| F11 | 契约 §4 列出的第一项延期交互 | ⛔ 本轮不提供（见 `docs/ROADMAP-DEFERRED.md`） | ⛔ |
| F12 | 契约 §4 列出的第二项延期交互 | ⛔ 本轮不提供（见 `docs/ROADMAP-DEFERRED.md`） | ⛔ |

## 五、自检

```bash
node tests/contract.test.js
```

自检内容（29 个文件扫描）：
1. `strings.js` ↔ `strings.json` ↔ 契约 §5.1/§5.2 **逐字**一致（61 条）；
2. `tokens.wxss` 覆盖契约 §2 全部设计令牌（28 项）；
3. 无中转层端口引用、无 F11/F12 关键字、无 npm 依赖、无硬编码 token、无日志输出；
4. `/access` + `/api` 各端点 URL/鉴权/两种解包口径/错误文案；
5. WS 握手 URL、`last_seq` 键、PING 与 ACK/ERROR 过滤、退避序列 1/2/4/8→30s；
6. F7 视图层：§5.2 标签映射、R1 可见性过滤、文本抽取、**seq 降序渲染 + 同 seq 去重（轮询与 WS 帧只渲染一次）**、
   源码级断言（§3.1 先 info 校验再连 WS、§4.1 F7(a) 首次 since=-1&limit=1000、§3.4.1 15s 兜底轮询、F10 单行状态行四态由轮询失败计数驱动、§3.4.2 WS 状态不得进入可见文案）；
7. **WXML 静态自检**（无 IDE 时的替代验证）：事件处理器均在页面 JS 中定义、文案键均存在、
   标签闭合、页面标题与 `nav.*` 一致、`tabBar` 文案与 `nav.*` 一致。

直连实测（真实服务器 + 真实 mobile token，证据 `evidence/T4-mp.txt`）：
`node packaging/t4-live-probe.mjs` 覆盖 `/api/health`、`/access/info`（含 401 负例）、
`/access/mobile/state`、`/access/mobile/action`、`/api/campaigns/{c}/events`、
`/access/device/status`（404）、`/ws` 握手（收到 PING 心跳）。

## 六、扩展文案（契约 §5 未列，ext.*）

契约 §5 之外的扩展文案，与 `clients/web-player/`（PC 端）**逐字收敛**，共 22 条：

| key | 文案 |
|---|---|
| ext.ph.token | 访问 token（mobile 端） |
| ext.lbl.table | 桌面名称 |
| ext.lbl.campaign | 战役 |
| ext.lbl.version | 服务版本 |
| ext.lbl.ends | 启用端 |
| ext.st.recording | 录音中… |
| ext.st.recordUnsupported | 当前环境不支持录音（需要 HTTPS/localhost 且设备有可用麦克风） |
| ext.st.uploadOk | 已上传 {bytes} 字节 |
| ext.st.sttStatus | 转写状态：{status} |
| ext.st.deviceNone | 无该设备记录 |
| ext.st.needServer | 请先填写服务器地址 |
| ext.st.needCode | 请先填写连接码 |
| ext.st.needPlayerId | 请先填写玩家 ID |
| ext.st.needToken | 请先填写访问 token |
| ext.turn.line | 回合 {turn_no} · {state} · 已提交 {submitted} |
| ext.ev.turn | 回合 {turn_no} · {state} |
| ext.ev.delta | 状态更新 {delta} |
| ext.ev.narrationPending | 旁白待审 |
| ext.ev.info | 信息公开 {info_id} |
| ext.ev.branch | 分支推进 {label} |
| ext.ev.job | 任务 {job_id} · {status} |
| ext.ev.directed | 定向消息 {body} |

`{name}` 为占位符，用 `lib/strings-map.js` 的 `format()` 填充；`tests/contract.test.js` 会断言这 22 条
与 PC 端逐字一致、且集合大小相同（防止一端偷偷增删）。

**事件类型标签的两条通道（易混淆，务必区分）**：
- **F7 主通道（REST 事件流，命名空间 B 的 `type`）** → 用契约 **§5.2 的 `ev.<TYPE>` 中文标签**（契约 §4.1 F7 明文要求），未知 type → `ev.OTHER` + 原始 type 文本；
- **WS 增强帧（命名空间 A 的 `kind`）** → 标签直接显示 kind 原文（STATE_DELTA / TURN_UPDATED / …），正文用 `ext.ev.*` 模板。
生产路径当前无 WS 下行发布方（契约 §3.4），事件流实际显示的是前者。

## 七、边界与已知限制

- 小程序不能加载官方录音硬件 SDK（Android AAR / iOS xcframework），因此本端只做「手机录音整段上传」；
  录音硬件文件仍由原生桥接/上位机经 `/access/audio_upload` 上传。语音识别由服务端后台 STT 完成，
  上传响应里的 `stt.status` 只表示任务受理状态。
- **F6 幂等的服务端现状（实测，2026-09-25）**：`POST /access/mobile/action` 用同一 `req_id` 重复提交时，
  服务端返回 `status:"ok"` 并**再落一条事件**（实测 seq 188 → 189），而非契约 §4.1 F6 期望的
  `duplicate`。原因：`access.py::mobile_action` 每请求新建 `CommandBus`，其 `BranchGuard`
  幂等键表是**进程内实例态**（`app/scheduler/branch_guard.py`），跨请求不共享。
  客户端已按契约实现（收到 `status:"duplicate"` 显示「重复提交已忽略」），服务端修复后无需改客户端。
- F11/F12 本轮不做，与 PC 端一致；不做原因统一记录在 `docs/ROADMAP-DEFERRED.md`（契约 §6.1 要求：原因不得写进客户端代码或客户端 README）。
- 本机微信开发者工具 CLI 存在但**无法用于编译验证**：`cli open --project` 返回
  `code 10 不存在此 AppID`（未登录 + 游客 AppID），且当前会话无交互桌面（截屏 `句柄无效`），
  故以 WXML 静态自检 + 契约单测 + 真实服务端直连实测作为替代证据（见 `evidence/T4-mp.txt`）。
