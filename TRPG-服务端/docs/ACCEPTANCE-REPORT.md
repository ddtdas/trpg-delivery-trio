# ACCEPTANCE-REPORT.md —— 交付验收报告（AC-1…AC-7）

> 状态：**已定稿**（T7 完成，2026-09-25）。AC-1…AC-7 逐条结论均引用真实证据路径；未实测项已如实标注。
> 唯一验收基线：`docs/PLAN-ACCEPTANCE.md`（AC-1…AC-7，共 30 条可执行判据）。
> 所有结论均引用**真实证据文件路径**；**未实测 / 非绿项一律如实标注，不写成「全绿」**。
>
> ⚠️ **勘误注记（2026-09-27 追加；下列说明只做时点界定，不修改本报告任何结论文本）**
> 本报告是 **T7（2026-09-25）时点快照**，「证据」列中的**具体产物名 / 文件名属当时观测值**，其后包内容已演进。已查证：
> ① `tests/test_ws_security.py`（§1 AC-1#5 证据列引用）**现已不在交付包内** —— `tests/` 现为 7 个 `test_*.py` + `conftest.py` + 2 个辅助文件，可收集用例 **172** 个（与 §1 AC-1#5 / §7 AC-7#30 的 172 一致）。
> ② **本报告全文不含任何 `index-*.js` / `index-*.css` 产物哈希**（已全树检索确认）；`index-VVtlFbKo.js` / `index-dhOuF4Mq.js` / `index-DE5dm9qD.js` 这三个历史串分别出现在 `docs/BUILD-WEB.md`（已修正）与 `docs/DEPLOY.md`（已加勘误），**不在本报告内**。
> ③ **现行 GM 端产物基线**见 `docs/BUILD-WEB.md` §5.2（2026-09-27 现场复算）；**时点观测值**见 `docs/BUILD-LOG.md` §1 / §2b。
> 判据：本报告自述「已定稿（T7 完成，2026-09-25）」，且 §0 已声明「哈希 / 大小 / 条目数一律以包外 `.sha256` 为准」——故按**历史记录**处置，只加本注记。

---

## 0. 交付物清单

| # | 交付物 | 路径 | 状态 |
|---|---|---|---|
| 1 | 封装版服务端（主持端） | `server/packaged/` | ✅ 已纳入交付包 |
| 2 | PC / 移动浏览器玩家端 | `clients/web-player/` | ✅ 已纳入交付包 |
| 3 | 微信小程序玩家端 | `clients/miniprogram/` | ✅ 已纳入交付包 |
| 4 | 交付包 | `TRPG-交付包-v1.zip`（sha256 见同名 `.sha256`） | ✅ 已构建 —— **sha256 / 大小 / 条目数一律以包外 `.sha256` 与 `BUILD-INFO.json` 为准**（本报告随包分发，无法自引用所在包的哈希） |
| 5 | 文档 | `docs/`（DEPLOY / PLAYER-WEB / MINIPROGRAM / OPERATIONS / CROSS-END-CONTRACT / ROADMAP-DEFERRED / 本报告） | ✅ 已纳入交付包 |

## 1. AC-1 服务端（主持端）正常运行

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| 1 | `GET /api/health` → 200 且 `status=ok`（远程 9210 实测） | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 2 | `GET /app/` → 200；`GET /player/` → 200 且返回玩家端页面（含设计令牌） | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 3 | `netstat` 显示 9210 LISTENING 于 `0.0.0.0`；防火墙入站 Allow 规则存在 | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 4 | 局域网第二台设备访问 `http://192.168.10.110:9210/api/health` → 200 | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 5 | `python -m pytest tests/ -q` ≥ 基线 166 passed（verifier 采集） | ✅ **PASS** | **172 passed / 0 failed**（基线 166，+64）。曾有的 1 个 flaky `test_heartbeat_loop_calls_ping_all_periodically` **已修复为事件驱动、确定性断言**（本地 10/10、加负载 5/5、远程 5/5；verifier 独立复跑 8/8），`tests/test_ws_security.py` = `05CF0CCBC0D49127…`（12:37:57）。见 `evidence/T6-acceptance.md §1.5.1` |
| 6 | 新增端点鉴权矩阵：`/access/player/audio` 无 token→401 / webapp→403 / mobile→200；`/access/host/*` 无 token→401 / mobile→403 / webapp→200；`/access/table/resolve` 无 token→401 | ✅ **PASS** | `evidence/T6-acceptance.md` |

## 2. AC-2 玩家端可连接（合并后无中转层）

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| 7 | PC 玩家端浏览器打开 `/player/`，填地址 + 连接码 + 玩家 ID → 「测试连接」成功（显示服务版本 + 三端启用状态） | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 8 | 小程序导入 `clients/miniprogram`，同一套输入 → 「测试连接」成功 | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 9 | 两端加入同一桌后 `turn.state=COLLECTING` 一致 | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 10 | **无 9321**：交付物中不存在运行中的中转服务；两端请求直指 9210（证据：抓取请求 URL） | ✅ **PASS** | `evidence/T6-acceptance.md` |

## 3. AC-3 跨端游戏（真实对局）

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| 11 | `/access/host/table` + `/access/host/turn` 后，两端各提交一次行动 → 事件流出现 2 条 `ACTION_SUBMITTED` | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 12 | 幂等：同一 `req_id` 重复提交 → 只落 1 条事件，两端均显示「重复提交已忽略」 | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 13 | WS 广播：一帧 `NARRATION_APPROVED` 后两端 5s 内都显示同一条旁白 | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 14 | 断线重连：断开 10s 恢复后两端自动重连并补齐 `last_seq` 之后事件（无重复、无丢失） | ✅ **PASS** | `evidence/T6-acceptance.md` |
| 15 | 非 COLLECTING 提交 → 两端给出同样拒绝文案（同字符串） | ✅ **PASS** | `evidence/T6-acceptance.md` |

## 4. AC-4 远程可达（局域网 + 公网）

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| 16 | 局域网：`http://192.168.10.110:9210/player/` 在另一台机器可用 | ✅ **PASS** | 局域网 `http://192.168.10.110:9210/player/` 实测 **200**（本机第二设备）；防火墙来源已收紧 |
| 17 | 公网：实测至少一种穿透/反代（cloudflared 或 frp）；若环境受限则给可直接执行脚本 + 配置模板 + 手册并标注「环境受限，脚本已备」 | ✅ **PASS** | cloudflared quick tunnel 实测（`/api/health` 200、`/player/` 200）；地址以日志动态解析为准；frp 方案见 `DEPLOY.md` §6.3.4 |
| 18 | 小程序合法域名：给出「不校验合法域名（开发）+ HTTPS 域名（生产）」两种模式配置说明与截图/步骤 | ✅ **PASS** | `DEPLOY.md` §7 + `MINIPROGRAM.md` §5 给出两种模式（开发不校验合法域名 / 生产 HTTPS+备案）配置说明 | `docs/DEPLOY.md` §7 |
| **18b-公网** | 公网暴露面安全：① 公网 `/player/` 与 `/api/health` 均 **200**；② `/docs`、`/redoc`、`/openapi.json`、`/api/tables` **不再匿名可达**（403/404） | ✅ **PASS** | 见下方「18b-公网 实测明细」；证据 `evidence/T7-tunnel-verify.txt` |
| **18b-局域网**（= `PLAN-ACCEPTANCE.md` **18c「局域网暴露面」**） | 局域网侧暴露面：敏感路径在局域网直连下是否匿名可达 | ⚠️ **已收紧来源 + 方案已备**（非完全 PASS，亦非 FAIL）：防火墙已从 Any 收紧；但放行网段内仍匿名 **200**，反代方案本轮不部署 | 见下方「18b-局域网 实测明细」；证据 `evidence/T7-tunnel-verify.txt` |

**18b-公网 实测明细（2026-09-25，integrator 独立复验）**

落地方式：队长裁决 (a) —— **cloudflared 配置文件式路径白名单**（`C:\trpg-tunnel\config.yml`，末条 `http_status:404` 兜底），
方案全文见 `DEPLOY.md` §6.3.5.2；Nginx/Caddy 保留为生产替代（§6.3.5.3 / §6.3.5.4）。

公网地址：`<当前地址>`（**不写死** —— quick tunnel 每次重连换域名，本轮已实测变更 3 次；取法见 `DEPLOY.md` §6.3.1）

| 判据 | 路径 | 实测 | 期望 | 结论 |
|---|---|---|---|---|
| 1 | `/player/` | **200** | 200 | ✅ |
| 2 | `/api/health` | **200** | 200 | ✅ |
| 3 | `/docs` | **404** | 非匿名可达 | ✅ |
| 4 | `/redoc` | **404** | 非匿名可达 | ✅ |
| 5 | `/openapi.json` | **404** | 非匿名可达 | ✅ |
| 6 | `/api/tables` | **404** | 非匿名可达 | ✅ |
| 额外 | `/mcp`、`/metrics/latency` | **404** | （额外收紧） | ✅ |
| 额外 | `/app/`（主持端控制台） | **404** | （config v2 移除，残留①已关闭） | ✅ |
| 回归 | `/api/campaigns/c_demo/events`（F7 主通道） | **200** | 必须可用 | ✅ 未被误封 |
| 回归 | `/access/info` 无 token / 带 token | 401 / 200 | 不变 | ✅ |
| 回归 | `/app/` | **404** | （config v2 已移除 /app，残留①关闭） | ✅ 已封 |
| 回归 | `/ws` WebSocket 握手 | **OPEN + 收到 PING 帧** | 必须可用 | ✅ |

> ⚠️ 判定注意：`/ws` **不可用普通 HTTP GET 判活**（FastAPI 的 WS 路由无 HTTP 处理器，GET 恒 404）；
> 必须用 WebSocket 客户端验证。复验前请先确认隧道是否在跑（见 `DEPLOY.md` §6.3.5.0 的适用性条款与核查命令）。

**18b-局域网 实测明细（2026-09-25）**（口径同 `PLAN-ACCEPTANCE.md` 第 18c 条）

隧道边缘白名单**只管公网**；局域网直连不经 cloudflared，**不受白名单约束**。

| 访问路径 | `/docs` | `/redoc` | `/openapi.json` | `/api/tables` |
|---|---|---|---|---|
| 公网（经隧道） | **404** | **404** | **404** | **404** |
| 局域网 `http://192.168.10.110:9210` | **200** | **200** | **200**（37KB） | **200** |

已落实的缓解：防火墙 `trpg-9210` 入站 RemoteAddress 由 **Any** 收紧为 `192.168.10.0/24` + `192.168.56.0/24`
（两条规则，实测生效；本机 192.168.10.160 仍在放行网段内，`/api/health` 200）。

> ⚠️ **未解决（如实记录）**：防火墙按**来源**过滤，不按**路径**过滤。
> **上述网段内**的设备访问这四个路径**实测仍为 200** —— 同网段的玩家/观众/其他设备依然可匿名读取。
> 即：局域网匿名面**只是缩小（不再是 Any），并未关闭**。
> 局域网 `/api/tables` 实测泄露全部 `table_id` / `campaign_id`（含调试遗留桌），
> 配合契约 **R1**（事件流无 viewer 过滤）可读任意战役事件流。

**结论**：18b-局域网判 **「已收紧来源 + 方案已备」**。
彻底解决需**反代**（`DEPLOY.md` §6.3.5.4，生产推荐、本轮不部署）或**应用层关闭文档路径**（需 T2 评估）。
登记于 `ROADMAP-DEFERRED.md` §2.1 残余风险 3。

## 5. AC-5 封装交付物

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| 19 | `server/` 含源码 + `start.bat` + `stop.bat` + `requirements.txt` + `configs/`；**干净目录**执行 `start.bat` 后 health 200 | ✅ **PASS** | T7 构建时实测：解压到干净临时目录 → `start.bat` exit=0 → `/api/health` `{"status":"ok","version":"0.1.0-t12"}` → `stop.bat` exit=0（7 步全绿） |
| 20 | `clients/web-player/` 可直接拷到 `server/player-web/` 生效；无 npm 依赖、无构建步骤 | ✅ **PASS** | 构建时自动归位：`clients/web-player` → 包内 `server/player-web` 共 6 文件；纯原生 HTML/CSS/JS，无 package.json / 无构建步骤 |
| 21 | `clients/miniprogram/` 微信开发者工具导入即跑（`project.config.json` 合法、无语法错误、无 9321 引用） | ✅ **PASS** | `clients/miniprogram/tests/contract.test.js` 全过；无 9321 引用（parity 组 (d) 覆盖）；详见 `evidence/T4-mp.txt` |
| 22 | `docs/` 齐备：`DEPLOY.md`、`PLAYER-WEB.md`、`MINIPROGRAM.md`、`CROSS-END-CONTRACT.md`、`ROADMAP-DEFERRED.md`、`ACCEPTANCE-REPORT.md`（+ `OPERATIONS.md`） | ✅ **PASS** | 包内 `docs/` 含 7 份（上述 6 份 + `OPERATIONS.md`） |
| 23 | 交付包 `TRPG-交付包-v1.zip` 内含三件 + 文档 + 校验清单（`CHECKSUMS.txt`） | ✅ **PASS** | 见下方「T7 构建产物」；哈希另见 `TRPG-交付包-v1.zip.sha256` |

## 6. AC-6 四端一致性

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| 24 | 设计令牌逐项相同（颜色 hex / 圆角 / 间距 / 字号 / 类名语义）→ 脚本比对 0 差异 | ✅ **PASS** | `packaging/parity-check.mjs`；`evidence/T5-parity.md`（**parity 233/233 PASS**，0 FAIL；契约 v1.30 / 520 行） |
| 25 | F1–F10 逐项两端均可用；F11/F12 两端均明确不提供 | ✅ **PASS** | `evidence/T5-parity.md`；F11/F12 记入 `ROADMAP-DEFERRED.md` |
| 26 | 页面文案（按钮/占位符/错误提示/状态行）逐条相同 → 0 差异 | ✅ **PASS** | `packaging/parity-check.mjs`（文案表逐字比对 0 差异）；`evidence/T5-parity.md` |
| 27 | 移动端与 PC 端功能数量与名称完全相同（parity 清单两端打勾一致） | ✅ **PASS** | `evidence/T5-parity.md`（含 #27c/#27e/#27f/#27g 细项） |

## 7. AC-7 不破坏既有

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| 28 | 冻结契约 **6 项**文件哈希与改造前一致（契约 §1.5 裁定为 6 项） | ✅ **PASS** | 6 项全等；基线值见 `OPERATIONS.md` §6，对照见 `evidence/AC-CHECKLIST.md` 附录 A1。⚠️ 该表第 2 项曾误抄为 **63 位**（已更正为 `…D7FAC95E…`），详见 `evidence/T7-tunnel-verify.txt` §4 |
| 29 | `/app`（主持端 UI）仍 200 且 bundle 引用不变 | ✅ **PASS**（局域网） | 局域网 `http://192.168.10.110:9210/app/` → **200**。⚠️ **公网 `/app/` 为 404 属有意为之**（加固 v2 移除 `^/app`，防 KP 控制台公开），**不得判为回归** —— 见 `DEPLOY.md` §6.3.5.2 |
| 30 | 既有 `/access` 11 端点行为不变（既有测试用例全绿） | ✅ **PASS** | 既有用例通过；`/access` 11 端点签名与行为不变。pytest **172 passed / 0 failed**（原 flaky 已修复为事件驱动、确定性） |

## 8. 汇总

| 分组 | 通过 / 总数 | 结论 |
|---|---|---|
| AC-1 服务端 | **6 / 6** | ✅ PASS（T6） |
| AC-2 玩家端可连接 | **4 / 4** | ✅ PASS（T6） |
| AC-3 跨端游戏 | **5 / 5** | ✅ PASS（T6） |
| AC-4 远程可达 | **3 / 4** | 16/17/18 ✅；**18b-公网 ✅ PASS**；**18c/18b-局域网 ⚠️ 残余风险**（已收紧来源，未关闭） |
| AC-5 封装交付物 | **5 / 5** | ✅ PASS（T7 本报告） |
| AC-6 四端一致性 | **4 / 4** | ✅ PASS（parity **233/233**，0 FAIL；契约 v1.30 / 520 行） |
| AC-7 不破坏既有 | **3 / 3** | ✅ PASS（pytest 172 passed / 0 failed，原 flaky 已修复） |
| **合计** | **31 / 32 PASS，1 项残余风险**（AC-4 18c 局域网暴露面） | **阻断级 FAIL = 0**（T6 结论） |

## 9. 未通过项与最小复现

> 每条 FAIL 必须给出最小复现命令与原始输出。全部通过时本节写「无」。

**无阻断级 FAIL**（T6 结论：阻断级 FAIL = 0）。以下为**非阻断**项，如实记录：

| # | 项 | 性质 | 说明 |
|---|---|---|---|
| 1 | **AC-4 18c 局域网暴露面** | ⚠️ **残余风险**（非 FAIL） | 隧道白名单只管公网；局域网直连 `/docs` `/redoc` `/openapi.json` `/api/tables` **实测仍 200**。已收紧防火墙来源（Any → `192.168.10.0/24` + `192.168.56.0/24`），但**按来源过滤不按路径过滤 ⇒ 网段内仍匿名可达**。彻底解决需反代（`DEPLOY.md` §6.3.5.4，本轮不部署） |
| 2 | ~~pytest 1 个既存 flaky~~ → **已修复** | ✅ **已消除** | `test_heartbeat_loop_calls_ping_all_periodically` 原为纯墙钟时序假设（10 次 7 过 3 挂）；**已改为事件驱动、确定性断言**（`deadline = loop.time() + 2.0`，`sleep(0.035)` 命中 0），本地 10/10、加负载 5/5、远程 5/5，全量 **172 passed / 0 failed** → AC-1#5 / AC-7#30 现为**确定性绿** |
| 3 | **残留②** `/api/campaigns/{c}/events` 公网匿名 200 | ⚠️ **设计保留**（R1 范畴） | 该端点是 F7 主通道，契约 §1.1 要求保持匿名可用。关键缓解：枚举入口 `/api/tables` 已封 404 ⇒ 匿名者拿不到 `campaign_id` |
| 4 | **KR-1 = R1 × R7 叠加** | ⚠️ 残余 | 已知 `campaign_id` 时可匿名读事件流；根治需服务端加可见性过滤（需契约变更）。详见 `evidence/T6-public-exposure.md` |

### 9.1 已知遗留项（队长裁决：**维持冻结、不落笔**，记入终验报告）

以下 3 条为 planner 提出的 **R1 文档候选改动**。队长于最终冻结令中裁决 **不落笔**，故此处**如实登记为已知遗留项**，供后续迭代参考：

| # | 遗留项 | 说明 |
|---|---|---|
| L1 | **REST 全量 payload 含 `TRANSCRIPT_APPENDED` / `ACTION_SUBMITTED`** | `GET /api/campaigns/{c}/events` 返回**全部**事件、不做 viewer 过滤（R1 本体）。当前缓解：客户端按 payload 的 `scope`/`targets` 做展示过滤；枚举入口 `/api/tables` 已封 404。 |
| L2 | **正确复用对象是 `visibility.py::filter_state_for`，而非 `viewer_may_see`** | 未来为 REST 加可见性过滤时，应复用 `filter_state_for`（state 级过滤），**不要**照搬 WS 路径的 `viewer_may_see`（后者只覆盖 3 类帧，见 R1b）。**两条须一起修**。 |
| L3 | **未来加鉴权需先定响应结构规格** | 若给 `/api/campaigns/{c}/events` 加鉴权/可见性过滤，属 **additive 变更**，须**先冻结响应结构规格**（字段增删、错误码、未授权时的返回形态），再改代码 —— 否则会打破两端已冻结的解析逻辑。 |

> 📌 关联登记：`docs/ROADMAP-DEFERRED.md` 的 **R1**（`:40`）与 **R1b**（`:41`，WS `STATE_DELTA` 房间级广播）已并列登记，并写明「**须一起修**」；
> 契约 `§3.4.2` 与 `§7.2 R1` 亦已双向交叉引用（v1.25）。**三处呼应，避免后人「只修一条就以为可见性已解决」。**

**最小复现（局域网暴露面）**：
```powershell
Invoke-WebRequest http://192.168.10.110:9210/openapi.json -UseBasicParsing | Select-Object StatusCode   # 期望 404，实测 200
```

## 10. 证据索引

| 证据文件 | 内容 |
|---|---|
| 证据文件 | 内容 | 关键结论 |
|---|---|---|
| `evidence/T1-contract.txt` | 契约冻结与端点复核 | 契约 v1.12；6 项冻结哈希 |
| `evidence/T2-server.txt` | 服务端改动、端点鉴权矩阵、pytest、备份与哈希 | 4 个新增端点 + `/player/` 托管 |
| `evidence/T3-web.txt` | 浏览器玩家端自测与截图 | F1–F10 可用 |
| `evidence/T4-mp.txt` | 小程序自测与契约单测 | 契约单测全过 |
| `evidence/T5-parity.md` | 四端一致性审查 | **parity 233/233 PASS**（0 FAIL；契约 v1.30 / 520 行） |
| `evidence/T6-acceptance.md` | **端到端验收总报告**（AC-1…AC-7 逐条 + 未实测项声明 + 两条残留） | **阻断级 FAIL = 0** |
| `evidence/T6-idempotency-before-after.md` | AC-3.12 幂等修复前后对照 | 同 `req_id` 两次 → 只 +1 条 |
| `evidence/T6-public-exposure.md` | 18b 公网/局域网 + **KR-1**（R1×R7 叠加） | 公网 PASS / 局域网未关闭 |
| `evidence/AC-CHECKLIST.md` | 30 条判据可执行清单（含 #27c/#27e/#27f/#27g） | 逐条 ⬜→✅ |
| `evidence/T7-tunnel-verify.txt` | T7 公网暴露实测（加固前后 / 边界 / 脚本告警 / 哈希更正） | 见 §6 / §7 |
| `TRPG-交付包-v1.zip.sha256` | 交付包哈希 | 见下方「T7 构建产物」 |

**T7 构建产物**：见本文件末尾「T7 构建产物」小节（sha256 / 条目数 / 干净目录验证结果）。

## 10.1 T7 构建产物（交付包实测）

构建命令：`node packaging/build-delivery.mjs --verify --json`（真实源，非合成）

> 🔑 **本报告的哈希规则（务必先读）**：本报告**随包分发**，因此**无法自引用所在包的 sha256**。
> 故本报告**不再写死**「当前包」的 sha256 / 大小 / 条目数 —— **一律以包外 `TRPG-交付包-v1.zip.sha256` 与 `BUILD-INFO.json` 为准**。
> 下方「构建历史」列出的是**各次构建的历史记录**（用于追溯演进），**不代表你手上这一包的哈希**。
> 若报告中的历史值与你的 sidecar 不一致，**以 sidecar 为准**。

| 项 | 值 |
|---|---|
| 交付包 | `TRPG-交付包-v1.zip` |
| 大小 | 见包外 `.sha256` 与 `BUILD-INFO.json`（**不在此写死**，见下方规则） |
| sha256 | 见包外 `TRPG-交付包-v1.zip.sha256`（**唯一权威**） |
| 条目数 | 见 `BUILD-INFO.json`（注：`tar -tf` 含目录条目、`ZipFile.Entries` 与构建器口径各不相同 —— **条目数不是包的身份，sha256 才是**） |
| 包内 server/ | **480 文件**（排除 **23** 项：`__pycache__` `*.pyc` `*.bak` `*.log` `*.pid` **+ 运行期数据** `data/audio_import/` `data/snapshots/` `*.db`） |
| 包内 clients/web-player/ | 6 文件 |
| 包内 clients/miniprogram/ | 29 文件（含 mp-eng 10:19 的 F7 口径修正） |
| 包内 docs/ | 7 文件（DEPLOY / PLAYER-WEB / MINIPROGRAM / OPERATIONS / CROSS-END-CONTRACT / ROADMAP-DEFERRED / ACCEPTANCE-REPORT） |
| 包内 server/player-web/ | 6 文件（构建时由 `clients/web-player/` 归位，权威源） |
| 打包工具 | compress-archive（中文条目名在资源管理器与 Expand-Archive 下均正常） |
| 回环自检 | ✅ OK，**0 missing / 0 extra**（解压后逐条比对条目名） |
| 构建耗时 | 252.2s |

**干净目录验证（AC-5 #19 判据，7/7 步全绿）**：

| # | 步骤 | 结果 |
|---|---|---|
| 1 | 解压到干净临时目录 | ✅ |
| 2 | `server/start.bat` 存在 | ✅ |
| 3 | 9210 端口空闲 | ✅ |
| 4 | `start.bat` 执行 | ✅ exit=0 |
| 5 | `GET /api/health` | ✅ `{"status":"ok","version":"0.1.0-t12"}` |
| 6 | `GET /player/` | ✅ **200**（len=5380） |
| 7 | `stop.bat` 执行 | ✅ exit=0（临时目录已自动清理） |

> 📌 **行数口径说明**：契约行数以 `Get-Content … | Measure` 计为 **520**；`BUILD-INFO.json.contractSnapshot.lines` 记为 **521**，
> 系构建脚本按 `split(换行)` 计数（**行尾换行符**多计 1）所致 —— **同一文件，非版本差异**。
>
> 📌 **哈希鸡生蛋说明**：本报告随包分发，因此**包内**的 ACCEPTANCE-REPORT 无法自引用包自身的 sha256；
> 权威哈希以包外同名 `TRPG-交付包-v1.zip.sha256` 与本节（仓库副本）为准。
> 原始构建日志：`evidence/T7-build.log`。
> 🔁 **本包为第 3 次构建**（前两次哈希均已作废）：

| 次 | 触发原因 | 结果 |
|---|---|---|
| #1 | 首次构建 | ✅ 通过；后因包内文本修正作废 |
| #2 | 按队长授权修正包内三处纯文本旧口径（`clients/miniprogram/README.md` 与 `pages/table/table.js` 的增量 limit、三份玩家端 README 的排序描述） | ✅ 通过；后因 mp-eng 10:19 再次改动客户端文件而作废 |
| #3 | ① 纳入 mp-eng 10:19 的客户端修正；② **修复阻断级缺陷**：`server/packaged/start.ps1` 缺 UTF-8 BOM 导致 **PS 5.1 解析失败、服务起不来** | ✅ 通过；后因本轮文档补充（BOM 排障小节）而作废 |
| #4 | 纳入文档补充（`DEPLOY.md` §8「构建产物 .ps1 必须带 UTF-8 BOM」、`ROADMAP-DEFERRED.md` L10） | ✅ 通过；后因 web-eng 10:42–10:53 再次改动玩家端、planner 升契约 v1.13 等 12 个文件而作废 |
| #5 | 纳入截至 10:53 的全部源变更（玩家端 app.js/index.html/strings.json/README.md、契约 v1.13、PARITY-CHECKLIST、ENDPOINT-SPEC-NEW 等） | ✅ 通过；后因契约升版至 v1.21 而作废 |
| #6 | 纳入契约 **v1.21 / 491 行** | ✅ 通过；后因队长修复 parity 组 (m) 的 `ext.st.recordUnsupported` 文案（PC 端 6 个文件）而作废 |
| #7 | 纳入队长对 **`ext.st.recordUnsupported`** 的统一修正（**当时 parity 231/231**，现已扩至 233） | ✅ 通过；后因 `clients/web-player/README.md`(11:55) 与契约/PLAN 更新而作废 |
| #8 | 纳入 11:55 的 `clients/web-player/README.md` 更新、契约 **v1.24**、PLAN-ACCEPTANCE | ✅ 通过；后因**数据审计**发现包内带运行期数据而作废 |
| #9 | **剔除运行期数据**（见下方「交付包数据审计」）+ 纳入 12:05 的 mp 客户端与契约 **v1.27** | ✅ 通过；后因 server-eng 的 **BOM 根因修复**（assemble.ps1 加 BOM 写入 + PS 5.1 自检）而作废 |
| #10 | 纳入 server-eng 的 **BOM 根因修复**（`assemble.ps1`/`start.ps1`）+ 新增 `data/.gitkeep` | ✅ 通过；后因 mp-eng 12:45:58 再改 `tests/contract.test.js` 而作废 |
| #11 | 纳入 mp-eng 11:20–12:45 的全部 `clients/miniprogram` 变更（含删除 `wsLine`） | ✅ 通过；后因 **T10（t21）落地**而作废 |
| #12 | 纳入 **T10（t21）** 服务端改动 + 交付说明新增「两条取用规则」 | ✅ 通过；后因队长授权修正 parity 数字而作废 |
| #13 | 按队长授权**修正 parity 数字**（227/231 → **233/233**，附测量时刻与契约版本）+ 修复 `BUILD-INFO.json` 的 `counts.docs.bytes` 计数 bug | ✅ 通过 |
| #14 | 纳入 15:24 前的文档修订（含做法 (b) 废弃、同 seq「REST 胜出」、ROADMAP 新增 **R1b**、DEPLOY 补「WS 发布路径已生效」） | ✅ 通过 |
| **#15（定稿）** | 队长最终冻结令后：纳入 **契约 v1.30（`DB07744B…`）**、planner 3 行指纹更新、**包内 docs 扩至 9 份**（+PLAN-ACCEPTANCE、+ENDPOINT-SPEC-NEW）、报告新增 §9.1 已知遗留项 | ✅ **通过** |

> ⚠️ **构建历史 ≠ 本包哈希**：本包由**最后一次构建**产出；其 sha256 **只在包外 `.sha256` sidecar** 中。

##### 🏁 第 13 次构建终检（**历史记录**；已被第 15 次定稿取代）

> 下表数值为**第 13 次构建**当时的实测值，**不是本包的哈希**。本包哈希见包外 `.sha256`。

| 检查项 | 实测结果 |
|---|---|
| [取件时点] | 2026-09-25 14:28:13 ｜ zip mtime **14:21:23** |
| size / entries | **7,142,951 B** / **526** |
| sha256（包外 sidecar） | `6fb04d1a2f0503e3f9869f183d061f9ef3f2723e0f765d9604f11fdb77b18678` ｜ **match=True** |
| 包内契约 | 首行 `v1.30 · 冻结`（**520 行**），与 `BUILD-INFO.json.contractSnapshot` 一致 |
| 包内 3 份 `.ps1`（**PS 5.1.19041.5247**） | `assemble.ps1` 6474B / `start.ps1` 5567B / `stop.ps1` 1408B —— **BOM=True，errors=0（3/3）** |
| 包内 parity 数字 | **233/233**（本次修正项；保留 `:339` 演进链与 `:340` 历史时点说明） |
| `BUILD-INFO.json` `counts.docs` | `{files:7, bytes:207477}`（本次修复；原为 `bytes:0`） |
| 数据审计 | `.wav`=0 ｜ `.db/.sqlite`=0 ｜ `snapshots`=0 ｜ `.bak`=0 ｜ `.log/.pid`=0 |
| 一致性（包内 vs 工作树） | `clients/miniprogram` **29/29** ｜ `clients/web-player`→`server/player-web` **6/6** |
| 回环自检 | **0 missing / 0 extra**（526 条目） |
| 干净目录验证 | **7/7 全绿**（解压 → start.bat exit=0 → `/api/health` ok/0.1.0-t12 → `/player/` 200 → stop.bat exit=0） |
| **比包新的可交付文件** | **✅ 无** |

##### 🏁 第 12 次构建的终检（历史记录；已被后续构建取代）

| 检查项 | 实测结果 |
|---|---|
| [取件时点] | 2026-09-25 13:44:48 ｜ zip mtime **13:40:13** |
| size / entries | **7,142,083 B** / **526** |
| sha256（包外 sidecar） | `a53b36363b6dca3a3eff621633b731fe31572c2060d1f1f722b15a726ac2b747` ｜ **match=True** |
| 包内契约首行 | `# 跨端契约与设计令牌（CROSS-END-CONTRACT v1.30 · 冻结）`（520 行，见 `BUILD-INFO.json.contractSnapshot`） |
| 交付说明「两条取用规则」 | ✅ **已生效**（哈希以包外 sidecar 为准 + 构建时快照 + 自动记录快照版本与构建时间） |
| 包内 3 份 `.ps1` | `assemble.ps1` 6474B / `start.ps1` 5567B / `stop.ps1` 1408B —— **BOM=True，PS 5.1 errors=0**（3/3） |
| 数据审计 | `.wav`=0 ｜ `.db/.sqlite`=0 ｜ `snapshots`=0 ｜ `.bak`=0 ｜ `.log/.pid`=0 ｜ `data/` = 仅 `.gitkeep` |
| 一致性（包内 vs 工作树） | `clients/miniprogram` **29 文件 0 不一致** ｜ `clients/web-player` → `server/player-web` **6 文件 0 不一致** |
| 保留项 | `player-web` 6 ｜ `docs` 7 ｜ `configs/access_config.yaml` 存在 |
| 干净目录验证 | **7/7 全绿**（解压 → start.bat exit=0 → `/api/health` ok/0.1.0-t12 → `/player/` 200 → stop.bat exit=0） |
| 回环自检 | **0 missing / 0 extra**（526 条目） |
| **比包新的文件** | **✅ 无** —— 工作区与交付包**已同步** |

##### 📌 第 11 次构建的一致性复核（包内 vs 工作树，逐文件）

| 源 | 包内目标 | 比对文件数 | 不一致 |
|---|---|---|---|
| `clients/miniprogram` | `clients/miniprogram` | 29 | **0** ✅ |
| `clients/web-player` | `server/player-web` | 6 | **0** ✅ |

> **注意**：`docs/` 下 12 个文件中有 5 个（`CAPTAIN-NOTES.md` `ENDPOINT-SPEC-NEW.md` `PARITY-CHECKLIST.md` `PLAN-ACCEPTANCE.md` `TASK-BRIEFS.md`）
> **不在交付包内** —— 交付包按 AC-5 #22 只收录 7 份（DEPLOY / PLAYER-WEB / MINIPROGRAM / OPERATIONS / CROSS-END-CONTRACT / ROADMAP-DEFERRED / ACCEPTANCE-REPORT）。
> 若验收方也需要 `PLAN-ACCEPTANCE.md` 与 `ENDPOINT-SPEC-NEW.md`，请队长明示，我加入 `REQUIRED_DOCS` 后重建。

##### ✅ 第 10 次构建的终检（解压后实测）

| 检查项 | 结果 |
|---|---|
| 包外 `.sha256` sidecar 与实际哈希 | **match=True** |
| 运行期数据 `.wav` / `.db` / `snapshots` / `.log`/`.pid` | **0 / 0 / 0 / 0** |
| 包内 `server/data/` | 仅 `.gitkeep`（0 B，用于保留空目录） |
| 包内三份 `.ps1` 在 **PS 5.1** 下解析 | `assemble.ps1` / `start.ps1` / `stop.ps1` 均 **errors=0** |
| 保留项 | `player-web` **6 文件** ｜ `docs` **7 文件** ｜ `configs/access_config.yaml` 存在 |
| 包内契约快照 | **v1.27 / 514 行**（自动记录于 `BUILD-INFO.json.contractSnapshot` 与 `使用说明.txt`） |
| 干净目录验证 | **7/7 全绿**（start.bat exit=0 → health ok → /player/ 200 → stop.bat exit=0） |

##### 🔍 交付包数据审计（队长要求核对 server/data/）

**发现问题（第 8 次构建时包内仍有）**：

| 项 | 内容 | 判定 |
|---|---|---|
| `server/data/trpg.db` | **90,112 B** 真实运行期数据库（含测试期战役/事件） | ❌ **不该交付** |
| `server/data/audio_import/` | **80 个测试录音 `.wav`**（含 `acc4-test.wav`、`clip.wav` 等测试上传） | ❌ **不该交付** |
| `server/data/snapshots/c_acc6/snapshot_000017.json` | 运行期快照 | ❌ **不该交付** |
| `server/var/*.log` | 运行日志 | ✅ 已被既有 `*.log` 规则排除（包内 var/ 为空） |

**处置**：在 `packaging/build-delivery.mjs` 增加**路径级排除** `EXCLUDE_PATH_RE`（`data/audio_import` / `data/snapshots` / `data/audio` 整棵子树）
与 `EXCLUDE_DATA_FILE_RE`（`*.db` / `*.sqlite` / `*.db-wal` 等），并**保留 `data/` 目录本身**（空目录，服务端需要它存在才能写）。
构建日志：`拷贝 server: 479 文件 … 排除 23`（原 561 文件 / 排除 20）。

**第 9 次构建后复验（解压后扫描）**：`.wav` = **0**、`.db/.sqlite` = **0**、`snapshots` 目录 = **0**、`.log/.pid` = **0**；
`server/data/` 保留为空目录 ✅；`configs/access_config.yaml` 保留 ✅（交付必需）。

**凭据扫描**：三端 token 字面量**仅出现在 `server/configs/access_config.yaml`**（交付必需），
**未泄漏到任何其它文件**（全包扫描 mobile/webapp/recorder 三个 token 字面量，各自仅命中该配置文件 1 次）。
> ⚠️ 该配置为**明文**，公开分发前请更换 token —— 已在 `DEPLOY.md` §5 与交付说明中提示。

**包内契约快照（构建时自动记录，见 `BUILD-INFO.json` 的 `contractSnapshot` 与包内 `使用说明.txt`）**：
`
{"present":true,"version":"v1.24","lines":501,"firstLine":"# 跨端契约与设计令牌（CROSS-END-CONTRACT v1.24 · 冻结）"}
`
> ⚠️ **本包内的 `docs/` 与 `clients/` 是【构建时快照】**。契约由 planner 在本轮持续升版（v1.13 → v1.24）。
> 自第 7 次构建起，该快照版本由构建脚本**自动写入** `BUILD-INFO.json` 与包内 `使用说明.txt`，不再依赖人手誊写。
> 若验收时契约已再次升版，请以**最新冻结版**为准，并核对其与包内快照的差异是否为澄清性补充。

> ⚠️ **本包是「构建时快照」**：契约由 planner 在打包期间持续升版（本轮观察到 **v1.13 → v1.30**，520 行）。**第 13 次构建已纳入冻结版 v1.30**，且包内契约与工作区逐字节相同。
> 因此**包内 docs/ 反映的是构建时刻的版本**；若交付前契约仍在变动，需要**再跑一次构建**（或先冻结文档）。
> 包内 ACCEPTANCE-REPORT 自身也必然比 zip 略新（哈希鸡生蛋），权威哈希以包外 `.sha256` 为准。

##### ⚠️ 本轮发现并修复的阻断级缺陷：封装件 .ps1 缺 BOM

**症状**：干净目录验证失败（`BUILD_EXIT=1`）—— `server/start.ps1` 解析报错、服务起不来。

**根因**：`server/packaged/start.ps1`（mtime 10:14:48，即上次成功构建之后被重新组装）**缺少 UTF-8 BOM**，但内容含中文。
Windows PowerShell **5.1** 读无 BOM 的 `.ps1` 会按 **ANSI/GBK** 解析 → 中文字符串被破坏 → 语法错误。

**实测对照（同一文件、两个解析器）**：

| 解析器 | start.ps1 | 说明 |
|---|---|---|
| Windows PowerShell **5.1** | **errors=5**（首条 `An expression was expected after '('`） | **目标环境的真实行为** |
| PowerShell **7.x** | errors=0 | ⚠️ **本机 pwsh 自检会漏掉这个坑** |

**旁证**：`server/packaged/start.bat` 第 2 行注释即写着「Real logic: start.ps1 (**UTF-8 with BOM**)」—— BOM 是设计意图，本次组装漏写。

**处置**：给 `start.ps1` 与 `assemble.ps1` **补上 UTF-8 BOM**（纯编码声明，**零逻辑改动**，字节 5564→5567 / 2538→2541）；
复验三份 `.ps1` 在 **PS 5.1 下 errors=0**。已同步 **server-eng 修根因**（`assemble.ps1` 生成时未写 BOM，需显式用 `UTF8Encoding($true)`，
并在组装末尾**用 PS 5.1 解析器自检**而非 pwsh 7）。

> 📌 **交付检查项（建议写入后续流程）**：**构建产物中凡含中文的 `.ps1` 必须带 UTF-8 BOM**，
> 且自检必须用 `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`（5.1），**不可用 pwsh 7**。

## 11. 结论

**整体结论：✅ 可交付（有条件）**

- **阻断级 FAIL = 0**；32 条判据中 **31 条 PASS**，1 条（AC-4 18c 局域网暴露面）为**已登记残余风险**。
- 三件交付物齐备且经干净目录验证：封装版服务端、PC/移动浏览器玩家端、微信小程序玩家端。
- 四端一致性：**parity 233/233 PASS**，**0 FAIL**（契约 v1.30 / 520 行；`evidence/T5-parity.md` 最终复跑 `RESULT: PASS — 0 差异`）。
  断言数演进：**219 → 227 → 231 → 233**（227 = 组 (k)2 + (l)3；231 = 再增组 (m) `ext.*` 4 项；**233 = 再增组 (n) WS 静默降级 2 项**）。
  > 📌 历史时点值：本报告早期版本曾写 **227/227**、其后为 231/231（均在当时正确）；**现值为 `parity 233/233 PASS`（0 差异；契约 v1.30 / 520 行）**。若你手上是旧版报告，一律以 **233/233** 为准；权威依据是 `packaging/parity-check.mjs` 的重跑输出（现已随包分发）。
- 冻结契约 6 项哈希全等；`/app`（局域网）仍 200。

**交付条件（使用方须知）**：
1. **公网地址每次隧道重连都会变** —— 以日志动态解析为准，交付文档不写死域名（见 `DEPLOY.md` §6.3.1）。
2. **`/app/` 公网返回 404 是有意为之**（加固 v2 移除），KP 主持端请走局域网，**不是故障**。
3. **局域网侧敏感路径仍匿名可达**（`/docs` `/openapi.json` `/api/tables`）—— 生产部署前须上反代收口。
4. **演示结束请停隧道**（Stop-ScheduledTask -TaskName trpg-tunnel-cf）；注意**停隧道不关闭局域网暴露**。
5. F11/F12 本轮两端一致不实现；其余已知限制见 `ROADMAP-DEFERRED.md`。

**已知限制**：`ROADMAP-DEFERRED.md` §2.1 残余风险登记（R1 / R7 残留 ×2）、§3 限制 L1–L9。
