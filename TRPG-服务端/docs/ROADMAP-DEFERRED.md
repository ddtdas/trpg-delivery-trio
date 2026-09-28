# ROADMAP-DEFERRED.md —— 本轮未做项与已知限制

> 状态：**骨架**（T7 阶段定稿）。
> 原则：**一致性优先于功能数量** —— 本轮未做的功能，PC 浏览器端与微信小程序端**一致地不做**，
> 不允许出现「一端有、另一端无」。任何新增功能须先改 `CROSS-END-CONTRACT.md` 再两端同步实现。

---

## 1. 明确延期功能

### F11 骰点托盘（玩家主动掷骰）

| 项 | 内容 |
|---|---|
| 状态 | **两端均不提供**（一致） |
| 延期原因 | 服务端 `/ws` 的 `COMMAND` 帧目前**仅 ACK、无副作用**；要支持玩家掷骰需新增一条**玩家侧写路径**，属于冻结契约（`ws_protocol.py` / `events.py`）的行为变更，本轮范围外。 |
| 影响 | 玩家端只能提交自由文本行动（F6），无法在客户端发起掷骰判定。 |
| 未来方案 | 在服务端新增 additive 端点（如 `POST /access/player/roll`），复用既有事件类型落库 + WS 广播；两端同步实现 UI 托盘与结果展示。需先改契约并重新冻结。 |
| 验收影响 | AC-6 第 25 条要求 F11 两端**一致地不提供** —— 当前状态满足。 |

### F12 玩家私语（玩家主动发私语）

| 项 | 内容 |
|---|---|
| 状态 | **两端均不提供**（一致） |
| 延期原因 | 与 F11 同源：服务端无**玩家侧**私语发起点。现有 `WHISPER` 帧是**下行**（仅推送给 targets），只能由 KP 侧产生。 |
| 影响 | 玩家之间/玩家与 KP 之间无法通过客户端发私语；仅能接收 KP 发起的私语。 |
| 未来方案 | 新增 `POST /access/player/whisper`（mobile token）→ 落库 + 定向 `WHISPER` 广播；两端同步实现输入框与目标选择。 |
| 验收影响 | 同上，AC-6 第 25 条要求两端一致不提供。 |

> 两端产物中**不得出现**「掷骰」「私语」作为可交互功能；parity 检查（`packaging/parity-check.mjs`）会断言两端均无相关关键字。

## 2. 契约 v1.4 已登记风险（R1–R7，**必读**）

> 来源：`CROSS-END-CONTRACT.md` §7.2。这些是**如实记录、不隐瞒**的已知风险，
> 两端实现必须按「本轮处置」列执行。

| # | 风险 | 影响 | 本轮处置 |
|---|---|---|---|
| **R1** | **事件流端点无可见性过滤**：`GET /api/campaigns/{c}/events` 返回**全部**事件，不做 viewer 过滤（WS 路径有 `viewer_may_see`，REST 路径没有）。 | 私密 payload 会被所有玩家拉取到 | 客户端**必须**按 payload 的 `scope` 与 `targets` 做展示过滤（`scope=public`、或 `targets` 含本人、或 `condition_met` 才显示）。建议 T2 追加 viewer 参数做服务端过滤（additive），本轮不阻塞。 |
| **R1b** | **WS `STATE_DELTA` 实为房间级广播**（契约 §3.4.2 v1.20）：Hub 的 `viewer_may_see` 只过滤 WHISPER / NARRATION_PENDING / JOB_STATUS，冻结件写的 scope=viewer「可见子集」与实现不符。 | 与 R1 **同类且叠加**：非 public 事件详情有两条外泄路径 | **须与 R1 一起修 —— 只修一条仍会外泄**。本轮处置：发布路径**不得**在 STATE_DELTA 携带非 public 详情（回退帧一律 `{type, redacted:true}`，SPEC §8 定稿）；契约 §7.2 R1 与 §3.4.2 已做双向交叉引用。 |
| **R2** | **turn.state 取值集合不一致**：projector 写 COLLECTING / CLOSED / RESOLVING，而 `ws_protocol.TurnState` 声明 COLLECTING / CLOSING / RESOLVING / DISTRIBUTED / ADVANCED（CLOSED 不在其中）。 | 客户端按字面枚举严格匹配会漏状态 | 客户端**只把 COLLECTING 当作可提交**，其余状态**原样显示字符串**，**不得**因未知状态崩溃或隐藏状态行。 |
| **R3** | TABLES 注册表是**进程内内存态**（`app/web/rest.py` 注释明示），重启即丢。 | 重启后连接码解析失败 | 属既有行为，本轮不改；**验收时重启后需重新开桌**（T6 注意）。 |
| **R4** | `/access/info` 的 `ws` 字段值 `/access/ws` 是**误导性**的（契约 §1.4）。 | 客户端连错地址，握手必失败 | 契约已明确**禁用**该字段作连接地址；WS 路径恒为 `/ws`。 |
| **R5** | ~~WS 无下行发布方（契约 §3.4）~~ → **✅ 已解决**：T2 按队长裁决落地的 **additive 发布路径已实测生效**（verifier 真实握手收到 **5 帧 `TURN_UPDATED`，seq 382–387**）。<br>历史：T1 测量时点生产路径从不调用 `Hub.publish`，房间日志恒空。 | 原为 F7 实时性缺失；**现已具备实时广播能力** | F7 **主通道仍为 REST 轮询**（首次 `limit=1000` / 增量 `limit=50` + 排空续拉），**WS 仍为可选增强**（连不上即静默降级，不得成为依赖）。见契约 §3.4.2 / §7.2 R5。 |
| **R6** | **F-2：`/access/mobile/action` 的 req_id 幂等失效**。根因：`CommandBus.__init__` 的 `self.guard = guard or BranchGuard()`，而 `mobile_action` **每请求新建 CommandBus 且不传共享 guard** → 判重键存在**请求级实例**里，请求结束即丢，跨请求永不判重。实测（修复前基线）：同 req_id 提交两次 → 落 **2 条** `ACTION_SUBMITTED`，两次均 `status:"ok"`。 | **AC-3.12 必 FAIL**；两端会各自多落一条行动事件 | 已下发 server-eng 修复（共享/持久化 BranchGuard）。**验收规则：修复后须实测「同 req_id 两次提交 → 只 +1 条 `ACTION_SUBMITTED`，且第二次响应 `status=duplicate`」**。客户端行为不变（仍显示 `重复提交已忽略`）。 |
| **R7** | **公网暴露面**：实测 `/openapi.json`、`/docs`、`/redoc`、`/api/tables` 可**公网匿名**访问。 | 信息泄露与枚举风险（API schema、表清单暴露） | **公网暴露期必须落实加固**：命名隧道 + Cloudflare Access，或 Nginx/Caddy + Basic Auth + 路径限制（屏蔽 `/docs`、`/redoc`、`/openapi.json`、`/api/tables`、`/mcp`）。判据见 **AC-4 第 18b 条**；**方案已由 integrator 写入 `DEPLOY.md` §6.3.5**（采用**路径白名单**：放行 `/api/health`、`/player/*`、`/access/*`、`/ws`、`/api/campaigns/*/events`，其余一律 404；Basic Auth 只加在 `/app/`）。⚠️ 禁用「整个 `/api/` 全封」—— 会连带封掉 F7 主通道。加固**不影响两端功能**（玩家端只用契约 §1.1 的 8 个端点，全部在白名单内）。**当前状态：方案已备、尚未在远程落实 → AC-4 18b 暂为 FAIL**。 |

### 2.1 本轮残余风险登记（R1 / R1b / R7 残留 · 队长裁决 2026-09-25）

> 队长已裁决：公网侧白名单 PASS（隧道继续开）；局域网侧已收紧防火墙来源；
> 反代作为**生产推荐**写入 `DEPLOY.md`，**本轮不部署**（交付物不含反代组件）。
> 因此下列风险**本轮不修**，登记备查。

#### 残余风险 1：R1 —— 事件流无可见性过滤

| 项 | 内容 |
|---|---|
| 事实 | `GET /api/campaigns/{c}/events` 返回**全部**事件，不做 viewer 过滤（WS 路径有 `viewer_may_see`，REST 路径没有） |
| 本轮缓解 | 客户端按 `scope` / `targets` / `condition_met` 做**展示过滤**（契约 §3.4 / §4.1 F7 要求）—— 只防「误显示」，**不防抓取** |
| 未解决 | 服务端无过滤 ⇒ **任何能访问该端点的人都能读到全部事件内容**（含私语类 payload） |
| 触发前提 | 需先知道 `campaign_id` |
| 后续方案 | 给事件流加 `viewer` 参数做服务端可见性过滤（additive），或对匿名调用关闭该路径 —— 需**契约变更** |
| 验收影响 | AC-3 相关判据按「客户端过滤」验收；服务端过滤不在本轮范围 |

#### 残余风险 2：R7 残留 —— 已知 campaign_id 时公网可匿名读事件流

| 项 | 内容 |
|---|---|
| 事实 | `/api/campaigns/{c}/events` 按契约 §1.1 **必须保持匿名可用**（它是 F7 主通道，白名单已精确放行） |
| 本轮缓解 | 白名单把 `/api/tables`（campaign 枚举来源）封为 **404**，**切断了匿名枚举链** —— 这是最关键的缓解 |
| 未解决 | 若 `campaign_id` 通过**其他途径**泄露（日志、截图、演示口播、LAN 侧枚举），匿名者仍可直接拉事件流 |
| 后续方案 | 与残余风险 1 同解：服务端可见性过滤；或在反代层对匿名关闭该路径（但会破坏玩家端 F7，需先改契约） |

#### 残余风险 3：R7 残留 —— 局域网直连下敏感路径仍匿名可达

| 项 | 内容 |
|---|---|
| 事实 | 隧道边缘白名单**只管公网**。局域网直连 `http://192.168.10.110:9210` 不经 cloudflared，**不受白名单约束** |
| 实测（2026-09-25） | 局域网 `/docs` **200**、`/redoc` **200**、`/openapi.json` **200**（37KB）、`/api/tables` **200**（泄露全部 table_id / campaign_id，含调试遗留桌） |
| 本轮缓解 | ✅ 防火墙 `trpg-9210` 入站 RemoteAddress 由 Any 收紧为 `192.168.10.0/24` + `192.168.56.0/24` |
| **未解决（重要）** | 防火墙按**来源**过滤，不按**路径**过滤 —— **上述网段内**的设备访问这四个路径**实测仍为 200**。同网段的玩家/观众/其他设备依然可匿名读取。匿名面**只是缩小，没有关闭** |
| 后续方案 | 上反代（`DEPLOY.md` §6.3.5.4，生产推荐、本轮不部署）或在应用层关闭 `/docs` `/redoc` `/openapi.json`（FastAPI `docs_url=None` 等，需 T2 评估） |
| 验收影响 | 见 `ACCEPTANCE-REPORT.md` 的 **18b-公网（PASS）** 与 **18b-局域网（已收紧来源 + 方案已备）** 两行 |

> 📌 **一句话总结**：公网侧已按白名单收口并实测 PASS；局域网侧的匿名面**已缩小但未关闭**，
> 根因是「隧道白名单 + 防火墙来源限制」都不是路径级控制。彻底解决需要**反代或应用层改动**，本轮不做。

## 3. 其它已知限制（非契约风险，但需知晓）

| # | 限制 | 说明 | 缓解 |
|---|---|---|---|
| L1 | 小程序生产环境需 HTTPS + 已备案域名 | 微信平台强制；局域网 `http://` 仅开发模式可用 | 见 `DEPLOY.md` §6.3 / §7 |
| L2 | 公网访问依赖第三方穿透 | cloudflared 快速隧道地址每次重启变化；frp 需自有公网服务器 | 正式环境用自有域名 + 命名隧道 / frp + HTTPS 反代 |
| L3 | 浏览器端麦克风需安全上下文 | 非 `localhost` 的 `http://` 页面 `getUserMedia` 受限 | 用 `localhost` 或 HTTPS；否则按 F8 降级提示 |
| L4 | 主持端 `/app/` 本轮不改动 | `web/src` 缺构建配置且源码落后于已部署 bundle | 维持现状；玩家端独立为 `/player/`，互不影响 |
| L5 | 事件流仅保留最近 50 条 | 前端窗口限制，非服务端截断 | 需要完整历史时查服务端事件接口 |
| L6 | 玩家端 token 明文存本地 | localStorage / wx storage 均为明文 | 仅存 mobile 端 token；`recorder` token 绝不下发；生产建议换发短期凭据 |
| L7 | 交付包含明文凭据配置 | `configs/access_config.yaml` 随包分发 | 公开分发前更换三端 token；生产改环境变量注入 |
| L8 | 冻结契约不可改（**6 项**） | `events.py` / `ws_protocol.py` / `allowlist.yml` / `docs/contracts/` 下 3 个文档 | 任何变更需走契约流程并重新验收 |
| L9 | 公网演示期 quick tunnel 无鉴权 | 任何拿到 URL 者可访问；`/api/*` 无需 token | 演示结束立即停隧道；长期对外按 R7 加固 |
| L10 | **构建产物 .ps1 必须带 UTF-8 BOM** | PS 5.1 读无 BOM 的 `.ps1` 按 GBK 解析，含中文者会**语法报错、服务起不来**；而 **pwsh 7 自检发现不了** | 生成脚本时显式用 `UTF8Encoding($true)`；自检必须用 **PS 5.1** 解析器（见 `DEPLOY.md` §8） |
| L11 | **content_schema 声明本轮未引入** | 规则包 / 模组的「内容 schema」维度本轮**不做**：rulepacks/index.json 与 modules/index.json 的 entry 只有 schema_version，**没有 content_schema 字段**。二者语义不同（前者=载体格式版本，后者=内容结构版本），**不得混为一谈**；tests/test_repo_unit.py:161 有专门用例锁定此点 | 如后续引入，需 registry / schema 层一并扩展，并重跑索引门禁与三端一致性校验；本轮全部判据仅涉及 schema_version |

| L12 | **R9 暗骰判据的两条未规定边界** | `app/domain/visibility.is_dark_roll` 的两条规则（① 掷骰者属 `DARK_ROLL_ACTORS`；② `card_id` 为空或属 `DARK_ROLL_CARD_IDS`）都不命中时判为「可见」。于是 `(actor="", card_id="npc_butler")` 与 `(actor="npc_butler", card_id="npc_butler")` 两种组合下，该条 `CHECK_RESOLVED` **对非 KP 可见** —— `card_id` 泛指 NPC 归属（而不是玩家 id）时被当成「某位玩家」 | 登记为**未规定边界**（R9 判据本就未覆盖这两条组合），**不是缺陷**；代码内 `visibility.py` 同处已注明。若后续要求「NPC 归属的骰」也按暗骰处理，需扩充 `DARK_ROLL_CARD_IDS` 的归属规则，会同时影响 `is_dark_roll` 的两处调用（`clip_event` 裁剪 / `leaked_literals` 负例判据） |

【待回填：T5/T6 过程中发现的其它限制（如有），逐条补入本表】

## 4. 与验收标准的关系

- `PLAN-ACCEPTANCE.md` §2.4 功能范围表已把 F11/F12 标为 ⛔（两端一致不实现）。
- AC-6 第 25 条：F1–F10 两端均可用、F11/F12 两端均明确不提供。
- 本文件即 AC-5 第 22 条要求的 `docs/ROADMAP-DEFERRED.md`。

## 5. 变更流程（如后续要解禁某项）

1. 修订 `CROSS-END-CONTRACT.md`（令牌 / 功能清单 / 文案 / 端点规格）。
2. 服务端实现 additive 端点（不得改既有端点签名）。
3. PC 端与小程序端**同一轮**同步实现。
4. 重跑 `packaging/parity-check.mjs` 与 `PLAN-ACCEPTANCE.md` 全量验收。
5. 更新本文件与 `ACCEPTANCE-REPORT.md`。
