# TRPG 跑团辅助系统 · 客户端（玩家端）

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Zero Build](https://img.shields.io/badge/build-zero--build-success.svg)](#简介)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6.svg)](#快速开始)
[![Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-orange.svg)](CHANGELOG.md)

> 玩家端页面 + 本地启动器：**零构建、零 npm 依赖、无 CDN 外链**。
> 双击 `start.bat` 即在本地拉起静态服务器、自动发现服务端地址并打开浏览器。

配套服务端仓库：**trpg-server**（主持端服务器，托管 `/player/` 页面）。

---

## 简介

本仓库是 TRPG 跑团辅助系统的**客户端（玩家端）**，面向玩家使用的 PC / 移动浏览器页面。

- **零构建**：没有 webpack / vite / npm，`client/` 下的文件即最终产物，直接由浏览器加载。
- **无外链**：不引用任何 CDN，完全离线可用（除访问服务端 API 外）。
- **本地启动器**：内置一个仅依赖 Python 标准库的静态服务器（`scripts/serve.py`），
  自动选择空闲端口、自动发现同机服务端地址、自动打开浏览器。
- **契约一致**：实现依据 `CROSS-END-CONTRACT.md` **v1.1**（冻结契约），
  固定文案表与小程序端**逐键 0 差异**。

### 功能清单

| 编号 | 功能 |
|---|---|
| F1 | 服务器连接（`GET /access/info` 校验 token 与可达性） |
| F2 | 连接码解析（`GET /access/table/resolve`） |
| F3 | 玩家身份（本地存储保存 playerId / playerName） |
| F4 | 加入桌面 |
| F5 | 回合状态（15s 兜底轮询 `/access/mobile/state`；实时性由 WS 推送驱动） |
| F6 | 行动提交（仅 `COLLECTING` 可提交，`req_id` 幂等） |
| F7 | 事件流（REST 主通道，展示最新 50 条；WS 为可选增强） |
| F8 | 语音录制与上传（需 HTTPS / localhost 安全上下文） |
| F9 | 设备状态（只读） |
| F10 | 连接状态与对账 |
| **R10** | 场景交互面板：房间 / 可交互物**热区坐标与动作集由服务端下发**，点击热区即「查看 / 搜索 / 撬锁」 |
| **R11** | 敏感交互进入**统一审批总线**，主持人拍板后才定向下发结果（拍板前玩家侧看不到任何正文） |

### 本轮（R2）新增

- **R10/R11 地点交互面板**：加入桌面后在「桌面」视图底部自动出现（**纯 JS 注入 DOM**，不改 `index.html` / `app.css`，因此镜像面只有 `app.js`）。
  非敏感动作（查看 / 搜索）直接返回检定结果并进入事件流；敏感动作（撬锁 / 取走）返回「已上报待主持人」并进入待审队列，
  主持人拍板后**无需刷新页面**即就地更新（WS 帧触发）。
- **事件流服务端裁剪**：非 KP 视图由**服务端**裁剪（响应含 `filtered=true`），暗骰（`CHECK_RESOLVED` 归属 KP）与 KP-only 事件整条不返回；客户端保留 `scope`/`targets` 二次过滤兜底。
- **镜像不变量（强制）**：本仓库 `client/` 与服务端 `player-web/` 是**同一份页面**，`app.js` / `app.css` / `tokens.json` / `strings.json` / `index.html`（以及 `README.md`）**必须逐字节一致**；任一文件改动都要两处同步并复核 sha256。
- ⚠️ **缓存注意**：由服务端托管时 `/player/app.js` 等静态响应只带 `ETag`/`Last-Modified`、**不带 `Cache-Control`**，更新前端后浏览器可能仍执行旧脚本 —— 验收请强制刷新（`Ctrl+F5`）。
---

## 快速开始

### 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（启动脚本基于 cmd + PowerShell 5.1） |
| Python | **3.12+**（仅用于运行本地静态服务器，无需安装任何第三方包） |
| 浏览器 | Chrome / Edge / Firefox 等现代浏览器 |

> 本地静态服务器只用 Python 标准库（`http.server`），**不需要 pip install**。

### 一键启动

```bat
:: 默认：从 8080 起自适应端口，自动发现同机服务端并打开浏览器
start.bat

:: 指定端口
start.bat 8081

:: 指定端口 + 指定服务端地址（跳过自动发现）
start.bat 8081 http://192.168.10.110:9210
```

启动脚本会依次执行：

1. 检测 Python 是否安装且版本 ≥ 3.12；
2. 探测端口占用（默认 8080，占用则依次顺延 8081→8090）；
3. 启动 `scripts/serve.py`（绑定 `127.0.0.1`）；
4. **解析服务端地址**：若命令行未给出 `server-url`，则尝试读取同机
   `../trpg-server/run/server.json`；读到即使用，读不到则打开页面让用户手工填写；
5. 打开浏览器到 `http://127.0.0.1:<port>/index.html?server=<server-url>`；
6. 打印实际地址。

### 停止

```bat
stop.bat          :: 读取 run/client.port 定位端口 → 停止本地服务器 → 确认端口释放
```

### 端口发现文件

启动成功后会在仓库根目录的 `run/` 下落盘两个文件（`run/` 已加入 `.gitignore`）：

| 文件 | 内容 |
|---|---|
| `run/client.port` | 实际端口（纯数字） |
| `run/client.json` | 本地服务器信息（端口、pid、页面 URL、启动时间） |

> **服务端发现文件 `../trpg-server/run/server.json`**：服务端 v1.0.1 起额外写入
> `deployment_id` 与 `install_dir` 两个字段（用于识别「这个发现文件指向哪个部署」）。
> **本客户端只读其中的 `port` / `url`，多出的字段会被忽略，自动发现行为完全不变。**

---

## 目录结构

```
trpg-client/
├─ start.bat / stop.bat        纯 ASCII 包装器（规避 cmd 代码页问题）
├─ scripts/
│  ├─ serve.py                 零依赖静态服务器（Python 标准库 http.server）
│  ├─ start.ps1                启动真实逻辑（UTF-8 带 BOM）
│  └─ stop.ps1                 停止真实逻辑（UTF-8 带 BOM）
├─ client/                     玩家端页面（零构建，文件即产物）
│  ├─ index.html               三视图骨架（连接设置 / 桌面 / 语音）
│  ├─ app.js                   全部前端逻辑（F1–F10、事件流、轮询、可选 WS、录音）
│  ├─ app.css                  设计令牌（CSS 变量）+ 契约 §2 组件语义类名
│  ├─ strings.json             固定文案表（三端逐字节一致，与小程序端 0 差异）
│  ├─ tokens.json              设计令牌机器可读副本（逐值等于契约 §2）
│  └─ README.md                页面级说明
├─ docs/
│  └─ PLAYER-WEB.md            玩家端页面功能与契约依据
├─ run/                        端口发现文件（运行期生成，已 gitignore）
└─ LICENSE  README.md  CHANGELOG.md  .gitignore  .gitattributes
```

---

## 配置

### 服务端地址如何传入

页面在启动时按以下**优先级**确定服务端地址（`app.js:851`）：

```js
var server = q.server || lsGet(LS.server) || window.location.origin;
```

1. **URL 查询参数 `?server=`**（最高优先级）—— 由 `start.bat` 自动注入；
2. 浏览器本地存储 `trpg.server`（用户在「连接设置」里填过）；
3. 当前页面 origin（兜底）。

> 也支持在 URL 中一并预填其它参数：
> `/index.html?server=http://192.168.10.110:9210&code=TABLE-0001&pid=pl-001&token=<mobile token>`

### 需要填写的连接信息

在页面「连接设置」中填写：

| 字段 | 说明 |
|---|---|
| 服务器地址 | 服务端地址，如 `http://192.168.10.110:9210`（通常已自动填好） |
| 访问 token | **mobile 端** token（见服务端 `configs/access_config.yaml`） |
| 连接码 | 由主持端（KP）提供，如 `TABLE-0001` |
| 玩家 ID | 本局内的玩家标识，如 `pl-001` |
| 昵称 | 显示名 |

填写后依次点击「测试连接」→「解析连接码」→「加入跑团」。

### 本地存储键

`trpg.playerId` / `trpg.playerName` / `trpg.server` / `trpg.code` / `trpg.token`，
以及事件流对账游标 `trpg_last_seq_<table_id>`。

> 🔒 token 只保存在浏览器本地存储、只随请求发送，**不硬编码、不写日志**；
> recorder token 从不下发到玩家端。

---

## 故障排查

| 现象 | 处理 |
|---|---|
| 启动脚本提示「Python 未安装 / 版本过低」 | 安装 Python 3.12+ 并确认在 PATH 中 |
| 端口 8080–8090 全部被占用 | 关闭占用进程，或显式指定一个空闲端口 `start.bat 8091` |
| 浏览器打开了但服务端地址为空 | 未找到 `../trpg-server/run/server.json`，请手工填写服务端地址 |
| 页面提示连接失败 | 确认服务端已启动、地址与端口正确、局域网可达 |
| 「测试连接」返回 401 / 403 | token 不正确或不是 mobile 端 token |
| 「解析连接码」失败 | 连接码拼写错误，或主持端尚未开桌 |
| 录音功能不可用 | 录音需安全上下文（`https://` 或 `http://localhost` / `http://127.0.0.1`）；明文 HTTP 的局域网地址下浏览器禁用麦克风，其余功能不受影响 |
| 事件流长时间不刷新 | F10 状态行会显示「重连中…／已断开」；检查服务端是否在运行 |
| 页面样式错乱 | 确认 `client/` 下 `app.css`、`app.js`、`strings.json`、`tokens.json` 齐全 |
| 中文乱码 | 确认 `.ps1` 为 UTF-8 **带 BOM**（PowerShell 5.1 否则按 ANSI 解析） |

> **BOM 铁律**：本仓库所有含中文的 `.ps1` 必须保存为 **UTF-8 带 BOM**。

---

## 与服务端的关系

本仓库的 `client/` 目录是**同一份**玩家端页面，服务端仓库的 `player-web/` 也托管一份
（挂载在服务端 `/player/`），便于玩家**无需本地安装**、直接用手机浏览器访问。

两种使用方式：

| 方式 | 入口 | 适用场景 |
|---|---|---|
| **本地启动器**（本仓库） | `start.bat` → `http://127.0.0.1:<port>/index.html?server=...` | 主持机/玩家机上本地开页面 |
| **服务端托管** | `http://<服务端IP>:<port>/player/` | 手机等移动设备直接访问 |

### 服务端实例身份端点（`/__trpg_server__`）

服务端 v1.0.1 新增了 **additive 身份端点** `GET /__trpg_server__`（无鉴权），
返回 `{service, ok, pid, port, deployment_id, install_dir, version}`。
它把「端口上的是不是**本部署**」与「是否**活着**」（`/api/health`）分开，
用于服务端 `start.bat` / `stop.bat` 在同机装有多个 TRPG 部署时不再互相误判。

**对客户端无影响**：

- 客户端的 `GET /__trpg_client__`（本地静态服务器身份端点）**保持不变**；
- 客户端**不需要**改任何逻辑 —— 自动发现仍只读 `../trpg-server/run/server.json` 的 `port` / `url`；
- 客户端与本端点**无交互**（它只服务服务端自身的启停判定）。

---

## 许可

本项目基于 [MIT License](LICENSE) 发布。
