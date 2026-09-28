# OPERATIONS.md —— 日常运维手册（启停 / 备份 / 恢复 / 排障）

> 状态：**骨架**（T7 阶段定稿）。标 `【待回填】` 的条目在 T2/T6 完成后替换为实测值。
> 相关文档：`DEPLOY.md`（首次部署与网络暴露）。

---

## 1. 服务拓扑速查

| 项 | 值 |
|---|---|
| 主机 | Windows，SSH 别名 `gzq110`（192.168.10.110，用户 Administrator） |
| 远程项目根 | `C:\Users\Administrator\Desktop\黑客松开发文档\trpg` |
| 服务 | FastAPI / uvicorn，端口 **9210**，监听 `0.0.0.0` |
| 进程标识 | `server/var/agent_9210.pid` |
| 日志 | `server/var/server.out.log`（stdout）、`server/var/server.err.log`（stderr） |
| 计划任务 | `trpg-9210-sys`（历史遗留，`stop.bat` 会尽力 `schtasks /End`；当前以直接拉起为主） |
| 本机操作助手 | `node packaging/remote.mjs run\|put\|get\|status` |
| 公网隧道 | 计划任务 `trpg-tunnel-cf`（SYSTEM，cloudflared quick tunnel + 路径白名单 `C:\trpg-tunnel\config.yml`）→ 见 §2.3 |
| 隧道管理脚本 | `packaging/tunnel-cf.ps1`（start/stop/status/url/install/uninstall） |

## 2. 启停

### 2.1 本地（交付包所在机器）

```cmd
cd server
start.bat      :: 退出码 0=新起成功 1=失败 2=已在运行
stop.bat       :: 退出码 0=已释放 1=仍占用
```

### 2.2 远程（192.168.10.110）

```powershell
# 状态总览（health + /app + /player + 监听 + 计划任务）
node packaging/remote.mjs status

# 远程重启
node packaging/remote.mjs run "schtasks /End /TN trpg-9210-sys; schtasks /Run /TN trpg-9210-sys"
# 权限不足时改用：
node packaging/remote.mjs run "Stop-ScheduledTask -TaskName 'trpg-9210-sys'; Start-ScheduledTask -TaskName 'trpg-9210-sys'"
```

> 中文路径一律经 `-EncodedCommand`（UTF-16LE base64）传递，避免编码损坏；不要使用 `ControlMaster`（本机 OpenSSH 会报 `getsockname failed`）。

### 2.3 公网隧道（cloudflared quick tunnel）

远程已注册计划任务 `trpg-tunnel-cf`（SYSTEM / Highest）常驻运行 cloudflared 快速隧道，
把 `http://127.0.0.1:9210` 暴露为临时公网地址。管理与排障用 `packaging/tunnel-cf.ps1`：

```powershell
# 状态（进程 / 计划任务 / 当前公网地址 / 端点探测）—— 只读，安全
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\tunnel-cf.ps1 status

# 只取当前公网地址（地址每次重启会变，别硬编码）
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\tunnel-cf.ps1 url

# 启动 / 停止
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\tunnel-cf.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\tunnel-cf.ps1 stop

# 注册 / 注销开机常驻计划任务
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\tunnel-cf.ps1 install
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\tunnel-cf.ps1 uninstall
```

从本机操作远程主机：

```powershell
node packaging/remote.mjs run "Get-ScheduledTask -TaskName 'trpg-tunnel-cf' | Select-Object TaskName,State"
node packaging/remote.mjs run "Get-Process cloudflared | Select-Object Id,Path"
node packaging/remote.mjs run "Stop-ScheduledTask -TaskName 'trpg-tunnel-cf'; Get-Process cloudflared | Stop-Process -Force"
```

**公网地址**：**不写死** —— quick tunnel 每次重连都会更换域名（本轮已实测变更 3 次，旧地址返回 530）。请用下方命令实时获取。

**取当前地址（不要硬编码）**：

```powershell
# 权威：日志动态解析（队长裁决：以日志为准）
node packaging/remote.mjs run "Get-Content C:\trpg-tunnel\cloudflared.log | Select-String 'trycloudflare' | Select-Object -Last 1"

# 备用：current-url.txt（**可能滞后**，仅作交叉参考）
node packaging/remote.mjs run "Get-Content 'C:\trpg-tunnel\current-url.txt' -ErrorAction SilentlyContinue"
```

> ⚠️ **取址以日志动态解析为准**（`current-url.txt` 可能滞后）。
> 桌面旧乱码目录里的 `tunnel.url.txt` **是过期地址**（未清理），**已有队友被它带偏过**，请勿引用。
> **交付文档不写死域名** —— 过期地址返回 530 会误导复验。

> ⚠️ **加固现状**：隧道已配置**路径白名单**（`C:\trpg-tunnel\config.yml`，见 `DEPLOY.md` §6.3.5.2）——
> 仅放行 `/player/`、`/app/`、`/access/*`、`/api/campaigns/*`、`/api/health`、`/ws`，其余一律 404。
> 实测 `/docs` `/redoc` `/openapi.json` `/api/tables` `/mcp` `/metrics/latency` 均已 **404**。
> 但 quick tunnel 本身仍是**无鉴权入口**（白名单内的路径匿名可访问），
> **演示结束仍应 `Stop-ScheduledTask -TaskName trpg-tunnel-cf`**，不要长期常驻、不要公开发布地址。
> 生产改用 Cloudflare 命名隧道 + Access 或 frp + HTTPS 反代。详见 `DEPLOY.md` §6.3。

> ⚠️ **路径纪律（历史教训）**：cloudflared.exe 曾位于乱码目录
> `C:\Users\Administrator\Desktop\榛戝鏉惧紑鍙戞枃妗tools\`（「黑客松开发文档」的 GBK 乱码形态），
> 任何人清理该目录都会让隧道起不来。**队长已把可执行文件与配置迁到纯 ASCII 路径 `C:\trpg-tunnel\`** 并更新任务指向。
> **今后隧道/服务文件一律放纯 ASCII 路径**，不要把可执行文件或配置放在中文目录（PowerShell 5.1 与 scp 的编码假设都不稳）。

#### 隧道相关故障

| 现象 | 原因 | 处置 |
|---|---|---|
| 公网地址打不开 | 隧道进程已退出 / 地址已变 | `tunnel-cf.ps1 status` 查看；用 `url` 取新地址 |
| 计划任务 Running 但无地址 | cloudflared 启动失败 | 看 cloudflared 日志；`tunnel-cf.ps1 start` 前台重试 |
| 公网 401 | 访问的是 `/access/*` 且未带 token | 属预期；带 `?token=` 或 `Authorization: Bearer` |
| 公网 404 `/player/` | `/player/` 未部署或白名单未放行 | 见 `DEPLOY.md` 第 8 节 `player_not_built`；白名单需含 `^/player` |
| 无法上传脚本到远程中文路径 | scp 与远端编码不一致 | 先传到 `C:/Windows/Temp/` 再用远程 PowerShell `Copy-Item` 移入 |

## 3. 健康检查

```powershell
# 本机
Invoke-RestMethod http://127.0.0.1:9210/api/health

# 远程（经 SSH）
node packaging/remote.mjs run "(Invoke-RestMethod http://127.0.0.1:9210/api/health) | ConvertTo-Json -Compress"

# 监听地址（应 0.0.0.0）
node packaging/remote.mjs run "Get-NetTCPConnection -State Listen -LocalPort 9210 | Select-Object -First 1 LocalAddress"
```

期望：`{"status":"ok","version":"<版本>"}`。【待回填：当前部署版本号】

## 4. 备份

### 4.1 改动前必备份

任何远程改动前，先在远程做全量快照：

```powershell
node packaging/remote.mjs run "$ts = Get-Date -Format yyyyMMdd-HHmmss; $p='C:\Users\Administrator\Desktop\黑客松开发文档'; Copy-Item -Recurse -Force \"$p\trpg\" \"$p\trpg_backup_$ts\"; Write-Output \"backup: $p\trpg_backup_$ts\""
```

### 4.2 备份内容与保留策略

| 内容 | 说明 |
|---|---|
| `trpg/` 全量源码与配置 | 含 `configs/access_config.yaml`（凭据） |
| `server/var/*.log` | 排障用；不进交付包（打包时按 `*.log` 排除） |
| 冻结契约 6 项 sha256 清单 | 见第 6 节（契约 v1.4 §1.5 裁定为 6 项） |

保留策略建议：至少保留最近 3 个 `trpg_backup_<ts>`；发布新版本前额外留一份。

【待回填：远程 `trpg_backup_*` 目录实际清单与 T2 记录的备份路径】

## 5. 恢复

```powershell
# 1) 停服
node packaging/remote.mjs run "cd 'C:\Users\Administrator\Desktop\黑客松开发文档\trpg'; .\stop.bat" 2>$null

# 2) 还原（示例：还原到指定快照）
node packaging/remote.mjs run "$p='C:\Users\Administrator\Desktop\黑客松开发文档'; Remove-Item -Recurse -Force \"$p\trpg\"; Copy-Item -Recurse -Force \"$p\trpg_backup_<ts>\" \"$p\trpg\""

# 3) 起服并验证
node packaging/remote.mjs run "cd 'C:\Users\Administrator\Desktop\黑客松开发文档\trpg'; .\start.bat"
node packaging/remote.mjs status
```

> 恢复后**必须**重跑第 6 节哈希校验与第 3 节健康检查，确认冻结契约未被改动。

## 6. 冻结契约完整性校验

交付硬约束：下列文件**哈希不得变化**，且既有 REST 端点与 `/access` 既有 11 端点签名**行为不得变化**。

> ⚠️ **哈希更正（integrator 实测 2026-09-25）**：契约 v1.4 §1.5 与 `evidence/AC-CHECKLIST.md` 附录 A1 中
> `app/web/ws_protocol.py` 的哈希只有 **63** 个字符（有效 SHA256 应为 64），**照抄会导致 AC-7#28 永远判不等**。
> 远程实算的真实值是 `3793B1E31C578D04D7FAC95E6113BDB252D2862B78976D1394825278906240F7`
> （基线串漏了第 17 位的 `F`）。本表已用更正后的值。请 planner/verifier 同步修正契约 §1.5 与 A1。

> **口径更正**：契约 v1.4 §1.5 已按远程实测裁定为 **6 项**（3 个代码/配置 + `docs/contracts/` 下 3 个文档）。
> 计划书早期写的「五件」是把 `docs/contracts/*` 当成 1 项，**以 6 项为准**（AC-7 第 28 条）。

| # | 文件（相对 PROJ） | 基线 sha256 |
|---|---|---|
| 1 | `trpg/agent/events.py` | `839B1016610D54D9C4528AF4D9B68425412FF5E9107890D7F3B2C47EA1635531` |
| 2 | `app/web/ws_protocol.py` | `3793B1E31C578D04D7FAC95E6113BDB252D2862B78976D1394825278906240F7` |
| 3 | `trpg/agent/allowlist.yml` | `47899A5D874E1B3A6242F3B51EE4563744A36BB623770DDE67E6F97C3D60F5A2` |
| 4 | `docs/contracts/mcp-contract.md` | `3C4B33AF04748F05B6FAF20A9F54A1D52E56BD7B75A4ADADC13C7725FC0EE777` |
| 5 | `docs/contracts/runtime-contract.md` | `4BB45B2218B9E319B499D706FC36F55DE2291DBF29B8084FDB812B5EE2F45F72` |
| 6 | `docs/contracts/security-sync.md` | `C296D229662DB764ACA666FC080C1920BFA1E7B1D1B6C6242931351FED581C3B` |

一键校验（远程，逐项比对）：

```powershell
node packaging/remote.mjs run "cd 'C:\Users\Administrator\Desktop\黑客松开发文档\trpg'; Get-FileHash trpg\agent\events.py,app\web\ws_protocol.py,trpg\agent\allowlist.yml,docs\contracts\mcp-contract.md,docs\contracts\runtime-contract.md,docs\contracts\security-sync.md -Algorithm SHA256 | Select-Object Path,Hash | Format-List"
```

【待回填：改造后**当前 sha256** 与上表逐项对照结果 + AC-7 第 28 条结论（T2/T6 产出，见 `evidence/T2-server.txt`、`evidence/T6-acceptance.md`）】

## 7. 回归测试

```powershell
node packaging/remote.mjs run "cd 'C:\Users\Administrator\Desktop\黑客松开发文档\trpg'; python -m pytest tests/ -q"
```

**回归基线（verifier 采集，权威）**：改造前 **541 passed / 0 failed**。
改造后必须 **≥ 541 且 0 failed**，否则视为回归（AC-1 第 5 条、AC-7 第 30 条）。

【待回填：改造后实测用例数（须 ≥541）与全绿结论 + 证据路径】

## 8. 排障决策树

```
服务不可用
├─ 9210 是否 LISTENING？ ── 否 ──> 看 var\server.err.log；按 DEPLOY.md §4 重启
│                           └─ 是 ──> /api/health 是否 200？
│                                      ├─ 否 ──> 进程假活：stop.bat 后重启
│                                      └─ 是 ──> 继续
├─ /app/ 是否 200？ ── 否 ──> web/dist/ 是否完整（CHECKSUMS.txt 校验）
├─ /player/ 是否 200？ ── 否 ──> 404 player_not_built => player-web/ 缺文件
├─ 局域网设备能否访问？ ── 否 ──> 防火墙 trpg-9210 规则 / 是否同网段
├─ 接口 401/403？ ── 是 ──> token 端别错（玩家端 mobile / 主持端 webapp）
└─ WS 是否频繁断？ ── 是 ──> 网络抖动或代理超时；客户端自动退避重连并带 last_seq 补齐
```

## 9. 升级流程（发布新版本）

1. 远程备份（第 4.1 节）。
2. 记录当前冻结契约 sha256（第 6 节）。
3. 同步新文件到远程 `trpg/`。
4. 重启服务（第 2.2 节）。
5. 跑第 3 / 6 / 7 节校验，全部通过才算升级成功。
6. 若任一校验失败 → 按第 5 节回滚到第 1 步的快照。

## 10. 变更记录

| 日期 | 变更 | 操作人 | 结果 |
|---|---|---|---|
| 【待回填】 | 【待回填】 | 【待回填】 | 【待回填】 |
