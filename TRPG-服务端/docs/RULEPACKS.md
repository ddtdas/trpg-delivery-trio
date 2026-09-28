# RULEPACKS.md — 规则包多版本与自动绑定（R23）

> 本轮（R2）新增。规则包从「一个隐式 CoC7 形状的配置文件」升级为
> **可声明、可扩展、可校验的多规则集数据层**，并接到开局链路上。

## 1. 已支持（已随包交付，可直接开局）

| ruleset id | 版本 | 族 / 版次 | 骰型 | 解析模型 | 属性 | 技能 | 难度 | 成长 |
|---|---|---|---|---|---|---|---|---|
| coc7 | 2.0.0 | coc / 7 | d100 | coc_percentile | 12 项（1–100 / 0–99） | 42 | regular, hard, extreme | 技能打勾 + 1d10，上限 99 |
| coc6 | 2.0.0 | coc / 6 | d100 | coc_classic | 11 项 | 47 | regular（+ 定值修正） | 技能打勾 + 1d10，上限 99 |
| dnd5e | 2.0.0 | dnd / 5e | d20 | d20_dc | 7 项（1–20，含 LEVEL） | 18 | 6 档 DC（5–30） | 等级晋升（XP 表） |
| custom | 0.0.1 | custom | d100 | coc_percentile | 1 项 | 1 | regular, hard, extreme | — |

三套规则包都完整包含：**属性表 / 技能表 / 检定与难度模型 / 伤害战斗最小闭环 / 成长规则**。

## 2. 待扩展（schema 已容纳，只差数据文件）

schema v2 不写死任何规则集。以下 id 已在
app/rules/rulepack_schema.py 的 RULESET_CATALOG 中登记为 planned，
只要按 §4 补一个 rulepack.yaml 即可启用：

| ruleset id | 族 / 版次 | 骰型 | 解析模型 | 备注 |
|---|---|---|---|---|
| coc5 | coc / 5 | d100 | coc_classic | 与 coc6 同族，直接复用 |
| dnd35 | dnd / 3.5 | d20 | d20_dc | BAB / 豁免需扩 formulas |
| dnd4e | dnd / 4e | d20 | d20_dc | 半级加值需扩 formulas |
| pf1e | pathfinder / 1e | d20 | d20_dc | 与 dnd35 同构 |
| pf2e | pathfinder / 2e | d20 | d20_dc | 四级成功度需扩解析模型 |

扩展方向（schema 已预留字段）：
- 新解析模型：在 RESOLUTION_MODELS 增加枚举 + 在 resolver.py 增加分支
- 新派生公式：在 formulas.py 的 FORMULA_REGISTRY 增加纯函数
- 新骰型/成功度分层：resolution 块内声明

## 3. schema v2 字段说明

rulepacks/<ruleset_id>/rulepack.yaml

    schema: 2                     # app.rules 读这个（int）；缺省视为 1
    schema_version: "2.0.0"       # 仓库索引器读这个（str）；两者必须一致
    id: coc7                      # 必须与目录名一致
    version: "2.0.0"
    display_name: "..."
    license: "..."

    ruleset:                      # 【v2 新增】声明「我是谁、怎么判」
      family: coc                 # coc | dnd | pathfinder | custom
      edition: "7"
      dice: d100
      resolution_model: coc_percentile

    attrs:                        # 属性表
      - {name: STR, min: 1, max: 100, abbr: "Strength", roll: "3d6x5"}

    skills:                       # 技能表（基础值，int 0..100，与 v1 同形）
      spot_hidden: 25

    skill_meta:                   # 【v2 新增】技能 → 主属性 / 分类（描述性）
      spot_hidden: {attr: "-", category: perception}

    checks:                       # v1 兼容块
      difficulties: [regular, hard, extreme]

    resolution:                   # 【v2 新增】引擎实际分派的判据
      model: coc_percentile       # 必须与 ruleset.resolution_model 一致
      difficulties: [regular, hard, extreme]
      critical: roll_eq_1
      fumble_skilled_threshold: 50

    combat:                       # 战斗最小闭环
      initiative: {order_by: dex_desc, tie_break: seeded_d100}
      attack_default: fighting_brawl
      defense_default: dodge
      damage_default: "1d6"
      armor: {enabled: true}
      major_wound: {enabled: true, threshold_divisor: 2}

    growth:                       # 成长规则
      model: skill_mark_roll_over # | level_advancement | none
      cap: 99
      gain: "1d10"

    formulas:                     # 【v2 新增】按规则集派生的角色卡字段
      hp_max: {fn: coc_hp_max, args: {con: $CON, siz: $SIZ}}

    card_rules:                   # 建卡硬门
      required_attrs: [STR, CON, SIZ, DEX, APP, INT, POW, EDU]
      skill_min: 0
      skill_max: 100
      allow_custom_skills: false
      max_skill_total: 4000

### 3.1 为什么 skills 保持 int 形状

v1 的 app/rules/arbiter.py 要求 skills 的值是 int 0..100。v2 **不改这一形状**，
只把丰富信息放到并列的 skill_meta 里。结果是：三套 v2 规则包**仍能被旧的
Arbiter 原样加载**（见 tests/test_rulepacks_v2.py::test_v1_arbiter_still_loads_every_pack），
历史链路零回归。

### 3.2 formulas 与 v1 derived 的区别

- derived（v1，保留）：只认 4 个函数（half / fifth / add / skill_threshold），
  由 Arbiter.derived() 消费，CoC7 专用。
- formulas（v2，新增）：由 app/rules/formulas.py 的 FORMULA_REGISTRY 消费，
  按规则集提供不同派生字段（CoC 的 HP/MP/SAN/MOV/Build，d20 的属性调整值/
  熟练加值/HP/AC/先攻/法术 DC/18 项技能加值）。

**声明顺序有意义**：后面的公式可以 $ref 前面已算出的公式
（例如 hp_max 引用 con_mod）。

### 3.3 取值优先级

角色卡上的显式值 > formulas 派生值 > 规则包 skills 基础值。

即：玩家自己写了的技能，永远覆盖推导；没写的，用规则包基础值兜底。

## 4. 新增一个规则集（3 步）

1. 建目录 rulepacks/<id>/rulepack.yaml，照 §3 填写；ruleset.resolution_model
   必须是 RESOLUTION_MODELS 之一。
2. 若需要新派生字段，在 app/rules/formulas.py 的 FORMULA_REGISTRY 加纯函数。
3. 跑 python -m pytest tests/test_rulepacks_v2.py，并把 id 从 planned 挪到
   packaged（app/rules/rulepack_schema.py 的 RULESET_CATALOG）。
4. **必须**调用 POST /api/repository/rebuild 刷新 rulepacks/index.json：
   索引里的 sha256 是**目录摘要**，绑定 rulepacks/<id>/ 的全部内容，
   改了任何一个字节都会让 digest 与 fingerprint 双双失配。

规则包目录名与 YAML 里的 id 必须一致；不一致会被标为 invalid 并返回
RULEPACK_INVALID，而不是静默采用其中一个。

## 5. 自动绑定（R23 核心）

模组清单 modules/<id>/module.yaml 里声明 ruleset：

    id: sample_coc
    ruleset: coc7

开局时服务端按该字段自动绑定规则包：

    from app.rules import binding
    bound = binding.bind_manifest(manifest)      # -> {ruleset, resolution_model, ...}
    payload = binding.open_table(manifest, card, ruleset_override="dnd5e")

同一个模组用不同 ruleset 开局，属性名、属性范围、技能数、难度档、
成长模型、派生公式**全部不同**（见 §7 实测）。

### 5.1 未知 ruleset：明确报错，不降级

未知 ruleset 抛 RulesetBindingError，携带稳定错误码，**没有任何兜底路径**：

| 错误码 | 触发条件 |
|---|---|
| RULEPACK_UNKNOWN_RULESET | 仓库里没有该规则包（含 planned 但未落地的） |
| RULEPACK_INVALID | 规则包存在但校验失败，或目录名与 id 不一致 |
| RULEPACK_NO_RULESET_DECLARED | 清单没有 ruleset 字段 |
| RULEPACK_MANIFEST_INVALID | 清单本身不是 mapping / module_id 非法 |
| RULEPACK_SCHEMA_UNSUPPORTED | schema 版本不支持 |
| RULEPACK_FIELD_MISSING / RULEPACK_FIELD_INVALID | v2 必填块缺失 / 类型错 |
| RULEPACK_FORMULA_UNKNOWN | formulas 引用了未注册的 fn |
| RULEPACK_RESOLUTION_MODEL_UNKNOWN | 未注册的解析模型 |
| RULEPACK_DIFFICULTY_UNKNOWN | 请求了该规则集未声明的难度档 |

错误体同时返回 available_rulesets 与 planned_rulesets，调用方可以直接看到
「有哪些可用」。别名（dnd → dnd5e）是**声明式**的，会在响应里回显
alias_applied，不构成静默替换。

## 6. HTTP 接口（additive，/api/rules/*）

与 T1 的 /api/rulepacks（仓库侧：列表/读/写/软删/索引）**命名空间不重叠**。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/rules/catalog | 已支持 / 待扩展清单 + 别名表 |
| GET | /api/rules/rulesets | 仓库可用列表 + index 负载 |
| GET | /api/rules/rulesets/{ruleset} | 单个规则包的声明与字段 |
| POST | /api/rules/bind | 按 ruleset 或 module_id 绑定 |
| POST | /api/rules/open | 开局并返回绑定后的字段/公式负载 |

失败一律 4xx + 错误码（未知 ruleset 返回 404），**不会 500，也不会静默降级**。

## 7. 实测对照（原始输出摘要）

同一模组 modules/sample_coc，分别以 coc7 / dnd5e 开局：

    resolution_model   : coc_percentile            vs  d20_dc
    attr names         : STR CON SIZ DEX APP INT POW EDU LUCK SAN HP MP
                       : STR DEX CON INT WIS CHA LEVEL
    attr ranges        : (0,99) (1,100)            vs  (1,20)
    skill count        : 42                        vs  18
    difficulties       : regular hard extreme      vs  very_easy ... nearly_impossible
    growth model       : skill_mark_roll_over      vs  level_advancement
    coc7 formulas      : hp_max=13 mp_max=14 san_start=70 mov=7 build=0
                         damage_bonus="0" dodge_default=27 spot_hidden_hard=22
    dnd5e formulas     : str_mod=3 prof_bonus=2 hp_max=24 ac=12 initiative=2
                         attack=5 spell_dc=11 passive_perception=13 athletics=5

复现：

    python scripts/rules_probe.py         # 规则层全量（含索引/兼容/报错）
    python scripts/rules_http_probe.py    # 真实 ASGI 路由 + HTTP 状态码
    python -m pytest tests/test_rulepacks_v2.py -q

## 8. 版权

规则包只包含引擎需要的**数值表与公式**，不含任何受版权保护的规则正文。
dnd5e 的数值取自 SRD 5.1（CC-BY-4.0）；CoC 各版仅收录自建数值表，
未复制 Chaosium 规则文本。各规则包 license 字段已逐包注明。
