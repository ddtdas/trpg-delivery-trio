# 新增端点精确规格（ENDPOINT-SPEC-NEW v1.4 · 冻结）

> 产出：T1（planner）。本文是 **T2 的实现规格**与 **T6 的验收依据**；与 docs/CROSS-END-CONTRACT.md v1.1 配套，二者冲突时以本文为准（本文更具体）。
> 全部为 **additive**：不改任何既有端点签名与行为，不新增 WS 帧，不动 /app。
> 证据与实测基线见 evidence/T1-contract.txt。

---

## 0. 通则

### 0.1 成功/失败包裹（/access 层）
- 成功：HTTP 200 + {"ok":true,"data":{…},"code":0}
- 失败：HTTP <4xx> + {"ok":false,"error":"<文本>","code":<http>}（扁平，无 detail 嵌套）
- **/access 层成功一律返回 HTTP 200**（不用 201），以便两端统一判断 ok。

### 0.2 鉴权辅助函数复用（**关键，含一个必须避开的陷阱**）

既有实现（app/web/access.py，实测行号）：

| 辅助 | 行号 | 语义 |
|---|---|---|
| _require_end(end) | 207 | 该端 token 正确 → 通过；**其余一切情况（含"合法但属于别的端"的 token）→ 401 "bad or missing token"** |
| _require_any_end | 247 | 任一启用端 token 通过；否则 401 |
| _require_kp_end | 262 | webapp(KP) 通过；**其它启用端 token → 403 kp_only**；无/错 token → 401 |
| _require_recorder_end | 289 | recorder 通过；**其它启用端 token → 403 recorder_only**；无/错 token → 401 |

> ⚠️ **陷阱（会让 AC-1.6 直接 FAIL）**：_require_end 对"合法但端不匹配"的 token 返回的是 **401**，不是 403。
> 因此 **POST /access/player/audio 不能直接用 _require_end("mobile")**，否则 webapp token 会得到 401，而 AC-1.6 要求 **403**。
> 必须按既有 *_only 家族的模式新增一个同构的 **`_require_player_end`**（403 mobile_only），实现与 _require_recorder_end 完全同构：

~~~python
def _require_player_end(authorization: str | None = Header(default=None),
                        token: str | None = Query(default=None)) -> dict[str, Any]:
    """玩家端专属端鉴权 (player audio)：mobile 通过；
    其它启用端 token 显式 403 mobile_only；无/错 token -> 401。
    与 _require_recorder_end / _require_kp_end 同构。"""
    cfg = _load_config()
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if token:
        provided = token
    entry = _matches_any_enabled_end(provided, cfg)
    if entry is None:
        _raise(CODE_AUTH, "bad or missing token")          # 401
    ends = cfg.get("ends") or {}
    if entry is ends.get("mobile"):
        return entry
    _raise(CODE_FORBIDDEN, "mobile_only")                  # 403
~~~

（若 T2 选择别的等价实现，**必须满足 §2 的鉴权矩阵**，实现方式不限。）

### 0.3 鉴权矩阵（**AC-1.6 逐格判据**）

| 端点 | 无 token | mobile token | webapp token | recorder token |
|---|---|---|---|---|
| GET /player/ 与 /player/{path} | 200 / 404（**无鉴权**） | 同左 | 同左 | 同左 |
| GET /access/table/resolve | **401** | **200** | **200** | **200** |
| POST /access/player/audio | **401** | **200** | **403 mobile_only** | **403 mobile_only** |
| POST /access/host/table | **401** | **403 kp_only** | **200** | **403 kp_only** |
| POST /access/host/turn | **401** | **403 kp_only** | **200** | **403 kp_only** |

token 传递：?token=<t> 或 Authorization: Bearer <t>，两者等价。

---

## 1. GET /player/ 与 GET /player/{path}

| 项 | 规格 |
|---|---|
| 鉴权 | **无** |
| 目录 | APP_ROOT/player-web/（新增目录） |
| /player/ | 返回 player-web/index.html，200，Content-Type text/html; charset=utf-8 |
| /player/{path} | 按扩展名返回静态文件：.css → text/css、.js → application/javascript、.json → application/json、.html → text/html、.svg → image/svg+xml、其它 → application/octet-stream |
| 缺文件 | **404**，响应体 {"error":"player_not_built"}（**不是** {ok,...} 包裹：本层属静态层） |
| 路径穿越 | 含 .. 或解析后逃出 player-web/ 的请求 → **404**（同缺文件体） |
| 既有行为 | **不得改动 /app 与 /app/{path}**；两套挂载互不影响 |

> 与既有 /app 的挂载实现（app/web/static.py 的 mount_static）保持同一风格，新增独立挂载，不改既有函数签名。

**验收命令（远程）**
~~~powershell
$b='http://127.0.0.1:9210'
(Invoke-WebRequest -UseBasicParsing "$b/player/").StatusCode
(Invoke-WebRequest -UseBasicParsing "$b/player/app.css").StatusCode
try { Invoke-WebRequest -UseBasicParsing "$b/player/nope.js" } catch { $_.Exception.Response.StatusCode.value__ }
(Invoke-WebRequest -UseBasicParsing "$b/app/").StatusCode
~~~

**期望**：200 / 200 / 404 / 200

---

## 2. GET /access/table/resolve?code=

| 项 | 规格 |
|---|---|
| 鉴权 | _require_any_end（任一启用端） |
| query | code（必填，min_length=1） |
| 缺 code / code 为空 | **400**，error "code required" |
| 大小写 | **不敏感**（trim 后大写比较） |
| 解析顺序 | ① 与 TABLES 的 table_id 精确匹配（大小写不敏感）→ ② 与 TABLES[t].config.code 匹配 → ③ 回退：把 code 直接当作 table_id/campaign |
| 命中 | 200，data.exists=true |
| 未命中 | **200**，data.exists=false（**不是 404**：客户端据此显示 err.notFound，而非网络错误） |

**返回 data**
~~~json
{
  "code": "TABLE-0001",
  "table_id": "t_acc",
  "campaign": "c_acc",
  "name": "示例桌",
  "exists": true
}
~~~
未命中时：{"code":"TABLE-0001","table_id":"","campaign":"","name":"","exists":false}

字段口径：table_id = TABLES 的键；campaign = TABLES[table_id]["campaign_id"]；name = TABLES[table_id].get("name") 或回退 table_id（**永不返回 null**）。

**验收命令**
~~~powershell
$b='http://127.0.0.1:9210'; $t='<MOBILE_TOKEN>'
(Invoke-WebRequest -UseBasicParsing "$b/access/table/resolve?code=t_acc&token=$t").Content
(Invoke-WebRequest -UseBasicParsing "$b/access/table/resolve?code=NOPE-XXXX&token=$t").Content
try { Invoke-WebRequest -UseBasicParsing "$b/access/table/resolve?code=t_acc" } catch { $_.Exception.Response.StatusCode.value__ }
~~~

**期望**：exists=true ／ exists=false（均 200）／ 401

---

## 3. POST /access/player/audio

| 项 | 规格 |
|---|---|
| 鉴权 | **_require_player_end**（mobile 200；其它启用端 403 mobile_only；无 token 401） |
| 请求 | multipart/form-data |
| 字段 | file（必填，UploadFile）、campaign（必填，Form）、kind（Form，默认 "voice"）、player_id（Form，默认 "pl_mobile"） |
| 参数错误 | campaign 为空 → **400** "campaign required"；file 为空（0 字节）→ **400** "empty file" |
| 落盘 | APP_ROOT/data/audio_import/<campaign>__<epoch秒>__<安全文件名>（文件名仅保留字母数字与 . _ -）；落盘失败**不阻断**（file_ref 返回 ""） |
| 事件 | 追加 TRANSCRIPT_APPENDED：payload.seg.speaker=player_id、payload.source="import"；随后**后台任务**再追加一条 source="stt"（STT 不可用时写降级占位文本，不阻断） |
| token 隔离 | **服务端内部**以 recorder 语义落库；recorder token **绝不返回给客户端、绝不写入日志**；客户端只持有 mobile token |
| 幂等 | 无（音频是追加语义，重复上传即两条事件） |

**返回 data（与 /access/audio_upload 同构）**
~~~json
{
  "seq": 12,
  "job": { "job_id": "job_import_1790295380", "status": "done" },
  "bytes": 20480,
  "kind": "voice",
  "file_ref": "C:\\...\\data\\audio_import\\c_acc__1790295380__voice.webm",
  "stt": { "status": "queued" }
}
~~~
stt.status 取值：queued ／ done ／ degraded（后台完成后变为 done 或 degraded）。

**验收命令**
~~~powershell
$b='http://127.0.0.1:9210'; $m='<MOBILE_TOKEN>'; $w='<WEBAPP_TOKEN>'
$f="$env:TEMP\v.webm"; [IO.File]::WriteAllBytes($f,[byte[]](1..64))
curl.exe -s -X POST "$b/access/player/audio?token=$m" -F "file=@$f" -F "campaign=c_acc" -F "kind=voice" -F "player_id=pl-001"
curl.exe -s -o NUL -w "%{http_code}" -X POST "$b/access/player/audio?token=$w" -F "file=@$f" -F "campaign=c_acc"
curl.exe -s -o NUL -w "%{http_code}" -X POST "$b/access/player/audio" -F "file=@$f" -F "campaign=c_acc"
~~~

**期望**：200 + ok:true ／ 403 ／ 401

---

## 4. POST /access/host/table

| 项 | 规格 |
|---|---|
| 鉴权 | _require_kp_end（webapp 200；mobile/recorder 403 kp_only；无 token 401） |
| 请求 | application/json |
| body | table_id（必填）、campaign_id（必填）、ruleset（可选，默认 "coc7"）、name（可选，默认取 table_id） |
| 参数错误 | table_id 或 campaign_id 为空 → **400** "table_id/campaign_id required" |
| 冲突 | table_id 已存在且 **campaign_id 不同** → **409** "table exists" |
| 幂等 | table_id 已存在且 **campaign_id 相同** → **200** + created:false（**返回既有记录，不报错**）；新建 → created:true。此幂等规则是**有意 additive 的选择**：保证验收脚本可重复执行（T6 可反复开桌），同时保留既有 409 冲突语义。 |
| 复用 | 复用 app/web/rest.py 既有 table 创建语义（TABLES 注册表结构一致） |

**返回 data**
~~~json
{
  "table_id": "t_acc",
  "campaign_id": "c_acc",
  "ruleset": "coc7",
  "name": "示例桌",
  "exists": true,
  "created": true
}
~~~

**验收命令**
~~~powershell
$b='http://127.0.0.1:9210'; $w='<WEBAPP_TOKEN>'; $m='<MOBILE_TOKEN>'
$body='{"table_id":"t_acc","campaign_id":"c_acc","name":"示例桌"}'
Invoke-WebRequest -UseBasicParsing -Method POST "$b/access/host/table?token=$w" -ContentType application/json -Body $body | ForEach-Object { $_.StatusCode; $_.Content }
Invoke-WebRequest -UseBasicParsing -Method POST "$b/access/host/table?token=$w" -ContentType application/json -Body $body | ForEach-Object { $_.Content }
try { Invoke-WebRequest -UseBasicParsing -Method POST "$b/access/host/table?token=$m" -ContentType application/json -Body $body } catch { $_.Exception.Response.StatusCode.value__ }
try { Invoke-WebRequest -UseBasicParsing -Method POST "$b/access/host/table" -ContentType application/json -Body $body } catch { $_.Exception.Response.StatusCode.value__ }
~~~

**期望**：200 created:true ／ 200 created:false（重复调用）／ 403 ／ 401

---

## 5. POST /access/host/turn

| 项 | 规格 |
|---|---|
| 鉴权 | _require_kp_end（webapp 200；mobile/recorder 403 kp_only；无 token 401） |
| 请求 | application/json |
| body | campaign（必填）、window_sec（可选，默认 300，合法范围 5..3600 的整数）、turn_no（可选）、req_id（可选，幂等键） |
| 参数错误 | campaign 为空 → **400** "campaign required"；window_sec 非整数或越界 → **400** "invalid window_sec" |
| 语义 | **开启行动窗**，使 GET /access/mobile/state?table_id=<t> 的 turn.state == **"COLLECTING"**。复用既有 turn_window / command_bus 语义（dispatch START_TURN），**不新造状态、不新增事件类型** |
| 幂等 | ① 同一 req_id 重复 → 返回上次结果，**不重复开启**；② 当前 turn.state 已是 COLLECTING → **不新开回合**，直接返回当前回合（already_collecting:true）。此规则保证验收中"开一次窗 + 两端各提交一次"精确产生 2 条 ACTION_SUBMITTED（AC-3.11）。 |

**返回 data（v1.3 按队长裁决更正 —— `countdown_end_ts` 为 ISO 字符串）**
~~~json
{
  "campaign": "c_acc",
  "table_id": "t_acc",
  "turn_no": 1,
  "state": "COLLECTING",
  "countdown_end_ts": "2026-09-25T02:44:33.425567+00:00",
  "countdown_end_ts_epoch": 1790304273,
  "window_sec": 600,
  "already_collecting": false,
  "status": "ok",
  "seq": 497
}
~~~
table_id 由 campaign 反查 TABLES 得到，查不到返回 ""（不报错）。

⚠️ **`countdown_end_ts` 的类型在两个命名空间**不同，客户端**勿混用**（v1.3 明确）：

| 出现位置 | 类型 | 依据 |
|---|---|---|
| `/access/host/turn` 响应 | **ISO 字符串**（如 `"2026-09-25T02:44:33.425567+00:00"`） | 与落库冻结事件 **`TurnStarted.countdown_end_ts: str`**（app/domain/events.py）**同值同型**；队长裁决 2026-09-25 |
| **WS 帧 `TurnInfo.countdown_end_ts`**（TURN_UPDATED） | **整数**（epoch 秒） | 冻结件 `app/web/ws_protocol.py`（**不可改**） |

- 为便于客户端，响应**额外提供 additive 整数字段 `countdown_end_ts_epoch`**（epoch 秒）。
- **T1 实测复核（2026-09-25）**：`POST /access/host/turn`（campaign=c_demo，已在 COLLECTING）→ `countdown_end_ts` = `"2026-12-31T23:59:59+00:00"`（**str**）、`countdown_end_ts_epoch` = `1798761599`（**int**），且 `already_collecting:true`（幂等未新开回合）。
- 📌 **给 T6 的提醒**：验收脚本**不得**断言 `countdown_end_ts` 为整数 —— 那是旧示例的写法（若按旧示例断言会**误报 FAIL**）。整数请用 `countdown_end_ts_epoch`。

**验收命令**
~~~powershell
$b='http://127.0.0.1:9210'; $w='<WEBAPP_TOKEN>'; $m='<MOBILE_TOKEN>'
Invoke-WebRequest -UseBasicParsing -Method POST "$b/access/host/turn?token=$w" -ContentType application/json -Body '{"campaign":"c_acc","window_sec":300}' | ForEach-Object { $_.Content }
(Invoke-WebRequest -UseBasicParsing "$b/access/mobile/state?table_id=t_acc&token=$m").Content
try { Invoke-WebRequest -UseBasicParsing -Method POST "$b/access/host/turn?token=$m" -ContentType application/json -Body '{"campaign":"c_acc"}' } catch { $_.Exception.Response.StatusCode.value__ }
~~~

**期望**：state=COLLECTING ／ mobile state 的 turn.state=COLLECTING ／ 403

---

## 6. 一次性鉴权矩阵验收脚本（AC-1.6 逐格）

~~~powershell
$b='http://127.0.0.1:9210'
$m='<MOBILE_TOKEN>'; $w='<WEBAPP_TOKEN>'; $r='<RECORDER_TOKEN>'
function Code($url,$method='GET',$body=$null){
  try { if($body){ (Invoke-WebRequest -UseBasicParsing -Method $method $url -ContentType application/json -Body $body).StatusCode }
        else { (Invoke-WebRequest -UseBasicParsing -Method $method $url).StatusCode } }
  catch { $_.Exception.Response.StatusCode.value__ }
}
$f="$env:TEMP\v.webm"; [IO.File]::WriteAllBytes($f,[byte[]](1..64))
"resolve none=" + (Code "$b/access/table/resolve?code=t_acc")
"resolve mobile=" + (Code "$b/access/table/resolve?code=t_acc&token=$m")
"resolve webapp=" + (Code "$b/access/table/resolve?code=t_acc&token=$w")
"host/table none=" + (Code "$b/access/host/table" 'POST' '{"table_id":"tx","campaign_id":"cx"}')
"host/table mobile=" + (Code "$b/access/host/table?token=$m" 'POST' '{"table_id":"tx","campaign_id":"cx"}')
"host/table webapp=" + (Code "$b/access/host/table?token=$w" 'POST' '{"table_id":"tx","campaign_id":"cx"}')
"host/turn none=" + (Code "$b/access/host/turn" 'POST' '{"campaign":"cx"}')
"host/turn mobile=" + (Code "$b/access/host/turn?token=$m" 'POST' '{"campaign":"cx"}')
"player/audio none=" + (curl.exe -s -o NUL -w "%{http_code}" -X POST "$b/access/player/audio" -F "file=@$f" -F "campaign=cx")
"player/audio webapp=" + (curl.exe -s -o NUL -w "%{http_code}" -X POST "$b/access/player/audio?token=$w" -F "file=@$f" -F "campaign=cx")
"player/audio mobile=" + (curl.exe -s -o NUL -w "%{http_code}" -X POST "$b/access/player/audio?token=$m" -F "file=@$f" -F "campaign=cx")
~~~

**期望**：401 / 200 / 200 ／ 401 / 403 / 200 ／ 401 / 403 ／ 401 / 403 / 200

---

## 7. T2 实现清单（对照）

1. app/web/static.py：新增 /player/ 与 /player/{path}（§1）；**不改既有 /app 行为**。
2. app/web/access.py：新增 _require_player_end（§0.2）+ 4 个端点（§2–§5）。
3. server/player-web/：占位 index.html（内容「玩家端未部署」）；若 T3 已产出真实文件则采用 T3 的，**不要覆盖**。
4. tests/test_access_player_endpoints.py：覆盖 §6 全部格子 + 参数校验 + 幂等（player/audio 无 token 401 / webapp 403 / mobile 200；host/* 无 token 401 / mobile 403 / webapp 200；table/resolve 401 与 200）。
5. python -m pytest tests/ -q 必须全绿，且**既有用例数不减少**。

---

## 8. T2 追加要求（队长裁决 2026-09-25）：WS 广播发布路径（additive）

背景：T1 实测（**当时**）生产路径**从不调用 Hub.publish**，8 类下行帧永不出现（证据 evidence/T1-contract.txt §5）。**该状态已于 2026-09-25 改变**：本节要求的 additive 发布路径已由 T2 落地并**实测生效**（WS 收到业务帧），故「从不 publish」只描述 T1 测量时点（详见契约 §3.4.2/§3.4.4）。队长裁决采纳**方案 A**：由 T2 追加 additive 发布路径使 WS 广播可用，同时**保留轮询为主通道**（契约 §3.4.1）。

| 项 | 要求 |
|---|---|
| 单一收口 | 只在 **EventStore.append** 这一个收口处触发发布，**禁止**在各业务分支散点调用 |
| best-effort | 发布失败**不得**影响事件落库与 HTTP 响应（try/except 兜底，**绝不向调用方抛出**） |
| 帧复用 | **严格复用冻结 8 帧**（app/web/ws_protocol.py 的 ServerFrame）；**不得新增帧类型**、不得改帧字段（ws_protocol.py 是冻结契约 6 项之一，sha256 必须不变） |
| 失败回退 | 无法映射为具体 8 帧类型时，回退为 **STATE_DELTA(event)**，保证前端至少能感知变化 |
| 失败回退·**脱敏（v1.2 强化；**v1.4 经队长裁决定稿**）** | ⚠️ **回退帧一律不得携带事件 payload**，统一 `value={type, redacted:true}`（只保留 `field="event"` 与 `type`，详情由轮询通道提供）。理由：**STATE_DELTA 是房间级广播**（见下行「可见性」行），而冻结事件含 KP 专属/目标专属/私密类型；带 payload 等于**向全体玩家泄密**。**不采用「按类型白名单放行 payload」**——域事件类型约 40 种且会新增，白名单必然漂移。 |
| 注入机制（v1.2 记录，**勿简化**） | 发布回调必须挂在 **`EventStore.on_append` 类属性（`ClassVar`）**，由 `app/main.py` 的 lifespan 注入。**不可改为实例属性**：`app/web/rest.py:88-89` 的 `_store()` **每次调用都新建 `EventStore` 实例** → 实例属性无法跨请求生效。另注意**描述符绑定陷阱**：把普通函数赋给类属性后 `self.on_append` 会变成 bound method（`self` 被当作第一个参数）→ 必须用 **`type(self).on_append`** 取。 |
| STATE_DELTA 的实际可见性（v1.2 明确） | 冻结件 `runtime-contract.md` 写 STATE_DELTA 为 scope=viewer「可见子集」，但 Hub 的 `viewer_may_see`（app/web/ws.py）**只过滤 WHISPER / NARRATION_PENDING / JOB_STATUS** → **STATE_DELTA 实际是房间级广播**。故：**发布路径不得在 STATE_DELTA 里携带任何非 public 的事件详情**。 |
| 隔离 | 不得改 /app；不得改变既有 /access 11 端点行为；不得改冻结契约 6 项 |
| 重放 | 发布后房间日志非空，重连带 last_seq 应能重放；两端按契约 §3.4.2 合并渲染并按 seq 去重 |
| 验收 | 发布路径可用 → AC-3.13 按实时达标；不可用 → 按「≤5s 轮询可见」达标（契约 §3.4.3） |

> 注意：该路径是**增强**，不是依赖。**两端在任何情况下都必须实现 §3.4.1 轮询**，且 WS 失败必须静默降级（不得报错、不得改文案）。

### 8.1 若坚持「按类型放行 payload」，白名单至少须包含以下私密类型（**T1 复核补充**）

T2 首版白名单为 9 类：`TRUTH_REVEALED / EVIDENCE_DEALT / CLUE_GRANTED / VOTE_CAST / NPC_ACT_PROPOSED / NPC_ACT_APPROVED / TRANSCRIPT_APPENDED / SESSION_SUMMARIZED / EVENT_INJECTED`。
**T1 复核发现该表不完整**，以下类型同样含 KP 专属/目标专属/私密内容，一旦走回退路径且带 payload 即会房间级泄露：

| 类型 | 为何私密 |
|---|---|
| **`NARRATION_PROPOSED`** | 映射后是 **`NARRATION_PENDING`（scope=kp）**；回退成 STATE_DELTA 会把**未审旁白全文**广播给全体玩家（**风险最高**） |
| `NARRATION_EDITED` / `NARRATION_REJECTED` | 同样含未公开旁白文本 |
| `INFO_REVEALED` | 自带 `scope`(public/whisper/condition) 与 `targets`；回退帧不做目标过滤 → 私语/条件信息的指针泄露 |
| `ROLE_ASSIGNED` | 含 **`secret_ref`（KP 专属指针，visibility.py 明示指针本身即 KP-only）** |
| `CHECK_RESOLVED` | 含 **`seed`**（骰点种子）→ 泄露可预测掷骰，属公平性/完整性风险 |
| `MAP_UPDATED` | 地图可见性可为 whisper/private（`can_see_map`） |

> ✅ **因此仍推荐最简且最稳的做法：回退帧一律不带 payload**（上表即为其必要性证据）。若 T2 坚持带 payload，请按本表**补齐白名单**，并补一条**防漂移**断言（域事件类型新增时白名单需同步）。

### 8.2 版本

| 版本 | 日期 | 变更 |
|---|---|---|
| **v1.2** | 2026-09-25 | 采纳 server-eng 的实现反馈：① **失败回退脱敏强化**为「一律不带 payload」（附私密类型清单与理由）；② 新增**注入机制**记录（`ClassVar` + `type(self).on_append`，勿简化为实例属性）；③ 明确 **STATE_DELTA 实为房间级广播**。 |
| v1.1 | 2026-09-25 | 新增 §8「T2 追加要求：WS 广播发布路径（additive）」。 |

---

## 9. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| **v1.1** | 2026-09-25 | 新增 §8「T2 追加要求：WS 广播发布路径（additive）」，落实队长 AC-3.13 方案 A 裁决（EventStore.append 单一收口 + best-effort hub.publish + 严格复用冻结 8 帧 + 失败回退 STATE_DELTA(event)）；明确该路径为增强、轮询恒为主通道。 |
| v1.0 | 2026-09-25 | 首版：5 个新增端点的请求/响应/错误码/鉴权矩阵/幂等语义 + 可直接执行的验收命令；标注 _require_end 401-vs-403 陷阱与 _require_player_end 实现。 |
