# TRPG 收尾 + 验收 总体计划与验收标准（v1）

> 目标主机：SSH `gzq110` → 192.168.10.110（Windows，用户 Administrator）
> 项目真源：`C:\Users\Administrator\Desktop\黑客松开发文档\trpg`（主持端服务器，FastAPI，端口 9210，当前 health 0.1.0-t12）
> 本机工作根：`E:\dsh3080工作区存放位置\dsh_gzq1\trpg_delivery`
> 调度方式：AgentTeams（队长编排，成员执行），本文件为唯一验收基线。

---

## 0. 现状事实（已实测，2026-09-25）

| 项 | 事实 |
|---|---|
| 服务端 | 9210 LISTENING，`/api/health` = `{"status":"ok","version":"0.1.0-t12"}`，`/app/` 200，防火墙 `trpg-9210` 入站 Allow |
| 局域网 | `http://192.168.10.110:9210` 从本机可达（health 200）；另有 192.168.56.1（VirtualBox 网段） |
| 公网 | 未发现任何穿透/反代进程（待侦察确认）；需提供内网穿透/反代方案与脚本 |
| 三端 token | `configs/access_config.yaml`：mobile=`f06e4ec6…`、webapp=`f4a8dc57…`、recorder=`6b52cd78…`，三端 enabled |
| 主持端 UI | `/app`（React 18 + vite5 预构建 bundle，已部署可用） |
| 前端源码 | `trpg/web/src` 存在，但 **web/ 下无 package.json / vite.config / node_modules** → 现成 React 无法重建；且源码比已部署 bundle 旧（源码 PlayerPanel 仍是 mockTransport） |
| 数据 | `/api/tables` 为空，无 campaign/事件 → 玩家端目前"无团可加入" |
| 玩家端服务端 | 队友交付包内 `player-gateway-prototype`（Node，127.0.0.1:9321）是**多余中转层**，与 9210 `/access` 契约重复 → 本计划要求合并去除 |
| 玩家端小程序 | 交付包内 `paotuan-echo-miniprogram` 存在，但指向 9321 网关的自定义 `/api/player/*`，**不是**服务端 `/access/*` 契约 |
| 工具链 | 远程 python 3.12.10 + pytest 9.1.1；本机 node v24 + npm 11 + pnpm 11；npm registry 可达 |

## 1. 交付物（用户要求）

1. **封装版服务端（主持端服务器）** —— 可独立部署的包：源码 + 启动/停止脚本 + 配置 + 网络可达性提示 + 文档。
2. **客户端 A：PC 浏览器版（玩家端）** —— 由服务端托管，浏览器直开即用。
3. **客户端 B：微信小程序版（移动端）** —— 微信开发者工具可直接导入运行。

**四端一致性铁律**：PC 版与小程序版**功能清单完全一致、视觉设计令牌完全一致**，不得出现"一端有、另一端无"。

## 2. 架构决策（收尾关键）

### 2.1 合并"玩家端服务端" → 主持端服务器
- 删除 9321 中转网关的角色：**玩家端客户端（PC/小程序）直连 9210 的 `/access/*` + `/ws`**。
- 服务端新增 **`POST /access/player/audio`**（mobile token 鉴权，服务端内部持 recorder token 转发/复用落库）→ 让玩家端在不持有 recorder token 的前提下也能上传录音（token 端隔离 R5 不破）。
- 旧网关 `player-gateway-prototype` 仅作历史归档，**不进交付物**。

### 2.2 PC 玩家端实现路线
- **不重建 React 主站**（缺构建配置 + 源码落后于部署产物，风险高、收益低）。主持端 `/app` 维持现状不动。
- **新增零构建的玩家端页面**：`server/player-web/`（原生 HTML/CSS/JS，无 npm 依赖），由服务端挂载到 **`/player/`**（新路径，纯 additive，不碰 `/app`）。
- 该页面同时是"PC 浏览器版"与"手机浏览器版"（响应式），并作为小程序端的**视觉基准**。

### 2.3 四端一致的落地机制
- 冻结一份 **《跨端契约与设计令牌》**（`docs/CROSS-END-CONTRACT.md`）：设计令牌（颜色/圆角/间距/字号/组件类名）、功能清单（每项含端点/帧/验收步骤）、状态与错误文案。
- 小程序用 WXSS 复刻同一套令牌（同 hex、同圆角、同间距、同字号），页面结构与文案逐项对齐。
- 验收用**同一份功能清单**分别驱动两个客户端跑一遍，逐项打勾（parity checklist）。

### 2.4 功能范围（以现有冻结契约为界）

| # | 功能 | PC(web) | 小程序 | 后端支撑 |
|---|---|---|---|---|
| F1 | 服务器发现 / 手填地址 / 测试连接 | ✅ | ✅ | `GET /access/info` |
| F2 | 连接码（房间号）→ 自动解析 table+campaign | ✅ | ✅ | `GET /access/table/resolve`（**新增**） |
| F3 | 玩家身份（ID/昵称）本地保存 | ✅ | ✅ | localStorage / wx storage |
| F4 | 状态轮询（回合/计数/事件提示） | ✅ | ✅ | `GET /access/mobile/state` |
| F5 | 实时订阅（8 类下行帧 + PING + 断线重连 + last_seq 对账） | ✅ | ✅ | `/ws` |
| F6 | 行动提交（COLLECTING 门控 + req_id 幂等 + 重复提交提示） | ✅ | ✅ | `POST /access/mobile/action` |
| F7 | 旁白/公开信息/私语/分支/任务 事件流展示 | ✅ | ✅ | WS 下行帧 |
| F8 | 语音录制与上传（整段） | ✅ | ✅ | `POST /access/player/audio`（**新增**） |
| F9 | 录音设备状态只读查询 | ✅ | ✅ | `GET /access/device/status` |
| F10 | 断线对账与错误提示（统一文案） | ✅ | ✅ | 客户端 |
| F11 | 骰点托盘（玩家主动掷骰） | ⛔ | ⛔ | **延期**：服务端 `/ws COMMAND` 仅 ACK 无副作用，需新增写路径（属契约变更，本轮不做） |
| F12 | 玩家发私语 | ⛔ | ⛔ | **延期**：同上（无玩家侧发起点） |

> F11/F12 记入 `docs/ROADMAP-DEFERRED.md`，两端一致地不实现（一致性优先于功能数量）。

## 3. 服务端新增（全部 additive，不改冻结契约）

| 端点 | 鉴权 | 用途 |
|---|---|---|
| `GET /player/` + `/player/{path}` | 无 | 静态托管玩家端页面（`server/player-web/`） |
| `GET /access/table/resolve?code=` | 任意启用端 | 连接码/table_id → `{table_id, campaign, name, exists}` |
| `POST /access/player/audio` | **mobile 端** | 玩家录音上传（服务端内部走 recorder 语义落库 + 后台 STT），返回与 `/access/audio_upload` 同构 |
| `POST /access/host/table` | **webapp(KP) 端** | 一键开桌（`{table_id, campaign_id, ruleset}`）→ 让"无团可加入"不再发生 |
| `POST /access/host/turn` | **webapp(KP) 端** | 开启行动窗（`{campaign, window_sec}`）→ 玩家端进入 COLLECTING 可提交 |

**冻结契约不可改**：`trpg/agent/events.py`、`app/web/ws_protocol.py`、`trpg/agent/allowlist.yml`、`docs/contracts/*`、REST 20 端点、`/access` 既有 11 端点签名。

## 4. 任务分解（AgentTeams DAG）

```
T1 契约冻结（令牌+功能清单+端点规格）        [planner]
 ├─ T2 服务端：player-web 托管 + 4 个新端点 + 封装包   [engineer-server]
 ├─ T3 PC 玩家端：/player 页面（零构建）               [engineer-web]   ← 依赖 T1
 └─ T4 小程序玩家端：/access 直连改造                  [engineer-mp]    ← 依赖 T1
      ├─ T5 四端一致性审查（逐项 parity）              [verifier]       ← 依赖 T2/T3/T4
      └─ T6 端到端验收（PC+小程序+LAN+公网+冻结契约回归）[verifier]      ← 依赖 T2/T3/T4
           └─ T7 封装与文档交付（交付包 + README + 部署手册）[integrator] ← 依赖 T5/T6
```

## 5. 验收标准（DoD，逐条可执行）

### AC-1 服务端（主持端）正常运行
1. `GET /api/health` → 200 且 `status=ok`（远程 9210 实测）。
2. `GET /app/` → 200；`GET /player/` → 200 且返回玩家端页面（含设计令牌）。
3. `netstat` 显示 9210 LISTENING 于 `0.0.0.0`；防火墙入站 Allow 规则存在。
4. 局域网第二台设备（本机）`http://192.168.10.110:9210/api/health` → 200。
5. `python -m pytest tests/ -q` → 全绿（与改造前基线一致或更多，不得回归）。
    **已知 flaky 的处置规则（2026-09-25 补充，T1 复核）**：允许存在**既存 flaky**，但必须同时满足三条才可判 PASS：
    (a) **至少一次完整全绿运行**的原始输出（同一次运行内全绿，不接受「多次拼凑」）；
    (b) **非回归证据必须覆盖「被测代码」**，而不只是「测试文件」的 mtime —— 须说明该用例**是否触达本轮改动过的模块**；
    (c) 记录 flaky 的**具体机制**（哪个时序假设）与复现率。
    **本轮的既存 flaky**：`tests/test_ws_security.py:132` `test_heartbeat_loop_calls_ping_all_periodically`（约 10 跑 7 过 3 挂）。
    **机制（T1 读码确认）**：该用例**直接单测 `heartbeat_loop`**（`app/web/ws.py`，mtime 09-24 **未被本轮改动**），并用 **FakeHub** —— **完全不经过 `app/main.py`**（故 `main.py` 今日 09:57 的改动与它无关）；其断言为 `interval=0.01` + `sleep(0.035)` 后 `assert len(calls) >= 2`，**是纯时序假设**，机器负载高时事件循环排不到第二轮即挂。
    **结论**：判 **非回归**（成立）；**建议修断言使其确定性**（如改 `>= 1`、或放大窗口、或用事件/假时钟驱动），修好后本项可无条件全绿。
6. 新增端点鉴权矩阵：`/access/player/audio` 无 token→401、webapp token→403、mobile token→200；
   `/access/host/*` 无 token→401、mobile token→403、webapp token→200；`/access/table/resolve` 无 token→401。

### AC-2 玩家端可连接（合并后无中转层）
7. PC 玩家端：浏览器打开 `http://192.168.10.110:9210/player/`，填入服务器地址 + 连接码 + 玩家 ID → "测试连接"成功（显示服务版本 + 三端启用状态）。
8. 小程序：微信开发者工具导入 `clients/miniprogram`，同一套输入 → "测试连接"成功。
9. 两个客户端加入同一桌后，`GET /access/mobile/state` 显示的 `turn.state=COLLECTING` 在两端一致。
10. **无 9321**：交付物中不存在运行中的玩家端中转服务；两端请求直指 9210（证据：抓取请求 URL）。

### AC-3 跨端游戏（真实对局）
11. 主持端 `/access/host/table` 开桌 + `/access/host/turn` 开回合后，PC 与小程序同时提交行动 → 服务端事件流出现 2 条 `ACTION_SUBMITTED`（`GET /api/campaigns/{c}/events` 证据）。
12. 幂等：同一 `req_id` 重复提交 → 服务端只落 1 条事件，两端都显示"重复提交已忽略"。
    **复验要求（队长裁决 2026-09-25，F-2）**：已知缺陷 —— `/access/mobile/action` 的 `req_id` 幂等**当前失效**（根因 `CommandBus.__init__` 的 `self.guard = guard or BranchGuard()` 为**实例级**，而 `mobile_action` 每请求新建 bus 且不传共享 guard，键随请求丢弃）。T1 已实测复现并留基线：同 `req_id` 两次提交 → 落 **2 条 `ACTION_SUBMITTED`**（seq 186/187），两次响应均 `status:"ok"`。
    **判定规则**：**修复前本条必 FAIL**（基线证据：evidence/T1-contract.txt §13）；**修复后须实测「同 `req_id` 两次提交 → 事件流只 +1 条 `ACTION_SUBMITTED`，且第二次响应 `data.status == "duplicate"`」**，并附修复前后事件计数对比。
    ✅ **已实测达标（2026-09-25，T1 独立复验 + mp-eng 复验）**：第 1 次 `status:"ok"`（`seqs:[480]`）、**第 2 次 `status:"duplicate"` 且同 seq**，事件计数 **+1**（2 → 3）→ **本条现判 PASS**。
13. WS 广播：KP 侧触发一帧 `NARRATION_APPROVED`（或服务端 publish）后，PC 与小程序**都**在 5s 内显示同一条旁白。
    **判据（队长裁决 2026-09-25，升级版）**：WS 广播可用时按**实时**达标；**若 WS 广播不可用则退化为「≤5s 轮询可见」**（F7 主通道为 `GET /api/campaigns/{c}/events`，2s 轮询）。**两条路径任一达成即 PASS**；验收须给出所用路径的证据（WS 原始帧，或轮询响应 + 时间戳）。依据见 docs/CROSS-END-CONTRACT.md §3.4。
14. 断线重连：断开网络 10s 后恢复，两端均自动重连并补齐 `last_seq` 之后的事件（无重复、无丢失）。
15. 非 COLLECTING 状态提交 → 两端均给出同样的拒绝文案（同字符串）。

### AC-4 远程可达（局域网 + 公网）
16. 局域网：`http://192.168.10.110:9210/player/` 在**另一台机器**打开可用（本机实测）。
17. 公网：提供并实测至少一种穿透/反代路径（优先 `cloudflared` 快速隧道或 `frp`；若外部网络/账号不可用，则给出**可直接执行的脚本 + 配置模板 + 逐步手册**，并把该项标记为"环境受限，脚本已备"）。公网地址访问 `/player/` 与 `/api/health` 均 200。
18. 小程序合法域名：给出"不校验合法域名（开发）+ HTTPS 域名（生产）"两种模式的配置说明与截图/步骤。
18b. **公网暴露面安全（队长裁决 2026-09-25 新增；编号用 18b 以免打乱既有 19–30 号）**：实测公网可**匿名**访问 `/openapi.json`、`/docs`、`/redoc`、`/api/tables`。因此**公网暴露期必须给出并落实加固方案**，采用其一（或并用）：
    (a) **命名隧道 + Cloudflare Access**：仅暴露必要路径，并以 Access 策略（Service Token / 指定邮箱域）做前置鉴权；**必须为「必需匿名路径」配置 Bypass 策略**（Access 默认保护整个 hostname）。
    (b) **Nginx/Caddy 反向代理 + 路径白名单**：**必须用白名单（allowlist）而非黑名单** —— 放行 `/api/health`、`/player/` 与 `/player/*`、`/access/*`、`/ws`（保留 Upgrade 头）、`/api/campaigns/*/events`（F7 主通道，契约 §1.1 明示无鉴权）；其余一切（含 `/docs`、`/redoc`、`/openapi.json`、`/api/tables`）→ **404**；HTTPS 证书有效。
    ⚠️ **关键约束（违反则本条直接 FAIL）**：**不得使用「全局 Basic Auth」或「用 Access 保护整个站点」** —— 判据要求 `/player/` 与 `/api/health` **匿名 200**，全局鉴权会把它们变成 401 / 登录页，本条**必 FAIL**。因此 Basic Auth 只可加在 `/app/`（可选），白名单路径必须保持匿名。
    🚫 **不得用「整个 /api 全封」的粗粒度规则** —— `GET /api/campaigns/{c}/events` 是 F7 主通道，封掉会使两端事件流全挂、连带 **AC-3 也 FAIL**。
    **验收**：公网 `/player/` 与 `/api/health` 均 **200（匿名，不带任何凭据）**；且 `/docs`、`/redoc`、`/openapi.json`、`/api/tables` 在公网**不再匿名可达**（404/403 或 Access 登录页）；须附 **curl 证据**并含匿名回归（`/api/campaigns/{c}/events` 仍 200）。加固方案由 integrator 写入 `docs/DEPLOY.md`。
    **适用性（重要，避免误判 FAIL）**：本条**只在实际开启公网暴露时**按上述验收；若最终交付**不开启公网暴露**（远程无隧道进程、无 80/443 监听、仅 9210 局域网监听），本条判 **N/A（未暴露）+ 方案已备**，**不算 FAIL**，但必须在报告里附「未暴露」的实测证据（进程/监听核查输出）。
        **实测记录（**加固前**，2026-09-25T00:57Z，外网侧；现状见下方「已加固并生效」）**：cloudflared **quick tunnel**（远程 pid 7696，`<旧地址A（已失效）>`）下 `/docs`、`/redoc`、`/openapi.json`(31KB)、`/api/tables` **全部匿名 200**，且 `/api/tables` **泄露全部 table_id/campaign_id**（含调试遗留 `t_probe`/`c_probe`、`t_demo`/`c_demo`）→ **本条当前判 FAIL**。证据：evidence/T6-public-exposure.md。
    ⚠️ **quick tunnel 的固有局限**：`trycloudflare.com` 快速隧道**不支持 Cloudflare Access 策略** → 方案 (a) 实际需**命名隧道 + 自有域名**，否则只能走 (b) 反代白名单。
    ✅ **落地建议（推荐默认走 (b)）**：因 quick tunnel 无法承载 Access，**建议以方案 (b)「反代 + 路径白名单（+ Basic Auth 仅作用于 /app/）」为默认落地方式**，(a) 仅在有自有域名时作为替代。
    ✅ **已加固并生效，本条可判定（队长裁决 + T1 独立复测）**：加固 = **cloudflared 配置式路径白名单**（`C:\trpg-tunnel\config.yml` + 计划任务 `trpg-tunnel-cf` 已补 onstart 触发器/30s 延迟）。
    ⚠️ **本条口径限定为「公网」**（经隧道的流量）；**局域网口径另见 18c**。加固 **v2**（2026-09-25）已移除 `^/app`，实测公网 `/app/` = **404**（残留 1 解决）。
    ⚠️ **公网地址易变（不写死）**：quick tunnel 每次重启换随机子域，**以日志动态解析为准**（`current-url.txt` 可能滞后）：`Get-Content C:\trpg-tunnel\cloudflared.log | Select-String 'trycloudflare' | Select-Object -Last 1`。本轮已实测轮换 3 次，历史地址均已 **530**。
    **逐判据结论**：判据 3–6（`/openapi.json`、`/docs`、`/redoc`、`/api/tables` 不再匿名可达）→ **PASS**（实测全部 404，另 `/mcp`、`/metrics/latency` 亦 404）；判据 2（`/api/health` 匿名 200）→ **PASS**；判据 1（`/player/` 匿名 200）→ **PASS**（实测公网 `/player/` = 200，len=5380 —— **T2 已部署 player-web，不再"待 T2"**）。故本条现可判 **PASS**。
    ⚠️ **残留项**：① `/app`（KP 控制台）→ **已由加固 v2 解决**（公网 404）；② `/api/campaigns/*/events` 公网匿名 200（R1 残留；枚举入口 `/api/tables` 已封，风险降低）。

18c. **局域网暴露面（新增，队长裁决口径拆分后单列；本轮记为「残余风险」，不阻塞交付）**：
    > 🔗 **命名对应**：本条即 **integrator 在 ACCEPTANCE-REPORT 中的「18b-局域网」行**（= PLAN-ACCEPTANCE 18c「局域网暴露面」）。两份文档双向引用，避免口径对不上。
    ⚠️ **机制（integrator 指出、T1 实测确认）**：**公网加固 ≠ 内网加固** —— 白名单在 **cloudflared 隧道边缘**生效，只约束经隧道的流量；局域网设备**直连 `192.168.10.110:9210`** 不经隧道，**不受白名单约束**。
    **实测对照（2026-09-25T09:36Z，同一时刻两组）**：
    | 路径 | 公网（经隧道） | 局域网直连 |
    |---|---|---|
    | `/docs` `/redoc` `/openapi.json` `/api/tables` `/app` | **404** | **全部 200**（openapi.json 37KB） |
    | `/player/` `/api/health` | **200** | **200** |
    **判定**：局域网侧**未加固** → 内网任何设备可匿名枚举 table/campaign 并打开 KP 控制台。**本轮记为残余风险（不阻塞），但生产必须收口**：上 **反代 + Basic Auth + 路径限制**（DEPLOY.md §6.3.5 方案 (b)）或收紧防火墙来源。
    ⚠️ **注意**：**停掉隧道不会关闭局域网暴露** —— 要同时止血须一并收紧防火墙来源。
    ⚠️ **与 R1 叠加**：匿名者凭 `/api/tables` 拿到的 campaign_id 可直接拉取事件流（契约 §7 R1 无 viewer 过滤），故 18b 修复应**同时**考虑给事件流加服务端可见性过滤或对匿名者关闭该路径。
    说明：T1 于 00:30Z 曾实测「无隧道进程」，隧道于 **~01:03Z 启动**（pid 7696），故暴露为**间歇性**、且**当前正在暴露**。

### AC-5 封装交付物
19. `server/`：源码 + `start.bat` + `stop.bat` + `requirements.txt` + `configs/`；在**干净目录**执行 `start.bat` 后 health 200（不依赖远程既有环境）。
    ⚠️ **启动脚本须在 Windows PowerShell 5.1 下验证（v1.0 补充，2026-09-25 实测教训）**：`pwsh 7` 对编码/字节序标记更宽容，**会放过真问题** —— 本轮实测：`server/packaged/start.ps1` 缺 **UTF-8 BOM** 时，**PS 5.1 解析报 5 个错、服务起不来**，而 **pwsh 7 自检完全无感**。
    → **验收要求**：解压包内 **3 份 `.ps1`（assemble / start / stop）** 必须**在 PS 5.1 下**跑语法检查（`[System.Management.Automation.Language.Parser]::ParseFile` 或 `powershell.exe -NoProfile`）得到 **errors = 0**，并**保留原始输出**；**仅用 pwsh 7 自检不足以判定通过**。
    → **通用原则**：**验收工具的运行时要与交付目标运行时一致**（此处 = Windows PowerShell 5.1），否则自检方式不对会放过真问题。
    🧰 **附：编辑工具会剥离 BOM（2026-09-25 实测，integrator 踩到）**：`tools.edit` 等文本编辑工具**写回文件时会丢掉 UTF-8 BOM** → 编辑含中文的 `.ps1` 后，PS 5.1 立刻报语法错（与 `start.ps1` 那次同类）。**规则**：**凡含中文的 `.ps1`，每次编辑后都要重新补 BOM，并用 PS 5.1 解析器（不是 pwsh 7）复验**。
20. `clients/web-player/`：可直接拷到服务端 `server/player-web/` 生效；无 npm 依赖、无构建步骤。
21. `clients/miniprogram/`：微信开发者工具导入即跑（`project.config.json` 合法、无语法错误、无对 9321 的引用）。
22. `docs/`：`DEPLOY.md`（服务端部署+网络暴露）、`PLAYER-WEB.md`、`MINIPROGRAM.md`、`CROSS-END-CONTRACT.md`、`ROADMAP-DEFERRED.md`、`ACCEPTANCE-REPORT.md`。
23. 交付包 zip：`TRPG-交付包-v1.zip`，内含上述三件 + 文档 + 校验清单。

### AC-6 四端一致性
24. 设计令牌逐项相同（颜色 hex、圆角、间距、字号、按钮/卡片/徽章类名语义）：脚本比对两份令牌文件 → 0 差异。
25. 功能清单 F1–F10 逐项在两端均可用；F11/F12 两端均明确不提供（一致）。
26. 页面文案（按钮、占位符、错误提示、状态行）逐条相同：脚本比对文案表 → 0 差异。
27. 移动端与 PC 端**功能数量与名称完全相同**：parity 清单两端打勾结果一致。

### AC-7 不破坏既有
28. 冻结契约 **6 项**文件哈希与改造前一致（3 个代码/配置 + docs/contracts/ 下 3 个文档；队长已裁定「五件」的写法是把 docs/contracts/* 当成 1 项所致）。6 项与 SHA256 见 docs/CROSS-END-CONTRACT.md §1.5 表。
29. `/app`（主持端 UI）仍 200 且 bundle 引用不变。
30. 既有 `/access` 11 端点行为不变（既有测试用例全绿）。

## 6. 证据与落盘

- 所有证据写入 `E:\dsh3080工作区存放位置\dsh_gzq1\trpg_delivery\evidence\`（命令 + 原始输出 + 截图）。
- 远程改动前先备份（`trpg_backup_<ts>` 目录 + 冻结契约哈希清单）。
- 最终 `ACCEPTANCE-REPORT.md` 逐条对照 AC-1…AC-7 给出 PASS/FAIL + 证据文件路径。

---

## 7. 队长实测补充与裁决（v1.1，2026-09-25）

### 7.1 已实测事实（覆盖 v1 中的推测）
| 项 | 实测结论 |
|---|---|
| WS 路径 | 真实 WS 路由 = `/ws`（main.py:50）；`/access/ws` 是 GET 说明端点，`/access/info.ws` 指向它 → **禁止**当 WS URL 用 |
| WS 鉴权失败 | 表现为**握手 HTTP 403**（accept 前 close(4400)，Starlette 转 403），非 WS 关闭码 4400 |
| WS 心跳 | 服务端每 15s 下发 `{"kind":"PING","ts":...}`；客户端上行 PING 被忽略且无 PONG |
| WS 业务帧 | **改造前生产环境从不调用 Hub.publish** → 实测只收到 PING（证据：packaging/_wsprobe.mjs 25s 观测 2 帧均为 PING） |
| 开回合路径 | REST 无开回合端点；command_bus 已注册 `start_turn`（command_bus.py:262）；`POST /api/campaigns/{c}/events` 写 TURN_STARTED 实测可使 `turn.state=COLLECTING` |
| 鉴权语义 | `_require_end("mobile")` 对合法但端不匹配的 token 返回 **401**；403 只出现在 `_require_kp_end/_require_recorder_end` 家族 |
| 演示桌 | `t_demo / c_demo`，turn_no=1，state=COLLECTING（已开，window_sec=3600） |
| 公网 | cloudflared quick tunnel 已作为计划任务 `trpg-tunnel-cf` 常驻（已补 onstart 触发器 + 30s 延迟）。**地址每次重启会变，任何文档都不写死域名；以日志动态解析为准**（`cloudflared.log | Select-String 'trycloudflare' | Select-Object -Last 1`；`current-url.txt` 可能滞后、仅作交叉参考）。本轮已轮换 **3 次**，历史地址均已 **530**。实测公网 /api/health 200、/player/ 200、/access/info 200（无 token 401）、/api/campaigns/c_demo/events 200；/docs /redoc /openapi.json /api/tables /app /mcp **均 404**（加固 v2） |
| 公网暴露面 | **加固前**：`/openapi.json`(200)、`/docs`(200)、`/redoc`(200)、`/api/tables`(200，无鉴权) → 存在无鉴权 API 风险。**加固后（队长裁决 2026-09-25，方案 (a) 云隧道路径白名单，实测生效）**：上述四者 + `/mcp` + `/metrics/latency` **全部 404**；判据见 AC-4 第 **18b** 条与契约 §7.2 **R7**。**v2 已移除 `^/app` → 公网 `/app/` 亦 404（原残留① 已解决）**。**残留（唯一）**：`/api/campaigns/*/events` 匿名可用（R1 范畴） |
| 冻结契约 | 实测 6 项（3 代码 + 3 docs/contracts），按 6 项 SHA256 全等验收 |
| 回归基线 | pytest 541 passed / 0 failed |

### 7.2 裁决
1. **AC-3.13 升级**：T2 追加 additive 发布路径（EventStore.append 单一收口 best-effort 调 hub.publish；严格复用冻结 8 帧；失败回退 `STATE_DELTA(event)`；不改协议、不改既有端点）。
   判据：KP 侧触发 `NARRATION_APPROVED` 后，两端 **5s 内**显示同一条旁白；若 WS 广播不可用，接受「≤5s 轮询可见」并记录降级原因。
2. **AC-1.6 修正**：`/access/player/audio` 对 webapp token 必须返回 **403 mobile_only**（新增 `_require_player_end` 同构实现），不是 401。
3. `/access/host/turn` 必须走 `CommandBus.dispatch("start_turn", {...})`（唯一写口 + 幂等）。
4. 冻结契约按 6 项哈希验收。
5. F11/F12 两端一致不做，原因只写 `docs/ROADMAP-DEFERRED.md`；客户端目录内任何文件（含注释/README/测试）不得出现相应关键词（避免 parity 误判）。
6. 交付物中不得存在运行中的 9321 中转服务。
7. T3 产出（clients/web-player/）必须先同步到 server/player-web/ 再跑 parity。

### 7.3 小程序验证的现实约束（新增 AC-6.28）
- 本机与远程均**未安装微信开发者工具**（实测：D:\wechat 仅为微信客户端；无 cli.bat）。安装尝试由子代理执行，成功则以真实编译/截图为证据；失败则本项判定为「环境受限」。
- 受限时的替代证据（必须齐备，缺一不可）：
  (a) `node clients/miniprogram/tests/contract.test.js` 全过；
  (b) 全部 .js 经 `node --check`、全部 .json 经 `JSON.parse` 通过；
  (c) 用 Node 模拟小程序请求**直打真实 9210**（info / table-resolve / mobile-state / mobile-action / player-audio）原始输出；
  (d) parity-check.mjs 0 差异（令牌/文案/禁用词/无 9321）。
