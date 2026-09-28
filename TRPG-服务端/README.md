# TRPG 跑团辅助系统 · 服务端

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688.svg)](https://fastapi.tiangolo.com/)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6.svg)](#快速开始)
[![Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-orange.svg)](CHANGELOG.md)

> 主持端（KP）服务器：**FastAPI + WebSocket 实时事件流 + 玩家端页面托管**。
> 默认自适应端口启动，启动后落盘发现文件，供配套客户端自动对接。

配套客户端仓库：**trpg-client**（玩家端静态页面 + 本地启动器）。

---

## 简介

本仓库是 TRPG（桌上角色扮演游戏）跑团辅助系统的**服务端**，负责：

- **主持端控制台**：预构建的 React UI，挂载在 `/app/`。
- **玩家端页面**：零构建原生 HTML/CSS/JS，挂载在 `/player/`（PC / 移动浏览器均可访问）。
- **实时事件流**：WebSocket `/ws` 广播团内事件，服务端每 15s 下发 `PING` 心跳。
- **接入层**：三端 token（`mobile` / `webapp` / `recorder`）鉴权与**连接码解析**。
- **领域内核**：事件溯源存储（SQLite WAL）、规则判定、`agent/` 裁判与场景/时间协调器。

设计目标是**开箱即用**：一份代码，双击 `start.bat` 即可在局域网上开桌；
端口被占用时自动顺延，不需要手工改配置。

---

## 本轮（R2）新增能力

> 以下为 R2 迭代新增，全部为 **additive**：既有端点签名、响应体与冻结契约（`docs/CROSS-END-CONTRACT.md` v1.1）零变化。
> 端点明细见 [`docs/ENDPOINT-SPEC-NEW.md`](docs/ENDPOINT-SPEC-NEW.md)；NPC 相关契约变更见 [`docs/R2-NPC-CONTRACT-CHANGE.md`](docs/R2-NPC-CONTRACT-CHANGE.md)。

| 能力 | 说明 | 端点 |
|---|---|---|
| **R10 场景交互** | 按房间下发可交互物（含 `anchor` 热区坐标与动作集），动作分「普通检定」与「敏感动作」 | `GET /api/campaigns/{campaign}/interactives`、`POST /api/campaigns/{campaign}/interact` |
| **R11/R17/R18/R19 统一审批总线** | 敏感交互 / 字幕 / 感知通知统一进待审队列，主持人拍板后才产生结果；**拍板前玩家侧看不到任何候选正文** | `GET\|POST /api/campaigns/{campaign}/approvals`、`GET /api/campaigns/{campaign}/pipeline/queue`、`GET /api/campaigns/{campaign}/pipeline/mine`、`POST /api/campaigns/{campaign}/pipeline/resolve` |
| **定向投递（防泄漏）** | 决定事件（`NARRATION_APPROVED` / `NARRATION_EDITED`）只带**脱敏正文**，真实内容经 `INFO_REVEALED(scope=whisper, targets=[…])` 定向下发 —— 避免被 `ws_bridge` 映射成 public 帧而广播全桌 | 内部：`app/web/pipeline_api.py::deliver_after_decision` |
| **R9 暗骰门禁** | `CHECK_RESOLVED` 中归属 KP 的暗骰（`card_id` 为 kp/gm/keeper… 或为空），非 KP 侧**整条不可见**（`clip_event` 与 `leaked_literals` 同一判据） | `app/domain/visibility.py::is_dark_roll` |
| **R28–R31 NPC 自主性** | NPC 技能 / 记忆 / 自主行动与提案；NPC 提案走**同一条**审批总线；默认解锁（`TRPG_NPC_GATE=locked` 可锁回旧 403 语义） | `GET /api/campaigns/{campaign}/npc/state`、`/npc/proposals`、`/npc/skills` 等 |
| **R23 规则包 · R4/R5/R15/R16/R20 总览** | 规则包浏览与总览聚合（只读、additive） | `/api/rules/*`、`/api/campaigns/{campaign}/overview` |
| **事件流服务端裁剪** | `/api/campaigns/{campaign}/events` 支持 `viewer` / `scope`：非 KP 视图在**服务端**裁剪（响应含 `filtered=true`），不再是「服务端全量 + 客户端自行过滤」 | `GET /api/campaigns/{campaign}/events`、`GET /access/mobile/events` |
| **GM 前端源码树随包** | `web/src/`（源码，32 个文件）随包交付，解决「包内无 GM 源码」；`web/dist/` 是**单一构建出口**（只由构建者重建） | — |

### 已知限制与注意事项

- **静态资源缓存**：`/player/app.js` 等静态响应只带 `ETag` / `Last-Modified`，**不带 `Cache-Control`**。更新前端后浏览器可能仍执行旧脚本，验收时请强制刷新（`Ctrl+F5`）。
- **交付包不含 `tests/`**：见下文「开发与测试」。
- **`.bak-*` 备份文件**：开发期回滚点（如 `README.md.bak-t5`）在封装前应清理。

---

## 快速开始

### 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（启动脚本基于 cmd + PowerShell 5.1） |
| Python | **3.12+**（实测 3.12.10 / 3.13.1） |
| 依赖 | 见 `requirements.txt`（仅运行必需，不含 torch 等重依赖） |

### 一键启动

```bat
:: 1) 首次运行：安装依赖
python -m pip install -r requirements.txt

:: 2) 启动（默认从 9210 起，被占用则自动顺延到 9211、9212 … 直到 9230）
start.bat

:: 指定端口启动（若该端口已被占用，将报错退出而不是静默换端口）
start.bat 9211
```

启动脚本会依次执行：

1. 检测 Python 是否安装且版本 ≥ 3.12；
2. 检查运行依赖是否齐备；
3. 探测端口占用（若本服务已在运行 → 直接打印现有地址并退出）；
4. 后台拉起 uvicorn；
5. 轮询 `/api/health`（最长 30s，返回 200 且 `status=ok` 才算成功）；
6. 打印**实际访问地址**（含局域网 IP）与连接码提示。

### 停止

```bat
stop.bat          :: 读取 run/server.port 定位端口，优雅停止并确认端口释放
```

### 退出码

| 码 | 含义 |
|---|---|
| `0` | 成功（或服务已在运行） |
| `1` | 环境 / 依赖错误 |
| `2` | 端口冲突（显式指定端口时） |
| `3` | 健康检查超时 |

### 端口发现文件

启动成功后会在仓库根目录的 `run/` 下落盘下列文件（`run/` 已加入 `.gitignore`）：

| 文件 | 内容 |
|---|---|
| `run/server.port` | 实际端口（纯数字） |
| `run/server.json` | `{"port":9211,"host":"0.0.0.0","pid":1234,"url":"...","deployment_id":"<uuid>","install_dir":"<部署根绝对路径>","started_at":"..."}` |
| `run/deployment.id` | 本部署的稳定身份（UUID v4，首次启动生成后每次复用） |

配套客户端会优先读取 `../trpg-server/run/server.json` 自动对接，无需手工填地址。

### 多部署共存（同一台机器装了多个 TRPG 服务端时）

`GET /api/health` 只回答「**活着**」：它的响应在不同部署/版本之间**逐字节同构**
（`{"status":"ok","version":"0.1.0-t12","ts":...}`），**不能**用来判断「端口上的是不是**本部署**」。
为此新增了**身份端点**（additive，既有端点签名与行为零变化）：

```bat
curl http://127.0.0.1:9210/__trpg_server__
:: {"service":"trpg-server","ok":true,"pid":2188,"port":9210,
::  "deployment_id":"5c5b15c4-9900-4df5-9ac4-c2103bdf246c",
::  "install_dir":"C:\\...\\trpg-server","version":"0.1.0-t12"}
```

- **无鉴权**：只暴露部署身份信息，不含任何密钥/令牌。
- `deployment_id`：每个部署实例**唯一且稳定** —— 首次启动时在部署根生成 `run/deployment.id`
  （UUID v4），之后每次启动复用；该文件不可写时退化为「部署根绝对路径的 SHA256 前 16 位」。
- `install_dir`：部署根的**绝对路径**，是「是不是同一个部署」的直接判据。

`start.bat` / `stop.bat` 的「是不是自己」一律以该端点为准
（`install_dir` 规范化后相等，**或** `deployment_id` 相等）：

| 端口上的占用者 | `start.bat <该端口>` | 无参数 `start.bat` |
|---|---|---|
| **本部署** | 幂等：`exit 0`，不重复起第二个实例 | 复用该端口：`exit 0` |
| **别的 TRPG 部署 / 旧版服务端** | **真冲突**：`exit 2` + 打印占用者 PID（**不覆写** `run/server.json`） | **跳过**它，落第一个**空闲**端口 |
| 其它任意进程 | **真冲突**：`exit 2` | **跳过**它 |

`stop.bat` 只停**本部署**：先做命令行防误杀校验（`_serve.py` / `trpg-server`），
再用身份端点确认「是本部署」；不是本部署一律拒绝停止并 `exit 1`。
身份端点不可达（旧版服务端）时退回命令行校验，**不放宽**守卫。

---

## 目录结构

```
trpg-server/
├─ start.bat / stop.bat        纯 ASCII 包装器（规避 cmd 代码页问题）
├─ scripts/
│  ├─ start.ps1                启动真实逻辑（UTF-8 带 BOM）
│  └─ stop.ps1                 停止真实逻辑（UTF-8 带 BOM）
├─ app/                        服务端应用
│  ├─ main.py                  FastAPI 入口（含 @app.websocket("/ws")）
│  ├─ web/
│  │  ├─ access.py             接入层：三端 token 鉴权、连接码解析
│  │  ├─ rest.py               REST 接口
│  │  ├─ ws.py                 WebSocket Hub（15s PING 心跳）
│  │  ├─ ws_bridge.py          事件 → WS 广播桥
│  │  ├─ pipeline_api.py       R2：场景交互 / 统一审批总线 / 定向投递（additive）
│  │  └─ static.py             静态托管：/app/ 与 /player/
│  ├─ app_core/                命令总线（唯一写口 + 幂等）
│  │  └─ interactions.py       R2：场景交互物解析与动作判定（additive）
│  ├─ npc/                     R2：NPC 技能 / 记忆 / 自主行动与提案（additive）
│  ├─ domain/                  领域模型与事件定义
│  ├─ store/                   事件溯源存储（SQLite WAL）、投影、快照
│  ├─ rules/                   规则判定与骰点
│  ├─ scheduler/               调度与分支保护
│  ├─ mcp/                     MCP 工具服务
│  ├─ voice/                   语音（STT/TTS，无 key 时自动降级）
│  └─ agent/                   LLM 裁判接入（审批、上下文构建、记忆、槽位）
├─ trpg/                       领域内核
│  └─ agent/                   裁判、规则内核、场景/时间协调器（冻结契约）
├─ configs/                    配置（access_config.yaml —— 三端 token）
├─ modules/ rulepacks/ skills/ 业务模块、规则包、技能
├─ web/dist/                   主持端 UI（React 预构建产物，挂载于 /app/）
├─ player-web/                 玩家端页面（零构建，挂载于 /player/）
├─ data/                       运行期数据（首次启动自建；仓库仅保留 .gitkeep）
├─ run/                        端口发现文件（运行期生成，已 gitignore）
├─ docs/                       部署 / 运维 / 跨端契约 / 验收 等文档
├─ tests/                      自动化测试（pytest）
├─ requirements.txt            运行依赖
├─ pyproject.toml              项目元数据与工具配置
└─ Makefile                    常用任务快捷入口
```

---

## 端点速览

统一响应包裹：成功 `{ok:true,data:{...},code:0}`；失败 `{ok:false,error:"...",code:<http>}`。
> 例外：`/api/health` 与 `/__trpg_server__` 返回**裸 JSON**（不套 `{ok,data,code}` 包裹）。

| 用途 | 端点 | 鉴权 |
|---|---|---|
| 健康检查 | `GET /api/health` | 无 |
| 部署身份 | `GET /__trpg_server__` | 无 |
| 主持端 UI | `GET /app/` | 无 |
| 玩家端页面 | `GET /player/` | 无 |
| 服务信息 | `GET /access/info` | 任一启用端 token |
| 连接码解析 | `GET /access/table/resolve?code=` | 任一启用端 token |
| 会话状态 | `GET /access/mobile/state?table_id=` | mobile |
| 提交行动 | `POST /access/mobile/action` | mobile |
| 玩家录音上传 | `POST /access/player/audio` | mobile |
| 一键开桌 | `POST /access/host/table` | webapp (KP) |
| 开启行动窗 | `POST /access/host/turn` | webapp (KP) |
| 实时通道 | `WS /ws?table=&viewer=&role=pl&token=` | 任一启用端 token |
| 场景交互物（R10） | `GET /api/campaigns/{campaign}/interactives` | mobile |
| 提交交互（R10/R11） | `POST /api/campaigns/{campaign}/interact` | mobile |
| 待审队列 / 审批决定（KP） | `GET|POST /api/campaigns/{campaign}/approvals` | webapp (KP) |
| 我的交互（玩家） | `GET /api/campaigns/{campaign}/pipeline/mine?player_id=` | mobile |
| NPC 自主性（R28–R31） | `GET /api/campaigns/{campaign}/npc/state`、`/npc/proposals` | webapp (KP) |
| 规则包（R23） | `/api/rules/*` | webapp (KP) |
| 总览（R4/R5/R15/R16/R20） | `GET /api/campaigns/{campaign}/overview` | webapp (KP) |
| 模组库（R22） | `GET /api/modules`、`GET /api/modules/{id}` | 无 |
| 一键下载 / 产物摘要（R24 / R35-2） | `GET /api/modules/{id}/download`、`GET /api/modules/{id}/package` | 无 |

> ⚠️ **两个 sha256 不是同一个量**（R35-2）：`GET /api/modules` 条目里的 `sha256/size/files`
> 是**解包后目录摘要** `sha256_dir(modules/<id>)`；`GET /api/modules/{id}/download` 返回的是打包后的
> `.modpkg`，其字节 sha256 由 `GET /api/modules/{id}/package` 的 `artifact.sha256` 与下载响应头
> `X-Artifact-Sha256` 给出。校验下载物请用后者，详见 [`docs/R35-DEFECT-CLOSURE.md`](docs/R35-DEFECT-CLOSURE.md)。

> ⚠️ 实时通道地址**恒为 `/ws`**。`/access/ws` 只是返回参数说明的 GET 端点，
> 不要把它当作 WebSocket URL。

---

## 配置

### 三端 token

配置位于 `configs/access_config.yaml`，包含 `mobile` / `webapp` / `recorder` 三端 token。
token 可通过 `Authorization: Bearer <t>` 或 `?token=<t>` 传递。

```yaml
# configs/access_config.yaml（结构示意）
access:
  mobile:   "<玩家端 token>"
  webapp:   "<主持端 token>"
  recorder: "<录音端 token>"
```

> 🔒 **上线前务必替换默认 token**，且不要提交本地覆盖文件
> （`configs/*.local.yaml`、`.env`、`.env.*` 已在 `.gitignore` 中排除）。
>
> ℹ️ **关于「包内是否含 `.env`」**：交付包内**确有 1 个 `.env` 文件** —— `web/.env.production`（451 B），内容仅 `VITE_TRPG_TRANSPORT=real` 与其上方注释，**不含任何 token / 密钥**；它是 GM 端前端**构建期**的模式开关（详见 `docs/BUILD-WEB.md` §5.1）。运行期真正的连接参数（table / viewer / role / campaign / token / ws）一律由 URL 查询串给出，不落在该文件里。

### 局域网访问

服务默认监听 `0.0.0.0`。首次使用需放行入站端口（管理员 PowerShell）：

```powershell
netsh advfirewall firewall add rule name="trpg-9210" dir=in action=allow protocol=TCP localport=9210
```

其它设备访问 `http://<本机IP>:9210/player/`。

### 公网访问（安全警告）

可用 `cloudflared` 快速隧道临时暴露：

```powershell
cloudflared tunnel --url http://127.0.0.1:9210
```

> ⚠️ **安全警告**：quick tunnel **无鉴权**，且部分 `/api/*` 路径不带 token 校验。
> 公网暴露期间等同于把内网 API 开放给匿名访问者。
> 生产环境必须改用**命名隧道 + Cloudflare Access** 或 **Nginx/Caddy + Basic Auth + 路径白名单**，
> 并限制可暴露路径。详见 [`docs/DEPLOY.md`](docs/DEPLOY.md)。

---

## 故障排查

| 现象 | 处理 |
|---|---|
| 退出码 1「缺少运行依赖」 | `python -m pip install -r requirements.txt` |
| 退出码 1「Python 版本过低」 | 安装 Python 3.12+ 并确认在 PATH 中 |
| 退出码 2「端口被占用」 | `stop.bat` 释放，或改用其它端口 `start.bat 9211` |
| 退出码 3「健康检查超时」 | 查看 `var\server.err.log`；多为依赖缺失或配置错误 |
| `/player/` 返回 404 `player_not_built` | `player-web/index.html` 缺失 |
| `/app/` 返回 404 `frontend_not_built` | `web/dist/index.html` 缺失 |
| 中文路径 / 中文输出乱码 | 确认 `.ps1` 为 UTF-8 **带 BOM**（PowerShell 5.1 否则按 ANSI 解析） |
| 局域网访问不通 | 检查防火墙入站规则与 `netstat -ano \| findstr :9210` |
| 重复双击 `start.bat` 起了两个实例 | 正常不会发生（脚本幂等）；若发生请查看 `run/server.json` 的 pid |

> **BOM 铁律**：本仓库所有含中文的 `.ps1` 必须保存为 **UTF-8 带 BOM**。
> 用编辑器保存后请复核；BOM 丢失会导致 PowerShell 5.1 按 ANSI/GBK 解析而损坏中文路径。

---

## 开发与测试

> **交付包说明（t5 修正）**：自动化测试（`tests/`，pytest）位于**源仓库**，
> 交付包按打包策略**不含 `tests/`**（与 `scripts/sim`、`scripts/evolve` 等开发期脚本同属排除项）。
> 因此在交付包内直接运行 `python -m pytest` 会因 `tests/` 目录不存在而失败，**属预期**；
> 请到**源仓库**执行：

```bat
python -m pytest tests/ -q
```

> 源仓库实测 **172 passed / 0 failed**（回归基线 166；原 flaky 心跳测试已修复为确定性断言）。

运行测试需要额外安装 `pytest` / `pytest-asyncio` / `hypothesis`
（见 `pyproject.toml` 的 `[project.optional-dependencies].dev`）。

---

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | 部署手册（含反代 / 加固方案） |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | 日常运维 |
| [`docs/PLAYER-WEB.md`](docs/PLAYER-WEB.md) | 玩家端页面说明 |
| [`docs/MINIPROGRAM.md`](docs/MINIPROGRAM.md) | 小程序端说明 |
| [`docs/CROSS-END-CONTRACT.md`](docs/CROSS-END-CONTRACT.md) | 跨端契约（冻结） |
| [`docs/ENDPOINT-SPEC-NEW.md`](docs/ENDPOINT-SPEC-NEW.md) | 端点规格 |
| [`docs/ACCEPTANCE-REPORT.md`](docs/ACCEPTANCE-REPORT.md) | 验收报告 |
| [`docs/PLAN-ACCEPTANCE.md`](docs/PLAN-ACCEPTANCE.md) | 验收计划 |
| [`docs/ROADMAP-DEFERRED.md`](docs/ROADMAP-DEFERRED.md) | 延后项路线图 |
| [`docs/BUILD-WEB.md`](docs/BUILD-WEB.md) | GM 前端构建说明（`web/src` → `web/dist` 单出口） |
| [`docs/BUILD-LOG.md`](docs/BUILD-LOG.md) | 构建记录与资产 sha256 登记 |
| [`docs/UI-TOKENS-MODU.md`](docs/UI-TOKENS-MODU.md) | GM 端主题覆盖层（魔都风格）说明 |
| [`docs/RULEPACKS.md`](docs/RULEPACKS.md) | 规则包格式与用例（R23） |
| [`docs/R2-NPC-CONTRACT-CHANGE.md`](docs/R2-NPC-CONTRACT-CHANGE.md) | R2 NPC 自主性契约变更说明 |
| [`docs/R35-DEFECT-CLOSURE.md`](docs/R35-DEFECT-CLOSURE.md) | R35 缺陷收敛：**索引 sha256 与下载产物 sha256 的语义区分**、一键落位空态契约、NPC 候选可见性字段 |

---

## 许可

本项目基于 [MIT License](LICENSE) 发布。
