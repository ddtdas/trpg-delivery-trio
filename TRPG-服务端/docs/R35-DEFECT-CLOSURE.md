# R35 缺陷收敛与契约澄清（第三个遗留缺陷 + R33 复测）

> 生成时点：2026-09-27（远程 192.168.10.110，服务端 9211）
> 作者：R2 修复代理　　状态：三项均已定位并给出改法，证据见正文
> 本文件为 **additive**：不改任何冻结文件、不新增事件类型、不新增 WS 帧。

---

## 1. R35-2 —— 索引 sha256 与下载物 sha256 不是同一个量

### 1.1 结论（先判定，再动手）

**不是索引生成逻辑的产品缺陷，而是契约语义不清 + 缺少「产物级 sha256」的发布面。**

依据（可复算）：

| 证据 | 位置 | 内容 |
|---|---|---|
| 索引条目由目录摘要生成 | `app/repository/index.py` | `scan_entries()` 调 `sha256_dir(child)` 得 `digest/size/nfiles`，分别写入 `sha256/size/files` |
| `sha256_dir` 的定义 | `app/repository/index.py` | 对「每行 相对路径 + NUL + 该文件 sha256 + 换行」拼接串取 sha256；`size` = 目录内文件大小之和；`files` = 文件个数 |
| **队级不变量把该等式锁死** | `scripts/r2_verify_invariants.py` 判据 I2 | `entry.sha256 == sha256_dir(<dir>)` 且 `size` 逐值相等；改成产物摘要会让门禁 FAIL |
| 同一模块在不同语境已有两套命名 | `app/repository/importer.py` | 导入响应返回 `package_sha256`（包字节）与 `content_sha256`（= 索引条目 sha256，即目录摘要） |

因此索引里的 `sha256/size/files` **必须**继续是「解包后目录摘要」，不得改成可下载产物的摘要。

### 1.2 真正缺什么

`GET /api/modules/{id}/download` 返回的是**打包后的 `.modpkg`（zip 容器）**，
其字节 sha256 与目录摘要必然不同；而此前**没有任何接口或响应头发布产物自身的 sha256**，
所以「按模组 id 下载并校验 sha256」这条判据在契约层面无法完成。

### 1.3 契约澄清（本文即为准）

| 量 | 含义 | 获取处 |
|---|---|---|
| `content.sha256` | 模组**目录**摘要 `sha256_dir(modules/<id>)`，与索引条目 `sha256` 逐字相同 | `GET /api/modules` → `entries[].sha256`；`GET /api/modules/{id}/package` → `content.sha256` |
| `artifact.sha256` | `GET /api/modules/{id}/download` 响应**字节**（`.modpkg`）的 sha256 | `GET /api/modules/{id}/package` → `artifact.sha256`；下载响应头 `X-Artifact-Sha256` |

**校验下载物必须用 `artifact.sha256`，不要与索引条目的 `sha256` 相比。**

新增端点（additive，不改既有端点形状）：

`GET /api/modules/{module_id}/package` → 200

    {
      "ok": true,
      "module_id": "dead_light",
      "artifact": {"sha256": "<32B hex>", "size": 12930, "files": 16,
                   "filename": "dead_light.modpkg",
                   "path": "/api/modules/dead_light/download",
                   "meaning": "可下载产物 .modpkg 的字节 sha256 ..."},
      "content":  {"sha256": "<32B hex>", "size": 39439, "files": 16,
                   "index_ref": "GET /api/modules -> entries[].sha256",
                   "meaning": "解包后目录摘要 sha256_dir(modules/dead_light) ..."},
      "download_path": "/api/modules/dead_light/download",
      "verify": "sha256(GET /api/modules/dead_light/download 的响应字节) == artifact.sha256",
      "note": "..."
    }

`GET /api/modules/{module_id}/download` 响应头新增：

| 头 | 含义 |
|---|---|
| `X-Artifact-Sha256` | 本次响应字节（`.modpkg`）的 sha256 |
| `X-Artifact-Size` | 产物字节数 |
| `X-Content-Sha256` | 索引条目里的目录摘要（同一模组目录） |
| `X-Content-Size` | 目录内文件大小之和 |
| `X-Content-Files` | 目录内文件个数 |

打包走 `pack_module(..., deterministic=True)`（固定 `packed_at` 与 zip 条目 mtime），
故「同输入必得同字节」：`/package` 给出的 `artifact.sha256` 与随后 `/download` 的字节 sha256 恒等，
可由调用方独立复算（R26 确定性）。

---

## 2. R35-7 —— GM 一次性落位未产生地图

### 2.1 现象（实测原文）

新战役 + 2 名玩家（`CHARACTER_CREATED`）、地图 ops 尚未产生时：

    suggest -> HTTP 200 map_id='' count=2
      suggestions = [{"player_id":"pl_a","to_room":"","kind":"place", ...},
                     {"player_id":"pl_b","to_room":"","kind":"place", ...}]
    apply(body={}) -> HTTP 422 detail=no map for campaign

先做一个 `set_fog`（地图条目存在、token 房间为空）：

    suggest -> HTTP 200 map_id='map_library' count=2 （to_room 仍为空串）
    apply(body={})               -> HTTP 201 applied_count=0 applied=[]
    apply(带显式 suggestions)     -> HTTP 201 applied_count=0 applied=[]
    overview.blocks.map(apply 后) -> tokens={}   ← 地图未产生

### 2.2 根因（代码位置）

| # | 缺陷 | 位置 |
|---|---|---|
| 1 | 建议的房间只能从**已落位棋子**反推：`rooms = sorted(set(token_rooms.values()))`；开局前 token 房间为空 ⇒ `to_room = ""` | `app/web/overview_api.py` `_suggest()` |
| 2 | apply 对 `not pid or not room` 的条目 **continue 静默跳过**，最后一律返回 201 + `applied_count` | `app/web/overview_api.py` `allocation_apply()` |
| 3 | apply 只读 `body["suggestions"]`，**`assignments` 被静默忽略**（调用方传了分配表仍 201/0） | 同上 |
| 4 | 空态判定不一致：suggest 返回 200（`map_id=""`），apply 返回 422 `no map for campaign` | `allocation_suggest()` vs `allocation_apply()` |

### 2.3 改法

* 新增 `_module_map_rooms(campaign)` / `_resolve_map(campaign, folded, explicit_id)`，
  由 suggest 与 apply **共用**：优先级 = 显式 `map_id` > 折叠地图 > **模组地图定义**；
  房间集合 = 折叠出的 token 房间 ∪ 模组地图声明房间。
  模组解析与 `app/web/pipeline_api.py` 的 `_module_dir/_map_id` **同源**（桌配置 `module/module_id` > 默认模组），
  不自造第二套口径；库里没有 campaign→module 表，故复用既有函数。
* **空态一致**：两个端点都走 `_resolve_map`，无地图时同为 422 `no map for campaign`。
* **一次性落位真的落位**：房间来自模组定义后，开局前也能给出真实 `to_room`；
  未落位棋子用既有 `add_token`、已在图上的用既有 `move`（都是既有 MAP_OPS，不新增 op/事件）。
* 请求体同时接受 `suggestions` 与 `assignments`；空列表 = 用服务端建议（保持既有语义）。
* **不再静默空转**：给不出房间的条目进 `skipped` 并带原因；若确有可落位条目却一条也没落成 → 422
  `allocation_apply_noop`，而不是 201 假成功。确无待落位角色时仍 201，但 `noop=true` + `reason` 明示。

响应新增字段（additive）：`map_source` / `module_id` / `rooms` / `requested_count` / `skipped` / `noop` / `reason`。

---

## 3. R35-13b —— NPC 自动叙事候选的可见性

### 3.1 判定：**是缺陷**（同一实体在创建视图与列表视图字段不一致），不是设计

实测同一时刻同一候选：

| 读口 | 是否带 `visible_to_players` |
|---|---|
| `POST /api/campaigns/{c}/npc/{id}/generate` → `proposal` | **有**，`False` |
| `POST /api/campaigns/{c}/npc_act` → 成功体 | **有**，`False`（契约骨架明文，见 `docs/R2-NPC-CONTRACT-CHANGE.md`） |
| `GET /api/campaigns/{c}/npc/proposals` → `proposals[]` | **没有该键**（`p.get(...) is None`） |
| `GET /api/campaigns/{c}/npc/state` → `pending[]` | **没有该键** |

判据 `all(x.get("visible_to_players") is False for x in proposals)` 实算为 `False`（因缺键取到 `None`）。

### 3.2 根因

`app/npc/director.py` 的 `_proposal_row()` 是列表/详情/state 三条读口的**唯一序列化器**，
它不导出该键；而创建路径在返回前**临时补写** `visible_to_players = False`。
于是「创建看到的实体」与「待审队列看到的实体」形状不同。

### 3.3 改法

在 `_proposal_row()` 内按状态统一导出 `visible_to_players`（唯一判据
`_PLAYER_VISIBLE_STATUSES = ("approved", "edited")`）：
`pending/rejected/superseded → False`，已放行状态 → `True`。
创建路径写死的 `False`（创建时状态恒为 `pending`）与之天然一致，无需改动。
additive 加键，不改 any 既有字段，不新增事件/帧。

---

## 4. 未改动清单（硬约束自查）

* 冻结 4 件未改：`app/domain/events.py`、`app/web/ws_protocol.py`、`app/web/ws_bridge.py`、`docs/CROSS-END-CONTRACT.md`。
* 未新增 WS 帧、未新增事件类型；落图只用既有 `MAP_UPDATED` + 既有 `MAP_OPS`。
* 未新增第二套审批机制。
