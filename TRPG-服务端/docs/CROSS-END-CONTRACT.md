# 跨端契约与设计令牌（CROSS-END-CONTRACT v1.31 · 冻结）

> 版本：**v1.31**（2026-09-26 定稿冻结；v1.31 落实队长批准的 **UI 统一重构**（依据 docs/SPEC-UI-REFACTOR.md v1.0，色调参考「魔都 TRPG」cnmods.net 实测令牌）：**§2 令牌块整体替换**为深色主题（唯一令牌源，两端逐值实现；**键名与结构不变、仅值变**，故 §6 断言条数仍为 **233**），**§2 组件规格表 `.err-bar` 的两个硬编码色同步改深色版**（bg `#2a1f20` / border 1px `#4a2f31`）；**功能零变化**为硬约束（不得改任何 id / data-* / 事件绑定 / 请求与轮询/WS 逻辑 / 文案文本 / strings 键值），**两端视觉逐值一致**（仅保留既有两条差异：容器宽度自适应、导航形态）；§1.5 冻结 6 项 sha256 **不含本文件**，故本次升版不与冻结条款冲突（升级后仍须复测 6 项 sha256 未变）；v1.30 落实队长「状态行语义」裁决：§3.4.2 新增「**WS 状态不得产生可见文案**」（两端单行状态行、**四态由轮询驱动**），并同步 §4 F10 行与 §4 明细，避免后人再要求「两端各加一行 WS 状态」；v1.29 归纳 **「seq 连续性假设」已致三处错误**（做法 (b) / verifier #27d / web-eng `_t3f7tail`）并写入「凡涉及 seq 差值或连续性的断言与实现都必须改为与环境无关」的规则；§6 基线更新为 **233 项**（新增组 `(n)` WS 静默降级 2 项）；v1.28 **修正 v1.24 的遗漏（web-eng 指出）**：**§3.4.1 第 208/210 行仍写「做法 (a) 或 (b)」**，与 §4.1 F7 的「(b) 已废弃」自相矛盾 → 现两节一致：**首次只允许做法 (a)**；v1.10 变更行的「或 (b)」亦标注已被取代；v1.27 采纳 mp-eng 的防误读建议：§4.1 F7 的「实测缺口」历史段**显式标注「下列行号为修复前行号、勿再引用」**（该段 v1.24 已改为「当时」口径，但旧行号仍易被照抄）；v1.26 落实队长裁决：§3.4.2 新增**同一 seq 竞态规则** —— 去重键=seq，**同 seq 时轮询结果覆盖 WS 帧（REST 胜出）**，与网络时序无关；v1.25 采纳 verifier 的综合观察：**非 public 事件详情的两条外泄路径并列登记** —— §7.2 R1（REST 无 viewer 过滤）与 §3.4.2 STATE_DELTA（房间级广播），二者**须一起修**；v1.24 落实队长三项裁决：① **做法 (b) 正式废弃**（首次只允许 (a)）；② 桌面旧取址文件已改名 `.obsolete`、写入端约束已授权 → **R7 结案**；③ **修正一处陈旧现在时表述**（§4.1 F7 里「组 (j) 当时 0/2 FAIL」→ 当时状态 + 现已 2/2 PASS）；v1.23 记录 §5.3 组 (m) 首跑抓到 `ext.st.recordUnsupported` 两端措辞不一致 → 队长裁决统一为 MP 版（PC 6 文件改齐，现 4/4 PASS），并把该条目作为**已冻结 ext.* 条目**记入契约；v1.22 采纳 verifier 的**断言覆盖交叉核对**：§3.4.2 源码级断言清单由 4 类补为 **5 类**（补 `setStorageSync('trpg_last_seq_…')` 小程序直接落盘）+ 新增「断言清单须与断言实现交叉核对」要求；§5.3 注明 T5 已实现为**断言组 (m)（4 项）**；v1.21 充实 R6 证据链：**修复形态经逐字节比对确认**（guard/bus 与备份 SAME，仅 access.py 变）+ A/B 探针 + 生产实测三重证据；v1.20 采纳 server-eng 反馈并复核：§3.4.2 明确 **STATE_DELTA 实为房间级广播**（Hub 只过滤 WHISPER/NARRATION_PENDING/JOB_STATUS）→ 发布路径**不得**在 STATE_DELTA 携带非 public 事件详情；v1.19 采纳 verifier 的 **seq 非连续**发现并实测确认：**做法 (b) `since=tip-50` 不可靠**（c_demo 应 21 条仅返 2 条、c_t1probe 应 4 条仅返 1 条）→ 标为「不建议采用」并记录 seq 非连续事实；v1.18 新增 §5.3 **`ext.*` 客户端扩展文案命名空间**（契约不枚举、但两端须逐字一致，T5 应额外断言）+ §4.1 F7 明确「**接口顺序 ≠ 渲染顺序**」；v1.17 采纳 mp-eng 补充：§3.4.2 游标权威新增**「WS 帧不得落盘」**（理由：落盘会污染冷启动游标 → 同样漏事件）+ 源码级断言清单；v1.16 采纳 mp-eng 指出的事实错误并更新状态：**R6（F-2 幂等）已修复并 T1 独立复验通过 → AC-3.12 现判 PASS**；v1.12 变更行中「组 (j) 0/2 FAIL」改为**当时状态**并注明现已 2/2 PASS；v1.15 修正 v1.13 的**遗漏**：§7.2 **R5** 行仍写「WS 无下行发布方」，现标 **✅ 已解决**（发布路径已生效）；v1.14 §7.2 R7 新增「桌面旧目录取址文件已废弃、不得引用」+「取址脚本在非权威目录必须拒绝写入」；v1.13 更新 §3.4.2/§3.4.3/§3.4.4 —— **T2 的 additive 发布路径已落地并实测生效**（WS 收到 5 帧 TURN_UPDATED，seq 382–387），「从不 publish」只适用于 T1 测量时点；AC-3.13 两条路径均已达成；v1.12 强化 F7 前向兼容要求 —— **必须用查询参数 `?token=`，`Authorization: Bearer` 头不构成等价替代**（verifier 实测两端均未带 query 参数）；v1.11 记录加固 v2（移除 /app）、公网地址易变性与「**公网加固 ≠ 内网加固**」机制 + 局域网残余风险；v1.10 按**队长裁决**统一取数口径：**首次 limit=1000（做法 a）或 tip-50（做法 b）；增量 limit=50 + 拉满续拉最多 3 轮**（推翻 v1.9 的「增量也 1000」）；supersedes v1.9 / v1.8 / v1.7 / v1.6 / v1.5 / v1.4 / v1.3 / v1.2 / v1.1 与 v1 sha256 2BB71D02F087A118F6D1426458C1E7AAD115A6A9A7553B9E98501915F96899DD）
> 产出：T1（planner）。本文件是 **T2 / T3 / T4 的唯一实现依据**；PC 玩家端（server/player-web/）与小程序端（clients/miniprogram/）**必须逐字逐值实现**。
> 变更纪律：冻结后任何改动 = 升版本号 + 队长批准；未升版即改 = 一致性验收（AC-6）FAIL。
> 证据：所有「实测」结论的命令与原始输出见 evidence/T1-contract.txt。

> **环境事实（T2/T3/T4 共用，已确认）**
> - 远程项目根 PROJ = C:\Users\Administrator\Desktop\黑客松开发文档\trpg —— **以远程实际为准**；计划书里写的路径少一层，勿照抄。
> - 服务端：FastAPI 单进程 9210；局域网 http://192.168.10.110:9210 ；SSH 别名 gzq110。
> - 三端 token 见 configs/access_config.yaml（mobile / webapp / recorder，均 enabled）。

---

## 0. 术语与三个命名空间（**先读，勿混用**）

**主持端** = KP 端（/app，webapp token）；**玩家端** = 本契约的两个客户端（PC 浏览器版 + 微信小程序版）。

服务端存在**三个互不相同**的命名空间。字段名、取值、出现位置都不同，混用会导致静默不显示或崩溃：

| # | 命名空间 | 字段名 | 取值示例 | 出现位置 | 玩家端是否接触 |
|---|---|---|---|---|---|
| A | **WS 帧 kind** | kind | STATE_DELTA / PING / ACK / ERROR | WS /ws 收发帧 | 可选（见 §3） |
| B | **事件流 type** | type | ACTION_SUBMITTED / NARRATION_APPROVED / TRANSCRIPT_APPENDED | GET /api/campaigns/{c}/events 的 events[].type | **是（F7 主通道）** |
| C | agent EventKind | kind（小写） | say / act / roll / clue / … 共 10 种 | trpg/agent/events.py（冻结件） | **否** |

**铁律**

1. 玩家端**只**使用 A（若接 WS）与 B（事件流）。命名空间 C **不得出现在玩家端任何代码或文案里**。
2. WS 帧的字段名是 kind，**不是** type（实测帧：{"kind":"PING","ts":1790295380}）。事件流的字段名是 type，**不是** kind。
3. GET /api/campaigns/{c}/events 返回的是**命名空间 B**；POST /api/campaigns/{c}/events 请求体里的 type 也是 B。

---

## 1. 服务端接入点（玩家端**只允许**使用以下端点）

### 1.1 玩家端允许调用的端点（全部实测复核）

| 用途 | 方法 + 路径 | 鉴权 | 返回 data 字段 | 状态 |
|---|---|---|---|---|
| 服务信息 / 连通性 | GET /access/info | 任意启用端 token | {service,version,ends:{mobile,webapp,recorder},openapi,ws,ts} | 已有 |
| 连接码解析 | GET /access/table/resolve?code= | 任意启用端 token | {code,table_id,campaign,name,exists} | **新增（T2）** |
| 会话状态（轮询） | GET /access/mobile/state?table_id= | **mobile** token | {table_id,campaign,tip,count,by_type,turn}；turn 可为 null | 已有 |
| 提交行动 | POST /access/mobile/action | **mobile** token | receipt（含 seqs） | 已有 |
| 玩家录音上传 | POST /access/player/audio（multipart） | **mobile** token | 与 /access/audio_upload 同构：{seq,job,bytes,kind,file_ref,stt} | **新增（T2）** |
| 录音设备状态（只读） | GET /access/device/status?device_id= | 任意启用端 token | 设备记录；无记录 → 404 | 已有 |
| **事件流（F7 主通道）** | GET /api/campaigns/{campaign}/events?since=&limit=&token= | **服务端当前不校验**（无鉴权） | {events:[GameEvent…],tip} | 已有，实测可用。**客户端必须带查询参数 ?token=<mobile token>**（**非 header**；见 §1.2 例外与 §4.1 F7 前向兼容要求） |
| 实时订阅（可选增强） | WS /ws?table=&viewer=&role=pl&last_seq=&token= | 任一启用端 token | 见 §3 | 已有，**能力受限**（§3.4） |

> **玩家端不得调用**：/access/advice、/access/nl、/access/voice/register、/access/voice/transcript、/access/audio_upload、POST /access/device/status、/access/host/*、/api/*（除 /api/campaigns/{c}/events）、/mcp/*。这些是 KP / recorder 端能力。

### 1.2 token 传递方式（两种等价）

- 查询参数：?token=<token>
- 请求头：Authorization: Bearer <token>
- 小程序统一用 Authorization: Bearer <mobile token>（设置页填写并本地保存，**不硬编码、不写日志**）。
- 未启用端一律 401（即使带 token）。

> ⚠️ **唯一例外 —— F7 事件流端点（见 §4.1 F7）**：请求 `GET /api/campaigns/{c}/events` 时**必须带查询参数 `?token=`**。
> **`Authorization: Bearer` 头不构成等价替代** —— 若服务端将来只按 query 参数实现鉴权/可见性过滤，头不会被识别，前向兼容的意图即落空。其余 `/access/*` 端点两者仍等价。
> （本条由 verifier 实测发现两端均未带 query 参数而补充，见 §8 v1.12。）

### 1.3 统一响应包裹与错误码（/access/* 层）

- 成功：{"ok":true,"data":{…},"code":0}
- 失败：{"ok":false,"error":"<文本>","code":<http>}（**扁平**，不是 detail 嵌套）
- 错误码：0 ok ／ 400 参数错误 ／ 401 鉴权失败 ／ 403 kp_only 或 recorder_only ／ 404 不存在 ／ 500 服务端异常。
- /api/* 层**不使用**该包裹：成功直接返回对象，失败返回 {"detail":"…"} + 4xx/422。**F7 事件流走 /api/*，必须按 /api 口径解析**（成功读 events 与 tip；失败读 detail）。

### 1.4 /access/info 的 ws 字段陷阱（**必读**）

data.ws 的值是字符串 "/access/ws"，但 **/access/ws 只是返回 WS 使用说明的 GET 文档端点，不是 WebSocket 地址**。
真实的 WebSocket 路径是 **/ws**（app/main.py 中 @app.websocket("/ws")；/access/ws 自身的文档体也写着 "channel":"/ws"）。

> **禁止**用 new WebSocket(base + info.data.ws) 或 wx.connectSocket({url: base + info.data.ws}) 去连接——那样连的是文档端点，握手必失败。

### 1.5 冻结契约不可改（T2/T3/T4 均不得触碰）

**实测为 6 项**（3 个代码/配置 + 3 个文档）。PLAN-ACCEPTANCE 里写的「五件」是把 docs/contracts/* 当成 1 项；按远程实际 docs/contracts/ 下有 3 个文件，故合计 **6 项**，验收（AC-7.28）按下列 6 个 sha256 比对：

| # | 文件（相对 PROJ） | sha256 |
|---|---|---|
| 1 | trpg/agent/events.py | 839B1016610D54D9C4528AF4D9B68425412FF5E9107890D7F3B2C47EA1635531 |
| 2 | app/web/ws_protocol.py | 3793B1E31C578D04D7FAC95E6113BDB252D2862B78976D1394825278906240F7 |
| 3 | trpg/agent/allowlist.yml | 47899A5D874E1B3A6242F3B51EE4563744A36BB623770DDE67E6F97C3D60F5A2 |
| 4 | docs/contracts/mcp-contract.md | 3C4B33AF04748F05B6FAF20A9F54A1D52E56BD7B75A4ADADC13C7725FC0EE777 |
| 5 | docs/contracts/runtime-contract.md | 4BB45B2218B9E319B499D706FC36F55DE2291DBF29B8084FDB812B5EE2F45F72 |
| 6 | docs/contracts/security-sync.md | C296D229662DB764ACA666FC080C1920BFA1E7B1D1B6C6242931351FED581C3B |

其余不可改：REST 既有端点签名、/access 既有 11 端点签名。**只允许新增 additive 端点**。

### 1.6 鉴权矩阵与 401/403 陷阱（**T2 必读，AC-1.6 逐格判据**）

| 端点 | 无 token | mobile token | webapp token | recorder token |
|---|---|---|---|---|
| GET /player/ 与 /player/{path} | 无鉴权（200 / 404） | — | — | — |
| GET /access/table/resolve | **401** | **200** | **200** | **200** |
| POST /access/player/audio | **401** | **200** | **403 mobile_only** | **403 mobile_only** |
| POST /access/host/table | **401** | **403 kp_only** | **200** | **403 kp_only** |
| POST /access/host/turn | **401** | **403 kp_only** | **200** | **403 kp_only** |

⚠️ **陷阱（会令 AC-1.6 FAIL）**：既有 `_require_end(end)` 对「合法但端不匹配」的 token 返回 **401**（不是 403）；只有 `_require_kp_end` / `_require_recorder_end` 家族才给 403。
因此 **POST /access/player/audio 必须新增同构的 `_require_player_end`（403 mobile_only）**；若直接复用 `_require_end("mobile")`，webapp token 会得到 401 而非 AC-1.6 要求的 403。
可直接抄的实现样例与一次性矩阵验收脚本见 docs/ENDPOINT-SPEC-NEW.md §0.2 与 §6。

既有 11 端点（实测）：GET /access/info、GET /access/ws、GET /access/mobile/state、POST /access/mobile/action、POST /access/audio_upload、POST /access/voice/register、POST /access/voice/transcript、POST /access/advice、POST /access/nl、POST /access/device/status、GET /access/device/status。

---

## 2. 设计令牌（Design Tokens，两端**完全相同**）

以下 JSON 块是**唯一令牌源**，两端逐值实现；T5 的一致性脚本按此块逐值比对（**必须可 JSON.parse**）。

~~~json
{
  "color": {
    "bg": "#17191a",
    "card": "#212625",
    "text": "rgba(255,255,255,0.82)",
    "muted": "#b9b9b9",
    "border": "rgba(255,255,255,0.14)",
    "accent": "#ffbb70",
    "accentText": "#1a1206",
    "ok": "#63e2b7",
    "warn": "#f2c97d",
    "err": "#e88080",
    "focus": "#ffbb70",
    "chipBg": "#2b3237"
  },
  "radius": { "card": "6px", "ctl": "4px", "chip": "999px" },
  "space": { "xs": "4px", "sm": "8px", "md": "12px", "lg": "16px", "xl": "24px" },
  "font": { "h1": "20px", "h2": "15px", "body": "14px", "small": "12px" },
  "layout": { "maxWidth": "560px", "sidebar": "none", "navHeight": "48px", "tapMin": "44px" }
}
~~~

**组件语义类名（PC 用 CSS class，小程序用同名 WXSS class）**

| 语义 | class | 规格 |
|---|---|---|
| 页面容器 | .pg | max-width 560px，左右 padding 16px，bg=color.bg |
| 卡片 | .card | bg=card，border 1px color.border，radius=card，padding 12px，margin-bottom 12px |
| 卡片标题 | .card-title | font-size h2，font-weight 600，margin-bottom 8px |
| 主按钮 | .btn-primary | bg=accent，color=accentText，radius=ctl，min-height 44px，font-size body，无边框 |
| 次按钮 | .btn | bg=card，color=text，border 1px color.border，radius=ctl，min-height 44px |
| 输入框 | .input | bg=card，border 1px color.border，radius=ctl，min-height 44px，padding 0 12px，font-size body |
| 徽章 | .chip | bg=chipBg，color=text，radius=chip，padding 2px 10px，font-size small |
| 状态行 | .status-line | font-size small，color=muted |
| 错误条 | .err-bar | bg #2a1f20，border 1px #4a2f31，color=err，radius=ctl，padding 8px 12px，font-size small |
| 成功行 | .ok-line | color=ok，font-size small |
| 列表项 | .item | bg=card，border 1px color.border，radius=ctl，padding 8px 12px，font-size body，margin-bottom 6px |
| 事件类型标签 | .ev-kind | font-size small，color=muted，margin-right 6px |
| 时间戳 | .ev-ts | font-size small，color=muted |

**两端差异只允许**：容器宽度自适应（PC 居中 560px；移动端 100%）、导航形态（PC 顶部 tab；小程序底部 tabBar，高度 navHeight=48px）—— **导航差异的边界（队长 2026-09-26 裁决；详见下方「导航平台限制」补充）**：导航**颜色必须对齐**（tabBar 底 `#262c31`、未选中 `#b9b9b9`、选中 `#ffbb70`、navigationBar 底 `#262c31`）；**形态与选中态装饰不要求对齐**（微信原生 tabBar 仅可配 `color`/`selectedColor`/`backgroundColor`/`borderStyle`，`borderStyle` 枚举仅 `black|white`，故附则的选中态字重 600 / pill 底 / 2px 指示条 / 1px 分隔线在小程序端物理上无法实现），属**已知平台限制**，不计为一致性差异。**另允许：移动端按钮触控适配**（`.btn` / `.btn-primary` 在小程序端整行铺满 + 上间距，PC 端按内容定宽 —— 属移动端点击目标适配，不计为视觉一致性差异）。**不允许功能差异**。所有可点元素 min-height ≥ 44px（两端都满足）。

> **v1.31 补充（导航平台限制，实测；队长 2026-09-26 批准）**：微信原生 tabBar **只能**配置 `color` / `selectedColor` / `backgroundColor` / `borderStyle` 四个字段，且 `borderStyle` 仅接受 `"black"|"white"` 枚举。
> （落位说明：本补充经队长批准，落于 §2 组件表之后；§8 的 v1.31 变更行第 ⑦ 条已同步记录。）
> ⇒ 导航**颜色必须对齐**（tabBar 底 `#262c31`、未选中 `#b9b9b9`、选中 `#ffbb70`、navigationBar 底 `#262c31`），但**选中态装饰（字重 / pill 底 / 指示条 / 1px 分隔线）在小程序端物理上无法实现**，属**已知平台限制**，不计为一致性差异。

---

## 3. WS 帧订阅规则（/ws，**可选增强通道**）

### 3.1 连接

~~~
ws://<host>:9210/ws?table=<table_id>&viewer=<player_id>&role=pl&last_seq=<int>&token=<mobile token>
~~~

- role 取值 kp|pl|spectator；玩家端固定 pl。
- **WS 路径恒为 /ws。** `info.ws` 字段（值为 "/access/ws"）仅是对「说明端点」的引用，**客户端不得将其作为 WS URL 使用**（§1.4）。两端逐字遵循：禁止 `new WebSocket(base + info.data.ws)` / `wx.connectSocket({url: base + info.data.ws})`。实测：连 "/access/ws" 做 WS 升级同样得到 **HTTP 403**（它不是 WS 路由），F5/F7/F10 会整体失效。
- table、viewer 缺失或 role 非法 → **握手被拒**；token 缺失/错误 → **握手被拒**。
- **拒绝的可观测形态（实测，权威）**：服务端在 `accept()` **之前**调用 `close(code=4400)`，因此连接从未升级为 WebSocket —— 客户端观察到的是**握手阶段 HTTP/1.1 403 Forbidden**（空 body、`Connection: close`），**永远收不到 4400 关闭码**。源码层面的 `close(4400)` 与客户端可观测的 403 不矛盾：**以 403 为准**。
  实测四种情形（无 token / role 非法 / 缺 table / token 错误）**全部为 HTTP 403**，无差异、无 body。

  **对照实验（T1 与 verifier 各自独立复现，2026-09-25）** —— 关键结论：**任何失败的 WS 升级都归一到 403**：

  | 探测（对 9210 直接发 Upgrade 请求） | 实测响应首行 |
  |---|---|
  | UPGRADE /ws（参数 + token 均有效） | **HTTP/1.1 101 Switching Protocols** ✅ |
  | UPGRADE /ws（无 token / 错 token / role 非法 / 缺 table） | HTTP/1.1 403 Forbidden |
  | UPGRADE /access/ws（**带有效 token**） | HTTP/1.1 403 Forbidden |
  | UPGRADE /nosuchroute（**路由不存在**） | HTTP/1.1 403 Forbidden |
  | UPGRADE /api/health（有效但非 WS 路由） | HTTP/1.1 403 Forbidden |

  因此客户端面对 403 时**无法区分**「token 错 / 参数错 / 路径错 / 服务端不支持 WS / 网络故障」五者 —— 这比「鉴权失败 = 403」更强，也**更强地支持**本节裁定：**不得依赖状态码做错误分类，必须先用 GET /access/info 校验连通性与 token**。

  → **客户端必须**：① 先用 GET /access/info 校验 token 与服务器可达性（F1），再尝试 WS；② **不要**依赖 WS 关闭码或握手状态码做错误分类（4400 不会到达，403 也不可细分）；③ WS 失败一律不阻塞 UI（事件流由 §3.4 的 REST 通道兜底）。

### 3.2 下行帧（S→C）

服务端冻结 8 类，**全带** seq、campaign_id、scope、ts：STATE_DELTA / TURN_UPDATED / NARRATION_PENDING（scope=kp）/ NARRATION_APPROVED（public）/ WHISPER（whisper）/ INFO_REVEALED（condition）/ BRANCH_TAKEN（public）/ JOB_STATUS（actor）。

另有心跳 {"kind":"PING","ts":<int>}，**每 15s** 一条；PING 只刷新心跳，**不进入事件列表**。

### 3.3 上行帧与应答（C→S）

玩家端只发一种：{"kind":"PING"}（可选，服务端不回应）。
玩家端**不得**发送 START_TURN / CLOSE_WINDOW / APPROVE_NARRATION（KP 专用，非 KP 会收到 {"kind":"ERROR","error":"kp_only"}）。
服务端对应答：{"kind":"ACK","req_id":…,"up":…} 或 {"kind":"ERROR","error":"…"}。

> **ACK 与 ERROR 不属于冻结的 8 类下行帧**。客户端**必须**把 kind 不在已知集合内的帧**忽略掉**（不崩溃、不写事件列表）。

### 3.4 事件通道与降级规则（**两端实现必须一致**）

#### 3.4.1 主通道：REST 轮询（**必须实现，永远是兜底**）

F7 的**主通道恒为** `GET /api/campaigns/{campaign}/events`：每 2s 一次，并在提交行动后立即拉取一次。

- **增量轮询**：`since=<本地 last_seq>&limit=50&token=<mobile token>`；**若某次返回条数 == 50（拉满）则立即用推进后的游标续拉，最多 3 轮**（防滞后、不丢事件）。
- **首次取数**：见 §4.1 F7 —— **做法 (a)** `since=-1&limit=1000` → 客户端取**最新 50 条**。🚫 **做法 (b) `since=max(-1, tip-50)&limit=50` 已于 v1.24 正式废弃、禁止采用**（理由见 §4.1 F7：单团 seq 不连续 → 把 seq 阈值当条数用会严重少返回）。

> **统一口径（队长裁决 2026-09-25，v1.10 生效；v1.24 更新）**：**首次 = `limit=1000`（做法 a）——🚫 做法 (b) `tip-50` 已于 v1.24 正式废弃、不得采用**；**增量 = `limit=50` + 拉满续拉（最多 3 轮）**。
> ⚠️ **v1.24 的废弃同时适用于本节与 §4.1 F7**（此前仅 §4.1 F7 更新、本节遗漏，v1.28 已补齐 —— 曾因此让读者误以为 (b) 仍可用）。
> 历史：v1.9 曾把增量也统一为 `limit=1000` 以消除与 §4.1 F7(a) 的字面矛盾；现按队长裁决**改回增量 `limit=50`**（配合排空规则效果等价，且单次 payload 更小）。
**无论 WS 是否可用，两端都必须实现该轮询**——它是功能可用的基线，也是 WS 不可用时的唯一事件来源。

#### 3.4.2 增强通道：WS 广播（**可选接入，不得成为依赖**）

队长裁决（2026-09-25，采纳方案 A）：由 **T2 追加 additive 发布路径**（EventStore.append 单一收口处 best-effort 调用 hub.publish；严格复用冻结 8 帧、不新增帧；无法映射时回退 STATE_DELTA(event)），使 8 类下行帧在生产可用。
> ✅ **已落地并实测生效（2026-09-25）**：verifier 真实握手收到 **5 帧 `TURN_UPDATED`（seq 382–387）**，即 T2 的 `hub.publish` 收口**已在生产生效**，8 类下行帧**不再恒空**。→ **WS 实时路径现为可用状态**；但**主通道仍是轮询**（§3.4.1），WS 仍按本节规则作为**增强**接入（不得成为依赖）。

两端接入规则（**逐字一致**）：

- MAY 连接 /ws（路径恒为 /ws，见 §3.1）。
- 连不上 / 握手 403 / 被拒 / 断开 → **静默降级**：只走 §3.4.1 轮询，**不得**报错、不得阻塞 UI、不得改变任何文案。
- 🚫 **WS 状态不得产生可见文案（队长裁决 2026-09-25，v1.30 明确）**：**两端均为「单行状态行」**，其**四态（st.connecting / st.connected / st.reconnecting / st.closed）由轮询驱动**（连接建立、连续失败计数、恢复等均由轮询结果决定）；**WS 连接状态一律不得进入可见文案** —— 不得为 WS 单独加一行、不得把 WS 的 open/close/error 映射为 st.* 文案、不得显示「WS 已连接/断开」之类文字。理由：WS 是可选增强，其可用性不得改变用户可见界面（否则同一功能在不同网络环境下文案不同，破坏四端一致性）。
- 收到**已知 kind**（§3.2 的 8 类）→ 合并渲染进事件流；**按 seq 去重**（同一 seq 的轮询结果与 WS 帧只渲染一次）。
- 收到 PING → 只刷新心跳（§3.5），不入事件列表。
- 收到 ACK / ERROR / 未知 kind → **忽略**（§3.3）。
- WS 恢复后**不得**重复渲染已显示的 seq（以本地 last_seq 为准）。
- **游标权威（两端逐字一致，v1.9 明确；v1.17 补充「落盘禁令」）**：`last_seq` **只由轮询推进**，**绝不由 WS 帧推进**，**也绝不由 WS 帧落盘**。
  - 理由①（推进）：WS 可能只发布**部分**事件（映射不完全），用帧 seq 推进游标会**跳过中间 seq** → 轮询路径**漏事件**；
  - 理由②（**落盘**，mp-eng 补充）：若用 WS 帧**写 storage**（`trpg_last_seq_<table>` / `localStorage`），会**污染冷启动读到的游标** —— 下次启动以该值为 `since`，同样漏事件。**落盘权也只属于轮询**。
  - **源码级断言（v1.22 补全为 5 类，含两端各自的直接落盘写法）**：WS 处理路径中不得出现
    ① `lastSeq = frame.seq` / `cursor = f.seq`（推进）；② `saveLastSeq(`（MP 封装落盘）；③ `lsSet(LAST_SEQ_PREFIX`（PC 封装落盘）；④ `localStorage.setItem('trpg_last_seq_…')`（PC 直接落盘）；⑤ `setStorageSync('trpg_last_seq_…')`（**小程序直接落盘** —— 本类由 verifier 交叉核对时发现原清单遗漏并补上）。命中即 FAIL。
  - 📌 **断言清单须与断言实现交叉核对覆盖**（verifier 提议，已采纳）：契约给出断言清单后，须逐条核对 parity 实现是否真的覆盖；反之断言实现新增模式也应回写契约。本清单即经此核对由 4 类补为 5 类。
- **WS 帧处置（两端逐字一致）**：帧的 `seq <= 本地 last_seq` → **直接丢弃**（已被轮询覆盖或已显示过）；`seq > last_seq` → 渲染（插入顶部、保持降序），但**不推进** last_seq —— 该 seq 随后会被轮询再次返回，由**按 seq 去重**保证只渲染一次。
- **去重键**：条目唯一键 = `seq`；轮询结果与 WS 帧**共用同一键空间**。
- 🔒 **同一 seq 的竞态规则（队长裁决 2026-09-25，v1.26 写入）**：**去重键 = `seq`；同 seq 时「轮询结果覆盖 WS 帧条目」——REST 胜出**。
  - 理由①：§4.1 F7 要求事件流类型标签按 **§5.2 `ev.*` 映射**，而 **REST 是主通道与权威表示**；
  - 理由②：若「先到先渲染」，同一 seq 的**标签会依赖网络时序**（同一端多次运行结果可能不同）→ **不确定、不利验收**；本规则**与网络时序无关**（确定性）。
  - **两端逐字一致**：轮询 ingest 时**不得**因「该 seq 已存在」而跳过，必须**直接重写该键**；WS 帧合并时同 seq **不得**覆盖已有条目。
  - **实测核对（T1，2026-09-25）**：PC `app.js:527-546 ingestEvents` 已按裁决去掉 `continue`、直接重写 `state.items[key]` ✅；MP `lib/event-view.js` `mergeFrame:127`（同 seq **不覆盖**）+ `mergeFeed:112`（轮询**总是覆盖**）→ **两种到达顺序下均为 REST 胜出** ✅。
- ⚠️ **STATE_DELTA 的实际可见性（v1.20 明确，安全相关）**：冻结件 `docs/contracts/runtime-contract.md` 写 STATE_DELTA 为 scope=viewer「可见子集」，但 Hub 的 `viewer_may_see`（app/web/ws.py）**只过滤 WHISPER / NARRATION_PENDING / JOB_STATUS** → **STATE_DELTA 实际是房间级广播**。故：**任何发布路径都不得在 STATE_DELTA 里携带非 public 的事件详情**；T2 的回退帧一律用 `value={type, redacted:true}`（详见 ENDPOINT-SPEC-NEW §8/§8.1）。
  > ⚠️ **与 §7.2 R1 并列（v1.25）**：**非 public 事件详情有两条外泄路径** —— ① 本条（WS STATE_DELTA 房间级广播）与 ② **R1**（REST 事件流无服务端 viewer 过滤）。**须一起修**，只修一条仍会外泄（verifier 提出）。

#### 3.4.3 降级判据（AC-3.13，队长裁决升级版）

「KP 侧触发一帧 NARRATION_APPROVED 后，两端在 5s 内显示同一条旁白」——
**WS 广播可用时按实时达标；若 WS 广播不可用则退化为「≤5s 轮询可见」**。**两条路径任一达成即 PASS**，验收须给出所用路径的证据（WS 原始帧，或轮询响应 + 时间戳）。
> 现状（2026-09-25）：**两条路径均已实测达成** —— 轮询路径 **1085ms** 可见；WS 路径真实握手收到业务帧（§3.4.2）。故 AC-3.13 可判 **PASS**，且**实时路径已可用**。

#### 3.4.4 历史背景（为何有此设计）

**T1 实测（2026-09-25，当时）**：本构建生产路径**从不调用 Hub.publish**（app/web/ws.py:148 定义，无生产调用方，仅 tests 与 scripts/sim），WS 只会收到 PING 与上行 ACK/ERROR，房间日志恒空 → 若 F7 依赖 WS 将永远为空（证据见 evidence/T1-contract.txt §5）。
→ **该状态已改变**：T2 已按队长裁决实现 additive 发布路径，并**实测生效**（verifier 收到 5 帧 TURN_UPDATED，seq 382–387，见 §3.4.2）。故「从不 publish」**只适用于 T1 测量时点**，不再描述当前生产状态。
**设计为何仍然成立**：**主通道定为轮询、WS 定为增强**——该设计对「发布路径已生效」与「未来再次不可用」两种情形**都兼容，两端无需改代码**；轮询始终是完整性与兜底的权威来源（§3.4.1），WS 只提供更低延迟。

### 3.5 last_seq 持久化与重连

- 本地存储 key 规则**两端相同**：trpg_last_seq_<table_id>
  - PC：localStorage.setItem("trpg_last_seq_" + tableId, String(seq))
  - 小程序：wx.setStorageSync("trpg_last_seq_" + tableId, seq)
- 重连退避：1 / 2 / 4 / 8s，上限 30s；重连时带上 last_seq；**30s 无任何帧**则主动重连。
- **心跳依据（两端逐字遵循）**：心跳以**服务端 PING 到达**为准 —— 服务端由 hub 每 15s 下发 `{"kind":"PING","ts":<int>}`。客户端上行 `{"kind":"PING"}` 会被服务端**静默忽略且不回 PONG**（实测：无任何应答），因此**不得**用「发出 PING 后等 PONG」作为存活判据，也**不得**依赖客户端 PING 维持连接。判据恒为：**距上次收到服务端帧（含 PING）超过 30s ⇒ 判定断线并重连**。
- 对账：重连成功后按 §4 F10 拉取 since=last_seq 补齐，无重复、无丢失。

---

## 4. 功能清单（F1–F10 两端**都必须有**；F11/F12 两端**都不做**）

| # | 名称（两端逐字一致） | 交互 | 端点 / 通道 |
|---|---|---|---|
| F1 | 服务器连接 | 地址输入 + 「测试连接」 | GET /access/info |
| F2 | 连接码 | 输入连接码 → 「解析」→ 显示桌名/战役 | GET /access/table/resolve |
| F3 | 玩家身份 | 玩家 ID + 昵称，本地保存 | 本地存储 |
| F4 | 加入桌面 | 「加入跑团」→ 进入桌面页 | 组合 F1+F2 |
| F5 | 回合状态 | 显示 turn_no / state / 已提交数，2s 轮询兜底 | GET /access/mobile/state |
| F6 | 行动提交 | textarea + 意图输入 + 「提交行动」，**仅 COLLECTING 可提交** | POST /access/mobile/action |
| F7 | 事件流 | 最近 **50** 条，**seq 降序渲染（最新在最上）**（类型标签 + 文本 + 时间） | GET /api/campaigns/{c}/events（主；取数规则见 §4.1 F7）；WS 帧（可选合并） |
| F8 | 语音录制上传 | 「开始录音/停止并上传」，显示上传结果 | POST /access/player/audio |
| F9 | 设备状态（只读） | 输入 device_id → 「查询」 | GET /access/device/status |
| F10 | 连接状态与对账 | 状态行显示 连接中/已连接/重连中/已断开（**单行；四态由轮询驱动，WS 状态不产生可见文案**，见 §3.4.2）；重连自动补齐 | /access/info + 事件流（轮询为主；WS 为可选增强，**不影响文案**） |
| F11 | 骰点托盘 | **两端都不提供** | — |
| F12 | 玩家私语 | **两端都不提供** | — |

**F11/F12 不做的一致原因**（两端都写进 ROADMAP-DEFERRED.md）：服务端 /ws 的 COMMAND 上行**仅 ACK、无副作用**，且无玩家侧发起点；要做需**新增写路径**＝改冻结契约，超出本轮范围。**一致性优先于功能数量**，故两端一致地不实现。

### 4.1 逐项实现要点（两端逐条对齐）

- **F1**：默认地址取 location.origin（PC）/ 设置页手填（小程序）；成功显示 version 与三端启用状态（ends.mobile/webapp/recorder）；失败显示 err.net 或 err.auth（401 → err.auth）。
- **F2**：code 大小写不敏感；exists:false → 显示 err.notFound（连接码不存在），**不是**网络错误。
- **F3**：PC key：trpg.playerId / trpg.playerName / trpg.server / trpg.code / trpg.token；小程序同名 key 存 wx.setStorageSync。
- **F4**：PC 支持 URL 预填 ?server=&code=&pid=&token=；小程序不支持 URL 预填（无等价物，**不作为功能差异**）。
- **F5**：turn 为 null → 显示 st.noTurn；turn.state 为 COLLECTING → 显示 st.collecting；其他状态显示原始 state 字符串（见 §7 风险 R2）；turn.submitted 在此端点里是**数字**（已提交人数）。
- **F6**：req_id 用 crypto.randomUUID()（小程序回退 Date.now() + 随机数）；服务端按 req_id 幂等；重复 → 显示 st.duplicate；成功 → st.submitted；空文本 → st.emptyAction（**不发请求**）；非 COLLECTING → 禁用提交并显示 st.notCollecting。
- **F7（队长裁决 2026-09-25 更新渲染顺序）**：**按 seq 降序渲染（最新在最上）**，展示**最新 50 条**。
  - ⚠️ **seq 非连续（T1 实测，v1.19 记录）**：**单 campaign 内 seq 不连续**（seq 为共享/全局递增，跨 campaign 交错 → 单团有大段空洞；实测 c_demo 21 条事件跨 seq 176–482、缺 386；c_t1probe 4 条跨 185–480）。故**任何「按 seq 差值推算条数」的写法都不成立**（如 `tip-50`、`seq+n`），取数只能按**条数**（`limit`）而非按 seq 跨度。
  - 🔁 **该错误假设已出现三处（v1.29 归纳，供防复发）**：① 契约**做法 (b)** `since=tip-50`（v1.19 实测证伪 → v1.24 废弃）；② verifier 的 parity **#27d** 原断言「最下面一条 == tip-49」（已改为「渲染集 == 返回集尾部 min(50,N) 条降序」）；③ web-eng 的 `packaging/_t3f7tail.mjs` 原断言「最下面一条 == tip-49」（共享服务端下其他 campaign 的写入会占用 seq → 偶发失败；已改为与环境无关的「渲染结果 == 该 campaign 最新 50 条，逐项一致」）。
  - ✅ **规则**：**凡涉及 seq 差值或连续性的断言/实现，都必须改写为与环境无关的形式**（按条数、或与实测返回值逐项比对），**不得假设 seq 连续**。
  - ⚠️ **取数陷阱（T1 实测）**：`GET /api/campaigns/{c}/events?since=-1&limit=50` 返回的是**最旧的 50 条**，**不是最新的** —— 服务端实现为 `[e for e in events if e.seq > since][:limit]`（按 seq 升序取**前** limit 条）。实测：某 campaign 有 seq 185/186/187 时，`since=-1&limit=2` 返回 **[185,186]**。**不得**直接把该响应当作「最新 50 条」渲染（否则两端都会显示最旧的 50 条）。
  - ⚠️ **接口顺序 ≠ 渲染顺序（v1.18 明确）**：该端点的**原始返回本身就是 seq 升序**（服务端取「seq > since 的**前** limit 条」）——**不得**把「接口返回的顺序」当作「渲染顺序」的判据；渲染顺序**只由客户端排序决定**（seq 降序）。同理，**对象键遍历顺序也不构成排序**（`for (var k in items)` 对数字键天然升序，是错觉来源）。
  - **正确做法（两端逐字一致；推荐 (a)）**：
    (a) **首次**：`since=-1&limit=1000&token=<mobile>`（服务端上限 1000）→ 客户端按 seq 取**最新 50 条** → 降序渲染；**之后增量轮询** `since=<本地 last_seq>&limit=50&token=<mobile>`，把新事件**插入顶部**（保持降序）。
    **排空规则（防滞后，两端逐字一致）**：若某次响应返回条数 **== 50（拉满）**，则立即用推进后的游标（`since=本次返回的最大 seq`）**再拉一次**，最多连续 **3 轮**；3 轮后仍未拉空则留待下一次 2s 轮询继续（**自愈，不丢事件**）。
    (b) **两步（🚫 已于 v1.24 正式废弃、禁止采用 —— 见下方说明）**：先取 `tip`（用 `since=-1&limit=1000` 响应里的 `tip`，或 `GET /api/session_state?campaign=`），再请求 `since=max(-1, tip-50)&limit=50` 直接拿最新 50 条；**增量轮询与排空规则同 (a)**（`limit=50` + 拉满续拉最多 3 轮）。
      - 🚫 **已废弃（队长裁决 2026-09-25，v1.24 正式生效）**：**首次取数只允许做法 (a)**；做法 (b) 禁止采用。理由：**事件 seq 在单个 campaign 内并不连续**（seq 是共享/全局递增，跨 campaign 交错 → 单团 seq 有大段空洞）。故 `since=tip-50` 会**严重少返回**：
        | campaign | 事件数 | tip | 做法 (b) `since=tip-50` 返回 | 应为（最新 min(50,N)） |
        |---|---|---|---|---|
        | c_demo | 21 | 482 | **2 条** ❌ | 21 条 |
        | c_t1probe | 4 | 480 | **1 条** ❌ | 4 条 |
        | c_probe | 1 | 175 | 1 条 ✅（连续，属巧合） | 1 条 |
      - **做法 (a) 不受影响**（`since=-1&limit=1000` 后客户端取尾部 min(50,N) 条，与 seq 是否连续无关）→ **两端现均采用 (a)**，故本轮无实现影响。
  - **前向兼容要求（两端必须遵守，v1.12 强化）**：请求该端点时**必须带上查询参数 `?token=<mobile token>`**（例如 `GET /api/campaigns/{c}/events?since=-1&limit=1000&token=<mobile>`）。**首次与增量请求都要带**。服务端**当前不校验**该参数（多余查询参数被忽略，行为不变），但**带上是无害的**；这样一旦后续给该端点加鉴权/可见性过滤（additive），**两端无需改代码即可兼容**。
    ⚠️ **`Authorization: Bearer` 头不构成等价替代**（§1.2 的「两者等价」在此端点**不适用**）：若服务端将来只读 query 参数，头不会被识别。**只带 header、不带 `?token=` = 未满足本条**。
    📌 **实测缺口（verifier 2026-09-25 发现，**当时** parity 组 (j) 为 0/2 FAIL；⚠️ **下列 `:548-549` / `:128-129` 均为「修复前行号」，勿再引用**）**：PC `server/player-web/app.js:548-549` 未带 token；小程序 `lib/api-client.js:128-129` 只带 `Authorization: Bearer` 头、**未带 query 参数**。
    ✅ **现已修复（勿按 FAIL 记录）**：两端均已带查询参数 —— **PC `app.js:551`**（`'&token=' + encodeURIComponent(state.token)`）、**MP `api-client.js:135`**（`token: String(this.profile.token || '')`）→ **parity 组 (j) 现 2/2 PASS**。
  - `last_seq` 语义不变：取已渲染事件的最大 seq；轮询用 `since=last_seq`（§3.5）。
  - 类型标签按 §5.2 的 ev.* 映射（未知 type → ev.OTHER + 原始 type 文本）；时间取 ts。
  - 按 seq 去重（与 §3.4.2 一致）；**必须按可见性过滤**（见 §7 风险 R1）。
- **F8**：PC 用 getUserMedia + MediaRecorder → FormData{file,campaign,kind=voice,player_id}；小程序用 wx.getRecorderManager() → wx.uploadFile（name=file，formData 同上）；显示 bytes 与 file_ref、stt.status；不支持时明确降级提示（不静默失败）。
- **F9**：404 → 显示「无该设备记录」（用 st.noDevice）。
- **F10**：状态行文案固定为 §5.1 的 st.* 四态；**单行；四态由轮询驱动**（不得由 WS 状态驱动，§3.4.2）；重连成功后用 since=last_seq 补齐。

---

## 5. 固定文案（两端**逐字相同**，T5 脚本按此表比对）

### 5.1 基础文案

| key | 文案 |
|---|---|
| title | TRPG 跑团玩家端 |
| nav.setup | 连接设置 |
| nav.table | 桌面 |
| nav.voice | 语音 |
| btn.test | 测试连接 |
| btn.resolve | 解析连接码 |
| btn.join | 加入跑团 |
| btn.leave | 离开桌面 |
| btn.submit | 提交行动 |
| btn.recStart | 开始录音 |
| btn.recStop | 停止并上传 |
| btn.query | 查询 |
| ph.server | 服务器地址，如 http://192.168.10.110:9210 |
| ph.code | 连接码，如 TABLE-XXXX |
| ph.playerId | 玩家 ID，如 pl-001 |
| ph.playerName | 昵称 |
| ph.action | 描述你要做什么…（必填） |
| ph.intent | 意图摘要（选填） |
| ph.deviceId | 设备 ID |
| st.connecting | 连接中… |
| st.connected | 已连接 |
| st.reconnecting | 重连中… |
| st.closed | 已断开 |
| st.collecting | 行动收集中 |
| st.notCollecting | 当前不在行动收集阶段，请等待主持人开启回合 |
| st.submitted | 已提交，等待主持人结算 |
| st.duplicate | 重复提交已忽略 |
| st.emptyAction | 行动描述不能为空 |
| st.noTurn | 尚未开启回合 |
| st.noDevice | 无该设备记录 |
| err.net | 网络连接失败，请检查服务器地址与网络 |
| err.auth | 身份验证失败：token 无效或未启用该端 |
| err.notFound | 连接码不存在 |
| err.server | 服务端异常 |
| sec.role | 我的状态 |
| sec.turn | 回合 |
| sec.action | 行动 |
| sec.events | 事件流 |
| sec.voice | 语音 |
| sec.device | 录音设备 |

### 5.2 事件类型标签（F7 用，type → 中文标签，两端逐字相同）

| key | 文案 |
|---|---|
| ev.ACTION_SUBMITTED | 行动提交 |
| ev.TURN_STARTED | 回合开始 |
| ev.TURN_CLOSED | 回合结束 |
| ev.CHECK_RESOLVED | 检定 |
| ev.NARRATION_PROPOSED | 旁白待审 |
| ev.NARRATION_APPROVED | 旁白 |
| ev.NARRATION_EDITED | 旁白（已修订） |
| ev.NARRATION_REJECTED | 旁白（未通过） |
| ev.INFO_REVEALED | 公开信息 |
| ev.CLUE_GRANTED | 线索 |
| ev.BRANCH_TAKEN | 分支 |
| ev.BRANCH_OVERRIDDEN | 分支（已覆盖） |
| ev.TRANSCRIPT_APPENDED | 语音转写 |
| ev.TRANSCRIPT_READY | 语音转写完成 |
| ev.ROLE_ASSIGNED | 角色分配 |
| ev.EVIDENCE_DEALT | 证据发放 |
| ev.VOTE_CAST | 投票 |
| ev.TRUTH_REVEALED | 真相揭示 |
| ev.MAP_UPDATED | 地图更新 |
| ev.SESSION_SUMMARIZED | 场次小结 |
| ev.OTHER | 其他事件 |

---

### 5.3 客户端扩展文案命名空间 `ext.*`（v1.18 补充）

契约 §5.1/§5.2 是**冻结的固定文案集**（T5 按它们逐字比对）。两端 **MAY** 各自定义**扩展文案**（如录音降级提示 `ext.st.recordUnsupported`），但**必须**遵守：

- **命名空间**：一律放在 `ext.` 前缀下，**不得**混入 §5.1/§5.2 的冻结 key；
- **两端一致**：同一 `ext.*` key 集合、**逐字相同**的文案（由两端自检 + T5 断言保证，**契约不逐个枚举**）；
- **理由**：这类提示属实现细节，契约不宜冻结具体措辞；但**四端一致性要求仍然适用**，故用命名空间隔离 + 两端自检来兼顾。
- **验收建议（已落地）**：T5 的 parity 脚本已实现为**断言组 (m) `ext.*` 扩展文案（4 项）** —— 断言两端 `ext.*` 的 **key 集合相同**且**逐字文案相同**（当前两端各 **22** 条 `ext.*`，已同步）。
- ✅ **组 (m) 首跑即生效（价值验证）**：该断言**第一次运行就抓到 1 处真不一致** —— `ext.st.recordUnsupported` 两端措辞不同（PC「…需要 HTTPS 或 localhost」vs MP「…需要 HTTPS/localhost 且设备有可用麦克风」）。**队长裁决统一为 MP 版**，PC 端 **6 个文件**已改齐；**现组 (m) 4/4 PASS、parity 231 项 0 差异**。→ 证明本节的「命名空间隔离 + 两端自检」设计**确实能防住静默漂移**（此前无此约束，该差异会一直藏着）。
- 📌 **已冻结的 `ext.*` 条目（队长裁决，两端逐字采用）**：`ext.st.recordUnsupported` = **「当前环境不支持录音（需要 HTTPS/localhost 且设备有可用麦克风）」**（本契约记录该裁决以防再漂移；其余 `ext.*` 仍按上文「两端一致、契约不枚举」执行）。

---

## 6. 一致性自检的**解析契约**（供 T5 的 packaging/parity-check.mjs 消费）

> 📊 **当前 parity 基线（T1 实测 2026-09-25）：233 项断言 / 0 差异**。分组：
> `(0)` 契约结构守卫 **1** ｜ 目录存在性 **2** ｜ `(a)` 令牌值 **56**（28×2）｜ `(b)` 固定文案 **122**（61×2）｜ `(c)` F11/F12 排除 **4** ｜ `(d)` 无 9321 **2** ｜ `(e)` 功能清单 F1–F10 **20** ｜ `(f)` tokens 文件 **2** ｜ `(g)` strings 文件 **3** ｜ `(h)` info.ws 误用排除 **2** ｜ `(i)` F7 渲染顺序 seq 降序 **3** ｜ `(j)` F7 请求带 `token=` **2** ｜ `(k)` WS 不推进游标（**含 4 类落盘/推进写法**）**2** ｜ `(l)` 取数口径 **6**（增量 limit=50 / **首次必须做法 (a)** / 排空续拉，各 2）｜ `(m)` `ext.*` 扩展文案 **4** ｜ `(n)` **WS 静默降级 2**（§3.4.2：连不上/403/被拒/断开 → 不报错、不阻塞、不改文案；**静态 + 运行时双层** —— 静态断言只拦「把 WS 回调接到状态行」这类实现错误，**完整验证靠运行时自测** `packaging/_t3wssilent.mjs`，当前 **6/6 PASS**）。
> → 合计 **233**，脚本自带「与断言总数一致」自校验。**引用 parity 数字时请以工具重跑输出为准**（勿引用历史批次的 227 等旧值）。

- §2 令牌：抓取本文件中**第一个** ~~~json 代码块，JSON.parse 后逐值比对（颜色 hex 逐字符、px 数值逐字符）。
- §5 文案：抓取 §5.1 与 §5.2 两张 markdown 表，每行格式为「竖线 key 竖线 文案 竖线」，解析为 {key: 文案}，**逐字**（含全角标点、省略号、括号）比对。
- 断言：(a) 每个令牌值在两端均出现；(b) 每条固定文案在两端均出现；(c) 两端均不出现「掷骰」「私语」关键字；(d) 两端均无 9321 引用。
- 两端自查产物：clients/web-player/tokens.json 与 strings.json、clients/miniprogram/tokens.wxss 与 strings.json 必须与本节解析结果一致。

### 6.1 两个会让 (c)/(d) 断言误 FAIL 的坑（T3/T4/T5 必读）

1. **关键字纪律**：T5 脚本断言「两端均不出现 掷骰 / 私语」。因此 **server/player-web/ 与 clients/miniprogram/ 下的任何文件（含注释、README、测试、JSON）都不得出现「掷骰」「私语」字样**。F11/F12「本轮不做」的**原因说明只能写在** docs/ROADMAP-DEFERRED.md 与交付说明里，**不要**写进客户端代码或客户端 README。
2. **扫描目录纪律**：T5 按 brief 扫描 server/player-web/* 与 clients/miniprogram/**。T3 的产出目录是 clients/web-player/，**必须先同步到 server/player-web/ 再跑 parity**，否则 T3 侧会被判为「缺失」而误 FAIL。T3 交付时必须说明已同步（或由 T7 统一同步）。

---

## 7. 实现约束与已知风险（T2/T3/T4 **必须遵守 / 必须知悉**）

### 7.1 硬约束

1. **不得改 /app**（主持端 React UI 及其 bundle 一律不动）。
2. **不得新增 WS 帧**（ws_protocol.py 冻结：S→C 8 类 + PING，C→S 6 类）。
3. **/access 既有 11 端点零行为变化**；只允许新增 additive 端点。
4. **PC 玩家端零构建**：纯原生 HTML/CSS/JS，无 npm、无 CDN 外链、无打包步骤。
5. **小程序不得引用 9321**（中转层已废除）；不得引用 npm 包。
6. **两端功能集合必须完全相同**（F1–F10 都有，F11/F12 都没有）。
7. token **不得硬编码**在源码里，**不得写入日志**；recorder token 绝不下发到玩家端。

### 7.2 已知风险（如实记录，不隐瞒）

| # | 风险 | 影响 | 本轮处置 |
|---|---|---|---|
| **R1** | **事件流端点无可见性过滤**：GET /api/campaigns/{c}/events 返回**全部**事件，不做 viewer 过滤（WS 路径有 viewer_may_see，REST 路径没有）。私密 payload 会被所有玩家拉取到。⚠️ **与 R7 叠加**：R7 加固后 `/api/tables` 已封 → **枚举面已消除**（匿名者无法自行枚举 campaign_id）；但 `/api/campaigns/*/events` 被白名单**放行**且**无鉴权** → **读取面残留**：**一旦 campaign_id 经其它途径泄露**（演示链接/截图/日志/URL 分享），其事件流即可被公网匿名读取；且因本条**无 viewer 过滤**，匿名者读到的是**全部**事件（含 player_id 与 action 文本）。verifier 实测：公网匿名 `GET /api/campaigns/c_f7probe/events` → **200**（`c_t1probe`、`c_probe` 同）。 | 私语类事件可能对非目标玩家可见；公网暴露期对匿名者可读 | 客户端**必须**按事件 payload 的 scope 与 targets 做展示过滤（scope=public、或 targets 含本人、或 condition_met 才显示）；并记入 ROADMAP-DEFERRED.md。建议 T2 追加 viewer 参数做服务端过滤（additive），本轮不阻塞。**⚠️ R7 叠加的取舍（已知并记录）**：F7 主通道该端点**无鉴权**，而 R7 加固白名单**必须放行** `/api/campaigns/*/events`（否则 F7 挂）→ 公网暴露期内匿名者可读事件流。**已采用的缓解**：① 客户端**一律带 `?token=`**（§4.1 F7），使服务端后续加鉴权成为**纯服务端 additive 变更**；② 建议 T2 给该端点加 token 校验 + viewer 可见性过滤；③ 暴露窗口最小化（演示结束即停隧道）。<br>⚠️ **与 §3.4.2 STATE_DELTA 并列登记（v1.25，verifier 提出）**：**非 public 事件详情共有两条外泄路径** —— **① 本条**（REST 事件流无服务端 viewer 过滤）与 **② WS STATE_DELTA 实为房间级广播**（Hub 的 viewer_may_see 只过滤 WHISPER / NARRATION_PENDING / JOB_STATUS）。**两条必须一起修**：只修一条（例如给 REST 加 viewer 过滤却仍用带 payload 的 STATE_DELTA 回退）**仍会外泄**。→ 建议 T2 加 viewer 过滤时**同时覆盖 REST 读取与 STATE_DELTA 发布路径**；已请 integrator 在 ROADMAP-DEFERRED.md **并列登记**。 |
| **R2** | turn.state 取值集合不一致：projector 写 COLLECTING / CLOSED / RESOLVING，而 ws_protocol.TurnState 声明 COLLECTING / CLOSING / RESOLVING / DISTRIBUTED / ADVANCED（CLOSED 不在其中）。 | 客户端若按字面枚举严格匹配会漏状态 | 客户端**只把 COLLECTING 当作可提交**，其余状态**原样显示字符串**，**不得**因未知状态崩溃或隐藏状态行。 |
| **R3** | TABLES 注册表是**进程内内存态**（app/web/rest.py 注释明示），重启即丢。 | 重启后连接码解析失败 | 属既有行为，本轮不改；验收时重启后需重新开桌（T6 注意）。 |
| **R4** | /access/info 的 ws 字段值 /access/ws 是**误导性**的（§1.4）。 | 客户端连错地址 | 契约已明确禁用该字段作连接地址。 |
| **R5** | ~~WS 无下行发布方（§3.4）~~ → **✅ 已解决（2026-09-25）**：T2 按队长裁决落地 additive 发布路径后，**8 类下行帧已在生产生效**（verifier 真实握手收到 5 帧 `TURN_UPDATED`，seq 382–387，见 §3.4.2）。 | 原为「F7 实时性缺失」；现**实时路径可用** | **F7 主通道仍为 REST 轮询**（§3.4.1，完整性与兜底权威）；**WS 仍按 §3.4.2 作为可选增强**接入（不得成为依赖）—— 该设计对「已生效」与「未来再次不可用」都兼容，两端无需改代码。 |
| **R6** | **F-2：/access/mobile/action 的 req_id 幂等失效**。根因：`CommandBus.__init__` 是 `self.guard = guard or BranchGuard()`（app/app_core/command_bus.py:60），而 app/web/access.py 的 `mobile_action` **每请求新建 CommandBus 且不传入共享 guard** → `check_key`/`record_key` 的键存在**请求级实例**里，请求结束即丢弃，故跨请求永不判重。**T1 实测复现（2026-09-25，修复前基线）**：同一 req_id 提交两次 → 落 **2 条 ACTION_SUBMITTED**（seq 186/187），两次响应均为 `status:"ok"`（第二次本应 `status:"duplicate"`）。 | **AC-3.12 修复前必 FAIL**（已留基线）；**修复后已达标 → 现判 PASS** | ✅ **已修复，且 T1 于 2026-09-25 独立复验通过**：同一 req_id 两次提交 → 第 1 次 `status:"ok"`（`seqs:[480]`）、**第 2 次 `status:"duplicate"` 且 `seqs:[480]`（同一 seq）**，事件计数 **+1**（before 2 → after 3）。修复方式：**按 campaign 维度共享/持久化 BranchGuard**（只改 guard 类不够，必须改调用点；**不可用单一全局 guard**，否则跨 campaign 串扰）。**T1 独立复核修复形态（2026-09-25）**：与改造前备份 `trpg_backup_20260925-090549` 逐字节比对 —— `app/scheduler/branch_guard.py`（`E3FCC0FA97D79ABD…`）与 `app/app_core/command_bus.py`（`8C246E1229879B53…`）**SAME（一行未改）**，仅 `app/web/access.py` DIFF（新增共享 guard 表 + 新端点）→ **check_key/record_key/dispatch 的 duplicate 分支语义未动**，修复收敛在调用点，形态正确。**三重证据**：① T1 自跑探针（c_t1probe：2→3，只 +1，第 2 次 `status:"duplicate"`）；② server-eng 的 A/B 对照探针（临时 DB、不污染共享库：旧写法 2 条 / 新写法 1 条，RESULT: PASS）；③ **生产实测**（独立 campaign `c_f2_1790332232` 连发 3 次 → ACTION_SUBMITTED **仅 1 条**；T1 复核 events total=2、ACTION_SUBMITTED=1；`c_idem_1790331498` 同）。基线证据：evidence/T1-contract.txt §13、evidence/T2-f2-idempotency.txt。**客户端行为不变**（仍显示 st.duplicate）。 |
| **R7** | **公网暴露面**：实测 `/openapi.json`、`/docs`、`/redoc`、`/api/tables` 可**公网匿名**访问（队长实测）。 | 信息泄露与枚举风险（API schema、表清单暴露） | 契约侧要求：**公网暴露期必须落实加固**（命名隧道 + Cloudflare Access，或 Nginx/Caddy + **路径白名单**）。**必须白名单、不得黑名单**；放行 `/api/health`、`/player/`、`/player/*`、`/access/*`、`/ws`、`/api/campaigns/*/events`，其余 → 404。⚠️ **不得全局 Basic Auth / 不得用 Access 保护整个站点**（会把 /player/ 与 /api/health 变成 401/登录页 → 18b 必 FAIL）；Basic Auth 只可加在 /app/。🚫 **不得「整个 /api 全封」**（`GET /api/campaigns/{c}/events` 是 F7 主通道，封掉连带 AC-3 FAIL）。判据见 PLAN-ACCEPTANCE **AC-4 第 18b 条**；方案由 integrator 写入 docs/DEPLOY.md（已完成 §6.3.5）。**适用性**：仅在实际开启公网暴露时按上述验收；若最终不开启暴露（无隧道进程、无 80/443 监听），该条判 **N/A（未暴露）+ 方案已备**，不算 FAIL。**实测更新（2026-09-25，外网侧，权威）**：cloudflared **quick tunnel**（远程 pid 7696，**旧地址** `<旧地址A（已失效）>` → 127.0.0.1:9210，**已被下方新地址取代**）下 `/docs`、`/redoc`、`/openapi.json`(31KB)、`/api/tables` **全部匿名 200**；`/api/tables` **泄露全部 table_id/campaign_id**（含调试遗留 `t_probe`/`c_probe`、`t_demo`/`c_demo`）→ **当时 R7 处于激活/FAIL 状态（该状态已于 2026-09-25 加固落地后解除，见本行末「已加固并生效」）**。⚠️ **quick tunnel（trycloudflare）不支持 Cloudflare Access** → 方案 (a) 实际需**命名隧道 + 自有域名**，否则只能走 (b) 反代白名单；**推荐默认走 (b)**（反代 + 路径白名单 + Basic Auth 仅作用于 /app/）。⚠️ **与 R1 叠加**：匿名者凭 campaign_id 可直接拉事件流。证据：evidence/T6-public-exposure.md。（T1 曾于 00:30Z 测得无隧道进程，隧道于 ~01:03Z 启动 —— 暴露为**间歇性**。）**✅ 已加固并生效（队长裁决 2026-09-25：按方案 (a) 落实，隧道不必停）**：加固方式 = **cloudflared 配置式路径白名单**（`C:\trpg-tunnel\config.yml` + 计划任务 `trpg-tunnel-cf`，已补 onstart 触发器 / 30s 延迟）；**加固 v2（2026-09-25）**：放行 `^/player`、`^/access`、`^/api/campaigns`、`^/api/health$`、`^/ws$`，其余 → `http_status:404`；**v2 已移除 `^/app`（主持端控制台不再公网可达）**。
> ⚠️ **公网地址是易变的（队长裁决：任何交付文档都不得写死域名）**：quick tunnel 每次重启会换随机子域，**以日志动态解析为准**：
> `Get-Content C:\trpg-tunnel\cloudflared.log | Select-String 'trycloudflare' | Select-Object -Last 1`
> `current-url.txt` 与 `tunnel.url.txt` **都可能滞后，仅作交叉参考**（历史上出现过只更新其一的情况）。**本文件不记录具体域名** —— 本轮地址已轮换 **3 次**，历史地址均已 **530**；复验前务必按上述命令重取。
>
> 🚫 **桌面旧目录下的取址文件已废弃、不得引用**：实测 `…\Desktop\<乱码目录名>tools\tunnel.url.txt` 的 **mtime 反而比权威文件更晚、内容却是过期地址**（2026-09-25：权威 09:37:35 vs 旧目录 09:34:47，后者内容不可用）—— 证明**有脚本在旧目录又写了一次过期值**。
> **光靠文档约束读者不够**（下一个人从旧目录跑脚本照样拿到过期值）。故要求：**取址脚本在非 `C:\trpg-tunnel` 目录必须拒绝写入并退出**（**仅告警不足**），旧目录文件应删除或改名 `.obsolete`。
> ✅ **已执行（2026-09-25，队长处置，T1 实测复核）**：旧目录文件已改名为 **`tunnel.url.txt.obsolete`**，**全盘已无 `tunnel.url.txt` 残留**；写入端约束已授权 integrator 执行（其 `tunnel-cf.ps1` 已更新）。→ **本条结案，契约与现实一致**。

| 公网路径 | 实测 | 判读 |
|---|---|---|
| `/api/health` | **200** | ✅ 判据要求保持可用 |
| `/access/info` | **200**（带 token；无 token 401） | ✅ 玩家端必需 |
| `/api/campaigns/c_demo/events` | **200** | ✅ F7 主通道必需（见残留 2） |
| `/player/` | **200**（len=5380，T2 已部署） | ✅ 玩家端入口可用 |
| `/app/` | **404**（加固 v2 已移除） | ✅ 残留 1 已解决 |
| `/openapi.json` `/docs` `/redoc` `/api/tables` `/mcp` `/metrics/latency` | **全部 404** | ✅ 敏感面已封 |

→ **R7 公网口径判为「已加固并生效」**（原「激活/FAIL」状态解除）。

⚠️ **关键机制：公网加固 ≠ 内网加固（integrator 指出，T1 已实测确认）**：白名单在 **cloudflared 隧道边缘**生效，**只作用于经隧道进来的流量**；局域网设备**直连 9210** 时请求根本不经过 cloudflared，**完全不受白名单约束**。
T1 实测对照（2026-09-25T09:36Z，同一时刻两组）：
| 路径 | 公网（经隧道） | 局域网直连 192.168.10.110:9210 |
|---|---|---|
| `/docs` `/redoc` `/openapi.json` `/api/tables` `/app` | **404** | **全部 200**（openapi.json 37KB） |
| `/player/` `/api/health` | **200** | **200** |

⚠️ **残余风险（局域网侧，本轮不阻塞但必须记录）**：局域网内**任何设备**仍可匿名访问 `/openapi.json`、`/docs`、`/redoc`、`/api/tables`（枚举 table/campaign）与 `/app`（KP 控制台）。要真正收口（含内网）必须上 **反代 + Basic Auth + 路径限制**（DEPLOY.md §6.3.5，方案 (b)）或收紧防火墙来源。
⚠️ **残留 2（仍在，读取面）**：`/api/campaigns/*/events` 被白名单放行且**无鉴权**，公网/内网均匿名可用。**枚举面已消除**（`/api/tables` 已 404，匿名者无法自行枚举 campaign_id），**读取面残留**：campaign_id 一旦经其它途径泄露即可匿名读全部事件。verifier 实测公网匿名 200（`c_f7probe` / `c_t1probe` / `c_probe`）。📏 **引用响应长度时须连同 `?limit` 一起标注**：该响应 len 随 limit 变化（`limit=3` ≈ 874–886；另一处记录 3611），**仅比长度会被误判为数据不一致**。→ 缓解见 R1；生产建议给该端点加服务端可见性过滤或对匿名关闭。
**加固不影响两端功能**：玩家端只用 §1.1 的 8 个端点，全部在白名单内。 |

---

## 8. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| **v1.31** | 2026-09-26 | 落实**队长批准的 UI 统一重构**（依据 docs/SPEC-UI-REFACTOR.md v1.0；色调与风格参考「魔都 TRPG」cnmods.net 实测令牌）：① **§2 令牌块整体替换为深色主题** —— `bg #17191a` / `card #212625` / `text rgba(255,255,255,0.82)` / `muted #b9b9b9` / `border rgba(255,255,255,0.14)` / `accent #ffbb70` / `accentText #1a1206` / `ok #63e2b7` / `warn #f2c97d` / `err #e88080` / `focus #ffbb70` / `chipBg #2b3237`；`radius` card `10px→6px`、ctl `8px→4px`、chip `999px` 不变；`space`/`font`/`layout` **逐值不变**。**键名与结构不变、仅值变** → parity 组 (a) 仍为 56 项，**§6 基线仍为 233 项**（令牌值替换不改变断言条数，故无需扩到 234+）。② **§2 组件规格表 `.err-bar` 的两个硬编码色**由 v1.30 的浅色版（浅红底／浅红边；**字面值不在此处内联**，见 v1.30 冻结快照 `evidence/_t2_baseline/pre_snapshot/docs/CROSS-END-CONTRACT.md` 的 §2 组件表 `.err-bar` 行）改为**深色版**（`bg #2a1f20` / `border 1px #4a2f31`，`color=err`）—— 小程序端 `tokens.wxss` 的 `--color-errBarBg/--color-errBarBorder` 两变量、PC 端 `app.css` 的 `.err-bar` 规则须同步，否则 (f)/视觉一致性 FAIL。③ **功能零变化**为硬约束：不得改任何 `id` / `data-*` / 事件绑定 / 请求逻辑 / 轮询与 WS 逻辑 / 文案文本 / `strings.json` 与 `strings.js` 键值（契约 §5.1/§5.2 固定文案逐字不变）。④ **两端视觉逐值一致**，仅保留本文件既有两条允许差异（容器宽度自适应、导航形态）。⑤ **§1.5 冻结 6 项 sha256 不含本文件**（6 项为 events.py / ws_protocol.py / allowlist.yml / docs/contracts/*3），故本次升版不与冻结条款冲突；升级后须复测该 6 项 sha256 **未变**。⑥ 纪律：**先升版再改实现**（未升版即改 = AC-6 FAIL）；两端任一端漏改令牌值 → parity (a)/(f) FAIL。⑦ **§2 新增「导航平台限制」补充（队长批准，落点两处：§2「两端差异只允许」行末的边界说明 + §2 组件表之后的补充块）**：微信原生 tabBar 仅可配 `color/selectedColor/backgroundColor/borderStyle`（`borderStyle` 枚举仅 `black|white`）⇒ 导航**颜色必须对齐**（tabBar 底 `#262c31` / 未选中 `#b9b9b9` / 选中 `#ffbb70` / navigationBar 底 `#262c31`，落点 `clients/miniprogram/app.json`），**选中态装饰（字重 / pill 底 / 指示条 / 1px 分隔线）在小程序端物理上无法实现**，计为已知平台限制、不算一致性差异。⑧ **§2「两端差异只允许」新增第 3 条允许差异（队长裁决 2026-09-26 09:33:04）**：移动端按钮触控适配 —— `.btn` / `.btn-primary` 在小程序端整行铺满 + 上间距、PC 端按内容定宽；属移动端点击目标适配，不计为视觉一致性差异。 |
| v1 | 2026-09-25 | 初稿（基于计划假设，未实测） |
| **v1.30** | 2026-09-25 | 落实**队长「状态行语义」裁决**：① §3.4.2 新增「🚫 **WS 状态不得产生可见文案**」——两端均为**单行状态行**，**四态由轮询驱动**，WS 的 open/close/error **不得**映射为 st.* 文案、不得另加一行（理由：WS 为可选增强，其可用性不得改变用户可见界面，否则同功能在不同网络环境文案不同、破坏四端一致性）；② §4 F10 行与 §4 明细同步该语义（并注明「WS 为可选增强，不影响文案」）。→ 本条同时**为 mp-eng 的 `wsLine` 反向断言提供了契约依据**（其 `tests/contract.test.js:488-489` 禁止 `wsLine` 与本节一致）。 |
| **v1.29** | 2026-09-25 | ① §4.1 F7 的「**seq 非连续**」条款归纳**该错误假设已致三处**（契约做法 (b) / verifier parity #27d / web-eng `_t3f7tail.mjs`，后两者均为「tip-49」式断言）并立规：**凡涉及 seq 差值或连续性的断言与实现，必须改写为与环境无关的形式**（按条数或与实测返回值逐项比对）；② §6 基线由 231 更新为 **233**，新增组 `(n)` **WS 静默降级 2 项**。 |
| **v1.28** | 2026-09-25 | **修正 v1.24 的遗漏（web-eng 指出，有效）**：v1.24 只把 §4.1 F7 的 (b) 标为废弃，**§3.4.1 第 208/210 行仍写「做法 (a) 或 (b)」** → 契约自相矛盾（web-eng 读 §3.4.1 后合理认为 (b) 仍可用）。现 **§3.4.1 与 §4.1 F7 一致：首次只允许做法 (a)**，并在 v1.10 变更行标注「或 (b)」已被取代。**教训**：废弃某规则时须**全仓检索该规则的所有表述**（本次 grep `tip-50|做法 (b)` 共 11 处，规范文本 2 处遗漏）。 |
| **v1.27** | 2026-09-25 | 采纳 mp-eng 的**防误读建议**：§4.1 F7「实测缺口」历史段（v1.24 已改为「当时」口径）**再显式标注「下列 `:548-549` / `:128-129` 均为修复前行号，勿再引用」** —— 该段是本轮 (j) 被反复误报的高频引用点，加标记以彻底切断「照抄旧行号」路径。 |
| **v1.26** | 2026-09-25 | 落实**队长裁决（同一 seq 竞态）**：§3.4.2 新增「**去重键 = seq；同 seq 时轮询结果覆盖 WS 帧条目（REST 胜出）**」+ 两端逐字一致的实现约束（轮询 ingest 不得跳过、须直接重写该键；WS 帧不得覆盖同 seq）+ 实测核对（PC `app.js:527-546` 已去 `continue`；MP `mergeFrame:127` 不覆盖 + `mergeFeed:112` 总覆盖 → 两种到达顺序均 REST 胜出）。理由：REST 是主通道与权威表示（标签按 §5.2 `ev.*`），且规则须与网络时序无关。 |
| **v1.25** | 2026-09-25 | 采纳 verifier 的**综合观察**并并列登记：**非 public 事件详情有两条外泄路径** —— **R1**（REST /api/campaigns/*/events 无服务端 viewer 过滤）与 **§3.4.2 STATE_DELTA**（实为房间级广播）。二者**必须一起修**，只修一条仍会外泄；已在 R1 行与 §3.4.2 双向交叉引用，并请 integrator 在 ROADMAP-DEFERRED.md 并列登记。 |
| **v1.24** | 2026-09-25 | 落实**队长三项裁决**：① **做法 (b) 正式废弃**（§4.1 F7：**首次只允许 (a)**；(b) 标 🚫 已废弃并保留实测证据）；② §7.2 R7 **结案** —— 旧目录文件已改名 `.obsolete`（T1 实测无残留）、写入端约束已授权 integrator 执行，契约与现实一致；③ **修正陈旧现在时表述**：§4.1 F7 内「组 (j) **当前** 0/2 FAIL」→ 当时状态 + **现已 2/2 PASS**（PC `app.js:551` / MP `api-client.js:135`）—— 这正是此前多轮「旧快照误报」的文本源头之一；④ §6 顶部新增**当前 parity 基线 231 项的完整分组明细**（供引用时对齐；契约内原本**不含** "227" 字样，故按队长意图把 **231** 写实）。 |
| **v1.23** | 2026-09-25 | §5.3 记录**组 (m) 首跑即抓到真不一致**（`ext.st.recordUnsupported`：PC「…需要 HTTPS 或 localhost」vs MP「…需要 HTTPS/localhost 且设备有可用麦克风」）→ **队长裁决统一为 MP 版**，PC 端 6 个文件改齐，**现 4/4 PASS / parity 231 项 0 差异**；并把该条目列为**已冻结 `ext.*` 条目**（防再漂移）。→ 验证了 §5.3「命名空间隔离 + 两端自检」设计的有效性。 |
| **v1.22** | 2026-09-25 | 采纳 verifier 的**断言覆盖交叉核对**（其核对实现时发现清单漏一类）：§3.4.2 源码级断言清单 **4 类 → 5 类**，补上 **`setStorageSync('trpg_last_seq_…')`（小程序直接落盘）**；并新增要求「**契约给出的断言清单须与 parity 断言实现交叉核对覆盖，双向回写**」；§5.3 注明 T5 已把 ext.* 实现为**断言组 (m)（4 项）**（当前 parity 合计 **231** 项）。 |
| **v1.21** | 2026-09-25 | 充实 **R6 证据链**（AC-3.12 的 PASS 依据）：T1 独立复核 —— 与备份逐字节比对确认 `branch_guard.py`/`command_bus.py` **SAME（guard 语义一行未改）**、仅 `access.py` 变（修复收敛在调用点，形态正确）；三重证据 = T1 探针（c_t1probe 2→3 只 +1）+ server-eng A/B 对照探针（旧 2 条/新 1 条）+ **生产实测**（`c_f2_1790332232` 连发 3 次仅落 1 条，T1 复核 total=2/ACTION_SUBMITTED=1）。 |
| **v1.20** | 2026-09-25 | 采纳 server-eng 的实现反馈（含一处**我方规格的安全缺陷**）：§3.4.2 新增「**STATE_DELTA 实际可见性**」—— 冻结件写 scope=viewer「可见子集」，但 Hub 的 viewer_may_see **只过滤 WHISPER/NARRATION_PENDING/JOB_STATUS** → **STATE_DELTA 实为房间级广播**；故**任何发布路径不得在 STATE_DELTA 携带非 public 事件详情**，T2 回退帧一律 `{type, redacted:true}`。T1 另复核其首版 9 类脱敏白名单**不完整**（缺 NARRATION_PROPOSED/EDITED/REJECTED、INFO_REVEALED、ROLE_ASSIGNED、CHECK_RESOLVED.seed、MAP_UPDATED），已写入 ENDPOINT-SPEC-NEW §8.1 并推荐「回退帧一律不带 payload」。 |
| **v1.19** | 2026-09-25 | 采纳 verifier 的 **seq 非连续**发现（其修正 #27d 断言时发现）并 T1 实测确认：**单 campaign 内 seq 不连续**（seq 共享/全局递增，跨团交错）→ ① §4.1 F7 **做法 (b) `since=tip-50` 标为「实测不可靠、不建议采用」**（实测 c_demo 21 条仅返 **2** 条、c_t1probe 4 条仅返 **1** 条；做法 (a) 不受影响，两端现均用 (a)）；② 新增「**seq 非连续**」事实，明确**取数只能按条数（limit）、不能按 seq 跨度推算**；③ 同步 PARITY-CHECKLIST 1b（首次应断言 (a)，不再把 (b) 当可接受选项）。**是否正式废弃 (b) 待队长裁决。** |
| **v1.18** | 2026-09-25 | ① 新增 **§5.3 `ext.*` 扩展文案命名空间**：契约 §5.1/§5.2 冻结集之外的扩展文案须置于 `ext.` 前缀、**两端 key 集合与文案逐字一致**（由两端自检 + T5 额外断言保证，契约不逐个枚举；当前两端各 22 条）；② §4.1 F7 明确「**接口顺序 ≠ 渲染顺序**」（该端点原始返回本就是 seq 升序；对象键遍历顺序亦不构成排序）。 |
| **v1.17** | 2026-09-25 | 采纳 mp-eng 的补充细节：§3.4.2「游标权威」由「**不推进**」扩展为「**不推进、也不落盘**」—— 理由②：用 WS 帧写 `trpg_last_seq_<table>` 会**污染冷启动游标**，下次启动以该值为 `since` 同样漏事件；并给出源码级断言清单（`lastSeq = frame.seq` / `cursor = f.seq` / `saveLastSeq` / `localStorage.setItem('trpg_last_seq_…')` 命中即 FAIL）。MP 已实测 `saveLastSeq` 命中 0。 |
| **v1.16** | 2026-09-25 | 采纳 mp-eng 指出的**事实错误**：① **R6 行更新为「✅ 已修复并实测」** —— T1 独立复验：同 req_id 第 2 次返回 `status:"duplicate"` 且 `seqs` 同值、事件 **+1**（2→3）→ **AC-3.12 现判 PASS**；② **v1.12 变更行中「组 (j) 当时 0/2 FAIL」改为「当时状态」**并注明**现已 2/2 PASS**（PC `app.js:551`、MP `api-client.js:135`），避免 T5/T6 按 FAIL 记假失败。 |
| **v1.15** | 2026-09-25 | **修正 v1.13 的遗漏（自查发现）**：v1.13 更新了 §3.4.2/§3.4.3/§3.4.4 反映「发布路径已生效」，但**漏改 §7.2 风险表 R5 行**（仍写「WS 无下行发布方」）→ 现标 **✅ 已解决**，并重申 F7 主通道仍为轮询、WS 仍为增强。同步 docs/ENDPOINT-SPEC-NEW.md 的背景段加历史限定。 |
| **v1.14** | 2026-09-25 | 采纳 verifier 的运维建议：§7.2 R7 新增 **🚫 桌面旧目录取址文件已废弃、不得引用**（实测其 mtime 反比权威文件更晚而内容过期 → 有脚本在旧目录误写），并要求 **取址脚本在非 `C:\trpg-tunnel` 目录拒绝写入并退出（仅告警不足）**，旧文件应删除或改名 `.obsolete`。 |
| **v1.13** | 2026-09-25 | 采纳 verifier 实测：**T2 的 additive 发布路径已落地并生效**（真实握手收到 5 帧 `TURN_UPDATED` seq 382–387）→ 更新 §3.4.2（标注已生效）、§3.4.3（AC-3.13 两条路径均已达成：轮询 1085ms / WS 业务帧）、§3.4.4（「从不 publish」改为**仅描述 T1 测量时点**，并说明设计对两种情形都兼容）；R7 补「引用响应长度须连同 `?limit` 标注」的精度提醒。 |
| **v1.12** | 2026-09-25 | 采纳 verifier 实测缺口并**强化 F7 前向兼容要求**：明确该端点**必须用查询参数 `?token=`**（首次与增量都要带），**`Authorization: Bearer` 头不构成等价替代**（§1.2 的「两者等价」在此端点不适用）；**当时** parity 组 (j) 为 **0/2 FAIL**（PC `app.js:548-549`、MP `lib/api-client.js:128-129` 均未带 query 参数）→ **现已补齐：两端均已带 `?token=`（PC `app.js:551`、MP `api-client.js:135`），组 (j) 2/2 PASS**。（原表述为当时状态，勿按 FAIL 记录。） |
| **v1.11** | 2026-09-25 | 采纳 integrator 的**公网/内网口径区分**并实测确认：§7.2 R7 新增「**公网加固 ≠ 内网加固**」机制（白名单只在 cloudflared 边缘生效，局域网直连 9210 不经隧道）与**公网/内网对照实测表**；记录**加固 v2 已移除 `^/app`**（残留 1 解决）、**公网地址易变**（v1.11 当时记为「以 `C:\trpg-tunnel\current-url.txt` 为准」；**该取址口径已被队长 2026-09-25 后续裁决取代** → 现为**以日志动态解析为准**，`current-url.txt` 可能滞后；见 §7.2 R7 正文）与**局域网侧残余风险**（/docs /redoc /openapi.json /api/tables /app 内网仍 200，需反代才能收口）。 |
| **v1.10** | 2026-09-25 | **队长裁决统一取数口径**（推翻 v1.9 的增量 1000）：**首次 = `limit=1000`（做法 a）或 `since=tip-50&limit=50`（做法 b，采用者须在文档写明）；增量 = `limit=50` + 拉满续拉最多 3 轮**。（⚠️ **其中的「或 (b)」已被 v1.24 废弃取代** —— 现行只允许做法 (a)，本条保留作历史记录。）§3.4.1 与 §4.1 F7 已同步为同一套，自相矛盾消除。⚠️ 连带更正：v1.9 曾要求增量 1000，故此前对 web-eng/mp-eng 的「增量改 1000」指示**已作废**（PC 原本的 limit=50 + 排空循环本就符合本裁决）。 |
| **v1.9** | 2026-09-25 | 采纳 mp-eng 发现的**契约自相矛盾**并修正：§3.4.1 原写 `limit=50`、§4.1 F7(a) 写 `limit=1000`，同一次轮询两处不一致 → **统一为 limit=1000**；新增**排空规则**（返回条数 == limit 时用推进后游标续拉，最多 3 轮，防滞后不丢事件）；§3.4.2 明确 **last_seq 只由轮询推进、WS 帧不推进游标**（避免 WS 只发布部分事件时跳过中间 seq 造成漏事件）与 **seq 为去重键**。 |
| **v1.8** | 2026-09-25 | 采纳 mp-eng 提出的**R7 白名单 × F7 无鉴权端点**张力问题：§1.1 事件流行与 §4.1 F7 新增**前向兼容要求**（客户端请求一律带 `?token=<mobile token>`；服务端当前忽略、带上无害，使后续服务端加鉴权成为纯 additive 变更，两端无需改代码）；§7.2 R1 记录该取舍与三条缓解（带 token / 建议 T2 加 token+viewer 过滤 / 暴露窗口最小化）。 |
| **v1.7** | 2026-09-25 | 落实**队长 F7 排序裁决**：§4 表与 §4.1 由「seq 升序、取尾部 50 条」改为「**seq 降序渲染（最新在最上）、展示最新 50 条**」；并写死**实测取数陷阱**（`since=-1&limit=N` 返回**最旧** N 条）与两种正确做法（(a) limit=1000 取尾部 50；(b) 先取 tip 再 since=tip-50）**（其中 (b) 已被 v1.24 废弃）**。同步 PARITY-CHECKLIST F7。 |
| **v1.6** | 2026-09-25 | 采纳 integrator 的 AC-4 18b 落地反馈：§7.2 R7 细化加固口径 —— **必须路径白名单（非黑名单）**、**不得全局 Basic Auth / 不得用 Access 保护整个站点**（否则 /player/ 与 /api/health 变 401/登录页 → 18b 必 FAIL）、**不得「整个 /api 全封」**（会连带 AC-3 FAIL）；同步 PLAN-ACCEPTANCE AC-4 第 18b 条与 AC-7 第 28 条（五件 → 实测 6 项）。 |
| **v1.5** | 2026-09-25 | 采纳 verifier 补充实测并独立复现：§3.1 新增**对照实验表**（/ws 有效 → 101；/ws 各种失败、/access/ws 带有效 token、/nosuchroute、/api/health 的 Upgrade 尝试 → **一律 403**），据此把裁定加强为「**任何失败的 WS 升级都归一 403，客户端无法区分 token 错/参数错/路径错/不支持 WS/网络故障**，必须先用 GET /access/info 校验」。纯澄清，不改接口/令牌/文案。 |
| **v1.4** | 2026-09-25 | 落实队长新增两项裁决：① §7.2 新增 **R6 = F-2（/access/mobile/action 的 req_id 幂等失效，根因 BranchGuard 实例级）**，含 T1 实测复现的修复前 FAIL 基线与「修复后须实测只 +1」的验收规则；② §7.2 新增 **R7 = 公网暴露面**（/openapi.json、/docs、/redoc、/api/tables 公网匿名可达），要求公网暴露期落实加固并指向 AC-4 第 18b 条。 |
| **v1.3** | 2026-09-25 | 落实**队长 AC-3.13 裁决（方案 A）**：① §3.4 重写为显式降级规则（§3.4.1 轮询=主通道且必须实现；§3.4.2 WS 广播=可选增强，含静默降级、seq 去重、ACK/ERROR 忽略等两端逐字一致的接入规则；§3.4.3 升级版 AC-3.13 判据「WS 可用则实时达标，否则 ≤5s 轮询可见，任一达成即 PASS」；§3.4.4 历史背景）；② 新增 §1.6 鉴权矩阵与 401/403 陷阱（_require_player_end，403 mobile_only）；③ 同步 docs/PLAN-ACCEPTANCE.md 的 AC-3.13 表述。 |
| **v1.2** | 2026-09-25 | 采纳 verifier 复核意见并**以实测裁定**：① §3.1 内联「WS 路径恒为 /ws、禁用 info.ws 作连接地址」；② 明确拒绝的可观测形态为**握手 HTTP 403**（源码 close(4400) 永不到达客户端，以 403 为准，四种情形实测一致）；③ §3.5 明确心跳依据为**服务端 PING 到达**、客户端 PING 无 PONG、30s 无服务端帧即重连；④ 按队长裁决把冻结契约由「五件」更正为**实测 6 项**（3 代码/配置 + docs/contracts/ 下 3 个文档）并内联 6 个 sha256（§1.5）；⑤ 新增环境事实块（远程项目根以 C:\Users\Administrator\Desktop\黑客松开发文档\trpg 为准，计划书路径少一层）。 |
| **v1.1** | 2026-09-25 | **实测定稿**：① 修正 WS 真实路径为 /ws 并标注 /access/info.ws 陷阱；② 明确三个命名空间与 WS 字段名 kind；③ 新增 §1.1 实测端点表（含鉴权与 data 字段）；④ **F7 主通道由 WS 下行帧改为 GET /api/campaigns/{c}/events**（因生产无发布方，实测证据见 §3.4）；⑤ 新增 ACK / ERROR 帧容错要求；⑥ 新增 §5.2 事件类型标签表；⑦ 新增 §6 解析契约、§7 实现约束与 R1–R5 风险；⑧ 补 st.noDevice 文案。 |
