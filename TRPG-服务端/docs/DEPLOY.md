# DEPLOY.md —— 服务端（主持端）部署手册

> 状态：**T2 实测值已回填**（2026-09-25）；整体由 T7 阶段定稿。T6 端到端复测后如有新值请更新。
> 适用交付物：TRPG-交付包-v1 的 `server/` 目录。
> 相关文档：`OPERATIONS.md`（日常运维）、`PLAYER-WEB.md`、`MINIPROGRAM.md`。

---

## 1. 组成与端口

| 项 | 值 |
|---|---|
| 服务 | FastAPI 单进程（uvicorn），入口 `app.main:app` |
| 端口 | **9210**（TCP，需入站放行） |
| 主持端 UI | `/app/`（React 预构建 bundle，本轮不改动） |
| 玩家端页面 | `/player/`（零构建原生页面，由本服务托管） |
| 健康检查 | `GET /api/health` |
| 实时通道 | `WS /ws` |
| Python | 3.12+（实测远程 3.12.10；本机 3.13.1 亦可运行） |

## 2. 目录结构（`server/` 内）

```
server/
  app/            服务端应用（含 web/access.py、web/rest.py、web/static.py、web/ws_protocol.py）
  trpg/           领域内核（agent/、events.py、allowlist.yml 等冻结契约）
  configs/        配置（access_config.yaml —— 三端 token）
  modules/ rulepacks/ skills/ scripts/ tests/   业务模块与测试
  data/           运行期数据（数据库、录音导入等）
  web/dist/       主持端 UI 构建产物
  player-web/     玩家端页面（来自 clients/web-player/）
  requirements.txt
  start.bat / stop.bat
  var/            运行期日志与 pid（server.out.log / server.err.log / agent_9210.pid）
```

## 3. 环境准备

1. 安装 **Python 3.12+**（安装时勾选 *Add Python to PATH*）。
2. 安装依赖：

```powershell
cd server
pip install -r requirements.txt
```

`requirements.txt` 只列运行必需依赖（fastapi / uvicorn / pydantic / PyYAML / aiofiles / python-multipart / httpx 等），
不含 torch / transformers 等重型可选依赖。

## 4. 启动与停止

### 4.1 一键启动（推荐）

双击交付包根目录的 `快速开始.bat`，或：

```cmd
cd server
start.bat
```

`start.bat` 流程：检测 python → 检测 9210 占用 → 后台拉起 uvicorn（stdout 写入 `var\server.out.log`）
→ 轮询 `/api/health` 最长 30s → 打印访问地址与 token 提示。

**退出码**：`0` = 本次启动成功且健康；`1` = 启动失败（看 `var\server.err.log`）；
`2` = 9210 已在监听（未重复启动，若健康视为可用）。

启动成功后访问：

- 主持端（KP）：`http://127.0.0.1:9210/app/`
- 玩家端：`http://127.0.0.1:9210/player/`

### 4.2 手动启动（排障用）

```powershell
cd server
python -m uvicorn app.main:app --host 0.0.0.0 --port 9210
```

前台运行便于直接观察报错；生产使用请走 `start.bat`（后台 + 日志落盘）。

### 4.3 停止

```cmd
cd server
stop.bat
```

按 `var\agent_9210.pid` 结束进程，再兜底释放 9210 端口，并做 3 次采样确认已释放。

### 4.4 多部署共存：`/__trpg_server__` 与 `deployment_id`

**问题**：同一台机器上可能装着**多个** TRPG 服务端（例如生产用的旧版本 + 新交付物）。
`GET /api/health` 只回答「**活着**」，而且它的响应在不同部署/版本之间**逐字节同构**：

```json
{"status":"ok","version":"0.1.0-t12","ts":"2026-09-26T05:45:43+00:00"}
```

因此**不能**用 health 判断「端口上的是不是**本部署**」。曾据此误判：显式指定被别的部署占用的端口
时谎称「幂等」并 `exit 0`，还把本部署的 `run/server.json` 覆写成**他人实例**的端口/PID；
无参数自适应时也会落回他人实例端口。

**解决**：服务端新增**身份端点**（additive，无鉴权，不含任何密钥/令牌）：

```cmd
curl http://127.0.0.1:9210/__trpg_server__
```

```json
{
  "service": "trpg-server",
  "ok": true,
  "pid": 2188,
  "port": 9210,
  "deployment_id": "5c5b15c4-9900-4df5-9ac4-c2103bdf246c",
  "install_dir": "C:\\Users\\Administrator\\Desktop\\trpg-lan\\trpg-server",
  "version": "0.1.0-t12"
}
```

| 字段 | 含义 |
|---|---|
| `service` | 恒为 `"trpg-server"`；**只有等于它才算身份响应** |
| `pid` | 当前服务进程 PID |
| `port` | **真实监听端口**（取监听套接字的 `getsockname()`，不受 Host 头/反代影响） |
| `deployment_id` | 本部署**唯一且稳定**的身份 |
| `install_dir` | 部署根**绝对路径**（「是不是同一个部署」的直接判据） |

**`deployment_id` 的生成**（任选其一，本实现用首选）：
1. **首选**：首次启动时在部署根生成 `run/deployment.id`（UUID v4），之后每次启动**复用**；
   `start.ps1` 与服务端 `app/web/identity.py` 读/写的是**同一个文件**，两侧同源。
2. 兜底：该文件不可读且不可写时，退化为「部署根绝对路径的 SHA256 前 16 位」
   （正斜杠归一 + 小写 + 去尾分隔符后摘要；Windows 路径大小写不敏感）。

**判定规则**（`scripts/start.ps1` / `scripts/stop.ps1` 一致）：
`install_dir` 规范化后**相等** —— **或** —— `deployment_id` **相等**。

| 端口上的占用者 | `start.bat <该端口>` | 无参数 `start.bat` |
|---|---|---|
| **本部署** | 幂等 `exit 0`（不重复起第二个实例） | 复用该端口 `exit 0` |
| **别的 TRPG 部署 / 旧版服务端**（无该端点） | **真冲突 `exit 2`** + 打印占用者 PID，**不覆写** `run/server.json` | **跳过**它，落第一个**空闲**端口 |
| 其它任意进程 | **真冲突 `exit 2`** | **跳过**它 |

`stop.bat` 只停**本部署**：先做命令行防误杀校验（命令行含 `_serve.py` 或 `trpg-server`），
再用身份端点确认「是本部署」；不是本部署一律**拒绝停止**并 `exit 1`。
身份端点不可达（旧版服务端）时退回命令行校验，**不放宽**守卫。

**运维提示**
- 身份端点**无鉴权**：它只暴露部署身份（PID/端口/路径/版本），不含 token。
  若公网暴露，请在反代/隧道**路径白名单**里按需放行或屏蔽 `/__trpg_server__`
  （见 §6.3 的公网加固口径：**必须白名单、不得黑名单**）。
- `run/deployment.id` 是**运行期文件**（`run/` 已 gitignore），删除它会让该部署在下次启动时
  换一个新的 `deployment_id`（`install_dir` 判据仍然有效，故不影响正常启停）。
- `run/server.json` 新增 `deployment_id` / `install_dir` 两个字段，便于运维直接判断
  「这个发现文件指向哪个部署」；既有字段（`port`/`host`/`pid`/`url`/`started_at`）未变。

## 5. 配置与凭据

三端 token 位于 `server/configs/access_config.yaml`：

| 端 | 用途 | token |
|---|---|---|
| `mobile` | 玩家端（浏览器 / 小程序） | `f06e4ec6…`（完整值见配置文件） |
| `webapp` | 主持端 KP | `f4a8dc57…`（完整值见配置文件） |
| `recorder` | 服务端内部录音落库（**绝不下发客户端**） | `6b52cd78…`（完整值见配置文件） |

> **实测（2026-09-25）**：三端均为 `enabled: true`；`GET /access/info`（任一启用端 token）返回
> `{"ends":{"mobile":true,"webapp":true,"recorder":true}}`。
> 本文档**不内联完整 token** —— 文档与配置文件分开流转时避免泄密；完整值只在 `server/configs/access_config.yaml`。

> **安全提醒**：交付包内为明文配置。公开分发前请更换三端 token；`recorder` token 不得出现在任何客户端产物或日志中。
> 生产环境建议改为环境变量注入，避免随包分发。

> **WS 发布路径（2026-09-25 实测生效）**：服务端 **WS 下行发布已生效**（T2 additive 发布：`EventStore.append` 单一收口、best-effort，异常不影响落库与 HTTP；实测收到业务帧 `TURN_UPDATED` / `STATE_DELTA`）。
> **但 F7 主通道仍为 REST 轮询**（完整性权威），**WS 为可选增强**：连不上/被拒/断开一律**静默降级**，不得成为依赖，也不得改变任何可见文案（契约 §3.4.1–§3.4.4）。
> 另：`STATE_DELTA` 为**房间级广播**，回退帧一律不带 payload（`{type, redacted:true}`）—— 详见契约 §3.4.2 与 §7.2 R1 / R1b。

## 6. 网络暴露

### 6.1 本机回环

默认即可用：`http://127.0.0.1:9210/`。uvicorn 以 `--host 0.0.0.0` 启动，因此局域网亦可直接访问。

### 6.2 局域网（手机 / 第二台电脑）

1. 查询本机局域网 IPv4：

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -like '192.168.*' | Select-Object IPAddress
```

2. 放行 9210 入站（管理员 PowerShell，只需执行一次）。

   ⚠️ **务必限制来源网段，不要用 Any**（见下方「来源限制」）：

```powershell
# 推荐：仅放行必要网段
New-NetFirewallRule -DisplayName 'trpg-9210' -Direction Inbound -Action Allow -Protocol TCP `
  -LocalPort 9210 -RemoteAddress 192.168.10.0/24,192.168.56.0/24

# 不推荐（等于对任何来源开放）：
# New-NetFirewallRule -DisplayName 'trpg-9210' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9210
```

3. 校验：

```powershell
Get-NetFirewallRule -DisplayName 'trpg-9210' | ForEach-Object {
  $af = $_ | Get-NetFirewallAddressFilter
  "$($_.DisplayName)  enabled=$($_.Enabled)  dir=$($_.Direction)  action=$($_.Action)  RemoteAddress=$($af.RemoteAddress -join ',')"
}
Test-NetConnection -ComputerName 192.168.10.110 -Port 9210
```

4. 其他设备访问 `http://<局域网IP>:9210/player/`。

#### 来源限制（2026-09-25 已落实）

远程 `trpg-9210` 入站规则已从 **Any 收紧为 `192.168.10.0/24` + `192.168.56.0/24`**（两条规则，实测生效）：

```text
rule: trpg-9210  enabled=True  dir=Inbound  action=Allow
      RemoteAddress=192.168.10.0/255.255.255.0,192.168.56.0/255.255.255.0
```

> ⚠️ **这只减少暴露面，不等于关闭局域网匿名访问**：
> 防火墙按**来源**过滤，不按**路径**过滤。**上述网段内的设备**（含本机 192.168.10.160）
> 访问 `http://192.168.10.110:9210/docs`、`/openapi.json`、`/api/tables` **实测仍为 200**。
> 也就是说：**同网段的玩家/观众/其他设备依然可以匿名读到这些路径**。
> 要真正在局域网内也收口，需上反代（§6.3.5.4，**生产推荐，本轮不部署**）或在应用层关闭这些路径。
> 详细边界说明见 §6.3.5.2 的「覆盖边界」小节。

**实测（AC-1 第 4 条 / AC-4 第 16 条，2026-09-25）** —— 第二台设备（本机 `192.168.10.160`）经局域网访问远程 9210：

| 路径 | 状态码 |
|---|---|
| `http://192.168.10.110:9210/api/health` | **200** |
| `http://192.168.10.110:9210/player/` | **200** |
| `http://192.168.10.110:9210/app/` | **200** |

证据：`evidence/T2-server.txt`、`evidence/T6-acceptance.md`。

### 6.3 公网暴露（cloudflared / frp）

> AC-4 第 17 条：需提供并实测至少一种穿透/反代路径，并给出**可直接执行的脚本 + 配置模板 + 手册**。
> 本节方案 A 已在远程主机实测可用（见 6.3.1），方案 B 为自有服务器替代方案。

#### ⚠️ 安全提示（务必先读）

```text
1. cloudflared quick tunnel 生成的是【无鉴权】的公网 HTTPS 地址：任何拿到该 URL 的人都能访问。

2. 【公网】加固后实际可匿名访问的表面（实测 2026-09-25；白名单配置见 §6.3.5.2）：
     /api/health               -> 200   无需 token（健康检查，保留）
     /player/                  -> 200   玩家端页面，无需 token（18b 判据 1 要求 200）
     /app/                     -> 404   主持端 KP 控制台（config v2 已移除该规则；原为 200 无鉴权，已修）
     /api/campaigns/{c}/events -> 200   ★  无鉴权（F7 主通道，契约 §1.1 必须保持可用）
     /access/*                 -> 401（无 token）/ 200（带 token）—— 这一层受保护
     /docs /redoc /openapi.json /api/tables /mcp /metrics/latency -> 404（白名单外，已封）

   加固前曾是 200、现已被白名单封掉的：/docs、/redoc、/openapi.json、/api/tables、/mcp、/metrics/latency。

   ★ 残留暴露面（详见 §6.3.5.7）：
     ① /app/ 主持端控制台 —— ✅ **已修**（config v2 移除 ^/app 规则，实测 404；原为 200 无鉴权）
     ② /api/campaigns/{c}/events 公网匿名 200 —— 属契约 R1 残留
        缓解：枚举入口 /api/tables 已封 404 ⇒ 匿名者拿不到 campaign_id
        根治：服务端加可见性过滤（需契约变更，本轮不做）

3. 因此 quick tunnel 仅限【演示 / 联调】期间开启，用完立即 stop；不要把 URL 公开发布到群里或文档外；
   不要在非受控环境长期常驻。停隧道步骤见 §6.3.5.2 的「应急操作」。

4. 隧道 URL 会出现在 cloudflared 日志与进程命令行中，注意日志文件的访问权限。
   取当前地址以 C:\trpg-tunnel\current-url.txt 为唯一权威来源（旧目录的 tunnel.url.txt 是过期地址）。

5. 公网暴露期加固见 §6.3.5。生产环境请改用（本轮不部署）：
     - §6.3.5.4 Nginx/Caddy 反代 + 路径白名单 + 对 /app 加 Basic Auth（生产推荐），或
     - §6.3.5.3 Cloudflare 命名隧道 + Access（需自有域名；quick tunnel 不支持 Access）。
```

#### 6.3.1 已部署路径（远程实测 · 2026-09-25 加固后）

远程主机已注册计划任务 **`trpg-tunnel-cf`**，以 SYSTEM / Highest 权限运行 cloudflared 快速隧道，
配合**路径白名单配置**（见 §6.3.5.2）把 `http://127.0.0.1:9210` 受控地暴露为临时公网地址。

实测事实（2026-09-25 加固后）：

| 项 | 值 |
|---|---|
| 计划任务 | `trpg-tunnel-cf`，State=**Running**，UserId=`NT AUTHORITY\SYSTEM`，RunLevel=Highest |
| 任务动作 | `C:\trpg-tunnel\cloudflared.exe tunnel --config "C:\trpg-tunnel\config.yml" --no-autoupdate --logfile "C:\trpg-tunnel\cloudflared.log" --url http://127.0.0.1:9210` |
| 运行进程 | `cloudflared`（PID **7696**，Path=`C:\trpg-tunnel\cloudflared.exe`） |
| 配置文件 | `C:\trpg-tunnel\config.yml`（生效路径；白名单全文见 §6.3.5.2） |
| **当前公网地址** | **不写死** —— 用 §6.3.1 的命令实时获取（quick tunnel 每次重连换域名；本轮已实测变更 3 次，旧地址均返回 530） |
| 服务版本 | `0.1.0-t12` |

> **注意：quick tunnel 地址每次隧道重启都会变化。** 上表地址是本次实测值，仅供演示与联调参考；
> 交付/演示前请取当前真实地址（见下方命令），不要硬编码。
>
> ⚠️ **取址纪律（队长裁决 2026-09-25）**：
> **以日志动态解析为准** —— quick tunnel 每次重连都会换域名，`current-url.txt` **可能滞后**，
> 因此以上面第一条命令（日志 `Select-Object -Last 1`）为权威。
> 桌面旧乱码目录里的 `tunnel.url.txt` **是过期地址**（未清理），**已有队友被它带偏过**，请勿引用。
> **本交付文档不写死任何具体域名** —— 过期地址会返回 **530** 并误导复验。
>
> 实测经验：cloudflared 日志**跨多次重启累积**，历史地址与当前地址混在一起
> （实测曾同时存在 2 个候选：`impaired-nov-commodities-handed` 已失效、`wages-wellness-retailer-head` 存活）。
> 因此 `tunnel-cf.ps1` 会列出全部候选地址并**逐个探测 `/api/health`**，只返回真正存活的那个。
> **不要用「取日志最后一行」的朴素做法。**

##### ⚠️ 历史脆弱点：cloudflared.exe 曾位于一个**乱码目录**（已修复）

**问题**：加固前，cloudflared.exe 位于

```text
C:\Users\Administrator\Desktop\榛戝鏉惧紑鍙戞枃妗tools\cloudflared.exe
```

即目录名是「黑客松开发文档」的 **GBK/UTF-8 乱码形态**（`榛戝鏉惧紑鍙戞枃妗`）后接 `tools`，
而正常路径 `...\黑客松开发文档\tools` 当时**并不存在**（Test-Path 为 False）。
这是早期某次用非 UTF-8 通道传中文路径留下的残留。

**风险**：
- 任何人「清理」或迁移该乱码目录，隧道会立刻起不来（任务指向的可执行文件消失）。
- 路径不可读、不可预期，排障困难，且容易被误认为恶意目录。
- 中文路径经 scp/编码不一致的通道操作时极易再次损坏。

**修复（队长已完成）**：把 cloudflared.exe 复制到**纯 ASCII 路径** `C:\trpg-tunnel\`，
并把计划任务 `trpg-tunnel-cf` 指向该路径（`C:\trpg-tunnel\cloudflared.exe` + `config.yml`）。
**现在任务不再依赖任何中文/乱码路径**，这是本轮的一个实质健壮性改进。

> 旧乱码目录 `榛戝鏉惧紑鍙戞枃妗tools` 仍残留在桌面上（含一份旧 cloudflared.exe 与旧日志），
> **已不是任务目标**，可择机清理；清理前请先确认任务指向 `C:\trpg-tunnel\`。
>
> **运维纪律**：今后任何隧道/服务相关文件都放在**纯 ASCII 路径**下，
> 不要把可执行文件或配置放在中文目录里（远程 PowerShell 5.1 与 scp 的编码假设都不稳）。

公网端点实测（从本机发起，加固后）：

| 端点 | 结果 | 说明 |
|---|---|---|
| `GET /player/` | **200** | 玩家端页面（T2 已交付；加固白名单放行） |
| `GET /api/health` | **200** `{"status":"ok","version":"0.1.0-t12",...}` | 无需 token |
| `GET /app/` | **200** | 主持端页面 |
| `GET /access/info`（无 token） | **401** | 预期行为：/access/* 需鉴权 |
| `GET /access/info?token=<mobile>` | **200** `{"ok":true,"data":{"service":"trpg","version":"0.1.0-t12","ends":{"mobile":true,"webapp":true,"recorder":true},...}}` | 带 token 正常 |
| `GET /access/info`（`Authorization: Bearer <mobile>`） | **200** | 两种传 token 方式均可用 |
| `GET /api/campaigns/c_demo/events` | **200** | F7 主通道（白名单精确放行，未被误封） |
| `GET /docs` `/redoc` `/openapi.json` `/api/tables` `/mcp` `/metrics/latency` | **404** | 白名单外，隧道边缘拒绝 |

复现命令：

```powershell
# 取当前公网地址（**以日志动态解析为准**）
node packaging/remote.mjs run "Get-Content C:\trpg-tunnel\cloudflared.log | Select-String 'trycloudflare' | Select-Object -Last 1"

# 备用：current-url.txt（**可能滞后**，仅作交叉参考）
node packaging/remote.mjs run "Get-Content 'C:\trpg-tunnel\current-url.txt' -ErrorAction SilentlyContinue"

$u = '<当前公网地址>'
(Invoke-WebRequest ($u + '/api/health') -UseBasicParsing).StatusCode
(Invoke-WebRequest ($u + '/player/')   -UseBasicParsing).StatusCode
(Invoke-WebRequest ($u + '/app/')      -UseBasicParsing).StatusCode
# /access/info 需要 token（mobile 端）
Invoke-RestMethod ($u + '/access/info?token=<mobile token>')
```

#### 6.3.2 隧道管理脚本（推荐，可直接执行）

`packaging/tunnel-cf.ps1` 提供 start / stop / status / url / install / uninstall 六个动作，
自动解析公网地址并做端点探测。

**本机（服务端所在机器，管理员 PowerShell）：**

```powershell
.\packaging\tunnel-cf.ps1 status     # 查看进程/任务/公网地址/端点探测（只读）
.\packaging\tunnel-cf.ps1 start      # 启动隧道并打印公网地址
.\packaging\tunnel-cf.ps1 url        # 只输出当前公网地址
.\packaging\tunnel-cf.ps1 stop       # 停止隧道（进程 + 计划任务）
.\packaging\tunnel-cf.ps1 install    # 注册为 SYSTEM 计划任务 trpg-tunnel-cf（开机常驻）
.\packaging\tunnel-cf.ps1 uninstall  # 注销计划任务并停止进程
```

**从本机操作远程主机（项目根执行）：**

```powershell
# 1) 上传脚本（注意：scp 对中文远程路径会失败，先传到 ASCII 路径再移动）
node packaging/remote.mjs put packaging/tunnel-cf.ps1 "C:/Windows/Temp/tunnel-cf.ps1"
node packaging/remote.mjs run "Copy-Item 'C:\Windows\Temp\tunnel-cf.ps1' '<远程 tools 目录>\tunnel-cf.ps1' -Force"

# 2) 查看状态 / 取公网地址
node packaging/remote.mjs run "powershell -NoProfile -ExecutionPolicy Bypass -File '<远程 tools 目录>\tunnel-cf.ps1' status"
node packaging/remote.mjs run "powershell -NoProfile -ExecutionPolicy Bypass -File '<远程 tools 目录>\tunnel-cf.ps1' url"

# 3) 停止隧道（演示结束务必执行）
node packaging/remote.mjs run "powershell -NoProfile -ExecutionPolicy Bypass -File '<远程 tools 目录>\tunnel-cf.ps1' stop"
```

> 直接查看已注册任务与进程（不依赖脚本）：

```powershell
node packaging/remote.mjs run "Get-ScheduledTask -TaskName 'trpg-tunnel-cf' | Select-Object TaskName,State"
node packaging/remote.mjs run "Get-Process cloudflared | Select-Object Id,Path"
node packaging/remote.mjs run "Stop-ScheduledTask -TaskName 'trpg-tunnel-cf'; Get-Process cloudflared | Stop-Process -Force"
```

#### 6.3.3 方案 A：cloudflared 快速隧道（手动方式）

```powershell
# 1) 安装（winget；或从 Cloudflare 官方下载 cloudflared.exe 放到工具目录）
winget install --id Cloudflare.cloudflared

# 2) 起隧道（保持窗口不关；或用 tunnel-cf.ps1 start 后台运行）
cloudflared tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:9210

# 3) 从输出中取形如 https://<随机子域>.trycloudflare.com 的地址并验证
Invoke-WebRequest https://<随机子域>.trycloudflare.com/api/health -UseBasicParsing | Select-Object StatusCode
```

**局限**：地址每次重启都变；无鉴权；无 SLA。仅适合演示。

#### 6.3.4 方案 B：frp（自有公网服务器 / 固定端口）

适合需要**固定入口**或希望自行控制鉴权的场景。

服务端 `frps.toml`（部署在有公网 IP 的机器）：

```toml
bindPort = 7000
auth.method = "token"
auth.token = "<请更换为强随机值>"
```

客户端 `frpc.toml`（部署在服务端同机）：

```toml
serverAddr = "<frps 公网 IP>"
serverPort = 7000
auth.method = "token"
auth.token = "<与 frps 一致>"

[[proxies]]
name = "trpg-9210"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9210
remotePort = 19210
```

启动：

```powershell
.\frps.exe -c .\frps.toml     # 公网机器
.\frpc.exe -c .\frpc.toml     # 服务端机器
```

访问 `http://<frps 公网 IP>:19210/player/`。

`frpc` 也可注册为计划任务常驻：

```powershell
schtasks /Create /TN "trpg-tunnel-frp" /TR "<路径>\frpc.exe -c <路径>\frpc.toml" /SC ONSTART /RU SYSTEM /RL HIGHEST /F
schtasks /Run /TN "trpg-tunnel-frp"
```

> **安全**：TCP 模式暴露的是裸端口，**没有 HTTPS 也没有鉴权**，风险高于 cloudflared。
> 若要让小程序使用，必须走 **HTTPS + 已备案域名**（见第 7 节）：
> 在 frps 前置 Nginx/Caddy 做 TLS 终止与反代，并加上访问控制。

#### 6.3.5 公网加固方案（AC-4 第 18b 条 · 必做）

> 依据：CROSS-END-CONTRACT v1.4 §7.2 风险 **R7** 与 `PLAN-ACCEPTANCE.md` **AC-4 第 18b 条**。
> 实测 `/openapi.json`、`/docs`、`/redoc`、`/api/tables` 可**公网匿名**访问。
> 公网暴露期**必须给出并落实**加固方案（二选一或并用）。

##### 6.3.5.0 验收判据（T6 会按此验）

| # | 判据 | 期望 |
|---|---|---|
| 1 | 公网 `GET /player/` | **200** |
| 2 | 公网 `GET /api/health` | **200** |
| 3 | 公网 `GET /docs` | **不再匿名可达**（403/404 或 Access 登录页） |
| 4 | 公网 `GET /redoc` | 同上 |
| 5 | 公网 `GET /openapi.json` | 同上 |
| 6 | 公网 `GET /api/tables` | 同上 |

须附 **curl 证据**（见 §6.3.5.4）。

> ⚠️ **关键约束（容易做错）**：判据 1 与 2 要求 `/player/` 与 `/api/health` **匿名 200**。
> 因此**不能**用「全局 Basic Auth」或「Access 保护整个站点」的粗粒度做法 ——
> 那会把这两个路径也变成 401 / 登录页，**直接导致 18b FAIL**。
> 正确做法：**路径白名单放行必要路径（不加鉴权）**，白名单之外一律 404；
> 如需鉴权，只加在 `/app/` 等非必需路径上。详见 §6.3.5.1 与 §6.3.5.3。

**适用性条款（planner 补充，避免 T6 误判 FAIL）**：
本条**只在实际开启公网暴露时**按上表验收。若最终交付**不开启公网暴露**
（远程无隧道进程、无 80/443 监听、仅 9210 局域网监听），本条判 **N/A（未暴露）+ 方案已备**，
**不算 FAIL**，但必须在报告中附「未暴露」的实测证据（进程 / 监听核查输出）。

> 📌 **当前实际状态（2026-09-25 实测）：公网暴露处于【开启】状态，且加固【已生效】。**
> 因此 18b **按原判据验收**（不适用 N/A 豁免）：
> `cloudflared` 在运行、计划任务 `trpg-tunnel-cf` State=Running、
> 公网 `<当前地址>`（取法见 §6.3.1）实测 `/api/health` **200**、`/player/` **200**，
> 且 `/docs` `/redoc` `/openapi.json` `/api/tables` `/app/` 全部 **404**。
> ⚠️ 暴露是**间歇性**的（隧道开启期间才存在）：若在隧道停止后复验，请先确认进程与监听状态，
> 再按 N/A 条款判定，**不要**把「隧道已停」误判为 FAIL。反之亦然：复验前请先确认隧道是否在跑。

> ⚠️ **与契约 R1 叠加的风险（契约 v1.7 §7.2 提示）**：匿名者若能拿到 `campaign_id`，
> 可直接拉取 `/api/campaigns/{c}/events`（该端点按契约 §1.1 **必须**保持匿名可用，且 R1 无 viewer 过滤）。
> **本白名单已把 `/api/tables`（campaign 枚举来源）封为 404，等于切断了匿名枚举链**，
> 这是当前最主要的缓解。剩余风险是「已知 campaign_id 的匿名读取」，属契约 R1 范畴，
> 需服务端加可见性过滤才能根治（本轮未做，已记入 `ROADMAP-DEFERRED.md`）。

**复验前先判定「当前是否处于暴露状态」（T6 请先跑这一段）**：

```powershell
# 远程：隧道进程 / 计划任务 / 监听
node packaging/remote.mjs run "Get-Process cloudflared,frpc,frps,ngrok -ErrorAction SilentlyContinue | Select-Object ProcessName,Id"
node packaging/remote.mjs run "Get-ScheduledTask -TaskName 'trpg-tunnel-cf' -ErrorAction SilentlyContinue | Select-Object TaskName,State"
node packaging/remote.mjs run "Get-NetTCPConnection -State Listen | Select-Object -ExpandProperty LocalPort -Unique | Sort-Object"

# 远程：取当前公网地址（地址每次隧道重启都会变）
node packaging/remote.mjs run "Get-Content 'C:\trpg-tunnel\cloudflared.log' -Raw | Select-String 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches | ForEach-Object { $_.Matches } | ForEach-Object { $_.Value } | Select-Object -Last 1"
```

判定：
- **有 cloudflared 进程 / 任务 Running** → 暴露中 → **按 §6.3.5.0 判据表验收（不适用 N/A）**。
- **无隧道进程且无 80/443 监听** → 未暴露 → **判 N/A + 方案已备**，并附上面的核查输出作为证据。
- 无论哪种，都要在报告里写明**判定时的地址与时间**（地址是临时的）。

##### 6.3.5.1 采用白名单（allowlist），不要用黑名单

**推荐白名单**（只放行两端真正需要的路径）：

| 路径 | 放行 | 理由 |
|---|---|---|
| `/api/health` | ✅ 匿名 | AC-4 18b 判据 2 要求 200；也是存活探测路径 |
| `/player/`、`/player/*` | ✅ 匿名 | 玩家端页面；判据 1 要求 200 |
| `/access/*` | ✅（自身有 token 鉴权） | 玩家端 8 端点中的 6 个走这里 |
| `/ws` | ✅（自身有 token 鉴权） | 实时通道（需保留 Upgrade 头） |
| `/api/campaigns/*/events` | ✅ 匿名 | **F7 事件流主通道**，契约 §1.1 明示无鉴权 |
| `/app/`、`/app/*` | ⚠️ 可选 | 主持端 KP UI；演示需要，但**建议加 Basic Auth 或 IP 白名单** |
| 其它一切 | ❌ **404** | 含 `/docs`、`/redoc`、`/openapi.json`、`/api/tables`、`/mcp` 等 |

> 🚫 **绝对不要用「整个 `/api/` 全封」的粗粒度规则**：
> `GET /api/campaigns/{c}/events` 挂在 `/api/` 前缀下，且是玩家端 F7 的**主通道**。
> 一封就会让两端事件流整体失效（AC-3 也会连带 FAIL）。
> 必须精确放行 `/api/campaigns/*/events` 与 `/api/health`。

> ✅ **加固不影响两端功能**（可打消顾虑）：玩家端**只用**契约 §1.1 的 8 个端点 ——
> `GET /access/info`、`GET /access/table/resolve`、`GET /access/mobile/state`、
> `POST /access/mobile/action`、`POST /access/player/audio`、`GET /access/device/status`、
> `GET /api/campaigns/{c}/events`、`WS /ws` —— **全部在上表白名单内**，
> 不依赖任何被屏蔽路径。

##### 6.3.5.2 本轮实际落地方式：cloudflared 配置式路径白名单（已生效 · 实测通过）

> 队长裁决 2026-09-25 选 (a)：**不引入 Nginx/Caddy**，直接用 cloudflared 的 `--config` + `ingress`
> 在隧道边缘做路径白名单。这是**本轮实际落地方式**；§6.3.5.3 / §6.3.5.4 保留为生产替代方案。
>
> ⚠️ **但它有覆盖边界**：只对**公网（经隧道）**生效，**局域网直连不受保护** —— 详见本节末尾的「覆盖边界」小节。
> 长期/生产部署请优先采用 **§6.3.5.4（生产推荐；反代收口，对包括局域网在内的所有来源生效）**。
> 📌 **本轮交付范围说明**：队长裁决 —— 反代作为**生产推荐方案**写入本文档，**本轮不部署**
> （交付物中**不含**反代组件）。本轮实际落地的是 §6.3.5.2 的隧道边缘白名单 + §6.2 的防火墙来源收紧。

**部署位置与任务**：

```text
可执行文件 : C:\trpg-tunnel\cloudflared.exe
配置文件   : C:\trpg-tunnel\config.yml
日志       : C:\trpg-tunnel\cloudflared.log
计划任务   : trpg-tunnel-cf（SYSTEM / Highest / 开机自启）
任务动作   : cloudflared.exe tunnel --config "C:\trpg-tunnel\config.yml" --no-autoupdate
             --logfile "C:\trpg-tunnel\cloudflared.log" --url http://127.0.0.1:9210
```

**实际生效的 `C:\trpg-tunnel\config.yml`**：

```yaml
# cloudflared 配置：TRPG 公网暴露路径白名单（队长加固 v2：移除 /app 主持端控制台）
tunnel: trpg-quick
no-autoupdate: true
protocol: http2
ingress:
  - hostname: "*"
    path: ^/player(/.*)?$
    service: http://127.0.0.1:9210
  - hostname: "*"
    path: ^/access(/.*)?$
    service: http://127.0.0.1:9210
  - hostname: "*"
    path: ^/api/campaigns(/.*)?$
    service: http://127.0.0.1:9210
  - hostname: "*"
    path: ^/api/health$
    service: http://127.0.0.1:9210
  - hostname: "*"
    path: ^/ws$
    service: http://127.0.0.1:9210
  - service: http_status:404      # 其余一律 404（含 /app、/docs、/openapi.json、/api/tables 等）
```

> 🚫 **`/app/` 经隧道返回 404 是【有意为之】，不是回归（T6/T7 请勿误判）**
>
> 白名单 **v2 已移除 `^/app(/.*)?$` 规则**：原配置放行了主持端 KP 控制台却未加鉴权，
> 等于把 KP 操作面公开（残留①）。**移除后 `/app/` 经隧道访问恒为 404，这是预期行为。**
> 主持端 KP 改走**局域网** `http://192.168.10.110:9210/app/`（实测 200）。
> ⚠️ 验收时若看到公网 `/app/` 404，**不得判为「主持端挂了」或回归** —— 请用局域网地址验证 KP 可用性。

> 📌 **v2 变更（2026-09-25）**：**已移除 `^/app(/.*)?$` 规则** —— 原配置放行主持端 KP 控制台却未加鉴权，
> 等于把 KP 操作面公开（残留①）。现 `/app/` 公网返回 **404**（实测），KP 改走局域网 `http://192.168.10.110:9210/app/`。

**关键点**：
- 最后一条 **无 `hostname`/`path` 的兜底规则 `http_status:404`** 是白名单生效的核心 ——
  不在白名单内的路径**在隧道边缘就被拒绝**，请求根本到不了应用。
- 白名单与 §6.3.5.1 清单一致，且**精确放行** `^/api/campaigns(/.*)?$` 与 `^/api/health$` ——
  没有用「整个 `/api/` 全封」，F7 主通道因此不受影响（实测 200）。
- 白名单在**隧道边缘**生效，对**所有**公网流量有效；**不需要**改服务端代码，也不影响两端功能。

**实测证据（2026-09-25，公网 `<当前地址>`，取法见 §6.3.1）**：

| 路径 | 状态码 | 判定 |
|---|---|---|
| `/api/health` | **200** | ✅ 判据 2 |
| `/access/info`（无 token） | 401 | ✅ 预期（应用层鉴权） |
| `/access/info?token=<mobile>` | 200 | ✅ |
| `/api/campaigns/c_demo/events` | **200** | ✅ **F7 主通道未被误封** |
| `/app/` | **404** | ✅ 已封（config v2 移除；原 200 无鉴权） |
| `/ws`（普通 GET） | 404 | ⚠️ 见下方说明 |
| `/ws`（**WebSocket 握手**） | **OPEN + 收到 `{"kind":"PING"}`** | ✅ 实时通道正常 |
| `/docs` | **404** | ✅ 判据 3 |
| `/redoc` | **404** | ✅ 判据 4 |
| `/openapi.json` | **404** | ✅ 判据 5 |
| `/api/tables` | **404** | ✅ 判据 6 |
| `/mcp`、`/metrics/latency` | 404 | ✅ 额外收紧 |
| `/player/` | 404 | **200** | ✅ 判据 1（T2 已交付，实测 200） |

> ⚠️ **`/ws` 不要用 curl 判活**：对 `/ws` 发普通 HTTP GET 会得到 404（FastAPI 的 WebSocket 路由没有 HTTP 处理器），
> 这**不代表**隧道封了 WS。正确验证是发起真正的 WebSocket 握手。
> 本次已用 WebSocket 客户端实测：握手 **OPEN**，并收到服务端 `{"kind":"PING","ts":...}` 帧 —— 隧道放行 WS 正常。
> T6 复验 AC-3 / AC-4 时请用 WS 客户端，不要用 `Invoke-WebRequest /ws`。

**管理命令（远程）**：

```powershell
# 重启隧道（改完 config.yml 后必须重启）
node packaging/remote.mjs run "Restart-ScheduledTask -TaskName 'trpg-tunnel-cf'"

# 取当前公网地址（quick tunnel 地址每次重启都会变！）
node packaging/remote.mjs run "Get-Content 'C:\trpg-tunnel\cloudflared.log' -Raw | Select-String -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches | ForEach-Object { $_.Matches } | ForEach-Object { $_.Value } | Select-Object -Last 1"

# 任务状态与上次结果（0 = 成功；2147942402 = 找不到文件）
node packaging/remote.mjs run "Get-ScheduledTaskInfo -TaskName 'trpg-tunnel-cf' | Select-Object LastRunTime,LastTaskResult"
```

> ⚠️ **quick tunnel 地址每次重启都会变化**：本次加固重启后地址已从
> 已观察到 **3 次变更**：`impaired-nov-commodities-handed` → `wages-wellness-retailer-head` → `stakeholders-rational-refer-election`（旧地址均返回 530）。
> 交付/验收前务必重新取当前地址，不要硬编码。

> 📌 **配置副本**：`黑客松开发文档\tools\trpg-tunnel.yml` 存有一份同内容副本（**非生效路径**）。
> **生效路径是 `C:\trpg-tunnel\config.yml`**，改配置请改这里。
###### 覆盖边界：白名单只管公网，局域网完全不受保护

**这是最容易被误判的一点**（实测 2026-09-25，同一时刻两条路径结果完全不同）：

| 访问路径 | /docs | /redoc | /openapi.json | /api/tables |
|---|---|---|---|---|
| **公网**（经隧道，`<当前地址>`） | **404** | **404** | **404** | **404** |
| **局域网直连**（http://192.168.10.110:9210） | **200** | **200** | **200**（37KB） | **200** |

原因：白名单在 **cloudflared 隧道边缘**生效，只作用于**经隧道进来**的流量。
局域网内任何设备**直连 9210** 时，请求根本不经过 cloudflared，因此**不受白名单约束**。

实测 `http://192.168.10.110:9210/api/tables`（局域网，匿名）返回：

```json
{"tables":[{"table_id":"t3web-r1","campaign_id":"t3webc-r1","ruleset":"coc7","config":{}},
{"table_id":"tx","campaign_id":"cx",...},
{"table_id":"t_verify","campaign_id":"c_verify2",...},
{"table_id":"t_demo","campaign_id":"c_demo","ruleset":"coc7","config":{}},
{"table_id":"t_t2probe","campaign_id":"c_t2probe",...}]}
```

→ **局域网内可匿名枚举全部 table_id / campaign_id（含调试遗留桌）**，
再配合契约 **R1**（事件流无 viewer 过滤）即可读取任意战役事件流。

**这意味着**：
- **AC-4 第 18b 条（口径为「公网」）当前 PASS**；
- 但**若验收口径包含局域网**，则**未加固**，属**残余风险**。
- 对本次交付尤其相关：玩家端在局域网使用（http://192.168.10.110:9210/player/），
  局域网就是真实使用场景，不是「内部可信网络」的同义词（同网段可能有观众/其他设备）。

**局域网侧的缓解选项**（按代价从低到高）：

| # | 措施 | 状态 | 做法 |
|---|---|---|---|
| 1 | 收紧防火墙来源 | ✅ **已落实 2026-09-25** | `trpg-9210` 入站规则 RemoteAddress 由 Any 改为 `192.168.10.0/24` + `192.168.56.0/24` |
| 2 | 用反代统一收口 | ⏳ **生产推荐，本轮不部署** | 上 §6.3.5.4 的 Nginx/Caddy（同一套白名单对**所有**来源生效，含局域网） |
| 3 | 应用层关文档 | ⏳ 未做（需 T2 评估） | 以环境变量关闭 /docs /redoc /openapi.json（FastAPI docs_url=None 等）——属**服务端改动** |
| 4 | 服务端加可见性过滤 | ⏳ 未做（需契约变更） | 根治 R1（事件流无 viewer 过滤） |

> ⚠️ **措施 1 的实际效果要说清楚**：防火墙按**来源**过滤，不按**路径**过滤。
> 收紧后**只**挡住了 `192.168.10.0/24` 与 `192.168.56.0/24` **之外**的来源；
> **这两个网段内**的设备（含本机 192.168.10.160）访问 `/docs`、`/openapi.json`、`/api/tables` **实测仍为 200**。
> 也就是说：**同网段的玩家/观众/其他设备依然可以匿名读到这些路径** —— 局域网侧的匿名面**只是缩小了，没有被关闭**。

> 📌 **给验收的建议**：报告里请**分别**列出「公网」与「局域网」两行的实测结果，
> 不要把其中一条的结论套用到另一条上（这正是本次双方测量结果看似矛盾的根因）。

###### 应急操作：停隧道止血 / 回滚

```powershell
# A) 停隧道止血（立即消除公网暴露；局域网仍开放，见上方边界说明）
node packaging/remote.mjs run "Stop-ScheduledTask -TaskName 'trpg-tunnel-cf' -ErrorAction SilentlyContinue; Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force"
# 验证：无 cloudflared 进程
node packaging/remote.mjs run "Get-Process cloudflared -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"

# B) 重新开启（白名单配置仍在，地址会变，需重新取）
node packaging/remote.mjs run "Start-ScheduledTask -TaskName 'trpg-tunnel-cf'"

# C) 改完 config.yml 后重启使白名单生效
node packaging/remote.mjs run "Restart-ScheduledTask -TaskName 'trpg-tunnel-cf'"

# D) 回滚为不限制路径的旧行为（不推荐，仅在白名单导致功能异常时临时使用）
#    编辑 C:\trpg-tunnel\config.yml：删掉末条 http_status:404，仅保留一条 service: http://127.0.0.1:9210
#    然后执行 C) 重启
```

> ⚠️ **注意**：停隧道**不会**关闭局域网暴露。若要同时止血，需另加防火墙限制（见上表措施 1）。

##### 6.3.5.3 生产替代方案 A：Cloudflare 命名隧道 + Access（⚠️ 非默认；前置条件：自有域名）

> 🚫 **前置条件（否则这一步会卡住）**：**cloudflared quick tunnel 不支持 Cloudflare Access 策略**。
> quick tunnel 用的是 `*.trycloudflare.com` 临时子域，**不属于你的 Cloudflare 账户**，无法为其创建 Access 应用。
> 因此方案 (a) **必须**先满足：**自有域名已接入 Cloudflare** + **命名隧道**（`cloudflared tunnel login` / `create` / `route dns`）。
> 没有自有域名时请直接走 **§6.3.5.4（默认推荐）** 或保持本轮的隧道边缘白名单。

```powershell
# 1) 登录并创建命名隧道（只需一次）
cloudflared tunnel login
cloudflared tunnel create trpg
cloudflared tunnel route dns trpg trpg.<你的域名>

# 2) 配置 ingress：先屏蔽敏感路径，再兜底到本地服务
```

```yaml
# %USERPROFILE%\.cloudflared\config.yml
tunnel: trpg
credentials-file: C:\Users\<用户>\.cloudflared\<tunnel-id>.json

ingress:
  # 先精确匹配并拒绝敏感路径（返回 404，不泄露存在性）
  - hostname: trpg.<你的域名>
    path: ^/(docs|redoc|openapi\.json|mcp)(/.*)?$
    service: http_status:404
  # 再拒绝 /api/tables 的匿名枚举
  - hostname: trpg.<你的域名>
    path: ^/api/tables(/.*)?$
    service: http_status:404
  # 其余放行到本地服务
  - hostname: trpg.<你的域名>
    service: http://127.0.0.1:9210
  - service: http_status:404
```

```powershell
# 3) 启动命名隧道
cloudflared tunnel run trpg

# 4) 在 Cloudflare Zero Trust 控制台为该 hostname 建 Access 应用
#    （Access -> Applications -> Add an application -> Self-hosted）
#    策略建议：Allow + 指定邮箱域 / 一次性 PIN / 服务令牌；
#    注意：Access 会拦截浏览器访问，小程序 wx.request 需改用 Service Token（CF-Access-Client-Id/Secret）
```

> ⚠️ **Access 必须为必需路径配置 Bypass 策略**：Access 默认保护**整个** hostname，
> 会把 `/player/` 与 `/api/health` 也变成登录页，**直接导致 AC-4 18b 判据 1–2 FAIL**。
> 请在 Access 应用里新增 **Bypass** 策略（或改用路径级应用），放行：
> `/player/*`、`/api/health`、`/access/*`、`/ws`、`/api/campaigns/*/events`；
> 其余路径保持 Allow（需登录）。这与 §6.3.5.3 的白名单是同一套路径清单。

> ⚠️ **Access 与小程序**：Cloudflare Access 默认基于浏览器会话，小程序 `wx.request` 不会带该会话。
> 若小程序需经 Access 访问，请为该应用创建 **Service Token**，并在小程序请求头带上
> `CF-Access-Client-Id` / `CF-Access-Client-Secret`（属于额外凭据，注意保密与轮换）。
> 更简单的做法：小程序走局域网/内网，公网入口只给 PC 浏览器端与演示使用。

##### 6.3.5.4 生产替代方案 B（✅ 生产推荐 · **本轮不部署**）：Nginx / Caddy 反代 + 路径白名单

**Caddy（自动 HTTPS，白名单写法）：**

```caddy
trpg.<你的域名> {
    # ---- 白名单：只放行两端需要的路径，且【不加鉴权】 ----
    @public path /api/health \
                /player /player/* \
                /access/* \
                /ws \
                /api/campaigns/*/events

    handle @public {
        reverse_proxy 127.0.0.1:9210 {
            # WebSocket 升级（Caddy 默认已透传，此处显式声明更稳）
            header_up Upgrade {http.upgrade}
            header_up Connection {http.connection}
        }
    }

    # ---- 主持端 /app/：放行但要求 Basic Auth（不影响两端玩家端）----
    @kp path /app /app/*
    handle @kp {
        basicauth {
            # 用 caddy hash-password 生成
            trpg $2a$14$<bcrypt-hash>
        }
        reverse_proxy 127.0.0.1:9210
    }

    # ---- 其它一切（/docs /redoc /openapi.json /api/tables /mcp ...）：404 ----
    handle {
        respond 404
    }
}
```

**Nginx（白名单写法）：**

```nginx
server {
    listen 443 ssl;
    server_name trpg.<你的域名>;

    ssl_certificate     /etc/ssl/trpg/fullchain.pem;
    ssl_certificate_key /etc/ssl/trpg/privkey.pem;

    # WebSocket 升级所需的 map（放在 http{} 块，若已存在则跳过）
    # map $http_upgrade $connection_upgrade { default upgrade; '' close; }

    # ---- 1) 白名单：放行玩家端必需路径，【不加鉴权】----
    #     注意精确到 /api/campaigns/*/events，禁止用 location /api/ 全封
    location = /api/health            { proxy_pass http://127.0.0.1:9210; }
    location ^~ /player/              { proxy_pass http://127.0.0.1:9210; }
    location ^~ /access/              { proxy_pass http://127.0.0.1:9210; }
    location = /ws                    { proxy_pass http://127.0.0.1:9210; }
    location ~ ^/api/campaigns/[^/]+/events$ { proxy_pass http://127.0.0.1:9210; }

    # ---- 2) 主持端 /app/：放行但要求 Basic Auth（可选；不影响两端玩家端）----
    location ^~ /app/ {
        auth_basic           "TRPG KP";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://127.0.0.1:9210;
    }

    # ---- 3) 其它一切：404（不泄露存在性）----
    #     覆盖 /docs /redoc /openapi.json /api/tables /mcp 等
    location / { return 404; }

    # ---- 4) 反代公共参数（放在 server 块内，作用于上面所有 proxy_pass）----
    proxy_http_version 1.1;
    proxy_set_header Upgrade    $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host       $host;
    proxy_set_header X-Real-IP  $remote_addr;
    proxy_read_timeout 3600s;   # WS 长连接，勿用默认 60s
}
```

> 若只想要最简版本：把 `/app/` 也并入白名单（不加鉴权），其余仍 `location / { return 404; }`。
> 这样判据 1–6 全部满足，代价是主持端 UI 也公网可达（演示可接受，长期不建议）。

生成 Basic Auth 口令：

```powershell
# Caddy
caddy hash-password --plaintext '<你的口令>'
# Nginx（需要 htpasswd 工具；Windows 可用 openssl 或 WSL）
htpasswd -c /etc/nginx/.htpasswd trpg
```

##### 6.3.5.5 加固后验收（AC-4 第 18b 条 · 附 curl 证据）

**判据 1–2（必须 200）：**

```bash
U=https://<你的公网域名>
curl -s -o /dev/null -w 'player  %{http_code}\n' "$U/player/"
curl -s -o /dev/null -w 'health  %{http_code}\n' "$U/api/health"
# 期望：两行都是 200
```

**判据 3–6（不得匿名可达）：**

```bash
U=https://<你的公网域名>
for p in /docs /redoc /openapi.json /api/tables; do
  curl -s -o /dev/null -w "$p  %{http_code}\n" "$U$p"
done
# 期望：全部 403 / 404（或 Access 登录页 302/200+HTML 登录页，见下方说明）
```

**判定说明**：
- 白名单反代（§6.3.5.3）→ 期望 **404**。
- Cloudflare Access（§6.3.5.2）→ 匿名请求会被重定向到登录页，curl 通常看到 **302** 或登录页 HTML；
  关键是**不能返回真实内容**。可用 `curl -s "$U/openapi.json" | head -c 200` 确认返回的不是 API schema。

**回归（确认加固没打坏两端功能）：**

```bash
U=https://<你的公网域名>; T=<mobile token>
curl -s -o /dev/null -w 'info        %{http_code}\n' "$U/access/info?token=$T"
curl -s -o /dev/null -w 'resolve     %{http_code}\n' "$U/access/table/resolve?code=<code>&token=$T"
curl -s -o /dev/null -w 'state       %{http_code}\n' "$U/access/mobile/state?table_id=<table>&token=$T"
curl -s -o /dev/null -w 'events(F7)  %{http_code}\n' "$U/api/campaigns/<campaign>/events?since=0&limit=50"
# 期望：全部 200 —— 尤其 events 必须 200，否则白名单把 /api/ 封过头了
```

**PowerShell 等价写法：**

```powershell
$u = 'https://<你的公网域名>'
foreach ($p in @('/player/','/api/health','/docs','/redoc','/openapi.json','/api/tables')) {
  try { $r = Invoke-WebRequest ($u + $p) -UseBasicParsing -TimeoutSec 15; Write-Host ($p + ' -> ' + $r.StatusCode) }
  catch { Write-Host ($p + ' -> ' + $_.Exception.Response.StatusCode.value__) }
}
```

**加固前后对照（2026-09-25，方式见 §6.3.5.2）**：

| 路径 | 加固前 | 加固后 | AC-4 18b 要求 | 判定 |
|---|---|---|---|---|
| `/openapi.json` | 200 | **404** | 非匿名可达 | ✅ |
| `/docs` | 200 | **404** | 非匿名可达 | ✅ |
| `/redoc` | 200 | **404** | 非匿名可达 | ✅ |
| `/api/tables` | 200 | **404** | 非匿名可达 | ✅ |
| `/mcp` | 401 | **404** | （额外收紧） | ✅ |
| `/metrics/latency` | — | **404** | （额外收紧） | ✅ |
| `/api/health` | 200 | **200** | 必须 200 | ✅ 判据 2 |
| `/api/campaigns/{c}/events` | 200 | **200** | 必须可用（F7 主通道） | ✅ |
| `/access/info`（无 token / 带 token） | 401 / 200 | **401 / 200** | 不变 | ✅ |
| `/ws`（WebSocket 握手） | OPEN | **OPEN + PING** | 必须可用 | ✅ |
| `/player/` | 404 | **200** | **必须 200** | ✅ 判据 1（T2 已交付） |

> **结论**：加固已于 2026-09-25 在远程**落实并实测生效**。**AC-4 18b 判据 3–6 已 PASS**；
> **判据 1（公网 `/player/` 200）已满足**（T2 已交付玩家端，实测 200）。**AC-4 18b-公网 判据 1–6 全部 PASS**。
> 证据：`evidence/T7-tunnel-verify.txt`。

> ⚠️ **地址反复变更**：本轮已观察到 **3 次**（`impaired-nov-commodities-handed` → `wages-wellness-retailer-head` → `stakeholders-rational-refer-election`），
> 旧地址均返回 **530**。**复验前务必重新取当前地址**（`C:\trpg-tunnel\current-url.txt`），不要引用本文档中的任何历史地址。

##### 6.3.5.6 最小加固清单（来不及上反代时的临时措施）

| 措施 | 命令 / 做法 |
|---|---|
| 用完即停 | `tunnel-cf.ps1 stop`（最重要） |
| 缩短暴露窗口 | 只在演示前启动，演示后立即停止 |
| 不公开地址 | 不把 trycloudflare 地址发到群/文档外 |
| 限制访问来源 | 若走 frp/反代，配置 IP 白名单 |
| 监控访问 | 检查 cloudflared 日志与 `server/var/server.out.log` 的异常请求 |

##### 6.3.5.7 残留暴露面（实测登记 · 本轮不修）

> 来源：planner 实测 + integrator 独立复核（2026-09-25）。两条都**在公网白名单生效之后**依然存在，
> 属**有意保留**（功能性依赖）或**未做的加固**，登记备查，不粉饰。

###### 残留 ①（✅ 已修复）：`/app/` 主持端控制台公网匿名可访问

> ✅ **状态更新（2026-09-25）**：队长已按「缓解 B」处理 —— **把 `^/app` 移出白名单**（config v2）。
> 实测 `https://<当前公网地址>/app/` → **404**。**该残留已关闭**，KP 改走局域网。
> 下面保留原始记录与两条缓解方案，供后续参考。

| 项 | 内容 |
|---|---|
| 实测 | `https://<公网地址>/app/` → **200**（len=576，无 `WWW-Authenticate` 头） |
| 实测 | `https://<公网地址>/app/assets/index-DE5dm9qD.js` → **200**（len≈79KB，主持端 bundle 可完整下载） |
| ⚠️ 勘误（2026-09-27 追加，原记录不改） | 上行的产物名 `index-DE5dm9qD.js` **从未对应任何真实构建产物**（历史批次为 `index-BUCDjFsz.js` / `index-DsfUF84T.js` 等）—— 属当时记录的转写错。**现行产物**见 `docs/BUILD-WEB.md` §5.2（`index-DsfUF84T.js`，96,095 B）。 |
| 原因 | 白名单里有 `^/app(/.*)?$`（为了演示时 KP 能从公网打开），但**没有加 Basic Auth** |
| 影响 | **任何人拿到公网地址即可打开主持端控制台**（开桌、开回合、审批旁白等 KP 操作面） |
| 缓解 A | 对 `/app/` 加 Basic Auth（Nginx/Caddy 配置见 §6.3.5.4，Basic Auth 正是只加在 /app 上） |
| 缓解 B | **暴露期把 `/app` 移出白名单**（演示 KP 走局域网 `http://192.168.10.110:9210/app/` 即可）—— 改动最小 |
| 本轮处置 | ✅ **已修**（2026-09-25）：队长按缓解 B 移除 `^/app` 规则，实测 `/app/` → 404 |

> 缓解 B 的具体做法：编辑 `C:\trpg-tunnel\config.yml`，删除 `^/app(/.*)?$` 那条 ingress 规则，
> 然后 `Restart-ScheduledTask -TaskName 'trpg-tunnel-cf'`。
> ⚠️ 注意：**不要**把 `/access/*` 一起删掉（玩家端要用）；`/app` 与 `/access` 是两条独立规则。

###### 残留 ②：`/api/campaigns/{c}/events` 公网匿名可访问（契约 R1 残留）

| 项 | 内容 |
|---|---|
| 实测 | `https://<公网地址>/api/campaigns/x/events?since=-1&limit=1` → **200** `{"events":[],"tip":-1}` |
| 原因 | 该端点是 **F7 事件流主通道**，契约 §1.1 要求它**保持匿名可用**（白名单已精确放行） |
| 影响 | 属契约 **R1**（事件流无 viewer 过滤）—— 知道 `campaign_id` 即可读该战役全部事件 |
| 关键缓解 | ✅ 枚举入口 **`/api/tables` 已封 404** ⇒ 匿名者**拿不到 `campaign_id`**，风险显著降低 |
| 残余风险 | 若 `campaign_id` 经其他途径泄露（日志、截图、口播、局域网侧枚举），匿名者仍可直接拉取 |
| 根治 | 服务端加可见性过滤（需契约变更，本轮不做）；或对匿名关闭该路径（会破坏 F7，需先改契约） |
| 本轮处置 | **未修**（登记）；已记入 `ROADMAP-DEFERRED.md` §2.1 残余风险 1 / 2 |

###### 残留暴露面汇总（公网口径，加固后）

| 路径 | 状态 | 是否可接受 |
|---|---|---|
| `/api/health` | 200 匿名 | ✅ 预期（健康检查） |
| `/player/` | 200 匿名 | ✅ 预期（18b 判据 1） |
| `/access/*` | 401 / 200 | ✅ 受 token 保护 |
| `/app/` | **404** | ✅ **已封**（config v2 移除该规则，残留①已关闭） |
| `/api/campaigns/{c}/events` | **200 匿名** | ⚠️ **残留②**，已被「封 /api/tables」显著缓解 |
| `/docs` `/redoc` `/openapi.json` `/api/tables` `/mcp` `/metrics/latency` | **404** | ✅ 已封 |

#### 6.3.6 选择建议

| 场景 | 推荐 | 理由 |
|---|---|---|
| 场景 | 推荐 | 理由 |
|---|---|---|
| 临时演示 / 联调（**本轮采用**） | cloudflared quick tunnel + **隧道边缘路径白名单**（§6.3.2 / §6.3.5.2） | 免账号、自带 HTTPS、一条命令；**但只保护公网，局域网不受保护** |
| **长期 / 生产部署（生产推荐 · 本轮不部署）** | **§6.3.5.4 反代 + 路径白名单（Nginx / Caddy）** | 同一套白名单对**包括局域网在内的所有来源**生效，可加 Basic Auth 与 IP 白名单 |
| 有自有域名、要身份鉴权 | §6.3.5.3 命名隧道 + Cloudflare Access | 固定域名 + 零信任登录；⚠️ **quick tunnel 不支持 Access**，必须先有自有域名 |
| 自有服务器 / 固定端口 | §6.3.4 frp + HTTPS 反代 + 访问控制 | 完全自控，但需自行加固 |

> **一句话选择法**：只需要临时给外部看 → quick tunnel + 边缘白名单（并记住局域网不设防）；
> 要真正收口（含局域网）→ 上反代（§6.3.5.4），这是**默认推荐**。

【已实测：本轮公网地址与端点状态见 §6.3.1 与 §6.3.5.2 的实测表；证据落盘 `evidence/T7-tunnel-verify.txt`】

## 7. 微信小程序合法域名说明

微信小程序正式版要求请求域名满足 **HTTPS + 已 ICP 备案 + 已在小程序后台配置**。两种模式：

| 模式 | 配置 | 适用 |
|---|---|---|
| 开发 / 演示 | 开发者工具 → 详情 → 本地设置 → 勾选 **不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书** | 局域网 `http://192.168.10.110:9210` 直连 |
| 生产 | 小程序后台 → 开发 → 开发设置 → 服务器域名 → request 合法域名 / socket 合法域名 填入 `https://<你的域名>` | 需 HTTPS 证书 + 备案 |

> 注意：`socket` 合法域名用于 `wx.connectSocket`，必须单独配置，且与 request 域名一致最省事。
> 详见 `MINIPROGRAM.md`。

## 8. 故障排查

| 现象 | 可能原因 | 处置 |
|---|---|---|
| `start.bat` 报 `python not found` | 未安装或未加入 PATH | 重装 Python 并勾选 Add to PATH |
| `start.bat` 一闪而过 / 报 PowerShell **语法错误**（如 `An expression was expected after '('`） | **`start.ps1` 缺 UTF-8 BOM**，PS 5.1 按 GBK 解析中文 → 字符串被破坏 | 确认 `server/start.ps1` 带 BOM（前三字节 `EF BB BF`）；见下方「构建产物 .ps1 必须带 BOM」 |
| `uvicorn/fastapi missing` | 依赖未装 | `pip install -r requirements.txt` |
| health 轮询超时（退出码 1） | 启动异常 / 端口被占 | 看 `var\server.err.log`；`netstat -ano \| findstr :9210` |
| 退出码 2 | 9210 已在监听 | 直接用现有实例；如需重启先 `stop.bat` |
| `/player/` 返回 404 `player_not_built` | `server/player-web/` 缺文件 | 把 `clients/web-player/` 内容拷入 `server/player-web/` |
| `/app/` 404 | `web/dist/` 缺失 | 确认包完整（`CHECKSUMS.txt` 校验） |
| 接口 401 | token 缺失/错误 | 确认对应端 token 与 `access_config.yaml` 一致 |
| 接口 403 `kp_only` / `recorder_only` | 用了错误端的 token | 玩家端用 `mobile`，主持端用 `webapp` |
| 手机打不开 | 防火墙未放行 / 不同网段 | 见 6.2；确认手机与服务器同一 Wi-Fi |
| WS 频繁断开 | 代理超时 / 网络抖动 | 客户端会自动退避重连（1/2/4/8s，上限 30s）并带 `last_seq` 补齐 |
| 小程序请求失败 | 合法域名未配置 | 见第 7 节 |

### 构建产物 .ps1 必须带 UTF-8 BOM（踩过的坑）

**Windows PowerShell 5.1 读无 BOM 的 `.ps1` 会按 ANSI/GBK 解析**，含中文的脚本会被破坏、直接语法报错。
而 **PowerShell 7 默认按 UTF-8 读**，所以**用 pwsh 7 自检会漏掉这个坑**。

**本项目实测**：`server/packaged/start.ps1` 曾因缺 BOM，在 PS 5.1 下报 **5 个语法错误**（服务起不来），
而同一文件在 pwsh 7 下 **errors=0**。补 BOM 后恢复正常。

**自检命令（必须用 5.1）**：

```powershell
$ps51 = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
Get-ChildItem . -Recurse -Filter *.ps1 | ForEach-Object {
  $code = "`$e=`$null;`$t=`$null; [System.Management.Automation.Language.Parser]::ParseFile('" + $_.FullName + "',[ref]`$t,[ref]`$e)|Out-Null; if (`$e) { Write-Output ('errors=' + `$e.Count) } else { 'errors=0' }"
  Write-Output ($_.Name + '  ' + ((& $ps51 -NoProfile -Command $code) -join ' '))
}
```

**写文件时显式带 BOM**（不要依赖 `Set-Content -Encoding UTF8` —— 它在 PS 5.1 下带 BOM、在 PS 7 下**不带**）：

```powershell
[IO.File]::WriteAllText($path, $content, (New-Object Text.UTF8Encoding $true))
```

## 9. 部署自检清单（交付验收用）

```powershell
# 1. 健康
Invoke-RestMethod http://127.0.0.1:9210/api/health

# 2. 主持端与玩家端页面
(Invoke-WebRequest http://127.0.0.1:9210/app/    -UseBasicParsing).StatusCode
(Invoke-WebRequest http://127.0.0.1:9210/player/ -UseBasicParsing).StatusCode

# 3. 监听地址（应为 0.0.0.0）
Get-NetTCPConnection -State Listen -LocalPort 9210 | Select-Object LocalAddress,LocalPort

# 4. 防火墙规则
Get-NetFirewallRule -DisplayName 'trpg-9210' | Select-Object DisplayName,Enabled,Action

# 5. 三端鉴权矩阵（示例：无 token 应 401）
try { Invoke-WebRequest http://127.0.0.1:9210/access/info -UseBasicParsing } catch { $_.Exception.Response.StatusCode.value__ }
```

**实测输出（2026-09-25，远程 9210，T2 部署后）**：

~~~text
health  = 200  {"status":"ok","version":"0.1.0-t12","ts":"2026-09-25T02:28:29Z"}
/app/   = 200
/player/ = 200
listen  = 0.0.0.0:9210
firewall= trpg-9210 Enabled=True Action=Allow
access/info (无 token) = 401
python -m pytest tests/ -q  ->  598 passed / 0 failed   (基线 541, 零回归)
~~~

证据文件：`evidence/T2-server.txt`（端点/鉴权矩阵/封装包/公网/冻结契约）、
`evidence/T2-ws-broadcast.txt`（WS 广播公网实测）、`evidence/T6-acceptance.md`（端到端验收）。

## 10. 交付包解压说明

- 交付包文件名：`TRPG-交付包-v1.zip`，内含顶层目录 `TRPG-交付包-v1/`。
- **Windows 资源管理器**直接右键解压：中文文件名正常。
- 用 **PowerShell `Expand-Archive`** 解压时，若包由 `tar` 生成可能出现中文名乱码；
  本交付包默认使用 `Compress-Archive` 生成，两种方式均正常（详见 `BUILD-INFO.json` 的 `zipTool` 字段）。
- 解压后先跑 `CHECKSUMS.txt` 校验，再执行 `快速开始.bat`。
