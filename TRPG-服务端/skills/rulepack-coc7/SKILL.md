# SKILL · rulepack-coc7（CoC7 规则包使用技能）

> 给 DSH/Agent：带这个 skill 即可正确调用本 TRPG 的 CoC7 检定链，无需读源码。

## 何时用

- 创建 CoC7 角色卡（`character_create` ruleset=coc7）
- 发起检定（`roll_check` / `roll_preview`）或解读 `CHECK_RESOLVED{rolled,total,level,seed}`

## 规则速记（`rulepacks/coc7/rulepack.yaml` v1.0.0）

- 属性 9 维 1..100（STR/CON/SIZ/DEX/APP/INT/POW/EDU/LUCK）+ SAN/HP/MP；技能 0..100，`max_skill_total: 4000`，`allow_custom_skills: false`。
- 检定三档：regular（≤技能）/ hard（≤半）/ extreme（≤五分之一）；critical 恒为 roll==1；fumble：技能≥50 时 roll==100，否则 roll≥96。
- 对抗：tie_break `[level, skill, roll]`；先攻 dex_desc + 种子 d100；默认伤害 1d6；护甲启用。
- 成长：cap 99，`roll_gt_skill` 成功涨 `1d10`。

## 调用模板

```json
// 预览（只读，不落事件）
{"name":"mcp__trpg__roll_preview","arguments":{"campaign_id":"c1","card_id":"card_x","target":"spot_hidden","difficulty":60}}
// 正式检定（KP token，落 CHECK_RESOLVED；seed 保证确定性）
{"name":"mcp__trpg__roll_check","arguments":{"actor":{"id":"kp","token":"<表token>"},"campaign_id":"c1","turn_no":1,"card_id":"card_x","target":"spot_hidden","difficulty":60,"seed":"20260919"}}
```

## 铁律

- 先掷骰后叙述（骰面决定叙事走向，不可倒置）。
- 派生值（hard/extreme/dodge）只认 `{fn: half|fifth|skill_threshold}` 注册表，YAML 里出现未知 fn 即加载拒收。
- 非法卡（缺 required_attrs / 技能越界）→ 422，按 `validation_report.errors` 逐条修。
